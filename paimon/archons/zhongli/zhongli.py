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
import os
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

# subprocess 活性超时：连续 5 分钟无 stderr 活动才 kill。
# 旧版用全程死线（fetch-board 1800s），但 BaoStock 单连接串行 + 网络方差大 →
# 5500 只行情快则 6 分钟、慢则 60 分钟，单一阈值无法兼顾。改为活性判定后，
# 只要 skill 还在打进度日志（每 500 只一条 board / 每 20 只一条 dividend）
# 就续命；真卡住才 kill。
_SKILL_IDLE_TIMEOUT = 5 * 60


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


# ============================================================
# 事件分级（A1：规则驱动日报的基础）
# ============================================================
# 按严重度分四档，规则判定（无 LLM）：
#   p0 致命：停分红 / 新 ST / 评分暴跌 >=20 / 分红历史断档
#   p1 警示：股息率骤跌 >=30% / 评分下滑 10-20
#   p2 提醒：评分小幅变化 5-10 / 新入选 / 退出 top30
#   p3 噪音：仅微调，不进日报
# 输出给 _compose_daily_digest 拼 markdown；同一股一轮只出一个最严重事件。

def _classify_event_severity(
    stock_data: dict,
    cur_score: float,
    prev_snap: ScoreSnapshot | None,
) -> tuple[str, str, str] | None:
    """判定单只股票本轮最严重的事件。返回 (severity, kind, reason) 或 None（无事件）。

    stock_data: 来自 scan_result 的 stock_data dict（含 dividend_yield / is_st / history_count）
    cur_score: 本次 total_score
    prev_snap: 上次快照（None 表示无历史，跳过对比类事件）
    """
    cur_dy = stock_data.get('dividend_yield', 0) or 0
    cur_is_st = stock_data.get('is_st', 0) or 0
    cur_history = stock_data.get('history_count', 0) or 0

    if prev_snap is None:
        return None  # 首次出现，交给 _detect_changes 的 entered 事件处理

    prev_dy = prev_snap.dividend_yield or 0
    prev_score = prev_snap.total_score or 0
    prev_detail = prev_snap.detail or {}
    prev_is_st = prev_detail.get('is_st', 0) or 0
    prev_history = prev_detail.get('history_count', 0) or 0

    score_drop = prev_score - cur_score  # 正数 = 下跌

    # --- P0 致命 ---
    if cur_is_st and not prev_is_st:
        return ('p0', 'st_risen', f'股票被标 ST（上次未标）')
    if prev_dy > 0.01 and cur_dy <= 0.001:
        return ('p0', 'dividend_halt',
                f'股息率跌至 {cur_dy * 100:.2f}%（上次 {prev_dy * 100:.2f}%），疑似停分红')
    if score_drop >= 20:
        return ('p0', 'score_crash',
                f'评分暴跌 {score_drop:.1f} 分（{prev_score:.1f} → {cur_score:.1f}）')
    if prev_history >= MIN_HISTORY_COUNT and cur_history < MIN_HISTORY_COUNT:
        return ('p0', 'history_broken',
                f'连续分红年数跌破 {MIN_HISTORY_COUNT} 年（{prev_history} → {cur_history}）')

    # --- P1 警示 ---
    if prev_dy > 0.01 and (prev_dy - cur_dy) / prev_dy >= 0.3:
        drop_pct = (prev_dy - cur_dy) / prev_dy * 100
        return ('p1', 'dividend_drop',
                f'股息率骤跌 {drop_pct:.0f}%（{prev_dy * 100:.2f}% → {cur_dy * 100:.2f}%）')
    if score_drop >= 10:
        return ('p1', 'score_decline',
                f'评分下滑 {score_drop:.1f} 分（{prev_score:.1f} → {cur_score:.1f}）')

    # --- P2 普通变化 ---
    if abs(prev_score - cur_score) >= 5:
        diff = cur_score - prev_score
        return ('p2', 'score_change',
                f'评分变化 {diff:+.1f}（{prev_score:.1f} → {cur_score:.1f}）')

    return None  # P3：无需进日报


def _aggregate_events(
    current: list[dict],
    prev_snapshots: list[ScoreSnapshot],
) -> dict[str, list[dict]]:
    """为每只股票判事件，按 severity 分组。

    返回 {'p0': [...], 'p1': [...], 'p2': [...]}，每个 item:
    {stock_code, stock_name, industry, kind, reason, total_score, dividend_yield}
    """
    prev_map = {s.stock_code: s for s in (prev_snapshots or [])}
    grouped: dict[str, list[dict]] = {'p0': [], 'p1': [], 'p2': []}

    for s in current:
        sd = s.get('stock_data') or {}
        code = sd.get('code', '')
        if not code:
            continue
        prev = prev_map.get(code)
        verdict = _classify_event_severity(sd, s.get('total_score', 0), prev)
        if verdict is None:
            continue
        severity, kind, reason = verdict
        grouped[severity].append({
            'stock_code': code,
            'stock_name': sd.get('name', ''),
            'industry': sd.get('industry', ''),
            'severity': severity,
            'kind': kind,
            'reason': reason,
            'total_score': s.get('total_score', 0),
            'dividend_yield': sd.get('dividend_yield', 0),
            'prev_score': (prev.total_score if prev else 0),
        })

    # 每档内按 |score_drop| 排序，严重的在前
    for sev in grouped:
        grouped[sev].sort(
            key=lambda x: abs(x['prev_score'] - x['total_score']),
            reverse=True,
        )
    return grouped


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
        # 当前扫描进度（供 /api/wealth/running 暴露给前端状态条）。
        # None = 未在扫描；扫描中至少包含 {stage, cur, total, started_at, updated_at}，
        # 各阶段（board/board_codes/dividend/financial/scoring）可附带额外字段如
        # valid/success/mode 等。
        self._progress: dict | None = None

    def is_scanning(self) -> bool:
        """是否正在跑扫描（supply 给 WebUI/tool 做并发保护）。"""
        return self._scan_lock.locked()

    def get_progress(self) -> dict | None:
        """当前扫描进度快照（None 表示未在跑）。"""
        return self._progress

    def _set_progress(self, stage: str, cur: int, total: int, **extra) -> None:
        now = time.time()
        prev = self._progress or {}
        self._progress = {
            "stage": stage,
            "cur": cur,
            "total": total,
            "started_at": prev.get("started_at", now),
            "updated_at": now,
            **extra,
        }

    # ---------- 四影路径（保留）----------

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[岩神] 执行子任务: {}", subtask.description[:80])

        from paimon.archons.base import FINAL_OUTPUT_RULE
        system = _SYSTEM_PROMPT
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"
        system += FINAL_OUTPUT_RULE

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
            self._set_progress("init", 0, 0, mode=mode)
            try:
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

                # 推送日报（digest · markdown）—— source="岩神·理财日报" 与旧 snapshot 推送区分
                # extra 塞 {p0_count, p1_count, ...} 供 /api/wealth/stats 查近 7 天统计
                if channel_name and chat_id:
                    try:
                        events = result.get('events') or {'p0': [], 'p1': [], 'p2': []}
                        digest_md, meta = self._compose_daily_digest(mode, result, events)
                        await march.ring_event(
                            channel_name=channel_name, chat_id=chat_id,
                            source="岩神·理财日报", message=digest_md,
                            extra=meta,
                        )
                    except Exception as e:
                        logger.error("[岩神·推送] 失败: {}", e)

                p0n = len((result.get('events') or {}).get('p0') or [])
                p1n = len((result.get('events') or {}).get('p1') or [])
                logger.info(
                    "[岩神·采集] 完成 mode={} qualified={} recommended={} changes={} p0={} p1={}",
                    mode, len(result['stocks']), len(result.get('recommended', [])),
                    len(result.get('changes', [])), p0n, p1n,
                )
            finally:
                # 任何路径结束（成功/失败/无数据）都清进度，避免前端一直"采集中"
                self._progress = None

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

        # 10. 事件分级（供日报用）
        events = _aggregate_events(results, prev)

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

        # 不 clear today；snapshot_upsert ON CONFLICT 自带覆盖（见 _full_scan 注释）
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

        # 事件分级
        events = _aggregate_events(results, prev)

        return {
            'mode': 'daily', 'scan_date': scan_date,
            'total_scanned': len(codes),
            'stocks': results, 'recommended': results,
            'changes': changes,
            'events': events,
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

        # 不 clear today；snapshot_upsert ON CONFLICT 自带覆盖（见 _full_scan 注释）。
        # rescore 这里是最关键的——cached_only 命中率不到 100% 时旧路径会丢光 today
        prev = await irminsul.snapshot_latest_for_watchlist()
        prev_map = {s.stock_code: s for s in prev}

        # 缓存读股息 + 财务
        cached_div = await self._skill_fetch_dividend(codes, cached_only=True)
        cached_fin = await self._skill_fetch_financial(codes, cached_only=True)

        results: list[dict] = []
        total = len(codes)
        for i, code in enumerate(codes, 1):
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
            if i % 10 == 0 or i == total:
                self._set_progress("scoring_rescore", i, total, passed=len(results))
                await irminsul.snapshot_upsert(
                    scan_date, _result_to_snapshot(scan_date, scored), actor="岩神",
                )

        results.sort(key=lambda x: x['total_score'], reverse=True)
        changes = _detect_changes(results, prev, scan_date=scan_date)
        if changes:
            await irminsul.change_save(changes, actor="岩神")

        events = _aggregate_events(results, prev)

        logger.info("[岩神·rescore] 完成 {} 只", len(results))
        return {
            'mode': 'rescore', 'scan_date': scan_date,
            'total_scanned': len(codes),
            'stocks': results, 'recommended': results,
            'changes': changes,
            'events': events,
        }

    # ---------- skill CLI 子进程调用 ----------

    async def _run_skill(self, args: list[str]) -> dict:
        """调 skill main.py 子进程，返回解析后的 JSON dict。

        - stderr 透传到 paimon 日志，并解析 ``PROGRESS: {...}`` 行 update self._progress
        - 活性超时：连续 _SKILL_IDLE_TIMEOUT 秒无 stderr 活动才 kill（旧版用全程死线，
          BaoStock 速率方差太大会错杀）
        - 子进程环境：PAIMON_SKILL_RUNTIME=1 让 skill loguru 切极简 format（避免双重时间戳）；
          PYTHONIOENCODING=utf-8 兜底 Windows cp936 中文乱码
        """
        if not _SKILL_MAIN_PY.exists():
            raise RuntimeError(f"skill 入口不存在: {_SKILL_MAIN_PY}")

        cmd = [sys.executable, str(_SKILL_MAIN_PY), *args]
        skill_tag = args[0] if args else "skill"
        logger.info("[岩神·skill/{}] 启动子进程 args={}", skill_tag, args)
        start_ts = time.time()
        env = {**os.environ, "PAIMON_SKILL_RUNTIME": "1", "PYTHONIOENCODING": "utf-8"}
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        last_activity_ts = time.time()

        async def _pump_stdout() -> None:
            """收 stdout 到内存（JSON 完整拿回来再 parse，不流式打日志避免刷屏）。"""
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.read(8192)
                if not chunk:
                    break
                stdout_chunks.append(chunk)

        async def _pump_stderr() -> None:
            """stderr 按行实时打 paimon INFO + 解析 PROGRESS 行更新进度。"""
            nonlocal last_activity_ts
            assert proc.stderr is not None
            async for raw_line in proc.stderr:
                last_activity_ts = time.time()  # 续命
                line = raw_line.decode("utf-8", "ignore").rstrip()
                stderr_chunks.append(raw_line)
                if not line:
                    continue
                # PROGRESS: {...} 是 skill 给 paimon 的结构化信号，不打日志（噪音）
                if line.startswith("PROGRESS: "):
                    try:
                        prog = json.loads(line[len("PROGRESS: "):])
                        if isinstance(prog, dict) and "stage" in prog:
                            self._set_progress(
                                prog["stage"],
                                int(prog.get("cur", 0)),
                                int(prog.get("total", 0)),
                                **{k: v for k, v in prog.items()
                                   if k not in ("stage", "cur", "total")},
                            )
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass
                    continue
                logger.info("[岩神·skill/{}] {}", skill_tag, line[:500])

        async def _watchdog() -> None:
            """每 30s 检查一次活性 + 打心跳；连续 _SKILL_IDLE_TIMEOUT 秒无 stderr 活动 → kill。"""
            while True:
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    return
                idle = time.time() - last_activity_ts
                elapsed = time.time() - start_ts
                if idle > _SKILL_IDLE_TIMEOUT:
                    logger.error(
                        "[岩神·skill/{}] {:.0f}s 无 stderr 活动，判定卡死，kill",
                        skill_tag, idle,
                    )
                    proc.kill()
                    return
                logger.info(
                    "[岩神·skill/{}] 仍在运行 {:.0f}s（{:.0f}s 前最后活动；空闲超 {:.0f}s 即 kill）",
                    skill_tag, elapsed, idle, _SKILL_IDLE_TIMEOUT,
                )

        wd_task = asyncio.create_task(_watchdog())
        try:
            await asyncio.gather(_pump_stdout(), _pump_stderr(), proc.wait())
        finally:
            wd_task.cancel()
            try:
                await wd_task
            except asyncio.CancelledError:
                pass

        out_b = b"".join(stdout_chunks)
        err_b = b"".join(stderr_chunks)
        elapsed = time.time() - start_ts
        logger.info(
            "[岩神·skill/{}] 结束 rc={} 耗时={:.1f}s stdout={}B stderr={}B",
            skill_tag, proc.returncode, elapsed, len(out_b), len(err_b),
        )

        rc = proc.returncode or 0
        if rc != 0:
            err_txt = (err_b or b"").decode("utf-8", "ignore").strip()
            # watchdog kill 时 returncode 通常为 -9 / -SIGKILL，给明确错误
            if rc < 0:
                raise RuntimeError(
                    f"skill 子进程被活性 watchdog kill（{_SKILL_IDLE_TIMEOUT}s 无活动）: {args}"
                )
            raise RuntimeError(f"skill 退出码 {rc}: {err_txt[:400]}")

        out_txt = (out_b or b"").decode("utf-8", "ignore").strip()
        if not out_txt:
            return {}
        # BaoStock CLI 登录成功时会往 stdout 打 "login success!\n" 污染 JSON，
        # 从首个 '{' 或 '[' 开始解析跳过非 JSON 前缀
        json_start = -1
        for i, ch in enumerate(out_txt):
            if ch in "{[":
                json_start = i
                break
        if json_start < 0:
            return {}
        json_txt = out_txt[json_start:]
        try:
            return json.loads(json_txt)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"skill 输出非 JSON: {e}; head={json_txt[:200]}"
            ) from e

    async def _skill_fetch_board(self) -> dict:
        """全市场抓（full_scan 用）。"""
        return await self._run_skill(["fetch-board"])

    async def _skill_fetch_board_by_codes(self, codes: list[str]) -> dict:
        """只抓指定股票行情（daily_update 用，走 skill fetch-board --codes）。"""
        if not codes:
            return {"industry_map": {}, "market_data": {}, "count": 0}
        args = ["fetch-board", "--codes", ",".join(codes)]
        return await self._run_skill(args)

    async def _skill_fetch_dividend(
        self, codes: list[str], cached_only: bool = False,
    ) -> dict[str, dict]:
        if not codes:
            return {}
        args = ["fetch-dividend", "--codes", ",".join(codes)]
        if cached_only:
            args.append("--cached-only")
        data = await self._run_skill(args)
        return data.get('dividends', {})

    async def _skill_fetch_financial(
        self, codes: list[str], cached_only: bool = False,
    ) -> dict[str, dict]:
        if not codes:
            return {}
        args = ["fetch-financial", "--codes", ",".join(codes)]
        if cached_only:
            args.append("--cached-only")
        data = await self._run_skill(args)
        return data.get('financials', {})

    async def _skill_cleanup_cache(self) -> None:
        try:
            await self._run_skill(["cleanup-cache"])
        except Exception as e:
            logger.warning("[岩神·采集] 清缓存失败（可忽略）: {}", e)

    # ---------- 格式化（供推送 + query）----------

    # ---------- 日报生成（A1 · 规则驱动 markdown digest）----------

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

        # --- 行业趋势：按行业取 TOP3 均值排序，列 Top5 ---
        by_industry: dict[str, list[float]] = {}
        for s in stocks:
            ind = (s.get('stock_data') or {}).get('industry') or '未知'
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
