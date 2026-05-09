"""任务工作区（自进化触发的内部 task 隔离目录）

每个 task 分配独立目录用于落产物：

  .paimon/tasks/{task_id_prefix}/
  ├── proposal.md        生执 propose_skill 草案（可选）
  ├── review.json        死执 review_proposal 评审结果（可选）
  └── summary.md         时执归档总结

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
