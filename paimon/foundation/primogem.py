"""原石 · Primogem —— Token 用量业务服务层

架构定位：服务层模块。业务逻辑留原石（费率查表 + 缓存折扣 + 多维聚合 + dashboard），
**数据落盘统一调世界树 `token_*` API**。不自建 SQLite 或独立文件库。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul


@dataclass
class ModelRate:
    input: float
    output: float
    cache_write: float
    cache_read: float


# 费率表（USD per token）
# DeepSeek 官网单价是 CNY/M tokens，按汇率 7.2 折算；cache_write 设 0 —— DeepSeek
# 无"缓存创建"计费概念（openai.py 也固定 cache_creation_tokens=0）。
# v4-pro 限时 2.5 折至 2026-05-05 23:59，到期后改回原价：
#   原价 CNY/M：miss 12 / hit 0.1 / output 24
#   折算 USD/token：0.417e-6 hit 1.67e-6 output 3.33e-6
_RATES: dict[str, ModelRate] = {
    "claude-opus-4":   ModelRate(15e-6,  75e-6,  18.75e-6, 1.5e-6),
    "claude-sonnet-4": ModelRate(3e-6,   15e-6,  3.75e-6,  0.3e-6),
    "claude-haiku":    ModelRate(0.8e-6, 4e-6,   1e-6,     0.08e-6),
    "gpt-4o":          ModelRate(2.5e-6, 10e-6,  2.5e-6,   1.25e-6),
    "gpt-4o-mini":     ModelRate(0.15e-6, 0.6e-6, 0.15e-6, 0.075e-6),
    "gpt-4":           ModelRate(30e-6,  60e-6,   30e-6,   15e-6),
    # DeepSeek v4-pro（折扣价，CNY 3/6/hit 0.025 折算）
    "deepseek-v4-pro":   ModelRate(0.417e-6,  0.833e-6,  0.0,  0.0035e-6),
    # DeepSeek v4-flash（稳定价，CNY 1/2/hit 0.02 折算）
    "deepseek-v4-flash": ModelRate(0.139e-6,  0.278e-6,  0.0,  0.00278e-6),
    # 即将弃用（2026-07-24）；对应 v4-flash 非思考 / 思考模式同价
    "deepseek-chat":     ModelRate(0.139e-6,  0.278e-6,  0.0,  0.00278e-6),
    "deepseek-reasoner": ModelRate(0.139e-6,  0.278e-6,  0.0,  0.00278e-6),
    "mimo":            ModelRate(1e-6,   1e-6,    1e-6,    0.5e-6),
}
_DEFAULT_RATE = ModelRate(3e-6, 15e-6, 3.75e-6, 0.3e-6)


class Primogem:
    """Token 业务服务方；数据落盘走世界树 `token_*`。"""

    def __init__(self, irminsul: Irminsul):
        self._irminsul = irminsul

    @staticmethod
    def _match_rate(model_name: str) -> ModelRate:
        name = (model_name or "").lower()
        for prefix, rate in _RATES.items():
            if prefix in name:
                return rate
        return _DEFAULT_RATE

    @staticmethod
    def compute_cost(
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        rate = Primogem._match_rate(model_name)
        base_input = input_tokens - cache_creation_tokens - cache_read_tokens
        if base_input < 0:
            base_input = 0
        return (
            base_input * rate.input
            + cache_creation_tokens * rate.cache_write
            + cache_read_tokens * rate.cache_read
            + output_tokens * rate.output
        )

    async def record(
        self,
        session_id: str,
        component: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        purpose: str = "",
    ) -> None:
        await self._irminsul.token_write(
            session_id=session_id,
            component=component,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            purpose=purpose,
            actor="原石",
        )

    # ---------- 聚合查询 ----------
    async def get_session_stats(self, session_id: str) -> dict[str, Any]:
        rows = await self._irminsul.token_aggregate(
            group_by=["component"], session_id=session_id,
        )
        return self._assemble_stats(rows, key="component")

    async def get_global_stats(self) -> dict[str, Any]:
        rows = await self._irminsul.token_aggregate(group_by=["component"])
        return self._assemble_stats(rows, key="component")

    async def get_purpose_stats(self) -> dict[str, dict[str, Any]]:
        rows = await self._irminsul.token_aggregate(group_by=["purpose"])
        result: dict[str, dict[str, Any]] = {}
        for r in rows:
            k = r.get("purpose") or "(未标记)"
            result[k] = self._row_to_entry(r)
        return result

    async def get_detail_stats(self) -> list[dict[str, Any]]:
        rows = await self._irminsul.token_aggregate(group_by=["component", "purpose"])
        return [
            {
                "component": r.get("component"),
                "purpose": r.get("purpose") or "",
                **self._row_to_entry(r),
            }
            for r in rows
        ]

    async def get_distribution_stats(self, by: str = "hour") -> list[dict[str, Any]]:
        key = "weekday" if by == "weekday" else "hour"
        rows = await self._irminsul.token_aggregate(group_by=[key])
        rows.sort(key=lambda r: r.get(key) or 0)
        return [{"period": r.get(key), **self._row_to_entry(r)} for r in rows]

    async def get_timeline_stats(
        self, period: str = "day", count: int = 7,
    ) -> list[dict[str, Any]]:
        if period == "week":
            seconds = count * 7 * 86400
            key = "week"
        elif period == "month":
            seconds = count * 30 * 86400
            key = "month"
        else:
            seconds = count * 86400
            key = "day"
        cutoff = time.time() - seconds
        rows = await self._irminsul.token_aggregate(group_by=[key], since=cutoff)
        rows.sort(key=lambda r: r.get(key) or "")
        return [{"period": r.get(key), **self._row_to_entry(r)} for r in rows]

    # ---------- helpers ----------
    @staticmethod
    def _row_to_entry(r: dict) -> dict[str, Any]:
        return {
            "input_tokens": r.get("sum_input_tokens") or 0,
            "output_tokens": r.get("sum_output_tokens") or 0,
            "cache_creation_tokens": r.get("sum_cache_creation_tokens") or 0,
            "cache_read_tokens": r.get("sum_cache_read_tokens") or 0,
            "cost_usd": r.get("sum_cost_usd") or 0.0,
            "count": r.get("count") or 0,
        }

    @staticmethod
    def _assemble_stats(rows: list[dict], *, key: str) -> dict[str, Any]:
        """兼容旧 get_global_stats / get_session_stats 返回结构：
        {
            total_input_tokens, total_output_tokens, total_cache_creation_tokens,
            total_cache_read_tokens, total_cost_usd, count, by_component: {...}
        }
        """
        total_in = total_out = total_cw = total_cr = 0
        total_cost = 0.0
        total_count = 0
        by_group: dict[str, dict] = {}
        for r in rows:
            entry = Primogem._row_to_entry(r)
            total_in += entry["input_tokens"]
            total_out += entry["output_tokens"]
            total_cw += entry["cache_creation_tokens"]
            total_cr += entry["cache_read_tokens"]
            total_cost += entry["cost_usd"]
            total_count += entry["count"]
            by_group[r.get(key) or "(unknown)"] = entry
        return {
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_cache_creation_tokens": total_cw,
            "total_cache_read_tokens": total_cr,
            "total_cost_usd": total_cost,
            "count": total_count,
            "by_component": by_group,  # 保留旧键名，即使 key 是 purpose 也叫 by_component
        }
