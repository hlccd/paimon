"""雷神 · Raiden — 永恒·造物

写代码（含自检）。专属工具：file_ops（结构化文件读写）、exec（跑测试/lint）。

四影管线 design/code 阶段入口：
- `write_design()` — 调 architecture-design skill 产出 design.md
- `write_code()` — 调 code-implementation skill 产出 code/ + self-check.log
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session

_SYSTEM_PROMPT = """\
你是雷神·巴尔泽布，掌管永恒与造物。你的职责是写代码。

能力：
1. 用 file_ops 工具读写文件（read/write/list/exists）
2. 用 exec 工具运行测试、lint 验证代码
3. 写完代码后必须自检

规则：
1. 当前项目路径是 {project_root}
2. 用 file_ops write 写文件，不要用 exec echo
3. 写完后用 exec 跑测试或检查语法
4. 输出结构化结果：文件路径 + 代码要点 + 自检结论
5. 调用工具时不要输出过程描述，只输出最终结果
"""


class RaidenArchon(Archon):
    name = "雷神"
    description = "代码生成、自检"
    allowed_tools = {"file_ops", "exec"}

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[雷神] 执行子任务: {}", subtask.description[:80])

        # 四影管线 design / code 阶段分派
        if subtask.description.startswith("[STAGE:design]"):
            from paimon.archons.nahida import _extract_prior_issues
            from paimon.foundation.task_workspace import create_workspace
            workspace = create_workspace(task.id)
            spec_path = workspace / "spec.md"
            from paimon.archons.nahida import _extract_issues_from_description
            prior_issues = (
                _extract_issues_from_description(subtask.description)
                or _extract_prior_issues(prior_results)
            )
            design_path = await self.write_design(
                spec_path=spec_path, workspace=workspace, model=model,
                prior_issues=prior_issues,
            )
            size_kb = design_path.stat().st_size / 1024 if design_path.exists() else 0
            result = f"design 已产出: {design_path}（{size_kb:.1f} KB）"
            await irminsul.progress_append(
                task_id=task.id, agent="雷神", progress_pct=100,
                message=result[:200], subtask_id=subtask.id, actor="雷神",
            )
            return result

        if subtask.description.startswith("[STAGE:code]"):
            from paimon.foundation.task_workspace import create_workspace
            workspace = create_workspace(task.id)
            spec_path = workspace / "spec.md"
            design_path = workspace / "design.md"

            # spec.md / design.md 都存在 → complex DAG，调 code-implementation skill
            # 否则（simple/trivial DAG 没 spec/design 节点）→ skill 拿不到 spec/design
            # 会兜圈 15 轮 LLM 强制收尾产 0 文件；走 LLM 直写绕开
            if spec_path.exists() and design_path.exists():
                from paimon.archons.nahida import (
                    _extract_issues_from_description, _extract_prior_issues,
                )
                prior_issues = (
                    _extract_issues_from_description(subtask.description)
                    or _extract_prior_issues(prior_results)
                )
                code_result = await self.write_code(
                    spec_path=spec_path, design_path=design_path,
                    workspace=workspace, model=model, prior_issues=prior_issues,
                )
                files = code_result.get("files", [])
                sc = code_result.get("self_check", {})
                ok = sc.get("ok", False)
                result = (
                    f"code 已产出: {len(files)} 个文件到 {workspace}/code/\n"
                    f"自检: {'✅ 全过' if ok else '⚠️ 未通过'} (详见 self-check.log)"
                )
            else:
                # simple/trivial 路径：不调 skill，LLM 直接写到 workspace/code/
                logger.info(
                    "[雷神·code] simple/trivial 路径（spec/design 不存在），LLM 直写到 {}",
                    workspace / "code",
                )
                result = await self._write_code_simple(
                    task, subtask, workspace, model, irminsul, prior_results,
                )
            await irminsul.progress_append(
                task_id=task.id, agent="雷神", progress_pct=100,
                message=result[:200], subtask_id=subtask.id, actor="雷神",
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

        temp_session = Session(id=f"raiden-{task.id[:8]}", name="雷神执行")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="雷神", purpose="代码生成",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="雷神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="雷神",
        )
        logger.info("[雷神] 子任务完成, 结果长度={}", len(result))
        return result

    # ============ 四影管线 code 简易路径（simple/trivial DAG 无 spec/design）============

    async def _write_code_simple(
        self, task: TaskEdict, subtask: Subtask, workspace: Path,
        model: Model, irminsul: Irminsul,
        prior_results: list[str] | None,
    ) -> str:
        """simple/trivial DAG 的 code 节点：不调 code-implementation skill，
        直接 LLM + file_ops/exec 工具产出到 workspace/code/，跑同款 self_check。
        """
        from paimon.archons.base import FINAL_OUTPUT_RULE

        code_dir = workspace / "code"
        code_dir.mkdir(parents=True, exist_ok=True)

        system = _SYSTEM_PROMPT.format(project_root=self._project_root())
        system += (
            f"\n\n## 当前任务\n{task.title}\n"
            f"\n## 你的子任务\n{subtask.description[:500]}\n"
            f"\n## 输出目录（必须）\n"
            f"代码必须用 file_ops write 写到 {code_dir}/\n"
            f"路径规则: {code_dir}/<相对路径> = 宿主项目对应文件\n"
            f"写完后用 exec 跑 py_compile/ruff/pytest 自检（错了继续修）\n"
        )
        if prior_results:
            system += "\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"
        system += await self._load_feedback_memories_block(irminsul)
        system += FINAL_OUTPUT_RULE

        temp_session = Session(id=f"raiden-{task.id[:8]}", name="雷神·code(简易)")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="雷神", purpose="代码生成(简易)",
        ):
            pass

        check_result = await self.self_check(workspace)

        from paimon.foundation.task_workspace import list_workspace_files
        files = [
            str(p.relative_to(code_dir))
            for p in list_workspace_files(workspace.name)
        ]

        ok = check_result.get("ok", False)
        return (
            f"code 已产出: {len(files)} 个文件到 {workspace}/code/\n"
            f"自检: {'✅ 全过' if ok else '⚠️ 未通过'} (详见 self-check.log)"
        )

    # ============ 四影管线 design 阶段入口 ============

    async def write_design(
        self, *, spec_path: Path, workspace: Path, model: Model,
        project_context: str = "", prior_issues: list[dict] | None = None,
    ) -> Path:
        """调 architecture-design skill 产出 {workspace}/design.md。"""
        workspace = workspace.resolve()
        design_path = workspace / "design.md"
        logger.info("[雷神·design] 产出到 {}", design_path)

        user_parts = [
            "调用 architecture-design skill，按它的规范产出 design.md。\n",
            "```yaml",
            f"spec_path: {spec_path}",
            f"workspace: {workspace}/",
            f"project_root: {self._project_root()}/",
        ]
        if project_context:
            user_parts.append(
                f"project_context: |\n  {project_context.replace(chr(10), chr(10) + '  ')}",
            )
        if prior_issues:
            from paimon.archons.nahida import _fmt_issue_yaml
            user_parts.append("prior_issues:")
            for it in prior_issues[:20]:
                user_parts.append(_fmt_issue_yaml(it))
        user_parts.append("```")
        user_msg = "\n".join(user_parts)

        await self._invoke_skill_workflow(
            skill_name="architecture-design",
            user_message=user_msg,
            model=model,
            session_name=workspace.name,
            component="雷神",
            purpose="写技术方案",
            allowed_tools={"file_ops"},
            framing=(
                f"【四影管线·design 阶段】\n产物写到: {design_path}\n"
                f"读 spec: {spec_path}\n"
                f"project_root: {self._project_root()}/（只读参考，不要写）"
            ),
        )

        if not design_path.exists():
            logger.warning("[雷神·design] LLM 未产出 design.md，写兜底占位")
            design_path.write_text(
                "# 技术方案\n\n（LLM 未产出 design.md，此为兜底占位）\n",
                encoding="utf-8",
            )
        return design_path

    # ============ 四影管线 code 阶段入口 ============

    async def write_code(
        self, *, spec_path: Path, design_path: Path, workspace: Path, model: Model,
        prior_issues: list[dict] | None = None,
    ) -> dict:
        """调 code-implementation skill 产出 workspace/code/ + self-check.log。

        返回 {files: [...rel], self_check: {ok: bool, log: str}}.
        """
        workspace = workspace.resolve()
        code_dir = workspace / "code"
        code_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[雷神·code] 产出到 {}", code_dir)

        user_parts = [
            "调用 code-implementation skill，按它的规范产出代码到 workspace/code/。\n",
            "```yaml",
            f"spec_path: {spec_path}",
            f"design_path: {design_path}",
            f"workspace: {workspace}/",
            f"project_root: {self._project_root()}/",
        ]
        if prior_issues:
            from paimon.archons.nahida import _fmt_issue_yaml
            user_parts.append("prior_issues:")
            for it in prior_issues[:20]:
                user_parts.append(_fmt_issue_yaml(it))
        user_parts.append("```")
        user_msg = "\n".join(user_parts)

        await self._invoke_skill_workflow(
            skill_name="code-implementation",
            user_message=user_msg,
            model=model,
            session_name=workspace.name,
            component="雷神",
            purpose="代码实现",
            allowed_tools={"file_ops", "exec"},
            framing=(
                f"【四影管线·code 阶段】\n产物写到: {code_dir}/\n"
                f"路径规则: workspace/code/{{相对路径}} = 宿主项目对应文件路径\n"
                f"读参考: {self._project_root()}/\n"
                "写完后必须自检三件套（py_compile/ruff/pytest），失败继续修。"
            ),
        )

        # archon 侧兜底再跑一次自检（即使 LLM 已跑过，确保 self-check.log 存在且结果可信）
        check_result = await self.self_check(workspace)

        # 列出实际产出文件（过滤 .check/ / __pycache__/ 等噪声）
        from paimon.foundation.task_workspace import list_workspace_files
        # 从 workspace 推算 task_id（workspace dirname 就是 task_id[:12]）
        files = [
            str(p.relative_to(code_dir))
            for p in list_workspace_files(workspace.name)
        ]

        return {
            "files": files,
            "self_check": check_result,
        }

    async def self_check(self, workspace: Path) -> dict:
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
                details["ruff"] = "warn"  # ruff warn 不算 fail（严格 E/F 再加码）

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


# ============ helpers ============


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
