"""世界树 SQLite 连接 + schema 初始化（无迁移代码版）。

子模块：
- _schema.sql      —— 全部表 DDL（10+ 张表，按"域"分组；纯 SQL 维护更直观）
- __init__.py      —— init_db 入口（执行 schema）

历史：曾有 _migrations.py 跑增量 ALTER + 老数据回填 + 旧表清理，
2026-05 起所有列定义合并到 _schema.sql 主表，迁移代码删除——新部署直接 schema 一次到位。
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite


# 启动时一次性读 .sql；后续 init_db 调用复用同一字符串
SCHEMA_DDL = (Path(__file__).parent / "_schema.sql").read_text(encoding="utf-8")


async def init_db(db_path) -> aiosqlite.Connection:
    """打开/创建世界树 DB、启用外键、建表。"""
    db = await aiosqlite.connect(str(db_path))
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode = WAL")  # 单用户仍有好处：读不阻塞写
    await db.executescript(SCHEMA_DDL)
    await db.commit()
    return db


__all__ = ["SCHEMA_DDL", "init_db"]
