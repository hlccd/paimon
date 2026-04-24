"""岩神 · ZhongliArchon

两条入口：
1. `execute()` —— 四影管线复杂任务入口（原 LLM tool-loop，保留兼容）
2. `collect_dividend(mode)` —— cron 触发的红利股采集入口
   - subprocess 调 skill `dividend-tracker` 抓原始数据
   - in-process scorer 评分
   - 写世界树 dividend_snapshot / watchlist / changes
   - march.ring_event 推送到派蒙独占出口

另有查询 API：`get_recommended / get_top / get_changes / get_stock_history / handle_query`
供 WebUI `/wealth` 面板、`dividend` tool 和 LLM 自然语言调用。
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from paimon.archons.base import Archon
from paimon.archons.zhongli.scorer import (
    build_advice,
    build_reasons,
    classify_stock,
    format_recommended,
    format_report,
    score_stock,
)
from paimon.foundation.irminsul import (
    ChangeEvent,
    Irminsul,
    ScoreSnapshot,
    WatchlistEntry,
)
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session

if TYPE_CHECKING:
    from paimon.foundation.march import MarchService


# ============================================================
# 业务常量（属于岩神，不属于 skill）
# ============================================================

# 股息率硬门槛（full_scan 筛选）
MIN_DIVIDEND_YIELD = 0.03
# 连续分红年数硬门槛
MIN_HISTORY_COUNT = 5
# 流通市值前置过滤（元；full_scan 用，避免给 5800 只全拉 dividend）
MIN_MARKET_CAP = 50_0000_0000     # 50 亿
# watchlist 容量 + 行业均衡
WATCHLIST_SIZE = 25
MAX_PER_INDUSTRY = 5
MAX_INDUSTRIES = 10

# skill CLI 入口
_SKILL_MAIN_PY = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "skills" / "dividend-tracker" / "main.py"
)

# subprocess 超时
_FETCH_BOARD_TIMEOUT = 30 * 60    # full_scan 行情抓取 30 分钟
_FETCH_BATCH_TIMEOUT = 30 * 60    # dividend/financial 批量 30 分钟


_SYSTEM_PROMPT = """\
你是岩神·摩拉克斯，掌管契约与财富。你的职责是理财分析。

能力：
1. 红利股分析、资产配置建议、退休规划
2. 用 exec 工具执行 curl 查询市场数据（备用；主要数据由岩神自动采集）

规则：
1. 所有投资建议必须注明"仅供参考，不构成投资建议"
2. 数据要标明来源和时间
3. 输出结构化结果
4. 调用工具时不要输出过程描述，只输出最终结果
"""


# ============================================================
# 业务辅助函数（原 tracker.py）
# ============================================================


def _apply_sector_caps(ranked_stocks: list[dict]) -> list[dict]:
    """行业均衡选股（原 tracker.py _apply_sector_caps）。

    1. 按行业前 3 名均分排名，选出 TOP N 行业
    2. 按行业均分比例分配配额（最少 1，最多 MAX_PER_INDUSTRY）
    3. 每行业取评分最高的 N 只，不足配额不补
    """
    by_industry: dict[str, list[dict]] = {}
    for stock in ranked_stocks:
        ind = stock['stock_data'].get('industry', '')
        by_industry.setdefault(ind, []).append(stock)

    industry_avg: dict[str, float] = {}
    for ind, stocks in by_industry.items():
        top3 = stocks[:3]
        industry_avg[ind] = sum(s['total_score'] for s in top3) / len(top3)

    n_industries = min(MAX_INDUSTRIES, len(by_industry))
    top_industries = sorted(industry_avg, key=industry_avg.get, reverse=True)[:n_industries]

    if not top_industries:
        return []

    total_avg = sum(industry_avg[ind] for ind in top_industries)
    if total_avg <= 0:
        return []
    raw = {ind: industry_avg[ind] / total_avg * WATCHLIST_SIZE for ind in top_industries}
    quotas = {ind: max(1, min(MAX_PER_INDUSTRY, int(raw[ind]))) for ind in top_industries}

    leftover = WATCHLIST_SIZE - sum(quotas.values())
    if leftover > 0:
        by_remainder = sorted(
            top_industries,
            key=lambda ind: raw[ind] - int(raw[ind]),
            reverse=True,
        )
        for ind in by_remainder:
            if leftover <= 0:
                break
            if quotas[ind] < MAX_PER_INDUSTRY:
                quotas[ind] += 1
                leftover -= 1

    result: list[dict] = []
    for ind in top_industries:
        available = by_industry[ind][:quotas[ind]]
        result.extend(available)
        logger.info(
            "[岩神·选股] {} 均分={:.1f} 配额={} 实选={}",
            ind, industry_avg[ind], quotas[ind], len(available),
        )

    result.sort(key=lambda x: x['total_score'], reverse=True)
    return result


def _score_single(
    code: str,
    div_info: dict,
    fin_info: dict | None,
    market_info: dict,
    industry: str,
    apply_filter: bool = True,
) -> dict | None:
    """单只股票评分（搬自 tracker.py _score_single）。

    返回 `{stock_data, score, total_score, classification, reasons, advice}` 或 None（不满足门槛）。
    """
    if not div_info:
        return None

    price = market_info.get('price', 0)
    dps = div_info.get('dividend_per_share', 0)
    if price > 0 and dps > 0:
        dividend_yield = dps / price
    else:
        dividend_yield = div_info.get('dividend_yield', 0)

    avg_3y_dps = div_info.get('avg_3y_dps', 0)
    avg_3y_yield = avg_3y_dps / price if price > 0 and avg_3y_dps > 0 else 0.0

    if apply_filter:
        if dividend_yield < MIN_DIVIDEND_YIELD:
            return None
        if div_info.get('history_count', 0) < MIN_HISTORY_COUNT:
            return None

    classification = classify_stock(market_info.get('name', ''), industry)

    stock_data = {
        'code': code,
        'name': market_info.get('name', ''),
        'industry': industry,
        'dividend_yield': dividend_yield,
        'avg_3y_dividend_yield': avg_3y_yield,
        'dividend_per_share': dps,
        'prev_dps': div_info.get('prev_dps', 0),
        'payout_ratio': div_info.get('payout_ratio', 0),
        'history_count': div_info.get('history_count', 0),
        'status': div_info.get('status', ''),
        'recent_dividend_count': div_info.get('recent_dividend_count', 1),
        'pe': market_info.get('pe', 0),
        'pb': market_info.get('pb', 0),
        'market_cap': market_info.get('market_cap', 0),
        'price': price,
        'last_trade_date': market_info.get('last_trade_date', ''),
        'dividend_fy': div_info.get('dividend_fy', ''),
        'pcf_ncf_ttm': market_info.get('pcf_ncf_ttm', 0),
        'is_st': market_info.get('is_st', 0),
    }

    sc = score_stock(stock_data, classification, fin_info)
    reasons = build_reasons(stock_data, sc, classification, fin_info)
    advice = build_advice(sc, stock_data, classification)

    return {
        'stock_data': stock_data,
        'score': sc,
        'total_score': sum(sc.values()),
        'classification': classification,
        'reasons': reasons,
        'advice': advice,
        'financial_data': fin_info,
    }


def _result_to_snapshot(scan_date: str, result: dict) -> ScoreSnapshot:
    """业务 scan 结果 → ScoreSnapshot dataclass（准备写世界树）。"""
    sd = result['stock_data']
    sc = result['score']
    fin = result.get('financial_data') or {}
    return ScoreSnapshot(
        scan_date=scan_date,
        stock_code=sd['code'],
        stock_name=sd.get('name', ''),
        industry=sd.get('industry', ''),
        total_score=result['total_score'],
        sustainability_score=sc.get('sustainability', 0),
        fortress_score=sc.get('fortress', 0),
        valuation_score=sc.get('valuation', 0),
        track_record_score=sc.get('track_record', 0),
        momentum_score=sc.get('momentum', 0),
        penalty=sc.get('penalty', 0),
        dividend_yield=sd.get('dividend_yield', 0),
        pe=sd.get('pe', 0),
        pb=sd.get('pb', 0),
        roe=fin.get('roe') or 0,
        market_cap=sd.get('market_cap', 0),
        reasons='\n'.join(result.get('reasons', [])),
        advice=result.get('advice', ''),
        detail={
            'payout_ratio': sd.get('payout_ratio', 0),
            'history_count': sd.get('history_count', 0),
            'dividend_per_share': sd.get('dividend_per_share', 0),
            'prev_dps': sd.get('prev_dps', 0),
            'avg_3y_dividend_yield': sd.get('avg_3y_dividend_yield', 0),
            'price': sd.get('price', 0),
            'last_trade_date': sd.get('last_trade_date', ''),
            'is_st': sd.get('is_st', 0),
            'dividend_fy': sd.get('dividend_fy', ''),
            'classification': result.get('classification', {}),
        },
    )


def _detect_changes(
    current: list[dict],
    prev_snapshots: list[ScoreSnapshot],
    top_n: int = 30,
    scan_date: str = "",
) -> list[ChangeEvent]:
    """对比上一快照生成 entered/exited/score_change 事件。"""
    if not prev_snapshots:
        return []

    events: list[ChangeEvent] = []
    today_str = scan_date or date.today().isoformat()

    cur_top_codes = {s['stock_data']['code'] for s in current[:top_n]}
    prev_map: dict[str, ScoreSnapshot] = {s.stock_code: s for s in prev_snapshots}
    prev_top_codes = {s.stock_code for s in prev_snapshots[:top_n]}

    for s in current[:top_n]:
        code = s['stock_data']['code']
        name = s['stock_data'].get('name', '')
        total = s['total_score']
        dy = s['stock_data'].get('dividend_yield', 0)

        if code not in prev_top_codes:
            events.append(ChangeEvent(
                event_date=today_str, stock_code=code, stock_name=name,
                event_type='entered', new_value=total,
                description=f"评分 {total:.1f}，股息率 {dy * 100:.1f}%",
            ))
            continue

        prev = prev_map.get(code)
        if prev:
            diff = total - prev.total_score
            if abs(diff) >= 5:
                events.append(ChangeEvent(
                    event_date=today_str, stock_code=code, stock_name=name,
                    event_type='score_change',
                    old_value=prev.total_score, new_value=total,
                    description=f"{prev.total_score:.1f} -> {total:.1f} ({diff:+.1f})",
                ))

    for code in prev_top_codes - cur_top_codes:
        prev = prev_map.get(code)
        if not prev:
            continue
        events.append(ChangeEvent(
            event_date=today_str, stock_code=code, stock_name=prev.stock_name,
            event_type='exited', old_value=prev.total_score,
            description='跌出推荐列表',
        ))

    return events


# ============================================================
# Archon 主类
# ============================================================


class ZhongliArchon(Archon):
    name = "岩神"
    description = "理财、红利股、资产管理"
    allowed_tools = {"exec"}

    def __init__(self):
        self._scan_lock = asyncio.Lock()

    def is_scanning(self) -> bool:
        """是否正在跑扫描（supply 给 WebUI/tool 做并发保护）。"""
        return self._scan_lock.locked()

    # ---------- 四影路径（保留）----------

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[岩神] 执行子任务: {}", subtask.description[:80])

        system = _SYSTEM_PROMPT
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"

        temp_session = Session(id=f"zhongli-{task.id[:8]}", name="岩神分析")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="岩神", purpose="理财分析",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="岩神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="岩神",
        )
        logger.info("[岩神] 子任务完成, 结果长度={}", len(result))
        return result

    # ---------- 红利股采集主入口（cron 驱动）----------

    async def collect_dividend(
        self, *, mode: str,
        irminsul: Irminsul,
        march: "MarchService",
        chat_id: str = "", channel_name: str = "",
    ) -> None:
        """采集入口。mode ∈ 'full' / 'daily' / 'rescore'。"""
        if mode not in ("full", "daily", "rescore"):
            logger.error("[岩神·采集] 未知 mode: {}", mode)
            return

        async with self._scan_lock:
            logger.info("[岩神·采集] 开始 mode={}", mode)
            try:
                if mode == "full":
                    result = await self._full_scan(irminsul)
                elif mode == "daily":
                    result = await self._daily_update(irminsul)
                else:
                    result = await self._rescore(irminsul)
            except Exception as e:
                logger.exception("[岩神·采集] 失败 mode={}: {}", mode, e)
                return

            if not result or not result.get('stocks'):
                logger.info("[岩神·采集] 完成（无新数据） mode={}", mode)
                return

            # 推送
            if channel_name and chat_id:
                try:
                    message = self._format_push_message(mode, result)
                    await march.ring_event(
                        channel_name=channel_name, chat_id=chat_id,
                        source="岩神", message=message,
                    )
                except Exception as e:
                    logger.error("[岩神·推送] 失败: {}", e)

            logger.info(
                "[岩神·采集] 完成 mode={} qualified={} recommended={} changes={}",
                mode, len(result['stocks']), len(result.get('recommended', [])),
                len(result.get('changes', [])),
            )

    # ---------- scan 流程（full / daily / rescore）----------

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

        # 2. 岩神筛选市值
        candidates = [
            code for code, info in market.items()
            if info.get('market_cap', 0) >= MIN_MARKET_CAP
        ]
        logger.info("[岩神·full_scan] 全市场 {} 只 → 市值>=50亿 {} 只", total_scanned, len(candidates))

        # 3. 批量抓股息
        dividends = await self._skill_fetch_dividend(candidates)

        # 4. 读上次快照 + 清今日
        prev = await irminsul.snapshot_latest_for_watchlist()
        await irminsul.snapshot_clear_date(scan_date, actor="岩神")

        # 5. 初评（股息阶段，apply_filter=True 过硬门槛）
        results: list[dict] = []
        for code, div_info in dividends.items():
            info = market.get(code)
            if not info:
                continue
            industry = industry_map.get(code) or info.get('industry', '未知')
            scored = _score_single(code, div_info, None, info, industry, apply_filter=True)
            if scored:
                results.append(scored)
                await irminsul.snapshot_upsert(
                    scan_date, _result_to_snapshot(scan_date, scored), actor="岩神",
                )
        logger.info("[岩神·full_scan] 股息初筛通过 {} 只", len(results))

        # 6. 批量抓财务 + 二次评分
        codes_with_div = [s['stock_data']['code'] for s in results]
        financials = await self._skill_fetch_financial(codes_with_div)
        for s in results:
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

        # 10. 清 skill 过期缓存
        await self._skill_cleanup_cache()

        return {
            'mode': 'full',
            'scan_date': scan_date,
            'total_scanned': total_scanned,
            'stocks': results,
            'recommended': recommended,
            'changes': changes,
        }

    async def _daily_update(self, irminsul: Irminsul) -> dict:
        """日常更新：只扫 watchlist 股票。"""
        scan_date = date.today().isoformat()

        watchlist = await irminsul.watchlist_get()
        if not watchlist:
            logger.info("[岩神·daily] watchlist 为空，自动改走 full_scan")
            return await self._full_scan(irminsul)

        codes = [e.stock_code for e in watchlist]
        industry_map = {e.stock_code: e.industry for e in watchlist}
        name_map = {e.stock_code: e.stock_name for e in watchlist}
        logger.info("[岩神·daily] 追踪 {} 只", len(codes))

        board_by_codes = await self._skill_fetch_board_by_codes(codes)
        market = board_by_codes.get('market_data', {})
        # skill fetch-board --codes 只收到 code 不知 name/industry，
        # 用 watchlist 的 name + industry 补齐 market_info（否则 snapshot stock_name 空）
        for code, info in market.items():
            if name_map.get(code) and not info.get('name'):
                info['name'] = name_map[code]
            if industry_map.get(code):
                info['industry'] = industry_map[code]
        merged_industry_map = {
            code: industry_map.get(code) or board_by_codes.get('industry_map', {}).get(code, '未知')
            for code in codes
        }

        prev = await irminsul.snapshot_latest_for_watchlist()
        await irminsul.snapshot_clear_date(scan_date, actor="岩神")

        dividends = await self._skill_fetch_dividend(codes)

        results: list[dict] = []
        for code, div_info in dividends.items():
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

        # 补财务
        financials = await self._skill_fetch_financial(list(dividends.keys()))
        for s in results:
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

        results.sort(key=lambda x: x['total_score'], reverse=True)

        # daily 不改 watchlist，只检测变化
        changes = _detect_changes(results, prev, scan_date=scan_date)
        if changes:
            await irminsul.change_save(changes, actor="岩神")

        return {
            'mode': 'daily', 'scan_date': scan_date,
            'total_scanned': len(codes),
            'stocks': results, 'recommended': results,
            'changes': changes,
        }

    async def _rescore(self, irminsul: Irminsul) -> dict:
        """秒级重评分：只用 skill 缓存 + 上次快照的 market 指标。无网络 I/O。"""
        scan_date = date.today().isoformat()

        watchlist = await irminsul.watchlist_get()
        if not watchlist:
            logger.info("[岩神·rescore] watchlist 为空，跳过")
            return {'stocks': []}

        codes = [e.stock_code for e in watchlist]
        industry_map = {e.stock_code: e.industry for e in watchlist}

        # 市场数据从上次 snapshot 取（price/pe/pb/市值）
        last_date = await irminsul.snapshot_latest_date()
        if not last_date:
            logger.info("[岩神·rescore] 无历史快照，改走 daily")
            return await self._daily_update(irminsul)

        prev = await irminsul.snapshot_latest_for_watchlist()
        prev_map = {s.stock_code: s for s in prev}
        await irminsul.snapshot_clear_date(scan_date, actor="岩神")

        # 缓存读股息 + 财务
        cached_div = await self._skill_fetch_dividend(codes, cached_only=True)
        cached_fin = await self._skill_fetch_financial(codes, cached_only=True)

        results: list[dict] = []
        for code in codes:
            div_info = cached_div.get(code)
            if not div_info:
                continue
            snap = prev_map.get(code)
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

        results.sort(key=lambda x: x['total_score'], reverse=True)
        changes = _detect_changes(results, prev, scan_date=scan_date)
        if changes:
            await irminsul.change_save(changes, actor="岩神")

        logger.info("[岩神·rescore] 完成 {} 只", len(results))
        return {
            'mode': 'rescore', 'scan_date': scan_date,
            'total_scanned': len(codes),
            'stocks': results, 'recommended': results,
            'changes': changes,
        }

    # ---------- skill CLI 子进程调用 ----------

    async def _run_skill(self, args: list[str], timeout: float) -> dict:
        """调 skill main.py 子进程，返回解析后的 JSON dict。"""
        if not _SKILL_MAIN_PY.exists():
            raise RuntimeError(f"skill 入口不存在: {_SKILL_MAIN_PY}")

        cmd = [sys.executable, str(_SKILL_MAIN_PY), *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"skill 子进程超时 > {timeout}s: {args}")

        rc = proc.returncode or 0
        if rc != 0:
            err_txt = (err_b or b"").decode("utf-8", "ignore").strip()
            raise RuntimeError(f"skill 退出码 {rc}: {err_txt[:400]}")

        out_txt = (out_b or b"").decode("utf-8", "ignore").strip()
        if not out_txt:
            return {}
        try:
            return json.loads(out_txt)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"skill 输出非 JSON: {e}; head={out_txt[:200]}") from e

    async def _skill_fetch_board(self) -> dict:
        """全市场抓（full_scan 用）。"""
        return await self._run_skill(["fetch-board"], timeout=_FETCH_BOARD_TIMEOUT)

    async def _skill_fetch_board_by_codes(self, codes: list[str]) -> dict:
        """只抓指定股票行情（daily_update 用，走 skill fetch-board --codes）。"""
        if not codes:
            return {"industry_map": {}, "market_data": {}, "count": 0}
        args = ["fetch-board", "--codes", ",".join(codes)]
        # daily watchlist 通常 ≤25 只，几秒完成，给 5 分钟上限足够
        return await self._run_skill(args, timeout=5 * 60)

    async def _skill_fetch_dividend(
        self, codes: list[str], cached_only: bool = False,
    ) -> dict[str, dict]:
        if not codes:
            return {}
        args = ["fetch-dividend", "--codes", ",".join(codes)]
        if cached_only:
            args.append("--cached-only")
        data = await self._run_skill(args, timeout=_FETCH_BATCH_TIMEOUT)
        return data.get('dividends', {})

    async def _skill_fetch_financial(
        self, codes: list[str], cached_only: bool = False,
    ) -> dict[str, dict]:
        if not codes:
            return {}
        args = ["fetch-financial", "--codes", ",".join(codes)]
        if cached_only:
            args.append("--cached-only")
        data = await self._run_skill(args, timeout=_FETCH_BATCH_TIMEOUT)
        return data.get('financials', {})

    async def _skill_cleanup_cache(self) -> None:
        try:
            await self._run_skill(["cleanup-cache"], timeout=60)
        except Exception as e:
            logger.warning("[岩神·采集] 清缓存失败（可忽略）: {}", e)

    # ---------- 格式化（供推送 + query）----------

    def _format_push_message(self, mode: str, result: dict) -> str:
        """采集完成后发给用户的消息。"""
        scan_date = result.get('scan_date', '')
        recommended = result.get('recommended') or []
        changes = result.get('changes') or []

        parts = [f"📊 红利股扫描报告（{scan_date}·{mode}）\n"]
        if recommended:
            parts.append(self._format_recommended(recommended))
        if changes:
            parts.append("\n" + self._format_changes(changes))
        parts.append("\n⚠️ 以上数据仅供参考，不构成投资建议。")
        return '\n'.join(parts)

    @staticmethod
    def _format_recommended(stocks: list[dict]) -> str:
        """推荐选股精简版（供推送）。"""
        n = len(stocks)
        lines = [f"推荐选股（{n} 只）"]
        for i, s in enumerate(stocks[:15], 1):
            sd = s['stock_data']
            lines.append(
                f"{i}. {sd.get('name', '')}({sd['code']}) {sd.get('industry', '')} "
                f"· {s['total_score']:.1f}分 · "
                f"股息率{sd.get('dividend_yield', 0) * 100:.1f}% "
                f"· {s.get('advice', '')}"
            )
        if n > 15:
            lines.append(f"... 另有 {n - 15} 只，详见 /wealth 面板")
        return '\n'.join(lines)

    @staticmethod
    def _format_changes(changes: list[ChangeEvent]) -> str:
        entered = [c for c in changes if c.event_type == 'entered']
        exited = [c for c in changes if c.event_type == 'exited']
        score_up = [
            c for c in changes
            if c.event_type == 'score_change'
            and (c.new_value or 0) > (c.old_value or 0)
        ]
        score_down = [
            c for c in changes
            if c.event_type == 'score_change'
            and (c.new_value or 0) < (c.old_value or 0)
        ]

        lines = ["📈 变化动态:"]
        if entered:
            lines.append("-- 新入选 --")
            for c in entered[:10]:
                lines.append(f"  {c.stock_name}({c.stock_code}) — {c.description}")
        if exited:
            lines.append("-- 退出 --")
            for c in exited[:10]:
                lines.append(f"  {c.stock_name}({c.stock_code}) — {c.description}")
        if score_up:
            lines.append("-- 评分上升 --")
            for c in score_up[:10]:
                lines.append(f"  {c.stock_name}({c.stock_code}) — {c.description}")
        if score_down:
            lines.append("-- 评分下降 --")
            for c in score_down[:10]:
                lines.append(f"  {c.stock_name}({c.stock_code}) — {c.description}")
        return '\n'.join(lines)

    # ---------- 查询 API（供 tool / 面板 / LLM 调用）----------

    async def get_recommended(self, irminsul: Irminsul) -> list[ScoreSnapshot]:
        return await irminsul.snapshot_latest_for_watchlist()

    async def get_top(self, n: int, irminsul: Irminsul) -> list[ScoreSnapshot]:
        return await irminsul.snapshot_latest_top(n)

    async def get_changes(self, days: int, irminsul: Irminsul) -> list[ChangeEvent]:
        return await irminsul.change_recent(days)

    async def get_stock_history(
        self, code: str, days: int, irminsul: Irminsul,
    ) -> list[ScoreSnapshot]:
        return await irminsul.snapshot_history(code, days)

    async def handle_query(self, text: str, irminsul: Irminsul) -> str:
        """自然语言查询分派（/dividend 指令 + dividend tool 共用）。
        与 fairy tracker.py handle_query 等价（改为读世界树）。"""
        desc = (text or "").lower()

        if "排行" in desc or "排名" in desc or "top" in desc:
            rows = await self.get_top(100, irminsul)
            return self._format_ranking(rows) if rows else "暂无数据，请先跑 /dividend run-daily"

        if "推荐" in desc or "选股" in desc:
            recs = await self.get_recommended(irminsul)
            return self._format_recommended_snapshots(recs) if recs else "暂无推荐，请先跑 /dividend run-full"

        if "变化" in desc or "动态" in desc:
            chs = await self.get_changes(7, irminsul)
            return self._format_changes_list(chs) if chs else "最近 7 天无显著变化"

        if "详情" in desc or "趋势" in desc or "历史" in desc:
            code = _extract_code(desc)
            if code:
                history = await self.get_stock_history(code, 90, irminsul)
                return self._format_history(code, history)
            return "请指定 6 位股票代码（如：601988 历史）"

        # 默认：推荐 + 排行
        recs = await self.get_recommended(irminsul)
        top = await self.get_top(100, irminsul)
        parts: list[str] = []
        if recs:
            parts.append(self._format_recommended_snapshots(recs))
        if top:
            parts.append(self._format_ranking(top))
        return '\n\n'.join(parts) if parts else "暂无数据，请先跑 /dividend run-daily"

    # ---------- snapshot 文本格式化（handle_query 用）----------

    @staticmethod
    def _format_recommended_snapshots(rows: list[ScoreSnapshot]) -> str:
        n = len(rows)
        lines = [f"推荐选股（{n} 只，行业均衡）", "=" * 40]
        for i, r in enumerate(rows, 1):
            dy = r.dividend_yield * 100
            cap_yi = (r.market_cap or 0) / 1e8
            lines.append(
                f"{i}. {r.stock_name}({r.stock_code}) {r.industry} "
                f"· 评分{r.total_score:.1f} · 股息率{dy:.1f}% "
                f"· PE{r.pe:.1f} · 市值{cap_yi:.0f}亿"
            )
            if r.advice:
                lines.append(f"   {r.advice}")
        return '\n'.join(lines)

    @staticmethod
    def _format_ranking(rows: list[ScoreSnapshot]) -> str:
        n = len(rows)
        lines = [f"评分排行 TOP {n}", "=" * 40]
        for i, r in enumerate(rows, 1):
            dy = r.dividend_yield * 100
            cap_yi = (r.market_cap or 0) / 1e8
            lines.append(
                f"{i}. {r.stock_name}({r.stock_code}) {r.industry} "
                f"· {r.total_score:.1f} · 股息率{dy:.1f}% "
                f"· PE{r.pe:.1f} · PB{r.pb:.2f} · 市值{cap_yi:.0f}亿"
            )
            if r.reasons:
                for reason in r.reasons.split('\n'):
                    if reason.strip():
                        lines.append(f"     {reason.strip()}")
        return '\n'.join(lines)

    @staticmethod
    def _format_changes_list(changes: list[ChangeEvent]) -> str:
        lines = ["红利股最近变化"]
        for c in changes:
            lines.append(
                f"[{c.event_type}] {c.stock_name}({c.stock_code}) — {c.description}"
            )
        return '\n'.join(lines)

    @staticmethod
    def _format_history(code: str, history: list[ScoreSnapshot]) -> str:
        if not history:
            return f"{code} 无历史评分数据"
        lines = [f"{code} 历史评分趋势（近 {len(history)} 条）"]
        for h in history:
            lines.append(
                f"  {h.scan_date} · 总分 {h.total_score:.1f}"
                f" | 可持续 {h.sustainability_score:.0f}"
                f" | 财务 {h.fortress_score:.0f}"
                f" | 估值 {h.valuation_score:.0f}"
                f" | 记录 {h.track_record_score:.0f}"
                f" | 动能 {h.momentum_score:.0f}"
            )
        return '\n'.join(lines)


# ============================================================
# helper
# ============================================================


def _extract_code(text: str) -> str | None:
    m = re.search(r'(\d{6})', text)
    return m.group(1) if m else None
