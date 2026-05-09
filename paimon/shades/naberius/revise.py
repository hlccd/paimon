"""生执·revise_proposal — 根据用户反馈重写 skill 草案。

stage = revise_proposal：用户在 /plugins 面板对 pending 提案"提建议改写"后触发。
读 skill_proposals 域的 user_feedback + 原 system_prompt / triggers / allowed_tools，
让 LLM 调 `revise_skill` 工具产出新版内容写回（in-place），同时 reset
review_verdict 让死执下次重审。

**tool-based 实现**（同生执 propose_skill / 死执 review_proposal）：
LLM 不输出文本 JSON，调 `revise_skill` 工具，参数 schema 强校验。

跟 propose 的差异：
- 不允许改 name / kind / target_skill（这些是用户认可的"提案身份"，重写只改内容）
- 必填全部内容字段（description / triggers / system_prompt / allowed_tools / rationale），
  防止 LLM 偷懒只改一两处导致信息断档

stage 归属：revise_proposal → 生执
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul, SkillProposal
    from paimon.llm.model import Model


_REVISE_SYSTEM = """\
你是 paimon 自进化系统的 skill 草案重写者。

用户在面板上对一份 skill 草案提了反馈/建议，**你的职能就是基于这份反馈
重写草案**——保留 skill 的核心身份（name / 目标），但内容（system_prompt /
triggers / allowed_tools / description / rationale）按用户建议改写。

## 行动

调 `revise_skill` 工具提交完整的新版内容——这是唯一允许的输出方式。

注意：
- **必须**输出完整新版本，不要写"在原版基础上加..."这种半成品
- system_prompt 要写完整 SKILL.md body，让另一个 LLM 看完就能直接用
- 用户建议如果是「扩大覆盖范围」（如"还应该支持非米哈游游戏"），
  你要把对应内容融入 triggers / system_prompt / 步骤里，而不是只提一句
- 用户建议如果是「修正错误」，你要从头重新组织相关章节
- 用户建议如果**为空**（用户只点了"重审"没输入文字），你**仍然要重写一次**——
  视作"按当前内容重审"的退化情形：可以做**轻微优化**（润色 / 补例子 / 修笔误），
  但保留原意，让死执下次审能拿到一个更干净的版本
"""


_REVISE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "revise_skill",
        "description": (
            "提交 skill 草案的重写版本。看完原草案 + 用户建议后必须调此工具——"
            "这是唯一允许的输出方式。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "一句话职能描述（≤80 字），按建议调整后的版本。",
                },
                "triggers": {
                    "type": "string",
                    "description": "什么场景下应该调用此 skill（≤200 字），按建议调整后的版本。",
                },
                "system_prompt": {
                    "type": "string",
                    "description": (
                        "完整 SKILL.md body：触发条件 / 步骤 / 输入 / 输出 / 注意事项。"
                        "**必须完整重写**，让另一个 LLM 看完就能直接用，不留 placeholder。"
                    ),
                },
                "allowed_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "skill 需要的工具列表（最小权限原则）。常用：file_ops, exec, "
                        "web_fetch, web_search, glob。按建议调整后的版本。"
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "为什么这值得沉淀（≤300 字），按建议调整后的版本。",
                },
            },
            "required": ["description", "triggers", "system_prompt", "allowed_tools"],
        },
    },
}


async def revise_proposal(
    prop_id: str,
    irminsul: "Irminsul",
    model: "Model",
) -> str:
    """生执 revise_proposal stage 主入口。

    跟 propose / review_proposal 不同，本入口直接接 prop_id（不走 task / subtask
    上下文），因为 revise 是**用户面板按钮触发**的简单异步流程，不需要 task 元数据。

    返回：
    - 重写成功：`prop_id=<12hex>\\n revision=<n>\\n（已写回，待死执重审）`
    - 失败：`SKIP: <原因>` —— 调用方（API / 触发器）可据此决定是否触发死执重审
    """
    from paimon.session import Session
    from paimon.shades._helpers.runner_helpers import load_feedback_memories_block

    prop: "SkillProposal | None" = await irminsul.skill_proposal_get(prop_id)
    if not prop:
        return f"SKIP: 提案 {prop_id} 不存在"
    if prop.status != "pending":
        return f"SKIP: 提案 {prop_id} 状态={prop.status}（非 pending），不允许 revise"

    user_feedback = (prop.user_feedback or "").strip()

    # 拼 user_msg：原草案 + 用户建议
    user_msg_parts = [
        f"## 原草案 (prop_id={prop_id})\n",
        f"**name**: {prop.name}",
        f"**kind**: {prop.kind}",
    ]
    if prop.kind == "improve" and prop.target_skill:
        user_msg_parts.append(f"**target_skill**: {prop.target_skill}")
    user_msg_parts.append(f"**description**: {prop.description}")
    user_msg_parts.append(f"**triggers**: {prop.triggers}")
    user_msg_parts.append(f"**allowed_tools**: {prop.allowed_tools}")
    user_msg_parts.append(f"**rationale**: {prop.rationale}")
    user_msg_parts.append(
        f"\n**system_prompt**:\n```\n{prop.system_prompt[:3500]}\n```\n"
    )
    if user_feedback:
        user_msg_parts.append(f"\n## 用户建议\n\n{user_feedback}")
    else:
        user_msg_parts.append(
            "\n## 用户建议（空）\n\n用户没有给出具体建议，只点了「重审」。"
            "这是一次轻量重写——保留原意，做润色 / 补例 / 修笔误。"
        )
    user_msg_parts.append("\n请调 `revise_skill` 工具提交完整的新版内容。")
    user_msg = "\n".join(user_msg_parts)

    system = _REVISE_SYSTEM
    system += await load_feedback_memories_block(irminsul)

    revise_state: dict = {
        "applied": False,
        "tool_error": None,
    }

    async def _executor(name: str, args_str: str) -> str:
        if name != "revise_skill":
            return f"错误：未知工具 {name}"
        if revise_state["applied"]:
            return "已写回新版本，请勿重复调用。回 'OK' 结束。"

        try:
            obj = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError as e:
            err = f"参数 JSON 解析失败：{e}"
            revise_state["tool_error"] = err
            return f"参数错误：{err}"

        description = str(obj.get("description", "")).strip()[:200]
        triggers = str(obj.get("triggers", "")).strip()[:500]
        system_prompt = str(obj.get("system_prompt", "")).strip()[:4000]
        rationale = str(obj.get("rationale", "")).strip()[:500]

        if not system_prompt:
            err = "system_prompt 不能为空"
            revise_state["tool_error"] = err
            return f"参数错误：{err}"

        # allowed_tools 容错
        at_raw = obj.get("allowed_tools")
        if isinstance(at_raw, str):
            allowed_tools = [t.strip() for t in at_raw.split(",") if t.strip()]
        elif isinstance(at_raw, list):
            allowed_tools = [str(t).strip() for t in at_raw if str(t).strip()]
        else:
            allowed_tools = list(prop.allowed_tools)  # 缺省保留原版

        try:
            ok = await irminsul.skill_proposal_update_content(
                prop_id,
                description=description or None,
                triggers=triggers or None,
                system_prompt=system_prompt,
                allowed_tools=allowed_tools,
                rationale=rationale or None,
                bump_revision=True,
                actor="生执·revise",
            )
        except Exception as e:
            logger.error("[生执·revise_proposal] 写回异常 prop_id={}: {}", prop_id, e)
            err = f"写回异常：{e}"
            revise_state["tool_error"] = err
            return f"写回异常：{err}"

        if not ok:
            err = f"提案 {prop_id} 状态变化（不再 pending），revise 终止"
            revise_state["tool_error"] = err
            return f"写回拒绝：{err}"

        revise_state["applied"] = True
        logger.info(
            "[生执·revise_proposal] 写回成功 prop_id={} revision={} (was {})",
            prop_id, prop.revision_count + 1, prop.revision_count,
        )
        return (
            f"新版本已写回 prop_id={prop_id}，revision={prop.revision_count + 1}。"
            "本次任务完成，回一句 'OK' 结束。"
        )

    temp_session = Session(
        id=f"shades-revise-{prop_id[:8]}", name="生执·revise_proposal",
    )
    temp_session.messages.append({"role": "system", "content": system})

    try:
        async for _ in model.chat(
            temp_session, user_msg,
            tools=[_REVISE_TOOL_SCHEMA],
            tool_executor=_executor,
            component="生执·revise_proposal",
            purpose="重写 skill 草案",
        ):
            pass
    except Exception as e:
        logger.warning("[生执·revise_proposal] LLM 调用异常 prop_id={}: {}", prop_id, e)
        return f"SKIP: LLM 调用失败：{e}"

    if revise_state["applied"]:
        return (
            f"prop_id={prop_id}\n"
            f"revision={prop.revision_count + 1}\n"
            "（新版已写回，待死执重审）"
        )

    if revise_state["tool_error"]:
        return f"SKIP: 工具调用失败：{revise_state['tool_error']}"

    logger.warning("[生执·revise_proposal] LLM 没调工具 prop_id={}", prop_id)
    return "SKIP: LLM 未调 revise_skill 工具，本次重写未生效"


async def run_revise_and_review_chain(
    prop_id: str,
    irminsul: "Irminsul",
    model: "Model",
) -> str | None:
    """前端「提建议改写」按钮的后台主入口：revise → 死执 review 重审。

    无论成功 / 失败 / 异常都在 finally 里清空 revising_at，让前端按钮解锁。
    返本次写回后的 prop_id（重写成功且重审完毕），SKIP 返 None。
    """
    from paimon.shades.jonova.review_proposal import review_proposal

    try:
        revise_result = await revise_proposal(prop_id, irminsul, model)
        logger.info(
            "[生执·revise_proposal] revise 完成 prop_id={} result={!r}",
            prop_id, revise_result[:120],
        )

        if revise_result.startswith("SKIP:"):
            return None

        review_result = await review_proposal(
            model=model,
            irminsul=irminsul,
            prior_results=[revise_result],
            origin_id=prop_id,
        )
        logger.info(
            "[生执·revise_proposal] re-review 完成 prop_id={} verdict_text={!r}",
            prop_id, review_result[:100],
        )
        return prop_id
    finally:
        # 兜底解锁：成功 / SKIP / 异常都把 revising_at 清空，前端按钮恢复可用
        await irminsul.skill_proposal_mark_revising_done(prop_id)
