"""memory — 记忆工具（草神专属）

包装世界树 memory_* API，支持跨会话记忆的读写和搜索。
"""
from __future__ import annotations

from typing import Any

from paimon.tools.base import BaseTool, ToolContext


class MemoryTool(BaseTool):
    name = "memory"
    description = (
        "记忆管理工具。读写存储在世界树中的跨会话记忆。"
        "记忆分四类：user(用户画像)、feedback(行为反馈)、project(项目事实)、reference(外部引用)。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["write", "get", "list", "search", "delete"],
                "description": "操作类型",
            },
            "mem_type": {
                "type": "string",
                "enum": ["user", "feedback", "project", "reference"],
                "description": "记忆类型",
            },
            "subject": {
                "type": "string",
                "description": "记忆主题（如用户名、项目名）",
            },
            "title": {
                "type": "string",
                "description": "记忆标题",
            },
            "body": {
                "type": "string",
                "description": "记忆内容",
            },
            "tags": {
                "type": "string",
                "description": "标签，逗号分隔（如 'python,架构,偏好'）",
            },
            "mem_id": {
                "type": "string",
                "description": "记忆ID（get/delete 时必填）",
            },
        },
        "required": ["action"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        from paimon.state import state
        if not state.irminsul:
            return "世界树未初始化"

        action = kwargs.get("action", "")

        if action == "write":
            mem_type = kwargs.get("mem_type", "")
            subject = kwargs.get("subject", "")
            title = kwargs.get("title", "")
            body = kwargs.get("body", "")
            if not mem_type or not subject or not title or not body:
                return "write 需要 mem_type, subject, title, body"
            tags_str = kwargs.get("tags", "")
            tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else None
            mem_id = await state.irminsul.memory_write(
                mem_type=mem_type, subject=subject, title=title, body=body,
                tags=tags, actor="草神",
            )
            return f"记忆已写入: {mem_id}"

        elif action == "get":
            mem_id = kwargs.get("mem_id", "")
            if not mem_id:
                return "get 需要 mem_id"
            mem = await state.irminsul.memory_get(mem_id)
            if not mem:
                return f"未找到记忆: {mem_id}"
            return f"[{mem.mem_type}] {mem.title}\n主题: {mem.subject}\n标签: {mem.tags}\n\n{mem.body}"

        elif action == "list":
            mem_type = kwargs.get("mem_type") or None
            subject = kwargs.get("subject") or None
            items = await state.irminsul.memory_list(mem_type=mem_type, subject=subject)
            if not items:
                return "无记忆记录"
            lines = []
            for m in items:
                lines.append(f"  [{m.mem_type}] {m.id} | {m.title} | 主题={m.subject} | 标签={m.tags}")
            return "\n".join(lines)

        elif action == "search":
            tags_str = kwargs.get("tags", "")
            tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else None
            if not tags:
                return "search 需要 tags"
            items = await state.irminsul.memory_list(tags_any=tags)
            if not items:
                return f"未找到匹配标签 {tags} 的记忆"
            lines = []
            for m in items:
                lines.append(f"  [{m.mem_type}] {m.id} | {m.title} | 标签={m.tags}")
            return "\n".join(lines)

        elif action == "delete":
            mem_id = kwargs.get("mem_id", "")
            if not mem_id:
                return "delete 需要 mem_id"
            ok = await state.irminsul.memory_delete(mem_id, actor="草神")
            return f"已删除: {mem_id}" if ok else f"未找到: {mem_id}"

        return f"未知操作: {action}"
