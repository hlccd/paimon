"""死执·self_check — 静态质量门（py_compile + ruff + pytest），写 self-check.log。

stage 归属：自检本身不是独立 stage，是 produce_code / simple_run(simple_code) 路径
内部调用的"即时反馈"（生执自调），同时 review_code 时死执也独立调一次（独立判定）。

概念上归死执（"质量门"），代码层无主公共 helper。
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path


async def run_self_check(workspace: Path) -> dict:
    """py_compile + ruff + pytest（auto-detect）。

    返回 {ok: bool, log: str, details: {...}}
    """
    workspace = workspace.resolve()
    code_dir = workspace / "code"
    log_path = workspace / "self-check.log"
    lines: list[str] = []
    details: dict = {}
    ok = True

    py_files = sorted(code_dir.rglob("*.py"))

    # 1. py_compile
    lines.append("=== py_compile ===")
    if not py_files:
        lines.append("SKIPPED (无 .py 文件)")
        details["py_compile"] = "skipped"
    else:
        args = [sys.executable, "-m", "py_compile"] + [str(p) for p in py_files]
        rc, out, err = await _run_subprocess(args, cwd=workspace)
        if rc == 0:
            lines.append(f"OK ({len(py_files)} files)")
            details["py_compile"] = "ok"
        else:
            lines.append(f"FAIL\n{out}\n{err}")
            details["py_compile"] = "fail"
            ok = False

    # 2. ruff check
    lines.append("\n=== ruff check ===")
    ruff = shutil.which("ruff")
    if not ruff:
        lines.append("SKIPPED (ruff 未安装)")
        details["ruff"] = "skipped"
    elif not py_files:
        lines.append("SKIPPED (无 .py 文件)")
        details["ruff"] = "skipped"
    else:
        rc, out, err = await _run_subprocess([ruff, "check", str(code_dir)], cwd=workspace)
        if rc == 0:
            lines.append("OK")
            details["ruff"] = "ok"
        else:
            lines.append(f"WARN\n{out}\n{err}")
            details["ruff"] = "warn"  # ruff warn 不算 fail

    # 3. pytest
    lines.append("\n=== pytest ===")
    tests_dir = code_dir / "tests"
    if not tests_dir.exists() or not any(tests_dir.rglob("test_*.py")):
        lines.append("SKIPPED (无 tests/test_*.py)")
        details["pytest"] = "skipped"
    else:
        rc, out, err = await _run_subprocess(
            [sys.executable, "-m", "pytest", str(tests_dir), "-x", "--tb=short"],
            cwd=workspace,
        )
        if rc == 0:
            lines.append("OK")
            details["pytest"] = "ok"
        else:
            lines.append(f"FAIL\n{out}\n{err}")
            details["pytest"] = "fail"
            ok = False

    # 总结
    lines.append("\n=== 总结 ===")
    lines.append(f"文件数: {len(py_files)}")
    lines.append(f"状态: {'✅ 全过' if ok else '⚠️ 未通过'}")

    log_text = "\n".join(lines)
    log_path.write_text(log_text, encoding="utf-8")

    return {"ok": ok, "log": log_text, "details": details}


async def _run_subprocess(args: list[str], *, cwd: Path) -> tuple[int, str, str]:
    """跑 subprocess，超时 3 分钟；返回 (rc, stdout, stderr) 截断后。"""
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=180)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", "TIMEOUT > 180s"
    out = (out_b or b"").decode("utf-8", "ignore")[:4000]
    err = (err_b or b"").decode("utf-8", "ignore")[:4000]
    return proc.returncode or 0, out, err
