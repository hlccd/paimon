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


# ============ 自动升级（git pull + sys.exit(100) 让 watchdog 拉起）============

import asyncio as _aio_upgrade
_upgrade_lock = _aio_upgrade.Lock()


async def upgrade_check_api(channel, request: web.Request) -> web.Response:
    """检查远程是否有更新：git fetch + git log local..origin。返回是否落后 + commit list。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    from paimon.__main__ import _run_git
    # fetch（30s timeout）
    rc, _, err = _run_git(["fetch", "origin"])
    if rc != 0:
        return web.json_response(
            {"ok": False, "error": f"git fetch 失败: {err.strip()[:200]}"}, status=500,
        )

    # 当前 HEAD
    rc, head_out, _ = _run_git(["rev-parse", "HEAD"])
    if rc != 0:
        return web.json_response({"ok": False, "error": "git rev-parse HEAD 失败"}, status=500)
    head_short_rc, head_short, _ = _run_git(["rev-parse", "--short", "HEAD"])
    head_subject_rc, head_subject_out, _ = _run_git(["log", "-1", "--pretty=%s"])
    head_subject = head_subject_out.strip() if head_subject_rc == 0 else ""

    # 落后 commit 数
    rc, count_out, _ = _run_git(["rev-list", "--count", "HEAD..origin/main"])
    behind = int(count_out.strip() or 0) if rc == 0 else 0

    # 落后的 commit list（最多 20 条）
    rc, log_out, _ = _run_git([
        "log", "--max-count=20", "--pretty=format:%h|%s|%cr",
        "HEAD..origin/main",
    ])
    commits = []
    if rc == 0 and log_out:
        for line in log_out.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"hash": parts[0], "subject": parts[1], "age": parts[2]})

    return web.json_response({
        "ok": True,
        "head": head_out.strip(),
        "head_short": head_short.strip() if head_short_rc == 0 else head_out.strip()[:7],
        "head_subject": head_subject,
        "behind": behind,
        "commits": commits,
    })


async def upgrade_trigger_api(channel, request: web.Request) -> web.Response:
    """git pull + 退出码 100 让 watchdog 拉起新代码。

    流程：
      1. 加锁防并发
      2. git fetch + 看是否落后；不落后直接返回
      3. git pull
      4. 异步 schedule 0.5s 后 raise SystemExit(100) 让 entry() 退出
      5. 立即返回 200 给前端，前端展示「正在重启…」
    """
    # USB-007 破坏性操作 server-side 确认
    from paimon.channels.webui.api import check_confirm, confirm_required_response
    if not check_confirm(request):
        return confirm_required_response()
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    from paimon.__main__ import _run_git, trigger_upgrade_exit

    if _upgrade_lock.locked():
        return web.json_response(
            {"ok": False, "error": "已有升级任务进行中，请勿重复触发"}, status=409,
        )

    async with _upgrade_lock:
        # #A1 自挑刺：dirty tree 检查 — 工作区有未提交修改时拉取会失败 / 冲突 / 数据丢失
        # `-uno` 排除 untracked 文件（如 paimon.log / .env / 用户自己的临时文件）；
        # 只关心 modified / staged / 冲突文件——这些才会真挡 git pull。
        rc, dirty_out, _ = _run_git(["status", "--porcelain", "-uno"])
        if rc == 0 and dirty_out.strip():
            return web.json_response({
                "ok": False,
                "error": "工作区有未提交的修改，拒绝升级（防止冲突 / 丢失）：\n"
                         + dirty_out.strip()[:500]
                         + "\n\n请 ssh 上去 `git stash` 或 `git checkout -- .` 后重试",
            }, status=400)

        # 再次 fetch + 看是否真的落后（防 stale check）
        rc, _, err = _run_git(["fetch", "origin"])
        if rc != 0:
            return web.json_response(
                {"ok": False, "error": f"git fetch 失败: {err.strip()[:200]}"}, status=500,
            )
        rc, behind_out, _ = _run_git(["rev-list", "--count", "HEAD..origin/main"])
        behind = int(behind_out.strip() or 0) if rc == 0 else 0
        if behind == 0:
            return web.json_response({"ok": False, "error": "已是最新版本，无需升级"}, status=400)

        # #A 主改进：pull 之前写 last_good_commit（用 pull 前的 HEAD 作为回退点）
        # 关键：paimon 主流程 60s 后才写 last_good_commit，但升级路径必须在 pull 之前写——
        # 否则 pull 到 broken commit、watchdog 累 3 次回退时，last_good 可能还是更早或不存在
        from paimon.config import config as _cfg
        rc, head_before, _ = _run_git(["rev-parse", "HEAD"])
        if rc == 0 and head_before.strip():
            try:
                target = _cfg.paimon_home / "last_good_commit"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(head_before.strip() + "\n", encoding="utf-8")
                logger.info("[升级] 已记录 pull 前 HEAD={} 作为回退点", head_before.strip()[:7])
            except Exception as e:
                logger.warning("[升级] 写 last_good_commit 失败（不阻塞升级）: {}", e)

        # 语法预检（升级前防 broken commit；只对 paimon/ 包扫）
        import subprocess as _sp, sys as _sys
        from paimon.__main__ import _project_root_for_git
        root = _project_root_for_git()
        try:
            check_proc = _sp.run(
                [_sys.executable, "-m", "compileall", "-q", str(root / "paimon")],
                capture_output=True, text=True, timeout=60,
            )
            if check_proc.returncode != 0:
                return web.json_response({
                    "ok": False,
                    "error": "本地代码语法预检失败（不应发生）："
                             + check_proc.stdout[:300] + check_proc.stderr[:300],
                }, status=500)
        except Exception as e:
            logger.warning("[升级] 语法预检异常（跳过）: {}", e)

        # git pull
        rc, pull_out, pull_err = _run_git(["pull", "--ff-only", "origin", "main"])
        if rc != 0:
            return web.json_response({
                "ok": False,
                "error": f"git pull 失败: {(pull_err or pull_out).strip()[:300]}",
            }, status=500)

        # pull 后再 syntax check 一遍
        try:
            check_proc = _sp.run(
                [_sys.executable, "-m", "compileall", "-q", str(root / "paimon")],
                capture_output=True, text=True, timeout=60,
            )
            if check_proc.returncode != 0:
                # 拉到 broken commit！立即 git reset --hard 回退
                _run_git(["reset", "--hard", "HEAD@{1}"])
                return web.json_response({
                    "ok": False,
                    "error": "拉取的代码语法预检失败，已自动 git reset 回退："
                             + check_proc.stdout[:300] + check_proc.stderr[:300],
                }, status=500)
        except Exception as e:
            logger.warning("[升级] pull 后语法预检异常（继续重启）: {}", e)

        # 检查 pyproject.toml 是否变（提示用户 watchdog 内 pip install）
        rc, dep_diff, _ = _run_git([
            "diff", "HEAD@{1}..HEAD", "--name-only", "--", "pyproject.toml",
        ])
        deps_changed = bool(rc == 0 and dep_diff.strip())

        rc, new_head_short, _ = _run_git(["rev-parse", "--short", "HEAD"])

        logger.info(
            "[升级] git pull 完成 → 新 HEAD={}，0.5s 后退出码 100 让 watchdog 拉起",
            new_head_short.strip() if rc == 0 else "?",
        )

        # 调度退出
        trigger_upgrade_exit()

        return web.json_response({
            "ok": True,
            "new_head_short": new_head_short.strip() if rc == 0 else "",
            "deps_changed": deps_changed,
            "deps_warning": (
                "pyproject.toml 已变化。watchdog 会拉起新进程，但**不会**自动 pip install — "
                "如有依赖变更请 ssh 上去跑 `pip install -e .` 后再重启 watchdog"
            ) if deps_changed else "",
            "message": "升级成功，进程将在 1 秒内重启加载新代码。前端会暂时无响应，请等 5-10 秒后刷新。",
        })


async def upgrade_rollback_status_api(channel, request: web.Request) -> web.Response:
    """读 .paimon/last_rollback（watchdog 触发回退时写入）→ 返回 JSON 给前端展示警示条。

    文件格式（5 行；paimon 启动通知后会附加第 6 行 "notified" 标记）：
      <ts>\n<before_hash>\n<after_hash>\n<fail_count>\n<kind>\n[notified\n]
    kind: ROLLED_BACK（成功回退）/ NEEDS_MANUAL（HEAD 已等于 last_good，无法再回退）
    """
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    from paimon.config import config as _cfg
    f = _cfg.paimon_home / "last_rollback"
    if not f.exists():
        return web.json_response({"has_rollback": False})
    try:
        lines = f.read_text(encoding="utf-8").splitlines()
        if len(lines) < 5:
            return web.json_response({"has_rollback": False, "warning": "last_rollback 格式不完整"})
        return web.json_response({
            "has_rollback": True,
            "ts": int(lines[0].strip() or 0),
            "before": lines[1].strip(),
            "after": lines[2].strip(),
            "fail_count": int(lines[3].strip() or 0),
            "kind": lines[4].strip(),
        })
    except Exception as e:
        logger.warning("[升级] 读 last_rollback 失败: {}", e)
        return web.json_response({"has_rollback": False, "error": str(e)})


async def upgrade_rollback_ack_api(channel, request: web.Request) -> web.Response:
    """用户点「我知道了」→ 删除 .paimon/last_rollback 让警示条消失。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    from paimon.config import config as _cfg
    f = _cfg.paimon_home / "last_rollback"
    try:
        if f.exists():
            f.unlink()
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 selfcheck 面板的 14 个路由（10 自检 + 4 升级）。"""
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
    app.router.add_get("/api/selfcheck/upgrade/check", lambda r, ch=channel: upgrade_check_api(ch, r))
    app.router.add_post("/api/selfcheck/upgrade/trigger", lambda r, ch=channel: upgrade_trigger_api(ch, r))
    app.router.add_get("/api/selfcheck/upgrade/rollback_status", lambda r, ch=channel: upgrade_rollback_status_api(ch, r))
    app.router.add_post("/api/selfcheck/upgrade/rollback_ack", lambda r, ch=channel: upgrade_rollback_ack_api(ch, r))
