"""雷神 · Raiden — 永恒·造物

⚠️ 当前状态（2026-05 解耦后）：
本节点 archon 本体跟四影解耦后**暂无具体职能**：
- 移除：execute() / write_design / write_code / _write_code_simple / self_check 全部业务
- 已搬到：`paimon/shades/naberius/produce.py + jonova/review.py`
- 保留：class + name + description（namespace 壳）

待用户后续安排：删除整个文件 / 重写新职能 / 保留等待（详见 docs/todo.md）。
"""
from __future__ import annotations

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model


class RaidenArchon(Archon):
    name = "雷神"
    description = "（解耦后暂无具体职能 / namespace 保留）"
    allowed_tools: set[str] = set()

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        # v6 解耦后：本节点跟四影 execute 路径解耦；asmoday 不再 dispatch 到此
        return f"[{self.name}] execute 路径已解耦（v6），请参考 docs/archons/raiden.md"
