"""会话生命周期清扫 — 由三月定时触发。

会话推进链（actor=派蒙，会话域唯一写入者）：

  hot ──[N 小时无 updated & 无 channel 绑定]──► archived
  archived ──[M 天]──► 物理删除

阈值从 config 读取（session_inactive_hours / session_archived_ttl_days）。
sweep 失败只记 warning + audit，不抛给调用方——三月下轮（默认 6h）会重试。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.session import SessionManager


@dataclass
class SweepReport:
    """一次清扫的汇总，写 audit + 日志用。"""
    session_archived: list[str] = field(default_factory=list)
    session_purged: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_audit_payload(self) -> dict:
        return {
            "session_archived_count": len(self.session_archived),
            "session_purged_count": len(self.session_purged),
            "errors": self.errors[:20],
            "duration_ms": round(self.duration_ms, 1),
        }

    @property
    def total_changes(self) -> int:
        return len(self.session_archived) + len(self.session_purged)


async def sweep_sessions(
    irminsul: "Irminsul",
    *,
    now: float,
    inactive_hours: float,
    archived_ttl_days: float,
    session_mgr: "SessionManager | None" = None,
) -> tuple[list[str], list[str], list[str]]:
    """扫会话：归档不活跃的 + 删除超过 TTL 的。

    返回 (archived_ids, purged_ids, errors)。失败计入 errors 不抛。
    """
    archived: list[str] = []
    purged: list[str] = []
    errors: list[str] = []

    inactive_seconds = inactive_hours * 3600.0
    archived_ttl_seconds = archived_ttl_days * 86400.0

    # 1) 不活跃 → archived（护栏：generating / 有 channel 绑定的都跳过，SQL 内实现）
    try:
        archived = await irminsul.session_archive_if_idle(
            now=now, inactive_seconds=inactive_seconds, actor="派蒙",
        )
    except Exception as e:
        errors.append(f"session_archive_if_idle: {e}")
        logger.warning("[派蒙·会话清扫] 会话归档失败: {}", e)

    # 2) archived 过期 → 物理删除
    try:
        purged = await irminsul.session_purge_expired(
            now=now, archived_ttl_seconds=archived_ttl_seconds, actor="派蒙",
        )
    except Exception as e:
        errors.append(f"session_purge_expired: {e}")
        logger.warning("[派蒙·会话清扫] 会话过期清理失败: {}", e)

    # 3) SessionManager 内存同步
    if session_mgr is not None:
        ids_to_invalidate = list(archived) + list(purged)
        if ids_to_invalidate:
            try:
                session_mgr.invalidate_removed(ids_to_invalidate)
            except Exception as e:
                errors.append(f"session_mgr.invalidate_removed: {e}")
                logger.warning("[派蒙·会话清扫] 内存同步失败: {}", e)

    return archived, purged, errors


async def run_lifecycle_sweep(
    irminsul: "Irminsul",
    cfg,
    *,
    session_mgr: "SessionManager | None" = None,
    now: float | None = None,
) -> SweepReport:
    """三月调用的清扫入口。只读 config，不依赖任何其他服务。"""
    if not getattr(cfg, "lifecycle_sweep_enabled", True):
        logger.debug("[派蒙·会话清扫] 已禁用（lifecycle_sweep_enabled=false），跳过")
        return SweepReport()

    start = time.monotonic()
    if now is None:
        now = time.time()

    report = SweepReport()

    session_archived, session_purged, session_errors = await sweep_sessions(
        irminsul,
        now=now,
        inactive_hours=cfg.session_inactive_hours,
        archived_ttl_days=cfg.session_archived_ttl_days,
        session_mgr=session_mgr,
    )
    report.session_archived = session_archived
    report.session_purged = session_purged
    report.errors.extend(session_errors)

    report.duration_ms = (time.monotonic() - start) * 1000.0

    # 只在有变更或出错时才写 audit + INFO 日志，避免轻扫刷屏
    if report.total_changes > 0 or report.errors:
        try:
            await irminsul.audit_append(
                event_type="lifecycle_sweep_report",
                payload=report.to_audit_payload(),
                actor="派蒙·会话清扫",
            )
        except Exception as e:
            logger.warning("[派蒙·会话清扫] audit 写入失败: {}", e)
        logger.info(
            "[派蒙·会话清扫] 完成（耗时 {:.1f}ms）"
            " | 归档 {} / 删除 {} | 错误 {}",
            report.duration_ms,
            len(report.session_archived), len(report.session_purged),
            len(report.errors),
        )
    else:
        logger.debug(
            "[派蒙·会话清扫] 完成（无变更，{:.1f}ms）",
            report.duration_ms,
        )

    return report
