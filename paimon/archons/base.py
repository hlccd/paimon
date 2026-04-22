"""七神基类 — 所有 Archon 的公共接口"""
from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.llm.model import Model


class Archon(abc.ABC):
    name: str = ""
    description: str = ""

    @abc.abstractmethod
    async def execute(
        self,
        task: TaskEdict,
        subtask: Subtask,
        model: Model,
        irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        """执行子任务，返回结果文本。"""
