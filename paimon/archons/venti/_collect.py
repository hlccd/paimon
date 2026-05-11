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

        - 'topic_research' → 风神 topic UGC 调研（run_topic_research_collect）
        - 'mihoyo_game' → 水神（run_furina_news_collect）
        - 'stock_watch' → 岩神（run_web_search_collect）
        - 其他 archon 注册的 binding_kind → 各自 collector

        feed_collect ScheduledTask 由 bootstrap._on_march_ring 触发，所有 binding_kind
        都走这里 dispatch；inflight 防重在 dispatcher 层做。
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
            kind = sub.binding_kind or ""
            meta = subscription_types.get(kind)
            if meta is None:
                logger.warning(
                    "[风神·订阅] 未知 binding_kind={} sub={}（无 collector 注册）",
                    kind, sub_id,
                )
                return
            # 通过 state 调 collector（签名 (sub, state)）
            from paimon.state import state as _state
            await meta.collector(sub, _state)
        finally:
            self._inflight.discard(sub_id)

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
            # USB-001：rc 数字 → 中文行动建议
            # rc=3 = 所有引擎都挂；rc=2 = 参数错
            hint_map = {
                2: "搜索参数错误（query/limit/engine 配置异常）",
                3: "全部搜索引擎暂时不可用（网络/反爬/限流），请稍后重试",
            }
            hint = hint_map.get(rc, f"搜索失败（退出码 {rc}）")
            raise RuntimeError(f"{hint}：{err_txt[:200]}")

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
