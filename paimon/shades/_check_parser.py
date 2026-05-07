"""check skill 产物解析器（共享工具）

check skill 在目标路径写 `.check/candidates.jsonl`，每行一条 finding 记录；
多轮迭代会重复记录同一 id，最后一条视为最新状态。

工人 review_* stage（`paimon/shades/worker/_review.py`）+ 三月自检 Deep 档都需要同样的解析：
- 按 `id` 去重保留最新
- 过滤掉 `REJECTED` / `DEFERRED`，只保留 `CANDIDATE` / `CONFIRMED`
- 按 severity (P0/P1/P2/P3) 统计

解析 **只信任文件内容**，不信 LLM 自述（LLM 自述的 summary 可能幻觉）。
"""
from __future__ import annotations

import json
from pathlib import Path


_SEV_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def parse_candidates_file(path: Path) -> list[dict]:
    """解析单个 candidates.jsonl，返回去重 + 过滤后的 findings 列表。

    - 按 `id` 字段去重（后出现的覆盖前面的 → 保留每 id 最新状态）
    - 过滤 status ∈ {REJECTED, DEFERRED}
    - 格式错误的行静默跳过（不抛）
    - 文件读取失败返回空列表
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    by_id: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        fid = rec.get("id") or f"_{len(by_id)}"
        by_id[fid] = rec

    findings: list[dict] = []
    for rec in by_id.values():
        status = (rec.get("status") or "").upper()
        if status in ("REJECTED", "DEFERRED"):
            continue
        findings.append(rec)
    return findings


def parse_candidates_tree(root: Path) -> list[dict]:
    """在 root 下递归查找所有 `.check/candidates.jsonl`，合并解析。

    工人 review_* stage 在 task workspace 下可能有多个阶段产物（spec/design/code 各自
    `.check/`），需要 rglob 汇总。三月自检只在项目根单层，可以直接用 `parse_candidates_file`。
    """
    all_findings: list[dict] = []
    for cand in root.rglob(".check/candidates.jsonl"):
        all_findings.extend(parse_candidates_file(cand))
    return all_findings


def count_severity(findings: list[dict]) -> dict[str, int]:
    """按 severity 统计 findings 数。未知/缺失视为 P2。"""
    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for f in findings:
        sev = (f.get("severity") or "P2").upper()
        if sev in counts:
            counts[sev] += 1
    return counts


def sort_by_severity(findings: list[dict]) -> list[dict]:
    """按 severity 升序（P0 在前）返回新 list，不修改原 list。"""
    return sorted(
        findings,
        key=lambda r: _SEV_RANK.get((r.get("severity") or "P2").upper(), 2),
    )


def findings_to_issues(
    findings: list[dict], *, subtask_id: str, limit: int = 20,
) -> list[dict]:
    """把 findings 规范化成 ReviewVerdict.issues 结构。

    前 `limit` 条（按 severity 排序后）+ 截断字段长度。
    三月自检面板可直接用 `findings` 原始列表，不需要这层。
    """
    sorted_findings = sort_by_severity(findings)
    issues: list[dict] = []
    for f in sorted_findings[:limit]:
        desc = str(f.get("description") or "")[:300]
        ev = str(f.get("evidence") or "")[:200]
        loc = ""
        if f.get("file"):
            loc = f"[{f['file']}"
            if f.get("line"):
                loc += f":{f['line']}"
            loc += "] "
        reason = loc + desc
        issues.append({
            "subtask_id": subtask_id,
            "severity": (f.get("severity") or "P2").upper(),
            "reason": reason[:400],
            "suggestion": ev[:400],
            "module": f.get("module", ""),
        })
    return issues
