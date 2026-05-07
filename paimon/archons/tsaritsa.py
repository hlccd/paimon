"""冰神 · Tsaritsa — 反抗·联合

⚠️ 当前状态（2026-05 解耦后）：

本节点 archon 本体跟四影解耦后**execute 内部业务已移除**，但保留概念归属：

- 移除：execute() 内部 skill_manage tool-loop / 通用 exec 推理
- 已搬到：`paimon/shades/worker/`（stage=exec / chat）
- **保留概念归属**：冰神语义负责 `/plugins` 面板（skill 生态管理）
  - 代码层 webui/api/plugins.py 直读 skill_loader，不经过本实例
  - 但语义上"skill 生态 / AI 自举"归冰神

待用户后续安排：是否给冰神实例挂新职能（如 webui 改成走冰神实例做面板代理）。
"""
from __future__ import annotations

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model


class TsaritsaArchon(Archon):
    name = "冰神"
    description = "Skill 生态管理（概念归属：/plugins 面板，代码层 webui 直读 skill_loader）"
    allowed_tools: set[str] = set()

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        return f"[{self.name}] execute 路径已解耦（v6），请参考 docs/archons/tsaritsa.md"
