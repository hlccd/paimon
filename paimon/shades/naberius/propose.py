"""生执·propose_skill — 凝练 skill 草案落世界树 skill_proposals 域。

stage = propose_skill：从 task 描述 + prior_results 抽出"可复用 skill 草案"
（name / description / triggers / system_prompt / allowed_tools），落 skill_proposals
域 status=pending；下游 review_proposal 节点读 prop_id 审。

**tool-based 实现**（参考 hermes-agent/tools/skill_manager_tool.py）：
LLM 不输出文本 JSON，而是调 `propose_skill` 工具，参数由 OpenAI
function-calling schema 强校验。判断不值得做时直接说 "Nothing to save."
不调任何工具——这种二元选择对弱模型友好得多，比文本 JSON 解析鲁棒。

stage 归属：propose_skill → 生执
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.llm.model import Model


_PROPOSE_SYSTEM = """\
你是 paimon 自进化系统的 skill 提案者。
我会给你一个最近的任务 / 会话片段。判断里面是否有**值得沉淀成可复用 skill** 的模式。

## 判断标准（**严格**，绝大多数情况都应该「不调工具」）

值得做：
- ✓ 任务多步（≥4 步）且方法**可复用**，用户未来很可能再来同样模式
- ✓ 跟现有 skill 不重叠

不值得做（**直接 'Nothing to save.' 不调工具**）：
- ✗ 单次问答 / 闲聊 / 临时事项
- ✗ 任务 1-2 步搞定，太琐碎
- ✗ 跟现有 skill 高度重叠
- ✗ 涉及个人隐私 / 临时凭据
- ✗ 描述含糊到无法泛化

## 行动

- **值得做** → 调 `propose_skill` 工具落档（用户面板会再审一道，你只是「提案」）
- **不值得** → 回一句 "Nothing to save." 然后停下，**不调任何工具**

## 多 skill 场景

如果上下文里有**多个独立可复用模式**（典型场景：月度扫描 / 大量历史任务汇总），
可以**多次调用 `propose_skill` 工具**，每次产出一个独立 skill 草案。
**单次任务最多产出 5 个 skill 提案**，超过会被拒绝。

每个 skill 必须满足上面的"值得做"标准，**不要为了凑数硬编**。
绝大多数 chat / 单 task 场景**只该产出 0 或 1 个**；只有看到丰富多元的历史汇总
才有可能识别多个独立模式。

调工具时 system_prompt 字段要写完整的 SKILL.md body：
触发条件 / 步骤 / 输入 / 输出 / 注意事项；要让另一个 LLM 看完就能直接用。
"""


_MAX_PROPOSALS_PER_RUN = 5  # 单次 propose 调用最多产出多少个独立 skill 草案


_PROPOSE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "propose_skill",
        "description": (
            "落一份 skill 草案到 paimon 待审队列（skill_proposals 域 status=pending）。"
            "草案进面板由用户审，不是直接装载到 skills/。"
            "**判断不值得做时不要调此工具**，直接回 'Nothing to save.' 即可。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "kebab-case skill 名，3-30 字符，必须语义化"
                        "（如 'game-character-build'，不能是 'skill-1'）。"
                        "正则约束：^[a-z][a-z0-9-]{1,29}$。"
                    ),
                },
                "kind": {
                    "type": "string",
                    "enum": ["new", "improve"],
                    "description": "默认 'new'。改进现有 skill 才填 'improve' 并填 target_skill。",
                },
                "target_skill": {
                    "type": "string",
                    "description": "kind='improve' 时必填要改进的现有 skill 名；kind='new' 留空。",
                },
                "description": {
                    "type": "string",
                    "description": "一句话职能描述（≤80 字）。",
                },
                "triggers": {
                    "type": "string",
                    "description": "什么场景下应该调用此 skill（≤200 字）。",
                },
                "system_prompt": {
                    "type": "string",
                    "description": (
                        "完整 SKILL.md body：触发条件 / 步骤 / 输入 / 输出 / 注意事项。"
                        "要让另一个 LLM 看完就能直接用，不留 placeholder。"
                    ),
                },
                "allowed_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "skill 需要的工具列表（最小权限原则，**只列真正用到的**）。"
                        "常用：file_ops, exec, web_fetch, web_search, glob。"
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "为什么这值得沉淀（任务事实 + 模式归纳，≤300 字）。",
                },
            },
            "required": ["name", "description", "triggers", "system_prompt"],
        },
    },
}


_KEBAB_RE = re.compile(r"^[a-z][a-z0-9-]{1,29}$")


async def propose_skill(
    *,
    title: str,
    description: str,
    session_id: str = "",
    origin_id: str = "",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None = None,
) -> str:
    """生执 propose_skill stage 主入口（tool-based 实现）。

    LLM 看任务 / 历史 → 调 propose_skill 工具落档 / 或说 "Nothing to save."。

    返回（被 review_proposal stage 通过 prior_results 解析）：
    - 工具落档成功：`prop_id=<12hex>\\n<草案概要>`
    - LLM 不调工具：`SKIP: <LLM 文本前 200 字>`
    - 工具参数校验失败：`SKIP: <错误信息>`
    - 落档异常：原始错误信息（pipeline 标 failed 走 revise）
    """
    from paimon.session import Session
    from paimon.shades._helpers.runner_helpers import (
        extract_result, load_feedback_memories_block,
    )

    # 取现有 skill 列表（提示 LLM 避免重叠）
    try:
        existing = await irminsul.skill_list(include_orphaned=False)
        existing_brief = "\n".join(
            f"- {s.name}: {s.description[:80]}" for s in existing[:30]
        ) or "（暂无）"
    except Exception:
        existing_brief = "（读取失败，请勿据此判定重叠）"

    # 拼 user_msg：task 描述 + prior_results + 现有 skill
    parts = [
        f"## 任务\n{title}\n\n{description}\n",
    ]
    if prior_results:
        parts.append("## 前序产物")
        for i, pr in enumerate(prior_results[:5], 1):
            parts.append(f"\n### 子任务 {i}\n{pr[:1500]}\n")
    parts.append(f"\n## 现有 skill 列表（避免重叠）\n{existing_brief}\n")
    parts.append(
        "\n请按上述判断标准决定：值得就调 `propose_skill` 工具，"
        "不值得就回 'Nothing to save.' 不调工具。"
    )
    user_msg = "\n".join(parts)

    system = _PROPOSE_SYSTEM
    system += await load_feedback_memories_block(irminsul)

    # 工具回调状态：闭包捕获，主流程读取
    # proposals 是 list[dict]，每条 {"prop_id":..., "name":...}；
    # 单次 propose 调用支持累计多个（上限 _MAX_PROPOSALS_PER_RUN）
    proposal_state: dict = {
        "proposals": [],
        "tool_error": None,
    }

    async def _executor(name: str, args_str: str) -> str:
        """propose_skill 工具 handler：参数校验 + 落档 + 状态回写。"""
        if name != "propose_skill":
            return f"错误：未知工具 {name}"

        # 单次 run 上限：超过即拒绝（防 LLM 失控刷 spam）
        if len(proposal_state["proposals"]) >= _MAX_PROPOSALS_PER_RUN:
            return (
                f"本次任务已产出 {len(proposal_state['proposals'])} 个 skill，"
                f"达上限 {_MAX_PROPOSALS_PER_RUN}。回一句 'OK' 结束。"
            )

        try:
            obj = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError as e:
            err = f"参数 JSON 解析失败：{e}"
            proposal_state["tool_error"] = err
            return f"参数错误：{err}"

        skill_name = str(obj.get("name", "")).strip()
        system_prompt = str(obj.get("system_prompt", "")).strip()

        if not skill_name or not system_prompt:
            err = "name 或 system_prompt 缺失"
            proposal_state["tool_error"] = err
            return f"参数错误：{err}"
        if not _KEBAB_RE.match(skill_name):
            err = f"name 格式不合规（应 kebab-case 3-30 字符），得 {skill_name!r}"
            proposal_state["tool_error"] = err
            return f"参数错误：{err}"

        kind = str(obj.get("kind", "new")).strip() or "new"
        if kind not in ("new", "improve"):
            kind = "new"
        target_skill = str(obj.get("target_skill", "")).strip()
        if kind == "improve" and not target_skill:
            err = "kind='improve' 时 target_skill 必填"
            proposal_state["tool_error"] = err
            return f"参数错误：{err}"

        # allowed_tools 容错：list / 逗号字符串 / null 都能吃
        at_raw = obj.get("allowed_tools")
        if isinstance(at_raw, str):
            allowed_tools = [t.strip() for t in at_raw.split(",") if t.strip()]
        elif isinstance(at_raw, list):
            allowed_tools = [str(t).strip() for t in at_raw if str(t).strip()]
        else:
            allowed_tools = []

        try:
            prop_id = await irminsul.skill_proposal_create(
                name=skill_name,
                kind=kind,
                target_skill=target_skill,
                description=str(obj.get("description", "")).strip()[:200],
                triggers=str(obj.get("triggers", "")).strip()[:500],
                system_prompt=system_prompt[:4000],
                allowed_tools=allowed_tools,
                rationale=str(obj.get("rationale", "")).strip()[:500],
                proposed_by_session=session_id,
                proposed_by_task=origin_id,
                actor="生执",
            )
        except ValueError as e:
            err = f"提案校验失败：{e}"
            proposal_state["tool_error"] = err
            return f"落档拒绝：{err}"
        except Exception as e:
            logger.error("[生执·propose_skill] 落档异常：{}", e)
            err = f"落档异常：{e}"
            proposal_state["tool_error"] = err
            return f"落档异常：{err}"

        proposal_state["proposals"].append({
            "prop_id": prop_id, "name": skill_name,
        })
        logger.info(
            "[生执·propose_skill] 落档成功 prop_id={} name={} kind={} ({}/{})",
            prop_id, skill_name, kind,
            len(proposal_state["proposals"]), _MAX_PROPOSALS_PER_RUN,
        )
        remaining = _MAX_PROPOSALS_PER_RUN - len(proposal_state["proposals"])
        if remaining > 0:
            tail = (
                f"如还有其他**独立可复用**模式可以再调一次（剩余 {remaining} 个名额）；"
                "如果没有了请回一句 'OK' 结束。"
            )
        else:
            tail = "已达上限，回一句 'OK' 结束。"
        return (
            f"成功落档：prop_id={prop_id}, name={skill_name}, kind={kind}。"
            f"已进入待审队列，等死执质量审 + 用户 /plugins 面板审批。{tail}"
        )

    temp_session = Session(
        id=f"shades-propose-{(origin_id or 'noop')[:8]}", name="生执·propose_skill",
    )
    temp_session.messages.append({"role": "system", "content": system})

    try:
        async for _ in model.chat(
            temp_session, user_msg,
            tools=[_PROPOSE_TOOL_SCHEMA],
            tool_executor=_executor,
            component="生执·propose_skill",
            purpose="凝练 skill 草案",
        ):
            pass
    except Exception as e:
        logger.warning("[生执·propose_skill] LLM 调用异常：{}", e)
        return f"SKIP: LLM 调用失败：{e}"

    # 工具落档成功 → 返多行产出（每行 prop_id=<id> name=<name>，下游 review 解析全部）
    proposals = proposal_state["proposals"]
    if proposals:
        lines = []
        for p in proposals:
            lines.append(f"prop_id={p['prop_id']} name={p['name']}")
        lines.append(
            f"（共 {len(proposals)} 条草案已落待审队列，"
            "等死执质量审 + 用户 /plugins 面板审批）"
        )
        return "\n".join(lines)

    # 工具调用失败（参数校验 / 落档异常）→ SKIP 含错误信息
    if proposal_state["tool_error"]:
        logger.info(
            "[生执·propose_skill] 工具调用失败：{}",
            proposal_state["tool_error"][:100],
        )
        return f"SKIP: {proposal_state['tool_error']}"

    # 没调工具 → LLM 判断不值得做
    final_text = (extract_result(temp_session) or "").strip()
    reason = final_text[:200] if final_text else "LLM 未给出最终判断"
    logger.info("[生执·propose_skill] 不值得做：{}", reason[:120])
    return f"SKIP: {reason}"
