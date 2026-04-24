"""岩神 · Zhongli — 契约·财富

职责分层（对齐 paimon 架构铁律）：
- scorer.py: 评分规则（纯函数：classify_stock / score_stock / build_reasons / build_advice）
- zhongli.py: 业务编排（scan 流程 + 变化检测 + 推送）+ 四影 execute 入口
- 存储：世界树 dividend 域（watchlist / snapshot / changes 三表）
- I/O：skill `skills/dividend-tracker` subprocess 调用
"""
from paimon.archons.zhongli.zhongli import ZhongliArchon

__all__ = ["ZhongliArchon"]
