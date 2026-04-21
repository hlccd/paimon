from __future__ import annotations

from loguru import logger

from paimon.state import state


def _extract_sender_id(message) -> str:
    author = getattr(message, "author", None)
    if not author:
        return ""
    if hasattr(message, "group_openid"):
        return getattr(author, "member_openid", "") or ""
    return getattr(author, "user_openid", "") or ""


def is_authorized(message) -> bool:
    cfg = state.cfg
    if not cfg or not cfg.qq_owner_ids:
        return True
    allowed = {s.strip() for s in cfg.qq_owner_ids.split(",") if s.strip()}
    if not allowed:
        return True
    sender_id = _extract_sender_id(message)
    if not sender_id:
        return False
    ok = sender_id in allowed
    if not ok:
        logger.debug("[派蒙·QQ频道] 拒绝未授权消息 sender={}", sender_id)
    return ok
