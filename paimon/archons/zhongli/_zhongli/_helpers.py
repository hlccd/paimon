"""岩神 · 模块级业务辅助：行业均衡 / 评分单股 / 事件聚合 / 变动检测。"""
from __future__ import annotations

from datetime import date

from loguru import logger

from paimon.archons.zhongli.scorer import (
    build_advice, build_reasons, classify_stock, score_stock,
)
from paimon.foundation.irminsul import ChangeEvent, ScoreSnapshot


# ============================================================
# 业务常量（原 zhongli.py 顶部；mixin 多模块共用，避免循环 import）
# ============================================================

MIN_DIVIDEND_YIELD = 0.04
MIN_HISTORY_COUNT = 5
MIN_MARKET_CAP = 100_0000_0000        # 100 亿
WATCHLIST_SIZE = 25
MAX_PER_INDUSTRY = 5
MAX_INDUSTRIES = 10


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
