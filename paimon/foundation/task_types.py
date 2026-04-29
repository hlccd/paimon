"""周期任务类型注册表 —— 方案 D 核心

把 scheduled_tasks.task_prompt 里的魔法前缀（`[FEED_COLLECT] <sub_id>` 之类）
升级为 schema 一等公民字段 task_type + source_entity_id。

每个需要周期任务的 archon 在自己模块实装 register_task_types()，
bootstrap 启动时统一调一轮。运行时 bootstrap._on_march_ring 查 registry
找到对应 dispatcher 执行；WebUI tasks_api 查 registry 拿 display 元数据
渲染 chip + 跳转链接。

未来任何新神 / 新面板要加周期任务都走这套；禁止再往 task_prompt 塞前缀编码。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.schedule import ScheduledTask
    from paimon.state import State

# task_type='user' 保留给用户自然语言任务（task_prompt 直接喂 LLM），不需要注册。
USER_TASK_TYPE = "user"


@dataclass(frozen=True)
class TaskTypeMeta:
    """一种 task_type 的元信息 + 行为绑定。

    必填：
      task_type           唯一标识符，如 'feed_collect' / 'dividend_scan'
      display_label       UI chip 文本，如 '风神订阅'
      manager_panel       管理面板 URL 前缀，如 '/feed'；/tasks 行点击时跳转
      dispatcher          _on_march_ring 到点触发时调的业务函数

    可选：
      icon                前端图标 key，如 'rss' / 'chart'
      description_builder 异步构造"本任务在做什么"的人类描述（/tasks 渲染时用）
                          入参 (source_entity_id, irminsul)，返回如 '风神订阅：Claude AI 资讯'
      anchor_builder      source_entity_id → 面板内锚点 id（如 'sub-abc123'），
                          拼成 `{manager_panel}#{anchor}` 定位到特定实体卡片
    """

    task_type: str
    display_label: str
    manager_panel: str
    dispatcher: Callable[["ScheduledTask", "State"], Awaitable[None]]
    icon: str = ""
    description_builder: Callable[[str, "Irminsul"], Awaitable[str]] | None = None
    anchor_builder: Callable[[str], str] | None = None


_REGISTRY: dict[str, TaskTypeMeta] = {}


def register(meta: TaskTypeMeta) -> None:
    """注册任务类型。重复注册发 warning 并覆盖（便于热重载场景）。"""
    if meta.task_type == USER_TASK_TYPE:
        raise ValueError(f"task_type='{USER_TASK_TYPE}' 为保留类型，不可注册")
    if meta.task_type in _REGISTRY:
        logger.warning("[task_types] 重复注册 {}，覆盖旧版本", meta.task_type)
    _REGISTRY[meta.task_type] = meta
    logger.info(
        "[task_types] 注册 {} → {} (面板={})",
        meta.task_type, meta.display_label, meta.manager_panel,
    )


def get(task_type: str) -> TaskTypeMeta | None:
    return _REGISTRY.get(task_type)


def all_types() -> list[TaskTypeMeta]:
    return list(_REGISTRY.values())


def is_registered(task_type: str) -> bool:
    return task_type in _REGISTRY


def clear_for_test() -> None:
    """仅测试用：清空注册表。"""
    _REGISTRY.clear()
