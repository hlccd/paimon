"""世界树 SQLite 连接 + schema 初始化 + 轻量增量迁移。

子模块：
- _schema.sql      —— 全部表 DDL（按"域"分组；新建 DB 用）
- _migrations.py   —— 增量 ALTER TABLE ADD COLUMN 列表（自动升级老 DB 用）
- __init__.py      —— init_db 入口（执行 schema → 跑 migrations）

设计：新建 DB 走 _schema.sql 一次到位；老 DB 升级时靠 _migrations.py 幂等补列。
不支持 DROP / ALTER COLUMN TYPE 等破坏性迁移（那种走「删 .paimon 重跑」原则）。
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite

from ._migrations import run_migrations


# 启动时一次性读 .sql；后续 init_db 调用复用同一字符串
SCHEMA_DDL = (Path(__file__).parent / "_schema.sql").read_text(encoding="utf-8")


async def init_db(db_path) -> aiosqlite.Connection:
    """打开/创建世界树 DB、启用外键、建表、跑增量迁移。"""
    db = await aiosqlite.connect(str(db_path))
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode = WAL")  # 单用户仍有好处：读不阻塞写
    await db.executescript(SCHEMA_DDL)
    await run_migrations(db)
    await db.commit()
    return db


__all__ = ["SCHEMA_DDL", "init_db"]
