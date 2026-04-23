"""用户答复关键词识别（docs/permissions.md §用户答复识别）

铁律：只有用户明确说"永久 / 以后都..."才入库；只说"放行 / 同意 / 拒绝"仅本次有效。
用规则引擎不用 LLM：成本可控、行为可预期。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

ReplyKind = Literal["perm_allow", "perm_deny", "allow", "deny", "unknown"]


# 永久性副词（必须先命中才算永久）
# 只接受明确的持久化副词，避免 "都同意" 这类聚合词被误判为永久
_PERMANENT_PREFIX = re.compile(
    r"(永久|永远|以后都|以后也|一直|始终|每次都|全部都)"
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


# ============================================================
# 批量答复解析（四影路径：死执扫 DAG 敏感操作后一次性询问）
# ============================================================

BatchKind = Literal[
    "all_allow",       # 全部本次放行
    "all_perm_allow",  # 全部永久放行
    "all_deny",        # 全部本次拒绝
    "all_perm_deny",   # 全部永久拒绝
    "partial",         # 部分放行（indices）
    "unknown",         # 无法判定 → 保守视为全拒
]


@dataclass
class BatchReplyResult:
    kind: BatchKind
    # partial 场景下指明哪些编号被放行（1-based；其余默认拒）
    allow_indices: list[int] = field(default_factory=list)
    # 是否携带永久语义（写世界树）
    permanent: bool = False


# "全部" / "都" 的聚合范围词
_ALL_SCOPE = re.compile(r"(全部|全都|都|所有|统统|通通|均|全|all)", re.IGNORECASE)

# 编号抽取：支持 "1,3" / "1、3" / "1 和 3" / "1 2 3" / "第 1、3 项"
_INDEX_NUMBERS = re.compile(r"\d+")


def classify_batch_reply(text: str, total: int) -> BatchReplyResult:
    """解析批量授权答复。

    total: 当前询问的敏感项总数（用于过滤越界编号）。

    语义优先级：
      1. 明确的全部拒绝（含永久）
      2. 明确的全部放行（含永久）
      3. 含数字编号且含放行词 → partial
      4. 仅含拒绝词 → 视为 all_deny（无 "全部" 时也保守归为全拒）
      5. 仅含放行词但无 "全部" → 视为 all_allow（单项列表场景下最友好）
      6. 其他 → unknown（pipeline 侧保守全拒 + 超时重问一次）
    """
    if not text or not text.strip():
        return BatchReplyResult(kind="unknown")
    if total <= 0:
        return BatchReplyResult(kind="unknown")

    t = text.strip()
    has_permanent = bool(_PERMANENT_PREFIX.search(t))
    has_all = bool(_ALL_SCOPE.search(t))
    has_allow = bool(_ALLOW.search(t))
    has_deny = bool(_DENY.search(t))
    nums = _extract_indices(t, total)

    # 1) 明确全拒
    if has_deny and (has_all or not has_allow) and not nums:
        return BatchReplyResult(
            kind="all_perm_deny" if has_permanent else "all_deny",
            permanent=has_permanent,
        )

    # 2) 明确全放
    if has_allow and has_all and not has_deny and not nums:
        return BatchReplyResult(
            kind="all_perm_allow" if has_permanent else "all_allow",
            permanent=has_permanent,
        )

    # 3) 数字编号 + 放行 → partial
    if nums and has_allow and not has_all:
        return BatchReplyResult(
            kind="partial",
            allow_indices=sorted(set(nums)),
            permanent=has_permanent,
        )

    # 4) 仅数字（无明确 allow/deny）→ 视为 partial 放行这些编号
    if nums and not has_deny and not has_allow:
        return BatchReplyResult(
            kind="partial",
            allow_indices=sorted(set(nums)),
            permanent=has_permanent,
        )

    # 5) 有拒绝词（无数字）→ 全拒（保守）
    if has_deny and not has_allow:
        return BatchReplyResult(
            kind="all_perm_deny" if has_permanent else "all_deny",
            permanent=has_permanent,
        )

    # 6) 有放行词（单项场景无需 "全部"）→ 全放
    if has_allow and not has_deny:
        return BatchReplyResult(
            kind="all_perm_allow" if has_permanent else "all_allow",
            permanent=has_permanent,
        )

    return BatchReplyResult(kind="unknown")


def _extract_indices(text: str, total: int) -> list[int]:
    """从文本中抽 1..total 范围内的编号（去重保序）。"""
    out: list[int] = []
    for m in _INDEX_NUMBERS.finditer(text):
        try:
            n = int(m.group())
        except ValueError:
            continue
        if 1 <= n <= total and n not in out:
            out.append(n)
    return out
