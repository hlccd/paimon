"""世界树 SQLite 连接 + schema 汇总 + 幂等迁移子包。

子模块：
- _schema.sql      —— 全部表 DDL（10+ 张表，按"域"分组；纯 SQL 维护更直观）
- _migrations.py   —— _MIGRATIONS 增量 ALTER 列表 + 历史数据回填 + 旧表清理
- __init__.py      —— init_db 入口（执行 schema + migrations + backfill）
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite

from ._migrations import (
    _backfill_scheduled_task_types,
    _drop_legacy_tables,
    _run_migrations,
)


# 启动时一次性读 .sql；后续 init_db 调用复用同一字符串
SCHEMA_DDL = (Path(__file__).parent / "_schema.sql").read_text(encoding="utf-8")


async def init_db(db_path) -> aiosqlite.Connection:
    """打开/创建世界树 DB、启用外键、建表、跑增量迁移。"""
    db = await aiosqlite.connect(str(db_path))
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode = WAL")  # 单用户仍有好处：读不阻塞写
    await db.executescript(SCHEMA_DDL)
    await _run_migrations(db)
    await _backfill_scheduled_task_types(db)
    await _drop_legacy_tables(db)
    await db.commit()
    return db


__all__ = ["SCHEMA_DDL", "init_db"]
