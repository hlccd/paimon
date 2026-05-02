"""风神 · 订阅采集 mixin：collect_subscription 入口 + impl + 空跑占位 + web_search 调用。"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from paimon.foundation.march import today_local_bounds

from ._models import _DEDUP_WINDOW_SECONDS, _SKILL_SEARCH_PY, _WEB_SEARCH_TIMEOUT

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.march import MarchService
    from paimon.llm.model import Model


class _CollectMixin:
    """订阅采集相关方法集合。"""

    async def collect_subscription(
        self, sub_id: str, *,
        irminsul: Irminsul,
        model: Model,
        march: MarchService,
    ) -> None:
        """订阅采集 dispatcher：按 sub.binding_kind 路由到对应 collector。

        - 'manual'（默认）→ 风神特化版（含事件聚类 + p0 预警，_collect_subscription_impl）
        - 'mihoyo_game' → 水神 light 版（run_web_search_collect，无聚类）
        - 其他 archon 注册的 binding_kind → 各自 collector

        旧链路（feed_collect ScheduledTask）由 bootstrap._on_march_ring 触发，
        所有 binding_kind 都走这里 dispatch；inflight 防重在 dispatcher 层做。
        """
        if sub_id in self._inflight:
            logger.info("[风神·订阅] 已在采集中，跳过重复触发 sub={}", sub_id)
            return
        self._inflight.add(sub_id)
        try:
            sub = await irminsul.subscription_get(sub_id)
            if not sub:
                logger.warning("[风神·订阅] 订阅不存在 sub_id={}", sub_id)
                return
            from paimon.foundation import subscription_types
            kind = sub.binding_kind or "manual"
            meta = subscription_types.get(kind)
            if meta is None:
                logger.warning(
                    "[风神·订阅] 未知 binding_kind={}, fallback 走 manual 风神原版",
                    kind,
                )
                await self._collect_subscription_impl(
                    sub_id, irminsul=irminsul, model=model, march=march,
                )
                return
            # 通过 state 调 collector（签名 (sub, state)）
            from paimon.state import state as _state
            await meta.collector(sub, _state)
        finally:
            self._inflight.discard(sub_id)

    async def _collect_subscription_impl(
        self, sub_id: str, *,
        irminsul: Irminsul,
        model: Model,
        march: MarchService,
    ) -> None:
        logger.info("[风神·订阅] 开始采集 sub_id={}", sub_id)

        sub = await irminsul.subscription_get(sub_id)
        if not sub:
            logger.warning("[风神·订阅] 订阅不存在 sub_id={}", sub_id)
            return
        if not sub.enabled:
            logger.info("[风神·订阅] 订阅已禁用 sub_id={}", sub_id)
            return

        source_label = f"风神·订阅·{(sub.query or '未命名')[:20]}"

        # Step 2: 搜索
        try:
            results = await self._run_web_search(sub.query, sub.max_items, sub.engine)
        except Exception as e:
            logger.error("[风神·订阅] 搜索失败 sub={} err={}", sub_id, e)
            await irminsul.subscription_update(
                sub_id, actor="风神", last_error=str(e)[:500],
            )
            return

        if not results:
            logger.info("[风神·订阅] 搜索无结果 sub={} query='{}'", sub_id, sub.query)
            await self._write_empty_run_marker(
                sub, source_label=source_label,
                irminsul=irminsul, march=march, reason="search_empty",
            )
            await irminsul.subscription_update(
                sub_id, actor="风神",
                last_run_at=time.time(), last_error="",
            )
            return

        # Step 3: 去重
        since_ts = time.time() - _DEDUP_WINDOW_SECONDS
        existing = await irminsul.feed_items_existing_urls(sub_id, since_ts=since_ts)
        new_items = [r for r in results if (r.get("url") or "") not in existing]

        # Step 3.5: 没新条目时是否能直接退出？
        # 当天已有同源 digest → touch 刷时间戳（不重 LLM / 不重置红点）
        # 当天没有 digest → 尝试用今日累计兜底合成
        day_start, day_end = today_local_bounds()
        if not new_items:
            existing_today = await irminsul.push_archive_list(
                actor="风神", since=day_start, until=day_end, limit=20,
            )
            has_today_digest = any(r.source == source_label for r in existing_today)
            if has_today_digest:
                logger.info(
                    "[风神·订阅] 无新条目且当天已有 digest sub={} total={}（touch）",
                    sub_id, len(results),
                )
                await self._write_empty_run_marker(
                    sub, source_label=source_label,
                    irminsul=irminsul, march=march,
                    reason="filtered_out_has_digest",
                )
                await irminsul.subscription_update(
                    sub_id, actor="风神",
                    last_run_at=time.time(), last_error="",
                )
                return
            logger.info(
                "[风神·订阅] 无新条目但当天还没 digest，尝试用累计数据补合成 sub={}",
                sub_id,
            )

        records: list = []
        inserted_ids: list = []
        if new_items:
            logger.info(
                "[风神·订阅] 新条目 {} 条 / 总 {} 条 sub={}",
                len(new_items), len(results), sub_id,
            )
            # Step 4: 落库（拿到 records 含 db id + 原字段，给 4.5 用）
            records = await irminsul.feed_items_insert_with_records(
                sub_id, new_items, actor="风神",
            )
            if not records:
                logger.warning("[风神·订阅] 条目入库 0 条 sub={}", sub_id)
                return
            inserted_ids = [r["id"] for r in records]

        # Step 4.5: 事件聚类 + 结构化分析（L1 舆情 docs/archons/venti.md §L1）
        # sentiment_enabled=False 或本批次无 records 时跳过聚类
        from paimon.config import config as _cfg
        processed_events: list = []
        if records and getattr(_cfg, "sentiment_enabled", True):
            try:
                from paimon.archons.venti_event import EventClusterer
                clusterer = EventClusterer(
                    irminsul, model,
                    force_new=False,  # 阶段 B 启用聚类 LLM；force_new=True 是阶段 A 的 fallback
                    max_llm_calls=getattr(_cfg, "sentiment_llm_calls_per_run_max", 30),
                )
                processed_events = await clusterer.process(sub, records)
                logger.info(
                    "[风神·订阅] 事件聚类完成 sub={} events={}（新={} 合并={}）",
                    sub_id, len(processed_events),
                    sum(1 for e in processed_events if e.is_new),
                    sum(1 for e in processed_events if not e.is_new),
                )
            except Exception as e:
                # 事件聚类失败不阻塞推送（feed_items 仍落盘 + 仍走旧 digest）
                logger.exception("[风神·订阅] 事件聚类异常 sub={}: {}", sub_id, e)

        # Step 5: 风神·舆情预警（阶段 B）—— p0 紧急推送（含 p2/p3 升级到 p0）
        # docs/archons/venti.md §L1 / docs/todo.md §风神增强 (4)
        # 只对本批次新事件做升级判定；累计模式下「持续中的 p0」不该重复推
        if processed_events:
            try:
                await self._dispatch_p0_alerts(
                    sub, processed_events, irminsul, march, _cfg,
                )
            except Exception as e:
                logger.exception(
                    "[风神·订阅] 舆情预警链路异常 sub={}（不阻塞日报）: {}",
                    sub_id, e,
                )

        # Step 5.5: LLM 日报 —— 用「当天累计」事件 / 条目，而不是仅本批次
        # 关键修复：dedup_per_day 下 upsert 会整段覆盖；如果只 summary 本批次，
        # 下午刷新会把上午合成的内容从公告里抹掉。所以这里拉今日累计：
        # - 优先用 feed_events（按 last_seen_at >= day_start，clusterer 会
        #   把今日有动静的旧事件 last_seen_at 滚到今天，自动落进窗口）
        # - 聚类整体失败 / 关闭时降级到 feed_items（按 captured_at >= day_start）
        today_events = await irminsul.feed_event_list(
            sub_id=sub.id, since=day_start, limit=200,
        )
        today_items = await irminsul.feed_items_list(
            sub_id=sub.id, since=day_start, limit=500,
        )

        if not today_events and not today_items:
            logger.info(
                "[风神·订阅] 当天累计为空，写空跑占位 sub={}", sub_id,
            )
            await self._write_empty_run_marker(
                sub, source_label=source_label,
                irminsul=irminsul, march=march, reason="accumulated_empty",
            )
            await irminsul.subscription_update(
                sub_id, actor="风神",
                last_run_at=time.time(), last_error="",
            )
            return

        # event_id → 该事件今日第一条 feed_items 的 url（给 ProcessedEvent.first_url）
        event_first_url: dict[str, str] = {}
        for it in today_items:
            eid = it.event_id or ""
            if eid and eid not in event_first_url:
                event_first_url[eid] = it.url

        if today_events:
            today_processed = [
                self._feed_event_to_processed(
                    ev, event_first_url.get(ev.id, ""), day_start,
                )
                for ev in today_events
            ]
            digest = await self._compose_event_digest(
                sub.query, today_processed, model,
            )
        else:
            today_items_payload = [
                {
                    "title": it.title or "",
                    "url": it.url or "",
                    "description": it.description or "",
                    "engine": it.engine or "",
                }
                for it in today_items
            ]
            digest = await self._compose_digest(
                sub.query, today_items_payload, model,
            )

        # Step 6: 综合日报推送
        # source 含订阅 query，公告卡头部一眼可区分（actor 仍是"风神"，
        # split("·",1)[0] 解析；extra_json 带 sub_id 给前端筛选 / 派蒙工具引用）
        digest_id = uuid4().hex[:12]
        try:
            # 日级幂等：cron 7am 跑过 + 用户中午手动「运行」会触两次响铃；
            # dedup_per_day=True → 同 source 当天 upsert，message 没变只 bump
            # 时间戳（保留 read_at），变了就原地更新 + reset 未读，避免一天
            # 同订阅出现两条公告
            ok = await march.ring_event(
                channel_name=sub.channel_name,
                chat_id=sub.chat_id,
                source=source_label,
                message=digest,
                extra={
                    "sub_id": sub.id,
                    "query": sub.query,
                    "digest_id": digest_id,
                },
                dedup_per_day=True,
            )
        except Exception as e:
            logger.error("[风神·订阅] 响铃失败 sub={} err={}", sub_id, e)
            ok = False

        if not ok:
            logger.warning("[风神·订阅] 响铃被拒/失败 sub={}（条目仍落盘）", sub_id)

        # Step 7: 标记 + 订阅 tick（仅 mark 本批次刚插入的；累计模式下旧条目
        # 上次跑时已经 mark 过 pushed_at）
        if inserted_ids:
            await irminsul.feed_items_mark_pushed(
                inserted_ids, digest_id, actor="风神",
            )
        await irminsul.subscription_update(
            sub_id, actor="风神",
            last_run_at=time.time(), last_error="",
        )

        logger.info(
            "[风神·订阅] 采集完成 sub={} 新增={} digest={}",
            sub_id, len(inserted_ids), digest_id,
        )

    async def _write_empty_run_marker(
        self,
        sub,
        *,
        source_label: str,
        irminsul: Irminsul,
        march: MarchService,
        reason: str,
    ) -> None:
        """空跑公告：当天无真数据时写一条占位 / 更新时间戳。

        - 当天已有同 source 公告（真日报或上次占位）→ 只刷新时间戳，read_at 不动
        - 当天无同 source 公告 → 写一条占位文案，首次空跑也能见反馈

        `reason` 供日志区分（search_empty / filtered_out / accumulated_empty）。
        """
        day_start, day_end = today_local_bounds()
        try:
            found, rec_id = await irminsul.push_archive_touch_daily(
                source=source_label, actor="风神",
                day_start=day_start, day_end=day_end,
            )
        except Exception as e:
            logger.warning(
                "[风神·订阅] 空跑 touch_daily 异常 sub={} reason={}: {}",
                sub.id, reason, e,
            )
            found, rec_id = (False, "")

        if found:
            logger.info(
                "[风神·订阅] 空跑刷新时间戳 sub={} reason={} rec={}",
                sub.id, reason, rec_id,
            )
            return

        placeholder = (
            f"📭 「{sub.query or '未命名'}」本周期暂无新增资讯。\n\n"
            f"本次已聚合但未发现符合条件的新内容，可稍后再刷新。"
        )
        try:
            await march.ring_event(
                channel_name=sub.channel_name,
                chat_id=sub.chat_id,
                source=source_label,
                message=placeholder,
                extra={
                    "sub_id": sub.id,
                    "query": sub.query,
                    "empty_run": True,
                    "reason": reason,
                },
                dedup_per_day=True,
            )
            logger.info(
                "[风神·订阅] 空跑占位公告已落 sub={} reason={}", sub.id, reason,
            )
        except Exception as e:
            logger.warning(
                "[风神·订阅] 空跑占位响铃失败 sub={} reason={}: {}",
                sub.id, reason, e,
            )

    async def _run_web_search(
        self, query: str, limit: int, engine: str,
    ) -> list[dict]:
        """调用 web-search skill 的 search.py，返回 JSON list。"""
        if not _SKILL_SEARCH_PY.exists():
            raise RuntimeError(
                f"web-search skill 不存在: {_SKILL_SEARCH_PY}；"
                "请确认 skills/web-search 已安装"
            )

        args: list[str] = [
            sys.executable, str(_SKILL_SEARCH_PY),
            query, "--limit", str(max(1, min(limit, 50))),
        ]
        if engine:
            args.extend(["--engine", engine])

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(), timeout=_WEB_SEARCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"web-search 超时 > {_WEB_SEARCH_TIMEOUT}s")

        rc = proc.returncode or 0
        if rc != 0:
            err_txt = (err_b or b"").decode("utf-8", "ignore").strip()
            # rc=3 = 所有引擎都挂；rc=2 = 参数错
            raise RuntimeError(f"web-search 退出码 {rc}: {err_txt[:200]}")

        out_txt = (out_b or b"").decode("utf-8", "ignore").strip()
        if not out_txt:
            return []
        try:
            data = json.loads(out_txt)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"web-search 输出非 JSON: {e}") from e

        if not isinstance(data, list):
            return []
        # 规范化：只保留必要字段 + 去空 url
        out: list[dict] = []
        for it in data:
            if not isinstance(it, dict):
                continue
            url = (it.get("url") or "").strip()
            if not url:
                continue
            out.append({
                "url": url,
                "title": (it.get("title") or "").strip(),
                "description": (it.get("description") or "").strip(),
                "engine": (it.get("engine") or "").strip(),
            })
        return out
