"""四影管线公共运行时 helper（无主，各影共享）。

跟七神解耦的独立实现：
- read_skill_body：读 SKILL.md 正文 + ${CLAUDE_SKILL_DIR} 替换
- setup_tools：构造 (tools list, executor)
- extract_result：5 级 fallback 抓 LLM 末轮文本
- load_feedback_memories_block：拉 feedback 类记忆
- invoke_skill_workflow：统一 skill 驱动工作流入口

使用方：生执 produce_*（spec/design/code/_simple）+ 死执 review。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.session import Session


_SKILL_BODY_CACHE: dict[str, str] = {}


def read_skill_body(skill_name: str) -> str:
    """读 skills/{name}/SKILL.md 的正文（去掉 YAML frontmatter）。缓存到进程。

    Claude Code 兼容：${CLAUDE_SKILL_DIR} → skill 绝对路径。
    """
    if skill_name in _SKILL_BODY_CACHE:
        return _SKILL_BODY_CACHE[skill_name]
    # paimon/shades/_helpers/runner_helpers.py → project_root = paimon/../..
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    skill_dir = project_root / "skills" / skill_name
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"skill 不存在: {skill_path}")
    text = skill_path.read_text(encoding="utf-8")
    # strip YAML frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            text = text[end + 4:].lstrip()
    text = text.replace("${CLAUDE_SKILL_DIR}", str(skill_dir))
    _SKILL_BODY_CACHE[skill_name] = text
    return text


def project_root_repr() -> str:
    """返回项目根的相对引用（"."），避免绝对路径进入 LLM system prompt。"""
    return "."


def setup_tools(
    session: "Session",
    *,
    allowed_tools: set[str] | None = None,
):
    """构造 tool-loop 所需的 (tools list, executor)。

    allowed_tools=None 表示放开所有工具（只在测试 / debug 用）。
    """
    from paimon.state import state
    if not state.tool_registry:
        return None, None

    from paimon.tools.base import ToolContext
    all_tools = state.tool_registry.to_openai_tools()
    if allowed_tools:
        tools = [t for t in all_tools if t["function"]["name"] in allowed_tools]
    else:
        tools = all_tools

    ctx = ToolContext(
        registry=state.tool_registry, channel=None, chat_id="", session=session,
    )

    async def _executor(name: str, arguments: str) -> str:
        return await state.tool_registry.execute(name, arguments, ctx)

    return tools or None, _executor


def extract_result(session: "Session") -> str:
    """从 session 末尾抓 LLM 输出。5 级 fallback + 落空诊断日志。

    跟 archons/base.py:_extract_result 等价实现。
    """
    # 1: clean final assistant
    for msg in reversed(session.messages):
        if msg.get("role") == "assistant" and not msg.get("tool_calls"):
            content = (msg.get("content") or "").strip()
            if content:
                return content

    # 2: tool_calls 同消息的 content
    for msg in reversed(session.messages):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            content = (msg.get("content") or "").strip()
            if content:
                logger.warning(
                    "[shades.extract_result] fallback L2: 末轮 LLM 没有纯 final，用 tool_calls 同消息 content (len={})",
                    len(content),
                )
                return content

    # 3: reasoning_content
    for msg in reversed(session.messages):
        if msg.get("role") == "assistant":
            reasoning = (msg.get("reasoning_content") or "").strip()
            if reasoning:
                logger.warning(
                    "[shades.extract_result] fallback L3: 末轮仅 reasoning_content (len={})",
                    len(reasoning),
                )
                return f"[LLM 在思考流输出，未给出 final content]\n{reasoning[:2000]}"

    # 4: 末条 tool message
    for msg in reversed(session.messages):
        if msg.get("role") == "tool":
            content = (msg.get("content") or "").strip()
            if content:
                logger.warning(
                    "[shades.extract_result] fallback L4: 末轮无 LLM 产出，回退末条 tool result",
                )
                return f"[来自工具调用结果，LLM 未做最终总结]\n{content[:2500]}"

    # 5: 全空
    roles = [m.get("role") for m in session.messages]
    logger.warning(
        "[shades.extract_result] 全部 fallback 落空 session={} msgs={} roles={}",
        session.id, len(session.messages), roles[-10:],
    )
    return ""


async def load_feedback_memories_block(
    irminsul: "Irminsul | None",
    limit: int = 15,
    body_max: int = 400,
) -> str:
    """拉 feedback 类记忆 → 拼成 markdown 段落注入 system prompt 末尾。

    跟 archons/base.py:_load_feedback_memories_block 等价。
    四影管线 execute 路径用，cron 路径不用。
    """
    if irminsul is None:
        return ""
    try:
        metas = await irminsul.memory_list(mem_type="feedback", limit=limit)
    except Exception as e:
        logger.debug("[shades.feedback] 读记忆失败（忽略）: {}", e)
        return ""
    if not metas:
        return ""

    metas.sort(key=lambda m: (m.created_at or 0, m.id))

    items: list[str] = []
    for meta in metas[:limit]:
        try:
            mem = await irminsul.memory_get(meta.id)
        except Exception:
            continue
        if mem is None:
            continue
        body = (mem.body or "").strip()
        if not body:
            continue
        body = body.replace("\r\n", " ").replace("\n", " ").replace("\t", " ")
        if len(body) > body_max:
            body = body[:body_max].rstrip() + "..."
        items.append(f"- {body}")
    if not items:
        return ""

    return (
        "\n\n## 用户行为反馈（跨会话 feedback 记忆，视为硬约束）\n"
        "以下来自 `/remember` 或时执自动反思，代表用户对助手行为的明确纠正："
        "\n" + "\n".join(items)
        + "\n\n（这些是背景约束，不要主动复述、不要把它们当成当前任务描述。）"
    )


async def invoke_skill_workflow(
    *,
    skill_name: str,
    user_message: str,
    model,
    session_name: str,
    component: str,
    purpose: str,
    allowed_tools: set[str] | None = None,
    framing: str = "",
) -> str:
    """统一 skill 驱动工作流：读 SKILL.md body 作为 system prompt，启动 tool-loop。

    跟 archons/base.py:_invoke_skill_workflow 等价（独立实现，不继承）。
    使用方：生执 produce_*（spec/design/code）+ 死执 review。
    """
    from paimon.session import Session
    try:
        skill_body = read_skill_body(skill_name)
    except FileNotFoundError as e:
        logger.error("[shades.invoke_skill_workflow] {}", e)
        return f"skill {skill_name} 不存在"

    system = skill_body
    if framing:
        system += "\n\n---\n\n" + framing

    temp_session = Session(
        id=f"{skill_name}-{session_name}", name=f"四影·{skill_name}",
    )
    temp_session.messages.append({"role": "system", "content": system})

    tools, executor = setup_tools(temp_session, allowed_tools=allowed_tools)
    async for _ in model.chat(
        temp_session, user_message,
        tools=tools, tool_executor=executor,
        component=component, purpose=purpose,
    ):
        pass

    return extract_result(temp_session)
