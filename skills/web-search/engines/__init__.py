"""搜索引擎适配器。每个模块暴露 async def search(query: str, limit: int) -> list[dict]。

结果字段：
  title: 标题
  url: 点开就能访问的真实 URL
  description: 摘要片段（可能为空字符串）
  engine: 引擎名（'bing' / 'baidu'）

失败策略：单引擎抛异常，由调用方 search.py 兜底；引擎内部只做一次 GET 不自己重试。
"""
from . import baidu, bing

ENGINES = {
    "bing": bing,
    "baidu": baidu,
}

__all__ = ["ENGINES", "bing", "baidu"]
