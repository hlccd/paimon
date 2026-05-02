"""岩神 · 用户关注股价格采集 + 偏离阈值预警 mixin。"""
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


class _WatchMixin:
    async def collect_user_watchlist(
        self, irminsul: Irminsul,
        march: "MarchService | None" = None,
        chat_id: str = "", channel_name: str = "",
    ) -> dict:
        """抓用户关注股日 K → 入库 → 检测日波动 → 推送。

        在 `_full_scan` / `_daily_update` 末尾调用；`_rescore` 不调（纯 cache）。
        对每只关注股按 price_max_date 决定起点：
        - 无历史 → 拉 3 年建底
        - 有历史 → 只拉 max_date+1 到今天（通常 1 条）
        """
        codes = await irminsul.user_watch_codes()
        if not codes:
            return {'count': 0, 'alerts': []}

        today = date.today()
        today_iso = today.isoformat()
        # 分首次建底 vs 日更增量，两种处理方式不同：
        # - 首次建底：start=3 年前，全量入库（第一行 change_pct=0 天然正确）
        # - 日更：start=max_date（不是 +1 天！）。baostock 在本批数据内部算 change_pct，
        #   需要"昨天+今天"两行才能正确算今天的 change_pct；若只给今天 1 行 prev_close=0
        #   → change_pct 永远 0 → 波动检测失效。拿到后 **丢掉 max_date 那一行**
        #   再 upsert（因为那行 change_pct=0 会覆盖掉库里昨天已算对的正确值）。
        initial_codes: list[str] = []
        daily_groups: dict[str, list[str]] = {}  # max_date -> [codes]
        for code in codes:
            max_date = await irminsul.user_watch_price_max_date(code)
            if not max_date:
                initial_codes.append(code)
            elif max_date < today_iso:
                daily_groups.setdefault(max_date, []).append(code)
            # else: 已是最新，skip

        logger.info(
            "[岩神·关注股] 待抓 initial={} daily={} 组（共 {} 只）",
            len(initial_codes), len(daily_groups),
            len(initial_codes) + sum(len(v) for v in daily_groups.values()),
        )

        # 用一个内部 helper 做 upsert + 回填 stock_name，两路共用
        async def _save(code: str, rows: list[dict], name: str) -> int:
            if not rows:
                return 0
            to_save = [
                UserWatchPrice(
                    stock_code=code, date=r.get('date', ''),
                    close=float(r.get('close', 0) or 0),
                    change_pct=float(r.get('change_pct', 0) or 0),
                    pe=float(r.get('pe', 0) or 0),
                    pb=float(r.get('pb', 0) or 0),
                    volume=float(r.get('volume', 0) or 0),
                )
                for r in rows if r.get('date')
            ]
            n = 0
            if to_save:
                n = await irminsul.user_watch_price_upsert(to_save, actor="岩神")
            if name:
                existing = await irminsul.user_watch_get(code)
                if existing is not None and not existing.stock_name:
                    await irminsul.user_watch_update(
                        code, stock_name=name, actor="岩神",
                    )
            return n

        total_upserted = 0

        # —— 首次建底
        if initial_codes:
            start = (today - timedelta(days=self._USER_WATCH_INIT_YEARS * 365)).isoformat()
            try:
                hist = await self._skill_fetch_stock_detail(initial_codes, start, today_iso)
            except Exception as e:
                logger.warning("[岩神·关注股·建底] skill 抓取失败: {}", e)
                hist = {}
            for code, payload in hist.items():
                payload = payload or {}
                rows = payload.get('rows') or []
                total_upserted += await _save(code, rows, (payload.get('name') or '').strip())

        # —— 日更增量（每组起点不同 → 分组调 skill）
        for max_date, group_codes in daily_groups.items():
            try:
                hist = await self._skill_fetch_stock_detail(group_codes, max_date, today_iso)
            except Exception as e:
                logger.warning("[岩神·关注股·日更] skill 抓取失败 start={}: {}", max_date, e)
                continue
            for code, payload in hist.items():
                payload = payload or {}
                rows = payload.get('rows') or []
                # 丢弃第一行（date == max_date）—— 它的 change_pct 在 provider 里被算成 0，
                # 入库会覆盖掉库里昨天已正确的 change_pct
                rows = [r for r in rows if r.get('date') != max_date]
                total_upserted += await _save(code, rows, (payload.get('name') or '').strip())

        # 波动检测（用最新一行的 change_pct）
        # 日期守卫：latest.date 必须 = 今天。否则 —— 周末/节假日 scan 跑起来
        # latest.date 是上个交易日，会把旧 alert 又推一遍，用户每个周末收一次
        # "上周五的波动"通知。只在真今天有新 K 线时才触发。
        entries = await irminsul.user_watch_list()
        alerts: list[dict] = []
        for e in entries:
            latest = await irminsul.user_watch_price_latest(e.stock_code)
            if not latest or latest.close <= 0 or latest.date != today_iso:
                continue
            if abs(latest.change_pct) >= e.alert_pct:
                alerts.append({
                    'code': e.stock_code,
                    'name': e.stock_name or e.stock_code,
                    'note': e.note,
                    'price': latest.close,
                    'change_pct': latest.change_pct,
                    'alert_pct': e.alert_pct,
                    'date': latest.date,
                })

        logger.info(
            "[岩神·关注股] 完成 codes={} upsert={} alerts={}",
            len(codes), total_upserted, len(alerts),
        )

        # 推送（有波动才发；dedup_per_day 同日多次扫描复用同一条卡）
        if alerts and march and chat_id and channel_name:
            try:
                md = self._compose_watch_alert(alerts)
                await march.ring_event(
                    channel_name=channel_name, chat_id=chat_id,
                    source="岩神·关注股波动", message=md, dedup_per_day=True,
                )
            except Exception as e:
                logger.error("[岩神·关注股] 推送失败: {}", e)

        return {'count': len(codes), 'alerts': alerts, 'upserted': total_upserted}

    @staticmethod
    def _compose_watch_alert(alerts: list[dict]) -> str:
        """把多只波动合并成一条 markdown 卡片（避免每只一张刷屏）。"""
        lines = [f"## 📈 关注股波动 · {alerts[0]['date']}", ""]
        alerts_sorted = sorted(alerts, key=lambda a: -abs(a['change_pct']))
        for a in alerts_sorted:
            arrow = "🔺" if a['change_pct'] >= 0 else "🔻"
            name_part = f"{a['name']}({a['code']})"
            note_part = f"  _{a['note']}_" if a['note'] else ""
            lines.append(
                f"- {arrow} **{name_part}** {a['price']:.2f} "
                f"({a['change_pct']:+.2f}% · 阈值 ±{a['alert_pct']:.1f}%){note_part}"
            )
        return "\n".join(lines)
