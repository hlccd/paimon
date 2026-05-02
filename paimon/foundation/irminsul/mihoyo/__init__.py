"""米哈游账号数据域 —— 世界树域 8.7

唯一写入者：水神
读取者：水神（业务流程）、WebUI /game 面板

子模块：
- _models.py  —— 5 个 dataclass + UP/常驻/硬保底常量
- _repo.py    —— MihoyoRepo（仓储类）
"""
from __future__ import annotations

from ._models import (
    HARD_PITY,
    PERMANENT_TOP_TIER,
    UP_POOLS,
    MihoyoAbyss,
    MihoyoAccount,
    MihoyoCharacter,
    MihoyoGacha,
    MihoyoNote,
)
from ._repo import MihoyoRepo

__all__ = [
    "HARD_PITY",
    "MihoyoAbyss",
    "MihoyoAccount",
    "MihoyoCharacter",
    "MihoyoGacha",
    "MihoyoNote",
    "MihoyoRepo",
    "PERMANENT_TOP_TIER",
    "UP_POOLS",
]
