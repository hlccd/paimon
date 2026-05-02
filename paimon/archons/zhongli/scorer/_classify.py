"""评分引擎 v3.0 — 行业常量 + classify_stock 入口（按行业分类返回 cyclical/defensive/consumer/general）。"""
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
