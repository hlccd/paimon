"""水神·芙宁娜 — archon 子包（namespace 壳）。

archon 本体只是 namespace 壳；游戏功能在姊妹子包 `furina_game/`（FurinaGameService），
保留 `/game` 面板 + mihoyo cron + 米哈游账号订阅类型。
"""
from __future__ import annotations

from .service import FurinaArchon

__all__ = ["FurinaArchon"]
