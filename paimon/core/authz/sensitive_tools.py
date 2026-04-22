"""工具敏感清单与派生逻辑

按 docs/permissions.md §敏感度分级：
- 普通：纯读 / 本地无副作用 / 低风险
- 敏感：系统 / 外部 / 凭据 / 可导致副作用的写

冰神装载 skill 时调用 derive_sensitivity，基于 skill 声明的 allowed_tools
自动派生其敏感度，无需手动 manifest 标记。
"""
from __future__ import annotations


# 敏感工具清单 —— 任一命中即视 skill 为敏感
# 命名兼容两套：Claude Code 风格（Bash/Write/Edit）+ 内置工具名（exec/schedule）
SENSITIVE_TOOLS: set[str] = {
    "Bash", "bash", "exec", "exec_shell", "shell",
    "Write", "write", "Edit", "edit", "NotebookEdit",
    "WebFetch", "web_fetch",
    "schedule",
    "send_file",
    "skill_manage",
    "dispatch",
    "knowledge_manage",
    "audio_process", "video_process",
}


TOOL_RISK_DESC: dict[str, str] = {
    "Bash": "执行 shell 命令",
    "bash": "执行 shell 命令",
    "exec": "执行 shell 命令",
    "exec_shell": "执行 shell 命令",
    "shell": "执行 shell 命令",
    "Write": "写入文件",
    "write": "写入文件",
    "Edit": "修改文件",
    "edit": "修改文件",
    "NotebookEdit": "修改 Notebook",
    "WebFetch": "访问外部网络",
    "web_fetch": "访问外部网络",
    "schedule": "注册定时任务",
    "send_file": "向用户推送文件",
    "skill_manage": "管理 skill 生态",
    "dispatch": "调度四影子任务",
    "knowledge_manage": "读写知识库",
    "audio_process": "处理音频（写中间文件）",
    "video_process": "处理视频（写中间文件）",
}


def _normalize(tool: str) -> str:
    """把 Claude Code 风格的受限声明归一化到基础工具名。

    `Bash(git:*)` / `Bash(python3:*)` → `Bash`
    `Read` → `Read`
    """
    if not tool:
        return tool
    lparen = tool.find("(")
    return tool[:lparen].strip() if lparen > 0 else tool.strip()


def derive_sensitivity(allowed_tools: list[str] | None) -> tuple[str, list[str]]:
    """根据 allowed_tools 派生 sensitivity。

    返回 (sensitivity, hits)：
      - sensitivity ∈ {"normal", "sensitive"}
      - hits: 命中的敏感工具原文（去重保序，保留 `Bash(git:*)` 这类细节以便展示）
    """
    if not allowed_tools:
        return "normal", []

    hits: list[str] = []
    seen: set[str] = set()
    for t in allowed_tools:
        base = _normalize(t)
        if base in SENSITIVE_TOOLS and t not in seen:
            hits.append(t)
            seen.add(t)

    return ("sensitive" if hits else "normal"), hits


def describe_tool_risk(tool: str) -> str:
    """按归一化后的工具名查风险描述；未知工具返回空串。"""
    return TOOL_RISK_DESC.get(_normalize(tool), "")


def describe_tools(tools: list[str]) -> str:
    """把命中的敏感工具清单转成给用户看的友好描述。

    多个同名变体（如 Bash(git:*)、Bash(python3:*)）按归一化名合并，
    只列一条；若有变体细节则附在括号里。
    """
    if not tools:
        return ""
    grouped: dict[str, list[str]] = {}
    for t in tools:
        base = _normalize(t)
        grouped.setdefault(base, []).append(t)

    lines = []
    for base, variants in grouped.items():
        desc = TOOL_RISK_DESC.get(base, "")
        detail = ""
        subs = [v for v in variants if v != base]
        if subs:
            detail = f"（{', '.join(subs)}）"
        if desc:
            lines.append(f"• {base} — {desc}{detail}")
        else:
            lines.append(f"• {base}{detail}")
    return "\n".join(lines)
