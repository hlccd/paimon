"""file_ops — 文件操作工具（雷神/水神用）

结构化的文件读写，比 exec cat/echo 更安全。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from paimon.tools.base import BaseTool, ToolContext

MAX_READ = 50000


class FileOpsTool(BaseTool):
    name = "file_ops"
    description = (
        "文件操作工具。支持读取、写入、列出文件。"
        "比 exec cat/echo 更安全，有路径检查和输出限制。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "list", "exists"],
                "description": "操作类型",
            },
            "path": {
                "type": "string",
                "description": "文件或目录的绝对路径",
            },
            "content": {
                "type": "string",
                "description": "写入内容（write 时必填）",
            },
        },
        "required": ["action", "path"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        path_str = kwargs.get("path", "")

        if not path_str:
            return "缺少 path 参数"

        path = Path(path_str).expanduser().resolve()

        if ".." in path.parts:
            return "路径不允许包含 .."

        if action == "read":
            if not path.is_file():
                return f"文件不存在: {path}"
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                if len(text) > MAX_READ:
                    return text[:MAX_READ] + f"\n\n... (截断，共 {len(text)} 字符)"
                return text
            except Exception as e:
                return f"读取失败: {e}"

        elif action == "write":
            content = kwargs.get("content", "")
            if not content:
                return "write 需要 content"
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                return f"已写入: {path} ({len(content)} 字符)"
            except Exception as e:
                return f"写入失败: {e}"

        elif action == "list":
            target = path if path.is_dir() else path.parent
            if not target.is_dir():
                return f"目录不存在: {target}"
            try:
                items = sorted(target.iterdir())[:200]
                lines = []
                for item in items:
                    marker = "d" if item.is_dir() else "f"
                    size = item.stat().st_size if item.is_file() else 0
                    lines.append(f"  [{marker}] {item.name}" + (f" ({size}B)" if size else ""))
                return "\n".join(lines) or "(空目录)"
            except Exception as e:
                return f"列出失败: {e}"

        elif action == "exists":
            if path.exists():
                kind = "目录" if path.is_dir() else "文件"
                return f"存在 ({kind}): {path}"
            return f"不存在: {path}"

        return f"未知操作: {action}"
