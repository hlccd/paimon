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


_SKILL_BODY_CACHE: dict[str, str] = {}


def _read_skill_body(skill_name: str) -> str:
    """读 skills/{name}/SKILL.md 的正文（去掉 YAML frontmatter）。缓存到进程。"""
    if skill_name in _SKILL_BODY_CACHE:
        return _SKILL_BODY_CACHE[skill_name]
    project_root = Path(__file__).resolve().parent.parent.parent
    skill_path = project_root / "skills" / skill_name / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"skill 不存在: {skill_path}")
    text = skill_path.read_text(encoding="utf-8")
    # strip YAML frontmatter (--- ... ---)
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            text = text[end + 4:].lstrip()
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
        for msg in reversed(session.messages):
            if msg.get("role") == "assistant" and msg.get("content") and not msg.get("tool_calls"):
                return msg["content"]
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
