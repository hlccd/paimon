"""冰神 · Tsaritsa — 反抗·联合

archon 本体保留 namespace 壳（七神不删铁律），当前**无具体职能**。

历史遗留：原本由冰神负责的 skill 域写入 / `/plugins` 面板代理 / 提案落盘
（apply_proposal）已全部移交给空执（paimon/shades/asmoday/）。
"""
from __future__ import annotations

from paimon.archons.base import Archon


class TsaritsaArchon(Archon):
    name = "冰神"
    description = "namespace 壳；skill 生态职能已移交给空执"
    allowed_tools: set[str] = set()

    async def execute(self) -> str:
        return f"[{self.name}] namespace 壳，无具体职能"
