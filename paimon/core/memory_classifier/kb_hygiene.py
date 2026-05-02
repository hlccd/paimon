"""knowledge 域按 category 批量整理 —— 与 memory_hygiene 平行；独立重入 flag。

run_kb_hygiene 列出全部 category，每个 category 内单独 LLM 分析 → merge/delete。
执行结果落 push_archive 让面板能回放。
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
from .kb import sanitize_kb_segment


_HYGIENE_KB_RUNNING = False


def is_kb_hygiene_running() -> bool:
    """返回 KB 整理是否在跑（面板用来禁用按钮+显示状态）。"""
    return _HYGIENE_KB_RUNNING


_HYGIENE_KB_PROMPT = """\
你在重整一个知识库的一个分类（category）下的全部条目。找出可合并 / 冗余 / 矛盾的。

动作：
- merge  : 多条（≥2）讲同一主题或互补 → 合并为一条；保留 topics 列表
- delete : 这条已冗余（跟其他某条重复 / 明显过时）→ 删除

原则：
- 保守：拿不准不动（不列入操作即为 keep）
- merge 合并要保留全部原意，merged_body 是一条流畅完整的文本
- merged_topic 是一个简洁新主题名（英文小写 + 短横），若跟某旧 topic 一样那就沿用
- 不要一条 topic 同时出现在多个操作里

【JSON 引号】string value 里不能有未转义双引号；引用片段用【xxx】

输出严格 JSON：
{{
  "operations": [
    {{"action":"merge","topics":["<t1>","<t2>",...],"merged_topic":"<新/旧 topic>","merged_body":"<完整内容>","reason":"..."}},
    {{"action":"delete","topics":["<t>"],"reason":"..."}}
  ]
}}

若该分类已经干净无需整理，输出 {{"operations": []}}。
"""


async def _analyze_kb_hygiene(category, entries, model):
    """LLM 分析单 category 下条目，返回操作计划。<2 条直接跳过。"""
    if len(entries) < 2:
        return []
    def _fmt(t, b):
        b = (b or "").strip().replace("\n", " ").replace("\r", " ")
        if len(b) > 400:
            b = b[:400] + "..."
        return {"topic": t, "body": b}
    listing = json.dumps([_fmt(t, b) for t, b in entries], ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": _HYGIENE_KB_PROMPT},
        {"role": "user", "content": f"分类：{category}\n该分类下全部 {len(entries)} 条：\n{listing}"},
    ]
    try:
        raw, usage = await model._stream_text(messages, component="kb_hygiene", purpose="知识批量整理")
        await model._record_primogem("", "kb_hygiene", usage, purpose="知识批量整理")
    except Exception as e:
        logger.warning("[知识整理] LLM 失败 category={}: {}", category, e)
        return []
    obj = _parse_reconcile_json(raw)
    if obj is None:
        obj = await _repair_reconcile_json(raw, model)
    if obj is None or not isinstance(obj, dict):
        return []
    ops = obj.get("operations")
    return ops if isinstance(ops, list) else []


async def _apply_kb_hygiene_plan(category, entries, ops, irminsul, actor="草神·知识整理"):
    """按计划执行 merge/delete；merge 写新 merged_topic，删原 topics（除非沿用）。"""
    stats = HygieneStats(mem_type=f"kb/{category}", before=len(entries))
    existing_topics = {t for t, _ in entries}
    touched: set[str] = set()
    for op in ops:
        action = op.get("action", "")
        topics = op.get("topics") or []
        if not isinstance(topics, list) or not topics:
            stats.skipped += 1
            continue
        valid = [t for t in topics if t in existing_topics and t not in touched]
        if not valid:
            stats.errors.append(f"op {action} topics 全无效或已动过: {topics}")
            continue
        try:
            if action == "merge":
                if len(valid) < 2:
                    stats.skipped += 1
                    continue
                merged_topic = sanitize_kb_segment((op.get("merged_topic") or "").strip())
                merged_body = (op.get("merged_body") or "").strip()
                if not merged_body:
                    stats.errors.append("merge 缺 merged_body，跳过")
                    continue
                if merged_topic == "default":
                    merged_topic = valid[0]
                await irminsul.knowledge_write(category, merged_topic, merged_body, actor=actor)
                touched.add(merged_topic)
                for drop in valid:
                    if drop == merged_topic:
                        continue
                    await irminsul.knowledge_delete(category, drop, actor=actor)
                    touched.add(drop)
                stats.merged += 1
                stats.deleted += len([t for t in valid if t != merged_topic])
            elif action == "delete":
                for drop in valid:
                    await irminsul.knowledge_delete(category, drop, actor=actor)
                    touched.add(drop)
                    stats.deleted += 1
            else:
                stats.errors.append(f"未知 action: {action}")
        except Exception as e:
            stats.errors.append(f"{action} {valid}: {e}")
            logger.warning("[知识整理] 失败 action={} topics={} err={}", action, valid, e)
    stats.after = stats.before - stats.deleted
    return stats


async def run_kb_hygiene(irminsul, model, *, trigger="manual"):
    """知识库按 category 分别跑整理；独立于 memory hygiene 的重入 flag。"""
    global _HYGIENE_KB_RUNNING
    import time as _time

    if _HYGIENE_KB_RUNNING:
        return HygieneReport(
            started_at=_time.time(), finished_at=_time.time(),
            trigger=trigger, stats=[],
            aborted="已有知识整理任务在跑，本次跳过",
        )

    _HYGIENE_KB_RUNNING = True
    started = _time.time()
    all_stats: list[HygieneStats] = []

    try:
        try:
            pairs = await irminsul.knowledge_list()
        except Exception as e:
            logger.warning("[知识整理] 列目录失败: {}", e)
            pairs = []
        by_cat: dict[str, list[str]] = {}
        for cat, tp in pairs:
            by_cat.setdefault(cat, []).append(tp)

        for cat, topics in sorted(by_cat.items()):
            if len(topics) < 2:
                all_stats.append(HygieneStats(mem_type=f"kb/{cat}", before=len(topics), after=len(topics)))
                continue
            entries = []
            for tp in topics:
                try:
                    body = await irminsul.knowledge_read(cat, tp)
                except Exception:
                    continue
                if body is not None:
                    entries.append((tp, body))
            ops = await _analyze_kb_hygiene(cat, entries, model)
            stats = await _apply_kb_hygiene_plan(cat, entries, ops, irminsul)
            all_stats.append(stats)
            logger.info(
                "[知识整理] category={} before={} after={} merged={} deleted={} errors={}",
                cat, stats.before, stats.after,
                stats.merged, stats.deleted, len(stats.errors),
            )
    finally:
        _HYGIENE_KB_RUNNING = False

    finished = _time.time()
    report = HygieneReport(started_at=started, finished_at=finished, trigger=trigger, stats=all_stats)

    try:
        duration = finished - started
        lines = [
            f"# 🧹 知识库整理 · {trigger}",
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
            source=f"草神·知识整理·{trigger}",
            actor="草神",
            message_md="\n".join(lines),
            channel_name="webui", chat_id="webui-push",
            extra={"merged": report.total_merged, "deleted": report.total_deleted},
        )
    except Exception as e:
        logger.warning("[知识整理] 写 push_archive 失败: {}", e)

    return report
