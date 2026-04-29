"""任务工作区（复杂任务写代码的隔离目录）

每个走"草神 spec → 雷神 design+code → 水神 review" 三阶段的任务分配独立目录：

  .paimon/tasks/{task_id_prefix}/
  ├── spec.md            草神产物
  ├── design.md          雷神技术方案
  ├── code/              雷神代码（保持同宿主项目的相对路径结构）
  ├── self-check.log     雷神自检输出
  ├── spec.check.json    水神 review_spec 结果
  ├── design.check.json  水神 review_design 结果
  ├── code.check.json    水神 review_code 结果
  └── summary.md         时执归档总结（派蒙呈现用）

设计约束：
- 工作区路径由 task_id 计算，无需世界树存储（纯 fs 约定）
- archon 内部都通过 `get_workspace(task_id)` 定位
- 时执生命周期 sweep 清 archived 任务时一并清工作区（见 _lifecycle.py）
- merge 时由派蒙把 code/ 下的内容 rsync/git apply 到用户 cwd
"""
from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from paimon.config import config


_ID_PREFIX_LEN = 12


def _workspace_root() -> Path:
    return config.paimon_home / "tasks"


def _task_dirname(task_id: str) -> str:
    return (task_id or "unknown")[:_ID_PREFIX_LEN] or "unknown"


def get_workspace_path(task_id: str) -> Path:
    """计算任务工作区路径（不判断是否存在）。"""
    return _workspace_root() / _task_dirname(task_id)


def create_workspace(task_id: str) -> Path:
    """创建工作区 + 预置 code/ 子目录；幂等。"""
    d = get_workspace_path(task_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "code").mkdir(exist_ok=True)
    logger.info("[任务工作区] 创建 task={} 路径={}", task_id[:8], d)
    return d


def workspace_exists(task_id: str) -> bool:
    return get_workspace_path(task_id).exists()


def cleanup_workspace(task_id: str) -> bool:
    """删除工作区目录。返回是否有实际删除。"""
    d = get_workspace_path(task_id)
    if not d.exists():
        return False
    shutil.rmtree(d, ignore_errors=True)
    logger.info("[任务工作区] 删除 task={} 路径={}", task_id[:8], d)
    return True


def list_workspace_files(task_id: str) -> list[Path]:
    """列出工作区 code/ 下所有"真产物"文件（过滤 .check/ / __pycache__/ 等噪声）。"""
    d = get_workspace_path(task_id) / "code"
    if not d.exists():
        return []
    return sorted(
        p for p in d.rglob("*")
        if p.is_file() and not _is_noise_path(p.relative_to(d))
    )


# 非产物路径：check skill 临时目录、Python 字节码缓存、其它语言同类产物
_NOISE_DIRS = {".check", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}
_NOISE_SUFFIXES = {".pyc", ".pyo"}


def _is_noise_path(rel: Path) -> bool:
    for part in rel.parts:
        if part in _NOISE_DIRS or part.startswith("."):
            return True
    return rel.suffix in _NOISE_SUFFIXES


def diff_against_cwd(task_id: str, cwd: Path | None = None) -> str:
    """code/ vs 用户 cwd 的简易 diff 摘要（用于 merge 前展示）。

    不走 git，直接按文件对比：新增 / 修改 / 相同。
    """
    code_dir = get_workspace_path(task_id) / "code"
    base = (cwd or Path.cwd()).resolve()
    if not code_dir.exists():
        return "(工作区 code/ 不存在)"

    lines: list[str] = []
    new_count = modified_count = same_count = 0
    for f in sorted(code_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(code_dir)
        if _is_noise_path(rel):
            continue
        target = base / rel
        if not target.exists():
            new_count += 1
            lines.append(f"  +  {rel}")
        else:
            try:
                if f.read_bytes() == target.read_bytes():
                    same_count += 1
                else:
                    modified_count += 1
                    lines.append(f"  M  {rel}")
            except OSError as e:
                lines.append(f"  ?  {rel} (读失败: {e})")

    header = f"新增 {new_count} / 修改 {modified_count} / 未变 {same_count}"
    return header + "\n" + "\n".join(lines) if lines else header


# ---------- 草神·文书归档面板用 ----------

# 归档面板感兴趣的顶层产物（code/ 走 list_workspace_files 单独处理）
_ARCHIVE_ARTIFACTS = [
    "spec.md", "design.md", "summary.md", "self-check.log",
    "spec.check.json", "design.check.json", "code.check.json",
]


def list_workspaces() -> list[dict]:
    """扫 workspace 根下所有 task_id 目录，列出每个的 task_id + 产物清单 + 创建时间。

    返回 [{task_id, created_at, artifacts: [{name, size, mtime}]}]。
    artifacts 包含顶层产物 + code/ 下的文件数汇总。
    """
    root = _workspace_root()
    if not root.exists():
        return []
    results: list[dict] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        task_id = d.name  # 12 字符前缀
        artifacts: list[dict] = []
        for name in _ARCHIVE_ARTIFACTS:
            f = d / name
            if f.exists() and f.is_file():
                stat = f.stat()
                artifacts.append({
                    "name": name,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
        # code/ 汇总成一条
        code_files = list_workspace_files(task_id)
        if code_files:
            artifacts.append({
                "name": "code/",
                "size": sum(p.stat().st_size for p in code_files if p.exists()),
                "mtime": max((p.stat().st_mtime for p in code_files if p.exists()), default=0),
                "file_count": len(code_files),
            })
        if not artifacts:
            continue  # 空目录跳过
        # 创建时间取目录 mtime
        try:
            created_at = d.stat().st_mtime
        except OSError:
            created_at = 0
        results.append({
            "task_id": task_id,
            "created_at": created_at,
            "artifacts": artifacts,
        })
    return results


def read_artifact(task_id: str, artifact: str) -> str | None:
    """读单个产物的文本内容；非文本或不存在返回 None。

    artifact 是相对 workspace 的路径，如 "spec.md" / "code/paimon/foo.py"。

    路径安全：用 resolve() 比较 is_relative_to，防 `..` / 绝对路径 / 符号链接
    越界；null byte 在更早位置拒绝。
    """
    if not artifact or "\x00" in artifact:
        return None
    workspace = get_workspace_path(task_id).resolve()
    try:
        path = (workspace / artifact).resolve()
    except (OSError, ValueError):
        return None
    # is_relative_to 严格判定 path 位于 workspace 目录内；符号链接经 resolve
    # 后的真实路径必须仍在 workspace 里，否则拒绝
    try:
        if not path.is_relative_to(workspace):
            return None
    except AttributeError:
        # 兜底：老 Python < 3.9
        try:
            path.relative_to(workspace)
        except ValueError:
            return None
    if not path.exists() or not path.is_file():
        return None
    # 限 2MB 上限，避免前端卡死
    if path.stat().st_size > 2 * 1024 * 1024:
        return f"(文件过大 > 2MB，不支持在面板内预览；路径: {path})"
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "(二进制文件，不支持预览)"
    except Exception as e:
        return f"(读取失败: {e})"


def merge_to_cwd(
    task_id: str, cwd: Path | None = None, *, overwrite: bool = False,
) -> dict:
    """把工作区 code/ 下内容合并到 cwd。

    不用 git（避免强制要求 git 环境）；直接按文件拷贝。
    - overwrite=False：已存在且内容不同的文件保留原文件，列入 skipped
    - overwrite=True：已存在的直接覆盖

    返回 {copied: [...rel], skipped: [...rel], errors: [...]}
    """
    code_dir = get_workspace_path(task_id) / "code"
    base = (cwd or Path.cwd()).resolve()
    result = {"copied": [], "skipped": [], "errors": []}
    if not code_dir.exists():
        result["errors"].append(f"工作区 code/ 不存在: {code_dir}")
        return result

    for f in sorted(code_dir.rglob("*")):
        if not f.is_file():
            continue
        rel_path = f.relative_to(code_dir)
        if _is_noise_path(rel_path):
            continue
        rel = str(rel_path)
        target = base / rel
        try:
            if target.exists() and not overwrite:
                if f.read_bytes() == target.read_bytes():
                    continue   # 完全一致，跳过
                result["skipped"].append(rel)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            result["copied"].append(rel)
        except Exception as e:
            result["errors"].append(f"{rel}: {e}")

    logger.info(
        "[任务工作区] merge task={} cwd={} copied={} skipped={} errors={}",
        task_id[:8], base, len(result["copied"]), len(result["skipped"]),
        len(result["errors"]),
    )
    return result
