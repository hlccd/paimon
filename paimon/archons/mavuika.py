"""火神 · Mavuika — 战争·冲锋

⚠️ 当前状态：archon 本体**暂无具体职能**——按七神保留铁律留 namespace 壳。
- 保留：class + name + description
- 待用户后续安排：删除 / 重写新职能 / 保留等待（详见 docs/todo.md）。
"""
from __future__ import annotations

from paimon.archons.base import Archon


class MavuikaArchon(Archon):
    name = "火神"
    description = "（namespace 保留 / 待新职能挂载）"
    allowed_tools: set[str] = set()

    async def execute(self) -> str:
        return f"[{self.name}] execute 路径已解耦，请参考 docs/archons/mavuika.md"
