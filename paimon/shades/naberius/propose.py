"""生执·propose_skill — 凝练 skill 草案落世界树 skill_proposals 域。

stage = propose_skill：从 task 描述 + prior_results 抽出"可复用 skill 草案"
（name / description / triggers / system_prompt / allowed_tools），落 skill_proposals
域 status=pending；下游 review_proposal 节点读 prop_id 审。

借鉴 hermes-agent 的"判断标准 + Nothing to save 短路"：LLM 看到
没价值做 skill 时输出 `{"skip": true, "skip_reason": "..."}`，propose 直接返不写表，
避免空 skill 提案污染面板。

stage 归属：propose_skill → 生执
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.llm.model import Model


_PROPOSE_SYSTEM = """\
你是「生执·propose_skill」，从用户的任务/历史归档里凝练**可复用 skill 草案**，
不直接落盘——草案先入待审队列经死执质量审 + 用户面板审 + 派蒙 safety 审，三道闸全过冰神才落 .claude/skills/。

## 判断标准（**严格**，不达标输出 skip）

值得做 skill：
- 任务流程**多步**且**可复用**（一次性 5+ 步，未来还会重复）
- 用户已显式标注"以后都这么做"或"沉淀成 skill"
- 跟现有 skill 有清晰边界（不重叠不重复）

**不值得**做 skill（应输出 skip=true）：
- 单次性问答 / 闲聊
- 任务太琐碎（1-2 步搞定）
- 跟某个现有 skill 高度重叠（已有就别新建）
- 描述含糊到无法泛化（"帮我看下"这种没法做 skill）
- 涉及个人隐私 / 临时凭据（不该入 skill 库）

## 输出格式（**严格 JSON**，无 markdown fence、无解释）

值得做：
```json
{
  "skip": false,
  "name": "kebab-case-name",
  "kind": "new",
  "target_skill": "",
  "description": "一句话职能（≤80 字）",
  "triggers": "什么时候调这个 skill（≤200 字）",
  "system_prompt": "完整 SKILL.md body：步骤 / 输入 / 输出 / 注意事项（≤4000 字）",
  "allowed_tools": ["file_ops"],
  "rationale": "为什么值得沉淀（任务事实 + 模式归纳，≤300 字）"
}
```

不值得做：
```json
{"skip": true, "skip_reason": "为什么不值得（≤200 字）"}
```

字段约束：
- `name`：kebab-case，3-30 字符；要语义化（不是 "skill-1"）
- `kind`：默认 "new"；如果是改进现有 skill 填 "improve" + `target_skill` 填现有 skill 名
- `allowed_tools` 只填**真正需要**的（最小权限原则）；常用：`file_ops` / `exec` / `web_search` / `glob`
- `system_prompt` 必须能让另一个 LLM 看完就知道"什么时候用 / 怎么用 / 输出什么"，不要 placeholder
"""


def _parse_propose_json(text: str) -> dict | None:
    """LLM 输出 JSON 容错解析：剥 markdown fence / 截首尾大括号 / json.loads。"""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # 兜底：截首尾 {...}
    s, e = text.find("{"), text.rfind("}")
    if 0 <= s < e:
        try:
            return json.loads(text[s:e + 1])
        except Exception:
            pass
    return None


_KEBAB_RE = re.compile(r"^[a-z][a-z0-9-]{1,29}$")


async def propose_skill(
    task: "TaskEdict",
    subtask: "Subtask",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None,
) -> str:
    """生执 propose_skill stage 主入口。

    返回值（被 review_proposal stage 通过 prior_results 解析）：
    - skip：`SKIP: <reason>`
    - 落档成功：`prop_id=<12hex>\\n<草案概要>`
    - 落档失败：原始错误信息（pipeline 标 failed 走 revise）
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

    # 拼 user_message：task 描述 + prior_results + 现有 skill
    parts = [
        f"## 任务\n{task.title}\n\n{task.description}\n",
    ]
    if prior_results:
        parts.append("## 前序产物")
        for i, pr in enumerate(prior_results[:5], 1):
            parts.append(f"\n### 子任务 {i}\n{pr[:1500]}\n")
    parts.append(f"\n## 现有 skill 列表（避免重叠）\n{existing_brief}\n")
    parts.append("\n请按上述判断标准输出 JSON。")
    user_msg = "\n".join(parts)

    system = _PROPOSE_SYSTEM
    system += await load_feedback_memories_block(irminsul)

    temp_session = Session(
        id=f"shades-propose-{task.id[:8]}", name="生执·propose_skill",
    )
    temp_session.messages.append({"role": "system", "content": system})

    async for _ in model.chat(
        temp_session, user_msg,
        component="生执·propose_skill", purpose="凝练 skill 草案",
    ):
        pass
    raw = extract_result(temp_session)

    obj = _parse_propose_json(raw)
    if not obj or not isinstance(obj, dict):
        logger.warning("[生执·propose_skill] LLM 输出 JSON 解析失败，标 skip 兜底")
        return "SKIP: LLM 输出格式错误，本次不产出提案"

    if obj.get("skip"):
        reason = str(obj.get("skip_reason") or obj.get("reason") or "")[:300]
        logger.info("[生执·propose_skill] skip：{}", reason[:100])
        return f"SKIP: {reason}"

    # 校验关键字段
    name = str(obj.get("name", "")).strip()
    system_prompt = str(obj.get("system_prompt", "")).strip()
    if not name or not system_prompt:
        return "SKIP: name 或 system_prompt 缺失，本次不产出提案"
    if not _KEBAB_RE.match(name):
        return f"SKIP: name 格式不合规（应 kebab-case，得 {name!r}）"

    kind = str(obj.get("kind", "new")).strip()
    target_skill = str(obj.get("target_skill", "")).strip()
    if kind not in ("new", "improve"):
        kind = "new"
    if kind == "improve" and not target_skill:
        return "SKIP: kind=improve 但 target_skill 为空"

    allowed_tools_raw = obj.get("allowed_tools") or []
    if isinstance(allowed_tools_raw, str):
        allowed_tools = [t.strip() for t in allowed_tools_raw.split(",") if t.strip()]
    elif isinstance(allowed_tools_raw, list):
        allowed_tools = [str(t).strip() for t in allowed_tools_raw if str(t).strip()]
    else:
        allowed_tools = []

    try:
        prop_id = await irminsul.skill_proposal_create(
            name=name,
            kind=kind,
            target_skill=target_skill,
            description=str(obj.get("description", "")).strip()[:200],
            triggers=str(obj.get("triggers", "")).strip()[:500],
            system_prompt=system_prompt[:4000],
            allowed_tools=allowed_tools,
            rationale=str(obj.get("rationale", "")).strip()[:500],
            proposed_by_session=task.session_id,
            proposed_by_task=task.id,
            actor="生执",
        )
    except ValueError as e:
        return f"SKIP: 提案校验失败：{e}"
    except Exception as e:
        logger.error("[生执·propose_skill] 落档异常：{}", e)
        raise

    summary = (
        f"prop_id={prop_id}\n"
        f"name={name} kind={kind}\n"
        f"description={obj.get('description', '')[:100]}\n"
        f"allowed_tools={allowed_tools}\n"
        "（草案已落待审队列，等死执质量审 + 用户 /plugins 面板审批）"
    )
    return summary
