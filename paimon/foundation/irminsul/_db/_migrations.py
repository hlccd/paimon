"""世界树 schema 增量迁移：启动时幂等 ALTER TABLE ADD COLUMN。

为什么需要：自动 git pull 升级模式下，服务器上 .paimon/irminsul.db 是老 DB，
新代码 _schema.sql 加了列时 `CREATE TABLE IF NOT EXISTS` 会跳过老表，新列不会被加上 →
业务 INSERT/SELECT 时 `no such column` 报错（schema 漂移）。

解决：每次新加列时**作者必须**在 _MIGRATIONS 列表登记一条 (table, column, col_def)，
启动时 _run_migrations 幂等 ALTER TABLE ADD COLUMN（已存在的列跳过）。

约束：本文件**只管增量 ALTER ADD COLUMN**，不管 DROP / ALTER COLUMN TYPE 等破坏性操作。
那些操作仍按「彻底新部署」原则处理（删 .paimon 重跑）。

SEC-001 防注入：table/column/col_def 全部硬编码，但保留 _validate_identifier 二次校验。
"""
from __future__ import annotations

import re

import aiosqlite
from loguru import logger


# SQL 标识符（表名/列名）格式：[a-zA-Z_][a-zA-Z0-9_]*，长度 ≤ 64
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]{0,63}$")
# 列定义允许的字符：拒绝分号 / 注释序列 / 反引号 等会改变 SQL 语句结构的字符
_COLDEF_BLOCKLIST = re.compile(r"[;`]|--|/\*|\*/")


def _validate_identifier(name: str, kind: str) -> None:
    """校验 SQL 标识符（表名/列名）。不通过即抛 ValueError。"""
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"非法 {kind} 名（仅允许字母数字下划线，≤64 字符）: {name!r}")


def _validate_col_def(col_def: str) -> None:
    """校验列定义字符串：拒绝分号/SQL 注释序列等。"""
    if _COLDEF_BLOCKLIST.search(col_def):
        raise ValueError(f"非法列定义（含 ; 或注释序列）: {col_def!r}")


# 新增列时**必须**在此登记，启动时幂等 ALTER。一旦合并到 _schema.sql 主表后**不要**
# 从此列表删除——本地有老 DB 的实例下次启动还需要靠这条 ALTER 补列。
#
# 当前为空：2026-05 启动瘦身已合并 13 列到 _schema.sql；之后新增列从这里登记。
# 例如：("task_subtasks", "new_col_y", "TEXT NOT NULL DEFAULT ''"),
_MIGRATIONS: list[tuple[str, str, str]] = [
]


async def run_migrations(db: aiosqlite.Connection) -> None:
    """跑 _MIGRATIONS 列表：每条幂等 ALTER（已存在的列跳过）。"""
    for table, column, col_def in _MIGRATIONS:
        # SEC-001 二次校验
        _validate_identifier(table, "table")
        _validate_identifier(column, "column")
        _validate_col_def(col_def)
        async with db.execute(f"PRAGMA table_info({table})") as cur:
            cols = {row[1] async for row in cur}
        if column not in cols:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            logger.info("[世界树] schema 迁移  {} 新增列 {}", table, column)
