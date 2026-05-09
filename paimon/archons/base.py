"""七神基类 — Archon ABC（namespace 标识）。

历史：
- 旧 base.py 含 6 个 helper（_invoke_skill_workflow / _setup_tools 等），
  当时四影通过 archon.execute → 这些 helper 跑 skill workflow。
- helper 全部下沉到 `paimon/shades/_helpers/runner_helpers.py`（无主公共），
  archons 子类的 execute 都是兜底（不参与执行路径），ABC helper 沦为死代码。
- 已删除 6 个 helper；selfcheck 等外部使用方改直接调 shades/_helpers。

剩余职责：
- ABC `execute` 抽象方法（满足 issubclass(X, Archon) + isinstance 检查）
- 类属性占位 `name / description / allowed_tools`（七神实例化时覆写）
"""
from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.llm.model import Model


class Archon(abc.ABC):
    name: str = ""
    description: str = ""
    allowed_tools: set[str] = set()

    @abc.abstractmethod
    async def execute(
        self,
        task: "TaskEdict",
        subtask: "Subtask",
        model: "Model",
        irminsul: "Irminsul",
        prior_results: list[str] | None = None,
    ) -> str:
        """执行子任务（兜底；archon 实例实际不参与执行路径）。"""
