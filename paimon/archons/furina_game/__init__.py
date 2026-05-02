"""水神 · 游戏信息服务（米哈游游戏：原神/星铁/绝区零）子包

子模块（按业务领域分 mixin）：
- _account.py    —— _AccountMixin: 扫码绑定 / cookie / device 注册 / _is_os / _mid_from_cookie
- _note.py       —— _NoteMixin: 便笺采集 / 树脂提醒 / 签到（_in/_all）
- _battle.py     —— _BattleMixin: 深渊 / 朔行连星 / 困难挑战 / 剧诗
- _character.py  —— _CharacterMixin: 角色仓库（gs/sr/zzz）
- _gacha.py      —— _GachaMixin: 抽卡同步（authkey 自动 / URL 手动 / worker / stats）
- _overview.py   —— _OverviewMixin: 总览 + 全量采集编排
- service.py     —— FurinaGameService 主类（6 mixin 组合 + __init__ + _run_skill）
- _register.py   —— task_types / subscription_types 注册 + 米哈游账号订阅 ensure/clear
"""
from __future__ import annotations

from ._register import (
    clear_mihoyo_subscriptions,
    ensure_mihoyo_subscriptions,
    register_subscription_types,
    register_task_types,
)
from .service import FurinaGameService

__all__ = [
    "FurinaGameService",
    "clear_mihoyo_subscriptions",
    "ensure_mihoyo_subscriptions",
    "register_subscription_types",
    "register_task_types",
]
