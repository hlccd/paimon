"""雷神 · Raiden — 永恒·造物

⚠️ 当前状态：archon 本体**暂无具体职能**——按七神保留铁律留 namespace 壳。
- 保留：class + name + description
- 待用户后续安排：删除 / 重写新职能 / 保留等待（详见 docs/todo.md）。
"""
from __future__ import annotations

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model


class RaidenArchon(Archon):
    name = "雷神"
    description = "（namespace 保留 / 待新职能挂载）"
    allowed_tools: set[str] = set()

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        return f"[{self.name}] 暂无具体职能（namespace 壳）"
