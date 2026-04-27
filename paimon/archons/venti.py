"""风神 · Venti — 自由·歌咏

新闻采集、舆情分析与追踪、推送整理。

两条入口：
1. `execute()` —— 四影管线复杂任务入口（LLM tool-loop，走 web_fetch/exec）
2. `collect_subscription()` —— 话题订阅后台采集入口（subprocess 直调 web-search skill，
   批量 LLM 早报，交三月响铃推送）
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.foundation.march import today_local_bounds
from paimon.llm.model import Model
from paimon.session import Session

if TYPE_CHECKING:
    from paimon.foundation.irminsul.feed_event import FeedEvent
    from paimon.foundation.march import MarchService

# web-search skill 脚本路径（文件存在则订阅能力可用；不存在仅告警不阻塞启动）
_SKILL_SEARCH_PY = (
    Path(__file__).resolve().parent.parent.parent / "skills" / "web-search" / "search.py"
)

# subprocess 超时：双引擎并发 + 反爬偶发慢，默认 60s
_WEB_SEARCH_TIMEOUT = 60.0

# 去重窗口：过去 30 天的 url 视为已见
_DEDUP_WINDOW_SECONDS = 30 * 24 * 3600

# 事件型日报 LLM 重试退避：第 1 次失败等 60s，第 2 次失败等 180s，第 3 次失败
# 不再重试，转走 P0+P1 兜底模板。`len(...)+1 = 总尝试次数`。
# 选 60s/180s 而非更短：失败模式以「上游 edge transient hiccup」为主，
# 拉长窗口能错过最常见的 30~60s 限流恢复期，再短反而连续撞同一波故障。
_DIGEST_RETRY_DELAYS = (60.0, 180.0)


_SYSTEM_PROMPT = """\
你是风神·巴巴托斯，掌管自由与歌咏。你的职责是信息采集与分析。

能力：
1. 用 web_fetch 工具抓取网页内容（新闻、文章、搜索结果）
2. 用 exec 工具执行 curl 等命令做补充抓取
3. 新闻摘要和舆情分析

规则：
1. 优先用 web_fetch 工具，它更安全且输出更干净
2. 输出结构化结果：标题、来源、摘要
3. 舆情分析时标注情感倾向（正面/中性/负面）
4. 调用工具时不要输出过程描述，只输出最终结果
"""


_DIGEST_PROMPT = """\
你是风神·巴巴托斯，负责给用户整理关注话题的日报。

用户订阅主题：「{query}」
下面是刚采集到的 {n} 条新条目（JSON），请整理成一段中文日报，体裁要求：

1. 开头一句 40 字内的总体概述（当前这些新内容的主要看点）
2. 之后用 1-3 级 bullet 列出条目，每条「标题 + 1 句话要点 + 来源 URL」
3. 末尾一句话点出情感倾向（正面 / 中性 / 负面 / 混合）和建议（要不要深读）
4. 全篇控制在 500 字内
5. 保留 URL 的 markdown 链接格式: [标题](URL)
6. 只输出最终日报文本，不要任何前置说明
"""


# 阶段 C · 事件型日报（按事件而非条目组织）
# 风神日报 system prompt 由通用 composer 渲染（保留 {query}/{n} 占位待调用方 .format）
from paimon.archons.venti_event import VENTI_DIGEST_SPEC
from paimon.foundation.digest import render_digest_prompt
_EVENT_DIGEST_PROMPT = render_digest_prompt(VENTI_DIGEST_SPEC)


def _build_fallback_digest(query: str, items: list[dict]) -> str:
    """LLM 失败时的降级模板：直接列条目。"""
    lines = [f"【订阅·{query}】刚刚采集到 {len(items)} 条新内容："]
    for it in items:
        title = (it.get("title") or "").strip() or "(无标题)"
        url = (it.get("url") or "").strip()
        if url:
            lines.append(f"- [{title}]({url})")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


def _build_event_fallback_digest(query: str, processed_events: list) -> str:
    """事件型日报 LLM 重试用尽后的精简降级模板：仅展示 P0 / P1。

    设计取舍：P2/P3 多是日常资讯噪音，LLM 挂了的时候硬塞进公告反而难读；
    省略后让用户聚焦真正紧急的内容。当天没有 P0/P1 时只发简短提示。
    """
    if not processed_events:
        return f"**风神·订阅日报【{query}】** 本次无新事件。"

    critical = [e for e in processed_events if e.severity in ("p0", "p1")]
    skipped = len(processed_events) - len(critical)

    if not critical:
        return (
            f"**风神·订阅日报【{query}】**\n"
            f"（LLM 合成失败 / 重试用尽 · 当日无 P0/P1 事件，"
            f"P2 及以下 {skipped} 个事件已省略）"
        )

    rank = {"p0": 0, "p1": 1}
    sorted_events = sorted(critical, key=lambda e: rank.get(e.severity, 4))

    skipped_tag = f"，P2 及以下 {skipped} 个已省略" if skipped else ""
    lines = [
        f"**风神·订阅日报【{query}】**",
        f"（LLM 合成失败 · 仅展示 P0+P1 共 {len(critical)} 个{skipped_tag}）",
        "",
    ]
    for ev in sorted_events:
        title = (ev.title or "(无标题)").strip()
        sev_icon = {"p0": "🔴", "p1": "🟠"}.get(ev.severity, "⚠")
        link = f"[{title}]({ev.first_url})" if ev.first_url else title
        upgrade = (
            "·升级" if (not ev.is_new and ev.severity_changed) else ""
        )
        sentiment_tag = (
            f"·{ev.sentiment_label}"
            if ev.sentiment_label and ev.sentiment_label != "neutral"
            else ""
        )
        lines.append(
            f"- {sev_icon} **[{ev.severity.upper()}{upgrade}{sentiment_tag}]** {link}"
        )
        if ev.summary:
            lines.append(f"  {ev.summary[:120]}")
    return "\n".join(lines)


class VentiArchon(Archon):
    name = "风神"
    description = "新闻采集、舆情分析、推送整理"
    allowed_tools = {"web_fetch", "exec"}

    def __init__(self) -> None:
        # 订阅采集 in-flight 集合：进入 collect_subscription 加入、finally 移除
        # 用途：① 前端卡片显示「采集中」角标 ② 防并发重入（cron + 手动按钮重叠）
        self._inflight: set[str] = set()

    def is_running(self, sub_id: str) -> bool:
        return sub_id in self._inflight

    # ---------- 四影管线入口（原有能力）----------

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[风神] 执行子任务: {}", subtask.description[:80])

        system = _SYSTEM_PROMPT
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"

        temp_session = Session(id=f"venti-{task.id[:8]}", name="风神采集")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="风神", purpose="信息采集",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="风神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="风神",
        )
        logger.info("[风神] 子任务完成, 结果长度={}", len(result))
        return result

    # ---------- 订阅采集入口（新增）----------

    async def collect_subscription(
        self, sub_id: str, *,
        irminsul: Irminsul,
        model: Model,
        march: MarchService,
    ) -> None:
        """主题订阅单次采集 + 推送。由三月 cron 触发（bootstrap 分派）。

        步骤：
        1. 读订阅（禁用/缺失直接退出）
        2. subprocess 调 web-search skill
        3. 过滤已见 url（30 天窗口）
        4. 落 feed_items
        5. 浅池 LLM 写日报 digest；失败降级模板
        6. 交三月 ring_event 推送
        7. 标记 feed_items pushed + 更新订阅 last_run_at
        """
        if sub_id in self._inflight:
            logger.info("[风神·订阅] 已在采集中，跳过重复触发 sub={}", sub_id)
            return
        self._inflight.add(sub_id)
        try:
            await self._collect_subscription_impl(
                sub_id, irminsul=irminsul, model=model, march=march,
            )
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

    async def _compose_digest(
        self, query: str, items: list[dict], model: Model,
    ) -> str:
        """浅池 LLM 写早报；失败降级到模板。"""
        system = _DIGEST_PROMPT.format(query=query, n=len(items))
        # 给 LLM 的条目裁剪 description，避免过长
        trimmed = [
            {
                "title": it.get("title", "")[:200],
                "url": it.get("url", ""),
                "description": it.get("description", "")[:400],
                "engine": it.get("engine", ""),
            }
            for it in items
        ]
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(trimmed, ensure_ascii=False)},
        ]
        try:
            raw, usage = await model._stream_text(messages, component="风神", purpose="订阅早报")
            await model._record_primogem(
                "", "风神", usage, purpose="订阅早报",
            )
        except Exception as e:
            logger.warning("[风神·订阅] LLM 早报失败，降级模板: {}", e)
            return _build_fallback_digest(query, items)

        text = raw.strip()
        # 清理可能的 code fence
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 2 and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()
        if not text:
            return _build_fallback_digest(query, items)
        return text

    @staticmethod
    def _feed_event_to_processed(
        ev: "FeedEvent", first_url: str, day_start: float,
    ) -> "ProcessedEvent":
        """把 feed_events 表中的事件转成 ProcessedEvent，喂给日报合成。

        累计模式（dedup_per_day 用）下不知道「本批次」是哪批，所以：
        - is_new = first_seen_at 是否落在今日窗口内
        - severity_changed / base_severity 缺失（设默认值），LLM prompt 里这两
          字段是参考性的，缺失只是损失一点叙述深度，不影响推送决策
        - first_url 由调用方传入（取该事件今日 feed_items 里第一条 url）
        """
        from paimon.archons.venti_event import ProcessedEvent
        return ProcessedEvent(
            event_id=ev.id,
            severity=ev.severity,
            base_severity="",
            is_new=ev.first_seen_at >= day_start,
            severity_changed=False,
            title=ev.title,
            summary=ev.summary,
            first_url=first_url or "",
            item_count=ev.item_count,
            sentiment_label=ev.sentiment_label,
            sentiment_score=ev.sentiment_score,
            last_seen_at=ev.last_seen_at,
            timeline=ev.timeline or [],
        )

    async def _compose_event_digest(
        self, query: str, processed_events: list, model: Model,
    ) -> str:
        """阶段 C 事件型日报。

        把本批次 ProcessedEvents 给 LLM，按 severity 分区组织成 markdown。
        LLM 调用按 _DIGEST_RETRY_DELAYS 重试；用尽后走 P0+P1 兜底模板。
        """
        if not processed_events:
            # 不应该到这里——调用方应已判过；保险返个空提示
            return f"**风神·订阅日报【{query}】** 本次无新事件。"

        import time as _time
        # 给 LLM 的事件结构（裁剪冗长字段；last_seen_at / timeline 给时效过滤用）
        events_payload = [
            {
                "title": (ev.title or "")[:80],
                "summary": (ev.summary or "")[:200],
                "severity": ev.severity,
                "sentiment_label": ev.sentiment_label,
                "sentiment_score": round(ev.sentiment_score, 2),
                "first_url": ev.first_url or "",
                "is_new": ev.is_new,
                "severity_changed": ev.severity_changed,
                "base_severity": ev.base_severity,
                "item_count": ev.item_count,
                "last_seen_at": _time.strftime(
                    "%Y-%m-%d %H:%M",
                    _time.localtime(ev.last_seen_at),
                ) if ev.last_seen_at else "",
                "timeline": ev.timeline or [],
            }
            for ev in processed_events
        ]
        today_date = _time.strftime("%Y-%m-%d", _time.localtime())
        system = _EVENT_DIGEST_PROMPT.format(
            query=query, n=len(processed_events),
            today_date=today_date,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(events_payload, ensure_ascii=False)},
        ]

        total_attempts = len(_DIGEST_RETRY_DELAYS) + 1
        last_err: Exception | str | None = None
        for attempt in range(total_attempts):
            try:
                raw, usage = await model._stream_text(messages, component="风神", purpose="事件日报")
                await model._record_primogem(
                    "", "风神", usage, purpose="事件日报",
                )
                text = (raw or "").strip()
                # 剥可能的 code fence（analysis prompt 已强约束，但兜一道）
                if text.startswith("```"):
                    lines_ = text.splitlines()
                    if len(lines_) >= 2 and lines_[-1].strip() == "```":
                        text = "\n".join(lines_[1:-1]).strip()
                if text:
                    if attempt > 0:
                        logger.info(
                            "[风神·订阅] 事件型日报 LLM 第 {}/{} 次重试成功",
                            attempt + 1, total_attempts,
                        )
                    return text
                # 空内容也按失败处理，可能是流被截或 prompt 触发拒答
                last_err = "LLM 返回空内容"
            except Exception as e:
                last_err = e

            if attempt + 1 < total_attempts:
                wait = _DIGEST_RETRY_DELAYS[attempt]
                logger.warning(
                    "[风神·订阅] 事件型日报 LLM 第 {}/{} 次失败: {}（{}s 后重试）",
                    attempt + 1, total_attempts, last_err, int(wait),
                )
                await asyncio.sleep(wait)
            else:
                logger.warning(
                    "[风神·订阅] 事件型日报 LLM 第 {}/{} 次失败: {}（重试用尽，降级 P0+P1 模板）",
                    attempt + 1, total_attempts, last_err,
                )

        return _build_event_fallback_digest(query, processed_events)

    # ---------- 阶段 B · 舆情预警分级推送 ----------

    async def _dispatch_p0_alerts(
        self, sub, processed_events: list, irminsul: Irminsul,
        march: "MarchService", cfg,
    ) -> None:
        """筛 p0 事件 + 冷却 check + 推 march.ring_event(source='风神·舆情预警')。

        触发条件（择一）：
        - 新事件 severity=p0
        - 已有事件升级到 p0（base_severity=p1/p2/p3）

        失败静默（推送失败不阻塞日常 digest 推送）。
        """
        from paimon.foundation.irminsul import is_severity_upgrade

        if not processed_events:
            return
        # 选出本批次需要紧急推送的 p0 事件
        urgent = [
            ev for ev in processed_events
            if ev.severity == "p0"
            and (ev.is_new or is_severity_upgrade(ev.base_severity, ev.severity))
        ]
        if not urgent:
            return

        cooldown_seconds = max(
            60, int(getattr(cfg, "sentiment_p0_cooldown_minutes", 30)) * 60,
        )
        now = time.time()

        for ev in urgent:
            # 重读 DB 拿到完整事件信息（entities / sources / last_pushed_at）
            try:
                event_obj = await irminsul.feed_event_get(ev.event_id)
            except Exception as e:
                logger.warning("[风神·舆情预警] 读事件失败 {}: {}", ev.event_id, e)
                continue
            if event_obj is None:
                logger.warning(
                    "[风神·舆情预警] 事件已被删除 {}，跳过", ev.event_id,
                )
                continue

            # 升级冷却：同事件 N 分钟内不重推
            if event_obj.last_pushed_at and (
                now - event_obj.last_pushed_at < cooldown_seconds
            ):
                logger.info(
                    "[风神·舆情预警] 冷却中 event={} ({}s 前刚推过)",
                    ev.event_id[:8], int(now - event_obj.last_pushed_at),
                )
                continue

            urgent_md = self._compose_p0_urgent(sub, ev, event_obj)
            try:
                ok = await march.ring_event(
                    channel_name=sub.channel_name,
                    chat_id=sub.chat_id,
                    source=f"风神·舆情预警·{(sub.query or '')[:20]}",
                    message=urgent_md,
                    extra={
                        "sub_id": sub.id,
                        "query": sub.query,
                        "event_id": ev.event_id,
                    },
                )
            except Exception as e:
                logger.error(
                    "[风神·舆情预警] 响铃失败 event={}: {}", ev.event_id, e,
                )
                ok = False
            if not ok:
                logger.warning(
                    "[风神·舆情预警] 响铃被拒 event={}（事件仍落盘）",
                    ev.event_id[:8],
                )
                continue

            # 推送成功 → 更新 last_pushed_at + last_severity + pushed_count
            try:
                await irminsul.feed_event_update(
                    ev.event_id, actor="风神·舆情预警",
                    last_pushed_at=now,
                    last_severity=ev.severity,
                    pushed_count_inc=1,
                )
            except Exception as e:
                logger.warning(
                    "[风神·舆情预警] 更新冷却字段失败 {}: {}",
                    ev.event_id[:8], e,
                )

            # audit 记一条（payload 不含敏感字段，便于后续在 dashboard 复盘）
            try:
                await irminsul.audit_append(
                    event_type="feed_event_pushed",
                    payload={
                        "sub_id": sub.id,
                        "event_id": ev.event_id,
                        "severity": ev.severity,
                        "base_severity": ev.base_severity,
                        "is_new": ev.is_new,
                        "is_upgrade": is_severity_upgrade(
                            ev.base_severity, ev.severity,
                        ),
                        "alert_kind": "p0_urgent",
                    },
                    actor="风神·舆情预警",
                )
            except Exception as e:
                logger.debug("[风神·舆情预警] audit 写失败（吞）: {}", e)

            logger.warning(
                "[风神·舆情预警] 已推送 P0 event={} title='{}' "
                "(was '{}' → 'p0', sub={})",
                ev.event_id[:8], ev.title[:40],
                ev.base_severity or "new", sub.id,
            )

    def _compose_p0_urgent(self, sub, processed_ev, event_obj) -> str:
        """生成 P0 紧急推送 markdown（docs/archons/venti.md §L1 / plan §7）。"""
        from paimon.foundation.irminsul import is_severity_upgrade
        from datetime import datetime

        # 升级标记
        upgrade_tag = ""
        if not processed_ev.is_new and is_severity_upgrade(
            processed_ev.base_severity, processed_ev.severity,
        ):
            upgrade_tag = f"（{processed_ev.base_severity} → p0 严重度上调）"

        # 情感数值格式
        score = event_obj.sentiment_score
        score_str = f"{score:+.2f}"
        sentiment_disp = (
            f"{event_obj.sentiment_label}（{score_str}）"
            if event_obj.sentiment_label else "未分析"
        )

        # 实体（最多 5 个）
        entities_str = "、".join(event_obj.entities[:5]) or "（无）"

        # 信源（最多 5 个 + 总条目数）
        sources_str = "、".join(event_obj.sources[:5])
        if not sources_str:
            sources_str = "（无信源）"
        sources_str = f"{sources_str}（共 {event_obj.item_count} 条报道）"

        last_seen = datetime.fromtimestamp(
            event_obj.last_seen_at,
        ).strftime("%Y-%m-%d %H:%M")

        first_url = processed_ev.first_url or ""
        title_md = (
            f"[{processed_ev.title}]({first_url})"
            if first_url else processed_ev.title
        )

        return (
            f"🚨 **风神·舆情预警 [P0]**{upgrade_tag}\n"
            f"\n"
            f"**订阅**：{sub.query}\n"
            f"**事件**：{title_md}\n"
            f"**摘要**：{processed_ev.summary or event_obj.summary}\n"
            f"**情感**：{sentiment_disp}\n"
            f"**关联实体**：{entities_str}\n"
            f"**信源**：{sources_str}\n"
            f"**最近更新**：{last_seen}"
        )
