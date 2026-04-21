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

-- ============ 域 8: 理财数据（岩神占位）============
CREATE TABLE IF NOT EXISTS dividend_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    record_date TEXT NOT NULL,
    amount REAL NOT NULL,
    yield_pct REAL NOT NULL DEFAULT 0,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dividend_symbol ON dividend_stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_dividend_date ON dividend_stocks(record_date);

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
    archived_at REAL
);
CREATE INDEX IF NOT EXISTS idx_session_channel ON session_records(channel_key);
CREATE INDEX IF NOT EXISTS idx_session_updated ON session_records(updated_at);
"""


# 未来新增列时，在此注册一条 (table, column, col_def)；启动时幂等 ALTER
_MIGRATIONS: list[tuple[str, str, str]] = [
    # ("skill_declarations", "new_column", "TEXT NOT NULL DEFAULT ''"),
]


async def init_db(db_path) -> aiosqlite.Connection:
    """打开/创建世界树 DB、启用外键、建表、跑增量迁移。"""
    db = await aiosqlite.connect(str(db_path))
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode = WAL")  # 单用户仍有好处：读不阻塞写
    await db.executescript(SCHEMA_DDL)
    await _run_migrations(db)
    await db.commit()
    return db


async def _run_migrations(db: aiosqlite.Connection) -> None:
    for table, column, col_def in _MIGRATIONS:
        async with db.execute(f"PRAGMA table_info({table})") as cur:
            cols = {row[1] async for row in cur}
        if column not in cols:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            logger.info("[世界树] schema 迁移  {} 新增列 {}", table, column)
