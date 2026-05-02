"""风神事件聚类员主类 EventClusterer：__init__ + _ProcessMixin + _LLMMixin。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from ._llm import _LLMMixin
from ._models import ProcessedEvent
from ._process import _ProcessMixin

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.llm.model import Model


class EventClusterer(_ProcessMixin, _LLMMixin):
    """风神事件聚类员：跨批次合并 + 单事件结构化抽取。

    阶段 A 行为：force_new=True，所有条目按 new 处理；analyze prompt 完整生效。
    阶段 B 起 force_new=False，启用聚类 LLM 决策跨批次合并。
    """

    def __init__(
        self, irminsul: "Irminsul", model: "Model",
        *, force_new: bool = True,
        max_llm_calls: int | None = None,
    ):
        """
        max_llm_calls: 单批最多调 LLM 次数（含聚类 + 各事件 analyze）。
                       超出预算后剩余事件走 _fallback_analysis，避免成本失控。
                       None 或 ≤0 视作不限。对应 config.sentiment_llm_calls_per_run_max
        """
        self._iru = irminsul
        self._model = model
        self._force_new = force_new
        self._max_llm_calls = max_llm_calls if (max_llm_calls and max_llm_calls > 0) else None
