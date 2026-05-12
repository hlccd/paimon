"""风神主类 VentiArchon：__init__ + is_running + 3 mixin（采集/日报/登录）。

archon 本体 execute 不参与执行；业务接口走 mixin + cron + webui 面板。
保留：_inflight / is_running / _CollectMixin / _DigestMixin / _LoginMixin
功能：topic_research cron / /feed 面板 / 站点扫码 cookies
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from paimon.archons.base import Archon

from ._collect import _CollectMixin
from ._digest import _DigestMixin
from ._login import _LoginMixin

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.llm.model import Model


class VentiArchon(_CollectMixin, _DigestMixin, _LoginMixin, Archon):
    """风神·巴巴托斯：topic 调研 + 站点 cookies 登录管理。"""

    name = "风神"
    description = "topic 调研订阅 + /feed 面板 + 站点登录代理"
    allowed_tools: set[str] = set()

    def __init__(self) -> None:
        # 订阅采集 in-flight 集合：进入 collect_subscription 加入、finally 移除
        # 用途：① 前端卡片显示「采集中」角标 ② 防并发重入（cron + 手动按钮重叠）
        self._inflight: set[str] = set()
        # hotspot / 近期回顾 单例 inflight 标志（不绑 sub_id；防并发 + 前端跨刷新看状态）
        self._hotspot_inflight: bool = False
        self._weekly_inflight: bool = False
        # 站点扫码登录会话池（_LoginMixin 用，惰性初始化但显式声明便于追踪）
        self._pending_login: dict = {}
        self._login_gc_task = None

    def is_running(self, sub_id: str) -> bool:
        return sub_id in self._inflight

    def is_hotspot_running(self) -> bool:
        return self._hotspot_inflight

    def is_weekly_running(self) -> bool:
        return self._weekly_inflight

    async def execute(self) -> str:
        # 保留方法签名仅为满足 Archon ABC 约定（archon 实例不参与执行路径）
        return f"[{self.name}] 业务接口走 mixin + cron + /feed 面板，archon 本体不参与执行"
