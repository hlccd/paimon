"""L1 记忆分类器 —— `/remember` 和草神面板"+ 新建记忆"共用。

一段自然语言 → LLM 分类为 (mem_type, title, subject)。失败降级规则见
classify_memory；subject 防路径注入走 sanitize_subject。
"""
from __future__ import annotations

import json
import re

from loguru import logger


# 单条记忆上限（memory 域设计值）；超了拒收，避免记忆域被单条挤爆
MAX_REMEMBER_CHARS = 2000


_CLASSIFY_PROMPT = """\
你是记忆分类器。用户用 /remember 命令告诉派蒙一段要记住的内容。
请把内容归入以下类型之一：
- user: 用户画像 / 偏好 / 角色（"我主要用 Go"、"偏好简洁"）
- feedback: 对派蒙行为的纠正 / 规范（"不要给总结"、"用中文"）
- project: 当前项目的持久事实（"这个项目在 /xxx"、"DB 是 PostgreSQL"）
- reference: 外部资源指针（"bugs 在 Linear INGEST"、"面板 grafana.xx"）

只输出 JSON 对象，严格格式：
{"type": "user|feedback|project|reference", "title": "短标题(<=20字)", "subject": "主题词(user/feedback 用 default, project 用项目名, reference 用简短关键词)"}

不要输出任何其他文字、不要 markdown 代码块。
"""


_SUBJECT_SAFE_RE = re.compile(r"^[\w一-鿿\-]+$")


def sanitize_subject(subject: str) -> str:
    """subject 必须是简单标识符（字母/数字/下划线/中文/短横）。
    含路径字符 / 空格 / 特殊字符的一律降级到 'default'，避免 resolve_safe 抛
    + 文件系统问题。
    """
    s = (subject or "").strip() or "default"
    if ".." in s or "/" in s or "\\" in s:
        return "default"
    if not _SUBJECT_SAFE_RE.match(s):
        return "default"
    return s[:80]


async def classify_memory(
    content: str, model,
) -> tuple[str | None, str | None, str | None]:
    """LLM 分类一段内容。返回 (type, title, subject)；三者全 None 表示失败。

    失败情境（调用方负责降级）：
    - LLM 调用异常
    - 返回非合法 JSON
    - 返回不是 dict
    - 返回 type 不在允许集合 / 缺 title
    """
    messages = [
        {"role": "system", "content": _CLASSIFY_PROMPT},
        {"role": "user", "content": f"内容：\n{content}"},
    ]
    try:
        raw, usage = await model._stream_text(
            messages, component="remember", purpose="记忆分类",
        )
        await model._record_primogem("", "remember", usage, purpose="记忆分类")
    except Exception as e:
        logger.warning("[记忆分类] LLM 调用失败: {}", e)
        return None, None, None

    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()

    try:
        obj = json.loads(text)
    except Exception as e:
        logger.warning("[记忆分类] JSON 解析失败: {} 原始={}", e, text[:200])
        return None, None, None

    if not isinstance(obj, dict):
        logger.warning("[记忆分类] 输出非对象: {}", type(obj).__name__)
        return None, None, None

    mem_type = obj.get("type", "")
    title = (obj.get("title") or "").strip()
    subject = (obj.get("subject") or "").strip() or "default"
    if mem_type not in ("user", "feedback", "project", "reference") or not title:
        return None, None, None
    return mem_type, title[:80], subject[:80]


def default_title(content: str, max_len: int = 30) -> str:
    """LLM 分类失败时的兜底标题：用内容前 N 字（清理控制字符）。"""
    safe = content.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return safe[:max_len]
