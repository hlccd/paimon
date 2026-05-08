"""七神基类 — Archon ABC（v7 后只剩 namespace 标识）。

历史：
- v6 之前 base.py 含 6 个 helper（_invoke_skill_workflow / _setup_tools 等），
  当时四影通过 archon.execute → 这些 helper 跑 skill workflow。
- v7 解耦后 helper 全部下沉到 `paimon/shades/_helpers/runner_helpers.py`（无主公共），
  archons 子类的 execute 都是兜底（asmoday 不再调它们），ABC helper 沦为死代码。
- v7 清理：删除 6 个 helper；selfcheck 等外部使用方改直接调 shades/_helpers。

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
        """执行子任务，返回结果文本。

        v7 后实际不被 asmoday 调用（管线已转 shades/_STAGE_ROUTER → 各影实现）。
        七神子类的 execute 一般兜底返"已解耦"字符串。
        """
