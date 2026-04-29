from __future__ import annotations

import json
from typing import TYPE_CHECKING

import botpy
from botpy.connection import ConnectionState
from loguru import logger

from paimon.channels.base import IncomingMessage
from paimon.channels.qq.middleware import is_authorized

if TYPE_CHECKING:
    from paimon.channels.qq.channel import QQChannel


# botpy 用 __slots__ 把 ark_data/embeds 等卡片字段全丢了（C2CMessage __slots__ 里没有 ark_data）。
# 在 parse 之前 hook：落 DEBUG 日志（排查新卡片类型），同时按 msg_id 缓存 ark_data，handler 取来用。
_ARK_CACHE: dict[str, dict] = {}
_ARK_CACHE_MAX = 64


def _patch_capture_card_fields() -> None:
    if getattr(ConnectionState, "_paimon_card_patched", False):
        return
    for evt in ("parse_group_at_message_create", "parse_c2c_message_create"):
        orig = getattr(ConnectionState, evt, None)
        if orig is None:
            continue

        def _wrap(orig_fn, evt_name):
            def _patched(self, payload):
                try:
                    d = payload.get("d", {}) if isinstance(payload, dict) else {}
                    logger.debug(
                        "[派蒙·QQ频道·原始 payload] {} 全字段:\n{}",
                        evt_name,
                        json.dumps(d, ensure_ascii=False, indent=2, default=str)[:8000],
                    )
                    # 卡片字段（ark_data / embeds / 未知扩展）按 msg_id 缓存，handler 取
                    msg_id = d.get("id")
                    if msg_id and ("ark_data" in d or "embeds" in d):
                        _ARK_CACHE[msg_id] = {
                            k: d[k] for k in ("ark_data", "embeds", "message_scene") if k in d
                        }
                        # LRU 兜底，避免内存涨
                        while len(_ARK_CACHE) > _ARK_CACHE_MAX:
                            _ARK_CACHE.pop(next(iter(_ARK_CACHE)))
                except Exception as e:
                    logger.warning("[派蒙·QQ频道·原始 payload] 处理失败: {}", e)
                return orig_fn(self, payload)
            return _patched

        setattr(ConnectionState, evt, _wrap(orig, evt))
    ConnectionState._paimon_card_patched = True
    logger.info("[派蒙·QQ频道] 卡片捕获已挂载（ark_data / embeds 按 msg_id 缓存）")


_patch_capture_card_fields()


def _build_card_prompt(card: dict) -> str | None:
    """把 ark_data 翻译成给 LLM 的结构化提示。无法识别返 None。

    QQ 不同 ark_type 字段结构不一样：
    - miniapp（小程序，如 B 站官方）：source / title / preview，**无 URL**
    - tuwen（图文 H5，如小红书分享）：tag / title / desc / jump_url，**有 URL**
    - 其他类型按需扩展
    """
    ark = card.get("ark_data") or {}
    fields = ark.get("fields") or {}

    # 平台名：miniapp 用 source，tuwen 用 tag
    source = fields.get("source") or fields.get("tag") or ""
    title = fields.get("title") or ""
    desc = fields.get("desc") or ""
    # 原始 URL：tuwen 给 jump_url；其他 ark_type 也可能用 link/url
    jump_url = fields.get("jump_url") or fields.get("link") or fields.get("url") or ""
    prompt = ark.get("prompt") or ""
    ark_type = ark.get("ark_type") or ""
    if not (source or title or jump_url or prompt):
        return None

    lines: list[str] = [
        "[QQ转发卡片]",
        f"卡片类型: {ark.get('ark_name', ark_type)}",
    ]
    if source:
        lines.append(f"来源平台: {source}")
    if title:
        lines.append(f"标题: {title}")
    if desc:
        lines.append(f"描述: {desc}")

    if jump_url:
        # 有原始 URL：直接放给 LLM，让平台 skill 的 trigger（xiaohongshu.com / bilibili.com）自动捕获
        lines += [
            "",
            f"原始 URL: {jump_url}",
            "",
            "请基于上述 URL 调对应平台 skill（小红书 → xhs / B站 → bili）做内容总结。",
        ]
    else:
        # 无 URL：要么搜反查，要么让用户补
        lines += [
            "",
            "⚠️ 此卡片未包含原始 URL（QQ 官方小程序协议常见，preview 仅是 QQ CDN 缩略图）。",
        ]
        if "哔哩哔哩" in source or "bilibili" in source.lower():
            lines += [
                "",
                "建议处理：",
                "1. 用搜索工具搜「<标题> bilibili」，从结果挑 bilibili.com/video/BV... 链接",
                "2. 提到 BV 号后调 bili skill / video_process",
                "3. 搜不到或重名时，告知用户复制原视频 URL 重发",
            ]
        elif "小红书" in source or "xiaohongshu" in source.lower() or "xhs" in source.lower():
            lines += [
                "",
                "建议处理：",
                "1. 用搜索工具搜「<标题> 小红书」，挑 xiaohongshu.com 链接",
                "2. 拿到长链后走 xhs skill",
                "3. 搜不到时让用户复制 xhslink 重发",
            ]
        else:
            lines += ["", "建议：告知用户「QQ 卡片不带原 URL，请粘贴原链接」。"]

    return "\n".join(lines)


def _clean_content(content: str | None) -> str:
    if not content:
        return ""
    return content.strip()


def _dump_msg_attrs(obj, depth: int = 0, max_depth: int = 3, max_str: int = 600) -> dict:
    """递归 dump 对象可见属性（卡片消息排查用）。深度+长度限制防爆炸。"""
    if depth > max_depth:
        return {"_truncated": "depth exceeded"}
    out: dict = {}
    for attr in dir(obj):
        if attr.startswith("_"):
            continue
        try:
            val = getattr(obj, attr)
        except Exception as e:
            out[attr] = f"<getattr error: {e}>"
            continue
        if callable(val):
            continue
        if val is None or isinstance(val, (bool, int, float)):
            out[attr] = val
        elif isinstance(val, str):
            out[attr] = val if len(val) <= max_str else val[:max_str] + f"...({len(val)} chars)"
        elif isinstance(val, (list, tuple)):
            out[attr] = [
                _dump_msg_attrs(v, depth + 1, max_depth, max_str)
                if hasattr(v, "__dict__")
                else repr(v)[:max_str]
                for v in val[:10]
            ]
            if len(val) > 10:
                out[attr].append(f"...({len(val)} items total)")
        elif isinstance(val, dict):
            out[attr] = {k: repr(v)[:max_str] for k, v in list(val.items())[:20]}
        elif hasattr(val, "__dict__"):
            out[attr] = _dump_msg_attrs(val, depth + 1, max_depth, max_str)
        else:
            out[attr] = repr(val)[:max_str]
    return out


def _build_wrap(
    channel: QQChannel,
    message,
    chat_id: str,
    msg_type: str,
) -> IncomingMessage:
    msg_id = str(message.id)

    # 卡片消息：botpy 把 ark 拼成了平铺文本写到 content；这里把缓存的结构化 ark_data 再翻译一遍
    # 给 LLM 一个明确「这是 QQ 转发卡片 + 来源 + 标题 + 建议处理路径」的提示
    card = _ARK_CACHE.pop(msg_id, None)
    if card:
        card_prompt = _build_card_prompt(card)
        if card_prompt:
            ark = card.get("ark_data") or {}
            fields = ark.get("fields") or {}
            logger.info(
                "[派蒙·QQ频道·卡片] type={} 来源={!r} 标题={!r} 有 URL={}",
                ark.get("ark_type"),
                fields.get("source") or fields.get("tag"),
                fields.get("title"),
                bool(fields.get("jump_url") or fields.get("link") or fields.get("url")),
            )
            text = card_prompt
        else:
            text = _clean_content(message.content)
    else:
        text = _clean_content(message.content)

    channel.register_chat_context(chat_id, msg_type, msg_id)

    async def _reply(reply_text: str) -> None:
        from paimon.channels.qq.reply import QQChannelReply

        r = QQChannelReply(channel, chat_id, msg_id, msg_type)
        await r.send(reply_text)
        await r.flush()

    return IncomingMessage(
        channel_name=channel.name,
        chat_id=chat_id,
        text=text,
        raw=message,
        _reply=_reply,
    )


class PaimonQQClient(botpy.Client):
    def __init__(self, channel: QQChannel, **kwargs):
        super().__init__(**kwargs)
        self._channel = channel

    async def on_group_at_message_create(self, message):
        chat_id = str(message.group_openid)
        await self._handle_message(message, chat_id, "group")

    async def on_c2c_message_create(self, message):
        author = getattr(message, "author", None)
        chat_id = str(getattr(author, "user_openid", "")) if author else ""
        if not chat_id:
            return
        await self._handle_message(message, chat_id, "c2c")

    async def _handle_message(self, message, chat_id: str, msg_type: str):
        if not is_authorized(message):
            return

        # 卡片消息排查：dump 整个 message 对象的所有可见属性。DEBUG 级，需要时开启
        try:
            dumped = _dump_msg_attrs(message)
            logger.debug(
                "[派蒙·QQ频道·原始数据] {} 消息全字段 dump:\n{}",
                msg_type,
                json.dumps(dumped, ensure_ascii=False, indent=2, default=str),
            )
        except Exception as e:
            logger.warning("[派蒙·QQ频道·原始数据] dump 失败: {}", e)

        msg = _build_wrap(self._channel, message, chat_id, msg_type)
        text = msg.text
        logger.info(
            "[派蒙·QQ频道] 收到{}消息 chat_id={} text_len={}",
            msg_type, chat_id[:8], len(text) if text else 0,
        )
        if not text:
            logger.info("[派蒙·QQ频道] text 为空，跳过 chat handle")
            return

        try:
            from paimon.core.chat import on_channel_message
            await on_channel_message(msg, self._channel)
        except Exception as e:
            logger.error("[派蒙·QQ频道] 消息处理失败: {}", e)
