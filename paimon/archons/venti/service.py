"""风神主类 VentiArchon：__init__ + is_running + 4 mixin（采集/日报/预警/...）。

⚠️ 当前状态（2026-05 解耦后）：
- execute() 内部"通用采集 tool-loop"已移除（asmoday 不再调本节点 execute）
- 保留：_inflight / is_running / _CollectMixin / _DigestMixin / _AlertMixin / _LoginMixin
- 保留功能：feed_collect cron / /feed 面板 / LLM digest（订阅 + 事件型）/ 站点扫码 cookies
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from paimon.archons.base import Archon
from paimon.foundation.irminsul.task import Subtask, TaskEdict

from ._alert import _AlertMixin
from ._collect import _CollectMixin
from ._digest import _DigestMixin
from ._login import _LoginMixin

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.llm.model import Model


class VentiArchon(_CollectMixin, _DigestMixin, _AlertMixin, _LoginMixin, Archon):
    """风神·巴巴托斯：舆情采集 + 日报组装 + P0 即时预警 + 站点 cookies 登录管理。"""

    name = "风神"
    description = "信息采集 + LLM digest + /feed 面板 + 站点登录代理"
    allowed_tools: set[str] = set()

    def __init__(self) -> None:
        # 订阅采集 in-flight 集合：进入 collect_subscription 加入、finally 移除
        # 用途：① 前端卡片显示「采集中」角标 ② 防并发重入（cron + 手动按钮重叠）
        self._inflight: set[str] = set()
        # 站点扫码登录会话池（_LoginMixin 用，惰性初始化但显式声明便于追踪）
        self._pending_login: dict = {}
        self._login_gc_task = None

    def is_running(self, sub_id: str) -> bool:
        return sub_id in self._inflight

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: "Model", irminsul: "Irminsul",
        prior_results: list[str] | None = None,
    ) -> str:
        # v6 解耦：execute 内部业务已移除（搬到 paimon/shades/naberius/）
        # asmoday 不再调本节点；保留方法签名仅为满足 Archon ABC 约定
        return f"[{self.name}] execute 路径已解耦（v6），请参考 docs/archons/venti.md"
