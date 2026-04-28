"""评分引擎 v3.0 — 行业均衡化 + 银行偏向修复

5 维度 105 分 + 独立惩罚：
- 分红可持续性 (sustainability)  30 分
- 财务堡垒     (fortress)        25 分
- 估值安全边际 (valuation)       22 分（PB 分支 20，PE/PEG/PB_DEBT/PE_ROE 含 bonus 可达 22）
- 分红记录     (track_record)    18 分（含市值5分）
- 盈利动能     (momentum)        10 分
- 惩罚         (penalty)         <= 0

金融行业独立路径：银行/保险/证券的可持续性维度使用盈利留存率
替代 CFO/NP（金融业 CFO 含存贷/保费/自营活动，不可用于衡量
分红覆盖），派息率阈值按监管特征调整。

核心理念：评分回答"分红能不能持续"，而不仅仅是"分红高不高"。
"""
from __future__ import annotations

# ============================================================
# 行业分类
# ============================================================

CYCLICAL_INDUSTRIES = [
    "钢铁", "煤炭", "有色金属", "化工", "建材",
    "石油石化", "采掘", "建筑装饰", "房地产", "石油", "水泥",
]

DEFENSIVE_INDUSTRIES = [
    "银行", "电力", "公用事业", "高速公路", "水务",
    "机场", "港口", "燃气", "环保", "交通运输",
]

CONSUMER_INDUSTRIES = [
    "食品饮料", "医药生物", "家用电器", "纺织服装",
    "商业贸易", "休闲服务", "农林牧渔", "医药",
]

FINANCIAL_SECTOR_KEYWORDS = ["银行", "保险", "证券"]

INDUSTRY_VALUATION = {
    "银行":    {"metric": "PB",      "good": 0.7, "fair": 1.0},
    "保险":    {"metric": "PE",      "good": 12,  "fair": 18},
    "证券":    {"metric": "PB",      "good": 1.0, "fair": 1.5},
    "电力":    {"metric": "PE",      "good": 10,  "fair": 15},
    "公用事业": {"metric": "PE",     "good": 10,  "fair": 15},
    "高速公路": {"metric": "PE",     "good": 10,  "fair": 15},
    "交通运输": {"metric": "PE",     "good": 10,  "fair": 15},
    "食品饮料": {"metric": "PEG",    "good": 1.0, "fair": 1.5},
    "医药生物": {"metric": "PEG",    "good": 1.0, "fair": 1.5},
    "医药":    {"metric": "PEG",     "good": 1.0, "fair": 1.5},
    "制造业":   {"metric": "PE_ROE", "pe_good": 15, "roe_min": 10},
    "房地产":   {"metric": "PB_DEBT","pb_good": 1.0, "debt_max": 70},
    "周期股":   {"metric": "PB_DEBT","pb_good": 1.0, "debt_max": 70},
}


def _is_financial_sector(industry: str) -> bool:
    return any(k in industry for k in FINANCIAL_SECTOR_KEYWORDS)



def classify_stock(name: str, industry: str) -> dict:
    """分类股票"""
    is_cyclical = any(c in industry for c in CYCLICAL_INDUSTRIES)
    is_defensive = any(d in industry for d in DEFENSIVE_INDUSTRIES)
    is_consumer = any(c in industry for c in CONSUMER_INDUSTRIES)
    is_financial = _is_financial_sector(industry)

    valuation_standard = None
    valuation_metric = "PE"

    for key, standard in INDUSTRY_VALUATION.items():
        if key in industry:
            valuation_standard = standard
            valuation_metric = standard["metric"]
            break

    if valuation_standard is None:
        if is_cyclical:
            valuation_standard = INDUSTRY_VALUATION["周期股"]
            valuation_metric = "PB_DEBT"
        else:
            valuation_standard = {"metric": "PE", "good": 15, "fair": 25}

    return {
        "industry": industry,
        "is_cyclical": is_cyclical,
        "is_defensive": is_defensive,
        "is_consumer": is_consumer,
        "is_financial": is_financial,
        "valuation_metric": valuation_metric,
        "valuation_standard": valuation_standard,
    }



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


# ============================================================
# 可持续性维度 — 金融行业路径（银行/保险/证券）
# ============================================================

def _score_sustainability_financial(sc: dict, stock_data: dict, fd: dict):
    """金融行业的分红可持续性评分（30分）

    银行 CFO 含存贷款活动、保险含保费收入、证券含自营交易，
    CFO/NP 对金融行业无意义。改用：盈利留存率、净利润趋势。
    """
    payout = stock_data.get('payout_ratio', 0)
    dy = stock_data['dividend_yield']
    roe = fd.get('roe')

    # 1a. 派息率 — 金融版 (10)
    # v3.0: 最佳区间收窄 28-35%，大多数银行 28-35% 不再全部满分
    if payout > 0.7:
        sc['sustainability'] += -2
    elif payout > 0.5:
        sc['sustainability'] += 1
    elif payout > 0.4:
        sc['sustainability'] += 4
    elif payout > 0.35:
        sc['sustainability'] += 8   # 35-40% 接近最佳
    elif payout >= 0.28:
        sc['sustainability'] += 10  # 28-35% 金融行业最佳区间
    elif payout >= 0.25:
        sc['sustainability'] += 8   # 25-28% 接近最佳
    elif payout >= 0.15:
        sc['sustainability'] += 7
    elif payout > 0:
        sc['sustainability'] += 4

    # 1b. 盈利留存率 (10) = ROE × (1 - payout_ratio)
    # v3.0: 门槛上移，ROE 12%×0.7=8.4% 不再满分，需 ROE 14%+ 才满分
    if roe is not None and payout > 0:
        retained_rate = (roe / 100) * (1 - payout)
        if retained_rate >= 0.10:
            sc['sustainability'] += 10
        elif retained_rate >= 0.08:
            sc['sustainability'] += 8
        elif retained_rate >= 0.06:
            sc['sustainability'] += 5
        elif retained_rate >= 0.04:
            sc['sustainability'] += 3
        else:
            sc['sustainability'] += 0
    elif roe is not None:
        # payout = 0，全部留存
        sc['sustainability'] += 7

    # 1c. 净利润增长趋势 (5)
    # 比 fortress 的稳定性更严格：这里看增长方向
    net_profits_3y = fd.get('net_profits_3y', [])
    valid = [p for p in net_profits_3y if p is not None]
    if len(valid) >= 2:
        growing = all(valid[i] >= valid[i + 1] for i in range(len(valid) - 1))
        latest_growing = valid[0] >= valid[1] if len(valid) >= 2 else False
        any_decline = any(
            valid[i + 1] > 0 and (valid[i] - valid[i + 1]) / valid[i + 1] < -0.05
            for i in range(len(valid) - 1)
        )
        if growing:
            sc['sustainability'] += 5
        elif latest_growing:
            sc['sustainability'] += 3
        elif not any_decline:
            sc['sustainability'] += 2
    else:
        sc['sustainability'] += 1

    # 1d. 股息率区间 (5) — 同通用
    if dy >= 0.06:
        sc['sustainability'] += 5
    elif dy >= 0.05:
        sc['sustainability'] += 4
    elif dy >= 0.04:
        sc['sustainability'] += 3
    elif dy >= 0.03:
        sc['sustainability'] += 1


# ============================================================
# 可持续性维度 — 通用路径（非金融行业）
# ============================================================

def _score_sustainability_general(sc: dict, stock_data: dict, classification: dict, fd: dict):
    """非金融行业的分红可持续性评分（30分）"""
    payout = stock_data.get('payout_ratio', 0)
    dy = stock_data['dividend_yield']
    is_defensive = classification.get('is_defensive', False)

    # 1a. 派息率 — 行业分层 (10)
    if is_defensive:
        # 公用事业/交运/高速：现金流稳定，可承受更高派息
        if payout > 1.0:
            sc['sustainability'] += 0  # 惩罚由 P4 独立承担
        elif payout > 0.9:
            sc['sustainability'] += 1
        elif payout > 0.8:
            sc['sustainability'] += 4
        elif payout >= 0.4:
            sc['sustainability'] += 10  # 40-80% 防御性行业最佳区间
        elif payout >= 0.3:
            sc['sustainability'] += 7
        elif payout >= 0.2:
            sc['sustainability'] += 4
        elif payout > 0:
            sc['sustainability'] += 2
    else:
        # 一般行业 / 周期股
        if payout > 1.0:
            sc['sustainability'] += 0  # 惩罚由 P4 独立承担
        elif payout > 0.8:
            sc['sustainability'] += 0
        elif payout > 0.7:
            sc['sustainability'] += 4
        elif payout > 0.6:
            sc['sustainability'] += 7
        elif payout >= 0.3:
            sc['sustainability'] += 10  # 30-60% 通用最佳区间
        elif payout >= 0.25:
            sc['sustainability'] += 7
        elif payout >= 0.2:
            sc['sustainability'] += 4
        elif payout > 0:
            sc['sustainability'] += 2

    # 1b. 现金流覆盖 (10) — CFO/净利润
    cfo_to_np = fd.get('cfo_to_np')
    if cfo_to_np is not None:
        if cfo_to_np >= 1.2:
            sc['sustainability'] += 10
        elif cfo_to_np >= 1.0:
            sc['sustainability'] += 8
        elif cfo_to_np >= 0.7:
            sc['sustainability'] += 5
        elif cfo_to_np >= 0.4:
            sc['sustainability'] += 3

    # 1c. 现金派息率 (5)
    if cfo_to_np is not None and cfo_to_np > 0 and payout > 0:
        cash_payout = payout / cfo_to_np
        if cash_payout < 0.5:
            sc['sustainability'] += 5
        elif cash_payout < 0.7:
            sc['sustainability'] += 3
        elif cash_payout < 0.9:
            sc['sustainability'] += 1

    # 1d. 股息率区间 (5)
    if dy >= 0.06:
        sc['sustainability'] += 5
    elif dy >= 0.05:
        sc['sustainability'] += 4
    elif dy >= 0.04:
        sc['sustainability'] += 3
    elif dy >= 0.03:
        sc['sustainability'] += 1


# ============================================================
# 评分理由
# ============================================================

def build_reasons(stock_data: dict, score: dict, classification: dict,
                  financial_data: dict | None = None) -> list[str]:
    """生成评分理由列表"""
    reasons = []
    dy = stock_data['dividend_yield']
    pe = stock_data.get('pe', 0)
    pb = stock_data.get('pb', 0)
    history = stock_data['history_count']
    payout = stock_data.get('payout_ratio', 0)
    mcap_yi = stock_data.get('market_cap', 0) / 1e8
    metric = classification.get('valuation_metric', 'PE')
    recent = stock_data.get('recent_dividend_count', 1)
    is_financial = classification.get('is_financial', False)
    fd = financial_data or {}
    penalty = score.get('penalty', 0)

    # 维度 1: 可持续性
    parts_s = []
    if payout > 0:
        if is_financial:
            pr_lv = "危险" if payout > 0.7 else "偏高" if payout > 0.5 else "合理" if payout >= 0.25 else "偏低"
        else:
            pr_lv = "危险" if payout > 1.0 else "偏高" if payout > 0.8 else "偏高" if payout > 0.7 else "健康" if payout >= 0.3 else "偏低"
        parts_s.append(f"派息率{payout*100:.0f}%（{pr_lv}）")
    if is_financial:
        roe = fd.get('roe')
        if roe is not None and payout > 0:
            rr = (roe / 100) * (1 - payout)
            parts_s.append(f"留存率{rr*100:.1f}%")
    else:
        cfo = fd.get('cfo_to_np')
        if cfo is not None:
            cfo_lv = "充裕" if cfo >= 1.2 else "良好" if cfo >= 1.0 else "偏紧" if cfo >= 0.7 else "不足"
            parts_s.append(f"现金覆盖{cfo:.2f}（{cfo_lv}）")
    dy_lv = "超高" if dy >= 0.08 else "高" if dy >= 0.06 else "良好" if dy >= 0.05 else "中等"
    parts_s.append(f"股息率{dy*100:.1f}%（{dy_lv}）")
    reasons.append(f"[可持续 {score['sustainability']:.0f}/30] {' | '.join(parts_s)}")

    # 维度 2: 财务堡垒
    parts_f = []
    roe = fd.get('roe')
    if roe is not None:
        if is_financial:
            roe_lv = "优秀" if roe >= 12 else "良好" if roe >= 10 else "中等" if roe >= 8 else "偏低"
        else:
            roe_lv = "优秀" if roe >= 15 else "良好" if roe >= 12 else "中等" if roe >= 10 else "偏低"
        parts_f.append(f"ROE {roe:.1f}%（{roe_lv}）")
    nm = fd.get('net_margin')
    if nm is not None:
        parts_f.append(f"净利率{nm:.1f}%")
    gm = fd.get('gross_margin')
    if gm is not None and not is_financial:
        parts_f.append(f"毛利率{gm:.1f}%")
    dr = fd.get('debt_ratio')
    if dr is not None:
        dr_lv = "低" if dr < 50 else "中" if dr < 65 else "高"
        parts_f.append(f"负债率{dr:.1f}%（{dr_lv}）")
    net_profits_3y = fd.get('net_profits_3y', [])
    valid = [p for p in net_profits_3y if p is not None]
    if len(valid) >= 3:
        if all(p > 0 for p in valid):
            parts_f.append("3年盈利稳定")
        else:
            parts_f.append("盈利有波动")
    if parts_f:
        reasons.append(f"[堡垒 {score['fortress']:.0f}/25] {' | '.join(parts_f)}")
    else:
        reasons.append(f"[堡垒 {score['fortress']:.0f}/25] 财务数据缺失")

    # 维度 3: 估值
    vs = classification.get('valuation_standard', {})
    if metric == "PB":
        g = vs.get('good', 0.7)
        f = vs.get('fair', 1.0)
        lv = "深度低估" if pb < g * 0.7 else "低估" if pb < g else "合理偏低" if pb < (g + f) / 2 else "合理" if pb < f else "略高"
        reasons.append(f"[估值 {score['valuation']:.0f}/22] PB {pb:.2f}（{lv}），PE {pe:.1f}")
    elif metric == "PE":
        g = vs.get('good', 10)
        f = vs.get('fair', 15)
        lv = "低估" if pe < g else "合理偏低" if pe < (g + f) / 2 else "合理" if pe < f else "略高"
        reasons.append(f"[估值 {score['valuation']:.0f}/22] PE {pe:.1f}（{lv}），PB {pb:.2f}")
    elif metric == "PEG":
        _pg = fd.get('profit_growth')
        if _pg is not None and _pg > 0 and pe > 0:
            peg_val = pe / _pg
            reasons.append(f"[估值 {score['valuation']:.0f}/22] PEG {peg_val:.1f}（PE {pe:.1f}/增速{_pg:.0f}%）")
        else:
            reasons.append(f"[估值 {score['valuation']:.0f}/22] PE {pe:.1f}，无增速数据")
    elif metric == "PB_DEBT":
        st = "破净" if pb < 1.0 else "接近破净" if pb < 1.2 else "合理"
        dr_txt = f"，负债率{fd.get('debt_ratio', 0):.0f}%" if fd.get('debt_ratio') is not None else ""
        reasons.append(f"[估值 {score['valuation']:.0f}/22] 周期股PB {pb:.2f}（{st}）{dr_txt}")
    else:
        reasons.append(f"[估值 {score['valuation']:.0f}/22] PE {pe:.1f}，PB {pb:.2f}")

    # 维度 4: 分红记录
    stab = "超稳定" if history >= 20 else "稳定" if history >= 15 else "较稳定" if history >= 10 else "尚可"
    dn = f"近12月{recent}次" if recent > 1 else "年度分红"
    dps = stock_data.get('dividend_per_share', 0)
    prev_dps = stock_data.get('prev_dps', 0)
    dps_part = ""
    if prev_dps > 0 and dps > 0:
        dps_g = (dps - prev_dps) / prev_dps * 100
        dps_part = f"，DPS{'↑' if dps_g > 0 else '↓'}{abs(dps_g):.0f}%"
    reasons.append(f"[记录 {score['track_record']:.0f}/18] {stab}（累计{history}次，{dn}）{dps_part}")

    # 维度 5: 动能
    parts_m = []
    pg = fd.get('profit_growth')
    if pg is not None:
        pg_lv = "高增长" if pg >= 15 else "稳增" if pg >= 5 else "微增" if pg >= 0 else "负增长"
        parts_m.append(f"利润{pg:.1f}%（{pg_lv}）")
    fc = fd.get('forecast_type')
    if fc:
        parts_m.append(f"预告:{fc}")
    if parts_m:
        reasons.append(f"[动能 {score['momentum']:.0f}/10] {' | '.join(parts_m)}")
    else:
        reasons.append(f"[动能 {score['momentum']:.0f}/10] 数据缺失")

    # 惩罚标注
    if penalty < 0:
        reasons.append(f"[惩罚 {penalty:.0f}]")
    if classification['is_cyclical']:
        if pg is not None and pg >= 10:
            reasons.append("  * 周期股：当前景气高点，股息率可能不可持续")
        else:
            reasons.append("  * 周期股：景气度动态惩罚")
    if dy >= 0.07:
        reasons.append(f"  * 高息警告：股息率{dy*100:.1f}%")
    if stock_data.get('is_st', 0) == 1:
        reasons.append("  * ST 状态：严重风险")
    if payout > 1.0:
        reasons.append(f"  * 分红超盈利：派息率{payout*100:.0f}%")

    if classification['is_defensive'] and not classification['is_cyclical']:
        reasons.append("  * 防御性行业：适合长期配置")

    return reasons


# ============================================================
# 推荐建议生成（原 tracker.py _build_advice）
# ============================================================

def build_advice(score: dict, stock_data: dict, classification: dict) -> str:
    """基于评分维度生成简短推荐建议（可持续性导向）

    score 的 key 是新维度名：sustainability / fortress / valuation / track_record / momentum
    """
    total = sum(score.values())
    dy = stock_data['dividend_yield']
    payout = stock_data.get('payout_ratio', 0)
    parts = []

    # 总体评价
    if total >= 75:
        parts.append("强烈推荐")
    elif total >= 65:
        parts.append("推荐关注")
    elif total >= 55:
        parts.append("可关注")
    else:
        parts.append("谨慎观察")

    # 可持续性（核心维度）
    sus = score.get('sustainability', 0)
    if sus >= 25:
        parts.append("分红可持续性强")
    elif sus >= 18:
        parts.append("分红较可持续")
    elif sus < 10:
        parts.append("分红持续性存疑")

    # 股息
    if dy >= 0.06:
        parts.append("高股息")

    # 估值
    val = score.get('valuation', 0)
    if val >= 16:
        parts.append("估值偏低")
    elif val <= 6:
        parts.append("估值偏高")

    # 行业特征
    if classification['is_defensive'] and not classification['is_cyclical']:
        parts.append("防御性强")
    if classification['is_cyclical']:
        parts.append("注意周期波动")

    # 财务堡垒
    fort = score.get('fortress', 0)
    if fort >= 20:
        parts.append("财务稳固")
    elif fort <= 8:
        parts.append("财务一般")

    # DPS 增长
    prev_dps = stock_data.get('prev_dps', 0)
    dps = stock_data.get('dividend_per_share', 0)
    if prev_dps > 0 and dps > 0:
        if dps > prev_dps * 1.05:
            parts.append("分红在增长")
        elif dps < prev_dps * 0.95:
            parts.append("分红在下降")

    # 风险信号
    if payout > 1.0:
        parts.append("分红超盈利")
    if dy >= 0.08:
        parts.append("高息警惕")
    if stock_data.get('is_st', 0) == 1:
        parts.append("ST风险")

    return "，".join(parts)
