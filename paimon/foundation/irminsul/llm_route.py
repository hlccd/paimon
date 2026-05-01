"""世界树域 15 · LLM 路由表（component[:purpose] → profile_id）

M2：给 Model.chat 按调用场景选 profile 的存储后盾。配合 model_router.py 的
resolve 算法：
  1. "component:purpose" 精确命中
  2. "component" 粗匹配
  3. 回落 LLMProfile.is_default

FK 到 llm_profiles.id + ON DELETE CASCADE —— profile 被删路由自动清理。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import aiosqlite
from loguru import logger


@dataclass
class LLMRoute:
    route_key: str = ""      # "风神" 或 "风神:事件聚类"
    profile_id: str = ""
    updated_at: float = 0.0


class LLMRouteRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def upsert(
        self, route_key: str, profile_id: str, *, actor: str,
    ) -> None:
        now = time.time()
        await self._db.execute(
            "INSERT INTO llm_routes (route_key, profile_id, updated_at) "
            "VALUES (?,?,?) "
            "ON CONFLICT(route_key) DO UPDATE SET "
            "profile_id=excluded.profile_id, updated_at=excluded.updated_at",
            (route_key, profile_id, now),
        )
        await self._db.commit()
        logger.info(
            "[世界树·LLM 路由] upsert key={} → profile={} actor={}",
            route_key, profile_id, actor,
        )

    async def delete(self, route_key: str, *, actor: str) -> bool:
        async with self._db.execute(
            "DELETE FROM llm_routes WHERE route_key = ?", (route_key,),
        ) as cur:
            ok = cur.rowcount > 0
        await self._db.commit()
        if ok:
            logger.info(
                "[世界树·LLM 路由] 删除 key={} actor={}", route_key, actor,
            )
        return ok

    async def get(self, route_key: str) -> LLMRoute | None:
        async with self._db.execute(
            "SELECT route_key, profile_id, updated_at FROM llm_routes "
            "WHERE route_key = ?", (route_key,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return LLMRoute(
            route_key=row[0], profile_id=row[1], updated_at=float(row[2]),
        )

    async def list_all(self) -> list[LLMRoute]:
        async with self._db.execute(
            "SELECT route_key, profile_id, updated_at FROM llm_routes "
            "ORDER BY route_key ASC",
        ) as cur:
            rows = await cur.fetchall()
        return [
            LLMRoute(route_key=r[0], profile_id=r[1], updated_at=float(r[2]))
            for r in rows
        ]

    async def clear_for_profile(self, profile_id: str, *, actor: str) -> int:
        """删除所有指向该 profile 的路由（FK CASCADE 通常会自动，此接口做显式清理备用）。"""
        async with self._db.execute(
            "DELETE FROM llm_routes WHERE profile_id = ?", (profile_id,),
        ) as cur:
            n = cur.rowcount
        await self._db.commit()
        if n > 0:
            logger.info(
                "[世界树·LLM 路由] 清理 profile={} 相关路由 {} 条 actor={}",
                profile_id, n, actor,
            )
        return n

    async def delete_purpose_overrides_for(
        self, component: str, *, actor: str,
    ) -> list[str]:
        """清空该 component 下所有 'component:purpose' 路由（不动 'component' 自身）。

        面板 cascade 操作用：组级 selector 改值时，把已"独立设置"的 purpose 全部
        恢复继承新组级值。返回被删 route_key 列表，调用方据此发 leyline 事件。
        """
        if not component:
            return []
        pattern = component + ":%"
        async with self._db.execute(
            "SELECT route_key FROM llm_routes WHERE route_key LIKE ?",
            (pattern,),
        ) as cur:
            keys = [r[0] for r in await cur.fetchall()]
        if not keys:
            return []
        await self._db.execute(
            "DELETE FROM llm_routes WHERE route_key LIKE ?", (pattern,),
        )
        await self._db.commit()
        logger.info(
            "[世界树·LLM 路由] 清空 component={} 下 purpose 路由 {} 条 actor={}",
            component, len(keys), actor,
        )
        return keys
