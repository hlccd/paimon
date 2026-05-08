"""死执·review — 评审产物质量（review_spec / review_design / review_code）。

双路径：
- light：产物小（spec/design < 2000 字，code < 200 行）走一次 LLM JSON 输出
- heavy：调 check skill，解析 .check/candidates.jsonl 写 *.check.json + 返 ReviewVerdict

产出 .check.json schema 是 pipeline `_resolve_verdict` / find_last_verdict_producer
读取的协议（field：level / summary / issues）。

stage 归属：review_spec / review_design / review_code → 死执 review_*
"""
from __future__ import annotations

import json
import shutil as _shutil
from pathlib import Path

from loguru import logger

from paimon.shades._helpers.runner_helpers import invoke_skill_workflow

# 轻量 review 阈值
_LIGHT_REVIEW_DOC_CHAR_THRESHOLD = 2000
_LIGHT_REVIEW_CODE_LINE_THRESHOLD = 200

# code 目录"轻量判定"统计文件扩展名
_CODE_EXTENSIONS = (".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp", ".c", ".h", ".hpp")

_LIGHT_REVIEW_SYSTEM = """\
你负责评审者，对产物做严格但快速的 review。
按 P0/P1/P2/P3 分级输出 findings，**只关心质量问题，不要泛泛赞美**。

严重度定义：
- P0 致命：语法错误 / 功能不可用 / 安全漏洞 / 与 prior 严重偏离 → redo
- P1 关键：逻辑错误 / 测试缺失 / 明显可用性问题 → revise
- P2 次要：代码风格 / 小 bug 影响体验但不阻塞
- P3 建议：可选优化 / 命名改进

**严格输出 JSON（不要 markdown fence、不要解释）**：
{"findings":[{"severity":"P0|P1|P2|P3","description":"具体问题定位+原因"}],"summary":"一句话总评"}

findings 可为空数组（产物确实合格）；有问题必须列出至少一条。
"""


def _measure_doc_chars(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return 0


def _measure_code_lines(code_dir: Path) -> int:
    if not code_dir.is_dir():
        return 0
    total = 0
    for ext in _CODE_EXTENSIONS:
        for f in code_dir.rglob(f"*{ext}"):
            try:
                total += len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
            except OSError:
                continue
    return total


def _should_use_lightweight_review(
    stage: str,
    *,
    spec_path: Path | None = None,
    design_path: Path | None = None,
    code_dir: Path | None = None,
) -> tuple[bool, str]:
    if stage == "review_spec" and spec_path is not None:
        n = _measure_doc_chars(spec_path)
        if 0 < n < _LIGHT_REVIEW_DOC_CHAR_THRESHOLD:
            return True, f"spec.md {n} 字符 < {_LIGHT_REVIEW_DOC_CHAR_THRESHOLD}"
        return False, f"spec.md {n} 字符"
    if stage == "review_design" and design_path is not None:
        n = _measure_doc_chars(design_path)
        if 0 < n < _LIGHT_REVIEW_DOC_CHAR_THRESHOLD:
            return True, f"design.md {n} 字符 < {_LIGHT_REVIEW_DOC_CHAR_THRESHOLD}"
        return False, f"design.md {n} 字符"
    if stage == "review_code" and code_dir is not None:
        n = _measure_code_lines(code_dir)
        if 0 < n < _LIGHT_REVIEW_CODE_LINE_THRESHOLD:
            return True, f"code {n} 行 < {_LIGHT_REVIEW_CODE_LINE_THRESHOLD}"
        return False, f"code {n} 行"
    return False, f"stage {stage} 无法判定"


async def _lightweight_review(
    *,
    stage: str,
    target_content: str,
    prior_context: str,
    model,
    subtask_id: str,
    task_id: str,
):
    """一次 LLM 调用做 review，解析成 ReviewVerdict。"""
    from paimon.shades._verdict import (
        LEVEL_PASS, LEVEL_REDO, LEVEL_REVISE, ReviewVerdict,
    )

    user_parts = [f"# 待审 stage: {stage}\n"]
    if prior_context:
        user_parts.append(f"## prior（对齐基准，只读）\n\n{prior_context[:4000]}\n")
    user_parts.append(f"## target\n\n{target_content[:8000]}\n")

    messages = [
        {"role": "system", "content": _LIGHT_REVIEW_SYSTEM},
        {"role": "user", "content": "\n".join(user_parts)},
    ]

    try:
        raw, usage = await model._stream_text(
            messages, component="死执", purpose=f"lightweight·{stage}",
        )
        await model._record_primogem(
            task_id, "死执", usage, purpose=f"lightweight·{stage}",
        )
    except Exception as e:
        # LLM 失败保守 revise（让生执继续完善）
        logger.error("[死执·{}·轻量] LLM 失败: {} → 保守 revise", stage, e)
        return ReviewVerdict(
            level=LEVEL_REVISE, issues=[],
            summary=f"{stage}(轻量): LLM 调用失败，保守 revise",
        )

    # 解析 JSON（容错剥 fence）
    raw = (raw or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 2:
            raw = "\n".join(lines[1:-1]).strip()

    findings = []
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            findings = obj.get("findings") or []
    except Exception as e:
        logger.warning(
            "[死执·{}·轻量] JSON 解析失败: {} raw={!r}",
            stage, e, raw[:200],
        )

    sev_count = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    issues: list[dict] = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        sev = f.get("severity", "P3")
        if sev not in sev_count:
            sev = "P3"
        sev_count[sev] += 1
        issues.append({
            "severity": sev,
            "reason": (f.get("description") or "")[:300],
            "suggestion": "",
            "subtask_id": subtask_id,
        })

    if sev_count["P0"] > 0:
        level = LEVEL_REDO
    elif sev_count["P1"] > 0:
        level = LEVEL_REVISE
    else:
        level = LEVEL_PASS

    summary = (
        f"{stage}(轻量): {sev_count['P0']} P0 / {sev_count['P1']} P1 / "
        f"{sev_count['P2']} P2 / {sev_count['P3']} P3"
    )
    logger.info("[死执·{}·轻量] verdict={} {}", stage, level, summary)
    return ReviewVerdict(level=level, issues=issues[:20], summary=summary)


async def _run_check_skill_and_parse(
    *,
    check_args: str,
    workspace: Path,
    model,
    stage_name: str,
    subtask_id: str,
    result_json_name: str,
):
    """调 check skill（参数模式）→ 解析 .check/candidates.jsonl → ReviewVerdict。"""
    workspace = workspace.resolve()
    logger.info("[死执·{}] 调 check: {}", stage_name, check_args[:100])

    # 清旧 .check/ 防读到上轮 candidates
    for old in list(workspace.rglob(".check")):
        if old.is_dir():
            _shutil.rmtree(old, ignore_errors=True)

    user_msg = (
        f"请调用 check skill，命令参数如下（非交互模式）：\n\n"
        f"`check {check_args}`\n\n"
        "skill 跑完后把 candidates.jsonl + report.md 留在目标路径的 .check/ 目录。"
        "你读出 candidates.jsonl 的 CONFIRMED findings 汇总给我（按 severity 分组计数 + 前 10 条摘要），"
        "不需要你生成 verdict JSON——返回文本给我即可。"
    )

    await invoke_skill_workflow(
        skill_name="check",
        user_message=user_msg,
        model=model,
        session_name=f"{workspace.name}-{stage_name}",
        component="死执",
        purpose=f"check·{stage_name}",
        allowed_tools={"file_ops", "glob", "exec"},
        framing=(
            f"【四影管线·{stage_name} 阶段】workspace={workspace}/\n"
            "这是 paimon 内部调用，不是用户交互；check skill 已有参数模式支持。"
        ),
    )

    return _parse_candidates_to_verdict(
        workspace=workspace,
        subtask_id=subtask_id,
        stage_name=stage_name,
        result_json_name=result_json_name,
    )


def _parse_candidates_to_verdict(
    *,
    workspace: Path,
    subtask_id: str,
    stage_name: str,
    result_json_name: str,
):
    """扫描 workspace 下所有 .check/candidates.jsonl，汇总 findings 写 *.check.json。"""
    from paimon.shades._check_parser import (
        count_severity, findings_to_issues, parse_candidates_tree,
    )
    from paimon.shades._verdict import (
        LEVEL_PASS, LEVEL_REDO, LEVEL_REVISE, ReviewVerdict,
    )

    findings = parse_candidates_tree(workspace)
    sev_count = count_severity(findings)

    if sev_count["P0"] > 0:
        level = LEVEL_REDO
    elif sev_count["P1"] > 0:
        level = LEVEL_REVISE
    else:
        level = LEVEL_PASS

    issues = findings_to_issues(findings, subtask_id=subtask_id, limit=20)
    summary = (
        f"{stage_name}: {sev_count['P0']} P0 / {sev_count['P1']} P1 / "
        f"{sev_count['P2']} P2 / {sev_count['P3']} P3"
    )

    # 落 *.check.json 给时执 summary 读
    out_path = workspace / result_json_name
    try:
        out_path.write_text(
            json.dumps({
                "level": level,
                "severity_counts": sev_count,
                "issues": issues,
                "summary": summary,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("[死执·{}] 写 {} 失败: {}", stage_name, result_json_name, e)

    logger.info("[死执·{}] verdict={} {}", stage_name, level, summary)
    return ReviewVerdict(level=level, issues=issues, summary=summary)


# ─────────────────────────────────────────────────────────────────────────────
# 公开入口（runner.py 路由 stage=review_* 时调）
# ─────────────────────────────────────────────────────────────────────────────

async def run_review_spec(
    *, spec_path: Path, workspace: Path, model, subtask_id: str = "",
):
    """审 spec.md。小文档 light，大文档 check skill。"""
    is_light, reason = _should_use_lightweight_review("review_spec", spec_path=spec_path)
    if is_light:
        logger.info("[死执·review_spec·轻量] 触发 ({})", reason)
        target = spec_path.read_text(encoding="utf-8", errors="ignore") if spec_path.is_file() else ""
        return await _lightweight_review(
            stage="review_spec",
            target_content=target,
            prior_context="",
            model=model,
            subtask_id=subtask_id,
            task_id=workspace.name,
        )
    return await _run_check_skill_and_parse(
        check_args=f"spec {spec_path} --level core --depth quick --fix report-only",
        workspace=workspace,
        model=model,
        stage_name="review_spec",
        subtask_id=subtask_id,
        result_json_name="spec.check.json",
    )


async def run_review_design(
    *, spec_path: Path, design_path: Path, workspace: Path, model, subtask_id: str = "",
):
    """审 design.md 对齐 spec。"""
    is_light, reason = _should_use_lightweight_review("review_design", design_path=design_path)
    if is_light:
        logger.info("[死执·review_design·轻量] 触发 ({})", reason)
        design_text = design_path.read_text(encoding="utf-8", errors="ignore") if design_path.is_file() else ""
        spec_text = spec_path.read_text(encoding="utf-8", errors="ignore") if spec_path.is_file() else ""
        return await _lightweight_review(
            stage="review_design",
            target_content=design_text,
            prior_context=spec_text,
            model=model,
            subtask_id=subtask_id,
            task_id=workspace.name,
        )
    return await _run_check_skill_and_parse(
        check_args=(
            f"spec {design_path} --level core --depth quick --fix report-only "
            f'--note "对齐 spec: {spec_path}"'
        ),
        workspace=workspace,
        model=model,
        stage_name="review_design",
        subtask_id=subtask_id,
        result_json_name="design.check.json",
    )


async def review(
    stage: str,
    task,
    subtask,
    model,
    irminsul,
    prior_results: list[str] | None = None,
) -> str:
    """死执·review 统一入口（asmoday 路由表调）。

    stage ∈ {review_spec, review_design, review_code}。返回文本（含 verdict JSON）
    给 pipeline `_resolve_verdict` 解析。
    """
    from paimon.foundation.task_workspace import create_workspace
    workspace = create_workspace(task.id).resolve()
    spec_path = workspace / "spec.md"
    design_path = workspace / "design.md"
    code_dir = workspace / "code"

    if stage == "review_spec":
        verdict = await run_review_spec(
            spec_path=spec_path, workspace=workspace, model=model,
            subtask_id=subtask.id,
        )
    elif stage == "review_design":
        verdict = await run_review_design(
            spec_path=spec_path, design_path=design_path, workspace=workspace,
            model=model, subtask_id=subtask.id,
        )
    elif stage == "review_code":
        # simple/trivial 无 design 时，用 task.description 作 fallback_requirement
        fallback = "" if design_path.is_file() else (task.description or "")
        verdict = await run_review_code(
            design_path=design_path, code_dir=code_dir, workspace=workspace,
            model=model, subtask_id=subtask.id,
            fallback_requirement=fallback,
        )
    else:
        return f"[死执·{stage}] 未知 review stage"

    # 把 ReviewVerdict 序列化到 result 文本（pipeline _resolve_verdict 读 JSON）
    verdict_dict = {
        "level": verdict.level,
        "issues": verdict.issues,
        "summary": verdict.summary,
    }
    return f"{verdict.summary}\n\n```json\n{json.dumps(verdict_dict, ensure_ascii=False, indent=2)}\n```"


async def run_review_code(
    *, design_path: Path, code_dir: Path, workspace: Path, model,
    subtask_id: str = "", fallback_requirement: str = "",
):
    """审 code 对齐 design。"""
    is_light, reason = _should_use_lightweight_review("review_code", code_dir=code_dir)
    if is_light:
        logger.info("[死执·review_code·轻量] 触发 ({})", reason)
        code_chunks: list[str] = []
        if code_dir.is_dir():
            for ext in _CODE_EXTENSIONS:
                for f in code_dir.rglob(f"*{ext}"):
                    try:
                        rel = f.relative_to(code_dir)
                        body = f.read_text(encoding="utf-8", errors="ignore")
                        code_chunks.append(f"### {rel}\n```\n{body}\n```\n")
                    except OSError:
                        continue
        code_text = "\n".join(code_chunks)
        if design_path.is_file():
            prior = design_path.read_text(encoding="utf-8", errors="ignore")
        elif fallback_requirement:
            prior = f"[原始用户需求]\n{fallback_requirement}"
        else:
            prior = ""
        return await _lightweight_review(
            stage="review_code",
            target_content=code_text,
            prior_context=prior,
            model=model,
            subtask_id=subtask_id,
            task_id=workspace.name,
        )

    # heavy：check skill
    align_spec = str(design_path) if design_path.is_file() else ""
    if not align_spec and fallback_requirement:
        req_file = workspace / "requirement.md"
        try:
            req_file.write_text(
                f"# 原始需求\n\n{fallback_requirement}\n", encoding="utf-8",
            )
            align_spec = str(req_file)
        except OSError as e:
            logger.warning("[死执·review_code] 写 requirement.md 失败: {}", e)
    check_args = (
        f"code-vs-spec {code_dir} --level core --depth quick --fix report-only"
        + (f" --spec {align_spec}" if align_spec else "")
    )
    return await _run_check_skill_and_parse(
        check_args=check_args,
        workspace=workspace,
        model=model,
        stage_name="review_code",
        subtask_id=subtask_id,
        result_json_name="code.check.json",
    )
