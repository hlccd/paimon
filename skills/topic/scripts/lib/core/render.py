"""渲染：Report → markdown / json。

两版 markdown：
- to_markdown_full：落盘 report.md（含 engagement 数字 + 分源明细），归档 / 给其他 skill 复用
- to_markdown_brief：stdout reply 走 LLM 输出契约的精简版（标题 + 链接 + 源标记 + ≤50 字摘要），
  去 engagement 数字 / 去 score / 去日期，节省 token + 简化体感
"""
from __future__ import annotations

import json as _json

from .schema import Item, Report


_SOURCE_NAME = {
    "bili": "B 站", "xhs": "小红书", "zhihu": "知乎",
    "weibo": "微博", "tieba": "贴吧", "hupu": "虎扑",
    "taptap": "TapTap", "github": "GitHub",
}

_SUMMARY_MAX_CHARS = 50   # brief 版每条摘要硬上限（用户诉求 v2）


def _fmt_engagement(item: Item) -> str:
    if not item.engagement:
        return ""
    parts = []
    if (v := item.engagement.get("view")):     parts.append(f"播放 {v:,}")
    if (v := item.engagement.get("like")):     parts.append(f"赞 {v:,}")
    if (v := item.engagement.get("comment")):  parts.append(f"评 {v:,}")
    if (v := item.engagement.get("favorite")): parts.append(f"藏 {v:,}")
    if (v := item.engagement.get("coin")):     parts.append(f"币 {v:,}")
    if (v := item.engagement.get("share")):    parts.append(f"转 {v:,}")
    if (v := item.engagement.get("repost")):   parts.append(f"转 {v:,}")
    if (v := item.engagement.get("reply")):    parts.append(f"回 {v:,}")
    if (v := item.engagement.get("thanks")):   parts.append(f"谢 {v:,}")
    if (v := item.engagement.get("follower")): parts.append(f"关 {v:,}")
    if (v := item.engagement.get("answer")):   parts.append(f"答 {v:,}")
    if (v := item.engagement.get("danmaku")):  parts.append(f"弹 {v:,}")
    return " · ".join(parts)


def _summarize(body: str, max_chars: int = _SUMMARY_MAX_CHARS) -> str:
    """body 截前 max_chars 字（替掉换行避免破坏 markdown 列表结构）。

    body 缺失返回空串；调用方据此决定是否带 "—" 分隔符。
    """
    if not body:
        return ""
    text = body.replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    # 截断后加省略号，但末尾不留破碎标点（"，..."这种）
    cut = text[:max_chars].rstrip("，。、；,.;:")
    return cut + "..."


def to_markdown_full(report: Report, *, top_n: int = 30) -> str:
    """落盘 report.md：完整结构（标题 + 时间窗 + 跨源 top + 分源明细 + engagement 数字）。

    给 LLM / 其他 skill 复用 / 归档查询用，不喂给 reply 输出契约。
    """
    lines: list[str] = []
    lines.append(f"# {report.topic} · 近 30 天调研")
    lines.append("")
    lines.append(
        f"> 时间窗：{report.range_from} ~ {report.range_to}　|　"
        f"生成于 {report.generated_at}"
    )
    lines.append("")

    if report.errors:
        lines.append("## 采集错误")
        for src, msg in report.errors.items():
            lines.append(f"- **{_SOURCE_NAME.get(src, src)}**：{msg}")
        lines.append("")

    if report.ranked:
        lines.append(f"## 综合 Top {min(top_n, len(report.ranked))}")
        lines.append("")
        for i, it in enumerate(report.ranked[:top_n], 1):
            src_name = _SOURCE_NAME.get(it.source, it.source)
            eng = _fmt_engagement(it)
            meta = f"`{src_name}`"
            if it.published_at: meta += f" · {it.published_at}"
            if it.author:       meta += f" · @{it.author}"
            if eng:             meta += f" · {eng}"
            meta += f" · score {it.score}"
            lines.append(f"{i}. **[{it.title}]({it.url})**  ")
            lines.append(f"   {meta}")
            if it.body:
                snippet = it.body.replace("\n", " ").strip()[:160]
                lines.append(f"   > {snippet}")
            lines.append("")

    for src, items in report.items_by_source.items():
        if not items:
            continue
        items_sorted = sorted(items, key=lambda it: it.score, reverse=True)
        lines.append(f"## {_SOURCE_NAME.get(src, src)}（{len(items)} 条）")
        lines.append("")
        for it in items_sorted[:10]:
            eng = _fmt_engagement(it)
            tail_parts = []
            if it.published_at: tail_parts.append(it.published_at)
            if eng:             tail_parts.append(eng)
            tail = " · ".join(tail_parts)
            lines.append(f"- [{it.title}]({it.url})　_{tail}_")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def to_markdown_brief(report: Report, *, top_n: int = 10) -> str:
    """stdout reply 用的精简版 —— LLM 在此基础上写最终输出（含各源讨论重点 + 情绪分析）。

    结构：
    - 综合 Top {top_n}：每条 `**[标题](url)** _(源)_ — 50 字摘要`，摘要缺失时降级
    - 分源 raw items（≤5 条/源）：让 LLM 写「各源讨论重点」时有原料
    - 跨源汇总（≤15 条）：让 LLM 写「情绪分析」时有总览原料

    去掉 full 版里的：日期 / score / engagement 数字 / 分源明细全表
    """
    lines: list[str] = []
    lines.append(f"# {report.topic} · 近 30 天")
    lines.append(f"> 时间窗 {report.range_from} ~ {report.range_to}")
    lines.append("")

    if report.errors:
        err_str = "; ".join(
            f"{_SOURCE_NAME.get(s, s)}={m[:40]}" for s, m in report.errors.items()
        )
        lines.append(f"> 采集错误：{err_str}")
        lines.append("")

    if report.ranked:
        n = min(top_n, len(report.ranked))
        lines.append(f"## 综合 Top {n}")
        lines.append("")
        for i, it in enumerate(report.ranked[:top_n], 1):
            src_name = _SOURCE_NAME.get(it.source, it.source)
            summary = _summarize(it.body)
            head = f"{i}. **[{it.title}]({it.url})** _({src_name})_"
            if summary:
                lines.append(f"{head} — {summary}")
            else:
                lines.append(head)
        lines.append("")

    # 各源 raw items：让 LLM 写「各源讨论重点」时能基于本源 top 5 实际内容总结
    # 格式精简，只给标题 + 简短 body 摘要（80 字让 LLM 有更多原料判断正负分化）
    nonempty_sources = [
        (src, items) for src, items in report.items_by_source.items() if items
    ]
    if nonempty_sources:
        lines.append("## 各源原始素材（供归纳「各源讨论重点」+「情绪分析」用）")
        lines.append("")
        for src, items in nonempty_sources:
            src_name = _SOURCE_NAME.get(src, src)
            items_sorted = sorted(items, key=lambda it: it.score, reverse=True)
            lines.append(f"### {src_name}（{len(items)} 条，下列前 5）")
            for it in items_sorted[:5]:
                snippet = _summarize(it.body, max_chars=80)
                if snippet:
                    lines.append(f"- {it.title} — {snippet}")
                else:
                    lines.append(f"- {it.title}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# 向后兼容老入口：默认 brief（reply）；显式 full 走 to_markdown_full
def to_markdown(report: Report, *, top_n: int = 10) -> str:
    """已废弃别名：默认转 to_markdown_brief。新代码请显式调 _full / _brief。"""
    return to_markdown_brief(report, top_n=top_n)


def to_json(report: Report) -> str:
    return _json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
