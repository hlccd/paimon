"""水神 · Furina — 戏剧·评审

成品评审（方案/文档/代码/架构挑刺）。质量终审官。
专属工具：file_ops（只读）、use_skill（调 check skill 做严格审查）。

四影管线 review 阶段入口：
- `review_spec()` — 调 check skill 审 spec.md（spec 模式）
- `review_design()` — 调 check 对齐 spec ↔ design
- `review_code()` — 调 check 对齐 design ↔ code
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

    # ============ 四影管线 review 阶段入口（调 check skill）============

    async def review_spec(
        self, *, spec_path: Path, workspace: Path, model: Model,
        subtask_id: str = "",
    ) -> "ReviewVerdict":
        """审 spec.md；check --level=core --depth=quick（只挑 P0/P1 严重问题，快速单轮）。"""
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
        """审 design.md；core + quick 档位。"""
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
        subtask_id: str = "",
    ) -> "ReviewVerdict":
        """审 code 对齐 design；core + quick 档位（每阶段 N+M+K 多轮成本过高，MVP 用快速档位）。"""
        return await self._run_check_and_parse(
            check_args=f"code-vs-spec {code_dir} --spec {design_path} --level core --depth quick --fix report-only",
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
