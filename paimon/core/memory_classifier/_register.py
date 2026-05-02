"""bootstrap 启动期注册 memory_hygiene + kb_hygiene 两个 task_type。

放独立模块避免 task_types registry 跟业务模块循环依赖。
"""
from __future__ import annotations

from loguru import logger

from .kb_hygiene import run_kb_hygiene
from .memory_hygiene import run_hygiene


def register_task_types() -> None:
    """由 bootstrap 启动时调一次：memory_hygiene + kb_hygiene。"""
    from paimon.foundation import task_types

    async def _desc_mem(_sid, _irm) -> str:
        return "记忆整理（批量合并/去重）"

    async def _dispatch_mem(task, state) -> None:
        if not state.irminsul or not state.model:
            logger.error("[草神·记忆整理] irminsul / model 未就绪，跳过")
            return
        await run_hygiene(state.irminsul, state.model, trigger="cron")

    task_types.register(task_types.TaskTypeMeta(
        task_type="memory_hygiene",
        display_label="草神·记忆整理",
        manager_panel="/knowledge",
        archon="nahida",
        icon="broom",
        description_builder=_desc_mem,
        anchor_builder=None,
        dispatcher=_dispatch_mem,
    ))

    async def _desc_kb(_sid, _irm) -> str:
        return "知识库整理（按分类合并/去重）"

    async def _dispatch_kb(task, state) -> None:
        if not state.irminsul or not state.model:
            logger.error("[草神·知识整理] irminsul / model 未就绪，跳过")
            return
        await run_kb_hygiene(state.irminsul, state.model, trigger="cron")

    task_types.register(task_types.TaskTypeMeta(
        task_type="kb_hygiene",
        display_label="草神·知识整理",
        manager_panel="/knowledge",
        archon="nahida",
        icon="broom",
        description_builder=_desc_kb,
        anchor_builder=None,
        dispatcher=_dispatch_kb,
    ))
