"""glob — 跨平台文件模式匹配工具

Claude Code 原生 `Glob` 的 paimon 对等工具。让 LLM 按通配符一次性
拿到匹配文件列表，避免在 Windows 下绕 find/ls 失败、在任何平台下
手动递归 file_ops(list)。

核心用途：check skill 分组扫描需要全项目文件列表；水神评审、未来其他
skill（fix / refactor 等）只要涉及"按模式找文件"都会用。

设计：
- pattern 支持 pathlib glob 语法：`**` 递归、`*`、`?`、`[...]`
- 跨平台：用 Python `pathlib.Path.glob` —— Windows/Linux/macOS 一致
- 返回相对 base 的 POSIX 风格路径（`/` 分隔），LLM 解析稳定
- 结果上限 500 + 遍历上限防爆炸（大仓库的 node_modules 等）
- 只返文件不返目录（列目录用 file_ops(list)）
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from paimon.tools.base import BaseTool, ToolContext

# 单次调用返回的匹配数上限（防止几千条塞爆 LLM context）
MAX_MATCHES = 500
# 遍历上限（防止误对巨量目录例如 node_modules 扫扫就卡）
MAX_TRAVERSED = 100_000


class GlobTool(BaseTool):
    name = "glob"
    description = (
        "按通配符模式快速查找文件（跨平台）。"
        "pattern 支持 `**`（递归任意目录层级）、`*`（同层通配）、`?`、`[...]`。"
        "常用示例: `**/*.py` 全项目 py 文件；`paimon/core/*.py` 限 core 单层；"
        "`docs/**/*.md` docs 下递归所有 md。"
        "返回相对 path（未指定则相对 cwd）的 POSIX 风格路径列表，每行一个。"
        "只返文件不返目录；上限 500 条。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "glob 模式，如 '**/*.py'",
            },
            "path": {
                "type": "string",
                "description": "起始目录绝对路径；省略时用当前工作目录",
            },
            "limit": {
                "type": "integer",
                "description": f"返回上限（默认 {MAX_MATCHES}，上限 {MAX_MATCHES}）",
            },
        },
        "required": ["pattern"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        pattern = (kwargs.get("pattern") or "").strip()
        path_str = (kwargs.get("path") or "").strip()
        try:
            limit = max(1, min(int(kwargs.get("limit", MAX_MATCHES)), MAX_MATCHES))
        except (TypeError, ValueError):
            limit = MAX_MATCHES

        if not pattern:
            return "缺少 pattern 参数"

        # 起始目录
        if path_str:
            base = Path(path_str).expanduser().resolve()
            if ".." in base.parts:
                return "path 不允许包含 .."
            if not base.is_dir():
                return f"起始目录不存在或非目录: {base}"
        else:
            base = Path.cwd()

        # Windows LLM 可能传反斜杠 pattern；规范化成正斜杠（pathlib glob 要求）
        norm_pattern = pattern.replace("\\", "/")

        # 绝对路径 pattern 不支持（base.glob 行为 platform-dependent）
        # LLM 应传 path 参数 + 相对 pattern
        if Path(norm_pattern).is_absolute() or norm_pattern.startswith("/"):
            return (
                "pattern 必须是相对路径模式。"
                "如需限定起始目录，请传 `path` 参数 + 相对 `pattern`。"
            )

        matches: list[Path] = []
        try:
            traversed = 0
            for m in base.glob(norm_pattern):
                traversed += 1
                if traversed > MAX_TRAVERSED:
                    return (
                        f"遍历超过 {MAX_TRAVERSED} 条，pattern={pattern!r} 范围太大。"
                        f"请用更具体的 pattern（如 `paimon/**/*.py` 而非 `**/*`）"
                        f"或用 path 参数限定起始目录。"
                    )
                if m.is_file():
                    matches.append(m)
                    if len(matches) >= limit:
                        break
        except OSError as e:
            return f"glob IO 失败: {e}"
        except Exception as e:
            return f"glob 异常: {e}"

        if not matches:
            return f"(0 个匹配 pattern={pattern!r} base={base})"

        # 输出：相对 base 的 POSIX 路径（`/` 分隔），LLM 跨平台解析稳定
        lines: list[str] = []
        for m in matches:
            try:
                rel = m.relative_to(base).as_posix()
            except ValueError:
                rel = str(m).replace("\\", "/")
            lines.append(rel)

        truncated = (
            f" (达上限 {limit}，可能还有更多)" if len(matches) >= limit else ""
        )
        header = f"# {len(lines)} 个匹配 pattern={pattern} base={base}{truncated}"
        return header + "\n" + "\n".join(lines)
