"""岩神 · 三档红利股扫描 mixin：full_scan / daily_update / rescore（全 5500 / watchlist 日更 / 仅评分）。"""
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

# 评分内部 helper / 模块级常量 — mixin 拆分后从 _helpers 集中引入
from ._helpers import (
    MAX_INDUSTRIES,
    MAX_PER_INDUSTRY,
    MIN_DIVIDEND_YIELD,
    MIN_HISTORY_COUNT,
    MIN_MARKET_CAP,
    WATCHLIST_SIZE,
    _aggregate_events,
    _apply_sector_caps,
    _detect_changes,
    _result_to_snapshot,
    _score_single,
)

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.march import MarchService
    from paimon.llm.model import Model


class _ScanMixin:
    async def _full_scan(self, irminsul: Irminsul) -> dict:
        """全市场扫描：skill 三段 I/O + in-process 评分 + 写世界树。"""
        scan_date = date.today().isoformat()
        logger.info("[岩神·full_scan] 启动")

        # 1. 抓全市场行情
        board = await self._skill_fetch_board()
        industry_map = board.get('industry_map', {})
        market = board.get('market_data', {})
        total_scanned = len(market)
        if not market:
            logger.warning("[岩神·full_scan] 行情抓取空")
            return {'stocks': []}

        # 2. 岩神筛选：市值硬门槛
        candidates = [
            code for code, info in market.items()
            if info.get('market_cap', 0) >= MIN_MARKET_CAP
        ]
        logger.info(
            "[岩神·full_scan] 全市场 {} 只 → 筛选后 {} 只",
            total_scanned, len(candidates),
        )

        # 3. 批量抓股息
        dividends = await self._skill_fetch_dividend(candidates)

        # 4. 读上次快照（不再 clear today；snapshot_upsert ON CONFLICT 自带覆盖。
        # 早期用"先清后写"模式，重写不全时会丢数据 —— 任何抓取/评分失败都会
        # 把昨天健康的 snapshot 抹掉，rescore 用 cache 命中率不到 100% 时
        # 直接砍掉 today 的推荐选股，前端从满变空。改 upsert 后无此风险。）
        prev = await irminsul.snapshot_latest_for_watchlist()
        prev_codes = {s.stock_code for s in (prev or [])}

        # 5. 初评（apply_filter 过硬门槛；上轮 watchlist 内强制不过滤，
        # 让 _aggregate_events 能捕捉停分红/历史断档等 P0 事件，
        # 否则 dy<3% 的票会被丢弃，dividend_halt 规则永远命不中）
        results: list[dict] = []
        total_div = len(dividends)
        for i, (code, div_info) in enumerate(dividends.items(), 1):
            info = market.get(code)
            if not info:
                continue
            industry = industry_map.get(code) or info.get('industry', '未知')
            apply_filter = code not in prev_codes
            scored = _score_single(code, div_info, None, info, industry, apply_filter=apply_filter)
            if scored:
                results.append(scored)
                await irminsul.snapshot_upsert(
                    scan_date, _result_to_snapshot(scan_date, scored), actor="岩神",
                )
            if i % 50 == 0 or i == total_div:
                self._set_progress("scoring_dividend", i, total_div, passed=len(results))
                logger.info("[岩神·full_scan] 股息评分进度 {}/{}，通过 {}", i, total_div, len(results))
        logger.info("[岩神·full_scan] 股息初筛通过 {} 只", len(results))

        # 6. 批量抓财务 + 二次评分
        codes_with_div = [s['stock_data']['code'] for s in results]
        financials = await self._skill_fetch_financial(codes_with_div)
        total_fin = len(results)
        for i, s in enumerate(results, 1):
            code = s['stock_data']['code']
            fin_info = financials.get(code)
            if fin_info is None:
                continue
            info = market.get(code)
            if not info:
                continue
            industry = industry_map.get(code) or info.get('industry', '未知')
            updated = _score_single(code, dividends.get(code, {}), fin_info, info, industry,
                                    apply_filter=False)
            if updated:
                s.update(updated)
                await irminsul.snapshot_upsert(
                    scan_date, _result_to_snapshot(scan_date, updated), actor="岩神",
                )
            if i % 50 == 0 or i == total_fin:
                self._set_progress("scoring_financial", i, total_fin)
                logger.info("[岩神·full_scan] 财务评分进度 {}/{}", i, total_fin)

        # 7. 排序 + 行业均衡
        results.sort(key=lambda x: x['total_score'], reverse=True)
        recommended = _apply_sector_caps(results)

        # 8. 刷 watchlist
        entries = [
            WatchlistEntry(
                stock_code=s['stock_data']['code'],
                stock_name=s['stock_data'].get('name', ''),
                industry=s['stock_data'].get('industry', ''),
                added_date=scan_date,
                last_refresh=scan_date,
            )
            for s in recommended
        ]
        if entries:
            await irminsul.watchlist_save(entries, scan_date, actor="岩神")

        # 9. 变化检测
        changes = _detect_changes(recommended, prev, scan_date=scan_date)
        if changes:
            await irminsul.change_save(changes, actor="岩神")

        # 10. 事件分级（供日报用）+ 持久化到 dividend_events 域
        events = _aggregate_events(results, prev)
        await self._persist_events(events, results, scan_date, irminsul)

        # 11. 清 skill 过期缓存
        await self._skill_cleanup_cache()

        return {
            'mode': 'full',
            'scan_date': scan_date,
            'total_scanned': total_scanned,
            'stocks': results,
            'recommended': recommended,
            'changes': changes,
            'events': events,
        }

    async def _daily_update(self, irminsul: Irminsul) -> dict:
        """日更：扫候选池（最近一次全扫描产出的 ~300 只）刷数据 + 评分。

        candidates ⊇ watchlist：watchlist 内的票一定在候选池里，所以前端
        「推荐选股」也跟着新鲜。watchlist 不在 daily 重选（保持月度稳定）。
        事件检测仍基于 watchlist 子集（不在 watchlist 的票评分波动不发 P0/P1）。

        候选池范围以 **watchlist.last_refresh（最近一次全扫描日）** 为准取
        snapshot codes —— 不能用 latest_date，因为 latest_date 一般是今天
        刚被 daily 写过的 21 只，会陷入"daily 只扫 21 → today 21 → 下次仍 21"。
        """
        scan_date = date.today().isoformat()

        last_full_date = await irminsul.watchlist_last_refresh()
        if not last_full_date:
            logger.info("[岩神·daily] watchlist 没有 refresh 记录，跑 full_scan 建候选池")
            return await self._full_scan(irminsul)

        # 从最近一次全扫描的 snapshot 完整记录里同时拿 codes + name + industry
        # 不能用 snapshot_latest_top —— 它取 latest_date=今天，今天只有 21 条
        # （上次 daily 写的 watchlist），候选池里非 watchlist 的 ~330 只 name/industry
        # 都拿不到，会让 entered/exited 列表无名 + 行业趋势出现 "未知 331 只"。
        full_snaps = await irminsul.snapshot_at_date(last_full_date)
        if not full_snaps:
            logger.info("[岩神·daily] 候选池为空（{}），自动改走 full_scan", last_full_date)
            return await self._full_scan(irminsul)

        codes = [s.stock_code for s in full_snaps]
        industry_map = {s.stock_code: s.industry for s in full_snaps}
        name_map = {s.stock_code: s.stock_name for s in full_snaps}
        logger.info(
            "[岩神·daily] 候选池 {} 只（基于 {} 全扫描结果）",
            len(codes), last_full_date,
        )

        board_by_codes = await self._skill_fetch_board_by_codes(codes)
        market = board_by_codes.get('market_data', {})
        # skill fetch-board --codes 不返 name/industry，用 snapshot 旧值补齐
        for code, info in market.items():
            if name_map.get(code) and not info.get('name'):
                info['name'] = name_map[code]
            if industry_map.get(code):
                info['industry'] = industry_map[code]
        merged_industry_map = {
            code: industry_map.get(code) or board_by_codes.get('industry_map', {}).get(code, '未知')
            for code in codes
        }

        # 不 clear today；snapshot_upsert ON CONFLICT 自带覆盖（见 _full_scan 注释）
        # prev 仍是 watchlist snap，事件检测保持 watchlist 范围（候选池其他票不发事件）
        prev = await irminsul.snapshot_latest_for_watchlist()

        dividends = await self._skill_fetch_dividend(codes)

        results: list[dict] = []
        total_div = len(dividends)
        for i, (code, div_info) in enumerate(dividends.items(), 1):
            info = market.get(code)
            if not info:
                continue
            scored = _score_single(
                code, div_info, None, info, merged_industry_map[code],
                apply_filter=False,
            )
            if scored:
                results.append(scored)
                await irminsul.snapshot_upsert(
                    scan_date, _result_to_snapshot(scan_date, scored), actor="岩神",
                )
            if i % 10 == 0 or i == total_div:
                self._set_progress("scoring_dividend", i, total_div, passed=len(results))

        # 补财务
        financials = await self._skill_fetch_financial(list(dividends.keys()))
        total_fin = len(results)
        for i, s in enumerate(results, 1):
            code = s['stock_data']['code']
            fin_info = financials.get(code)
            if fin_info is None:
                continue
            info = market.get(code)
            if not info:
                continue
            updated = _score_single(code, dividends.get(code, {}), fin_info, info,
                                    merged_industry_map[code], apply_filter=False)
            if updated:
                s.update(updated)
                await irminsul.snapshot_upsert(
                    scan_date, _result_to_snapshot(scan_date, updated), actor="岩神",
                )
            if i % 10 == 0 or i == total_fin:
                self._set_progress("scoring_financial", i, total_fin)

        results.sort(key=lambda x: x['total_score'], reverse=True)

        # daily 不改 watchlist，只检测变化
        changes = _detect_changes(results, prev, scan_date=scan_date)
        if changes:
            await irminsul.change_save(changes, actor="岩神")

        # 事件分级 + 持久化
        events = _aggregate_events(results, prev)
        await self._persist_events(events, results, scan_date, irminsul)

        # "推荐选股"前端语义是 watchlist（21 只行业均衡选出的），不是候选池 352 只。
        # daily 只刷数据不重选，所以 recommended 取当前 watchlist 的子集。
        watchlist = await irminsul.watchlist_get()
        watchlist_codes = {e.stock_code for e in watchlist}
        recommended = [s for s in results if s['stock_data']['code'] in watchlist_codes]

        return {
            'mode': 'daily', 'scan_date': scan_date,
            'total_scanned': len(codes),
            'stocks': results, 'recommended': recommended,
            'changes': changes,
            'events': events,
        }

    async def _rescore(self, irminsul: Irminsul) -> dict:
        """重评分：候选池 350+ 范围，仅"不抓网络"，其余跟日更对齐。

        与日更的差异：股息 / 财务走 cached_only；行情指标用最近一次全扫描
        snapshot 里的 price/pe/pb/市值（不另外抓 fetch-board）。
        与日更一致：扫描范围 = 候选池 350+；事件检测基于 watchlist；公告按日
        聚合（dedup_per_day=True）；recommended 取 watchlist 子集。
        """
        scan_date = date.today().isoformat()

        last_full_date = await irminsul.watchlist_last_refresh()
        if not last_full_date:
            logger.info("[岩神·rescore] 无全扫描历史，改走 full_scan 建候选池")
            return await self._full_scan(irminsul)

        full_snaps = await irminsul.snapshot_at_date(last_full_date)
        if not full_snaps:
            logger.info("[岩神·rescore] 候选池为空（{}），改走 daily", last_full_date)
            return await self._daily_update(irminsul)

        codes = [s.stock_code for s in full_snaps]
        industry_map = {s.stock_code: s.industry for s in full_snaps}
        # snap_map 提供 market_info 来源（重评分不抓 fetch-board）
        snap_map: dict[str, ScoreSnapshot] = {s.stock_code: s for s in full_snaps}
        logger.info(
            "[岩神·rescore] 候选池 {} 只（基于 {} 全扫描结果，纯 cache 重算）",
            len(codes), last_full_date,
        )

        # 缓存读股息 + 财务
        cached_div = await self._skill_fetch_dividend(codes, cached_only=True)
        cached_fin = await self._skill_fetch_financial(codes, cached_only=True)

        # prev 仍用 watchlist snap，事件检测保持 watchlist 范围
        prev = await irminsul.snapshot_latest_for_watchlist()

        results: list[dict] = []
        total = len(codes)
        for i, code in enumerate(codes, 1):
            div_info = cached_div.get(code)
            if not div_info:
                continue
            snap = snap_map.get(code)
            if not snap:
                continue
            market_info = {
                'name': snap.stock_name,
                'price': snap.detail.get('price', 0),
                'pe': snap.pe, 'pb': snap.pb,
                'market_cap': snap.market_cap,
                'is_st': snap.detail.get('is_st', 0),
            }
            fin_info = cached_fin.get(code)
            scored = _score_single(
                code, div_info, fin_info, market_info, industry_map[code],
                apply_filter=False,
            )
            if scored:
                results.append(scored)
                await irminsul.snapshot_upsert(
                    scan_date, _result_to_snapshot(scan_date, scored), actor="岩神",
                )
            if i % 50 == 0 or i == total:
                self._set_progress("scoring_rescore", i, total, passed=len(results))
                logger.info(
                    "[岩神·rescore] 评分进度 {}/{}，通过 {}", i, total, len(results),
                )

        results.sort(key=lambda x: x['total_score'], reverse=True)
        changes = _detect_changes(results, prev, scan_date=scan_date)
        if changes:
            await irminsul.change_save(changes, actor="岩神")

        events = _aggregate_events(results, prev)
        await self._persist_events(events, results, scan_date, irminsul)

        # recommended 取 watchlist 子集（与 daily 对齐）
        watchlist = await irminsul.watchlist_get()
        watchlist_codes = {e.stock_code for e in watchlist}
        recommended = [s for s in results if s['stock_data']['code'] in watchlist_codes]

        logger.info("[岩神·rescore] 完成 {} 只", len(results))
        return {
            'mode': 'rescore', 'scan_date': scan_date,
            'total_scanned': len(codes),
            'stocks': results, 'recommended': recommended,
            'changes': changes,
            'events': events,
        }
