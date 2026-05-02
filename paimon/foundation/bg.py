"""后台任务安全包装 — fire-and-forget 模式的统一防 GC 入口。

为什么需要：见 paimon/state.py:65-68 的陷阱说明。`asyncio.create_task()` 直接调
不存引用 → 任务可能被 GC 静默 cancel（Python asyncio 仅对根任务保强引用）。
本模块把 chat.py 早期版本的 _track_bg_task helper 提取为模块级公开 API，
作为全项目唯一的 fire-and-forget 入口。

用法：
    from paimon.foundation.bg import bg
    bg(state.venti.collect_subscription(sub_id, ...), label="venti·订阅采集")

防护机制：
- 防 GC：把任务挂到 state.pending_bg_tasks 集合
- 防异常吞没：done callback 检测异常并 logger.exception；
  CancelledError（正常取消）不报，避免 shutdown 时刷屏
- 自动清理：done 后从 set 移除，防内存泄漏
- Shutdown 协作：__main__.py finally 调 shutdown_pending() 等待未完成任务
  落盘后再关闭 channels/march/irminsul，保证数据不丢。
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from loguru import logger


def bg(
    coro: Coroutine[Any, Any, Any],
    *,
    label: str = "",
    name: str | None = None,
) -> asyncio.Task:
    """启动 fire-and-forget 后台任务，自动防 GC + 异常可见。

    Args:
        coro: 要后台运行的协程对象（已经调用过参数：`some_func(...)`）
        label: 给日志用的人类可读标签（如 "venti·订阅采集"）。也作为 task name 兜底。
        name: 显式 task name（不传则用 label）。

    Returns:
        asyncio.Task 实例。调用方通常不持有，但需要时可以 await/cancel。

    Raises:
        RuntimeError: 当前无 running event loop（asyncio.create_task 的契约）。
                      sync 入口请自行用 try/except 处理。
    """
    # 函数内 import 避免任何潜在的循环依赖（state.py 不 import bg.py，
    # 但函数内 import 让 bg.py 顶层完全无依赖，更稳）
    from paimon.state import state

    task = asyncio.create_task(coro, name=name or label or None)
    state.pending_bg_tasks.add(task)
    task.add_done_callback(_make_done_callback(label))
    return task


def _make_done_callback(label: str):
    """生成 done callback。独立工厂避免闭包持 task 引用形成回收障碍。"""

    def _on_done(t: asyncio.Task) -> None:
        # discard 在 asyncio 单线程模型内串行执行，无需锁
        from paimon.state import state
        state.pending_bg_tasks.discard(t)

        # cancelled 是预期路径（shutdown / 用户取消），不当异常报
        if t.cancelled():
            return

        exc = t.exception()
        if exc is not None:
            logger.opt(exception=exc).error(
                "[bg·{}] 后台任务异常退出: {}",
                label or t.get_name() or "?", exc,
            )

    return _on_done


async def shutdown_pending(timeout: float = 10.0) -> None:
    """进程退出时调用：等所有 bg 任务完成（最多 timeout 秒），剩余 cancel。

    必须在 __main__.py finally 块的 channels/march/irminsul 关闭**之前**调用。
    否则 bg 任务可能正在写世界树却被 irminsul.close 截断，造成数据残缺。

    Args:
        timeout: 最长等待秒数。超时后未完成的任务会被 cancel。
    """
    from paimon.state import state

    if not state.pending_bg_tasks:
        return

    # 复制一份避免 done callback 边迭代边修改 set
    pending = list(state.pending_bg_tasks)
    logger.info(
        "[bg·shutdown] 等待 {} 个后台任务完成（≤{}s）",
        len(pending), timeout,
    )

    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=timeout,
        )
        logger.info("[bg·shutdown] 全部完成")
    except asyncio.TimeoutError:
        still_pending = [t for t in pending if not t.done()]
        logger.warning(
            "[bg·shutdown] {} 个任务超时未完成，强制 cancel",
            len(still_pending),
        )
        for t in still_pending:
            t.cancel()
        # 等 cancel 真正生效（CancelledError 传播完）
        await asyncio.gather(*still_pending, return_exceptions=True)
