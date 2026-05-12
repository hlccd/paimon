"""风神 · 每日热点 cron 入口：6 源并发拉 + LLM 综合 + 落库。

cron 注册两条 task（11/17 各跑一次）；周报 cron 在 Phase 2 加。
"""
from __future__ import annotations

import asyncio
import datetime
import time

from loguru import logger

from ._compose_daily import compose_daily
from ._models import SOURCE_LABELS, CollectResult
from .sources import bili as src_bili
from .sources import hn as src_hn
from .sources import tieba as src_tieba
from .sources import weibo as src_weibo
from .sources import xhs as src_xhs
from .sources import zhihu as src_zhihu


_SOURCES = [
    ("bili", src_bili.collect),
    ("hn", src_hn.collect),
    ("zhihu", src_zhihu.collect),
    ("weibo", src_weibo.collect),
    ("xhs", src_xhs.collect),
    ("tieba", src_tieba.collect),
]

def _decide_slot() -> str:
    """记录"最后一次什么时段触发"的信息（不参与唯一约束）。

    - 10:00 ~ 13:59 → morning（正常 cron 11:00 落在这）
    - 16:00 ~ 19:59 → afternoon（正常 cron 17:00 落在这）
    - 其他时间触发 → manual（用户手动「立即跑」）
    """
    hour = datetime.datetime.now().hour
    if 10 <= hour < 14:
        return "morning"
    if 16 <= hour < 20:
        return "afternoon"
    return "manual"


async def run_daily_hotspot_collect(state) -> None:
    """每日热点入口；inflight 由**调用方**（API / cron dispatcher）同步设置 + finally 清理，
    避免 bg fire-and-forget 与前端 fetch 的 race（前端拉 today 时已能看到 running=true）。
    """
    if not state.irminsul:
        logger.error("[风神·hotspot] state.irminsul 未就绪")
        return
    if not state.model:
        logger.error("[风神·hotspot] state.model 未就绪")
        return
    await _do_run_daily(state)


async def _do_run_daily(state) -> None:
    irminsul = state.irminsul
    capture_date = datetime.datetime.now().strftime("%Y-%m-%d")
    capture_slot = _decide_slot()
    logger.info("[风神·hotspot] 开始采集 {} {}", capture_date, capture_slot)

    t0 = time.time()
    # 6 源并发；单源 timeout 各自包在 collector 内
    tasks = [coll() for _, coll in _SOURCES]
    results: list[CollectResult] = []
    for r in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(r, Exception):
            logger.error("[风神·hotspot] collector 抛异常: {}", r)
            continue
        results.append(r)

    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    sources_ok = ",".join(r.source for r in ok)
    sources_fail = ",".join(f"{r.source}:{r.error[:40]}" for r in failed)

    logger.info(
        "[风神·hotspot] 采集完成 ok={} fail={} 总条目={}",
        sources_ok or "-", sources_fail or "-",
        sum(len(r.items) for r in ok),
    )

    if not ok:
        # 全部失败：仍 upsert 一条占位，markdown 写错误说明
        markdown = (
            f"## ⚠️ 全部 {len(_SOURCES)} 源采集失败\n\n"
            + "\n".join(f"- **{SOURCE_LABELS.get(r.source, r.source)}**：{r.error}" for r in failed)
        )
        duration_s = int(time.time() - t0)
        await irminsul.daily_hotspot_upsert(
            capture_date=capture_date, capture_slot=capture_slot,
            markdown=markdown, sources_ok="", sources_fail=sources_fail,
            items_total=0, duration_s=duration_s,
        )
        return

    # LLM 综合
    try:
        markdown = await compose_daily(ok, state.model)
    except Exception as e:
        logger.error("[风神·hotspot] LLM 综合失败: {}", e)
        # 兜底：直接列各源 raw（保证用户能看到原料）
        markdown = _fallback_render(ok)

    items_total = sum(len(r.items) for r in ok)
    duration_s = int(time.time() - t0)
    await irminsul.daily_hotspot_upsert(
        capture_date=capture_date, capture_slot=capture_slot,
        markdown=markdown, sources_ok=sources_ok, sources_fail=sources_fail,
        items_total=items_total, duration_s=duration_s,
    )
    logger.info(
        "[风神·hotspot] 完成 {} {} markdown={} chars duration={}s",
        capture_date, capture_slot, len(markdown), duration_s,
    )


def _fallback_render(ok: list[CollectResult]) -> str:
    """LLM 失败时降级：直接按源列 top 10。"""
    lines = ["## ⚠️ LLM 综合失败，降级展示各源 Top 10\n"]
    for r in ok:
        label = SOURCE_LABELS.get(r.source, r.source)
        lines.append(f"### {label}")
        for it in r.items[:10]:
            lines.append(f"{it.rank}. **[{it.title}]({it.url})**")
        lines.append("")
    return "\n".join(lines)


# ─── 周报（每周六早 10 点 cron）─────────────────────────────

async def run_weekly_hotspot_collect(state) -> None:
    """近期回顾入口；inflight 由**调用方**管理（同 daily 一致避免 race）。"""
    if not state.irminsul:
        logger.error("[风神·近期回顾] state.irminsul 未就绪")
        return
    if not state.model:
        logger.error("[风神·近期回顾] state.model 未就绪")
        return
    await _do_run_weekly(state)


async def _do_run_weekly(state) -> None:
    irminsul = state.irminsul
    today = datetime.date.today()
    range_end_date = today
    range_start_date = today - datetime.timedelta(days=6)
    capture_date = today.strftime("%Y-%m-%d")
    range_start = range_start_date.strftime("%Y-%m-%d")
    range_end = range_end_date.strftime("%Y-%m-%d")

    logger.info("[风神·近期回顾] 开始汇总 {} ~ {}", range_start, range_end)
    t0 = time.time()

    items = await irminsul.daily_hotspot_list_recent(days=7)
    items_in_range = [
        r for r in items
        if r.get("capture_date") and range_start <= r["capture_date"] <= range_end
    ]
    items_in_range.sort(key=lambda r: r.get("captured_at", 0))

    from ._compose_weekly import compose_weekly
    try:
        markdown = await compose_weekly(
            items_in_range, state.model,
            range_start=range_start, range_end=range_end,
        )
    except Exception as e:
        logger.error("[风神·近期回顾] LLM 综合失败: {}", e)
        # 即使 LLM 失败也落一条占位（带数据范围），让前端能展示"暂无内容 + 范围"
        markdown = (
            f"## 近期回顾 · {range_start} ~ {range_end}\n\n"
            f"⚠️ 本次合成失败：{str(e)[:160]}"
        )

    duration_s = int(time.time() - t0)
    await irminsul.weekly_hotspot_upsert(
        capture_date=capture_date, range_start=range_start, range_end=range_end,
        markdown=markdown, daily_count=len(items_in_range),
        duration_s=duration_s,
    )
    logger.info(
        "[风神·近期回顾] 完成 {} ~ {} daily_count={} markdown={} chars duration={}s",
        range_start, range_end, len(items_in_range), len(markdown), duration_s,
    )
