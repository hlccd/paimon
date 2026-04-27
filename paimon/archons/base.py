"""七神基类 — 所有 Archon 的公共接口和工具过滤"""
from __future__ import annotations

import abc
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.llm.model import Model
    from paimon.session import Session


# 所有 archon system_prompt 末尾追加的硬性输出契约。
# 历史 bug：archon 偶发把 tool_calls 当终点，不再生成 final content text →
# `_extract_result()` 找不到 final assistant message，subtask.result 为空，
# 用户在 /task-index 看到"(产物为空)"。修复路径：prompt 显式声明 final
# content 是必须的，archon._extract_result 同时加 fallback 兜底。
FINAL_OUTPUT_RULE = """
⚠️ 输出契约（硬性要求）：
- 无论你是否调用了工具，**最后一轮必须输出一段中文文字**，作为对当前子任务的最终回答或总结。
- 不能只留下 tool_calls 就停止；不能把答案完全寄存在 reasoning 里；不能让最后一条消息是 tool 调用结果。
- 上层（四影 / /task-index 摘要）会从你最末一条「assistant 文本消息」抓取 result，没有就视作产物为空。
"""

_SKILL_BODY_CACHE: dict[str, str] = {}


def _read_skill_body(skill_name: str) -> str:
    """读 skills/{name}/SKILL.md 的正文（去掉 YAML frontmatter）。缓存到进程。

    兼容层：Claude Code 运行时会注入 `${CLAUDE_SKILL_DIR}` 环境变量指向 skill 目录，
    原生 skill（如 check）的 SKILL.md 里会用这个变量引用 references/ scripts/ assets/。
    paimon 没有这个环境变量 → 字面替换成 skill 的绝对路径，LLM 才能 Read 到 references。
    这是 paimon 适配 Claude Code 原生 skill 的基础能力（对所有 archon 透明）。
    """
    if skill_name in _SKILL_BODY_CACHE:
        return _SKILL_BODY_CACHE[skill_name]
    project_root = Path(__file__).resolve().parent.parent.parent
    skill_dir = project_root / "skills" / skill_name
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"skill 不存在: {skill_path}")
    text = skill_path.read_text(encoding="utf-8")
    # strip YAML frontmatter (--- ... ---)
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            text = text[end + 4:].lstrip()
    # Claude Code 兼容：${CLAUDE_SKILL_DIR} → skill 绝对路径
    text = text.replace("${CLAUDE_SKILL_DIR}", str(skill_dir))
    _SKILL_BODY_CACHE[skill_name] = text
    return text


class Archon(abc.ABC):
    name: str = ""
    description: str = ""
    allowed_tools: set[str] = set()

    @abc.abstractmethod
    async def execute(
        self,
        task: TaskEdict,
        subtask: Subtask,
        model: Model,
        irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        """执行子任务，返回结果文本。"""

    def _setup_tools(
        self, session: Session, *, allowed_override: set[str] | None = None,
    ):
        """构造 tool-loop 所需的 (tools list, executor)。

        allowed_override：临时覆盖 self.allowed_tools（不修改实例；并发安全）。
        """
        from paimon.state import state
        if not state.tool_registry:
            return None, None

        from paimon.tools.base import ToolContext
        all_tools = state.tool_registry.to_openai_tools()
        effective = allowed_override if allowed_override is not None else self.allowed_tools
        if effective:
            tools = [t for t in all_tools if t["function"]["name"] in effective]
        else:
            tools = all_tools

        ctx = ToolContext(registry=state.tool_registry, channel=None, chat_id="", session=session)

        async def _executor(name: str, arguments: str) -> str:
            return await state.tool_registry.execute(name, arguments, ctx)

        return tools or None, _executor

    @staticmethod
    def _extract_result(session: Session) -> str:
        """从 session 末尾抓 LLM 输出。分级 fallback + 落空诊断日志。

        优先级：
        1. 最后一条「无 tool_calls 的 assistant message」的 content（健康路径）
        2. 最后一条「带 tool_calls 但 content 也非空」的 assistant message 的 content
           （某些 provider 在工具调用前会同时输出推理文本）
        3. 最后一条 assistant message 的 reasoning_content（thinking 模型把答案
           写到思考流；前缀标注以避免误导）
        4. 最后一条 tool message 的 content（兜底：工具结果直接当答案，比如
           web_fetch / web-search 返回完整文本）
        5. 全空 → 返回 ""，由调用方决定怎么处理（archon 会写空 result，时执仍
           会归档；用户在 /task-index 摘要里能看到诊断兜底文案）

        命中 fallback (2/3/4) 时打 WARNING 日志，便于事后定位 LLM 在哪个层级
        断流。
        """
        # 1: clean final assistant
        for msg in reversed(session.messages):
            if msg.get("role") == "assistant" and not msg.get("tool_calls"):
                content = (msg.get("content") or "").strip()
                if content:
                    return content

        # 2: 工具调用前的过渡文本
        for msg in reversed(session.messages):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                content = (msg.get("content") or "").strip()
                if content:
                    logger.warning(
                        "[archon._extract_result] fallback L2: 末轮 LLM 没有"
                        "纯 final content，用 tool_calls 同消息的 content "
                        "(len={})", len(content),
                    )
                    return content

        # 3: reasoning_content
        for msg in reversed(session.messages):
            if msg.get("role") == "assistant":
                reasoning = (msg.get("reasoning_content") or "").strip()
                if reasoning:
                    logger.warning(
                        "[archon._extract_result] fallback L3: 末轮 LLM 仅在"
                        "reasoning_content 输出，未生成 final content "
                        "(reasoning_len={})", len(reasoning),
                    )
                    return f"[LLM 在思考流输出，未给出 final content]\n{reasoning[:2000]}"

        # 4: 末条 tool message
        for msg in reversed(session.messages):
            if msg.get("role") == "tool":
                content = (msg.get("content") or "").strip()
                if content:
                    logger.warning(
                        "[archon._extract_result] fallback L4: 末轮 LLM 完全"
                        "没产出，回退到末条 tool result (tool_call_id={}, "
                        "len={})", msg.get("tool_call_id"), len(content),
                    )
                    return f"[来自工具调用结果，LLM 未做最终总结]\n{content[:2500]}"

        # 5: 全空，记录消息数 + role 序列供排查
        roles = [m.get("role") for m in session.messages]
        logger.warning(
            "[archon._extract_result] 全部 fallback 落空 session={} "
            "msg_count={} roles={}",
            session.id, len(session.messages), roles[-10:],
        )
        return ""

    @staticmethod
    def _project_root() -> str:
        return str(Path(__file__).resolve().parent.parent.parent)

    async def _invoke_skill_workflow(
        self,
        *,
        skill_name: str,
        user_message: str,
        model: "Model",
        session_name: str,
        component: str,
        purpose: str,
        allowed_tools: set[str] | None = None,
        framing: str = "",
    ) -> str:
        """统一 skill 驱动工作流：读 SKILL.md body 作为 system prompt，启动 tool-loop。

        用于 archon 的薄壳方法（write_spec / write_design / write_code / review_*）。
        相比 `use_skill` tool，此路径省一次 tool call 往返，archon 直接接管 skill 指令执行。
        """
        from paimon.session import Session
        try:
            skill_body = _read_skill_body(skill_name)
        except FileNotFoundError as e:
            logger.error("[archon] {}", e)
            return f"skill {skill_name} 不存在"

        system = skill_body
        if framing:
            system += "\n\n---\n\n" + framing

        temp_session = Session(id=f"{skill_name}-{session_name}", name=f"{self.name}·{skill_name}")
        temp_session.messages.append({"role": "system", "content": system})

        # 用 allowed_override 参数路径（不修改实例属性，并发安全）
        tools, executor = self._setup_tools(temp_session, allowed_override=allowed_tools)
        async for _ in model.chat(
            temp_session, user_message,
            tools=tools, tool_executor=executor,
            component=component, purpose=purpose,
        ):
            pass

        return self._extract_result(temp_session)
