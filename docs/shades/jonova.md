# 死执·若纳瓦

> 隶属：[神圣规划](../aimon.md) / 四影 — **审**（评审 + 自检）
> 调用关系：生执出产物 → 死执审 verdict → 不通过 → 生执 revise

**定位**：v7 起转岗为"质量审" — 给生执的产物（spec / design / code）打 verdict。
原"安全审"职能（task review / scan plan / skill review）已上提派蒙 [`paimon/core/safety/`](../../paimon/core/safety/)。

## 核心能力

### 1. 评审循环（review_spec / review_design / review_code）

为生执的产物打 verdict（pass / revise / redo），驱动多轮迭代。

- **轻量路径**：产物小（spec/design < 2000 字，code < 200 行）→ 一次 LLM JSON 调用，按 P0/P1/P2/P3 分级
- **重型路径**：产物大 → 调 [`check`](../../skills/check/) skill，解析 `.check/candidates.jsonl` → ReviewVerdict

输出 schema：`{level: pass|revise|redo, summary: str, issues: list[{subtask_id, reason, suggestion}]}`

实现：[`paimon/shades/jonova/review.py`](../../paimon/shades/jonova/review.py)

### 2. 静态自检（self_check）

py_compile + ruff + pytest 三件套，写 `self-check.log`。

调用方：
- 生执 produce_code 跑完 skill 后**即时调一次**（自调，给 LLM 反馈让它继续修）
- 死执 review_code 重型路径里也间接通过 check skill 调

实现：[`paimon/shades/jonova/self_check.py`](../../paimon/shades/jonova/self_check.py)

## v7 转岗变化

**移除**（→ 派蒙 [`paimon/core/safety/`](../../paimon/core/safety/)）：
- `task_review`：入口任务级安全审
- `scan_plan`：DAG 敏感操作扫描 + 批量授权
- `review_skill_declaration`：skill 热加载审

**保留 + 新增**：
- `review`（统一入口，按 stage 路由到 review_spec/design/code）
- `run_self_check`（静态质量门）

## 与派蒙的边界

- **派蒙**（[paimon/core/safety/](../../paimon/core/safety/)）：所有"安全审" — task / DAG / skill 三个时点
- **死执**（本节点）：所有"质量审" — 评审产物 + 静态自检
