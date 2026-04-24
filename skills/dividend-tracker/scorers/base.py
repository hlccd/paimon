#!/usr/bin/env python3
"""
行业分类器 - 识别股票所属行业并判断是否为周期股
"""

import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("错误：缺少依赖，请运行: pip install pandas")
    sys.exit(1)

# 周期性行业列表
CYCLICAL_INDUSTRIES = [
    "钢铁", "煤炭", "有色金属", "化工", "建材",
    "石油石化", "采掘", "建筑装饰", "房地产"
]

# 防御性行业列表
DEFENSIVE_INDUSTRIES = [
    "银行", "电力", "公用事业", "高速公路", "水务",
    "机场", "港口", "燃气", "环保"
]

# 消费类行业
CONSUMER_INDUSTRIES = [
    "食品饮料", "医药生物", "家用电器", "纺织服装",
    "商业贸易", "休闲服务", "农林牧渔"
]

# 行业估值标准
INDUSTRY_VALUATION = {
    "银行": {"metric": "PB", "good": 0.7, "fair": 1.0},
    "电力": {"metric": "PE", "good": 10, "fair": 15},
    "公用事业": {"metric": "PE", "good": 10, "fair": 15},
    "高速公路": {"metric": "PE", "good": 10, "fair": 15},
    "食品饮料": {"metric": "PEG", "good": 1.0, "fair": 1.5},
    "医药生物": {"metric": "PEG", "good": 1.0, "fair": 1.5},
    "制造业": {"metric": "PE_ROE", "pe_good": 15, "roe_min": 10},
    "房地产": {"metric": "PB_DEBT", "pb_good": 1.0, "debt_max": 70},
    "周期股": {"metric": "PB_DEBT", "pb_good": 1.0, "debt_max": 70},
}


def classify_stock(stock_name: str, industry: str) -> dict:
    """
    分类股票并返回分类信息

    Returns:
        {
            "industry": str,
            "is_cyclical": bool,
            "is_defensive": bool,
            "valuation_metric": str,
            "valuation_standard": dict
        }
    """
    is_cyclical = any(cyc in industry for cyc in CYCLICAL_INDUSTRIES)
    is_defensive = any(def_ind in industry for def_ind in DEFENSIVE_INDUSTRIES)
    is_consumer = any(cons in industry for cons in CONSUMER_INDUSTRIES)

    # 确定估值标准
    valuation_standard = None
    valuation_metric = "PE"  # 默认

    for ind_key, standard in INDUSTRY_VALUATION.items():
        if ind_key in industry:
            valuation_standard = standard
            valuation_metric = standard["metric"]
            break

    # 默认估值标准
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
        "valuation_metric": valuation_metric,
        "valuation_standard": valuation_standard
    }


def get_market_cap_requirement(is_cyclical: bool) -> int:
    """获取市值要求（元）"""
    if is_cyclical:
        return 20_000_000_000  # 200亿
    else:
        return 5_000_000_000   # 50亿


if __name__ == "__main__":
    # 测试
    test_cases = [
        ("长江电力", "电力"),
        ("中国神华", "煤炭"),
        ("贵州茅台", "食品饮料"),
        ("招商银行", "银行"),
        ("中国建筑", "建筑装饰"),
    ]

    for name, industry in test_cases:
        result = classify_stock(name, industry)
        print(f"\n{name} ({industry})")
        print(f"  周期股: {result['is_cyclical']}")
        print(f"  防御股: {result['is_defensive']}")
        print(f"  估值指标: {result['valuation_metric']}")
        print(f"  估值标准: {result['valuation_standard']}")
