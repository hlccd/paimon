"""
派蒙·意图粗分类

根据用户消息 + 可用 Skills + 会话上下文，判断任务类型：
- chat: 闲聊/问候/知识问答 → 派蒙直接回复
- skill:<name>: 简单任务，某个 skill 可处理 → 天使调度
- complex: 复杂任务，需多步骤协作 → 四影（未实现时回退普通对话）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.angels.registry import SkillRegistry
    from paimon.llm.model import Model
    from paimon.session import Session


@dataclass
class IntentResult:
    kind: str  # "chat" | "skill" | "complex"
    skill_name: str = ""


_CLASSIFY_PROMPT = """\
你是意图分类器，负责判断用户消息的任务类型。

## 可用 Skills
{skill_catalog}

## 分类规则
1. **chat** — 闲聊、问候、简单知识问答（一两句话能回答的）、日常对话
2. **skill:<name>** — 用户的请求明确可以被某个 skill 处理（例如发了该 skill 触发域名的链接）
3. **complex** — 以下任一情况：
   - 需要深度分析、多角度论述、结构化输出的任务（如"分析优缺点"、"对比A和B"、"写一份方案/报告"）
   - 需要多个步骤才能完成的任务（如"帮我做三件事"、"先...然后...最后..."）
   - 需要使用工具（执行代码、读取文件、搜索等）才能完成的任务
   - 涉及项目分析、代码审查、架构评估等需要深度思考的任务

## 注意
- 简单问答（"Python是什么"、"今天星期几"）→ chat，不要判成 complex
- 只有用户意图明确匹配某个 skill 时才返回 skill，不要猜测
- 拿不准是 chat 还是 complex 时，偏向 complex（宁可多做不要少做）
- 会话历史可作为参考，保持多轮连贯

只输出分类标签，如: chat 或 skill:bili 或 complex
不要输出任何其他内容。"""


async def classify_intent(
    model: Model,
    session: Session,
    user_input: str,
    skill_registry: SkillRegistry | None,
) -> IntentResult:
    if not skill_registry or not skill_registry.skills:
        return IntentResult(kind="chat")

    catalog_lines = []
    for s in skill_registry.list_all():
        line = f"- {s.name}: {s.description}"
        if s.triggers:
            line += f" (触发特征: {s.triggers})"
        catalog_lines.append(line)
    catalog = "\n".join(catalog_lines)

    system = _CLASSIFY_PROMPT.format(skill_catalog=catalog)

    context_msgs = []
    recent = [m for m in session.messages if m.get("role") in ("user", "assistant")][-4:]
    for m in recent:
        content = m.get("content", "")
        if content and len(content) > 200:
            content = content[:200] + "..."
        if content:
            context_msgs.append({"role": m["role"], "content": content})

    messages = [
        {"role": "system", "content": system},
        *context_msgs,
        {"role": "user", "content": user_input},
    ]

    try:
        raw, usage = await model._stream_text(messages)
        await model._record_primogem(session.id, "paimon", usage, purpose="意图分类")
        label = raw.strip().lower()
    except Exception as e:
        logger.warning("[派蒙·意图] 分类失败，回退到 chat: {}", e)
        return IntentResult(kind="chat")

    if label.startswith("skill:"):
        skill_name = label[6:].strip()
        if skill_registry.exists(skill_name):
            logger.info("[派蒙·意图] skill:{}", skill_name)
            return IntentResult(kind="skill", skill_name=skill_name)
        logger.warning("[派蒙·意图] 分类返回未知 skill '{}', 回退 chat", skill_name)
        return IntentResult(kind="chat")

    if label == "complex":
        logger.info("[派蒙·意图] complex → 四影管线")
        return IntentResult(kind="complex")

    logger.info("[派蒙·意图] chat")
    return IntentResult(kind="chat")
