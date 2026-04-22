"""授权体系 — 跨天使 / 四影路径的统一权限决策

按 docs/permissions.md 的设计：
- 世界树持久化（authz 域）
- 派蒙启动灌缓存、运行时写缓存
- 敏感度从 skill.allowed_tools 自动派生（见 sensitive_tools）
"""
from .cache import AuthzCache
from .decision import AuthzDecision, Verdict
from .keywords import classify_reply
from .sensitive_tools import SENSITIVE_TOOLS, TOOL_RISK_DESC, derive_sensitivity

__all__ = [
    "AuthzCache",
    "AuthzDecision",
    "Verdict",
    "classify_reply",
    "SENSITIVE_TOOLS",
    "TOOL_RISK_DESC",
    "derive_sensitivity",
]
