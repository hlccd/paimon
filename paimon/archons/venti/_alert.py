"""风神 · P0 即时预警 mixin：_dispatch_p0_alerts 投送 + _compose_p0_urgent 文案。"""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from loguru import logger


class _AlertMixin:
    """P0 严重事件即时预警相关方法集合。"""

    async def _dispatch_p0_alerts(
        self, sub, processed_events: list, irminsul: Irminsul,
        march: "MarchService", cfg,
    ) -> None:
        """筛 p0 事件 + 冷却 check + 推 march.ring_event(source='风神·舆情预警')。

        触发条件（择一）：
        - 新事件 severity=p0
        - 已有事件升级到 p0（base_severity=p1/p2/p3）

        失败静默（推送失败不阻塞日常 digest 推送）。
        """
        from paimon.foundation.irminsul import is_severity_upgrade

        if not processed_events:
            return
        # 选出本批次需要紧急推送的 p0 事件
        urgent = [
            ev for ev in processed_events
            if ev.severity == "p0"
            and (ev.is_new or is_severity_upgrade(ev.base_severity, ev.severity))
        ]
        if not urgent:
            return

        cooldown_seconds = max(
            60, int(getattr(cfg, "sentiment_p0_cooldown_minutes", 30)) * 60,
        )
        now = time.time()

        for ev in urgent:
            # 重读 DB 拿到完整事件信息（entities / sources / last_pushed_at）
            try:
                event_obj = await irminsul.feed_event_get(ev.event_id)
            except Exception as e:
                logger.warning("[风神·舆情预警] 读事件失败 {}: {}", ev.event_id, e)
                continue
            if event_obj is None:
                logger.warning(
                    "[风神·舆情预警] 事件已被删除 {}，跳过", ev.event_id,
                )
                continue

            # 升级冷却：同事件 N 分钟内不重推
            if event_obj.last_pushed_at and (
                now - event_obj.last_pushed_at < cooldown_seconds
            ):
                logger.info(
                    "[风神·舆情预警] 冷却中 event={} ({}s 前刚推过)",
                    ev.event_id[:8], int(now - event_obj.last_pushed_at),
                )
                continue

            urgent_md = self._compose_p0_urgent(sub, ev, event_obj)
            try:
                ok = await march.ring_event(
                    channel_name=sub.channel_name,
                    chat_id=sub.chat_id,
                    source=f"风神·舆情预警·{(sub.query or '')[:20]}",
                    message=urgent_md,
                    extra={
                        "sub_id": sub.id,
                        "query": sub.query,
                        "event_id": ev.event_id,
                    },
                )
            except Exception as e:
                logger.error(
                    "[风神·舆情预警] 响铃失败 event={}: {}", ev.event_id, e,
                )
                ok = False
            if not ok:
                logger.warning(
                    "[风神·舆情预警] 响铃被拒 event={}（事件仍落盘）",
                    ev.event_id[:8],
                )
                continue

            # 推送成功 → 更新 last_pushed_at + last_severity + pushed_count
            try:
                await irminsul.feed_event_update(
                    ev.event_id, actor="风神·舆情预警",
                    last_pushed_at=now,
                    last_severity=ev.severity,
                    pushed_count_inc=1,
                )
            except Exception as e:
                logger.warning(
                    "[风神·舆情预警] 更新冷却字段失败 {}: {}",
                    ev.event_id[:8], e,
                )

            # audit 记一条（payload 不含敏感字段，便于后续在 dashboard 复盘）
            try:
                await irminsul.audit_append(
                    event_type="feed_event_pushed",
                    payload={
                        "sub_id": sub.id,
                        "event_id": ev.event_id,
                        "severity": ev.severity,
                        "base_severity": ev.base_severity,
                        "is_new": ev.is_new,
                        "is_upgrade": is_severity_upgrade(
                            ev.base_severity, ev.severity,
                        ),
                        "alert_kind": "p0_urgent",
                    },
                    actor="风神·舆情预警",
                )
            except Exception as e:
                logger.debug("[风神·舆情预警] audit 写失败（吞）: {}", e)

            logger.warning(
                "[风神·舆情预警] 已推送 P0 event={} title='{}' "
                "(was '{}' → 'p0', sub={})",
                ev.event_id[:8], ev.title[:40],
                ev.base_severity or "new", sub.id,
            )

    def _compose_p0_urgent(self, sub, processed_ev, event_obj) -> str:
        """生成 P0 紧急推送 markdown（docs/archons/venti.md §L1 / plan §7）。"""
        from paimon.foundation.irminsul import is_severity_upgrade
        from datetime import datetime

        # 升级标记
        upgrade_tag = ""
        if not processed_ev.is_new and is_severity_upgrade(
            processed_ev.base_severity, processed_ev.severity,
        ):
            upgrade_tag = f"（{processed_ev.base_severity} → p0 严重度上调）"

        # 情感数值格式
        score = event_obj.sentiment_score
        score_str = f"{score:+.2f}"
        sentiment_disp = (
            f"{event_obj.sentiment_label}（{score_str}）"
            if event_obj.sentiment_label else "未分析"
        )

        # 实体（最多 5 个）
        entities_str = "、".join(event_obj.entities[:5]) or "（无）"

        # 信源（最多 5 个 + 总条目数）
        sources_str = "、".join(event_obj.sources[:5])
        if not sources_str:
            sources_str = "（无信源）"
        sources_str = f"{sources_str}（共 {event_obj.item_count} 条报道）"

        last_seen = datetime.fromtimestamp(
            event_obj.last_seen_at,
        ).strftime("%Y-%m-%d %H:%M")

        first_url = processed_ev.first_url or ""
        title_md = (
            f"[{processed_ev.title}]({first_url})"
            if first_url else processed_ev.title
        )

        return (
            f"🚨 **风神·舆情预警 [P0]**{upgrade_tag}\n"
            f"\n"
            f"**订阅**：{sub.query}\n"
            f"**事件**：{title_md}\n"
            f"**摘要**：{processed_ev.summary or event_obj.summary}\n"
            f"**情感**：{sentiment_disp}\n"
            f"**关联实体**：{entities_str}\n"
            f"**信源**：{sources_str}\n"
            f"**最近更新**：{last_seen}"
        )
