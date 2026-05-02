"""Quick 自检快照 dataclass：单组件探针结果 + 整体 snapshot 包装。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComponentProbe:
    """Quick 探针的单组件结果。"""
    name: str
    status: str = "ok"             # 'ok' | 'degraded' | 'critical'
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class QuickSnapshot:
    """单次 Quick 自检整体快照；overall 由 components 派生（critical>degraded>ok）。"""
    ts: float = 0.0
    overall: str = "ok"            # 派生：任一 critical → critical；任一 degraded → degraded；否则 ok
    duration_seconds: float = 0.0
    components: list[ComponentProbe] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON 序列化用：dataclass → 嵌套 dict（blob 写盘 / API 返回都用）。"""
        return {
            "ts": self.ts,
            "overall": self.overall,
            "duration_seconds": self.duration_seconds,
            "components": [
                {
                    "name": c.name, "status": c.status,
                    "latency_ms": c.latency_ms,
                    "details": c.details, "error": c.error,
                }
                for c in self.components
            ],
            "warnings": self.warnings,
        }
