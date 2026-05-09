"""七神基类 — Archon ABC（namespace 标识）。

剩余职责：
- ABC（满足 issubclass(X, Archon) + isinstance 检查）
- 类属性占位 `name / description / allowed_tools`（七神实例化时覆写）

execute() 已退化为兜底空方法；archon 实例不参与任何执行路径。
"""
from __future__ import annotations

import abc


class Archon(abc.ABC):
    name: str = ""
    description: str = ""
    allowed_tools: set[str] = set()

    @abc.abstractmethod
    async def execute(self) -> str:
        """兜底；archon 实例实际不参与执行路径。"""
