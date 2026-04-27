"""世界树域 14 · LLM Profile（用户可管理的模型条目）

把"模型配置"抽成用户可管理的第一类实体。同一个 API 端点下的不同 model、
不同 thinking 配置都能独立成一条 profile；未来扩展无需改代码。

M1 范围：仅存储 + 面板管理。M2 会加 `llm_routes` 表并让 Model.chat 按
component+purpose 路由到 profile。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import aiosqlite
from loguru import logger


@dataclass
class LLMProfile:
    id: str = ""
    name: str = ""                    # 展示名（UNIQUE），如 "DS v4-pro (thinking high)"
    provider_kind: str = "openai"     # "anthropic" | "openai"（决定用哪个 Provider 类）
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 64000           # 仅 anthropic 生效
    reasoning_effort: str = ""        # "" | "high" | "max"，仅 openai/deepseek 生效
    extra_body: dict[str, Any] | None = None   # 如 {"thinking":{"type":"enabled"}}
    is_default: bool = False
    notes: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


_MASKED = "***"


def _mask_key(key: str) -> str:
    """掩码 api_key：列表展示用；编辑面板要真正改还得重新填。"""
    return _MASKED if key else ""


class LLMProfileRepo:
    """LLM Profile 仓储。"""

    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    # ---------- 写入 ----------

    async def create(self, profile: LLMProfile, *, actor: str) -> str:
        profile_id = uuid4().hex[:12]
        now = time.time()
        extra_body_json = json.dumps(profile.extra_body or {}, ensure_ascii=False)
        await self._db.execute(
            "INSERT INTO llm_profiles "
            "(id, name, provider_kind, api_key, base_url, model, "
            "max_tokens, reasoning_effort, extra_body_json, is_default, notes, "
            "created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                profile_id, profile.name, profile.provider_kind,
                profile.api_key, profile.base_url, profile.model,
                profile.max_tokens, profile.reasoning_effort, extra_body_json,
                1 if profile.is_default else 0, profile.notes,
                now, now,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树·LLM Profile] 新建 {} name={} kind={} model={} actor={}",
            profile_id, profile.name, profile.provider_kind, profile.model, actor,
        )
        return profile_id

    async def update(
        self, profile_id: str, *, actor: str, **fields: Any,
    ) -> bool:
        """部分更新。fields 支持 name / api_key / base_url / model / max_tokens /
        reasoning_effort / extra_body / notes / provider_kind。不含 is_default
        （改默认走 set_default）。api_key 传 "***" 表示保留原值不动。"""
        if not fields:
            return False

        allowed = {
            "name", "provider_kind", "api_key", "base_url", "model",
            "max_tokens", "reasoning_effort", "notes",
        }
        sets: list[str] = []
        params: list[Any] = []
        for key, val in fields.items():
            if key == "extra_body":
                sets.append("extra_body_json = ?")
                params.append(json.dumps(val or {}, ensure_ascii=False))
            elif key == "api_key":
                # 掩码占位：跳过不更新（前端没改 key 时传 "***" 回来）
                if val == _MASKED:
                    continue
                sets.append("api_key = ?")
                params.append(val)
            elif key in allowed:
                sets.append(f"{key} = ?")
                params.append(val)

        if not sets:
            return False

        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(profile_id)

        async with self._db.execute(
            f"UPDATE llm_profiles SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        ) as cur:
            ok = cur.rowcount > 0
        await self._db.commit()
        if ok:
            logger.info(
                "[世界树·LLM Profile] 更新 {} fields={} actor={}",
                profile_id, list(fields.keys()), actor,
            )
        return ok

    async def delete(self, profile_id: str, *, actor: str) -> bool:
        """删除 profile；若是当前默认则拒绝（先改默认再删）。"""
        async with self._db.execute(
            "SELECT is_default FROM llm_profiles WHERE id = ?", (profile_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return False
        if row[0]:
            raise ValueError("默认 profile 不能删除，请先设置其他 profile 为默认")

        await self._db.execute(
            "DELETE FROM llm_profiles WHERE id = ?", (profile_id,),
        )
        await self._db.commit()
        logger.info("[世界树·LLM Profile] 删除 {} actor={}", profile_id, actor)
        return True

    async def set_default(self, profile_id: str, *, actor: str) -> bool:
        """设为全局默认；原默认自动清零（事务内保证唯一）。"""
        async with self._db.execute(
            "SELECT id FROM llm_profiles WHERE id = ?", (profile_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return False
        await self._db.execute("UPDATE llm_profiles SET is_default = 0 WHERE is_default = 1")
        await self._db.execute(
            "UPDATE llm_profiles SET is_default = 1, updated_at = ? WHERE id = ?",
            (time.time(), profile_id),
        )
        await self._db.commit()
        logger.info("[世界树·LLM Profile] 设默认 {} actor={}", profile_id, actor)
        return True

    async def set_default_by_name(self, name: str, *, actor: str) -> bool:
        async with self._db.execute(
            "SELECT id FROM llm_profiles WHERE name = ?", (name,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return False
        return await self.set_default(row[0], actor=actor)

    # ---------- 查询 ----------

    async def get(self, profile_id: str, *, include_key: bool = True) -> LLMProfile | None:
        async with self._db.execute(
            "SELECT id, name, provider_kind, api_key, base_url, model, "
            "max_tokens, reasoning_effort, extra_body_json, is_default, notes, "
            "created_at, updated_at FROM llm_profiles WHERE id = ?",
            (profile_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_record(row, include_key=include_key) if row else None

    async def list(self, *, include_keys: bool = False) -> list[LLMProfile]:
        async with self._db.execute(
            "SELECT id, name, provider_kind, api_key, base_url, model, "
            "max_tokens, reasoning_effort, extra_body_json, is_default, notes, "
            "created_at, updated_at FROM llm_profiles "
            "ORDER BY is_default DESC, name ASC",
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_record(r, include_key=include_keys) for r in rows]

    async def get_default(self) -> LLMProfile | None:
        async with self._db.execute(
            "SELECT id, name, provider_kind, api_key, base_url, model, "
            "max_tokens, reasoning_effort, extra_body_json, is_default, notes, "
            "created_at, updated_at FROM llm_profiles "
            "WHERE is_default = 1 LIMIT 1",
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_record(row, include_key=True) if row else None

    # ---------- 内部 ----------

    @staticmethod
    def _row_to_record(row, *, include_key: bool) -> LLMProfile:
        try:
            extra = json.loads(row[8] or "{}")
            if not isinstance(extra, dict):
                extra = {}
        except (json.JSONDecodeError, TypeError):
            extra = {}
        api_key = row[3] or ""
        return LLMProfile(
            id=row[0],
            name=row[1],
            provider_kind=row[2],
            api_key=api_key if include_key else _mask_key(api_key),
            base_url=row[4] or "",
            model=row[5] or "",
            max_tokens=int(row[6]),
            reasoning_effort=row[7] or "",
            extra_body=extra,
            is_default=bool(row[9]),
            notes=row[10] or "",
            created_at=float(row[11]),
            updated_at=float(row[12]),
        )
