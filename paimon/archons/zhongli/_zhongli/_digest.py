"""岩神 · 每日 digest 组装 + 事件持久化 mixin。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from paimon.archons.zhongli.scorer import (
    build_advice, build_reasons, classify_stock, score_stock,
)
from paimon.foundation.irminsul import (
    ChangeEvent, ScoreSnapshot, UserWatchPrice, WatchlistEntry,
)

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.march import MarchService
    from paimon.llm.model import Model


class _DigestMixin:
    async def _persist_events(
        self, events: dict[str, list[dict]], current: list[dict],
        scan_date: str, irminsul: Irminsul,
    ) -> None:
        """把 _aggregate_events 的产物 upsert 到世界树 dividend_events 域。

        副作用：
        - 命中事件：upsert（同 stock_code+event_type 7 天内 merge）
        - current 中本轮该股没命中此 type 但表里有 active → mark resolved（自动闭环）

        events 结构：{'p0':[...], 'p1':[...], 'p2':[...]}
        每条 ev 含 {stock_code/stock_name/industry/severity/kind/reason/total_score/
                    dividend_yield/prev_score}（来自 _aggregate_events）
        """
        # 收集本轮命中：code → {event_types}
        active_now: dict[str, set[str]] = {}
        ev_count = 0
        for sev_list in events.values():
            for ev in sev_list:
                code = ev.get('stock_code', '')
                etype = ev.get('kind', '')
                if not code or not etype:
                    continue
                active_now.setdefault(code, set()).add(etype)

                tl_entry = {
                    "scan_date": scan_date,
                    "severity": ev.get('severity', ''),
                    "reason": ev.get('reason', ''),
                    "total_score": ev.get('total_score', 0),
                    "prev_score": ev.get('prev_score', 0),
                    "dividend_yield": ev.get('dividend_yield', 0),
                    "ts": time.time(),
                }
                detail = {
                    "total_score": ev.get('total_score', 0),
                    "prev_score": ev.get('prev_score', 0),
                    "dividend_yield": ev.get('dividend_yield', 0),
                }
                title = f"{ev.get('stock_name', '')}（{code}）{etype}"
                try:
                    await irminsul.dividend_event_upsert(
                        stock_code=code, event_type=etype,
                        severity=ev.get('severity', 'p2'),
                        stock_name=ev.get('stock_name', ''),
                        industry=ev.get('industry', ''),
                        title=title, summary=ev.get('reason', ''),
                        timeline_entry=tl_entry, detail=detail,
                        actor="岩神",
                    )
                    ev_count += 1
                except Exception as e:
                    logger.error("[岩神·事件] upsert 失败 {} {} {}", code, etype, e)

        # 自动闭环：current 列表里本轮被扫的股票，把它们 active 中
        # 不在本轮命中 types 集合的事件标 resolved
        resolved_count = 0
        for s in current:
            sd = s.get('stock_data') or {}
            code = sd.get('code', '')
            if not code:
                continue
            types_now = active_now.get(code, set())
            try:
                n = await irminsul.dividend_event_mark_resolved(
                    code, exclude_types=types_now, actor="岩神",
                )
                resolved_count += n
            except Exception as e:
                logger.error("[岩神·事件] resolve 失败 {} {}", code, e)

        logger.info(
            "[岩神·事件] 持久化 scan_date={} upsert={} resolved={}",
            scan_date, ev_count, resolved_count,
        )

    @staticmethod
    def _compose_daily_digest(
        mode: str, result: dict, events: dict[str, list[dict]],
    ) -> tuple[str, dict]:
        """生成"理财日报 markdown" + 元数据 dict（供 push_archive.extra 存放）。

        events 结构：{'p0':[...], 'p1':[...], 'p2':[...]}，来自 _aggregate_events。
        result 结构：scan 内部 dict（stocks/recommended/changes/scan_date/...）。

        返回 (markdown, meta):
          meta = {mode, scan_date, p0_count, p1_count, p2_count, total_scanned, recommended_count}
        """
        scan_date = result.get('scan_date', '')
        total_scanned = result.get('total_scanned', 0)
        stocks = result.get('stocks') or []
        recommended = result.get('recommended') or []
        changes = result.get('changes') or []

        p0 = events.get('p0') or []
        p1 = events.get('p1') or []
        p2 = events.get('p2') or []

        lines: list[str] = [
            f"# 📊 岩神·理财日报 · {scan_date} · {mode}",
            "",
            f"**概览**：扫描 {total_scanned} 只 · 通过筛选 {len(stocks)} 只 · 推荐 {len(recommended)} 只",
            "",
        ]

        # --- 行业趋势：按行业取 TOP3 均值排序，列 Top5（先放概览之后）---
        # 跳过 "未知"：脏数据不该出现在 Top5 行业里（污染均值排序）
        by_industry: dict[str, list[float]] = {}
        for s in stocks:
            ind = (s.get('stock_data') or {}).get('industry') or ''
            if not ind or ind == '未知':
                continue
            by_industry.setdefault(ind, []).append(s.get('total_score', 0))
        industry_rank = [
            (ind, sum(scores[:3]) / min(3, len(scores)), len(scores))
            for ind, scores in by_industry.items() if scores
        ]
        industry_rank.sort(key=lambda x: x[1], reverse=True)
        if industry_rank:
            lines.append("## 🏭 行业趋势 · Top5 均值")
            lines.append("")
            for ind, avg, n in industry_rank[:5]:
                lines.append(f"- **{ind}**：均值 {avg:.1f} 分（{n} 只）")
            lines.append("")

        # --- P0 致命异常 ---
        if p0:
            lines.append(f"## 🚨 P0 致命异常（{len(p0)} 只）")
            lines.append("")
            for ev in p0[:10]:
                dy = (ev.get('dividend_yield') or 0) * 100
                lines.append(
                    f"- **{ev['stock_name']}（{ev['stock_code']}）** · {ev['industry']}"
                )
                lines.append(f"  - {ev['reason']}")
                lines.append(
                    f"  - 当前评分 {ev['total_score']:.1f} · 股息率 {dy:.2f}%"
                )
            if len(p0) > 10:
                lines.append(f"- ... 另有 {len(p0) - 10} 只 P0 异常")
            lines.append("")

        # --- P1 警示 ---
        if p1:
            lines.append(f"## ⚠️ P1 警示（{len(p1)} 只）")
            lines.append("")
            for ev in p1[:10]:
                dy = (ev.get('dividend_yield') or 0) * 100
                lines.append(
                    f"- **{ev['stock_name']}（{ev['stock_code']}）** · "
                    f"{ev['industry']} · {ev['reason']}（{ev['total_score']:.1f} 分 / "
                    f"股息率 {dy:.2f}%）"
                )
            if len(p1) > 10:
                lines.append(f"- ... 另有 {len(p1) - 10} 只 P1 警示")
            lines.append("")

        # --- P2 评分小幅变化概览（只报数不列表，避免日报过长）---
        if p2:
            up = sum(1 for e in p2 if e['total_score'] > e['prev_score'])
            down = len(p2) - up
            lines.append(
                f"## 📐 P2 评分小幅变化：共 {len(p2)} 只（上升 {up} · 下降 {down}）"
            )
            lines.append("")

        # --- 新入选 / 退出 ---
        entered = [c for c in changes if c.event_type == 'entered'][:5]
        exited = [c for c in changes if c.event_type == 'exited'][:5]
        if entered:
            lines.append(f"## 📈 新入选 TOP {len(entered)}")
            lines.append("")
            for c in entered:
                lines.append(
                    f"- **{c.stock_name}（{c.stock_code}）** · {c.description}"
                )
            lines.append("")
        if exited:
            lines.append(f"## 📉 退出 TOP {len(exited)}")
            lines.append("")
            for c in exited:
                lines.append(
                    f"- **{c.stock_name}（{c.stock_code}）** · {c.description}"
                )
            lines.append("")

        # --- 尾部 ---
        lines.append("---")
        lines.append("")
        lines.append("⚠️ 以上数据仅供参考，不构成投资建议。")

        meta = {
            "mode": mode,
            "scan_date": scan_date,
            "p0_count": len(p0),
            "p1_count": len(p1),
            "p2_count": len(p2),
            "total_scanned": total_scanned,
            "recommended_count": len(recommended),
        }
        return "\n".join(lines), meta
