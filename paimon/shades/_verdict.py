"""水神裁决协议与解析器

docs/aimon.md §2.3：水神评审三级结论 —— 通过 / 修改 / 重做。
pipeline 在每轮 dispatch 完后，从"最后一个水神节点"的产物里解析出
ReviewVerdict 喂回生执，决定是否继续下一轮。

容错原则：解析失败 → 默认 pass（防止 LLM 偶发格式错误阻塞管线）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from loguru import logger

from paimon.foundation.irminsul.task import Subtask


# 三级裁决
LEVEL_PASS = "pass"
LEVEL_REVISE = "revise"
LEVEL_REDO = "redo"

_LEVEL_ALIASES = {
    # 英文
    "pass": LEVEL_PASS, "passed": LEVEL_PASS, "approve": LEVEL_PASS, "approved": LEVEL_PASS,
    "ok": LEVEL_PASS,
    "revise": LEVEL_REVISE, "fix": LEVEL_REVISE, "modify": LEVEL_REVISE,
    "redo": LEVEL_REDO, "reject": LEVEL_REDO, "rework": LEVEL_REDO,
    # 中文
    "通过": LEVEL_PASS, "合格": LEVEL_PASS,
    "修改": LEVEL_REVISE, "有问题需修改": LEVEL_REVISE, "小改": LEVEL_REVISE,
    "重做": LEVEL_REDO, "严重问题需重做": LEVEL_REDO, "大改": LEVEL_REDO,
}


@dataclass
class ReviewVerdict:
    level: str                                       # pass / revise / redo
    issues: list[dict] = field(default_factory=list)  # [{subtask_id, reason, suggestion}]
    summary: str = ""

    @property
    def needs_more_rounds(self) -> bool:
        return self.level in (LEVEL_REVISE, LEVEL_REDO)


def _normalize_level(raw: str) -> str:
    if not raw:
        return LEVEL_PASS
    key = raw.strip().lower()
    return _LEVEL_ALIASES.get(key, _LEVEL_ALIASES.get(raw.strip(), LEVEL_PASS))


def _extract_json_block(text: str) -> str | None:
    """从自由文本中抽出第一段 JSON 对象。容忍 ```json 包裹 + 前后散文。"""
    if not text:
        return None
    # 先剥 code fence
    fence_re = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
    m = fence_re.search(text)
    if m:
        return m.group(1)
    # 直接找第一个平衡的 {...}
    depth, start = 0, -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start : i + 1]
    return None


def parse_verdict(raw_text: str) -> ReviewVerdict:
    """从水神的自由产物里抽出 verdict。

    LLM 可能输出：纯 JSON / code fence 包裹 / 自然语言带嵌入 JSON。
    任何解析失败都降级为 pass（容错优先，配合 audit 记录问题）。
    """
    if not raw_text:
        return ReviewVerdict(level=LEVEL_PASS, summary="(水神产物为空，默认通过)")

    blob = _extract_json_block(raw_text)
    if not blob:
        # 无 JSON，扫关键词
        text = raw_text.lower()
        if any(k in text for k in ("重做", "redo", "rework")):
            return ReviewVerdict(level=LEVEL_REDO, summary=raw_text[:400])
        if any(k in text for k in ("修改", "revise", "fix")):
            return ReviewVerdict(level=LEVEL_REVISE, summary=raw_text[:400])
        return ReviewVerdict(level=LEVEL_PASS, summary=raw_text[:400])

    try:
        obj = json.loads(blob)
    except Exception as e:
        logger.warning("[水神·verdict] JSON 解析失败，默认通过: {} 原文={}",
                       e, blob[:200])
        return ReviewVerdict(level=LEVEL_PASS, summary=raw_text[:400])

    if not isinstance(obj, dict):
        return ReviewVerdict(level=LEVEL_PASS, summary=raw_text[:400])

    level = _normalize_level(str(obj.get("level", "")))
    issues_raw = obj.get("issues") or []
    issues: list[dict] = []
    if isinstance(issues_raw, list):
        for item in issues_raw:
            if not isinstance(item, dict):
                continue
            issues.append({
                "subtask_id": str(item.get("subtask_id", "")),
                "reason": str(item.get("reason", "")),
                "suggestion": str(item.get("suggestion", "")),
            })
    summary = str(obj.get("summary", "")).strip() or raw_text[:400]
    return ReviewVerdict(level=level, issues=issues, summary=summary)


def find_last_verdict_producer(subtasks: list[Subtask]) -> Subtask | None:
    """在 plan 中找"最后一个水神节点"作为 verdict 的产出者。

    约定：pipeline 把 DAG 中 assignee=水神 的节点按 created_at 取末尾。
    没有水神节点 → 返回 None（pipeline 视为 pass）。
    """
    water_nodes = [s for s in subtasks if s.assignee == "水神"]
    if not water_nodes:
        return None
    return max(water_nodes, key=lambda s: s.created_at)
