"""评分引擎主路径 score_stock：5 维度 105 分 + 惩罚；按行业走 financial / general 分支。"""
from __future__ import annotations

from ._classify import (
    CYCLICAL_INDUSTRIES, DEFENSIVE_INDUSTRIES, CONSUMER_INDUSTRIES,
    INDUSTRY_VALUATION, _is_financial_sector,
)
from ._sustainability import _score_sustainability_financial, _score_sustainability_general



# ============================================================
# 评分函数 — 5 维度 100 分 + 独立惩罚
# ============================================================

def score_stock(stock_data: dict, classification: dict, financial_data: dict | None = None) -> dict:
    """
    多维度评分 -> {sustainability, fortress, valuation, track_record, momentum, penalty}

    penalty 独立于各维度，从总分中扣除。
    """
    sc: dict[str, float] = {
        'sustainability': 0, 'fortress': 0, 'valuation': 0,
        'track_record': 0, 'momentum': 0, 'penalty': 0,
    }

    dy = stock_data['dividend_yield']
    history = stock_data['history_count']
    pe = stock_data.get('pe', 0)
    pb = stock_data.get('pb', 0)
    mcap = stock_data.get('market_cap', 0)
    payout = stock_data.get('payout_ratio', 0)
    is_financial = classification.get('is_financial', False)
    is_defensive = classification.get('is_defensive', False)

    fd = financial_data or {}

    # ── 维度 1: 分红可持续性 (30) ──

    if is_financial:
        _score_sustainability_financial(sc, stock_data, fd)
    else:
        _score_sustainability_general(sc, stock_data, classification, fd)

    # ── 维度 2: 财务堡垒 (25) ──

    # 2a. ROE 质量 (8)
    roe = fd.get('roe')
    if roe is not None:
        if is_financial:
            if roe >= 12:   sc['fortress'] += 8
            elif roe >= 10: sc['fortress'] += 6
            elif roe >= 8:  sc['fortress'] += 4
            elif roe >= 6:  sc['fortress'] += 2
        else:
            if roe >= 15:   sc['fortress'] += 8
            elif roe >= 12: sc['fortress'] += 6
            elif roe >= 10: sc['fortress'] += 4
            elif roe >= 8:  sc['fortress'] += 2

    # 2b. 利润率 (5)
    net_margin = fd.get('net_margin')
    gross_margin = fd.get('gross_margin')
    if net_margin is not None:
        if is_financial:
            if net_margin >= 35:   sc['fortress'] += 5
            elif net_margin >= 30: sc['fortress'] += 4
            elif net_margin >= 25: sc['fortress'] += 3
            elif net_margin >= 20: sc['fortress'] += 1
        else:
            if net_margin >= 20:   sc['fortress'] += 3
            elif net_margin >= 15: sc['fortress'] += 2.5
            elif net_margin >= 10: sc['fortress'] += 2
            elif net_margin >= 5:  sc['fortress'] += 1
            # 毛利率补充（非金融，衡量成本转嫁能力）
            if gross_margin is not None:
                if gross_margin >= 40:   sc['fortress'] += 2
                elif gross_margin >= 25: sc['fortress'] += 1

    # 2c. 资产负债强度 (7)
    # v3.0: 金融豁免分 4→2（银行高负债是常态，不应大额加分）
    dr = fd.get('debt_ratio')
    if dr is not None and not is_financial:
        if dr < 50:    sc['fortress'] += 3
        elif dr < 60:  sc['fortress'] += 2
        elif dr < 70:  sc['fortress'] += 1
    elif is_financial:
        sc['fortress'] += 1

    cr = fd.get('current_ratio')
    if cr is not None and not is_financial:
        if cr >= 2.0:   sc['fortress'] += 2
        elif cr >= 1.5: sc['fortress'] += 1.5
        elif cr >= 1.0: sc['fortress'] += 1
    elif is_financial:
        sc['fortress'] += 0.5

    ic = fd.get('interest_coverage')
    if ic is not None and not is_financial:
        if ic >= 5:   sc['fortress'] += 2
        elif ic >= 3: sc['fortress'] += 1.5
        elif ic >= 1: sc['fortress'] += 1
    elif is_financial:
        sc['fortress'] += 0.5

    # 2d. 盈利稳定性 (5)
    net_profits_3y = fd.get('net_profits_3y', [])
    valid_profits = [p for p in net_profits_3y if p is not None]
    if len(valid_profits) >= 3:
        all_positive = all(p > 0 for p in valid_profits)
        big_drop = False
        for i in range(1, len(valid_profits)):
            if valid_profits[i - 1] > 0 and valid_profits[i] > 0:
                # (新 - 旧) / |旧|，列表按最新在前排列
                change = (valid_profits[i - 1] - valid_profits[i]) / abs(valid_profits[i])
                if change < -0.2:
                    big_drop = True
        if all_positive and not big_drop:
            sc['fortress'] += 5
        elif all_positive:
            sc['fortress'] += 3
        elif sum(1 for p in valid_profits if p > 0) >= 2:
            sc['fortress'] += 1
    elif len(valid_profits) >= 2:
        if all(p > 0 for p in valid_profits):
            sc['fortress'] += 2

    # ── 维度 3: 估值安全边际 (22) ──

    # 3a. 行业估值 (12-14) — 阈值由 INDUSTRY_VALUATION 驱动
    # v3.0: PB 分支满分 12，PE/PEG/PB_DEBT 分支含 bonus 可达 14
    metric = classification.get('valuation_metric', 'PE')
    vs = classification.get('valuation_standard', {})

    if metric == "PB":
        # 银行/证券：PB 估值，阈值由 good/fair 驱动
        # v3.0: 满分 14→12，收紧阈值避免常态性破净轻松满分
        g = vs.get('good', 0.7)
        f = vs.get('fair', 1.0)
        if pb > 0:
            if pb < g * 0.7:       sc['valuation'] += 12  # 真正深度低估
            elif pb < g:           sc['valuation'] += 10  # 低估
            elif pb < (g + f) / 2: sc['valuation'] += 8   # 合理偏低
            elif pb < f:           sc['valuation'] += 5   # 合理
            elif pb < f * 1.2:     sc['valuation'] += 3   # 略高

    elif metric == "PE":
        # 电力/公用事业/交运/保险：PE 估值，阈值由 good/fair 驱动
        g = vs.get('good', 10)
        f = vs.get('fair', 15)
        mid = (g + f) / 2
        if pe > 0:
            if pe < g:         sc['valuation'] += 12  # 低估
            elif pe < mid:     sc['valuation'] += 10  # 合理偏低
            elif pe < f:       sc['valuation'] += 7   # 合理
            elif pe < f * 1.2: sc['valuation'] += 4   # 略高
            else:              sc['valuation'] += 2
        if pb > 0 and pb < 2.0:
            sc['valuation'] += 2

    elif metric == "PEG":
        # 消费/医药：PEG 估值（PE/利润增速），无增速时退回 PE
        _pg = fd.get('profit_growth')
        if pe > 0 and _pg is not None and _pg > 0:
            peg = pe / _pg
            if peg < 1.0:    sc['valuation'] += 12
            elif peg < 1.5:  sc['valuation'] += 9
            elif peg < 2.0:  sc['valuation'] += 6
            else:             sc['valuation'] += 3
        elif pe > 0 and pe < 20:
            sc['valuation'] += 6   # 无增速，退回 PE 判断
        elif pe > 0 and pe < 30:
            sc['valuation'] += 3
        if dy >= 0.05:        sc['valuation'] += 2  # 高股息补偿
        elif dy >= 0.04:      sc['valuation'] += 1

    elif metric == "PE_ROE":
        if pe > 0:
            if pe < 10:   sc['valuation'] += 10
            elif pe < 15: sc['valuation'] += 7
            elif pe < 20: sc['valuation'] += 4
        if payout >= 0.4:   sc['valuation'] += 4
        elif payout >= 0.3: sc['valuation'] += 2

    elif metric == "PB_DEBT":
        # 周期股：PB + 负债率 bonus（弥补 PB 单指标上限不足）
        if pb > 0:
            if pb < 0.8:   sc['valuation'] += 10
            elif pb < 1.0: sc['valuation'] += 8
            elif pb < 1.2: sc['valuation'] += 5
            else:          sc['valuation'] += 2
        if dr is not None and dr < 50:
            sc['valuation'] += 4
        elif dr is not None and dr < 60:
            sc['valuation'] += 2

    else:
        if pe > 0 and pe < 15:    sc['valuation'] += 8
        elif pe > 0 and pe < 25:  sc['valuation'] += 5
        if pb > 0 and pb < 2.0:   sc['valuation'] += 4
        elif pb > 0 and pb < 3.0: sc['valuation'] += 2

    # 3b. 股息隐含安全边际 (8) — v3.0: 6→8 分，吸收 PB 缩减的 2 分
    if dy >= 0.06 and pe > 0 and pe < 12:
        sc['valuation'] += 8
    elif dy >= 0.05 and pe > 0 and pe < 15:
        sc['valuation'] += 6
    elif dy >= 0.04 and pe > 0 and pe < 18:
        sc['valuation'] += 4
    elif dy >= 0.04 and pe > 0 and pe < 25:
        sc['valuation'] += 2

    # ── 维度 4: 分红记录 (18) ──

    # 4a. 历史分红次数 (8)
    if history >= 20:   sc['track_record'] += 8
    elif history >= 15: sc['track_record'] += 7
    elif history >= 10: sc['track_record'] += 5
    elif history >= 7:  sc['track_record'] += 3
    elif history >= 5:  sc['track_record'] += 2

    # 4b. DPS 增长方向 (5)
    prev_dps = stock_data.get('prev_dps', 0)
    dps = stock_data.get('dividend_per_share', 0)
    if prev_dps > 0 and dps > 0:
        dps_growth = (dps - prev_dps) / prev_dps
        if dps_growth >= 0.10:
            sc['track_record'] += 5
        elif dps_growth > 0:
            sc['track_record'] += 3
        elif dps_growth > -0.05:
            sc['track_record'] += 2  # 基本持平
        else:
            sc['track_record'] += 0  # 分红下降
    elif dps > 0:
        sc['track_record'] += 1  # 无上年数据

    # 4c. 规模可靠性 (5) — 每500亿+0.5分，上限5
    mcap_yi = mcap / 1e8
    sc['track_record'] += min(5, int(mcap_yi / 500) * 0.5)

    # ── 维度 5: 盈利动能 (10) ──

    # 5a. 利润增长 (6) — 只用 YOYNI，不再重复 EPS
    pg = fd.get('profit_growth')
    if pg is not None:
        if pg >= 15:    sc['momentum'] += 6
        elif pg >= 8:   sc['momentum'] += 5
        elif pg >= 0:   sc['momentum'] += 3
        elif pg >= -10: sc['momentum'] += 1

    # 5b. 业绩预告信号 (4)
    forecast = fd.get('forecast_type')
    if forecast:
        fc = forecast.strip()
        if fc in ('预增', '扭亏'):
            sc['momentum'] += 4
        elif fc in ('续盈', '略增'):
            sc['momentum'] += 3
        elif fc == '略减':
            sc['momentum'] += 0  # 确认的负面信号，不应等同缺失
        elif fc in ('预减', '首亏', '续亏'):
            sc['momentum'] += 0
    else:
        # 缺失：金融行业常不发预告，给保守分；其他行业视为无信息
        if is_financial:
            sc['momentum'] += 1
        else:
            sc['momentum'] += 0

    # ── 惩罚机制（独立于维度，从总分扣除） ──

    # P1. 周期股惩罚 — 动态：景气越高惩罚越重
    if classification['is_cyclical']:
        if pg is not None and pg >= 10:
            sc['penalty'] -= 1   # 景气上行，风险较低
        elif pg is not None and pg < -10:
            sc['penalty'] -= 5   # 景气下行，利润下滑
        else:
            sc['penalty'] -= 3   # 基础惩罚
        if dr is not None and dr >= 65:
            sc['penalty'] -= 2

    # P2. 高息警告（价值陷阱信号）— 7.5%起扣，每超0.75%多扣1分，上限10
    if dy >= 0.075:
        sc['penalty'] -= min(10, int((dy - 0.075) / 0.0075) + 1)

    # P3. ST 状态
    if stock_data.get('is_st', 0) == 1:
        sc['penalty'] -= 10

    # P4. 分红超盈利
    if payout > 1.0:
        sc['penalty'] -= 5

    return sc
