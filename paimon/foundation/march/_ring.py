"""三月事件响铃实现：静默落 push_archive + 滑窗限流 + 日级幂等 + audit 审计。

抽离为独立 free function 让 service.py 类文件不超过 500 行；MarchService.ring_event
只是 5 行 delegator，行为与原实现完全一致。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from ._helpers import (
    RING_EVENT_MAX_PER_WINDOW,
    RING_EVENT_WINDOW_SECONDS,
    today_local_bounds,
)

if TYPE_CHECKING:
    from .service import MarchService


async def ring_event_impl(
    svc: "MarchService",
    *,
    channel_name: str,
    chat_id: str,
    source: str,
    message: str = "",
    prompt: str = "",
    task_id: str = "",
    level: str = "silent",
    extra: dict | None = None,
    dedup_per_day: bool = False,
) -> bool:
    """事件响铃入口（2026-04-25 改造为静默归档）。

    历史：原本经地脉 `march.ring` 投递到聊天会话，污染对话流。
    现在：所有 ring_event 调用静默落地到世界树 `push_archive` 域，
    WebUI 导航栏全局红点 + 抽屉消费；聊天会话只承载用户对话 + /schedule
    定时任务（_fire_task 路径不变）。

    参数：
      svc: 调用方 MarchService 实例（用 _irminsul / _leyline / _event_rate_limit）
      channel_name: 推送目标频道（webui / telegram / qq），仅供归档元信息
      chat_id:      推送目标会话 id（同上，归档用）
      source:       调用方（"风神·舆情日报" / "风神·舆情预警" / "岩神·..."）
      message:      整理好的 markdown 文案（必填；prompt 字段已废弃）
      prompt:       已废弃，传入会被并入 message 末尾（保兼容）
      task_id:      可选，关联的定时任务 id（写入 extra_json）
      level:        'silent'（默认，不打断）| 'loud'（预留，当前实现仍是静默）
      dedup_per_day: 日级幂等模式（默认 False）。True 时按 (actor, source,
                    当地日期) 去重：当日首次响铃新建一条；同日再次响铃且
                    message 未变 → no-op；message 变了 → 原地更新并 reset
                    未读。适用于「每日订阅日报」/「红利股变化」这类 cron
                    + 手动刷新会重复推送的场景。事件驱动型（P0 预警）应
                    保持 False。dedup 路径跳过滑窗限流（upsert 本身幂等）。

    返回：
      True  — 已归档（含 created / updated / unchanged）
      False — 被限流拒绝（仅非 dedup 路径）

    抛出：
      ValueError — message 为空 / source / channel_name / chat_id 缺失
    """
    # prompt 字段早期设计为 LLM 人格化提示，现已废弃；如调用方还传，并入 message
    if prompt and not message:
        message = prompt
    elif prompt and message:
        message = f"{message}\n\n{prompt}"
    if not message:
        raise ValueError("ring_event: message 非空（prompt 已废弃，请用 message）")
    # strip 校验
    source = (source or "").strip()
    channel_name = (channel_name or "").strip()
    chat_id = (chat_id or "").strip()
    if not source or not channel_name or not chat_id:
        raise ValueError("ring_event: source / channel_name / chat_id 均必填")
    if any(c in source for c in "\n\r\t"):
        raise ValueError("ring_event: source 不能含换行/制表符")

    # 非 dedup 路径才走滑窗限流；dedup 是幂等 upsert，重复调用本身无副作用
    if not dedup_per_day:
        key = (source, channel_name, chat_id)
        if not svc._rate_limit_check(key):
            logger.warning(
                "[三月·事件响铃] 限流拒绝 source={} channel={}/{} "
                "({}s 内已 ≥{} 次)",
                source, channel_name, chat_id[:20],
                RING_EVENT_WINDOW_SECONDS, RING_EVENT_MAX_PER_WINDOW,
            )
            return False

    # 从 source 推出 actor（"风神·舆情日报" → "风神"）；用于面板按神分组
    actor = source.split("·", 1)[0] if "·" in source else source

    # 落地到 push_archive（静默归档）
    # extra: 调用方扩展字段（如 sub_id / event_id / change_id）+ task_id（如有）
    merged_extra: dict = dict(extra) if extra else {}
    if task_id and "task_id" not in merged_extra:
        merged_extra["task_id"] = task_id
    rec_id = ""
    upsert_status = ""  # created / updated / unchanged（仅 dedup 路径有值）
    try:
        if dedup_per_day:
            day_start, day_end = today_local_bounds()
            upsert_status, rec_id = await svc._irminsul.push_archive_upsert_daily(
                source=source, actor=actor,
                message_md=message,
                day_start=day_start, day_end=day_end,
                channel_name=channel_name, chat_id=chat_id,
                level=level,
                extra=merged_extra,
            )
        else:
            rec_id = await svc._irminsul.push_archive_create(
                source=source, actor=actor,
                message_md=message,
                channel_name=channel_name, chat_id=chat_id,
                level=level,
                extra=merged_extra,
            )
    except Exception as e:
        logger.error("[三月·事件响铃] 归档失败 source={}: {}", source, e)
        return False

    # 通知 WebUI 红点更新（前端 SSE 可订阅；当前用前端 30s 轮询，
    # 这条 publish 是预留扩展点）
    # dedup 路径下 unchanged 状态不再触发红点（用户既然已读、内容也没变）
    publish_event = not (dedup_per_day and upsert_status == "unchanged")
    if publish_event:
        try:
            await svc._leyline.publish(
                "push.archived",
                {"id": rec_id, "actor": actor, "source": source, "level": level},
                source=f"三月·事件响铃@{actor}",
            )
        except Exception as e:
            logger.debug("[三月·事件响铃] leyline publish 失败（不影响归档）: {}", e)

    if dedup_per_day:
        logger.info(
            "[三月·事件响铃] source={} → push_archive {} (actor={} len={} daily={})",
            source, rec_id, actor, len(message), upsert_status,
        )
    else:
        logger.info(
            "[三月·事件响铃] source={} → push_archive {} (actor={} len={})",
            source, rec_id, actor, len(message),
        )

    # audit 落盘（失败不影响推送链路）
    try:
        await svc._irminsul.audit_append(
            event_type="march_ring_event",
            payload={
                "source": source,
                "actor": actor,
                "archive_id": rec_id,
                "channel_name": channel_name,
                "chat_id": chat_id,
                "level": level,
                "message_prefix": message[:200],
                "task_id": task_id,
            },
            actor=f"三月·{source}",
        )
    except Exception as e:
        logger.debug("[三月·事件响铃] audit 写入失败（不影响推送）: {}", e)

    return True
