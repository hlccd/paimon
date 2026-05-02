"""三月自检面板 API — Quick 探针 + Deep 历史 runs + report/findings 详情。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def selfcheck_page(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.Response(
            text=channel._get_login_html(), content_type="text/html",
        )
    from paimon.channels.webui.selfcheck_html import build_selfcheck_html
    cfg = channel.state.cfg
    deep_hidden = bool(getattr(cfg, "selfcheck_deep_hidden", True)) if cfg else True
    return web.Response(
        text=build_selfcheck_html(deep_hidden=deep_hidden),
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def selfcheck_quick_latest_api(channel, request: web.Request,
) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    svc = channel.state.selfcheck
    if not svc:
        return web.json_response({"run": None})
    latest = await svc.latest_run("quick")
    return web.json_response({"run": _run_to_json(latest) if latest else None})


async def selfcheck_quick_run_api(channel, request: web.Request,
) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    svc = channel.state.selfcheck
    if not svc:
        return web.json_response({"error": "selfcheck 未启用"}, status=503)
    run = await svc.run_quick(triggered_by="webui")
    return web.json_response({"run": _run_to_json(run)})


async def selfcheck_runs_list_api(channel, request: web.Request,
) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    svc = channel.state.selfcheck
    if not svc:
        return web.json_response({"runs": []})
    kind = request.query.get("kind", "").strip() or None
    if kind and kind not in ("quick", "deep"):
        return web.json_response({"error": "kind 必须是 quick 或 deep"}, status=400)
    try:
        limit = max(1, min(int(request.query.get("limit", "50")), 500))
        offset = max(0, int(request.query.get("offset", "0")))
    except (TypeError, ValueError):
        limit, offset = 50, 0
    runs = await svc.list_runs(kind=kind, limit=limit, offset=offset)
    total = await svc.count_runs(kind=kind)
    return web.json_response({
        "runs": [_run_to_json(r) for r in runs],
        "total": total,
    })


async def selfcheck_run_detail_api(channel, request: web.Request,
) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    svc = channel.state.selfcheck
    if not svc:
        return web.json_response({"error": "selfcheck 未启用"}, status=503)
    run_id = request.match_info["run_id"]
    run = await svc.get_run(run_id)
    if not run:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response({"run": _run_to_json(run)})


async def selfcheck_run_report_api(channel, request: web.Request,
) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    svc = channel.state.selfcheck
    if not svc:
        return web.json_response({"error": "selfcheck 未启用"}, status=503)
    run_id = request.match_info["run_id"]
    text = await svc.get_report(run_id)
    if text is None:
        return web.Response(text="report.md 不存在（Quick 记录或 Deep 未完成）", status=404)
    return web.Response(
        text=text,
        content_type="text/markdown",
        charset="utf-8",
        headers={
            "Content-Disposition": f'inline; filename="report-{run_id[:8]}.md"',
        },
    )


async def selfcheck_run_findings_api(channel, request: web.Request,
) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    svc = channel.state.selfcheck
    if not svc:
        return web.json_response({"findings": []})
    run_id = request.match_info["run_id"]
    findings = await svc.get_findings(run_id)
    return web.json_response({"findings": findings, "count": len(findings)})


async def selfcheck_run_quick_api(channel, request: web.Request,
) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    svc = channel.state.selfcheck
    if not svc:
        return web.json_response({"snapshot": None})
    run_id = request.match_info["run_id"]
    snap = await svc.get_quick_snapshot(run_id)
    return web.json_response({"snapshot": snap})


async def selfcheck_run_delete_api(channel, request: web.Request,
) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    svc = channel.state.selfcheck
    if not svc:
        return web.json_response({"error": "selfcheck 未启用"}, status=503)
    run_id = request.match_info["run_id"]
    ok = await svc.delete_run(run_id)
    return web.json_response({"ok": ok})


async def selfcheck_deep_run_api(channel, request: web.Request,
) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    # Deep 暂缓开关（docs/todo.md §三月·自检·Deep 暂缓）
    cfg = channel.state.cfg
    if cfg and getattr(cfg, "selfcheck_deep_hidden", True):
        return web.json_response(
            {
                "error": "Deep 自检当前暂缓（LLM 执行不充分）",
                "hint": "换 Claude Opus 级模型后设 SELFCHECK_DEEP_HIDDEN=false",
            },
            status=503,
        )
    svc = channel.state.selfcheck
    if not svc:
        return web.json_response({"error": "selfcheck 未启用"}, status=503)
    try:
        data = await request.json() if request.body_exists else {}
    except Exception:
        data = {}
    args = (data.get("args") or "").strip() or None
    result = await svc.run_deep(args=args, triggered_by="webui")
    status = 200 if result.get("started") else 409
    return web.json_response(result, status=status)


def _run_to_json(run) -> dict:
    """SelfcheckRun → JSON dict（给前端 + API 用）"""
    return {
        "id": run.id,
        "kind": run.kind,
        "triggered_at": run.triggered_at,
        "triggered_by": run.triggered_by,
        "status": run.status,
        "duration_seconds": run.duration_seconds,
        "check_args": run.check_args,
        "error": run.error,
        "p0_count": run.p0_count,
        "p1_count": run.p1_count,
        "p2_count": run.p2_count,
        "p3_count": run.p3_count,
        "findings_total": run.findings_total,
        "quick_summary": run.quick_summary,
        "progress": run.progress,  # deep running 期间 watcher 填充
    }


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 selfcheck 面板的 10 个路由。"""
    app.router.add_get("/selfcheck", lambda r, ch=channel: selfcheck_page(ch, r))
    app.router.add_get("/api/selfcheck/quick/latest", lambda r, ch=channel: selfcheck_quick_latest_api(ch, r))
    app.router.add_post("/api/selfcheck/quick/run", lambda r, ch=channel: selfcheck_quick_run_api(ch, r))
    app.router.add_get("/api/selfcheck/runs", lambda r, ch=channel: selfcheck_runs_list_api(ch, r))
    app.router.add_get("/api/selfcheck/runs/{run_id}", lambda r, ch=channel: selfcheck_run_detail_api(ch, r))
    app.router.add_get("/api/selfcheck/runs/{run_id}/report", lambda r, ch=channel: selfcheck_run_report_api(ch, r))
    app.router.add_get("/api/selfcheck/runs/{run_id}/findings", lambda r, ch=channel: selfcheck_run_findings_api(ch, r))
    app.router.add_get("/api/selfcheck/runs/{run_id}/quick", lambda r, ch=channel: selfcheck_run_quick_api(ch, r))
    app.router.add_delete("/api/selfcheck/runs/{run_id}", lambda r, ch=channel: selfcheck_run_delete_api(ch, r))
    app.router.add_post("/api/selfcheck/deep/run", lambda r, ch=channel: selfcheck_deep_run_api(ch, r))
