"""敏感信息检测 —— 跨模块共享

用途：拦截跨会话 memory 可能包含的密钥 / 密码 / 隐私号码等敏感串。
调用方：`commands.cmd_remember`（用户显式记忆入口）、`shades.istaroth.extract_experience`
（压缩后自动提取入口）。

策略：宁少勿多。只拦截强特征的串；正常中文内容不应误伤。
"""
from __future__ import annotations

import re


SENSITIVE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),              # OpenAI/Anthropic API key 风格
    re.compile(r"(?i)\bapi[_-]?key\b[:=\s]+\S{8,}"),    # api_key: xxx
    re.compile(r"(?i)\bpassword\b[:=\s]+\S{4,}"),       # password: xxx
    re.compile(r"(?i)\btoken\b[:=\s]+[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"(?i)\bsecret\b[:=\s]+\S{8,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"\b\d{16,19}\b"),                       # 银行卡号
    re.compile(r"\b\d{17}[0-9Xx]\b"),                   # 中国身份证
]


def detect_sensitive(text: str) -> str:
    """返回命中的模式描述；未命中返回空串。"""
    for pat in SENSITIVE_PATTERNS:
        if pat.search(text):
            return pat.pattern[:40]
    return ""
