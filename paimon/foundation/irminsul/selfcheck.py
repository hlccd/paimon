"""自检归档数据域 —— 世界树域 12

唯一写入者：三月·SelfCheckService（Quick / Deep 自检产物）
读取者：SelfCheckService（历史查询）、WebUI 面板

职责：
- selfcheck_runs 表：每次自检的元数据 + 聚合计数
- 文件系统 <home>/irminsul/selfcheck/{run_id}/ ：原始产物快照
    quick：quick_snapshot.json
    deep ：report.md / candidates.jsonl / state.json

保留策略：由 SelfCheckService 调用 gc(kind, keep_n) 裁剪最旧。
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger


@dataclass
class SelfcheckRun:
    id: str = ""
    kind: str = ""                       # 'quick' | 'deep'
    triggered_at: float = 0.0
    triggered_by: str = "user"           # 'user' / 'cron' / '三月'
    status: str = "running"              # 'running' | 'completed' | 'failed'
    duration_seconds: float = 0.0
    check_args: str = ""                 # deep 专用
    error: str = ""
    p0_count: int = 0
    p1_count: int = 0
    p2_count: int = 0
    p3_count: int = 0
    findings_total: int = 0
    quick_summary: dict[str, Any] = field(default_factory=dict)  # 解 JSON 后
    progress: dict[str, Any] = field(default_factory=dict)        # deep 专用：watcher 轮询 state.json 快照


class SelfcheckRepo:
    def __init__(self, db: aiosqlite.Connection, blobs_root: Path):
        """blobs_root = <home>/irminsul/selfcheck"""
        self._db = db
        self._root = blobs_root
        self._root.mkdir(parents=True, exist_ok=True)

    # ---------- blob path ----------

    def blob_dir(self, run_id: str) -> Path:
        """返回 run_id 对应的 blob 目录（不保证存在）。"""
        return self._root / run_id

    def ensure_blob_dir(self, run_id: str) -> Path:
        p = self.blob_dir(run_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ---------- CRUD ----------

    async def create(self, run: SelfcheckRun, *, actor: str) -> str:
        now = time.time()
        if not run.triggered_at:
            run.triggered_at = now
        await self._db.execute(
            "INSERT INTO selfcheck_runs "
            "(id, kind, triggered_at, triggered_by, status, duration_seconds, "
            "check_args, error, p0_count, p1_count, p2_count, p3_count, "
            "findings_total, quick_summary_json, progress_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run.id, run.kind, run.triggered_at, run.triggered_by,
                run.status, run.duration_seconds, run.check_args, run.error,
                run.p0_count, run.p1_count, run.p2_count, run.p3_count,
                run.findings_total,
                json.dumps(run.quick_summary, ensure_ascii=False),
                json.dumps(run.progress, ensure_ascii=False),
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·创建自检 {} kind={} by={}",
            actor, run.id, run.kind, run.triggered_by,
        )
        return run.id

    # 列名白名单：拒绝未知 key 进入 SQL（防 SEC-001 SQL 注入面）
    # 入参支持的逻辑名 quick_summary/progress 在转换后变成 _json 列；
    # 校验是基于"转换后实际进 SQL 的列名"
    _UPDATE_ALLOWED = frozenset({
        "kind", "triggered_at", "triggered_by", "status",
        "duration_seconds", "check_args", "error",
        "p0_count", "p1_count", "p2_count", "p3_count",
        "findings_total",
        "quick_summary_json", "progress_json",
    })

    async def update(
        self, run_id: str, *, actor: str, **fields,
    ) -> bool:
        if not fields:
            return False
        if "quick_summary" in fields:
            fields["quick_summary_json"] = json.dumps(
                fields.pop("quick_summary"), ensure_ascii=False,
            )
        if "progress" in fields:
            fields["progress_json"] = json.dumps(
                fields.pop("progress"), ensure_ascii=False,
            )

        unknown = set(fields) - self._UPDATE_ALLOWED
        if unknown:
            raise ValueError(
                f"SelfcheckRepo.update 不允许字段 {sorted(unknown)}; "
                f"允许 {sorted(self._UPDATE_ALLOWED)}"
            )

        cols = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [run_id]
        async with self._db.execute(
            f"UPDATE selfcheck_runs SET {cols} WHERE id = ?", values,
        ) as cur:
            rowcount = cur.rowcount
        await self._db.commit()
        if rowcount:
            logger.info(
                "[世界树] {}·更新自检 {}  ({} 字段)",
                actor, run_id, len(fields),
            )
        return bool(rowcount)

    async def get(self, run_id: str) -> SelfcheckRun | None:
        async with self._db.execute(
            "SELECT id, kind, triggered_at, triggered_by, status, "
            "duration_seconds, check_args, error, p0_count, p1_count, "
            "p2_count, p3_count, findings_total, quick_summary_json, "
            "progress_json "
            "FROM selfcheck_runs WHERE id = ?",
            (run_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return self._row_to_run(row)

    async def list(
        self, *, kind: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[SelfcheckRun]:
        conds: list[str] = []
        params: list[Any] = []
        if kind:
            conds.append("kind = ?")
            params.append(kind)
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        params.extend([limit, offset])
        sql = (
            "SELECT id, kind, triggered_at, triggered_by, status, "
            "duration_seconds, check_args, error, p0_count, p1_count, "
            "p2_count, p3_count, findings_total, quick_summary_json, "
            "progress_json "
            f"FROM selfcheck_runs {where} "
            "ORDER BY triggered_at DESC LIMIT ? OFFSET ?"
        )
        async with self._db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [self._row_to_run(r) for r in rows]

    async def count(self, *, kind: str | None = None) -> int:
        if kind:
            sql = "SELECT COUNT(*) FROM selfcheck_runs WHERE kind = ?"
            params: tuple = (kind,)
        else:
            sql = "SELECT COUNT(*) FROM selfcheck_runs"
            params = ()
        async with self._db.execute(sql, params) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def latest(self, kind: str) -> SelfcheckRun | None:
        rows = await self.list(kind=kind, limit=1, offset=0)
        return rows[0] if rows else None

    async def delete(self, run_id: str, *, actor: str) -> bool:
        """删 DB 记录 + 同步 rm 掉 blob 目录。"""
        async with self._db.execute(
            "DELETE FROM selfcheck_runs WHERE id = ?", (run_id,),
        ) as cur:
            rowcount = cur.rowcount
        await self._db.commit()

        # 文件系统同步：即便 rowcount=0 也兜底清理残留目录
        blob = self.blob_dir(run_id)
        if blob.exists():
            shutil.rmtree(blob, ignore_errors=True)

        if rowcount:
            logger.info("[世界树] {}·删除自检 {}", actor, run_id)
        return bool(rowcount)

    async def sweep_zombie_running(self, *, actor: str) -> int:
        """把所有 status='running' 的记录标 failed + 填充 error。

        启动时调一次。解决"Deep 跑一半进程被杀 → DB 记录永远 running"的问题：
        - 面板显示幽灵 running 行
        - GC 按 `status != 'running'` 过滤，永远不清理
        新进程内存态 _deep_busy 初始化为 False，DB zombie 清理后一切对齐。
        """
        async with self._db.execute(
            "SELECT id FROM selfcheck_runs WHERE status = 'running'",
        ) as cur:
            rows = await cur.fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            return 0

        placeholders = ",".join("?" * len(ids))
        await self._db.execute(
            f"UPDATE selfcheck_runs "
            f"SET status = 'failed', "
            f"    error = '进程重启前未完成（zombie running → failed）' "
            f"WHERE id IN ({placeholders})",
            ids,
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·自检 zombie 清理 {} 条 running → failed",
            actor, len(ids),
        )
        return len(ids)

    async def gc(self, *, kind: str, keep_n: int, actor: str) -> int:
        """按 kind 保留最近 keep_n 条（仅非 running 的），其余连 blob 一起删。

        返回被删的记录数。
        """
        if keep_n < 0:
            keep_n = 0
        async with self._db.execute(
            "SELECT id FROM selfcheck_runs "
            "WHERE kind = ? AND status != 'running' "
            "ORDER BY triggered_at DESC LIMIT -1 OFFSET ?",
            (kind, keep_n),
        ) as cur:
            rows = await cur.fetchall()
        to_drop = [r[0] for r in rows]
        if not to_drop:
            return 0

        # SQLite IN (?, ?, ...) 动态占位符
        placeholders = ",".join("?" * len(to_drop))
        await self._db.execute(
            f"DELETE FROM selfcheck_runs WHERE id IN ({placeholders})",
            to_drop,
        )
        await self._db.commit()

        for rid in to_drop:
            blob = self.blob_dir(rid)
            if blob.exists():
                shutil.rmtree(blob, ignore_errors=True)

        logger.info(
            "[世界树] {}·自检 GC kind={} 删除 {} 条（保留最近 {}）",
            actor, kind, len(to_drop), keep_n,
        )
        return len(to_drop)

    # ---------- helpers ----------

    @staticmethod
    def _row_to_run(row: tuple) -> SelfcheckRun:
        try:
            quick_summary = json.loads(row[13] or "{}")
        except (json.JSONDecodeError, TypeError):
            quick_summary = {}
        # progress 列（索引 14）— 旧库可能没有此列，row 长度 < 15 时兜底空 dict
        progress: dict[str, Any] = {}
        if len(row) > 14:
            try:
                progress = json.loads(row[14] or "{}")
            except (json.JSONDecodeError, TypeError):
                progress = {}
        return SelfcheckRun(
            id=row[0], kind=row[1], triggered_at=row[2],
            triggered_by=row[3], status=row[4],
            duration_seconds=row[5], check_args=row[6], error=row[7],
            p0_count=row[8], p1_count=row[9],
            p2_count=row[10], p3_count=row[11],
            findings_total=row[12], quick_summary=quick_summary,
            progress=progress,
        )
