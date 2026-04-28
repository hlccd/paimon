"""水神 · Furina — 戏剧·评审

成品评审（方案/文档/代码/架构挑刺）。质量终审官。
专属工具：file_ops（只读）、use_skill（调 check skill 做严格审查）。

四影管线 review 阶段入口：
- `review_spec()` — 调 check skill 审 spec.md（spec 模式）
- `review_design()` — 调 check 对齐 spec ↔ design
- `review_code()` — 调 check 对齐 design ↔ code

按产物体量分档：小产物走**轻量 review**（一次 LLM 调用，不跑 check skill）；
大产物走**check skill 严格审查**（原路径）。阈值由 _LIGHT_REVIEW_* 常量控制。
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session


# 轻量 review 阈值：产物小于此值直接走一次 LLM（不跑 check skill）
# spec/design 是 markdown 文档，按字符数（≈ token 数 × 2~3）衡量
# code 目录按所有代码文件总行数衡量（常见 py/ts/js/go/rs 等）
_LIGHT_REVIEW_DOC_CHAR_THRESHOLD = 2000
_LIGHT_REVIEW_CODE_LINE_THRESHOLD = 200

# code 目录"轻量判定"时统计行数的文件扩展名
_CODE_EXTENSIONS = (".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp", ".c", ".h", ".hpp")


def _measure_doc_chars(path: Path) -> int:
    """文档字符数；文件不存在返回 0。"""
    if not path.is_file():
        return 0
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return 0


def _measure_code_lines(code_dir: Path) -> int:
    """code 目录所有代码文件总行数。目录不存在返回 0。"""
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
    """判定是否走轻量 review 路径。返回 (is_light, reason)。

    review_spec: 看 spec.md 字符数
    review_design: 看 design.md 字符数
    review_code: 看 code 目录所有代码文件总行数
    """
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


_LIGHT_REVIEW_SYSTEM = """\
你是水神·芙宁娜，对产物做严格但快速的 review。
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

_SYSTEM_PROMPT = """\
你是水神·芙宁娜，掌管戏剧与评审。你是质量终审官。

能力：
1. 严格评审方案/代码/文档/架构
2. 用 file_ops read 查看代码文件（只读，不修改）

评审规则：
1. 你的职责是审查和挑刺，不是生产内容
2. 指出问题要具体：位置、原因、改进建议
3. 不要客气，该挑刺就挑刺

**输出格式（硬性要求）**：
先简要说明评审过程（可选，≤200 字），然后在最后输出一个 JSON 对象作为终审结论。
JSON 必须严格按以下字段：

```json
{
  "level": "pass | revise | redo",
  "issues": [
    {"subtask_id": "xxx", "reason": "具体问题", "suggestion": "改进建议"}
  ],
  "summary": "总体评价（一句话）"
}
```

- level=pass: 没有明显问题，可以交付
- level=revise: 有问题但方向正确，局部修改即可（在 issues 里列出具体 subtask）
- level=redo: 严重问题/方向错误，需要整体重做
- issues 为空数组时仍需保留字段
- subtask_id 从"需要评审的内容"段落里对应节点的 id 提取；若无法归因到具体节点，留空字符串

只允许输出一段正文 + 一个 JSON 代码块；禁止多个 JSON。
"""


class FurinaArchon(Archon):
    name = "水神"
    description = "评审、游戏信息"
    allowed_tools = {"file_ops"}

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[水神] 执行子任务: {}", subtask.description[:80])

        # 四影管线 review 阶段分派（调 check skill）
        desc = subtask.description
        if desc.startswith(("[STAGE:review_spec]", "[STAGE:review_design]", "[STAGE:review_code]")):
            from paimon.foundation.task_workspace import get_workspace_path, create_workspace
            import json as _json
            workspace = create_workspace(task.id)
            spec_path = workspace / "spec.md"
            design_path = workspace / "design.md"
            code_dir = workspace / "code"

            # subtask_id 应指向被审的"生产节点"（deps[0]）而不是 review 节点自己，
            # 这样 issues 反映"生产节点 X 被挑出问题"，pipeline 回炉时 _plan_revise
            # 才能正确定位要重派的生产节点。
            reviewed_id = (subtask.deps or [None])[0] if subtask.deps else subtask.id

            if desc.startswith("[STAGE:review_spec]"):
                verdict = await self.review_spec(
                    spec_path=spec_path, workspace=workspace, model=model,
                    subtask_id=reviewed_id,
                )
            elif desc.startswith("[STAGE:review_design]"):
                verdict = await self.review_design(
                    spec_path=spec_path, design_path=design_path,
                    workspace=workspace, model=model, subtask_id=reviewed_id,
                )
            else:  # review_code
                verdict = await self.review_code(
                    design_path=design_path, code_dir=code_dir,
                    workspace=workspace, model=model, subtask_id=reviewed_id,
                    # simple/trivial DAG 无 design 阶段，传 task.description 作 prior 基准
                    fallback_requirement=task.description,
                )

            # 产物：文本 + 末尾 JSON（pipeline 的 _resolve_verdict 按 find_last_verdict_producer 解析）
            verdict_obj = {
                "level": verdict.level,
                "issues": verdict.issues,
                "summary": verdict.summary,
            }
            result = (
                f"{verdict.summary}\n\n"
                f"```json\n{_json.dumps(verdict_obj, ensure_ascii=False, indent=2)}\n```"
            )
            await irminsul.progress_append(
                task_id=task.id, agent="水神", progress_pct=100,
                message=verdict.summary[:200], subtask_id=subtask.id, actor="水神",
            )
            return result

        from paimon.archons.base import FINAL_OUTPUT_RULE
        system = _SYSTEM_PROMPT
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 需要评审的内容\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i} 产物\n{pr[:3000]}\n"
        system += FINAL_OUTPUT_RULE

        temp_session = Session(id=f"furina-{task.id[:8]}", name="水神评审")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="水神", purpose="评审",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="水神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="水神",
        )
        logger.info("[水神] 子任务完成, 结果长度={}", len(result))
        return result

    # ============ 轻量 review 路径（小产物不跑 check skill）============

    async def _lightweight_review(
        self,
        *,
        stage: str,
        target_content: str,
        prior_context: str,
        model: Model,
        subtask_id: str,
        task_id: str,
    ) -> "ReviewVerdict":
        """一次 LLM 调用做 review，解析成 ReviewVerdict。

        比 check skill 路径快 ~20 倍（单次 ~5-10s vs check skill ~200s）；
        适用于：spec.md / design.md < 2000 字符，code 总行数 < 200 行。
        不加载 check skill 的 references，不走 tool-loop。
        """
        from paimon.shades._verdict import (
            LEVEL_PASS, LEVEL_REDO, LEVEL_REVISE, ReviewVerdict,
        )

        user_parts = [f"# 待审 stage: {stage}\n"]
        if prior_context:
            user_parts.append(
                f"## prior（对齐基准，只读）\n\n{prior_context[:4000]}\n",
            )
        user_parts.append(f"## target\n\n{target_content[:8000]}\n")

        messages = [
            {"role": "system", "content": _LIGHT_REVIEW_SYSTEM},
            {"role": "user", "content": "\n".join(user_parts)},
        ]

        try:
            raw, usage = await model._stream_text(
                messages, component="水神", purpose=f"lightweight·{stage}",
            )
            await model._record_primogem(
                task_id, "水神", usage, purpose=f"lightweight·{stage}",
            )
        except Exception as e:
            logger.error("[水神·{}·轻量] LLM 调用失败: {} → 保守 pass", stage, e)
            return ReviewVerdict(
                level=LEVEL_PASS, issues=[],
                summary=f"{stage}(轻量): LLM 调用失败，保守 pass",
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
                "[水神·{}·轻量] JSON 解析失败: {} raw_preview={!r}",
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
        logger.info("[水神·{}·轻量] verdict={} {}", stage, level, summary)
        return ReviewVerdict(level=level, issues=issues[:20], summary=summary)

    # ============ 四影管线 review 阶段入口（调 check skill）============

    async def review_spec(
        self, *, spec_path: Path, workspace: Path, model: Model,
        subtask_id: str = "",
    ) -> "ReviewVerdict":
        """审 spec.md。小文档走轻量 LLM；大文档走 check skill core+quick 档。"""
        is_light, reason = _should_use_lightweight_review(
            "review_spec", spec_path=spec_path,
        )
        if is_light:
            logger.info("[水神·review_spec·轻量] 触发 ({})", reason)
            target = spec_path.read_text(encoding="utf-8", errors="ignore") if spec_path.is_file() else ""
            return await self._lightweight_review(
                stage="review_spec",
                target_content=target,
                prior_context="",
                model=model,
                subtask_id=subtask_id,
                task_id=workspace.name,
            )
        return await self._run_check_and_parse(
            check_args=f"spec {spec_path} --level core --depth quick --fix report-only",
            workspace=workspace,
            model=model,
            stage_name="review_spec",
            subtask_id=subtask_id,
            result_json_name="spec.check.json",
        )

    async def review_design(
        self, *, spec_path: Path, design_path: Path, workspace: Path, model: Model,
        subtask_id: str = "",
    ) -> "ReviewVerdict":
        """审 design.md 对齐 spec。小文档走轻量 LLM；大文档走 check skill。"""
        is_light, reason = _should_use_lightweight_review(
            "review_design", design_path=design_path,
        )
        if is_light:
            logger.info("[水神·review_design·轻量] 触发 ({})", reason)
            design_text = design_path.read_text(encoding="utf-8", errors="ignore") if design_path.is_file() else ""
            spec_text = spec_path.read_text(encoding="utf-8", errors="ignore") if spec_path.is_file() else ""
            return await self._lightweight_review(
                stage="review_design",
                target_content=design_text,
                prior_context=spec_text,
                model=model,
                subtask_id=subtask_id,
                task_id=workspace.name,
            )
        return await self._run_check_and_parse(
            check_args=f"spec {design_path} --level core --depth quick --fix report-only --note \"对齐 spec: {spec_path}\"",
            workspace=workspace,
            model=model,
            stage_name="review_design",
            subtask_id=subtask_id,
            result_json_name="design.check.json",
        )

    async def review_code(
        self, *, design_path: Path, code_dir: Path, workspace: Path, model: Model,
        subtask_id: str = "", fallback_requirement: str = "",
    ) -> "ReviewVerdict":
        """审 code 对齐 design。小代码走轻量 LLM；大代码走 check skill。

        simple/trivial DAG 无 design 阶段时，design_path 不存在 —— 用
        `fallback_requirement`（task.description）作对齐基准代替 design.md。
        """
        is_light, reason = _should_use_lightweight_review(
            "review_code", code_dir=code_dir,
        )
        if is_light:
            logger.info("[水神·review_code·轻量] 触发 ({})", reason)
            # 拼接所有代码文件（轻量路径上限 8KB target_content，够几个小文件）
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
            # prior 优先用 design.md；不存在则退回原始需求（simple/trivial DAG 场景）
            if design_path.is_file():
                prior = design_path.read_text(encoding="utf-8", errors="ignore")
            elif fallback_requirement:
                prior = f"[原始用户需求]\n{fallback_requirement}"
            else:
                prior = ""
            return await self._lightweight_review(
                stage="review_code",
                target_content=code_text,
                prior_context=prior,
                model=model,
                subtask_id=subtask_id,
                task_id=workspace.name,
            )
        # 重路径：check skill 对齐 design.md；若 design 不存在则用原始需求作为 --spec 降级
        align_spec = str(design_path) if design_path.is_file() else ""
        if not align_spec and fallback_requirement:
            # 临时把原始需求写进 workspace/requirement.md 给 check 当 spec
            req_file = workspace / "requirement.md"
            try:
                req_file.write_text(
                    f"# 原始需求\n\n{fallback_requirement}\n", encoding="utf-8",
                )
                align_spec = str(req_file)
            except OSError as e:
                logger.warning("[水神·review_code] 写 requirement.md 失败: {}", e)
        check_args = (
            f"code-vs-spec {code_dir} --level core --depth quick --fix report-only"
            + (f" --spec {align_spec}" if align_spec else "")
        )
        return await self._run_check_and_parse(
            check_args=check_args,
            workspace=workspace,
            model=model,
            stage_name="review_code",
            subtask_id=subtask_id,
            result_json_name="code.check.json",
        )

    async def _run_check_and_parse(
        self, *, check_args: str, workspace: Path, model: Model,
        stage_name: str, subtask_id: str, result_json_name: str,
    ) -> "ReviewVerdict":
        """调 check skill（参数模式）→ 解析 .check/candidates.jsonl → 组装 ReviewVerdict。"""
        import shutil as _shutil
        workspace = workspace.resolve()
        logger.info("[水神·{}] 调 check: {}", stage_name, check_args[:100])

        # 清 workspace 下所有旧 .check/ 目录（避免读到上轮 review 的旧 candidates）
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

        await self._invoke_skill_workflow(
            skill_name="check",
            user_message=user_msg,
            model=model,
            session_name=f"{workspace.name}-{stage_name}",
            component="水神",
            purpose=f"check·{stage_name}",
            allowed_tools={"file_ops", "glob", "exec"},
            framing=(
                f"【四影管线·{stage_name} 阶段】workspace={workspace}/\n"
                "这是 paimon 内部调用，不是用户交互；check skill 已有参数模式支持。"
            ),
        )

        # 读 .check/candidates.jsonl（check 在目标路径的父目录创建 .check/）
        verdict = self._parse_candidates_to_verdict(
            workspace=workspace,
            subtask_id=subtask_id,
            stage_name=stage_name,
            result_json_name=result_json_name,
        )
        return verdict

    def _parse_candidates_to_verdict(
        self, *, workspace: Path, subtask_id: str,
        stage_name: str, result_json_name: str,
    ) -> "ReviewVerdict":
        """扫描 workspace 下所有 .check/candidates.jsonl，汇总 findings。

        level 规则：P0>0 → redo；P1>0 → revise；其它 → pass。
        解析细节委托到 `paimon.shades._check_parser`（三月自检也复用同一解析器）。
        """
        # 延迟导入避免 shades → archons.furina 循环
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

        # 把结构化结果落盘到 workspace 根（供时执 summary 读）
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
            logger.warning("[水神·{}] 写 {} 失败: {}", stage_name, result_json_name, e)

        logger.info(
            "[水神·{}] verdict={} {}",
            stage_name, level, summary,
        )
        return ReviewVerdict(level=level, issues=issues, summary=summary)
