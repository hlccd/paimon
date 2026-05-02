"""共享 helper：LLM JSON 解析 + 修复 / Hygiene 通用 dataclass。

被 memory / memory_hygiene / kb / kb_hygiene 4 个模块共用，避免重复代码。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from loguru import logger


_REPAIR_PROMPT = """\
你刚输出的 JSON 无法解析。常见错误是 string value 里含未转义双引号。
请重新输出**严格合法**的 JSON，同样的字段结构。

要求：
- 不要 markdown 代码块、不要解释
- string value 里的双引号必须改为中文【】或《》或单引号 'xxx'
- 只输出 JSON 本身
"""


def _parse_reconcile_json(raw: str) -> dict | None:
    """从 LLM 原始输出抠出 JSON；含 ``` 代码块时剥壳。失败返回 None。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError as e:
        logger.debug("[记忆冲突] 首次 JSON 解析失败（尝试修复）: {} 原始={}", e, text[:200])
        return None


async def _repair_reconcile_json(raw: str, model) -> dict | None:
    """LLM 自修复：原输出 + 错误信息扔回去，让 LLM 重新生成合法 JSON。

    失败场景才触发，不影响正常路径开销。失败就 None，调用方降级 new。
    """
    messages = [
        {"role": "system", "content": _REPAIR_PROMPT},
        {"role": "user", "content": f"原输出（需修复）：\n{raw[:2000]}"},
    ]
    try:
        fixed_raw, usage = await model._stream_text(
            messages, component="reconcile", purpose="JSON 修复",
        )
        await model._record_primogem("", "reconcile", usage, purpose="JSON 修复")
    except Exception as e:
        logger.warning("[记忆冲突] JSON 修复 LLM 调用失败: {}", e)
        return None
    return _parse_reconcile_json(fixed_raw)


@dataclass
class HygieneStats:
    """单 mem_type / category 的整理统计；errors 收集执行期非致命错误。"""
    mem_type: str
    before: int = 0
    after: int = 0
    merged: int = 0
    deleted: int = 0
    skipped: int = 0  # LLM 未动的（keep）
    errors: list = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@dataclass
class HygieneReport:
    """一轮整理的整体报告；面板 / push_archive 据此渲染。aborted 非空 = 整体跳过。"""
    started_at: float
    finished_at: float
    trigger: str  # 'cron' | 'manual'
    stats: list  # list[HygieneStats]
    aborted: str = ""  # 非空 = 整体异常跳过

    @property
    def total_merged(self) -> int:
        """全部 mem_type 合并总次数。"""
        return sum(s.merged for s in self.stats)

    @property
    def total_deleted(self) -> int:
        """全部 mem_type 删除总条数。"""
        return sum(s.deleted for s in self.stats)
