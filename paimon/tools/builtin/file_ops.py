"""file_ops — 文件操作工具（雷神/水神用）

结构化的文件读写，比 exec cat/echo 更安全。

SEC-003 路径穿越防护：
所有路径 expanduser().resolve() 后必须落在 _ALLOWED_ROOTS 内（项目根 + paimon_home）。
旧实现用 `".." in path.parts` 字符串检查，resolve() 已展开 .. 后此检查永为 False，
形同虚设；改用 pathlib.Path.is_relative_to(allowed_root) 真正限制访问范围。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from paimon.tools.base import BaseTool, ToolContext

MAX_READ = 50000


def _allowed_roots() -> list[Path]:
    """返回允许访问的根目录白名单。

    懒加载 config（避免 import 时副作用）；resolve 一次缓存到 list 里。
    cwd 通常 = 项目根；paimon_home 通常 = .paimon/（任务工作区）。
    两者可能重叠（默认 paimon_home 在仓库根下），但 is_relative_to 检查不受影响。
    """
    from paimon.config import config
    roots: list[Path] = []
    try:
        roots.append(Path.cwd().resolve())
    except (OSError, RuntimeError):
        pass
    try:
        roots.append(Path(config.paimon_home).expanduser().resolve())
    except (OSError, RuntimeError):
        pass
    return roots


def _is_allowed(path: Path) -> bool:
    """检查 path 是否在允许 root 内（已 resolve 过的绝对路径）。"""
    for root in _allowed_roots():
        try:
            if path.is_relative_to(root):
                return True
        except (ValueError, OSError):
            continue
    return False


def _is_task_workspace(path: Path) -> bool:
    """是否在四影任务工作区 paimon_home/tasks/{task_id}/ 内。

    任务工作区是 LLM 自产数据（spec/design/code），多轮迭代必然覆盖；
    USB-007 强制 overwrite 拦截只对宿主项目源码 / paimon_home 其他子目录生效，
    避免错杀正常的 round 2 修订流程。
    """
    from paimon.config import config
    try:
        tasks_root = (Path(config.paimon_home).expanduser().resolve() / "tasks")
        return path.is_relative_to(tasks_root)
    except (ValueError, OSError, RuntimeError):
        return False


class FileOpsTool(BaseTool):
    name = "file_ops"
    description = (
        "文件操作工具。支持读取、写入、列出文件。"
        "比 exec cat/echo 更安全，有路径检查和输出限制。"
        "路径必须落在项目根或 paimon_home 内。"
        "write 默认拒绝覆盖已存在文件，需显式传 overwrite=true。"
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
                "description": "文件或目录路径（绝对或相对 cwd 均可；必须在项目根或 paimon_home 内）",
            },
            "content": {
                "type": "string",
                "description": "写入内容（write 时必填）",
            },
            "overwrite": {
                "type": "boolean",
                "description": "write 时是否允许覆盖已存在文件，默认 false。覆盖前会拒绝；显式传 true 才允许。",
                "default": False,
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

        # SEC-003 路径穿越防护：必须落在白名单 root 内
        if not _is_allowed(path):
            roots_str = " / ".join(str(r) for r in _allowed_roots())
            return f"路径不允许（必须在项目根或 paimon_home 内）: {path}（允许 root: {roots_str}）"

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
            overwrite = bool(kwargs.get("overwrite", False))
            # USB-007 破坏性操作确认：默认拒绝覆盖宿主项目源码 / 重要 user 数据
            # 但任务工作区 .paimon/tasks/{tid}/ 是 LLM 自产，多轮迭代必然覆盖 → 自动放行
            if path.exists() and not overwrite and not _is_task_workspace(path):
                return (
                    f"目标已存在: {path}（如需覆盖请加 overwrite=true；"
                    f"任务工作区 .paimon/tasks/* 默认允许覆盖，无需此参数）"
                )
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
            # list 的 target 也必须在白名单内（path.parent 可能跑出 root）
            if not _is_allowed(target):
                return f"路径不允许: {target}"
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
