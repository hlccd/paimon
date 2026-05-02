"""记忆指令 /remember：L1 记忆显式入口；分类 + reconcile 全自动。"""
from __future__ import annotations

from loguru import logger

# 敏感检测：复用 paimon.core.safety，保持向后兼容的旧私有别名
from paimon.core.safety import SENSITIVE_PATTERNS as _SENSITIVE_PATTERNS  # noqa: F401
from paimon.core.safety import detect_sensitive as _detect_sensitive
from paimon.state import state

from ._dispatch import CommandContext, command


@command("remember")
async def cmd_remember(ctx: CommandContext) -> str:
    """/remember <内容> — L1 记忆显式入口。

    LLM 自动分类 + 冲突检测：跟已有记忆矛盾自动替换，可合并自动合并，重复自动跳过。
    """
    from paimon.core.memory_classifier import MAX_REMEMBER_CHARS, remember_with_reconcile

    content = ctx.args.strip()
    if not content:
        return "用法: /remember <要记住的内容>"
    if len(content) > MAX_REMEMBER_CHARS:
        return f"内容过长（{len(content)} 字），单条记忆上限 {MAX_REMEMBER_CHARS} 字；请拆分后分别 /remember"
    hit = _detect_sensitive(content)
    if hit:
        logger.warning("[派蒙·记忆] /remember 命中敏感串 (pattern={}) 已拒绝", hit)
        return (
            f"⚠️ 检测到疑似敏感信息（pattern: {hit}），已拒绝写入。\n"
            "L1 记忆会注入每次对话的系统提示；请勿在此存储密钥/密码/身份证/银行卡等隐私信息。"
        )
    if not state.irminsul or not state.model:
        return "世界树 / 模型未就绪"

    outcome = await remember_with_reconcile(
        content, state.irminsul, state.model,
        source=f"cmd /remember @ {ctx.msg.channel_name}",
        actor="派蒙",
    )
    if not outcome.ok:
        return f"记忆写入失败: {outcome.error}"

    tag = f"[{outcome.mem_type}/{outcome.subject}]"
    if outcome.action == "new":
        return f"已记住 {tag} {outcome.title} (id={outcome.mem_id[:8]})"
    if outcome.action == "merge":
        return (
            f"已合并到原记忆 {tag}「{outcome.target_title}」→「{outcome.title}」\n"
            f"理由：{outcome.reason}"
        )
    if outcome.action == "replace":
        return (
            f"已替换旧记忆 {tag}「{outcome.target_title}」为「{outcome.title}」\n"
            f"理由：{outcome.reason}"
        )
    if outcome.action == "duplicate":
        return f"已存在相同记忆「{outcome.target_title}」，未重复写入"
    return f"未知动作 {outcome.action}"
