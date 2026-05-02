"""三月 Deep 自检实现：调 check skill → 守 .check/ 产物 → 解析归档 → 推送。

Deep 是 LLM 驱动的项目体检（参数模式 project-health），跑 3-15 分钟；
单例锁防并发；watcher 后台轮询 state.json 写 progress 进度；
完成后必须看到 candidates.jsonl 才算成功（防 LLM 偷懒）。
"""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from ._helpers import (
    _CHECK_DIR_NAME,
    _CHECK_FILES,
    _PROGRESS_POLL_INTERVAL,
    _extract_progress,
    _platform_exec_hint,
)

if TYPE_CHECKING:
    from .service import SelfCheckService


async def run_deep_inner(
    svc: "SelfCheckService", run_id: str, args: str, *, triggered_by: str,
) -> None:
    """Deep 实际执行：入 running 记录 → 跑 check → 归档快照 → 解析 → 更新 → 推送。

    **关键约束**：完成判定必须基于 blob 目录里真的有 `candidates.jsonl`。
    LLM 可能没按指令生成 .check/（幻觉 / 提前结束 / 路径错位）——
    若产物缺失，标 failed 而不是 completed，避免面板显示"0 findings 全绿"误导用户。

    完成后**必须**把 _deep_busy 置回 False + 从 state.session_tasks 清理，
    走 finally 保障即便 cancel / 异常路径也能释放。
    """
    from paimon.foundation.irminsul import SelfcheckRun
    from paimon.shades._check_parser import (
        count_severity, parse_candidates_file,
    )
    from paimon.state import state

    t0 = time.time()
    task_key = f"selfcheck_deep_{run_id}"

    try:
        run = SelfcheckRun(
            id=run_id, kind="deep", triggered_at=t0,
            triggered_by=triggered_by, status="running",
            check_args=args,
        )
        await svc._irminsul.selfcheck_create(run, actor="三月·自检")
        logger.info(
            "[三月·自检·Deep] 启动 run={} args='{}' by={}",
            run_id, args, triggered_by,
        )

        project_root = Path(__file__).resolve().parent.parent.parent.parent
        root_check = project_root / _CHECK_DIR_NAME
        state_path = root_check / "state.json"

        # 清掉可能的旧 .check/ 避免混入别轮产物
        if root_check.exists():
            shutil.rmtree(root_check, ignore_errors=True)

        # 启动进度 watcher（后台轮询 state.json 写 DB）
        stop_watcher = asyncio.Event()
        watcher_task = asyncio.create_task(
            _progress_watcher(svc, run_id, state_path, stop_watcher),
            name=f"selfcheck_watcher_{run_id}",
        )

        try:
            # 调 check skill（超时保护）
            timeout = max(60, int(svc._cfg.selfcheck_deep_timeout_seconds))
            await asyncio.wait_for(
                _invoke_check_skill(svc, args, project_root),
                timeout=timeout,
            )

            # 快照 .check/ → blob
            blob = svc._irminsul.selfcheck_ensure_blob_dir(run_id)
            snapshotted: list[str] = []
            for fname in _CHECK_FILES:
                src = root_check / fname
                if src.exists():
                    try:
                        shutil.copy2(src, blob / fname)
                        snapshotted.append(fname)
                    except OSError as e:
                        logger.warning(
                            "[三月·自检·Deep] 快照 {} 失败: {}", fname, e,
                        )

            # 清理 <root>/.check/（产物已快照，不留原地）
            shutil.rmtree(root_check, ignore_errors=True)

            # **产物存在性校验**：candidates.jsonl 必须存在才算成功
            # 若 LLM 未按指令执行，标 failed 避免 UI 误导
            cand_path = blob / "candidates.jsonl"
            if not cand_path.exists():
                await mark_deep_failed(
                    svc, run_id, t0,
                    "check skill 未生成 candidates.jsonl —— "
                    f"可能 LLM 偷懒 / 执行路径不对 / 提前终止。"
                    f"已快照 {len(snapshotted)} 个文件: {snapshotted}",
                )
                return

            findings = parse_candidates_file(cand_path)
            sev = count_severity(findings)
            total = len(findings)

            duration = time.time() - t0
            await svc._irminsul.selfcheck_update(
                run_id, actor="三月·自检",
                status="completed",
                duration_seconds=duration,
                p0_count=sev["P0"], p1_count=sev["P1"],
                p2_count=sev["P2"], p3_count=sev["P3"],
                findings_total=total,
            )
            await svc._irminsul.audit_append(
                event_type="selfcheck_deep_completed",
                payload={
                    "run_id": run_id,
                    "args": args,
                    "duration_seconds": round(duration, 2),
                    "severity_counts": sev,
                    "findings_total": total,
                    "snapshotted": snapshotted,
                },
                actor="三月·自检",
            )
            logger.info(
                "[三月·自检·Deep] 完成 run={} P0={} P1={} P2={} P3={} "
                "耗时={:.1f}s",
                run_id, sev["P0"], sev["P1"], sev["P2"], sev["P3"], duration,
            )

            # 推送通知（如果 march 在）
            await _notify_deep_result(svc, run_id, sev, total, duration)

            # GC
            try:
                await svc._irminsul.selfcheck_gc(
                    kind="deep",
                    keep_n=max(1, int(svc._cfg.selfcheck_deep_retention)),
                    actor="三月·自检",
                )
            except Exception as e:
                logger.warning("[三月·自检·Deep] GC 失败: {}", e)

        except asyncio.TimeoutError:
            await mark_deep_failed(
                svc, run_id, t0,
                f"超时 ({svc._cfg.selfcheck_deep_timeout_seconds}s)",
            )
        except asyncio.CancelledError:
            await mark_deep_failed(svc, run_id, t0, "被取消")
            raise
        except Exception as e:
            logger.exception("[三月·自检·Deep] 异常 run={}: {}", run_id, e)
            await mark_deep_failed(svc, run_id, t0, str(e))
        finally:
            # 停 watcher（成功/失败/取消都要停；让它自己退出循环，不强杀）
            stop_watcher.set()
            try:
                await asyncio.wait_for(watcher_task, timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                watcher_task.cancel()

    finally:
        # 始终释放 busy + 清理 task 引用，即便 cancel / 异常路径
        svc._deep_busy = False
        state.session_tasks.pop(task_key, None)


async def _progress_watcher(
    svc: "SelfCheckService", run_id: str, state_path: Path, stop: asyncio.Event,
) -> None:
    """后台轮询 `.check/state.json`，抽进度字段写 DB。

    - 间隔 5s；stop event 触发立刻退出
    - 所有 IO 异常都吞（文件可能不存在、写到一半、JSON 不完整）
    - 同一进度快照不重复写 DB（polled_at 之外字段相同则跳过）
    """
    last_snapshot: dict[str, Any] = {}
    while not stop.is_set():
        try:
            if state_path.exists():
                raw = state_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                progress = _extract_progress(data)
                # 空 progress（非 dict 入参 / 全字段缺省）→ 不触发 update
                if progress:
                    # 对比时剔除 polled_at（每次都变），看实质是否变化
                    cur_sig = {k: v for k, v in progress.items() if k != "polled_at"}
                    last_sig = {k: v for k, v in last_snapshot.items() if k != "polled_at"}
                    if cur_sig != last_sig:
                        await svc._irminsul.selfcheck_update(
                            run_id, actor="三月·自检·进度",
                            progress=progress,
                        )
                        last_snapshot = progress
        except (OSError, json.JSONDecodeError):
            # 文件不存在 / 写到一半 / 格式损坏：本轮略过，下轮再试
            pass
        except Exception as e:
            # 非预期异常（DB 连接断等）：记一下继续轮询，不拖垮主流程
            logger.debug("[三月·自检·进度] watcher 异常（吞）: {}", e)

        # 睡眠 + 可响应 stop：用 wait_for 让 5s 轮询兼 stop 信号
        try:
            await asyncio.wait_for(stop.wait(), timeout=_PROGRESS_POLL_INTERVAL)
        except asyncio.TimeoutError:
            continue  # 正常超时 → 进下一轮
    logger.debug("[三月·自检·进度] watcher 退出 run={}", run_id)


async def _invoke_check_skill(
    svc: "SelfCheckService", args: str, project_root: Path,
) -> None:
    """复用 Archon 基类的 _invoke_skill_workflow 跑 check skill。

    借一个临时 Archon 外壳（不登记 state.channels，仅作 workflow 驱动）。
    """
    from paimon.archons.base import Archon

    class _SelfCheckArchon(Archon):
        name = "派蒙·自检"
        description = "三月·Deep selfcheck（调 check skill）"
        # file_ops 文件读写、glob 跨平台文件查找、exec 兜底复杂命令
        allowed_tools = {"file_ops", "glob", "exec"}

        async def execute(self, *a, **k) -> str:
            return ""

    archon = _SelfCheckArchon()
    platform_hint = _platform_exec_hint()
    framing = (
        f"【三月·Deep 自检 · paimon 适配层】\n"
        f"目标路径: 项目根 {project_root}\n"
        f"产物位置: {project_root}/.check/（必须写齐 "
        f"candidates.jsonl + report.md + state.json 三件套）\n"
        "\n"
        "## ⚠️ 强制启动顺序（违反会失败）\n"
        "你可用的 tool 名字**必须**严格对照下面列表（大小写敏感，注意"
        "`glob` 是 paimon 的原生工具，不是 Python 的 import glob 模块）：\n"
        "\n"
        f"**第一步**：跑 `glob(pattern=\"paimon/**/*.py\", path=\"{project_root}\")`\n"
        "  拿到 paimon 目录下所有 Python 文件的相对路径列表（每行一个）。\n"
        "  这是 check skill 「第二步初始化 → 扫描目标」的正确实现。\n"
        "\n"
        "**禁止的替代写法**（以下任何一种都会导致失败，请严格避免）：\n"
        "  ❌ `exec(\"find ... -name *.py\")` —— Windows 下 find 语义不同会返错\n"
        "  ❌ `exec(\"ls ... / dir ...\")` —— shell 解析差异大\n"
        "  ❌ `exec(\"python -c \\\"import os.walk / glob / fnmatch...\\\"\")` \n"
        "       —— 多行字符串在 PowerShell 转义常坏，已观测到返 5 字符空输出\n"
        "  ❌ 自己拼 `file_ops(list)` 递归各个子目录 —— 慢、易遗漏\n"
        "  ✅ 直接 `glob(pattern=\"paimon/**/*.py\")` —— 一次调用拿全列表\n"
        "\n"
        "## 工具映射（Claude Code 原生 → paimon 工具）\n"
        "check SKILL.md 里写的是 Claude Code 的原生工具名，你在 paimon 里只能用：\n"
        "  - Read          → file_ops(action=\"read\", path=...)\n"
        "  - Write         → file_ops(action=\"write\", path=..., content=...)\n"
        "  - Edit          → file_ops(action=\"write\", ...) 整文件覆写（无 edit 模式）\n"
        "  - Glob          → **glob(pattern=\"**/*.py\", path=...)** ← 原生工具\n"
        "                    跨平台；一次拿完整匹配列表;支持 `**`、`*`、`?`、`[...]`\n"
        "                    例: glob(pattern=\"paimon/**/*.py\") 拿 paimon 子树所有 py\n"
        "  - Grep          → exec(command=...) 按当前平台见下方「执行环境」\n"
        "  - Bash(*)       → exec(command=...) 按当前平台见下方「执行环境」\n"
        "  - AskUserQuestion → 不可用（非交互模式本来就不需要）\n"
        "\n"
        f"## 执行环境（重要 — 决定你能用哪些命令）\n"
        f"{platform_hint}\n"
        "\n"
        "## 执行约束\n"
        "- 参数模式 = 零交互，不要等用户答复，直接执行\n"
        "- ${CLAUDE_SKILL_DIR} 已被替换成 skill 绝对路径，Read references/* 直接读即可\n"
        "- 若某轮扫描出错，记录到 state.json errors 字段后继续，不中止\n"
        "- 所有 finding 都要完整写入 candidates.jsonl（每行 JSON）\n"
        "\n"
        "## 优先级原则（LLM 执行时必记）\n"
        "1. **按模式找文件 → glob(pattern=...)**（最常用，递归、跨平台）\n"
        "2. **列单层目录 → file_ops(action=\"list\", path=...)**\n"
        "3. **读文件 → file_ops(action=\"read\", path=...)**（不要 exec cat）\n"
        "4. **写文件 → file_ops(action=\"write\", ...)**（不要 exec echo/heredoc）\n"
        "5. **exec 只用于**: 运行单个 python 脚本、跑测试命令等 file_ops/glob 办不到的活\n"
        "\n"
        "这是 paimon 内部体检，不是用户交互；最终输出只要简短 severity 统计即可，"
        "真正的产物由 paimon 从 .check/ 目录读取归档。"
    )
    user_msg = (
        f"请按参数模式调用 check skill：\n\n"
        f"```\ncheck {args}\n```\n\n"
        "严格遵循 SKILL.md 第一步「参数模式」→ 第二步初始化 → 第三步执行 → "
        "第四步生成报告的完整流程。\n"
        "\n"
        "### 立即执行的第一个工具调用\n"
        "请**立刻**调用 paimon 的 `glob` 工具拿项目 Python 文件列表：\n\n"
        "```json\n"
        "tool_name: glob\n"
        "arguments: {\n"
        f'  "pattern": "paimon/**/*.py",\n'
        f'  "path": "{project_root}"\n'
        "}\n"
        "```\n"
        "然后按返回的文件列表分组扫描。**不要**用 exec/python/find 等替代 —— "
        "glob 是为此专门提供的工具。\n"
        "\n"
        "**关键产物**：candidates.jsonl（finding 原始数据，每行 JSON）+ "
        "report.md（汇总报告）+ state.json（执行状态）——必须都写到 "
        f"{project_root}/.check/。\n"
        "\n"
        "执行完毕后只要用一两行汇总 severity 计数即可（P0=? P1=? P2=? P3=?），"
        "paimon 会自己读 .check/ 里的产物做持久化。"
    )
    await archon._invoke_skill_workflow(
        skill_name="check",
        user_message=user_msg,
        model=svc._model,
        session_name=f"selfcheck-deep-{int(time.time())}",
        component="三月·自检",
        purpose="Deep·code-health",
        allowed_tools={"file_ops", "glob", "exec"},
        framing=framing,
    )


async def _notify_deep_result(
    svc: "SelfCheckService", run_id: str,
    sev: dict[str, int], total: int, duration: float,
) -> None:
    """Deep 完成后推📨 推送（失败静默）。"""
    if not svc._march:
        return
    try:
        from paimon.state import state
        webui = state.channels.get("webui")
        if not webui:
            return
        from paimon.channels.webui.channel import PUSH_CHAT_ID
        head = "🩺" if sev["P0"] == 0 else "🚨"
        msg = (
            f"{head} Deep 自检完成 run={run_id[:8]}\n"
            f"  耗时 {duration:.0f}s · 共 {total} 条\n"
            f"  P0={sev['P0']} P1={sev['P1']} P2={sev['P2']} P3={sev['P3']}\n"
            f"  详情 → /selfcheck"
        )
        await svc._march.ring_event(
            channel_name="webui", chat_id=PUSH_CHAT_ID,
            source="三月·自检", message=msg,
        )
    except Exception as e:
        logger.debug("[三月·自检·Deep] 推送失败（静默）: {}", e)


async def mark_deep_failed(
    svc: "SelfCheckService", run_id: str, t0: float, reason: str,
) -> None:
    """Deep 任何失败路径的统一收尾：写 failed 状态 + audit。"""
    duration = time.time() - t0
    try:
        await svc._irminsul.selfcheck_update(
            run_id, actor="三月·自检",
            status="failed", error=reason[:500],
            duration_seconds=duration,
        )
        await svc._irminsul.audit_append(
            event_type="selfcheck_deep_failed",
            payload={
                "run_id": run_id,
                "reason": reason[:500],
                "duration_seconds": round(duration, 2),
            },
            actor="三月·自检",
        )
    except Exception as e:
        logger.error("[三月·自检·Deep] 标失败记录本身失败: {}", e)
