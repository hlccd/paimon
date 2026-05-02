"""选股建议构造 build_advice：根据评分 + 行业给"买入/观察/回避"建议文本。"""
from __future__ import annotations


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
