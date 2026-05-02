"""分红可持续性维度评分：金融行业（盈利留存率）vs 一般行业（CFO/NP）双路径。"""
from __future__ import annotations


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
