"""任务面板 API — /tasks 页面 + 三月调度任务列表 + 四影任务详情。"""
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
    from paimon.channels.webui.tasks_html import build_tasks_html
    return web.Response(
        text=build_tasks_html(),
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


async def tasks_complex_list_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """列 7 天内创建者派蒙*的未归档四影任务（按 updated_at DESC，上限 20）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"tasks": []})

    edicts = await irminsul.task_list(limit=50)
    now = _time.time()
    cutoff = now - 7 * 86400

    items = [
        e for e in edicts
        if (e.creator or "").startswith("派蒙")
        and e.lifecycle_stage != "archived"
        and (e.updated_at or e.created_at) >= cutoff
    ][:20]

    # 拉子任务计数（顺手汇总；任务数 ≤ 20，单 query 数量可控）
    out = []
    for e in items:
        try:
            subs = await irminsul.subtask_list(e.id)
            sub_total = len(subs)
            sub_done = sum(1 for s in subs if s.status == "completed")
            sub_failed = sum(1 for s in subs if s.status == "failed")
        except Exception as ex:
            logger.debug("[四影面板] 子任务计数失败 task={}: {}", e.id[:8], ex)
            sub_total = sub_done = sub_failed = 0
        end_ts = e.archived_at or e.updated_at or 0
        duration = (end_ts - e.created_at) if e.created_at and end_ts > e.created_at else 0
        out.append({
            "id": e.id,
            "title": e.title,
            "status": e.status,
            "lifecycle_stage": e.lifecycle_stage,
            "creator": e.creator,
            "session_id": e.session_id,
            "created_at": e.created_at,
            "updated_at": e.updated_at,
            "archived_at": e.archived_at,
            "duration_seconds": int(duration),
            "subtask_total": sub_total,
            "subtask_completed": sub_done,
            "subtask_failed": sub_failed,
        })
    return web.json_response({"tasks": out})


async def tasks_complex_detail_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """返回单个四影任务详情：edict + 子任务清单 + summary md（用于 modal）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    task_id = request.match_info["task_id"]
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"error": "irminsul not ready"}, status=503)

    edict = await irminsul.task_get(task_id)
    if not edict:
        return web.json_response({"error": "not found"}, status=404)

    subtasks = await irminsul.subtask_list(task_id)
    end_ts = edict.archived_at or edict.updated_at or 0
    duration = (end_ts - edict.created_at) if edict.created_at and end_ts > edict.created_at else 0

    # 摘要：复用 /task-index 同款 fallback 链（workspace summary.md →
    # push_archive 终局消息 → subtask.result 拼接 → 诊断兜底）
    from paimon.shades._task_summary import resolve_task_summary
    summary_md = await resolve_task_summary(
        irminsul, task_id, subtasks, max_chars=5000,
    )

    return web.json_response({
        "task": {
            "id": edict.id,
            "title": edict.title,
            "description": edict.description,
            "status": edict.status,
            "lifecycle_stage": edict.lifecycle_stage,
            "creator": edict.creator,
            "session_id": edict.session_id,
            "created_at": edict.created_at,
            "updated_at": edict.updated_at,
            "archived_at": edict.archived_at,
            "duration_seconds": int(duration),
        },
        "subtasks": [
            {
                "id": s.id,
                "assignee": s.assignee,
                "description": s.description,
                "status": s.status,
                "verdict_status": s.verdict_status,
                "round": s.round,
                "result": (s.result or "")[:1500],
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in subtasks
        ],
        "summary_md": summary_md,
    })


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 tasks 面板 4 个路由（page + 3 个 API）。"""
    app.router.add_get("/tasks", lambda r, ch=channel: tasks_page(ch, r))
    app.router.add_get("/api/tasks", lambda r, ch=channel: tasks_api(ch, r))
    app.router.add_get("/api/tasks/complex", lambda r, ch=channel: tasks_complex_list_api(ch, r))
    app.router.add_get("/api/tasks/complex/{task_id}", lambda r, ch=channel: tasks_complex_detail_api(ch, r))
