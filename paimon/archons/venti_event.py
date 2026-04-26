"""风神 L1 · 事件级舆情监测核心 (EventClusterer)

docs/archons/venti.md §L1 事件级舆情监测

把单批次新条目升级为事件级情报：
1. 聚类 LLM（_llm_cluster）  —— 阶段 A 暂跳过、强制 new；B 阶段启用
2. 分析 LLM（_llm_analyze）  —— 给每个事件出"标题/摘要/实体/时间线/严重度/情感"
3. UPSERT 到 feed_events + 关联 feed_items.event_id

设计要点：
- LLM 用浅池（mimo-v2-omni）；token 记原石 component="风神" purpose="事件聚类/分析"
- 严格 JSON 输出 + 多道兜底，失败降级为模板事件，绝不阻塞批次
- 严重度由 LLM 直接判定（p0-p3），不在此处做规则修正
- 事件 upsert 完全幂等：merge 时 item_count_inc + last_seen_at 滚动
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.feed_event import FeedEvent
    from paimon.foundation.irminsul.subscription import Subscription
    from paimon.llm.model import Model


# 同一订阅 7 天回看；超出按 last_seen_at 截
LOOKBACK_SECONDS = 7 * 24 * 3600
# 单批送聚类 LLM 的"近期事件候选"上限
MAX_RECENT_CANDIDATES = 20
# 单事件最多关联条目数（防 LLM 错把 wholly irrelevant 条目都塞过来）
MAX_ITEMS_PER_EVENT = 30
# 新事件分析时 description 截断长度
MAX_DESC_LEN = 400
# title 最长字数（超过 LLM 输出截断）
MAX_TITLE_LEN = 80
# summary 最长字数
MAX_SUMMARY_LEN = 200
# severity / sentiment_label 的合法集合
_VALID_SEVERITY = {"p0", "p1", "p2", "p3"}
_VALID_SENTIMENT_LABEL = {"positive", "neutral", "negative", "mixed"}


@dataclass
class ProcessedEvent:
    """聚类 + 分析后的单个事件，给 collect_subscription 做后续推送决策。"""
    event_id: str
    severity: str                    # 当前 severity (p0-p3)
    base_severity: str               # merge 前的旧 severity（new 时为 ""）
    is_new: bool                     # 是新建事件还是 merge 已有
    severity_changed: bool           # 跟旧 severity 不同（升级 / 降级 / 平级）
    title: str
    summary: str
    first_url: str                   # 第一个 url（推送时点开用）
    item_count: int                  # 本批次为此事件贡献的条目数
    sentiment_label: str
    sentiment_score: float
    last_seen_at: float = 0.0        # 事件最近一次更新时间 (unix)，digest 时效过滤用
    timeline: list = None            # [{"ts": int, "point": str}, ...]，digest 判定起源/动态用


# ---------- 公共工具 ----------

_CODE_FENCE = re.compile(r"^```(?:json)?\s*\n?", re.MULTILINE)
_TRAILING_FENCE = re.compile(r"\n?```\s*$", re.MULTILINE)


def _strip_code_fence(text: str) -> str:
    """LLM 偶尔包 ```json\n...\n```；剥掉再 json.loads。"""
    text = text.strip()
    text = _CODE_FENCE.sub("", text, count=1)
    text = _TRAILING_FENCE.sub("", text, count=1)
    return text.strip()


def _extract_domain(url: str) -> str:
    """从 url 抽 host（无协议返空字符串）。"""
    try:
        host = urlparse(url).netloc.lower().strip()
        # 去 www.
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    return text[:n] if len(text) > n else text


# ---------- 风神领域 DigestSpec（注入通用 prompt 模板）----------

from paimon.foundation.digest import (
    DigestSpec,
    render_analyze_prompt,
    render_cluster_prompt,
)

VENTI_DIGEST_SPEC = DigestSpec(
    actor="风神·巴巴托斯",
    domain="舆情新闻",
    item_kind="新闻条目",
    entity_kinds="人物 / 公司 / 产品 / 地点",
    cluster_examples=(
        '  * "OpenAI 发布 GPT-5"、"GPT-5 上线" → 合并\n'
        '  * "苹果 WWDC 公布 X"、"WWDC 大会回顾"、"X 在 WWDC 亮相" → 合并\n'
        '  * "DeepSeek V4 发布"、"DeepSeek 新模型开源" → 合并\n'
        '  * "苹果发布会" vs "苹果裁员" → 分开（不同动作）\n'
        '  * "OpenAI 起诉" vs "Anthropic 融资" → 分开（不同主体）'
    ),
    digest_focus="事件影响 + 整体情感倾向",
    regular_examples="产品迭代 / 例行公告",
    advice_examples="具体下一步看什么 / 何时再来扫（可选）",
)

# 风神聚类 + 分析 system prompt 由通用模板渲染（一次性 .format）
# 日报 prompt 走 venti.py 的 _compose_event_digest（保留 {query}/{n} 占位待 format）
_CLUSTER_SYSTEM = render_cluster_prompt(VENTI_DIGEST_SPEC)
_ANALYZE_SYSTEM = render_analyze_prompt(VENTI_DIGEST_SPEC)


# ---------- EventClusterer ----------

class EventClusterer:
    """风神事件聚类员：跨批次合并 + 单事件结构化抽取。

    阶段 A 行为：force_new=True，所有条目按 new 处理；analyze prompt 完整生效。
    阶段 B 起 force_new=False，启用聚类 LLM 决策跨批次合并。
    """

    def __init__(
        self, irminsul: "Irminsul", model: "Model",
        *, force_new: bool = True,
        max_llm_calls: int | None = None,
    ):
        """
        max_llm_calls: 单批最多调 LLM 次数（含聚类 + 各事件 analyze）。
                       超出预算后剩余事件走 _fallback_analysis，避免成本失控。
                       None 或 ≤0 视作不限。对应 config.sentiment_llm_calls_per_run_max
        """
        self._iru = irminsul
        self._model = model
        self._force_new = force_new
        self._max_llm_calls = max_llm_calls if (max_llm_calls and max_llm_calls > 0) else None

    async def process(
        self, sub: "Subscription", item_rows: list[dict[str, Any]],
    ) -> list[ProcessedEvent]:
        """主入口。

        item_rows: 来自 feed_items_insert 后的条目，每个 dict 必须含
        {id(int from db), title, url, description, captured_at}
        """
        if not item_rows:
            return []

        now = time.time()

        # 1) 准备聚类候选（同订阅 7 天内）
        recent: list[FeedEvent] = []
        if not self._force_new:
            recent = await self._iru.feed_event_list(
                sub_id=sub.id,
                since=now - LOOKBACK_SECONDS,
                limit=MAX_RECENT_CANDIDATES,
            )

        # 2) 聚类：grouping 决策
        # - force_new=True：跳过 LLM，每条独立成一组（仅用于排查 / fallback）
        # - 否则：调 LLM 做 grouping。同批次内多条是同事件时合并成一组；
        #   recent 即使为空（首次跑 / 周期内无历史）也调，让 LLM 至少做同批次内合并。
        #   单条输入也调（极便宜，但保证一致性）
        if self._force_new:
            groups: list[dict[str, Any]] = [
                {"item_indices": [i], "merge_with_event_id": None}
                for i in range(len(item_rows))
            ]
        elif len(item_rows) <= 1:
            # 单条没合并空间，省一次 LLM
            groups = [
                {"item_indices": [i], "merge_with_event_id": None}
                for i in range(len(item_rows))
            ]
        else:
            groups = await self._llm_cluster(sub.query, recent, item_rows)

        # 漏标兜底：LLM 没列入任何 group 的 item，单条独立成新事件
        # （宁可分裂也不丢条目；feed_items 已落库不能没 event_id）
        covered_idxs: set[int] = set()
        for g in groups:
            covered_idxs.update(g.get("item_indices") or [])
        missing = [i for i in range(len(item_rows)) if i not in covered_idxs]
        if missing:
            logger.warning(
                "[风神·事件] 聚类 LLM 漏标 {} 条 → 强制独立 new 兜底",
                len(missing),
            )
            for i in missing:
                groups.append({"item_indices": [i], "merge_with_event_id": None})

        # 3) 逐组：分析 → upsert → attach feed_items
        results: list[ProcessedEvent] = []
        recent_by_id = {ev.id: ev for ev in recent}
        llm_calls_used = 0  # LLM 调用预算计数（不含聚类那一次）

        for group in groups:
            idxs: list[int] = list(group.get("item_indices") or [])
            if not idxs:
                continue
            # 单事件最多 MAX_ITEMS_PER_EVENT 条
            idxs = idxs[:MAX_ITEMS_PER_EVENT]
            group_items = [item_rows[i] for i in idxs]
            merge_target_id = group.get("merge_with_event_id") or ""

            base_event = None
            if merge_target_id:
                base_event = recent_by_id.get(merge_target_id)
                # 二次保险：在并发场景下事件可能刚被 sweep
                if base_event is None:
                    base_event = await self._iru.feed_event_get(merge_target_id)

            # 超预算后剩余事件走 fallback，不再调 LLM
            budget_exceeded = (
                self._max_llm_calls is not None
                and llm_calls_used >= self._max_llm_calls
            )
            if budget_exceeded:
                if llm_calls_used == self._max_llm_calls:
                    # 第一次踩线提示一次（避免每个 group 都打 warning）
                    logger.warning(
                        "[风神·事件] LLM 预算 {} 已耗尽，剩余事件走 fallback",
                        self._max_llm_calls,
                    )
                analysis = self._fallback_analysis(group_items, base_event)
            else:
                try:
                    analysis = await self._llm_analyze(
                        sub.query, group_items, base_event,
                    )
                    llm_calls_used += 1
                except Exception as e:
                    logger.warning(
                        "[风神·事件] analyze LLM 异常 sub={} merge={}: {}",
                        sub.id, merge_target_id or "(new)", e,
                    )
                    analysis = self._fallback_analysis(group_items, base_event)

            sources = sorted({
                _extract_domain(it.get("url") or "")
                for it in group_items
            } - {""})

            if base_event is not None:
                # merge：累计 item_count、合并 sources、更新所有分析字段
                merged_sources = sorted(set(base_event.sources) | set(sources))
                await self._iru.feed_event_update(
                    base_event.id, actor="风神",
                    title=analysis["title"],
                    summary=analysis["summary"],
                    entities=analysis["entities"],
                    timeline=analysis["timeline"],
                    severity=analysis["severity"],
                    sentiment_score=analysis["sentiment_score"],
                    sentiment_label=analysis["sentiment_label"],
                    last_seen_at=now,
                    sources=merged_sources,
                    item_count_inc=len(group_items),
                )
                event_id = base_event.id
                base_severity = base_event.severity
                is_new = False
            else:
                # new：建事件
                from paimon.foundation.irminsul import FeedEvent as _FE
                new_event = _FE(
                    subscription_id=sub.id,
                    title=analysis["title"],
                    summary=analysis["summary"],
                    entities=analysis["entities"],
                    timeline=analysis["timeline"],
                    severity=analysis["severity"],
                    sentiment_score=analysis["sentiment_score"],
                    sentiment_label=analysis["sentiment_label"],
                    item_count=len(group_items),
                    first_seen_at=now,
                    last_seen_at=now,
                    sources=sources,
                )
                event_id = await self._iru.feed_event_create(
                    new_event, actor="风神",
                )
                base_severity = ""
                is_new = True

            # 5) 回写 feed_items.event_id + sentiment
            item_ids = [it["id"] for it in group_items]
            await self._iru.feed_items_attach_event(
                item_ids, event_id,
                sentiment_score=analysis["sentiment_score"],
                sentiment_label=analysis["sentiment_label"],
                actor="风神",
            )

            results.append(ProcessedEvent(
                event_id=event_id,
                severity=analysis["severity"],
                base_severity=base_severity,
                is_new=is_new,
                severity_changed=(analysis["severity"] != base_severity),
                title=analysis["title"],
                summary=analysis["summary"],
                first_url=(group_items[0].get("url") or ""),
                item_count=len(group_items),
                sentiment_label=analysis["sentiment_label"],
                sentiment_score=float(analysis["sentiment_score"]),
                last_seen_at=now,
                timeline=list(analysis.get("timeline") or []),
            ))

        logger.info(
            "[风神·事件] 处理完成 sub={} 输入={} 事件={}（新={} 合并={}）",
            sub.id, len(item_rows), len(results),
            sum(1 for r in results if r.is_new),
            sum(1 for r in results if not r.is_new),
        )
        return results

    # ---------- LLM 调用 ----------

    async def _llm_cluster(
        self, query: str, recent: list["FeedEvent"],
        item_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """聚类 LLM。

        返回 grouping list，每个 group 形如：
        {"item_indices": [int, ...], "merge_with_event_id": str | None}

        失败兜底：每条 item 独立成一组（merge_with_event_id=None），
        等价于"全部新建事件"，不会丢条目。
        """
        n = len(item_rows)
        fallback_groups: list[dict[str, Any]] = [
            {"item_indices": [i], "merge_with_event_id": None}
            for i in range(n)
        ]

        candidates_part = "\n".join(
            f"- event_id={ev.id} severity={ev.severity} title={ev.title}"
            f"\n  summary: {_truncate(ev.summary, 120)}"
            for ev in recent
        ) or "（暂无候选）"
        items_part = "\n".join(
            f"[{i}] title: {_truncate(it.get('title', ''), 100)}"
            f"\n     url: {it.get('url', '')}"
            f"\n     desc: {_truncate(it.get('description', ''), 150)}"
            for i, it in enumerate(item_rows)
        )
        user_msg = (
            f"订阅关键词: {query}\n\n"
            f"## 候选事件（近 7 天，最多 {MAX_RECENT_CANDIDATES} 条）\n"
            f"{candidates_part}\n\n"
            f"## 待判定的新条目（共 {n} 条；下标 0~{n-1}）\n"
            f"{items_part}\n"
        )
        messages = [
            {"role": "system", "content": _CLUSTER_SYSTEM},
            {"role": "user", "content": user_msg},
        ]
        try:
            raw, usage = await self._model._stream_text(messages)
            await self._model._record_primogem(
                "", "风神", usage, purpose="事件聚类",
            )
        except Exception as e:
            logger.warning("[风神·事件·聚类] LLM 异常 → 每条独立 new: {}", e)
            return fallback_groups

        try:
            data = json.loads(_strip_code_fence(raw))
            groups = data.get("groups")
            if not isinstance(groups, list) or not groups:
                raise ValueError("groups 缺失或空列表")
            recent_ids = {ev.id for ev in recent}
            normalized: list[dict[str, Any]] = []
            seen_idxs: set[int] = set()
            for g in groups:
                if not isinstance(g, dict):
                    continue
                indices_raw = g.get("item_indices") or []
                if not isinstance(indices_raw, list):
                    continue
                # 过滤越界、非 int、重复
                clean_idxs: list[int] = []
                for x in indices_raw:
                    try:
                        i = int(x)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= i < n and i not in seen_idxs:
                        seen_idxs.add(i)
                        clean_idxs.append(i)
                if not clean_idxs:
                    continue
                merge_id = g.get("merge_with_event_id")
                if isinstance(merge_id, str) and merge_id and merge_id in recent_ids:
                    merge_target: str | None = merge_id
                else:
                    merge_target = None  # LLM 编造了不存在的 event_id → 强制新建
                normalized.append({
                    "item_indices": clean_idxs,
                    "merge_with_event_id": merge_target,
                })
            if not normalized:
                raise ValueError("解析后 groups 为空")
            return normalized
        except Exception as e:
            logger.warning(
                "[风神·事件·聚类] JSON 解析失败 → 每条独立 new: {} | raw[:200]={}",
                e, raw[:200],
            )
            return fallback_groups

    async def _llm_analyze(
        self, query: str, items: list[dict[str, Any]],
        base_event: "FeedEvent | None",
    ) -> dict:
        """事件分析 LLM。失败抛异常，由调用方走 _fallback_analysis 兜底。"""
        items_part = "\n".join(
            f"[{i}] title: {it.get('title', '')}"
            f"\n     url: {it.get('url', '')}"
            f"\n     desc: {_truncate(it.get('description', ''), MAX_DESC_LEN)}"
            for i, it in enumerate(items)
        )
        base_part = ""
        if base_event is not None:
            base_part = (
                "\n## 已有事件 base 摘要（merge 模式）\n"
                f"title: {base_event.title}\n"
                f"summary: {base_event.summary}\n"
                f"severity(旧): {base_event.severity}\n"
                f"sentiment_label(旧): {base_event.sentiment_label}\n"
                f"item_count(旧): {base_event.item_count}\n\n"
                "请在 base 基础上做「增量演进」，summary 突出「新发展」，"
                "不要从头复述。\n"
            )
        user_msg = (
            f"订阅关键词: {query}\n"
            f"{base_part}\n"
            f"## 本组条目（{len(items)} 条）\n"
            f"{items_part}\n"
        )
        messages = [
            {"role": "system", "content": _ANALYZE_SYSTEM},
            {"role": "user", "content": user_msg},
        ]
        raw, usage = await self._model._stream_text(messages)
        await self._model._record_primogem(
            "", "风神", usage, purpose="事件分析",
        )

        data = json.loads(_strip_code_fence(raw))
        # 字段校验 + 边界规范
        title = _truncate(str(data.get("title") or ""), MAX_TITLE_LEN)
        summary = _truncate(str(data.get("summary") or ""), MAX_SUMMARY_LEN)
        if not title:
            raise ValueError("title 为空")

        entities = data.get("entities") or []
        if not isinstance(entities, list):
            entities = []
        entities = [str(e)[:40] for e in entities[:8]]

        timeline = data.get("timeline") or []
        if not isinstance(timeline, list):
            timeline = []
        norm_timeline: list[dict] = []
        for tl in timeline[:5]:
            if not isinstance(tl, dict):
                continue
            try:
                ts = float(tl.get("ts") or 0)
            except (TypeError, ValueError):
                ts = 0.0
            point = _truncate(str(tl.get("point") or ""), 100)
            if point:
                norm_timeline.append({"ts": ts, "point": point})

        severity = str(data.get("severity") or "p3").lower().strip()
        if severity not in _VALID_SEVERITY:
            severity = "p3"

        try:
            score = float(data.get("sentiment_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        score = max(-1.0, min(1.0, score))

        label = str(data.get("sentiment_label") or "neutral").lower().strip()
        if label not in _VALID_SENTIMENT_LABEL:
            label = "neutral"

        return {
            "title": title,
            "summary": summary,
            "entities": entities,
            "timeline": norm_timeline,
            "severity": severity,
            "sentiment_score": score,
            "sentiment_label": label,
        }

    @staticmethod
    def _fallback_analysis(
        items: list[dict[str, Any]],
        base_event: "FeedEvent | None",
    ) -> dict:
        """LLM 失败 / JSON 解析失败时的模板事件，severity=p3、neutral。"""
        first = items[0] if items else {}
        title = _truncate(
            str(first.get("title") or "（无标题）"),
            MAX_TITLE_LEN,
        )
        summary = _truncate(
            str(first.get("description") or first.get("title") or ""),
            MAX_SUMMARY_LEN,
        )
        if base_event is not None:
            # merge 兜底：保留 base 字段，仅在 summary 后追加"+ N 条新报道"
            return {
                "title": base_event.title,
                "summary": _truncate(
                    f"{base_event.summary}（+{len(items)} 条新报道）",
                    MAX_SUMMARY_LEN,
                ),
                "entities": base_event.entities,
                "timeline": base_event.timeline,
                "severity": base_event.severity,
                "sentiment_score": base_event.sentiment_score,
                "sentiment_label": base_event.sentiment_label,
            }
        return {
            "title": title,
            "summary": summary,
            "entities": [],
            "timeline": [],
            "severity": "p3",
            "sentiment_score": 0.0,
            "sentiment_label": "neutral",
        }
