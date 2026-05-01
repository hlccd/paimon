"""订阅类型注册表 —— 业务实体生命周期带订阅

每个 archon 在自己模块实装 register_subscription_types()，bootstrap 启动时
统一调一轮。venti.collect_subscription 触发时按 sub.binding_kind 查 registry
找到对应 collector 执行——一个采集器实现复用给所有走 web-search 模板的 archon。

binding_kind 取值：
  - 'manual'：用户在 /feed 手填关键词订阅（venti 注册）
  - 'mihoyo_game'：水神隐式订阅（绑账号自动 ensure；furina_game 注册）
  - 后续可扩 'stock_watch' 等

设计沿用 task_types.py 模式（dataclass + 模块级 dict 注册表）；不强行抽公共
基类，因为 SubscriptionTypeMeta 跟 TaskTypeMeta 字段差异大（collector 签名 vs
dispatcher 签名）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.subscription import Subscription
    from paimon.state import State


# Collector 签名：执行一次订阅采集（搜→去重→落库→digest→push→mark_pushed）
# 跟 task_types.dispatcher 对齐：从 state 拿 archon/model/irminsul/march 等依赖
SubscriptionCollector = Callable[["Subscription", "State"], Awaitable[None]]


@dataclass(frozen=True)
class SubscriptionTypeMeta:
    """一种 binding_kind 的元信息 + 采集器绑定。

    必填：
      binding_kind     唯一标识符，如 'manual' / 'mihoyo_game'
      display_label    UI chip 文本，如 '风神订阅' / '水神·游戏资讯'
      archon           所属神 key（同 task_types.ARCHONS）
      manager_panel    管理面板 URL 前缀，如 '/feed' / '/game'；/tasks 跳转用
      collector        venti.collect_subscription dispatch 时调用的采集函数

    可选：
      description_builder  异步构造"本订阅在做什么"的人类描述
                           入参 (Subscription, Irminsul)，返回中文短句
    """

    binding_kind: str
    display_label: str
    archon: str
    manager_panel: str
    collector: SubscriptionCollector
    description_builder: Callable[
        ["Subscription", "Irminsul"], Awaitable[str],
    ] | None = None


_REGISTRY: dict[str, SubscriptionTypeMeta] = {}


def register(meta: SubscriptionTypeMeta) -> None:
    """注册订阅类型。重复注册发 warning 并覆盖（便于热重载场景）。"""
    if meta.binding_kind in _REGISTRY:
        logger.warning(
            "[subscription_types] 重复注册 {}，覆盖旧版本", meta.binding_kind,
        )
    _REGISTRY[meta.binding_kind] = meta
    logger.info(
        "[subscription_types] 注册 {} → {} (面板={})",
        meta.binding_kind, meta.display_label, meta.manager_panel,
    )


def get(binding_kind: str) -> SubscriptionTypeMeta | None:
    return _REGISTRY.get(binding_kind)


def all_types() -> list[SubscriptionTypeMeta]:
    return list(_REGISTRY.values())


def is_registered(binding_kind: str) -> bool:
    return binding_kind in _REGISTRY


def clear_for_test() -> None:
    """仅测试用：清空注册表。"""
    _REGISTRY.clear()
