"""草神 · Nahida — 智慧·文书

archon 本体本身只是 namespace 壳，**保留概念归属**：草神语义负责 `/knowledge` 面板
（3 tab：记忆 / 知识库 / 文书归档），代码层 `webui/api/{knowledge_kb,knowledge_archives,authz}.py`
直读 irminsul，不经过本实例。memory 域的唯一写入者也是草神（业务接口层面）。
"""
from __future__ import annotations

from paimon.archons.base import Archon


class NahidaArchon(Archon):
    name = "草神"
    description = "智慧·文书（概念归属：知识 / 偏好 / 文书归档面板，代码层 webui 直读 irminsul）"
    allowed_tools: set[str] = set()

    async def execute(self) -> str:
        return f"[{self.name}] 业务接口走 webui /knowledge 面板，archon 本体不参与执行"
