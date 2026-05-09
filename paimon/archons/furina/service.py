"""水神·芙宁娜 — archon 本体（namespace 壳）

archon 本体（FurinaArchon）只是 namespace 壳，本身不承载业务。
游戏功能（签到 / 便笺 / 深渊 / 抽卡）在姊妹子包 `archons/furina_game/`（FurinaGameService）。
"""
from __future__ import annotations

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.llm.model import Model


class FurinaArchon(Archon):
    name = "水神"
    description = "archon 本体 namespace 壳；游戏服务在 furina_game/ 子包"
    allowed_tools: set[str] = set()

    async def execute(self) -> str:
        return f"[{self.name}] archon 本体不参与执行；游戏功能在 furina_game/"
