"""晨星 scout 阶段：plan_info（拆议题）+ collect（调 tool 收资料）。

跑在 council 主 loop 之前。议题简单（主观偏好）时 skip 跳过 collect。

调用图：
    morningstar.run_agents
      └→ _scout.run_scout
           ├→ plan_info（LLM JSON）
           ├→ if skip: 直接返空 background
           └→ collect（LLM tool-loop，浅池 + 受限 tool 白名单）
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from loguru import logger

from .prompts import build_collect_system, build_plan_info_prompt

if TYPE_CHECKING:
    from paimon.llm.model import Model


# scout 工具白名单：仅允许查信息类，禁 exec（议题讨论不触副作用）
_SCOUT_ALLOWED_TOOLS = {"file_ops", "glob", "knowledge", "memory", "topic", "web_search"}

# 信息包硬上限（超截断）
_BACKGROUND_MAX_CHARS = 4000

# 信息需求最多条数
_MAX_INFO_NEEDS = 4


async def run_scout(
    topic: str,
    model: "Model",
    *,
    component: str = "agents",
    on_notice: Callable[[str], Awaitable[None]] | None = None,
    session_id: str = "",
) -> tuple[str, dict]:
    """跑 scout 阶段。

    返 (background, meta)：
      - background：信息包文本（skip 时为空串）
      - meta：{skip: bool, reason: str, info_needs: [...], llm_calls: int}
    """
    meta: dict = {"skip": False, "reason": "", "info_needs": [], "llm_calls": 0}

    # ─── plan_info ───
    try:
        msgs = build_plan_info_prompt(topic)
        text, _ = await model._stream_text(
            msgs, component=component, purpose="晨星·拆议题",
        )
        meta["llm_calls"] += 1
    except Exception as e:
        logger.warning("[晨星·scout] plan_info LLM 异常，跳过 scout: {}", e)
        meta["skip"] = True
        meta["reason"] = f"plan_info LLM 异常: {e}"
        return "", meta

    plan = _safe_parse_json(text)
    skip = bool(plan.get("skip", False))
    reason = str(plan.get("reason", ""))[:120]
    meta["reason"] = reason

    needs_raw = plan.get("info_needs") or []
    info_needs: list[dict] = []
    if isinstance(needs_raw, list):
        for n in needs_raw[:_MAX_INFO_NEEDS]:
            if isinstance(n, dict) and n.get("topic"):
                info_needs.append({
                    "topic": str(n["topic"])[:60],
                    "source_hint": str(n.get("source_hint", ""))[:30],
                })
    meta["info_needs"] = info_needs

    if skip or not info_needs:
        meta["skip"] = True
        if not skip and not info_needs:
            meta["reason"] = meta["reason"] or "无外部信息需求"
        logger.info("[晨星·scout] skip={} reason={!r}", meta["skip"], meta["reason"])
        if on_notice:
            try:
                await on_notice(f"🧭 晨星·议题已明，跳过调研（{meta['reason'][:40]}）")
            except Exception:
                pass
        return "", meta

    # ─── collect ───
    if on_notice:
        try:
            await on_notice(
                f"🔎 晨星·调研 {len(info_needs)} 项资料"
                f"（{', '.join(set(n['source_hint'] for n in info_needs if n['source_hint']))}）"
            )
        except Exception:
            pass

    background = await _run_collect(
        topic, info_needs, model,
        component=component, session_id=session_id, meta=meta,
    )
    if len(background) > _BACKGROUND_MAX_CHARS:
        logger.warning(
            "[晨星·scout] 信息包超长 ({} > {}) 截断",
            len(background), _BACKGROUND_MAX_CHARS,
        )
        background = background[:_BACKGROUND_MAX_CHARS] + "\n\n（信息包过长，已截断）"

    logger.info(
        "[晨星·scout] 完成：{} 项调研 / {} 字背景资料 / {} LLM calls",
        len(info_needs), len(background), meta["llm_calls"],
    )
    return background, meta


def _safe_parse_json(text: str) -> dict:
    """plan_info 输出 JSON 容错解析（剥围栏 + 截大括号）。失败返空 dict 等价于 skip。"""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    s = text.find("{")
    e = text.rfind("}")
    if 0 <= s < e:
        try:
            return json.loads(text[s:e + 1])
        except Exception as e2:
            logger.warning("[晨星·scout] plan_info JSON 解析失败: {} text={!r}", e2, text[:200])
    return {}


async def _run_collect(
    topic: str,
    info_needs: list[dict],
    model: "Model",
    *,
    component: str,
    session_id: str,
    meta: dict,
) -> str:
    """tool-loop 模式跑 collect。复用 paimon.shades._helpers 公共 helper。"""
    from paimon.session import Session
    from paimon.shades._helpers.runner_helpers import extract_result, setup_tools

    system = build_collect_system(info_needs)
    user_msg = (
        f"议题：{topic}\n\n"
        "按 system 里的清单逐项收集，最后输出信息包 markdown。"
    )

    temp_session = Session(
        id=f"agents-scout-{session_id[:8] if session_id else 'tmp'}",
        name="晨星·调研",
    )
    temp_session.messages.append({"role": "system", "content": system})

    tools, executor = setup_tools(temp_session, allowed_tools=_SCOUT_ALLOWED_TOOLS)

    try:
        async for _ in model.chat(
            temp_session, user_msg,
            tools=tools, tool_executor=executor,
            component=component, purpose="晨星·调研",
        ):
            pass
        meta["llm_calls"] += 1   # 粗略计 1 次（实际 tool-loop 内多轮但归并 1 次主调用）
    except Exception as e:
        logger.error("[晨星·scout] collect tool-loop 异常: {}", e)
        return f"（调研异常：{str(e)[:200]}）"

    return extract_result(temp_session) or "（调研结果为空）"
