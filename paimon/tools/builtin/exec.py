"""exec — 轻量 shell 执行工具

SEC-002 命令注入防护：
- 危险命令模式拦截（rm -rf 顶层路径、del /q C:\\、format/dd/mkfs/shutdown 等不可逆破坏）
- cwd 强制项目根（避免 LLM 通过 cd 跳出工作区后再操作）
- 命令落 audit log（事后可追溯）

未做白名单：保留 LLM 调常用工具（yt-dlp/curl/ffmpeg/git/python）的能力；
依赖危险模式黑名单 + 文件层 file_ops 路径白名单 (SEC-003) 双重保险。
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from loguru import logger

from paimon.tools.base import BaseTool, ToolContext

MAX_OUTPUT = 8000
TIMEOUT = 60

# 不可逆破坏命令模式 — 命中即拒绝
# 设计：宁少勿多，覆盖最常见的"清盘/格盘/递归删根/强制关机"
# 不写白名单是因为 LLM 调用 yt-dlp/curl/ffmpeg/git 等是合法用法；这里只挡明显破坏
_DANGEROUS_PATTERNS = [
    # rm -rf / 类（包括 rm -rf / rm -rf /* rm -rf ~ rm -rf $HOME）
    re.compile(r"\brm\s+(-[rRfFv]+\s+)?(/\s*$|/\s+|/\*|~|\$HOME|\$\{HOME\})"),
    # del /q /s 顶层 / format / mkfs
    re.compile(r"\bdel\s+(/[a-zA-Z]\s+)*[A-Z]:\\\s*\*?", re.IGNORECASE),
    re.compile(r"\bformat\s+[A-Z]:", re.IGNORECASE),
    re.compile(r"\bmkfs(\.|\b)"),
    re.compile(r"\bdd\s+if=.*\bof=/dev/(sd|hd|nvme)"),
    # 关机/重启
    re.compile(r"\bshutdown\b\s+(-[a-z]\s+)*(now|/s|/r)", re.IGNORECASE),
    re.compile(r"\breboot\b"),
    re.compile(r"\bpoweroff\b"),
    re.compile(r"\bhalt\b\s*$"),
    # rm -rf 项目根 / paimon 包（防 LLM 误操作清自己）
    re.compile(r"\brm\s+-[rRfFv]+\s+(\./|/)?paimon(/|\s|$)"),
    re.compile(r"\brm\s+-[rRfFv]+\s+(\./|/)?\.git(/|\s|$)"),
    # curl|sh / wget|sh 远程脚本直跑
    re.compile(r"\bcurl\s+[^|]+\|\s*(sh|bash|zsh|ash)\b"),
    re.compile(r"\bwget\s+(-[a-zA-Z]+\s+)*[^|]+\|\s*(sh|bash)\b"),
    # chmod 777 顶层 / chown 顶层
    re.compile(r"\bchmod\s+777\s+/(\s|$)"),
    re.compile(r"\bchown\s+\S+\s+/(\s|$)"),
]


def _check_dangerous(command: str) -> str | None:
    """命中危险模式返回拒绝原因，None 表示通过。"""
    if not command or not command.strip():
        return None
    for pat in _DANGEROUS_PATTERNS:
        m = pat.search(command)
        if m:
            return f"命中危险命令模式: {m.group(0)!r}"
    return None


class ExecTool(BaseTool):
    name = "exec"
    description = (
        "执行 Shell 命令并返回输出。"
        "适用于运行 yt-dlp、curl、ffmpeg 等命令行工具。"
        "超时 60 秒，输出截断到 8000 字符。"
        "出于安全考虑：危险命令（rm -rf /、format、mkfs、shutdown、curl|sh 等）会被拦截。"
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

        # SEC-002 危险命令拦截
        reason = _check_dangerous(command)
        if reason:
            logger.warning("[天使·exec] 拒绝危险命令: {} — {}", command[:200], reason)
            # audit 落库（best-effort，state 未 ready 时 silent skip）
            try:
                from paimon.state import state
                if state.irminsul:
                    await state.irminsul.audit_append(
                        event_type="exec_blocked",
                        payload={
                            "command": command[:500],
                            "reason": reason,
                            "session_id": getattr(ctx.session, "id", "") if ctx.session else "",
                        },
                        actor="天使·exec",
                    )
            except Exception:
                pass
            return f"拒绝执行: {reason}\n命令: {command[:200]}"

        # 正常执行：cwd 强制项目根
        cwd = Path.cwd()
        logger.info("[天使·exec] cmd=({}) cwd={}", command[:200], cwd)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=TIMEOUT,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
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
