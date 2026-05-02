"""草神知识面板 - 文书归档段（四影任务产物 list / read）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def knowledge_archives_list_api(channel, request: web.Request) -> web.Response:
    """列所有任务 workspace 的产物汇总：task_id + 标题 + 创建时间 + 产物清单。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    from paimon.foundation.task_workspace import list_workspaces
    irminsul = channel.state.irminsul

    try:
        entries = list_workspaces()
    except Exception as e:
        logger.error("[草神·文书] list_workspaces 异常: {}", e)
        return web.json_response({"error": str(e)}, status=500)

    # 每个 entry 关联 task 拉 title（如果能找到）
    items = []
    for e in entries:
        title = ""
        if irminsul:
            try:
                task = await irminsul.task_get(e["task_id"])
                if task:
                    title = task.title or task.description[:60]
            except Exception:
                pass
        items.append({
            "task_id": e["task_id"],
            "title": title,
            "created_at": e["created_at"],
            "artifacts": e["artifacts"],
        })
    # 按时间倒序
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return web.json_response({"items": items})


async def knowledge_archives_read_api(channel, request: web.Request) -> web.Response:
    """读单个任务的单份产物全文（markdown / code）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    task_id = request.query.get("task_id", "").strip()
    artifact = request.query.get("artifact", "").strip()
    if not task_id or not artifact:
        return web.json_response(
            {"error": "缺少 task_id / artifact"}, status=400,
        )

    from paimon.foundation.task_workspace import read_artifact
    try:
        content = read_artifact(task_id, artifact)
    except Exception as e:
        logger.error("[草神·文书] 读产物异常 {}/{}: {}", task_id, artifact, e)
        return web.json_response({"error": str(e)}, status=500)
    if content is None:
        return web.json_response({"error": "未找到"}, status=404)
    return web.json_response({
        "task_id": task_id,
        "artifact": artifact,
        "body": content,
    })


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 knowledge_archives 面板的 2 个路由。"""
    app.router.add_get("/api/knowledge/archives/list", lambda r, ch=channel: knowledge_archives_list_api(ch, r))
    app.router.add_get("/api/knowledge/archives/read", lambda r, ch=channel: knowledge_archives_read_api(ch, r))
