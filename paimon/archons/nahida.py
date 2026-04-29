"""草神 · Nahida — 智慧·文书

推理、知识整合、文书起草、偏好管理。
专属工具：knowledge（知识库）、memory（记忆）、exec（通用）。

四影管线 spec 阶段入口：`write_spec()` — 调 requirement-spec skill 产出 spec.md。
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
你是草神·纳西妲，掌管智慧与知识。

能力：
1. 深度推理和分析
2. 通过 knowledge 工具读写知识库（按 category/topic 组织的结构化知识）
3. 通过 memory 工具管理跨会话记忆（用户偏好、项目事实、行为反馈等）
4. 通过 exec 执行命令获取信息

规则：
1. 当前项目路径是 {project_root}
2. 需要持久化的知识用 knowledge 工具写入，不要用 exec 写文件
3. 需要记住的用户偏好/反馈用 memory 工具写入
4. **写入 memory 前先用 memory list / search 看看已有记录，避免重复或覆盖**
5. 调用工具时不要输出过程描述，只输出最终结果
"""


class NahidaArchon(Archon):
    name = "草神"
    description = "推理、知识整合、文书起草"
    allowed_tools = {"knowledge", "memory", "exec"}

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[草神] 执行子任务: {}", subtask.description[:80])

        # 四影管线 spec 阶段分派
        if subtask.description.startswith("[STAGE:spec]"):
            from paimon.foundation.task_workspace import create_workspace
            workspace = create_workspace(task.id)
            # revise 轮优先用 description 内嵌的 issues（确定性通道）
            prior_issues = (
                _extract_issues_from_description(subtask.description)
                or _extract_prior_issues(prior_results)
            )
            spec_path = await self.write_spec(
                requirement=f"{task.title}\n{task.description}",
                workspace=workspace, model=model,
                prior_issues=prior_issues,
            )
            size_kb = spec_path.stat().st_size / 1024 if spec_path.exists() else 0
            result = f"spec 已产出: {spec_path}（{size_kb:.1f} KB）"
            await irminsul.progress_append(
                task_id=task.id, agent="草神", progress_pct=100,
                message=result[:200], subtask_id=subtask.id, actor="草神",
            )
            return result

        from paimon.archons.base import FINAL_OUTPUT_RULE
        system = _SYSTEM_PROMPT.format(project_root=self._project_root())
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"
        system += await self._load_feedback_memories_block(irminsul)
        system += FINAL_OUTPUT_RULE

        temp_session = Session(id=f"nahida-{task.id[:8]}", name="草神执行")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="草神", purpose="推理执行",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="草神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="草神",
        )
        logger.info("[草神] 子任务完成, 结果长度={}", len(result))
        return result

    # ============ 四影管线 spec 阶段入口 ============

    async def write_spec(
        self, *, requirement: str, workspace: Path, model: Model,
        project_context: str = "", prior_issues: list[dict] | None = None,
    ) -> Path:
        """调 requirement-spec skill 产出 {workspace}/spec.md。

        revise 轮 prior_issues 带上水神挑出的 findings。
        """
        workspace = workspace.resolve()
        spec_path = workspace / "spec.md"
        logger.info("[草神·spec] 产出到 {}", spec_path)

        # 组装 user_message（YAML 契约块）
        user_parts = [
            "调用 requirement-spec skill，按它的规范产出 spec.md。\n",
            "```yaml",
            f"requirement: |\n  {requirement.replace(chr(10), chr(10) + '  ')}",
            f"workspace: {workspace}/",
        ]
        if project_context:
            user_parts.append(
                f"project_context: |\n  {project_context.replace(chr(10), chr(10) + '  ')}",
            )
        if prior_issues:
            user_parts.append("prior_issues:")
            for it in prior_issues[:20]:
                user_parts.append(_fmt_issue_yaml(it))
        user_parts.append("```")
        user_msg = "\n".join(user_parts)

        await self._invoke_skill_workflow(
            skill_name="requirement-spec",
            user_message=user_msg,
            model=model,
            session_name=workspace.name,
            component="草神",
            purpose="写产品方案",
            allowed_tools={"file_ops"},
            framing=(
                f"【四影管线·spec 阶段】workspace={workspace}/\n"
                f"产物必须写到: {spec_path}\n"
                "只用 file_ops 工具（read/write）；不要 exec。"
            ),
        )

        if not spec_path.exists():
            logger.warning("[草神·spec] LLM 未产出 spec.md，写兜底占位")
            spec_path.write_text(
                f"# spec\n\n## 背景\n需求：{requirement[:200]}\n\n"
                "（LLM 未产出完整 spec，此为兜底占位）\n",
                encoding="utf-8",
            )
        return spec_path


def _fmt_issue_yaml(it: dict) -> str:
    """把单个 issue 格式化为 YAML block（安全转义 reason/suggestion 里的引号）。

    用 YAML single-quote string 包裹（`'text'`），内部 `'` 按 YAML 约定 double 成 `''`；
    这样 reason/suggestion 里含 `"` 不会破坏 YAML 结构。
    """
    sev = str(it.get("severity", "P2"))
    reason = str(it.get("reason", ""))[:200].replace("\n", " ")
    sugg = str(it.get("suggestion", ""))[:200].replace("\n", " ")
    # 用 single-quote 包裹 + 内部 `'` 替换为 `''`（YAML 约定）
    reason_esc = reason.replace("'", "''")
    sugg_esc = sugg.replace("'", "''")
    return (
        f"  - severity: {sev}\n"
        f"    reason: '{reason_esc}'\n"
        f"    suggestion: '{sugg_esc}'"
    )


def _extract_issues_from_description(desc: str) -> list[dict]:
    """从 subtask.description 里抽 `[REVISE_FEEDBACK_JSON]...[/REVISE_FEEDBACK_JSON]` 块。

    这是生执在 revise 轮直接嵌的确定性反馈通道；优先于 prior_results 链路抽取。
    """
    if not desc or "[REVISE_FEEDBACK_JSON]" not in desc:
        return []
    import json
    start_marker = "[REVISE_FEEDBACK_JSON]"
    end_marker = "[/REVISE_FEEDBACK_JSON]"
    i = desc.find(start_marker)
    if i < 0:
        return []
    j = desc.find(end_marker, i + len(start_marker))
    if j < 0:
        return []
    blob = desc[i + len(start_marker):j].strip()
    try:
        obj = json.loads(blob)
        if isinstance(obj, dict) and isinstance(obj.get("issues"), list):
            return obj["issues"][:20]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _extract_prior_issues(prior_results: list[str] | None) -> list[dict]:
    """从 prior_results（上游水神节点的 result 文本）里抽 verdict JSON 的 issues。

    水神 review_* 的 result 文本形如：
      {summary}\\n\\n```json\\n{...verdict...}\\n```

    用通用的"平衡花括号扫描"提取 JSON 块（同 _verdict.py 的 _extract_json_block 风格）。
    """
    if not prior_results:
        return []
    import json
    for txt in prior_results:
        if not txt or '"level"' not in txt or '"issues"' not in txt:
            continue
        # 找所有可能的 JSON 块（平衡 {}）
        for start in range(len(txt)):
            if txt[start] != "{":
                continue
            depth = 0
            for i in range(start, len(txt)):
                c = txt[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(txt[start : i + 1])
                        except (json.JSONDecodeError, ValueError):
                            obj = None
                        if (
                            isinstance(obj, dict)
                            and "level" in obj
                            and isinstance(obj.get("issues"), list)
                        ):
                            return obj["issues"][:20]
                        break
    return []
