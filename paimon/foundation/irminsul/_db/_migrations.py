"""世界树 schema 迁移：增量 ALTER + 历史数据回填 + 旧表清理。

每条 _MIGRATIONS 是 (table, column, col_def) 三元组；启动幂等执行，已存在的列跳过。
_backfill_scheduled_task_types：把旧 [PREFIX] 编码的 task_prompt 升级到 task_type 字段。
_drop_legacy_tables：清理被替代的历史表名。
"""
from __future__ import annotations

import aiosqlite
from loguru import logger


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
    # 风神 L1·事件级舆情：feed_items 关联事件 + 缓存条目级情感
    ("feed_items", "event_id",         "TEXT NOT NULL DEFAULT ''"),
    ("feed_items", "sentiment_score",  "REAL NOT NULL DEFAULT 0.0"),
    ("feed_items", "sentiment_label",  "TEXT NOT NULL DEFAULT ''"),
    # 定时任务类型化（方案 D）：把 task_prompt 里的 [PREFIX] 魔法编码
    # 升级为 schema 字段，正式支持 archon 各自注册 task_type
    ("scheduled_tasks", "task_type", "TEXT NOT NULL DEFAULT 'user'"),
    ("scheduled_tasks", "source_entity_id", "TEXT NOT NULL DEFAULT ''"),
    # 水神·抽卡三游戏化：旧数据全归原神（gs）
    ("mihoyo_gacha", "game", "TEXT NOT NULL DEFAULT 'gs'"),
    # 订阅生命周期改造：subscription 加业务实体绑定字段（区别于 ScheduledTask.source_entity_id）
    # binding_kind='manual' 是手填关键词订阅；'mihoyo_game' 是水神隐式订阅；后续可扩 stock_watch 等
    ("subscriptions", "binding_kind", "TEXT NOT NULL DEFAULT 'manual'"),
    ("subscriptions", "binding_id",   "TEXT NOT NULL DEFAULT ''"),
]


async def _backfill_scheduled_task_types(db: aiosqlite.Connection) -> None:
    """把旧 [PREFIX] 编码的 scheduled_tasks 回填到 task_type/source_entity_id 字段。

    幂等：只 UPDATE 还停留在 task_type='user' 且 task_prompt 是旧前缀格式的行；
    首次启动后都已正确归位，后续启动 no-op。
    保留 task_prompt 原值——即便代码回滚，旧 startswith 分派仍能工作。
    """
    backfills: list[tuple[str, str]] = [
        ("feed_collect", "[FEED_COLLECT] "),
        ("dividend_scan", "[DIVIDEND_SCAN] "),
    ]
    for task_type, prefix in backfills:
        async with db.execute(
            "SELECT COUNT(*) FROM scheduled_tasks "
            "WHERE task_type = 'user' AND task_prompt LIKE ?",
            (prefix + "%",),
        ) as cur:
            row = await cur.fetchone()
        n = (row or (0,))[0]
        if not n:
            continue
        await db.execute(
            "UPDATE scheduled_tasks SET "
            "  task_type = ?, "
            "  source_entity_id = SUBSTR(task_prompt, ? + 1) "
            "WHERE task_type = 'user' AND task_prompt LIKE ?",
            (task_type, len(prefix), prefix + "%"),
        )
        logger.info(
            "[世界树] schema 迁移  scheduled_tasks 回填 task_type={} 共 {} 条",
            task_type, n,
        )


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
    """跑 _MIGRATIONS 列表：每条幂等 ALTER（已存在的列跳过）。"""
    for table, column, col_def in _MIGRATIONS:
        async with db.execute(f"PRAGMA table_info({table})") as cur:
            cols = {row[1] async for row in cur}
        if column not in cols:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            logger.info("[世界树] schema 迁移  {} 新增列 {}", table, column)
