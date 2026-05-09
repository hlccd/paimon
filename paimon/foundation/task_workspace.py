"""任务工作区（复杂任务的隔离目录）

每个 `/task` 任务分配独立目录用于落产物：

  .paimon/tasks/{task_id_prefix}/
  ├── proposal.md        生执 propose_skill 草案（可选）
  ├── review.json        死执 review_proposal 评审结果（可选）
  └── summary.md         时执归档总结（派蒙呈现用）

设计约束：
- 工作区路径由 task_id 计算，无需世界树存储（纯 fs 约定）
- 各 stage 通过 `get_workspace_path(task_id)` 定位
- 时执生命周期 sweep 清 archived 任务时一并清工作区（见 _lifecycle.py）
"""
from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from paimon.config import config


def _workspace_root() -> Path:
    return config.paimon_home / "tasks"


def _task_dirname(task_id: str) -> str:
    """task_id 全长 32 hex；目录用前 12 位让人能粘贴定位。"""
    return task_id[:12] if len(task_id) >= 12 else task_id


def get_workspace_path(task_id: str) -> Path:
    """计算任务工作区路径（不判断是否存在）。"""
    return _workspace_root() / _task_dirname(task_id)


def create_workspace(task_id: str) -> Path:
    """创建工作区目录；幂等。"""
    d = get_workspace_path(task_id)
    d.mkdir(parents=True, exist_ok=True)
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


# ---------- 草神·文书归档面板用 ----------

# 归档面板感兴趣的顶层产物
_ARCHIVE_ARTIFACTS = ["proposal.md", "review.json", "summary.md"]


def list_workspaces() -> list[dict]:
    """扫 workspace 根下所有 task_id 目录，列出每个的 task_id + 产物清单 + 创建时间。

    返回 [{task_id, created_at, artifacts: [{name, size, mtime}]}]。
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
        if not artifacts:
            continue  # 空目录跳过
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

    artifact 是相对 workspace 的路径，如 "proposal.md" / "summary.md"。

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
    try:
        if not path.is_relative_to(workspace):
            return None
    except AttributeError:
        try:
            path.relative_to(workspace)
        except ValueError:
            return None
    if not path.exists() or not path.is_file():
        return None
    if path.stat().st_size > 2 * 1024 * 1024:
        return f"(文件过大 > 2MB，不支持在面板内预览；路径: {path})"
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "(二进制文件，不支持预览)"
    except Exception as e:
        return f"(读取失败: {e})"
