"""评分理由文案构造 build_reasons：把评分细节转成用户可读的中文 bullet。"""
from __future__ import annotations

from ._classify import _is_financial_sector


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
