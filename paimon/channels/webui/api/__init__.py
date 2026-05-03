"""WebUI 业务面板 API 子包 — 各面板 handler + register_routes 集中在此。

设计：每个业务面板（authz/tasks/plugins/...）一个独立 module，导出
`register_routes(app, channel)` 函数。主 channel.py 的 _setup_routes
只调本模块 register_all_routes 聚合分发，避免单类承担 100+ handler。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web


def check_confirm(request: web.Request) -> bool:
    """USB-007 破坏性操作 server-side 确认：
    要求请求带 `X-Confirm: yes` header 才允许执行。
    防 CSRF（第三方页面 POST 不带 header） + 防误删（前端必须显式确认）。
    """
    return (request.headers.get("X-Confirm") or "").strip().lower() in (
        "yes", "1", "true",
    )


def confirm_required_response() -> web.Response:
    return web.json_response(
        {
            "ok": False,
            "error": "破坏性操作需 X-Confirm: yes header（前端 confirm 后再发）",
        },
        status=400,
    )

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
