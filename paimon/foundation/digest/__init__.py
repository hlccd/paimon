"""通用日报合成基础设施（第一步：仅 prompt 层抽象）

为各神（风神舆情、岩神理财、未来水神娱乐 / 草神科技）提供「事件聚类 → 结构化分析 → 日报合成」
三步 LLM 流水线的**通用 prompt 模板**，按 `DigestSpec` 注入领域文本生成各神专属 prompt。

不抽数据层：聚类候选池 / 事件 upsert / 条目挂事件 仍由各神独立持有 repo（feed_events /
dividend_changes / ...）。等 ≥2 个真实接入再考虑抽 `DigestPipeline + DomainAdapter`
协议（见 docs/todo.md §通用日报合成器·下一步）。

docs/archons/venti.md §L1 当前调用方：风神（venti_event.py + venti.py）
"""
from .composer import DigestSpec, render_analyze_prompt, render_cluster_prompt, render_digest_prompt

__all__ = [
    "DigestSpec",
    "render_cluster_prompt",
    "render_analyze_prompt",
    "render_digest_prompt",
]
