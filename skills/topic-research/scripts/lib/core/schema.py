"""统一 schema：每个平台 collector 输出 Item，最终聚合成 Report。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Item:
    """单个内容项（B 站视频 / 小红书笔记 / 微博 / ...）"""
    source: str                        # 'bili' / 'xhs' / 'zhihu' / ...
    item_id: str                       # 平台原生 ID（BV 号 / 笔记 id / ...）
    title: str
    url: str = ""
    body: str = ""                     # 简介 / 正文摘要
    author: str = ""
    published_at: str = ""             # YYYY-MM-DD
    engagement: dict[str, int] = field(default_factory=dict)
    # engagement 字段约定（各平台尽量对齐）：
    #   view / like / comment / share / favorite / coin / danmaku
    relevance: float = 0.5             # 相关度提示（0-1，初步打分；rerank 会重写）
    score: float = 0.0                 # 综合得分（score.py 计算后填）
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Report:
    """整次调研的最终结果。"""
    topic: str
    range_from: str                    # YYYY-MM-DD
    range_to: str
    generated_at: str                  # ISO 8601
    items_by_source: dict[str, list[Item]] = field(default_factory=dict)
    ranked: list[Item] = field(default_factory=list)         # 跨源排序后的 top-N
    errors: dict[str, str] = field(default_factory=dict)     # source → error msg

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "range_from": self.range_from,
            "range_to": self.range_to,
            "generated_at": self.generated_at,
            "items_by_source": {
                src: [it.to_dict() for it in items]
                for src, items in self.items_by_source.items()
            },
            "ranked": [it.to_dict() for it in self.ranked],
            "errors": dict(self.errors),
        }
