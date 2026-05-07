"""讨论循环：assemble → dispatch + speak loop → synthesize。

LLM 调用上限 30 次（含 assemble + 多轮 dispatch/speak + synthesize）；
发言上限 12 轮（避免 dispatch 死循环）；
连续 3 次同角色判死锁提前收敛。
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loguru import logger

from .prompts import (
    build_assemble_prompt, build_dispatch_prompt,
    build_speak_prompt, build_synthesize_prompt,
)
from .roles import ROLES


MAX_LLM_CALLS = 30        # 总 LLM 调用数（assemble + dispatch + speak + synthesize）
MAX_TURNS = 12            # 发言轮次上限
DEADLOCK_REPEAT_K = 3     # 连续 K 个发言来自同一角色 → 死锁


@dataclass
class CouncilResult:
    members: list[str]
    opening: str
    history: list[dict] = field(default_factory=list)
    final: str = ""
    llm_calls: int = 0
    converge_reason: str = ""   # consensus / deadlock / max_calls / max_turns / error


def _safe_parse_json(text: str, default: dict) -> dict:
    """LLM 输出 JSON 容错解析：剥 markdown 围栏 / 截首尾大括号 / 试 json.loads。"""
    text = (text or "").strip()
    if text.startswith("```"):
        # 剥 ```json ... ``` 围栏（按行）
        lines = text.split("\n")
        text = "\n".join(l for l in lines if not l.strip().startswith("```"))
        text = text.strip()
    # 直接尝试
    try:
        return json.loads(text)
    except Exception:
        pass
    # 兜底：找第一个 { 和最后一个 } 截 substring（应对 LLM 在 JSON 前后加废话的情况）
    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1])
        except Exception as e:
            logger.warning("[晨星] JSON 解析失败用 default：{} | text={!r}", e, text[:200])
    else:
        logger.warning("[晨星] JSON 无法定位用 default：text={!r}", text[:200])
    return default


def _is_deadlock(history: list[dict]) -> bool:
    """连续 K 个发言来自同一角色 → 死锁。"""
    if len(history) < DEADLOCK_REPEAT_K:
        return False
    last_keys = [h["role_key"] for h in history[-DEADLOCK_REPEAT_K:]]
    return len(set(last_keys)) == 1


async def run_council(
    topic: str,
    model,
    *,
    component: str = "agents",
    on_speak: Callable[[str, str, str], Awaitable[None]] | None = None,
    session_id: str = "",
) -> CouncilResult:
    """跑一次多视角讨论。

    on_speak(role_key, role_name, content) —— 每个发言完毕后回调（流式 reply 用）。
    session_id —— 落 primogem 用（不传则空字符串，原石只记 component/purpose 不记 session）。
    """
    llm_calls = 0
    history: list[dict] = []

    # ─── 1. assemble：晨星挑角色 + 写开题 ───
    msgs = build_assemble_prompt(topic)
    text, _ = await model._stream_text(msgs, component=component, purpose="晨星·召集")
    llm_calls += 1
    plan = _safe_parse_json(text, default={"members": [], "opening": ""})
    # 校验 + 去重 + 截 5 个（LLM 可能返重复 key）
    seen: set[str] = set()
    members: list[str] = []
    for m in plan.get("members", []):
        if not isinstance(m, str) or m in seen or m not in ROLES:
            continue
        members.append(m)
        seen.add(m)
        if len(members) >= 5:
            break
    opening = (plan.get("opening") or "")[:300]
    if len(members) < 2:
        # 兜底：用结构性 3 个保底
        members = ["requirement", "architecture", "review"]
        logger.info("[晨星] 召集失败兜底：{}", members)
    if not opening:
        opening = topic[:200]
    logger.info(
        "[晨星] 议题={!r} 召集 {} 天使={} 开题={} 字",
        topic[:60], len(members), members, len(opening),
    )

    # ─── 2. discussion loop ───
    converge_reason = "max_turns"
    for turn in range(MAX_TURNS):
        # 进入循环还要消耗：dispatch (1) + speak (1) + 留给 synthesize (1) = 3 calls
        # 提前判停防超 MAX_LLM_CALLS
        if llm_calls + 3 > MAX_LLM_CALLS:
            converge_reason = "max_calls"
            break

        # dispatch
        msgs = build_dispatch_prompt(
            topic, opening, history, members, turn + 1, MAX_TURNS,
        )
        text, _ = await model._stream_text(msgs, component=component, purpose="晨星·调度")
        llm_calls += 1
        decision = _safe_parse_json(text, default={
            "next_speaker": members[turn % len(members)],
            "instruction": "请基于已有发言给出你的视角观点",
            "should_converge": False,
        })
        # should_converge 健壮解析：LLM 可能返字符串 "true"/"false" 或 bool
        sc_raw = decision.get("should_converge")
        if isinstance(sc_raw, str):
            should_converge = sc_raw.strip().lower() in ("true", "yes", "1")
        else:
            should_converge = bool(sc_raw)
        if should_converge:
            converge_reason = "consensus"
            logger.info("[晨星] 收敛(consensus)：{}", str(decision.get("reason", ""))[:80])
            break

        next_role = decision.get("next_speaker")
        if next_role not in ROLES or next_role not in members:
            next_role = members[turn % len(members)]   # 兜底轮转
        instruction = (decision.get("instruction") or "请发表你的观点")[:200]

        # speak
        role_meta = ROLES[next_role]
        msgs = build_speak_prompt(
            role_system=role_meta["system"],
            topic=topic, opening=opening,
            history=history, instruction=instruction,
        )
        utterance, _ = await model._stream_text(
            msgs, component=component, purpose=f"天使·{role_meta['name']}",
        )
        llm_calls += 1
        utterance = (utterance or "").strip()[:400]
        if not utterance:
            logger.warning("[晨星] {} 空发言，跳过", role_meta["name"])
            continue
        history.append({
            "role_key": next_role, "role_name": role_meta["name"],
            "content": utterance, "instruction": instruction,
        })
        if on_speak:
            try:
                await on_speak(next_role, role_meta["name"], utterance)
            except Exception as e:
                logger.warning("[晨星] on_speak 回调异常: {}", e)

        if _is_deadlock(history):
            converge_reason = "deadlock"
            logger.info("[晨星] 死锁检测：连续 {} 轮同角色", DEADLOCK_REPEAT_K)
            break

    # ─── 3. synthesize ───
    final = ""
    try:
        msgs = build_synthesize_prompt(topic, opening, history)
        final, _ = await model._stream_text(msgs, component=component, purpose="晨星·综合")
        llm_calls += 1
    except Exception as e:
        logger.error("[晨星] synthesize 异常: {}", e)
        converge_reason = "error"
        final = "（综合环节异常，仅保留讨论 history）"

    logger.info(
        "[晨星] 完成：{} 轮发言 / {} LLM / 收敛={}",
        len(history), llm_calls, converge_reason,
    )
    return CouncilResult(
        members=members, opening=opening, history=history,
        final=final, llm_calls=llm_calls, converge_reason=converge_reason,
    )
