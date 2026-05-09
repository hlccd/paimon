"""派蒙·task_review — 入口任务级安全审查。

判断用户提交的请求是否安全（/evolve 命令、自进化触发器调用前）。

容错策略：
  - LLM 调用失败（网络/超时）→ fail-open 保持可用性 + 日志留痕
  - LLM 输出非合法 JSON / 缺 safe 字段 → fail-closed（防 prompt injection 绕审）
"""
from __future__ import annotations

import json

from loguru import logger

from paimon.foundation.irminsul import Irminsul
from paimon.llm.model import Model


_REVIEW_PROMPT = """\
你是安全审查官·若纳瓦。你的职责是判断用户请求是否安全。

审查标准：
1. 是否涉及删除系统文件、修改核心配置等破坏性操作
2. 是否试图获取未授权的权限
3. 是否包含恶意代码注入或攻击指令
4. 是否违反基本安全规范

正常的编程、分析、写作、查询等请求应该放行。

只输出 JSON，格式：{"safe": true/false, "reason": "简短原因"}
不要输出任何其他内容。"""


async def task_review(
    *,
    title: str,
    description: str,
    session_id: str = "",
    model: Model,
    irminsul: Irminsul,
) -> tuple[bool, str]:
    """入口任务级安全审查。返回 (safe, reason)。"""
    messages = [
        {"role": "system", "content": _REVIEW_PROMPT},
        {"role": "user", "content": f"请审查以下请求:\n\n{title}\n{description}"},
    ]

    # Step 1: LLM 调用 — 失败 fail-open（保持可用性）
    try:
        raw, usage = await model._stream_text(messages, component="派蒙·安全审", purpose="入口审查")
        await model._record_primogem(session_id, "派蒙·安全审", usage, purpose="入口审查")
    except Exception as e:
        logger.error("[派蒙·安全审] LLM 调用失败，跳过审查（fail-open）: {}", e)
        return True, ""

    # Step 2: JSON 解析 — 失败 fail-closed（防止 prompt injection 让 LLM 输出非 JSON 绕审）
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "[派蒙·安全审] LLM 输出非合法 JSON，保守拒绝: {} 原始={}",
            e, raw[:200],
        )
        return False, "审查 LLM 输出非合法 JSON（疑似 prompt injection 尝试）"

    if not isinstance(result, dict) or "safe" not in result:
        logger.warning("[派蒙·安全审] LLM 输出缺 safe 字段，保守拒绝: {}", raw[:200])
        return False, "审查 LLM 输出缺 safe 字段"

    safe = bool(result.get("safe"))
    reason = str(result.get("reason", ""))

    if safe:
        logger.info("[派蒙·安全审] 审查通过: {}", title[:60])
    else:
        logger.warning("[派蒙·安全审] 审查拒绝: {} — {}", title[:60], reason)

    return safe, reason
