"""小红书 collector：MVP 阶段 stub。

调研发现：
- 小红书反爬非常严，Bing / 百度对 `site:xiaohongshu.com` 限定几乎 0 命中
  （搜索引擎无法索引 xhs 内容）
- 用关键词 + "小红书" 搜出来的全是知乎 / smzdm / 媒体二次报道，不是 xhs 笔记本身
- 唯一可行路径：cookies + 直连 xhs 笔记搜索 API（参考 paimon/skills/xhs 的解析逻辑）

P2 阶段方案：
1. 复用 paimon/skills/xhs 的 cookie 配置
2. 调 xhs `/api/sns/web/v1/search/notes` 笔记搜索接口
3. 拿真实 engagement（点赞 / 收藏 / 评论 / 分享）
4. 解析 published_at（需要从笔记详情拉）

现阶段返回空列表 + 明确 error，让用户知道现状。
"""
from __future__ import annotations

from . import log
from .schema import Item


def collect(
    topic: str,
    range_from: str,
    range_to: str,
    *,
    limit: int = 20,
) -> list[Item]:
    """xhs collector stub（P2 阶段实装）。"""
    log.source_log("xhs", "MVP 阶段未实装；需 cookies + xhs 笔记 API（详见 SKILL.md P2 计划）")
    return []
