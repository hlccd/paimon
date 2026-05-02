"""WebUI 业务面板 API 子包 — 各面板 handler + register_routes 集中在此。

设计：每个业务面板（authz/tasks/plugins/...）一个独立 module，导出
`register_routes(app, channel)` 函数。主 channel.py 的 _setup_routes
只调本模块 register_all_routes 聚合分发，避免单类承担 100+ handler。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from . import (
    authz,
    feed,
    game,
    knowledge,
    knowledge_archives,
    knowledge_kb,
    llm,
    plugins,
    push,
    selfcheck,
    sentiment,
    session,
    tasks,
    token,
    wealth,
    wealth_stock_subs,
    wealth_user_watch,
    main,
)

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


def register_all_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """聚合注册所有业务面板的路由（按面板 module 分发）。"""
    for module in (
        authz,
        feed,
        game,
        knowledge,
        knowledge_archives,
        knowledge_kb,
        llm,
        plugins,
        push,
        selfcheck,
        sentiment,
        session,
        tasks,
        token,
        wealth,
        wealth_stock_subs,
        wealth_user_watch,
        main,
    ):
        module.register_routes(app, channel)
