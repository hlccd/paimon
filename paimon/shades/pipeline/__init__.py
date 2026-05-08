"""四影管线 — 闭环结构子包

```
[环1·入口审] 死执·review → 拒绝即归档
     ↓
[环2·主循环 N 轮]
   生执·plan → 死执·scan_plan → 派蒙·batch_ask（批量敏感授权）
     → 空执·dispatch(拓扑并发 + 失败重试) → 解析评审 verdict
     pass → 跳出
     revise/redo → 回生执下一轮（失败节点触发改派）
     round≥cap → 尽力而为返回最后一轮产物
     ↓
[环3·归档] 时执·archive（成功/失败都进；失败先跑 saga 补偿）
```

环 2 的核心是"spec/design/code + review_* 多轮循环"（v7：四影各 stage 派发）。

子模块（mixin 模式）：
- _execute.py    —— execute 主循环（_ExecuteMixin）
- _authorize.py  —— 批量授权 + 阻塞节点 drop / saga 补偿（_AuthorizeMixin）
- _verdict.py    —— 评审 verdict 解析 + 阶段渲染（_VerdictMixin）
- _final.py      —— 最终产物组装 + 任务实体创建（_FinalMixin）
- service.py     —— ShadesPipeline 主类 + PrepareResult + prepare/run/通知 helpers
"""
from __future__ import annotations

from .service import PrepareResult, ShadesPipeline

__all__ = ["PrepareResult", "ShadesPipeline"]
