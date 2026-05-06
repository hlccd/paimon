"""渲染：Report → markdown / json。"""
from __future__ import annotations

import json as _json

from .schema import Item, Report


_SOURCE_NAME = {
    "bili": "B 站", "xhs": "小红书", "zhihu": "知乎",
    "weibo": "微博", "tieba": "贴吧", "hupu": "虎扑",
    "taptap": "TapTap", "github": "GitHub",
}


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
    if (v := item.engagement.get("thanks")):   parts.append(f"谢 {v:,}")
    if (v := item.engagement.get("follower")): parts.append(f"关 {v:,}")
    if (v := item.engagement.get("answer")):   parts.append(f"答 {v:,}")
    if (v := item.engagement.get("danmaku")):  parts.append(f"弹 {v:,}")
    return " · ".join(parts)


def to_markdown(report: Report, *, top_n: int = 20) -> str:
    """生成 markdown 简报。结构：标题 + 时间窗 + 跨源 top + 分源明细。"""
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

    # 跨源 top
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

    # 分源明细
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


def to_json(report: Report) -> str:
    return _json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
