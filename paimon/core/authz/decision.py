"""授权决策树 —— 天使路径权限闸

按 docs/aimon.md §2.4 天使路径：
  调用天使前 → 派蒙查本地缓存
    ├── 永久放行 → 直调 + 提示
    ├── 永久禁止 → 拒绝 + 说明
    ├── 普通权限 → 放行 + 友好告知
    └── 敏感权限无记录 → 询问用户，按答复处理
"""
from __future__ import annotations

import asyncio
from enum import Enum

from loguru import logger

from paimon.angels.registry import SkillInfo, SkillRegistry
from paimon.channels.base import Channel
from paimon.foundation.irminsul import Irminsul
from paimon.session import Session

from .cache import AuthzCache
from .keywords import classify_reply
from .sensitive_tools import derive_sensitivity, describe_tools


class Verdict(Enum):
    ALLOW = "allow"
    DENY = "deny"


class AuthzDecision:
    def __init__(
        self,
        cache: AuthzCache,
        irminsul: Irminsul,
        skill_registry: SkillRegistry,
        *,
        ask_timeout: float = 30.0,
        user_id: str = "default",
    ):
        self._cache = cache
        self._irminsul = irminsul
        self._skill_registry = skill_registry
        self._ask_timeout = ask_timeout
        self._user_id = user_id

    async def check_skill(
        self,
        skill_name: str,
        *,
        channel: Channel,
        chat_id: str,
        session: Session,
    ) -> tuple[Verdict, str]:
        """天使路径权限闸。返回 (verdict, user_hint_text)。

        user_hint_text 是给用户看的提示（"按之前的永久授权放行"等），
        调用方决定是否把它发到 channel。空串表示无需额外提示。
        """
        skill = self._skill_registry.get(skill_name)
        if skill is None:
            # 未知 skill 让上层处理错误（不是权限问题）
            return Verdict.ALLOW, ""

        sensitivity, hits = derive_sensitivity(skill.allowed_tools or [])

        # 1) 非敏感：直接放行，友好提示
        if sensitivity == "normal":
            return Verdict.ALLOW, ""

        # 2) 永久授权命中
        cached = self._cache.get("skill", skill_name)
        if cached == "permanent_allow":
            return Verdict.ALLOW, f"（按之前的永久授权放行 skill「{skill_name}」）"
        if cached == "permanent_deny":
            return (
                Verdict.DENY,
                f"skill「{skill_name}」已被永久禁止。可在「插件面板」撤销后重试。",
            )

        # 3) 本次会话临时决策
        scope = self._cache.get_session_scope(session.id, "skill", skill_name)
        if scope == "allow":
            return Verdict.ALLOW, ""
        if scope == "deny":
            return Verdict.DENY, f"本次会话已拒绝 skill「{skill_name}」。"

        # 4) 敏感且无记录 → 询问
        return await self._ask_and_decide(
            skill=skill, hits=hits,
            channel=channel, chat_id=chat_id, session=session,
        )

    async def _ask_and_decide(
        self,
        *,
        skill: SkillInfo,
        hits: list[str],
        channel: Channel,
        chat_id: str,
        session: Session,
    ) -> tuple[Verdict, str]:
        prompt = self._build_ask_prompt(skill, hits)

        try:
            reply = await channel.ask_user(chat_id, prompt, timeout=self._ask_timeout)
        except NotImplementedError:
            logger.warning(
                "[派蒙·授权] 频道 {} 未支持 ask_user，本次保守拒绝",
                channel.name,
            )
            return (
                Verdict.DENY,
                f"当前频道暂不支持权限询问。敏感 skill「{skill.name}」"
                "请在 WebUI 中确认后再试。",
            )
        except asyncio.TimeoutError:
            logger.info("[派蒙·授权] 询问超时 skill={}", skill.name)
            return Verdict.DENY, f"（{int(self._ask_timeout)} 秒无答复，本次拒绝 skill「{skill.name}」）"

        kind = classify_reply(reply)
        logger.info(
            "[派蒙·授权] skill={} 用户答复='{}' 分类={}",
            skill.name, reply[:40], kind,
        )

        if kind == "perm_allow":
            await self._irminsul.authz_set(
                "skill", skill.name, "permanent_allow",
                user_id=self._user_id, session_id=session.id,
                reason="user_permanent_allow", actor="派蒙",
            )
            self._cache.set("skill", skill.name, "permanent_allow")
            return Verdict.ALLOW, f"已永久放行 skill「{skill.name}」，以后不再询问。"

        if kind == "perm_deny":
            await self._irminsul.authz_set(
                "skill", skill.name, "permanent_deny",
                user_id=self._user_id, session_id=session.id,
                reason="user_permanent_deny", actor="派蒙",
            )
            self._cache.set("skill", skill.name, "permanent_deny")
            return Verdict.DENY, f"已永久禁止 skill「{skill.name}」。可在插件面板撤销。"

        if kind == "allow":
            self._cache.set_session_scope(session.id, "skill", skill.name, "allow")
            return Verdict.ALLOW, ""

        if kind == "deny":
            self._cache.set_session_scope(session.id, "skill", skill.name, "deny")
            return Verdict.DENY, f"已拒绝本次 skill「{skill.name}」。"

        # unknown
        return (
            Verdict.DENY,
            f"没理解你的意思，本次保守拒绝 skill「{skill.name}」。"
            "想放行请明确说「放行 / 同意」，永久放行请说「永久放行 / 以后都允许」。",
        )

    @staticmethod
    def _build_ask_prompt(skill: SkillInfo, hits: list[str]) -> str:
        tool_desc = describe_tools(hits)
        return (
            f"这个任务会调用 skill「{skill.name}」，其中会执行以下敏感操作：\n"
            f"{tool_desc}\n\n"
            f"要放行吗？（放行 / 拒绝 / 永久放行 / 永久禁止）"
        )
