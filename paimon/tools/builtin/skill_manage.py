"""skill_manage — Skill 生态管理工具（冰神用）

扫描 skills 目录、查看和注册 skill 声明到世界树。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from paimon.tools.base import BaseTool, ToolContext


class SkillManageTool(BaseTool):
    name = "skill_manage"
    description = (
        "Skill 生态管理工具。扫描 skills 目录发现 skill，查看 skill 详情，"
        "注册 skill 声明到世界树。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["scan", "list", "get"],
                "description": "操作类型: scan=扫描目录, list=列出已注册, get=查看详情",
            },
            "skill_name": {
                "type": "string",
                "description": "skill 名称（get 时必填）",
            },
        },
        "required": ["action"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        from paimon.state import state

        action = kwargs.get("action", "")

        if action == "scan":
            return await self._scan(state)
        elif action == "list":
            return await self._list(state)
        elif action == "get":
            return await self._get(state, kwargs.get("skill_name", ""))
        return f"未知操作: {action}"

    async def _scan(self, state) -> str:
        skill_registry = state.skill_registry
        if not skill_registry:
            return "Skill 注册表未初始化"

        project_root = Path(__file__).resolve().parent.parent.parent
        skills_dir = project_root / "skills"
        if not skills_dir.exists():
            return f"skills 目录不存在: {skills_dir}"

        found = []
        for d in sorted(skills_dir.iterdir()):
            if not d.is_dir() or d.name.startswith((".", "__")):
                continue
            skill_md = d / "SKILL.md"
            registered = skill_registry.exists(d.name)
            status = "已注册" if registered else "未注册"
            has_md = "有 SKILL.md" if skill_md.exists() else "缺 SKILL.md"
            found.append(f"  {d.name}: {status} | {has_md}")

        if not found:
            return "未发现任何 skill 目录"

        return f"扫描 {skills_dir}:\n" + "\n".join(found)

    async def _list(self, state) -> str:
        skill_registry = state.skill_registry
        if not skill_registry:
            return "Skill 注册表未初始化"

        skills = skill_registry.list_all()
        if not skills:
            return "暂无已注册 skill"

        lines = []
        for s in skills:
            triggers = f" (触发: {s.triggers})" if s.triggers else ""
            lines.append(f"  {s.name}: {s.description[:60]}{triggers}")
        return "已注册 Skills:\n" + "\n".join(lines)

    async def _get(self, state, name: str) -> str:
        if not name:
            return "get 需要 skill_name"

        skill_registry = state.skill_registry
        if not skill_registry:
            return "Skill 注册表未初始化"

        skill = skill_registry.get(name)
        if not skill:
            return f"未找到 skill: {name}"

        return (
            f"Skill: {skill.name}\n"
            f"描述: {skill.description}\n"
            f"触发: {skill.triggers or '无'}\n"
            f"允许工具: {skill.allowed_tools or '无'}\n"
            f"\n--- SKILL.md 内容 ---\n{skill.body[:3000]}"
        )
