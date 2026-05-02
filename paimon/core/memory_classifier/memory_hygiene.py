"""memory 域批量整理（cron + 面板手动触发共用）。

run_hygiene 对 4 种 mem_type 各跑一轮：列条目 → LLM 分析 → 应用 merge/delete。
全局 _HYGIENE_RUNNING 防并发双跑；执行结果落 push_archive 供面板回溯。
"""
from __future__ import annotations

import json

from loguru import logger

from ._common import (
    HygieneReport,
    HygieneStats,
    _parse_reconcile_json,
    _repair_reconcile_json,
)
from .memory import RECONCILE_CANDIDATE_LIMIT


# 全局重入 flag：cron + 面板按钮共用，避免并发双跑
_HYGIENE_RUNNING = False


def is_hygiene_running() -> bool:
    """返回当前 memory 整理是否在跑（面板用来禁用按钮 + 显示状态）。"""
    return _HYGIENE_RUNNING


_HYGIENE_PROMPT = """\
你在重整一个【{mem_type}】类跨会话记忆库。下面列出了全部 N 条记忆，
请分析并生成整理操作计划：找出可合并的、矛盾/过时的、完全重复的。

动作类型：
- merge  : 多条（2 条及以上）讲同一件事或互补 → 合并成一条；保留 ids 列表
- delete : 这条是冗余的（跟其他某条完全重复，或明显过时矛盾）→ 删除

原则：
- 保守：拿不准就不动（不出现在计划里即为 keep）
- merge 要保留所有原意，不要丢信息；merged_body 要是一条流畅完整的记忆
- delete 必须有明确理由（冗余或矛盾），不要删独立意义的条目
- 不要处理同一条 id 两次（不要让一条 id 同时出现在 merge 和 delete）

【JSON 引号规则】string value 里绝对不能有未转义双引号；引用片段用 中文【xxx】

输出严格 JSON，不要 markdown / 解释：
{{
  "operations": [
    {{
      "action": "merge",
      "ids": ["<id1>", "<id2>", ...],
      "merged_title": "<整合后标题 ≤20 字>",
      "merged_body": "<整合后完整内容>",
      "reason": "<一句说明>"
    }},
    {{
      "action": "delete",
      "ids": ["<id>"],
      "reason": "<一句说明>"
    }}
  ]
}}

如果当前记忆都健康无需整理，输出 {{"operations": []}}。
"""


async def _analyze_hygiene(
    mem_type: str, memories: list, model,
) -> list[dict]:
    """LLM 批量分析记忆，返回操作计划（list of dict）。失败返回空列表。"""
    if len(memories) < 2:
        return []

    def _fmt(m):
        b = (m.body or "").strip().replace("\n", " ").replace("\r", " ")
        if len(b) > 300:
            b = b[:300] + "..."
        return {"id": m.id, "title": (m.title or "").strip(), "body": b}

    listing = json.dumps([_fmt(m) for m in memories], ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": _HYGIENE_PROMPT.format(mem_type=mem_type)},
        {"role": "user", "content": f"全部 {len(memories)} 条记忆：\n{listing}"},
    ]

    try:
        raw, usage = await model._stream_text(
            messages, component="hygiene", purpose="记忆批量整理",
        )
        await model._record_primogem("", "hygiene", usage, purpose="记忆批量整理")
    except Exception as e:
        logger.warning("[记忆整理] LLM 失败 type={}: {}", mem_type, e)
        return []

    obj = _parse_reconcile_json(raw)
    if obj is None:
        # 复用修复流程
        obj = await _repair_reconcile_json(raw, model)
    if obj is None or not isinstance(obj, dict):
        logger.warning("[记忆整理] 解析失败 type={}", mem_type)
        return []

    ops = obj.get("operations")
    if not isinstance(ops, list):
        return []
    return ops


async def _apply_hygiene_plan(
    mem_type: str,
    memories: list,
    ops: list[dict],
    irminsul,
    actor: str = "草神·记忆整理",
) -> HygieneStats:
    """按操作计划执行：merge → update 第一条 + 删剩余；delete → 删。

    已处理过的 id 登记到 touched 集合，避免多动作冲突。
    """
    stats = HygieneStats(mem_type=mem_type, before=len(memories))
    by_id = {m.id: m for m in memories}
    touched: set[str] = set()

    for op in ops:
        action = op.get("action", "")
        ids = op.get("ids") or []
        if not isinstance(ids, list) or not ids:
            stats.skipped += 1
            continue
        # id 必须在候选集内且未被动过
        valid_ids = [i for i in ids if i in by_id and i not in touched]
        if not valid_ids:
            stats.errors.append(f"op {action} ids 全无效或已动过: {ids}")
            continue

        try:
            if action == "merge":
                if len(valid_ids) < 2:
                    stats.skipped += 1
                    continue
                merged_title = (op.get("merged_title") or "").strip()[:80]
                merged_body = (op.get("merged_body") or "").strip()
                if not merged_title or not merged_body:
                    stats.errors.append("merge 缺 merged_title/body，跳过")
                    continue
                keeper_id = valid_ids[0]
                await irminsul.memory_update(
                    keeper_id,
                    title=merged_title, body=merged_body,
                    actor=actor,
                )
                touched.add(keeper_id)
                for drop_id in valid_ids[1:]:
                    await irminsul.memory_delete(drop_id, actor=actor)
                    touched.add(drop_id)
                stats.merged += 1
                stats.deleted += len(valid_ids) - 1

            elif action == "delete":
                for drop_id in valid_ids:
                    await irminsul.memory_delete(drop_id, actor=actor)
                    touched.add(drop_id)
                    stats.deleted += 1
            else:
                stats.errors.append(f"未知 action: {action}")
        except Exception as e:
            stats.errors.append(f"{action} {valid_ids}: {e}")
            logger.warning("[记忆整理] 操作失败 action={} ids={} err={}", action, valid_ids, e)

    stats.after = stats.before - stats.deleted
    return stats


async def run_hygiene(
    irminsul, model, *, trigger: str = "manual",
) -> HygieneReport:
    """对全部 4 种 mem_type 跑一轮记忆整理。写 push_archive 审计。

    trigger: 'cron' | 'manual'，仅记录用。
    重入保护：并发调用只第一个生效，其余立即返回 aborted 报告。
    """
    global _HYGIENE_RUNNING
    import time as _time

    if _HYGIENE_RUNNING:
        return HygieneReport(
            started_at=_time.time(), finished_at=_time.time(),
            trigger=trigger, stats=[],
            aborted="已有整理任务在跑，本次跳过",
        )

    _HYGIENE_RUNNING = True
    started = _time.time()
    all_stats: list[HygieneStats] = []

    try:
        for mem_type in ("user", "feedback", "project", "reference"):
            try:
                metas = await irminsul.memory_list(
                    mem_type=mem_type, limit=RECONCILE_CANDIDATE_LIMIT,
                )
            except Exception as e:
                logger.warning("[记忆整理] 查 {} 失败: {}", mem_type, e)
                continue
            if len(metas) < 2:
                all_stats.append(HygieneStats(mem_type=mem_type, before=len(metas), after=len(metas)))
                continue

            full = []
            for meta in metas:
                try:
                    m = await irminsul.memory_get(meta.id)
                except Exception:
                    continue
                if m is not None:
                    full.append(m)

            ops = await _analyze_hygiene(mem_type, full, model)
            stats = await _apply_hygiene_plan(mem_type, full, ops, irminsul)
            all_stats.append(stats)
            logger.info(
                "[记忆整理] type={} before={} after={} merged={} deleted={} errors={}",
                mem_type, stats.before, stats.after,
                stats.merged, stats.deleted, len(stats.errors),
            )

    finally:
        _HYGIENE_RUNNING = False

    finished = _time.time()
    report = HygieneReport(
        started_at=started, finished_at=finished,
        trigger=trigger, stats=all_stats,
    )

    # 审计：写 push_archive 供面板查看
    try:
        duration = finished - started
        lines = [
            f"# 🧹 记忆整理 · {trigger}",
            "",
            f"**耗时**：{duration:.1f}s · **合并**：{report.total_merged} 次 · **删除**：{report.total_deleted} 条",
            "",
        ]
        for s in all_stats:
            lines.append(
                f"- **{s.mem_type}**：{s.before} → {s.after} 条"
                + (f"（合并 {s.merged}、删除 {s.deleted}）" if (s.merged or s.deleted) else "（无变化）")
            )
            for err in s.errors[:3]:
                lines.append(f"  - ⚠️ {err}")
        await irminsul.push_archive_create(
            source=f"草神·记忆整理·{trigger}",
            actor="草神",
            message_md="\n".join(lines),
            channel_name="webui", chat_id="webui-push",
            extra={"merged": report.total_merged, "deleted": report.total_deleted},
        )
    except Exception as e:
        logger.warning("[记忆整理] 写 push_archive 失败（不影响整理结果）: {}", e)

    return report
