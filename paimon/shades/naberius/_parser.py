"""LLM 输出 JSON 解析 helper：剥代码围栏 / 容错解析 / 抢救 / 转 Subtask。"""
from __future__ import annotations

import json
import re
import time
from uuid import uuid4
from loguru import logger
from paimon.core.authz.sensitive_tools import derive_sensitivity
from paimon.foundation.irminsul.task import Subtask, TaskEdict


# assignee 字段值 = stage 名，跟 paimon/shades/worker/_stages.py:ALL_STAGES 对齐
_VALID_STAGES = {
    "spec", "design", "code",
    "review_spec", "review_design", "review_code",
    "simple_code", "exec", "chat",
}
_STAGE_TOOL_MAP = {
    "spec": ["file_ops"],
    "design": ["file_ops"],
    "code": ["file_ops", "exec"],
    "review_spec": ["file_ops", "glob", "exec"],
    "review_design": ["file_ops", "glob", "exec"],
    "review_code": ["file_ops", "glob", "exec"],
    "simple_code": ["file_ops", "exec"],
    "exec": ["exec"],
    "chat": ["file_ops"],
}


def _strip_code_fence(raw: str) -> str:
    """去掉 ```...``` 包裹（LLM 偶尔违反"不要 markdown fence"指令时的兜底）。"""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
    return raw.strip()


def _tolerant_json_parse(raw: str) -> tuple[object | None, str | None]:
    """尽力把 raw 解析成 JSON，失败返回 (None, 最后一次报错信息)。

    修复链（从轻到重）：
      1. 原文直接 json.loads
      2. 剥 ```fence``` 再试
      3. 截取从首个 '{' 或 '[' 到最后一个匹配的 '}' 或 ']'（LLM 偶尔前后加解释）
      4. 删尾随逗号（`,}` / `,]`）
    不做"嵌套未转义双引号"的智能修复——正则做不对，交给 LLM 重试。
    """
    if not raw:
        return None, "empty"
    last_err: str | None = None
    candidates: list[str] = []
    stripped = raw.strip()
    candidates.append(stripped)
    candidates.append(_strip_code_fence(stripped))

    # 截子串：从首个 { 或 [ 到最后一个 } 或 ]
    for ob, cb in (("{", "}"), ("[", "]")):
        i = stripped.find(ob)
        j = stripped.rfind(cb)
        if 0 <= i < j:
            candidates.append(stripped[i: j + 1])

    # 删尾随逗号（生成新候选）
    trailing_comma_re = re.compile(r",(\s*[}\]])")
    candidates += [trailing_comma_re.sub(r"\1", c) for c in list(candidates)]

    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        try:
            return json.loads(cand), None
        except Exception as e:
            last_err = str(e)
    return None, last_err


def _extract_items_from_obj(obj: object) -> list[dict]:
    """兼容两种格式：{"subtasks":[...]} 或 直接 [...]。非 list 归一为空。"""
    if isinstance(obj, dict) and "subtasks" in obj:
        items = obj["subtasks"]
    elif isinstance(obj, list):
        items = obj
    else:
        items = []
    if not isinstance(items, list):
        return []
    return items


def _salvage_from_raw_text(raw: str, task: TaskEdict) -> list[dict]:
    """最后兜底：从 raw 文本正则抓 "assignee":"<stage>" 和 "description":"..." 片段，
    保留 LLM 意图。抓不到才降级单节点 chat。
    """
    # 找第一个合法 assignee（stage 名）
    assignee: str | None = None
    for m in re.finditer(r'"assignee"\s*:\s*"([^"]+)"', raw):
        cand = m.group(1).strip()
        if cand in _VALID_STAGES:
            assignee = cand
            break

    if not assignee:
        logger.warning("[生执·salvage] 从 raw 抓不到合法 assignee → 回退单节点 chat")
        return [{"id": "s1", "assignee": "chat",
                 "description": task.description, "deps": []}]

    # 找第一个非空 description（不强求合法 JSON 转义，尽力匹配第一个"...")
    desc_match = re.search(
        r'"description"\s*:\s*"([^"]{3,})"', raw,
    )
    description = (
        desc_match.group(1).strip() if desc_match else task.description
    )
    logger.warning(
        "[生执·salvage] 从 raw 抢救 assignee={} desc_len={}",
        assignee, len(description),
    )
    return [{"id": "s1", "assignee": assignee,
             "description": description, "deps": []}]


def _items_to_subtasks(items: list[dict], task_id: str, round: int) -> list[Subtask]:
    """LLM 临时 id → 真实 uuid 映射；生成 Subtask 列表。"""
    now = time.time()
    tmp_to_real: dict[str, str] = {}
    # 第一遍：分配真实 id
    for i, item in enumerate(items):
        tmp = str(item.get("id") or f"s{i+1}")
        tmp_to_real[tmp] = uuid4().hex[:12]

    subtasks: list[Subtask] = []
    for i, item in enumerate(items):
        tmp = str(item.get("id") or f"s{i+1}")
        real_id = tmp_to_real[tmp]
        raw_deps = item.get("deps") or []
        if not isinstance(raw_deps, list):
            raw_deps = []
        real_deps = [tmp_to_real[str(d)] for d in raw_deps if str(d) in tmp_to_real]

        assignee = item.get("assignee", "chat")
        description = item.get("description", "").strip()
        sensitive_ops = item.get("sensitive_ops") or []
        if not isinstance(sensitive_ops, list):
            sensitive_ops = []
        # 若 LLM 没标 sensitive_ops，尝试从 assignee 的 allowed_tools 推断
        if not sensitive_ops:
            inferred = _infer_sensitive_ops(assignee)
            sensitive_ops = inferred
        compensate = str(item.get("compensate") or "").strip()

        subtasks.append(Subtask(
            id=real_id, task_id=task_id, parent_id=None,
            assignee=assignee, description=description,
            status="pending",
            created_at=now + i * 0.001,  # 保序
            updated_at=now + i * 0.001,
            deps=real_deps, round=round,
            sensitive_ops=sensitive_ops, verdict_status="",
            compensate=compensate,
        ))
    return subtasks


def _infer_sensitive_ops(assignee: str) -> list[str]:
    tools = _STAGE_TOOL_MAP.get(assignee, [])
    _, hits = derive_sensitivity(tools)
    return hits
