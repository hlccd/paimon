"""岩神 · 评分引擎子包

5 维度 105 分 + 独立惩罚：
- 分红可持续性 (sustainability)  30 分
- 财务堡垒     (fortress)        25 分
- 估值安全边际 (valuation)       22 分
- 分红记录     (track_record)    18 分（含市值5分）
- 盈利动能     (momentum)        10 分
- 惩罚         (penalty)         <= 0

子模块：
- _classify.py        —— 行业常量 + classify_stock
- _score.py           —— score_stock 主路径
- _sustainability.py  —— 分红可持续性维度（金融 vs 一般行业）
- _reasons.py         —— build_reasons 中文理由文案
- _advice.py          —— build_advice 选股建议
"""
from __future__ import annotations

from ._advice import build_advice
from ._classify import (
    CONSUMER_INDUSTRIES,
    CYCLICAL_INDUSTRIES,
    DEFENSIVE_INDUSTRIES,
    FINANCIAL_SECTOR_KEYWORDS,
    INDUSTRY_VALUATION,
    classify_stock,
)
from ._reasons import build_reasons
from ._score import score_stock

__all__ = [
    "CONSUMER_INDUSTRIES",
    "CYCLICAL_INDUSTRIES",
    "DEFENSIVE_INDUSTRIES",
    "FINANCIAL_SECTOR_KEYWORDS",
    "INDUSTRY_VALUATION",
    "build_advice",
    "build_reasons",
    "classify_stock",
    "score_stock",
]
