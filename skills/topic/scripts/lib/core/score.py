"""计分：recency × engagement × relevance 三维加权。

每个源内部先把 engagement 归一化到 0-1（log 缩放），再跨源加权。
recency 用线性衰减（30 天前 0 分，今天 1 分）。
"""
from __future__ import annotations

import datetime as _dt
import math

from .schema import Item


def _recency_score(published_at: str, range_from: str, range_to: str) -> float:
    """0-1，越新越高（线性衰减）。窗外 0。"""
    if not published_at or not (range_from <= published_at[:10] <= range_to):
        return 0.0
    try:
        d_pub = _dt.date.fromisoformat(published_at[:10])
        d_to = _dt.date.fromisoformat(range_to)
        d_from = _dt.date.fromisoformat(range_from)
    except ValueError:
        return 0.0
    span = (d_to - d_from).days or 1
    age = (d_to - d_pub).days
    return max(0.0, 1.0 - age / span)


# 各源的 engagement 字段权重（用于把 dict 加权成单个 raw 值）
_ENGAGEMENT_WEIGHTS: dict[str, dict[str, float]] = {
    "bili":  {"view": 1.0, "like": 5.0, "comment": 8.0, "favorite": 10.0, "share": 12.0},
    "xhs":   {"like": 1.0, "comment": 3.0, "favorite": 5.0, "share": 8.0},   # MVP 多为 0
    "zhihu": {
        "like": 1.0, "comment": 2.0, "favorite": 5.0, "thanks": 3.0,   # answer / article
        "follower": 0.3, "answer": 2.0, "view": 0.05,                  # question 类型
    },
    "weibo": {"view": 0.5, "repost": 5.0, "comment": 3.0, "like": 1.0},
    "tieba": {"reply": 5.0, "view": 0.3, "like": 1.0},   # 贴吧主要 engagement 是回复数
}


def _engagement_raw(item: Item) -> float:
    """把 engagement dict 加权成单个 raw 值。"""
    weights = _ENGAGEMENT_WEIGHTS.get(item.source, {})
    if not weights:
        return float(sum(item.engagement.values())) if item.engagement else 0.0
    return sum(weights.get(k, 0.0) * float(v) for k, v in item.engagement.items())


def _normalize_engagement(items: list[Item]) -> dict[str, float]:
    """同源内 log 缩放到 0-1。返回 {item_id: norm}。"""
    if not items:
        return {}
    raws = [(it.item_id, _engagement_raw(it)) for it in items]
    log_raws = [(iid, math.log1p(max(0.0, v))) for iid, v in raws]
    max_log = max((v for _, v in log_raws), default=0.0)
    if max_log <= 0:
        return {iid: 0.0 for iid, _ in log_raws}
    return {iid: v / max_log for iid, v in log_raws}


def score_items(
    items_by_source: dict[str, list[Item]],
    range_from: str,
    range_to: str,
    *,
    w_recency: float = 0.3,
    w_engagement: float = 0.5,
    w_relevance: float = 0.2,
) -> None:
    """原地填 item.score；不返回。"""
    for src, items in items_by_source.items():
        eng_norm = _normalize_engagement(items)
        for it in items:
            r = _recency_score(it.published_at, range_from, range_to)
            e = eng_norm.get(it.item_id, 0.0)
            rel = max(0.0, min(1.0, it.relevance))
            it.score = round(w_recency * r + w_engagement * e + w_relevance * rel, 4)


def rank(items_by_source: dict[str, list[Item]], top_n: int = 30) -> list[Item]:
    """跨源合并 → 按 score 降序 → top_n。"""
    flat: list[Item] = []
    for items in items_by_source.values():
        flat.extend(items)
    flat.sort(key=lambda it: it.score, reverse=True)
    return flat[:top_n]
