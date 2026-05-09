"""自进化提案触发器：浅池 LLM 判 should_propose + 调生执 / 死执函数链。

唯一活跃入口：
- `maybe_nudge_session(session, irminsul)` — chat / skill 路径完成时调
  （每 NUDGE_THRESHOLD 条 user 消息满阈值才跑判定，借鉴 hermes-agent 计数器）

借鉴 hermes-agent：
- 严格判定门槛，绝大多数情况返 should_propose=false（短路退出）
- max 调用数：should_propose 判 1 + propose 1 + review N 次浅池 call
"""
from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.session import Session


# nudge 阈值：每 N 条 user 消息触发一次 should_propose 判定
# 5 条是 hermes-agent 的实证默认值，平衡"够多对话才能识别可复用模式"和"浅池调用频率"
NUDGE_THRESHOLD = 5


def _parse_trigger_json(text: str) -> dict | None:
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


async def run_propose_review_chain(
    *,
    title: str,
    description: str,
    session_id: str,
    origin_id: str,
    irminsul: "Irminsul",
    model,
) -> list[str]:
    """直接调生执 propose_skill + 死执 review_proposal。

    返本次产生的全部 prop_id 列表（生执单次最多 5 个），SKIP 路径返空列表。
    """
    import re
    from paimon.shades.naberius.propose import propose_skill
    from paimon.shades.jonova.review_proposal import review_proposal

    propose_result = await propose_skill(
        title=title,
        description=description,
        session_id=session_id,
        origin_id=origin_id,
        model=model,
        irminsul=irminsul,
        prior_results=None,
    )
    logger.info(
        "[自进化触发] propose 完成 origin={} result={!r}",
        origin_id[:8], propose_result[:100],
    )

    # SKIP 路径：propose 自己判定不值得做，结束
    if propose_result.startswith("SKIP:"):
        return []

    # 解析所有 prop_id：propose_skill 成功路径多行 'prop_id=<12hex> name=<x>'
    prop_ids: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"prop_id=([0-9a-f]{12})", propose_result):
        pid = m.group(1)
        if pid not in seen:
            seen.add(pid)
            prop_ids.append(pid)
    if not prop_ids:
        logger.warning(
            "[自进化触发] propose 输出无 prop_id origin={}", origin_id[:8],
        )
        return []

    # 调死执 review_proposal 自动审
    review_result = await review_proposal(
        model=model,
        irminsul=irminsul,
        prior_results=[propose_result],
        origin_id=origin_id,
    )
    logger.info(
        "[自进化触发] review 完成 origin={} verdict_text={!r}",
        origin_id[:8], review_result[:100],
    )

    return prop_ids


# ─── chat 路径 nudge 触发器（hermes 风格计数器）────────────────────────────────

_NUDGE_TRIGGER_PROMPT = """\
你看下面这段最近的会话历史，判断用户是否在反复做某种**可复用的任务**，值得凝练成 skill。

判断标准（**严格**，绝大多数会话应返 false）：
- ✓ 用户多次（≥2 次）做相同**模式**的事（如"问 X 游戏新角色配队"出现 2 次以上）
- ✓ 任务方法**可复用**：未来很可能再来一次同样的需求
- ✓ 跟现有 skill 不重叠
- ✗ 单次问答 / 闲聊 / 一次性查询 → false
- ✗ 内容是临时事项（"今晚吃啥" / "周二有空吗"）→ false
- ✗ 个人隐私 / 临时凭据 → false

只输出 JSON：{"propose": true/false, "reason": "≤30 字"}
不要 markdown fence、不要任何额外文字。
"""


async def maybe_nudge_session(session: "Session", irminsul: "Irminsul") -> None:
    """chat / skill 路径完成后调（fire-and-forget）。

    每 NUDGE_THRESHOLD 条 user 消息满阈值跑一次浅池 should_propose 判定；
    判定 yes 则跑 propose+review 链产出提案落 skill_proposals 域。

    所有异常吞掉（不能影响主流程；用户 chat 已经回复完了）。
    """
    try:
        session._nudge_user_turns += 1
    except AttributeError:
        # 老 session 可能没此字段（重启前创建的），直接初始化
        session._nudge_user_turns = 1

    if session._nudge_user_turns < NUDGE_THRESHOLD:
        logger.debug(
            "[chat·nudge propose] session={} 计数 {}/{}",
            session.id[:8], session._nudge_user_turns, NUDGE_THRESHOLD,
        )
        return

    # reset 计数器（即便后面判 false，也不应连续每条都跑判定）
    session._nudge_user_turns = 0

    from paimon.state import state as _state
    if not _state.model:
        return

    # 拼最近会话 context（最多 30 条，每条 ≤300 字）
    recent = session.messages[-30:] if len(session.messages) > 1 else []
    lines = []
    for m in recent:
        role = m.get("role")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            lines.append(f"[{role}] {str(content)[:300]}")
    if not lines:
        return
    context = "\n".join(lines)[:5000]

    # 浅池 1 call 判 should_propose
    try:
        raw, _ = await _state.model._stream_text(
            messages=[
                {"role": "system", "content": _NUDGE_TRIGGER_PROMPT},
                {"role": "user", "content": f"## 最近 {len(recent)} 条会话\n\n{context}"},
            ],
            component="自进化触发",
            purpose="should_propose_chat",
        )
    except Exception as e:
        logger.debug("[chat·nudge propose] LLM 调用失败：{}", e)
        return

    obj = _parse_trigger_json(raw)
    if not obj or not obj.get("propose"):
        logger.debug(
            "[chat·nudge propose] 判定 false session={} reason={!r}",
            session.id[:8], (obj or {}).get("reason", ""),
        )
        return

    reason = str(obj.get("reason", ""))[:80]
    logger.info(
        "[chat·nudge propose] 判定 should_propose=true session={} reason={!r}",
        session.id[:8], reason,
    )

    origin_id = uuid.uuid4().hex
    title = f"chat 自进化触发：{(session.name or '会话')[:50]}"
    description = (
        f"基于会话 {session.id[:8]} 的最近 {len(recent)} 条对话凝练 skill。\n"
        f"触发理由：{reason}\n\n{context}"
    )

    try:
        await run_propose_review_chain(
            title=title,
            description=description,
            session_id=session.id,
            origin_id=origin_id,
            irminsul=irminsul,
            model=_state.model,
        )
    except Exception as e:
        logger.warning("[chat·nudge propose] 链路异常：{}", e)
