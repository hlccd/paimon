"""每日热点 collector 通用 schema。"""
from __future__ import annotations

from dataclasses import dataclass, field


# 各源人类可读名（写进 sources_ok / sources_fail / LLM prompt 给 LLM 上下文用）
SOURCE_LABELS: dict[str, str] = {
    "bili": "B 站",
    "zhihu": "知乎",
    "weibo": "微博",
    "hn": "HackerNews",
    "xhs": "小红书",
    "tieba": "百度热搜",
}


@dataclass
class HotItem:
    """归一化的热榜条目（跨源统一 schema）。"""
    source: str          # "bili" / "zhihu" / "weibo" / "hn"
    rank: int            # 源内排名（1=最热）
    title: str           # 原标题
    url: str             # 主链接
    hot_value: int = 0   # 热度数字（播放量/票数/讨论数；跨源不可比）
    extra: dict = field(default_factory=dict)  # 源特有字段（debug 用）

    def for_prompt(self) -> dict:
        """喂 LLM 时的精简形式（去掉 extra 节省 token）。"""
        return {
            "source": self.source,
            "rank": self.rank,
            "title": self.title,
            "url": self.url,
            "hot_value": self.hot_value,
        }


@dataclass
class CollectResult:
    """单源 collect 结果（包含错误信息让 service 层汇总到 sources_fail）。"""
    source: str
    items: list[HotItem]
    error: str = ""        # 空 = 成功；非空 = 失败原因（写进 sources_fail）

    @property
    def ok(self) -> bool:
        return not self.error and len(self.items) > 0
