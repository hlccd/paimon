"""死执·review_proposal — 审 skill 自进化提案的质量。

stage = review_proposal：从 prior_results 解析 prop_id（生执单次最多产出 5 条），
循环每个 prop_id 跑一次 LLM tool-based 质量审，写回 skill_proposals.review_verdict。

审查维度：
1. 草案完整度（system_prompt 不空泛 / triggers 清晰 / 步骤可执行）
2. 跟现有 skill_declarations 是否重叠
3. allowed_tools 是否最小权限（敏感工具是否真需要）
4. 边界是否清晰（什么时候用 / 不该用）

**tool-based 实现**（同生执 propose_skill）：LLM 不输出文本 JSON，
而是调 `submit_review` 工具，参数 schema 强校验。

输出 ReviewVerdict 协议 JSON（供 _verdict.parse_verdict 消费）：
- level: pass / revise / redo（多条审时取最严格）
- summary / issues
每条 prop 的 verdict 已独立写入 skill_proposals 表，多 skill 场景下用户面板
能看到各自不同的 verdict badge。

stage 归属：review_proposal → 死执
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
    from paimon.llm.model import Model


_REVIEW_SYSTEM = """\
你是「死执·review_proposal」，对生执 propose_skill 凝练的 skill 草案做质量审。

## 审查维度

P0 致命（→ redo）：
- system_prompt 完全空泛 / 只是个标题没内容
- 跟现有 skill 高度重叠（功能完全冗余）
- allowed_tools 包含敏感工具但 system_prompt 没说明为何需要
- name / description 跟功能不符（误导）

P1 关键（→ revise）：
- triggers 描述模糊（无法判断什么时候调）
- 步骤跳跃（看完 system_prompt 不知道怎么做）
- 边界不清（不知道什么时候**不该**用此 skill）

P2 次要（→ pass，仍可在 issues 里提）：
- 文笔可优化 / 例子不足 / 命名可更精准

## 行动

看完提案后**必须调 `submit_review` 工具**提交裁决——这是唯一的输出方式。
不要先写一段分析再调工具，直接调即可。
"""


_REVIEW_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_review",
        "description": (
            "提交 skill 提案的审查裁决。看完待审提案后必须调此工具——"
            "这是唯一允许的输出方式，不要用文本回复。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "enum": ["pass", "revise", "redo"],
                    "description": (
                        "pass = 提案合格推到用户审批；"
                        "revise = 生执需要重产（P1 关键问题）；"
                        "redo = 直拒（P0 致命问题或提案没价值）。"
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "≤150 字客观陈述（用户面板展示）。"
                        "如 'prompt 步骤跳跃且 triggers 模糊'，不要委婉。"
                    ),
                },
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "具体问题",
                            },
                            "suggestion": {
                                "type": "string",
                                "description": "改进建议（可选）",
                            },
                        },
                        "required": ["reason"],
                    },
                    "description": "具体问题列表。pass 可填 []。",
                },
            },
            "required": ["level", "summary"],
        },
    },
}


def _extract_prop_ids(prior_results: list[str] | None) -> list[str]:
    """从生执 propose 的输出里抽全部 prop_id（生执单次最多产出 5 个）。

    propose 成功时返回多行 'prop_id=<12hex> name=<x>'；SKIP 时返空 list。
    保持插入顺序去重。
    """
    if not prior_results:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for pr in prior_results:
        for m in re.finditer(r"prop_id=([0-9a-f]{12})", pr):
            pid = m.group(1)
            if pid not in seen:
                seen.add(pid)
                out.append(pid)
    return out


def _is_skip_prior(prior_results: list[str] | None) -> bool:
    """前序生执 propose 是 SKIP（没产出提案）。"""
    if not prior_results:
        return False
    return any("SKIP:" in pr for pr in prior_results)


def _level_to_verdict(level: str) -> str:
    """ReviewVerdict.level → skill_proposals.review_verdict 映射。"""
    return {
        "pass": VERDICT_PASS,
        "revise": VERDICT_NEEDS_REVISE,
        "redo": VERDICT_REJECT,
    }.get(level, VERDICT_PASS)


async def _review_single(
    prop_id: str,
    task_id_short: str,
    model: "Model",
    irminsul: "Irminsul",
    existing_brief: str,
) -> dict:
    """审单条提案：跑一次 LLM tool loop → 写回 verdict → 返 ReviewVerdict dict。"""
    from paimon.session import Session

    prop = await irminsul.skill_proposal_get(prop_id)
    if not prop:
        return {
            "level": "redo",
            "summary": f"[{prop_id}] 提案不存在",
            "issues": [],
        }

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
        f"\n请按审查维度严格审，调 `submit_review` 工具提交裁决。"
    )

    review_state: dict = {
        "level": None,
        "summary": None,
        "issues": None,
        "tool_error": None,
    }

    async def _executor(name: str, args_str: str) -> str:
        if name != "submit_review":
            return f"错误：未知工具 {name}"
        if review_state["level"]:
            return (
                f"已提交裁决 level={review_state['level']}，请勿重复调用。"
                "回 'OK' 结束本次任务。"
            )
        try:
            obj = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError as e:
            err = f"参数 JSON 解析失败：{e}"
            review_state["tool_error"] = err
            return f"参数错误：{err}"

        level = str(obj.get("level", "")).strip().lower()
        if level not in ("pass", "revise", "redo"):
            err = f"level 必须是 pass / revise / redo，得 {level!r}"
            review_state["tool_error"] = err
            return f"参数错误：{err}"

        summary = str(obj.get("summary", "")).strip()[:500]
        if not summary:
            err = "summary 必填"
            review_state["tool_error"] = err
            return f"参数错误：{err}"

        issues_raw = obj.get("issues")
        if isinstance(issues_raw, list):
            issues = [
                {
                    "reason": str(i.get("reason", "")).strip()[:200],
                    "suggestion": str(i.get("suggestion", "")).strip()[:200],
                }
                for i in issues_raw if isinstance(i, dict) and i.get("reason")
            ]
        else:
            issues = []

        review_state["level"] = level
        review_state["summary"] = summary
        review_state["issues"] = issues
        logger.info(
            "[死执·review_proposal] 提交裁决 prop_id={} level={} issues={}",
            prop_id, level, len(issues),
        )
        return (
            f"裁决已记录：level={level}, summary 长度={len(summary)} 字, "
            f"issues={len(issues)} 项。本次任务完成，回一句 'OK' 结束即可。"
        )

    temp_session = Session(
        id=f"shades-review-{task_id_short}-{prop_id[:6]}",
        name="死执·review_proposal",
    )
    temp_session.messages.append({"role": "system", "content": _REVIEW_SYSTEM})

    try:
        async for _ in model.chat(
            temp_session, user_msg,
            tools=[_REVIEW_TOOL_SCHEMA],
            tool_executor=_executor,
            component="死执·review_proposal",
            purpose="审 skill 提案",
        ):
            pass
    except Exception as e:
        logger.warning("[死执·review_proposal] LLM 调用异常 prop_id={}: {}", prop_id, e)
        review_state["level"] = "revise"
        review_state["summary"] = f"LLM 调用异常：{e}"
        review_state["issues"] = []

    if not review_state["level"]:
        if review_state["tool_error"]:
            logger.warning(
                "[死执·review_proposal] 工具参数校验失败 prop_id={}: {}，默认 revise",
                prop_id, review_state["tool_error"][:100],
            )
            review_state["summary"] = f"工具参数校验失败：{review_state['tool_error']}"
        else:
            logger.warning(
                "[死执·review_proposal] LLM 没调工具 prop_id={}，默认 revise 兜底",
                prop_id,
            )
            review_state["summary"] = "LLM 未提交裁决（没调 submit_review 工具）"
        review_state["level"] = "revise"
        review_state["issues"] = []

    level = review_state["level"]
    summary = review_state["summary"] or "(无总评)"
    issues = review_state["issues"] or []

    verdict = _level_to_verdict(level)
    try:
        await irminsul.skill_proposal_set_review(
            prop_id, verdict, summary, actor="死执",
        )
    except Exception as e:
        logger.error("[死执·review_proposal] 写 verdict 失败 {}: {}", prop_id, e)

    return {
        "level": level,
        "summary": f"[{prop.name}] {summary}",
        "issues": issues,
    }


async def review_proposal(
    *,
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None,
    origin_id: str = "",
) -> str:
    """死执 review_proposal stage 主入口（tool-based 实现）。

    返回 ReviewVerdict 协议 JSON 字符串（被 _verdict.parse_verdict 消费）。
    支持生执单次产出多条草案的场景：循环每个 prop_id 各跑一次 LLM 审，
    最终用最严格的 level 作为整体 verdict（任一 redo 整体 redo；
    任一 revise 且无 redo 整体 revise；全 pass 则 pass）。
    每条 prop 的 verdict 已独立写入 skill_proposals 表，多 skill 场景下
    用户面板能看到各自不同的 verdict badge。
    """
    if _is_skip_prior(prior_results):
        logger.info("[死执·review_proposal] 前序 SKIP，直接 pass")
        return json.dumps({
            "level": "pass",
            "summary": "生执判定无需提案",
            "issues": [],
        }, ensure_ascii=False)

    prop_ids = _extract_prop_ids(prior_results)
    if not prop_ids:
        logger.warning("[死执·review_proposal] prior_results 无 prop_id，标 redo")
        return json.dumps({
            "level": "redo",
            "summary": "前序未产出 prop_id，无法审",
            "issues": [],
        }, ensure_ascii=False)

    # 取现有 skill 列表（重叠检查 — 多条共用一份）
    try:
        existing = await irminsul.skill_list(include_orphaned=False)
        existing_brief = "\n".join(
            f"- {s.name}: {s.description[:80]}" for s in existing[:30]
        ) or "（暂无）"
    except Exception:
        existing_brief = "（读取失败）"

    # 循环审每条
    results = []
    for pid in prop_ids:
        r = await _review_single(pid, origin_id[:8], model, irminsul, existing_brief)
        results.append(r)

    # 聚合：取最严格 level（redo > revise > pass）
    _SEVERITY = {"pass": 0, "revise": 1, "redo": 2}
    overall_level = max(results, key=lambda r: _SEVERITY.get(r["level"], 0))["level"]

    if len(results) == 1:
        # 单条：返该条原 dict（向后兼容）
        return json.dumps(results[0], ensure_ascii=False)

    # 多条：合成总评
    summary_lines = [f"共审 {len(results)} 条 skill 草案，整体 {overall_level}："]
    all_issues = []
    for r in results:
        summary_lines.append(f"- {r['summary']} ({r['level']})")
        for it in r.get("issues") or []:
            all_issues.append(it)
    out = {
        "level": overall_level,
        "summary": "\n".join(summary_lines)[:1500],
        "issues": all_issues,
    }
    return json.dumps(out, ensure_ascii=False)
