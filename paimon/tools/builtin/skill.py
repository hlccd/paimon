"""use_skill — 让 LLM 按需加载 Skill 的完整指令"""
from __future__ import annotations

from typing import Any

from paimon.tools.base import BaseTool, ToolContext


class UseSkillTool(BaseTool):
    name = "use_skill"
    description = "加载指定 Skill 的完整指令。当判断用户消息匹配某个 Skill 的能力时调用。"
    parameters = {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "要加载的 Skill 名称（从可用 Skills 列表中选择）",
            },
        },
        "required": ["skill_name"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        from paimon.state import state

        skill_name = kwargs.get("skill_name", "")

        if not state.skill_registry:
            return "Skill 系统未初始化"

        skill = state.skill_registry.get(skill_name)
        if not skill:
            available = ", ".join(s.name for s in state.skill_registry.list_all())
            return f"Skill '{skill_name}' 不存在。可用: {available}"

        return (
            f"# Skill: {skill.name}\n\n"
            f"{skill.body}\n\n"
            f"---\n请严格按照以上指令处理用户的请求。"
        )
