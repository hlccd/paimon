"""exec — 轻量 shell 执行工具"""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from paimon.tools.base import BaseTool, ToolContext

MAX_OUTPUT = 8000
TIMEOUT = 60


class ExecTool(BaseTool):
    name = "exec"
    description = (
        "执行 Shell 命令并返回输出。"
        "适用于运行 yt-dlp、curl、ffmpeg 等命令行工具。"
        "超时 60 秒，输出截断到 8000 字符。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令",
            },
        },
        "required": ["command"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        if not command:
            return "错误: 缺少 command 参数"

        logger.info("[天使·exec] {}", command[:200])

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=TIMEOUT,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"命令超时 ({TIMEOUT}s): {command[:100]}"
        except Exception as e:
            return f"执行失败: {e}"

        out = stdout.decode(errors="replace") if stdout else ""
        err = stderr.decode(errors="replace") if stderr else ""

        result = ""
        if out:
            result += out
        if err:
            result += f"\n[stderr]\n{err}"
        if proc.returncode and proc.returncode != 0:
            result += f"\n[exit code: {proc.returncode}]"

        if len(result) > MAX_OUTPUT:
            result = result[:MAX_OUTPUT] + f"\n... (截断，共 {len(result)} 字符)"

        return result.strip() or "(无输出)"
