"""revise 路径的 issue 解析 helpers（无主公共 helper）。

生执 produce_spec / produce_design / produce_code 拼 prior_issues 进 user_message
YAML 块时用。
"""
from __future__ import annotations

import json


def fmt_issue_yaml(it: dict) -> str:
    """单个 issue 格式化为 YAML block（用 single-quote 安全转义）。"""
    sev = str(it.get("severity", "P2"))
    reason = str(it.get("reason", ""))[:200].replace("\n", " ")
    sugg = str(it.get("suggestion", ""))[:200].replace("\n", " ")
    reason_esc = reason.replace("'", "''")
    sugg_esc = sugg.replace("'", "''")
    return (
        f"  - severity: {sev}\n"
        f"    reason: '{reason_esc}'\n"
        f"    suggestion: '{sugg_esc}'"
    )


def extract_issues_from_description(desc: str) -> list[dict]:
    """从 subtask.description 抽 [REVISE_FEEDBACK_JSON] 块（生执 revise 直接嵌入的反馈）。"""
    if not desc or "[REVISE_FEEDBACK_JSON]" not in desc:
        return []
    start_marker = "[REVISE_FEEDBACK_JSON]"
    end_marker = "[/REVISE_FEEDBACK_JSON]"
    i = desc.find(start_marker)
    if i < 0:
        return []
    j = desc.find(end_marker, i + len(start_marker))
    if j < 0:
        return []
    blob = desc[i + len(start_marker):j].strip()
    try:
        obj = json.loads(blob)
        if isinstance(obj, dict) and isinstance(obj.get("issues"), list):
            return obj["issues"][:20]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def extract_prior_issues(prior_results: list[str] | None) -> list[dict]:
    """从 prior_results 文本里抽评审 verdict JSON 的 issues（平衡花括号扫描）。"""
    if not prior_results:
        return []
    for txt in prior_results:
        if not txt or '"level"' not in txt or '"issues"' not in txt:
            continue
        for start in range(len(txt)):
            if txt[start] != "{":
                continue
            depth = 0
            for i in range(start, len(txt)):
                c = txt[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(txt[start:i + 1])
                        except (json.JSONDecodeError, ValueError):
                            obj = None
                        if (
                            isinstance(obj, dict)
                            and "level" in obj
                            and isinstance(obj.get("issues"), list)
                        ):
                            return obj["issues"][:20]
                        break
    return []
