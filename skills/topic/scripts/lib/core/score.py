"""计分 + 排序：平台特性化 engagement + recency + relevance 三维加权。

每个源有专属 engagement 公式（B 站重 view、知乎重 voteup/thanks、小红书 only like、
贴吧 only reply、微博重 repost），同源 P90 归一化避免爆款压扁其他条目。
recency 用线性衰减（30 天前 0 分，今天 1 分）。

排序「每源至少 1 上榜」的 diversity rank：
- 各源 top 1 无条件入榜（即使 score 偏低）—— 用户原诉求是"覆盖度优先"
- 剩余名额按全局 score 降序填
- 最终按 score 倒序展示
- 边界：源数 > top_n 时按各源 top 1 score 降序截 top_n（牺牲源覆盖度换分数下限）
"""
from __future__ import annotations

import datetime as _dt
import math

from .schema import Item


# ─────────────────────────────────────────────────────────────
# Recency
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# Engagement —— 平台特性化公式
# 每个公式输出 raw engagement_score（log 缩放后加权），再走 P90 归一化
# ─────────────────────────────────────────────────────────────

def _eng_bili(eng: dict) -> float:
    """B 站 search API 字段：view + danmaku + favorite（无 like/coin/comment）。

    view 是流行度基础；favorite 反映"想回看"=实用/优质；danmaku 反映互动深度。
    P2 todo：二次拉 view stat 拿 like/coin/comment 后可改成互动率公式
    （`like/view × 100 + coin/view × 1000`）抗刷量。
    """
    view = max(0.0, float(eng.get("view") or 0))
    danmaku = max(0.0, float(eng.get("danmaku") or 0))
    fav = max(0.0, float(eng.get("favorite") or 0))
    return (
        math.log10(view + 1) * 0.4
        + math.log10(fav + 1) * 0.3
        + math.log10(danmaku + 1) * 0.3
    )


def _eng_zhihu(eng: dict) -> float:
    """知乎：voteup(='like') 主信号；thanks 罕见但精准；comment 撕逼噪音大权重低。

    collector 把 voteup_count 写在 'like' key 里（schema 历史原因；不改 schema）。
    """
    voteup = max(0.0, float(eng.get("like") or 0))
    thanks = max(0.0, float(eng.get("thanks") or 0))
    comment = max(0.0, float(eng.get("comment") or 0))
    fav = max(0.0, float(eng.get("favorite") or 0))
    return (
        math.log10(voteup + 1) * 0.5
        + math.log10(thanks + 1) * 0.3
        + math.log10(comment + 1) * 0.1
        + math.log10(fav + 1) * 0.1
    )


def _eng_xhs(eng: dict) -> float:
    """小红书：当前 collector 只解析 like（DOM 摘要可见这一项）。

    后续若 collector 补 favorite / comment（点进笔记详情才有），可升级为
    `0.5·log10(like) + 0.3·log10(favorite) + 0.2·log10(comment)`；
    favorite 缺失时降级 `like·0.7 + comment·0.3`。
    """
    like = max(0.0, float(eng.get("like") or 0))
    fav = max(0.0, float(eng.get("favorite") or 0))
    comment = max(0.0, float(eng.get("comment") or 0))
    if fav > 0 or comment > 0:
        return (
            math.log10(like + 1) * 0.5
            + math.log10(fav + 1) * 0.3
            + math.log10(comment + 1) * 0.2
        )
    return math.log10(like + 1)   # MVP only-like 路径


def _eng_tieba(eng: dict) -> float:
    """贴吧：本质=讨论，回帖数主信号；DOM 抓不到浏览量稳定值。"""
    reply = max(0.0, float(eng.get("reply") or 0))
    view = max(0.0, float(eng.get("view") or 0))
    if view > 0:
        return math.log10(reply + 1) * 0.7 + math.log10(view + 1) * 0.3
    return math.log10(reply + 1)


def _eng_weibo(eng: dict) -> float:
    """微博：repost = 传播力（微博特色），comment + like 辅助。"""
    repost = max(0.0, float(eng.get("repost") or 0))
    comment = max(0.0, float(eng.get("comment") or 0))
    like = max(0.0, float(eng.get("like") or 0))
    return (
        math.log10(repost + 1) * 0.4
        + math.log10(comment + 1) * 0.3
        + math.log10(like + 1) * 0.3
    )


def _eng_default(eng: dict) -> float:
    """未知 source 兜底：所有数值字段加和取 log。"""
    if not eng:
        return 0.0
    total = sum(max(0.0, float(v or 0)) for v in eng.values())
    return math.log10(total + 1)


_ENG_FN = {
    "bili":  _eng_bili,
    "zhihu": _eng_zhihu,
    "xhs":   _eng_xhs,
    "tieba": _eng_tieba,
    "weibo": _eng_weibo,
}


def _percentile(sorted_values: list[float], p: float) -> float:
    """sorted_values（升序）的 p 百分位（p ∈ [0, 100]），最近邻法。"""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = int(len(sorted_values) * p / 100)
    idx = max(0, min(len(sorted_values) - 1, idx))
    return sorted_values[idx]


def _normalize_p90(raws: list[float]) -> list[float]:
    """同源 P90 归一化到 [0, 1]：除 P90 后 clip。

    比 max 归一化抗一个爆款拉低其他条目（P90 = 第 9 名 / 10 条时是第 9 名）。
    P90 ≤ 0 时全 0。
    """
    if not raws:
        return []
    sorted_v = sorted(raws)
    p90 = _percentile(sorted_v, 90)
    if p90 <= 0:
        return [0.0] * len(raws)
    return [min(v / p90, 1.0) for v in raws]


def _compute_relevance(item: Item, topic: str) -> float:
    """关键词匹配相关度：topic 在 title/body 中的出现深浅。

    - title 包含 topic：1.0
    - body 包含 topic：0.5（次于 title）
    - 都不含但 collector 拿到了：0.2（弱相关兜底，因 collector 是搜 topic 来的）

    短期抽取式；P2 可上 LLM rerank（topic-rerank 把 30 条喂 LLM 重打分）。
    """
    if not topic:
        return 0.5
    topic_lower = topic.lower()
    title_lower = (item.title or "").lower()
    body_lower = (item.body or "").lower()
    if topic_lower in title_lower:
        return 1.0
    if topic_lower in body_lower:
        return 0.5
    return 0.2


def score_items(
    items_by_source: dict[str, list[Item]],
    range_from: str,
    range_to: str,
    *,
    topic: str = "",
    w_recency: float = 0.25,
    w_engagement: float = 0.5,
    w_relevance: float = 0.25,
) -> None:
    """原地填 item.score。每源用专属 engagement 公式 + P90 归一化。

    topic 参数用于 _compute_relevance 关键词匹配；为空时降级到 item.relevance（默认 0.5）。
    """
    for src, items in items_by_source.items():
        if not items:
            continue
        eng_fn = _ENG_FN.get(src, _eng_default)
        raws = [eng_fn(it.engagement or {}) for it in items]
        norms = _normalize_p90(raws)
        for it, en in zip(items, norms):
            r = _recency_score(it.published_at, range_from, range_to)
            # 优先用关键词匹配（topic 非空时）；否则降级到 item.relevance（discover 阶段写过的）
            if topic:
                rel = _compute_relevance(it, topic)
                it.relevance = rel  # 写回方便 debug / 落盘 json 看
            else:
                rel = max(0.0, min(1.0, it.relevance))
            it.score = round(
                w_recency * r + w_engagement * en + w_relevance * rel, 4,
            )


# ─────────────────────────────────────────────────────────────
# Rank: 每源至少 1 上榜（diversity rank）
# ─────────────────────────────────────────────────────────────

def rank(
    items_by_source: dict[str, list[Item]],
    top_n: int = 10,
    *,
    diversity: bool = True,
) -> list[Item]:
    """跨源合并 → top_n。

    diversity=True 时启「每源至少 1 上榜」：
    1. 每源 top 1 无条件入榜（用户原诉求：覆盖度优先）
    2. 剩余 top_n - len(已入榜) 名额按全局 score 降序填
    3. 最终按 score 倒序展示

    diversity=False 退化为纯全局 score 排序。

    边界：
    - 源数 > top_n 时按各源 top 1 score 降序截前 top_n 个源（牺牲源覆盖换分数下限）
    - 数据条数 ≤ top_n 时直接全展（不需要 diversity 逻辑）
    """
    flat: list[Item] = []
    for items in items_by_source.values():
        flat.extend(items)
    if not flat:
        return []
    flat.sort(key=lambda it: it.score, reverse=True)

    if not diversity or len(items_by_source) <= 1 or len(flat) <= top_n:
        return flat[:top_n]

    # 各源 top 1 无条件入榜（用户诉求：每源至少 1 上榜）
    # 不再用 P50 阈值过滤 —— 旧设计在多源数据集中度高时会卡掉数据偏旧/偏冷的源
    # （如某源 published_at 都是 5 天前 → recency 略低 → 全局 P50 卡掉它）
    # 用户原意是"覆盖度 > 单条最低质量"，所以无条件入榜
    diversity_picks: list[Item] = []
    for src, items in items_by_source.items():
        if not items:
            continue
        items_sorted = sorted(items, key=lambda i: i.score, reverse=True)
        diversity_picks.append(items_sorted[0])

    # 极端：源数 > top_n 时按 score 降序截 top_n（牺牲覆盖度）
    diversity_picks.sort(key=lambda i: i.score, reverse=True)
    diversity_picks = diversity_picks[:top_n]
    seen_ids = {(it.source, it.item_id) for it in diversity_picks}

    # 剩余名额按全局 score 降序填
    remaining = top_n - len(diversity_picks)
    rest = [it for it in flat if (it.source, it.item_id) not in seen_ids]
    final = diversity_picks + rest[:remaining]
    final.sort(key=lambda it: it.score, reverse=True)
    return final[:top_n]
