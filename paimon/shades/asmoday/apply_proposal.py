"""空执 · apply skill 自进化提案 → 落 `<project_root>/skills/<name>/SKILL.md` + 注册。

唯一调用方：webui `/api/plugins/proposals/<id>/approve` 用户点同意后同步调。
不在 cron / 启动期跑——每条 approved 提案立即落盘，失败回滚标 audit。

设计：
1. 读 skill_proposals.status='approved' 提案
2. 拼 SKILL.md 文本（YAML frontmatter + body）
3. 派蒙 core/safety/skill_review 跑安全审（tool 越权 / sensitive / triggers 等）
4. atomic 写盘：先写 .tmp/SKILL.md → safety 审 pass → mv 到正式目录
5. registry.scan_and_load 触发热加载（让运行时立即可用）
6. mark_applied 写 status=applied + applied_at

借鉴 hermes-agent：原子 temp-replace；审查失败 rmtree 回滚。

failure 处理：
- safety 审拒：删 .tmp/，不写 skills/，audit 记原因，提案保持 status=approved
  让用户/管理员决定是否人工介入（暂不 auto-rollback 到 rejected——尊重用户已 approve 的意愿）
- 落盘异常：同上
- mark_applied 失败：skill 已生效但状态没刷，下次启动再补刷；不致命
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul, SkillProposal
    from paimon.llm.model import Model


@dataclass
class ApplyResult:
    ok: bool
    skill_name: str = ""
    error: str = ""
    skill_dir: str = ""


def _build_skill_md(prop: "SkillProposal") -> str:
    """SkillProposal → SKILL.md 文本（YAML frontmatter + body）。"""
    tools_yaml = ",".join(prop.allowed_tools) if prop.allowed_tools else ""
    fm_lines = [
        "---",
        f"name: {prop.name}",
        f"description: {prop.description.replace(chr(10), ' ')}",
    ]
    if prop.triggers:
        # triggers 多行用 yaml | 块标量
        if "\n" in prop.triggers:
            fm_lines.append("triggers: |")
            for line in prop.triggers.split("\n"):
                fm_lines.append(f"  {line}")
        else:
            fm_lines.append(f"triggers: {prop.triggers}")
    if tools_yaml:
        fm_lines.append(f"allowed-tools: {tools_yaml}")
    fm_lines.append("source: ai_gen")
    fm_lines.append(f"origin: {prop.proposed_by_session or 'unknown'}")
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(prop.system_prompt.strip())
    return "\n".join(fm_lines) + "\n"


async def apply_proposal(
    prop_id: str,
    *,
    irminsul: "Irminsul",
    model: "Model",
    skills_dir: Path,
    actor: str = "空执",
) -> ApplyResult:
    """读 approved 提案 → 派蒙 safety 审 → 落 SKILL.md → 注册 skill_declarations。"""
    from paimon.foundation.irminsul import STATUS_APPROVED
    from paimon.foundation.irminsul.skills import SkillDecl
    from paimon.core.authz.sensitive_tools import derive_sensitivity
    from paimon.core.safety import review_skill_declaration

    prop = await irminsul.skill_proposal_get(prop_id)
    if not prop:
        return ApplyResult(ok=False, error=f"提案 {prop_id} 不存在")
    if prop.status != STATUS_APPROVED:
        return ApplyResult(
            ok=False, skill_name=prop.name,
            error=f"提案状态非 approved（当前 {prop.status}），不可落盘",
        )

    skill_dir = skills_dir / prop.name
    tmp_dir = skills_dir.parent / f".{prop.name}.tmp"

    # 1. 同名冲突检查
    if skill_dir.exists():
        return ApplyResult(
            ok=False, skill_name=prop.name,
            error=f"同名 skill 已存在：{skill_dir}（请先 /plugins 撤销旧 skill 或改提案 name）",
        )

    # 2. 派蒙 safety 审：派生 sensitivity + 跑 review_skill_declaration
    sensitivity, sensitive_tools = derive_sensitivity(prop.allowed_tools or [])
    decl = SkillDecl(
        name=prop.name,
        source="ai_gen",
        origin=prop.proposed_by_session or "",
        sensitivity=sensitivity,
        description=prop.description,
        triggers=prop.triggers,
        allowed_tools=list(prop.allowed_tools or []),
        sensitive_tools=list(sensitive_tools or []),
    )
    try:
        passed, reason = await review_skill_declaration(decl, model)
    except Exception as e:
        logger.error("[空执·apply] safety 审异常 {}: {}", prop_id, e)
        return ApplyResult(
            ok=False, skill_name=prop.name,
            error=f"safety 审异常：{e}",
        )

    if not passed:
        try:
            await irminsul.audit_append(
                event_type="skill_proposal_apply_safety_rejected",
                payload={
                    "prop_id": prop_id, "name": prop.name,
                    "reason": reason, "allowed_tools": prop.allowed_tools,
                },
                actor=actor,
            )
        except Exception:
            pass
        logger.warning("[空执·apply] safety 审拒 {}: {}", prop.name, reason)
        return ApplyResult(
            ok=False, skill_name=prop.name,
            error=f"派蒙 safety 审拒：{reason}",
        )

    # 3. atomic 写盘：先写 .tmp/，再 mv 正式目录
    try:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=False)
        (tmp_dir / "SKILL.md").write_text(_build_skill_md(prop), encoding="utf-8")
        # 原子 rename
        tmp_dir.rename(skill_dir)
    except Exception as e:
        logger.error("[空执·apply] 写盘失败 {}: {}", prop.name, e)
        # 清理 .tmp/
        if tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass
        if skill_dir.exists() and not (skill_dir / "SKILL.md").exists():
            try:
                shutil.rmtree(skill_dir)
            except Exception:
                pass
        return ApplyResult(
            ok=False, skill_name=prop.name,
            error=f"写盘失败：{e}",
        )

    # 4. 注册 skill_declarations + 触发热加载
    try:
        await irminsul.skill_declare(decl, actor=actor)
    except Exception as e:
        logger.error("[空执·apply] 写 skill_declarations 失败 {}: {}", prop.name, e)
        # 文件已写，但 DB 注册失败：保留文件让下次启动 scan_and_load 补刷
        # 不回滚文件，避免反复 LLM 调用浪费

    # 5. 通知 SkillRegistry 内存层加载
    try:
        from paimon.state import state
        if state.skill_registry:
            state.skill_registry.scan_and_load()
        if state.leyline:
            await state.leyline.publish(
                "skill.loaded", {"name": prop.name, "source": "ai_gen"},
                source="空执",
            )
    except Exception as e:
        logger.debug("[空执·apply] registry 热加载或 leyline 发布失败：{}", e)

    # 6. mark_applied
    try:
        await irminsul.skill_proposal_mark_applied(prop_id, actor=actor)
    except Exception as e:
        logger.warning("[空执·apply] mark_applied 失败 {}: {}", prop_id, e)

    logger.info(
        "[空执·apply] 落盘成功 {} → {}（source=ai_gen, sensitivity={}）",
        prop.name, skill_dir, sensitivity,
    )
    return ApplyResult(
        ok=True, skill_name=prop.name, skill_dir=str(skill_dir),
    )
