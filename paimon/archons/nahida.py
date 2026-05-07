"""草神 · Nahida — 智慧·文书

⚠️ 当前状态（2026-05 解耦后）：

本节点 archon 本体跟四影解耦后**execute 内部业务已移除**，但保留概念归属：

- 移除：execute() 内部 spec 路由 + write_spec + 通用 tool-loop + _extract_issues_* helpers
- 已搬到：`paimon/shades/worker/`（stage=spec / chat）和 `_revise_helpers.py`
- **保留概念归属**：草神语义负责 `/knowledge` 面板（草神·智识，3 tab：记忆 / 知识库 / 文书归档）
  - 代码层 webui/api/{knowledge_kb,knowledge_archives,authz}.py 直读 irminsul
  - 不经过本实例，但语义上"知识 / 偏好 / 文书归档"归草神

待用户后续安排：是否给草神实例挂新职能（如 webui 改成走草神实例做面板代理）。
"""
from __future__ import annotations

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model


class NahidaArchon(Archon):
    name = "草神"
    description = "智慧·文书（概念归属：知识 / 偏好 / 文书归档面板，代码层 webui 直读 irminsul）"
    allowed_tools: set[str] = set()

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        return f"[{self.name}] execute 路径已解耦（v6），请参考 docs/archons/nahida.md"
