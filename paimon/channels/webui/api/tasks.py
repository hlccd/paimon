"""任务面板 API — /tasks 页面 + 三月调度任务列表（用户定时任务 + 系统 cron）。"""
from __future__ import annotations

import time as _time
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def tasks_page(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """渲染任务面板 HTML（未登录跳登录页）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.Response(text=channel._get_login_html(), content_type="text/html")
    from paimon.channels.webui.render import render_warm_page
    return web.Response(
        text=render_warm_page(
            title="任务",
            content_template="tasks",
            active="tasks",
            extra_css='<link rel="stylesheet" href="/static/css/tasks.css">',
            extra_js='<script src="/static/js/tasks.js"></script>',
        ),
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def tasks_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """列三月所有调度任务，注入 task_type 元信息让前端按神分组+跳转管理面板。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    march = channel.state.march
    if not march:
        return web.json_response({"tasks": []})

    # 方案 D：不再过滤内部任务；内部类型经 task_types registry 查元信息注入 source 段，
    # 前端据此渲染 chip + 跳转链接 + 禁用启停，避免双写冲突同时保持可见性
    from paimon.foundation import task_types as _tt

    tasks = await march.list_tasks()
    rows: list[dict] = []
    for t in tasks:
        row = {
            "id": t.id,
            "prompt": t.task_prompt,
            "trigger_type": t.trigger_type,
            "trigger_value": t.trigger_value,
            "enabled": t.enabled,
            "next_run_at": t.next_run_at,
            "last_run_at": t.last_run_at,
            "last_error": t.last_error,
            "consecutive_failures": t.consecutive_failures,
            "created_at": t.created_at,
            "task_type": t.task_type or "user",
            "source_entity_id": t.source_entity_id or "",
        }
        if t.task_type and t.task_type != "user":
            meta = _tt.get(t.task_type)
            if meta:
                desc = ""
                if meta.description_builder:
                    try:
                        desc = await meta.description_builder(
                            t.source_entity_id, channel.state.irminsul,
                        )
                    except Exception as e:
                        logger.debug(
                            "[WebUI·tasks] description_builder 失败 {}: {}",
                            t.task_type, e,
                        )
                        desc = t.source_entity_id or ""
                else:
                    desc = t.source_entity_id or ""
                anchor = ""
                if meta.anchor_builder and t.source_entity_id:
                    try:
                        anchor = meta.anchor_builder(t.source_entity_id)
                    except Exception:
                        anchor = ""
                jump_url = (
                    f"{meta.manager_panel}#{anchor}"
                    if anchor else meta.manager_panel
                )
                row["source"] = {
                    "task_type": t.task_type,
                    "label": meta.display_label,
                    "icon": meta.icon,
                    "description": desc,
                    "jump_url": jump_url,
                    "manager_panel": meta.manager_panel,
                    "archon": meta.archon,
                    "archon_name": _tt.archon_name(meta.archon),
                    "editable": False,   # 内部类型统一禁止 /tasks 编辑
                }
            else:
                # 未注册类型：展示 ❓ chip + 允许手动删除做孤儿清理
                row["source"] = {
                    "task_type": t.task_type,
                    "label": f"❓ {t.task_type}",
                    "icon": "",
                    "description": t.source_entity_id or "（未知来源）",
                    "jump_url": "",
                    "manager_panel": "",
                    "archon": "",
                    "archon_name": "其他",
                    "editable": False,
                }
        rows.append(row)

    # archons 排序列表用于前端渲染顺序（key→中文名），未登记的归到「其他」段落
    archons = [{"key": k, "name": v} for k, v in _tt.ARCHONS.items()]
    return web.json_response({"tasks": rows, "archons": archons})


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 tasks 面板路由（page + 定时/系统任务 API）。"""
    app.router.add_get("/tasks", lambda r, ch=channel: tasks_page(ch, r))
    app.router.add_get("/api/tasks", lambda r, ch=channel: tasks_api(ch, r))
