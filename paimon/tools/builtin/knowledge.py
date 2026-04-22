"""knowledge — 知识库工具（草神专属）

包装世界树 knowledge_* API，支持知识的读写和管理。
"""
from __future__ import annotations

from typing import Any

from paimon.tools.base import BaseTool, ToolContext


class KnowledgeTool(BaseTool):
    name = "knowledge"
    description = (
        "知识库管理工具。读写存储在世界树中的结构化知识。"
        "知识按 category/topic 组织，如 'architecture/paimon' 或 'tech/python'。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "list", "delete"],
                "description": "操作类型",
            },
            "category": {
                "type": "string",
                "description": "知识分类（如 architecture, tech, project）",
            },
            "topic": {
                "type": "string",
                "description": "具体主题（如 paimon, python, microservice）",
            },
            "body": {
                "type": "string",
                "description": "知识内容（write 时必填，Markdown 格式）",
            },
        },
        "required": ["action"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        from paimon.state import state
        if not state.irminsul:
            return "世界树未初始化"

        action = kwargs.get("action", "")
        category = kwargs.get("category", "")
        topic = kwargs.get("topic", "")

        if action == "read":
            if not category or not topic:
                return "read 需要 category 和 topic"
            content = await state.irminsul.knowledge_read(category, topic)
            return content if content else f"未找到知识: {category}/{topic}"

        elif action == "write":
            if not category or not topic:
                return "write 需要 category 和 topic"
            body = kwargs.get("body", "")
            if not body:
                return "write 需要 body"
            await state.irminsul.knowledge_write(category, topic, body, actor="草神")
            return f"知识已写入: {category}/{topic}"

        elif action == "list":
            items = await state.irminsul.knowledge_list(category)
            if not items:
                return "知识库为空" if not category else f"分类 '{category}' 下无内容"
            return "\n".join(f"  {c}/{t}" for c, t in items)

        elif action == "delete":
            if not category or not topic:
                return "delete 需要 category 和 topic"
            ok = await state.irminsul.knowledge_delete(category, topic, actor="草神")
            return f"已删除: {category}/{topic}" if ok else f"未找到: {category}/{topic}"

        return f"未知操作: {action}"
