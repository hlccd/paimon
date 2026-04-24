"""世界树 SQLite 连接 + schema 汇总 + 幂等迁移。

10 张表的 DDL 统一落在此。每个 repo 不再各自建表。
"""
from __future__ import annotations

import aiosqlite
from loguru import logger

SCHEMA_DDL = """
-- ============ 域 1: 授权记录 ============
CREATE TABLE IF NOT EXISTS authz_records (
    id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'default',
    session_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(subject_type, subject_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_authz_user ON authz_records(user_id);

-- ============ 域 2: Skill 生态声明 ============
CREATE TABLE IF NOT EXISTS skill_declarations (
    name TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT '',
    sensitivity TEXT NOT NULL DEFAULT 'normal',
    description TEXT NOT NULL DEFAULT '',
    triggers TEXT NOT NULL DEFAULT '',
    allowed_tools TEXT NOT NULL DEFAULT '[]',
    sensitive_tools TEXT NOT NULL DEFAULT '[]',
    manifest_json TEXT NOT NULL DEFAULT '{}',
    orphaned INTEGER NOT NULL DEFAULT 0,
    installed_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_source ON skill_declarations(source);
CREATE INDEX IF NOT EXISTS idx_skill_orphaned ON skill_declarations(orphaned);

-- ============ 域 4: 记忆索引 ============
CREATE TABLE IF NOT EXISTS memory_index (
    id TEXT PRIMARY KEY,
    mem_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    title TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    ttl REAL
);
CREATE INDEX IF NOT EXISTS idx_memory_type_subject ON memory_index(mem_type, subject);
CREATE INDEX IF NOT EXISTS idx_memory_ttl ON memory_index(ttl);

-- ============ 域 5: 活跃任务（4 张表）============
CREATE TABLE IF NOT EXISTS task_edicts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    creator TEXT NOT NULL,
    status TEXT NOT NULL,
    lifecycle_stage TEXT NOT NULL DEFAULT 'hot',
    session_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    archived_at REAL
);
CREATE INDEX IF NOT EXISTS idx_task_status ON task_edicts(status);
CREATE INDEX IF NOT EXISTS idx_task_lifecycle ON task_edicts(lifecycle_stage);
CREATE INDEX IF NOT EXISTS idx_task_session ON task_edicts(session_id);

CREATE TABLE IF NOT EXISTS task_subtasks (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    parent_id TEXT,
    assignee TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (task_id) REFERENCES task_edicts(id)
);
CREATE INDEX IF NOT EXISTS idx_subtask_task ON task_subtasks(task_id);
CREATE INDEX IF NOT EXISTS idx_subtask_status ON task_subtasks(status);

CREATE TABLE IF NOT EXISTS task_flow_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    action TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    FOREIGN KEY (task_id) REFERENCES task_edicts(id)
);
CREATE INDEX IF NOT EXISTS idx_flow_task ON task_flow_history(task_id);

CREATE TABLE IF NOT EXISTS task_progress_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    subtask_id TEXT,
    agent TEXT NOT NULL,
    progress_pct INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    FOREIGN KEY (task_id) REFERENCES task_edicts(id)
);
CREATE INDEX IF NOT EXISTS idx_progress_task ON task_progress_log(task_id);

-- ============ 域 6: Token 记录 ============
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    component TEXT NOT NULL,
    model_name TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL,
    purpose TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_token_session ON token_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_token_ts ON token_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_token_component ON token_usage(component);
CREATE INDEX IF NOT EXISTS idx_token_purpose ON token_usage(purpose);

-- ============ 域 7: 审计记录 ============
CREATE TABLE IF NOT EXISTS audit_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    session_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_revisions(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_revisions(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_revisions(task_id);

-- ============ 域 8: 理财数据（岩神·红利股追踪）============
-- 三张表：watchlist（推荐股池）+ snapshot（每日评分）+ changes（变化事件）
-- 唯一写入者：岩神
CREATE TABLE IF NOT EXISTS dividend_watchlist (
    stock_code   TEXT PRIMARY KEY,
    stock_name   TEXT NOT NULL DEFAULT '',
    industry     TEXT NOT NULL DEFAULT '',
    added_date   TEXT NOT NULL,
    last_refresh TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_watchlist_industry ON dividend_watchlist(industry);

CREATE TABLE IF NOT EXISTS dividend_snapshot (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date             TEXT NOT NULL,
    stock_code            TEXT NOT NULL,
    stock_name            TEXT NOT NULL DEFAULT '',
    industry              TEXT NOT NULL DEFAULT '',
    total_score           REAL NOT NULL DEFAULT 0,
    sustainability_score  REAL NOT NULL DEFAULT 0,
    fortress_score        REAL NOT NULL DEFAULT 0,
    valuation_score       REAL NOT NULL DEFAULT 0,
    track_record_score    REAL NOT NULL DEFAULT 0,
    momentum_score        REAL NOT NULL DEFAULT 0,
    penalty               REAL NOT NULL DEFAULT 0,
    dividend_yield        REAL NOT NULL DEFAULT 0,
    pe                    REAL NOT NULL DEFAULT 0,
    pb                    REAL NOT NULL DEFAULT 0,
    roe                   REAL NOT NULL DEFAULT 0,
    market_cap            REAL NOT NULL DEFAULT 0,
    reasons               TEXT NOT NULL DEFAULT '',
    advice                TEXT NOT NULL DEFAULT '',
    detail_json           TEXT NOT NULL DEFAULT '{}',
    created_at            REAL NOT NULL,
    UNIQUE(scan_date, stock_code)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_code_date ON dividend_snapshot(stock_code, scan_date DESC);
CREATE INDEX IF NOT EXISTS idx_snapshot_date_score ON dividend_snapshot(scan_date, total_score DESC);

CREATE TABLE IF NOT EXISTS dividend_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date  TEXT NOT NULL,
    stock_code  TEXT NOT NULL,
    stock_name  TEXT NOT NULL DEFAULT '',
    event_type  TEXT NOT NULL,   -- 'entered' | 'exited' | 'score_change'
    old_value   REAL,
    new_value   REAL,
    description TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_changes_date ON dividend_changes(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_changes_code ON dividend_changes(stock_code, event_date DESC);

-- ============ 域 10: 定时任务（三月）============
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    channel_name TEXT NOT NULL DEFAULT '',
    task_prompt TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    trigger_value TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    next_run_at REAL NOT NULL DEFAULT 0,
    last_run_at REAL NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sched_enabled ON scheduled_tasks(enabled);
CREATE INDEX IF NOT EXISTS idx_sched_next ON scheduled_tasks(next_run_at);

-- ============ 域 11: 订阅（风神）============
CREATE TABLE IF NOT EXISTS subscriptions (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL DEFAULT 'default',
    query          TEXT NOT NULL,
    channel_name   TEXT NOT NULL,
    chat_id        TEXT NOT NULL,
    schedule_cron  TEXT NOT NULL,
    max_items      INTEGER NOT NULL DEFAULT 10,
    engine         TEXT NOT NULL DEFAULT '',
    enabled        INTEGER NOT NULL DEFAULT 1,
    linked_task_id TEXT NOT NULL DEFAULT '',
    last_run_at    REAL NOT NULL DEFAULT 0,
    last_error     TEXT NOT NULL DEFAULT '',
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sub_enabled ON subscriptions(enabled);
CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id);

CREATE TABLE IF NOT EXISTS feed_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    engine          TEXT NOT NULL DEFAULT '',
    captured_at     REAL NOT NULL,
    pushed_at       REAL,
    digest_id       TEXT NOT NULL DEFAULT '',
    UNIQUE(subscription_id, url),
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);
CREATE INDEX IF NOT EXISTS idx_feed_sub ON feed_items(subscription_id);
CREATE INDEX IF NOT EXISTS idx_feed_captured ON feed_items(captured_at);
CREATE INDEX IF NOT EXISTS idx_feed_pushed ON feed_items(pushed_at);

-- ============ 域 9: 聊天会话 ============
CREATE TABLE IF NOT EXISTS session_records (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    channel_key TEXT NOT NULL DEFAULT '',
    messages_json TEXT NOT NULL DEFAULT '[]',
    session_memory_json TEXT NOT NULL DEFAULT '[]',
    last_context_tokens INTEGER NOT NULL DEFAULT 0,
    last_context_ratio REAL NOT NULL DEFAULT 0.0,
    last_compressed_at REAL NOT NULL DEFAULT 0.0,
    compressed_rounds INTEGER NOT NULL DEFAULT 0,
    response_status TEXT NOT NULL DEFAULT 'idle',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    archived_at REAL,
    compression_failures INTEGER NOT NULL DEFAULT 0,
    auto_compact_disabled INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_session_channel ON session_records(channel_key);
CREATE INDEX IF NOT EXISTS idx_session_updated ON session_records(updated_at);

-- ============ 域 12: 自检归档（三月）============
-- 每次 Quick / Deep 自检的元数据 + 聚合计数；完整产物（report.md / candidates.jsonl / state.json）
-- 落文件系统 `.paimon/irminsul/selfcheck/{run_id}/`。
-- docs/foundation/march.md §自检体系
CREATE TABLE IF NOT EXISTS selfcheck_runs (
    id                 TEXT PRIMARY KEY,                 -- 12 位 hex
    kind               TEXT NOT NULL,                    -- 'quick' | 'deep'
    triggered_at       REAL NOT NULL,
    triggered_by       TEXT NOT NULL DEFAULT 'user',     -- 'user' / 'cron' / '三月' 等
    status             TEXT NOT NULL DEFAULT 'running',  -- 'running' | 'completed' | 'failed'
    duration_seconds   REAL NOT NULL DEFAULT 0,
    check_args         TEXT NOT NULL DEFAULT '',         -- deep 专用：check 命令的参数
    error              TEXT NOT NULL DEFAULT '',
    p0_count           INTEGER NOT NULL DEFAULT 0,
    p1_count           INTEGER NOT NULL DEFAULT 0,
    p2_count           INTEGER NOT NULL DEFAULT 0,
    p3_count           INTEGER NOT NULL DEFAULT 0,
    findings_total     INTEGER NOT NULL DEFAULT 0,
    quick_summary_json TEXT NOT NULL DEFAULT '{}'        -- quick 专用：overall + component 快照
);
CREATE INDEX IF NOT EXISTS idx_selfcheck_kind ON selfcheck_runs(kind);
CREATE INDEX IF NOT EXISTS idx_selfcheck_time ON selfcheck_runs(triggered_at DESC);
"""


# 未来新增列时，在此注册一条 (table, column, col_def)；启动时幂等 ALTER
_MIGRATIONS: list[tuple[str, str, str]] = [
    # 授权体系：skill_declarations 加 sensitive_tools（allowed_tools 命中敏感清单的子集）
    ("skill_declarations", "sensitive_tools", "TEXT NOT NULL DEFAULT '[]'"),
    # 时执压缩熔断：连续失败计数 + 禁用标志
    ("session_records", "compression_failures", "INTEGER NOT NULL DEFAULT 0"),
    ("session_records", "auto_compact_disabled", "INTEGER NOT NULL DEFAULT 0"),
    # 四影闭环：子任务 DAG + 多轮迭代 + 敏感操作预声明 + 水神裁决标记
    ("task_subtasks", "deps", "TEXT NOT NULL DEFAULT '[]'"),
    ("task_subtasks", "round", "INTEGER NOT NULL DEFAULT 1"),
    ("task_subtasks", "sensitive_ops", "TEXT NOT NULL DEFAULT '[]'"),
    ("task_subtasks", "verdict_status", "TEXT NOT NULL DEFAULT ''"),
    # 四影闭环 v2：saga 补偿动作（失败回滚）
    ("task_subtasks", "compensate", "TEXT NOT NULL DEFAULT ''"),
    # 三月·自检：Deep 进度快照（watcher 轮询 .check/state.json 后存此列）
    ("selfcheck_runs", "progress_json", "TEXT NOT NULL DEFAULT '{}'"),
]


async def init_db(db_path) -> aiosqlite.Connection:
    """打开/创建世界树 DB、启用外键、建表、跑增量迁移。"""
    db = await aiosqlite.connect(str(db_path))
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode = WAL")  # 单用户仍有好处：读不阻塞写
    await db.executescript(SCHEMA_DDL)
    await _run_migrations(db)
    await _drop_legacy_tables(db)
    await db.commit()
    return db


async def _drop_legacy_tables(db: aiosqlite.Connection) -> None:
    """清理历史版本遗留的表名（幂等；首次启动或新 DB 上无副作用）。"""
    # 2026-04-24: 岩神·红利股追踪重构——旧 dividend_stocks 单表被 dividend_watchlist/
    # dividend_snapshot/dividend_changes 取代；旧表从未被业务方写入。
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dividend_stocks'",
    ) as cur:
        row = await cur.fetchone()
    if row:
        await db.execute("DROP TABLE dividend_stocks")
        logger.info("[世界树] schema 迁移  DROP 旧表 dividend_stocks")


async def _run_migrations(db: aiosqlite.Connection) -> None:
    for table, column, col_def in _MIGRATIONS:
        async with db.execute(f"PRAGMA table_info({table})") as cur:
            cols = {row[1] async for row in cur}
        if column not in cols:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            logger.info("[世界树] schema 迁移  {} 新增列 {}", table, column)
