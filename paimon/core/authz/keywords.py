"""用户答复关键词识别（docs/permissions.md §用户答复识别）

铁律：只有用户明确说"永久 / 以后都..."才入库；只说"放行 / 同意 / 拒绝"仅本次有效。
用规则引擎不用 LLM：成本可控、行为可预期。
"""
from __future__ import annotations

import re
from typing import Literal

ReplyKind = Literal["perm_allow", "perm_deny", "allow", "deny", "unknown"]


# 永久性副词（必须先命中才算永久）
_PERMANENT_PREFIX = re.compile(
    r"(永久|永远|以后都|以后也|一直|始终|每次都|全部都|都)"
)

# 放行语义（中英混合 + 常见口语）
# 注意：不用裸 `好` / `行`（避免误匹配 "你好/不行/流行"）；要求带限定词
_ALLOW = re.compile(
    r"(放行|同意|允许|可以|好(的|吧|啊|呀|嘞)|没问题|行吧|嗯嗯?|ok|okay|yes|\by\b|go)",
    re.IGNORECASE,
)

# 拒绝语义（权限上下文下，拒绝信号一律压过放行）
_DENY = re.compile(
    r"(拒绝|不要|不行|不用|不可以|不允许|不同意|别|算了|禁止|no|\bn\b|stop|cancel)",
    re.IGNORECASE,
)


def classify_reply(text: str) -> ReplyKind:
    """分类用户对权限询问的答复。

    返回：
      - perm_allow：永久放行（写世界树）
      - perm_deny：永久禁止（写世界树）
      - allow：本次放行
      - deny：本次拒绝
      - unknown：无法判定（视为拒绝处理）

    优先级：DENY > ALLOW。这样 "不要放行"、"不可以"、"不同意" 这类
    同时命中双方的短语能被正确归为拒绝。
    """
    if not text:
        return "unknown"

    t = text.strip()
    has_permanent = bool(_PERMANENT_PREFIX.search(t))
    has_allow = bool(_ALLOW.search(t))
    has_deny = bool(_DENY.search(t))

    if has_deny:
        return "perm_deny" if has_permanent else "deny"
    if has_allow:
        return "perm_allow" if has_permanent else "allow"

    return "unknown"
