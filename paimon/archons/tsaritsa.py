"""冰神 · Tsaritsa — 反抗·联合

archon 本体本身只是 namespace 壳，**保留概念归属**：冰神语义负责 `/plugins` 面板
（skill 生态管理 + 自进化提案审批 + 授权撤销）。代码层 `webui/api/plugins.py` 直读
skill_loader，不经过本实例。skill 域的唯一写入者也是冰神
（apply_proposal.py 写 SKILL.md + 注册 skill_declarations）。
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
        return f"[{self.name}] 业务接口走 webui /plugins 面板 + apply_proposal.py，archon 本体不参与执行"
