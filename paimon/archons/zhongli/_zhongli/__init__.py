"""岩神 · ZhongliArchon 拆分实现子包：4 个 mixin + 模块级 helper + 注册。

子模块（不对外，由 paimon.archons.zhongli.zhongli 重新组合 + re-export）：
- _helpers.py   —— _apply_sector_caps / _score_single / _result_to_snapshot 等模块级 helper
- _scan.py      —— _ScanMixin: full / daily / rescore 三档扫描
- _skill.py     —— _SkillMixin: subprocess 跑 dividend-tracker 6 个动作
- _watch.py     —— _WatchMixin: 用户关注股价格采集 + 偏离阈值预警
- _digest.py    —— _DigestMixin: 每日 digest 组装 + 事件持久化
- _register.py  —— register_task_types / register_subscription_types / ensure/clear_stock_subscriptions
"""
from __future__ import annotations
