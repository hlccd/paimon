"""时执 archive 收尾 hook：浅池 LLM 判 should_propose + 直接调 propose+review 链。

跟用户主动 `/evolve` 的区别：
- `/evolve` 走完整四影管线（plan → propose_skill → review_proposal）
- archive hook 跳过 plan，直接调 propose_skill / review_proposal 函数（节省 LLM 调用）

借鉴 hermes-agent：
- 严格判定门槛，绝大多数 task 应返 should_propose=false（避免每次 archive 都跑 propose）
- 短路退出：should_propose=false → 0 后续调用
- max 调用数：should_propose 判 1 + propose 1 + review 1 = 3 次浅池 call

防递归：如果 task.description 含 _PROPOSE_TRIGGER_MARKER，archive 时跳过 hook
（避免 archive hook 自己启动的 propose task 再次触发 hook）。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask, TaskEdict


# 防递归 marker：archive hook 自己启动的 propose flow 不再触发自身
PROPOSE_TRIGGER_MARKER = "[propose-triggered]"


_TRIGGER_PROMPT = """\
你看下面这个任务的执行摘要，判断是否值得从中凝练一个**可复用的 skill** 沉淀下来。

判断标准（**严格**，绝大多数 task 应返 false）：
- ✓ 任务多步（≥4 步）且方法**可复用**（用户未来很可能用同样模式再做）
- ✓ 解决了一类问题，不是一次性查询
- ✓ 跟现有 skill 不重叠
- ✗ 单次问答 / 闲聊 / 太琐碎（< 4 步搞定）→ false
- ✗ 内容是个人临时需求（"今天吃啥"）→ false
- ✗ 涉及个人隐私 / 临时凭据 → false

只输出 JSON：{"propose": true/false, "reason": "≤30 字"}
不要 markdown fence、不要任何额外文字。
"""


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


def _build_summary_context(
    task: "TaskEdict", subtasks: list["Subtask"], summary: dict,
) -> str:
    """拼任务执行摘要给浅池 LLM 看（should_propose 判定 + propose 凝练共用）。"""
    completed = [s for s in subtasks if s.status == "completed"][:6]
    sub_lines = "\n".join(
        f"- [{s.assignee}] {s.description[:120]}\n  → {(s.result or '')[:300]}"
        for s in completed
    )
    return (
        f"## 任务\n{task.title}\n\n"
        f"## 描述\n{task.description[:500]}\n\n"
        f"## 子任务（{summary['completed']} 完成 / {summary['failed']} 失败）\n"
        f"{sub_lines}\n"
    )


async def maybe_trigger_propose(
    task: "TaskEdict",
    subtasks: list["Subtask"],
    summary: dict,
    irminsul: "Irminsul",
) -> None:
    """archive 收尾 hook 主入口。

    流程：
    1. 防递归（task.description 含 marker 跳过）
    2. 失败 / 无产出 task 跳过
    3. 浅池 LLM 判 should_propose（1 call，绝大多数返 false 后短路）
    4. yes → 直接调 propose_skill + review_proposal 函数链落 skill_proposals 表

    所有异常吞掉（archive hook 不能阻塞主管线归档）。
    """
    # 1. 防递归
    if PROPOSE_TRIGGER_MARKER in task.description:
        return

    # 2. 失败 / 无产出
    if summary.get("completed", 0) < 1:
        return
    if summary.get("rounds", 0) < 1:
        return

    # 3. 浅池判 should_propose
    from paimon.state import state as _state
    if not _state.model:
        return

    context = _build_summary_context(task, subtasks, summary)
    try:
        raw, _ = await _state.model._stream_text(
            messages=[
                {"role": "system", "content": _TRIGGER_PROMPT},
                {"role": "user", "content": context},
            ],
            component="时执·propose 触发",
            purpose="should_propose",
        )
    except Exception as e:
        logger.debug("[时执·propose 触发] LLM 调用失败：{}", e)
        return

    obj = _parse_trigger_json(raw)
    if not obj or not obj.get("propose"):
        return  # 短路退出（绝大多数 task 应走这条）

    reason = str(obj.get("reason", ""))[:80]
    logger.info(
        "[时执·propose 触发] 判定 should_propose=true task={} reason={!r}",
        task.id[:8], reason,
    )

    # 4. 调 propose + review 函数链
    try:
        await _run_propose_review_chain(task, context, reason, irminsul, _state.model)
    except Exception as e:
        logger.warning("[时执·propose 触发] 提案产生异常：{}", e)


async def _run_propose_review_chain(
    origin_task: "TaskEdict",
    context: str,
    trigger_reason: str,
    irminsul: "Irminsul",
    model,
) -> None:
    """直接调 propose_skill + review_proposal 函数（不走 plan/pipeline）。"""
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.shades.naberius.propose import propose_skill
    from paimon.shades.jonova.review_proposal import review_proposal

    # 合成 task：description 加 marker 确保此 task 即便走 archive 也不会再触发自身
    synthetic_task_id = uuid.uuid4().hex
    now = time.time()
    syn_task = TaskEdict(
        id=synthetic_task_id,
        title=f"自进化触发：{origin_task.title[:60]}",
        description=(
            f"{PROPOSE_TRIGGER_MARKER}\n"
            f"基于已完成任务 {origin_task.id[:8]} 凝练 skill 草案。\n"
            f"触发理由：{trigger_reason}\n\n{context}"
        ),
        creator="时执·propose 触发",
        status="running",
        session_id=origin_task.session_id,
        created_at=now, updated_at=now,
    )

    propose_sub = Subtask(
        id=f"prop-{synthetic_task_id[:8]}",
        task_id=synthetic_task_id, parent_id=None,
        assignee="propose_skill",
        description="凝练 skill 草案",
        status="running",
        created_at=now, updated_at=now,
    )

    propose_result = await propose_skill(
        syn_task, propose_sub, model, irminsul, prior_results=None,
    )
    logger.info(
        "[时执·propose 触发] propose 完成 origin_task={} result={!r}",
        origin_task.id[:8], propose_result[:100],
    )

    # SKIP 路径：propose 自己判定不值得做，结束
    if propose_result.startswith("SKIP:"):
        return

    # 调 review_proposal 自动审
    review_sub = Subtask(
        id=f"rev-{synthetic_task_id[:8]}",
        task_id=synthetic_task_id, parent_id=None,
        assignee="review_proposal",
        description="审 propose 提案",
        status="running",
        created_at=now, updated_at=now,
    )
    review_result = await review_proposal(
        syn_task, review_sub, model, irminsul,
        prior_results=[propose_result],
    )
    logger.info(
        "[时执·propose 触发] review 完成 origin_task={} verdict_text={!r}",
        origin_task.id[:8], review_result[:100],
    )
