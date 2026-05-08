"""死执·review_proposal — 审 skill 自进化提案的质量。

stage = review_proposal：从 prior_results 解析 prop_id，读 skill_proposals 域里
status=pending 的提案，审：
1. 草案完整度（system_prompt 不空泛 / triggers 清晰 / 步骤可执行）
2. 跟现有 skill_declarations 是否重叠
3. allowed_tools 是否最小权限（敏感工具是否真需要）
4. 边界是否清晰（什么时候用 / 不该用）

输出符合 ReviewVerdict 协议的 JSON：
- level: pass / revise / redo
- summary / issues
同时写 skill_proposals.review_verdict + review_notes（供 /plugins 面板展示）：
- level=pass    → verdict='pass'
- level=revise  → verdict='needs_revise'（用户面板 approve 按钮 disabled）
- level=redo    → verdict='reject'（联动 status=rejected）

stage 归属：review_proposal → 死执（v8 自进化）
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from loguru import logger

from paimon.foundation.irminsul import (
    VERDICT_PASS, VERDICT_NEEDS_REVISE, VERDICT_REJECT,
)

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.llm.model import Model


_REVIEW_SYSTEM = """\
你是「死执·review_proposal」，对生执 propose_skill 凝练的 skill 草案做质量审。

## 审查维度（严格）

### P0 致命（→ redo / reject）
- system_prompt 完全空泛 / 只是个标题没内容
- 跟现有 skill 高度重叠（功能完全冗余）
- allowed_tools 包含 sensitive 工具但 system_prompt 没说明为何需要
- name / description 跟功能不符（误导）

### P1 关键（→ revise）
- triggers 描述模糊（无法判断什么时候调）
- 步骤跳跃（看完 system_prompt 不知道怎么做）
- 边界不清（不知道什么时候**不该**用此 skill）
- rationale 没说明"为什么沉淀成 skill 比每次现写好"

### P2 次要（仍标 pass，但提一下）
- 文笔可优化
- 例子不足
- 命名可更精准

## 输出格式（**严格 JSON**，无 markdown fence、无解释）

```json
{
  "level": "pass" | "revise" | "redo",
  "summary": "≤150 字总评（用户面板展示）",
  "issues": [
    {"subtask_id": "", "reason": "...", "suggestion": "..."}
  ]
}
```

约束：
- `level=pass` 表示提案合格可推到用户审批；`revise` 让生执重产；`redo` 是直拒（提案没价值或严重问题）
- `summary` 中文、第一人称客观陈述（不要"建议..."这种委婉，直接说"prompt 步骤跳跃"）
- 如果是 SKIP 的 prior 输入（生执判定不值得做），直接输出 `{"level":"pass","summary":"生执判定无需提案","issues":[]}`
"""


def _extract_prop_id(prior_results: list[str] | None) -> str | None:
    """从生执 propose 的输出里抽 prop_id。

    propose 成功时返回首行 'prop_id=<12hex>'；SKIP 时无 prop_id。
    """
    if not prior_results:
        return None
    for pr in prior_results:
        m = re.search(r"prop_id=([0-9a-f]{12})", pr)
        if m:
            return m.group(1)
    return None


def _is_skip_prior(prior_results: list[str] | None) -> bool:
    """前序生执 propose 是 SKIP（没产出提案）。"""
    if not prior_results:
        return False
    return any("SKIP:" in pr for pr in prior_results)


def _parse_review_json(text: str) -> dict | None:
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
    s, e = text.find("{"), text.rfind("}")
    if 0 <= s < e:
        try:
            return json.loads(text[s:e + 1])
        except Exception:
            pass
    return None


def _level_to_verdict(level: str) -> str:
    """ReviewVerdict.level → skill_proposals.review_verdict 映射。"""
    return {
        "pass": VERDICT_PASS,
        "revise": VERDICT_NEEDS_REVISE,
        "redo": VERDICT_REJECT,
    }.get(level, VERDICT_PASS)


async def review_proposal(
    task: "TaskEdict",
    subtask: "Subtask",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None,
) -> str:
    """死执 review_proposal stage 主入口。

    返回 ReviewVerdict 协议 JSON 字符串（被 _verdict.parse_verdict 消费）。
    同时把 verdict 写到 skill_proposals.review_verdict / review_notes。
    """
    from paimon.session import Session
    from paimon.shades._helpers.runner_helpers import extract_result

    # 1. SKIP 短路：生执说没价值做 skill，直接 pass 不写 verdict
    if _is_skip_prior(prior_results):
        logger.info("[死执·review_proposal] 前序 SKIP，直接 pass")
        return json.dumps({
            "level": "pass",
            "summary": "生执判定无需提案",
            "issues": [],
        }, ensure_ascii=False)

    # 2. 取 prop_id
    prop_id = _extract_prop_id(prior_results)
    if not prop_id:
        logger.warning("[死执·review_proposal] prior_results 无 prop_id，标 redo")
        return json.dumps({
            "level": "redo",
            "summary": "前序未产出 prop_id，无法审",
            "issues": [],
        }, ensure_ascii=False)

    # 3. 读提案
    prop = await irminsul.skill_proposal_get(prop_id)
    if not prop:
        return json.dumps({
            "level": "redo",
            "summary": f"提案 {prop_id} 不存在",
            "issues": [],
        }, ensure_ascii=False)

    # 4. 取现有 skill 列表（重叠检查）
    try:
        existing = await irminsul.skill_list(include_orphaned=False)
        existing_brief = "\n".join(
            f"- {s.name}: {s.description[:80]}" for s in existing[:30]
        ) or "（暂无）"
    except Exception:
        existing_brief = "（读取失败）"

    # 5. 拼 user_message
    user_msg = (
        f"## 待审提案 (prop_id={prop_id})\n\n"
        f"**name**: {prop.name}\n"
        f"**kind**: {prop.kind}"
        + (f"\n**target_skill**: {prop.target_skill}" if prop.kind == "improve" else "")
        + f"\n**description**: {prop.description}\n"
        f"**triggers**: {prop.triggers}\n"
        f"**allowed_tools**: {prop.allowed_tools}\n"
        f"**rationale**: {prop.rationale}\n"
        f"\n**system_prompt**:\n```\n{prop.system_prompt[:3000]}\n```\n"
        f"\n## 现有 skill 列表（重叠检查参考）\n{existing_brief}\n"
        f"\n请按审查维度严格审，输出 ReviewVerdict JSON。"
    )

    temp_session = Session(
        id=f"shades-review-{task.id[:8]}", name="死执·review_proposal",
    )
    temp_session.messages.append({"role": "system", "content": _REVIEW_SYSTEM})

    async for _ in model.chat(
        temp_session, user_msg,
        component="死执·review_proposal", purpose="审 skill 提案",
    ):
        pass
    raw = extract_result(temp_session)

    # 6. 解析 + 写回 skill_proposals
    obj = _parse_review_json(raw)
    if not obj or not isinstance(obj, dict):
        logger.warning("[死执·review_proposal] JSON 解析失败，默认 revise")
        obj = {"level": "revise", "summary": "评审产物 JSON 解析失败", "issues": []}

    level = str(obj.get("level", "")).strip().lower() or "pass"
    if level not in ("pass", "revise", "redo"):
        level = "pass"
    summary = str(obj.get("summary", "")).strip()[:500] or "(无总评)"

    verdict = _level_to_verdict(level)
    try:
        await irminsul.skill_proposal_set_review(
            prop_id, verdict, summary, actor="死执",
        )
    except Exception as e:
        logger.error("[死执·review_proposal] 写 verdict 失败 {}: {}", prop_id, e)

    # 7. 返回 JSON 文本（供 _verdict.parse_verdict 消费）
    out = {
        "level": level,
        "summary": f"[{prop.name}] {summary}",
        "issues": obj.get("issues") or [],
    }
    return json.dumps(out, ensure_ascii=False)
