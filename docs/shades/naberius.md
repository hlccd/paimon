# 生执·纳贝里士

> 隶属：[神圣规划](../aimon.md) / 四影 — **生**（编排 + 产出）
> 调用关系：生执出 DAG → 派蒙审 → 空执派 → 生执 produce / 死执 review → 时执收

**定位**：v7 起统一承担"生" — DAG 编排 + 产物生产，是四影体量最大的影。
是工人 9 stage 中 6 个产物 stage（spec / design / code / simple_code / exec / chat）的归属。

## 两段职能

### 1. 编排（plan）

LLM 把任务拆成 DAG。每个节点带 `assignee` 字段（即 stage 名）告诉空执派给谁。

- 写代码任务（trivial / simple / complex）走硬编码模板（不调 LLM 编排）
- 其他任务走 LLM 编排 → JSON 解析 → 容错三层兜底（tolerant_parse / 重试 / salvage）
- 多轮 revise（基于死执 verdict）：保留 pass 节点 + 重出 problem 节点

实现：[`paimon/shades/naberius/plan.py`](../../paimon/shades/naberius/plan.py) + [`code_pipeline.py`](../../paimon/shades/naberius/code_pipeline.py)

### 2. 产出（produce）

#### Skill 驱动 stage（调对应 skill workflow）

| stage | skill | 产物 |
|---|---|---|
| `spec` | requirement-spec | `workspace/spec.md` |
| `design` | architecture-design | `workspace/design.md` |
| `code` | code-implementation | `workspace/code/` + 自检日志 |

实现：[`paimon/shades/naberius/produce.py`](../../paimon/shades/naberius/produce.py)

#### 纯 LLM tool-loop stage

| stage | 用途 | tools |
|---|---|---|
| `simple_code` | trivial 任务直接 LLM 写代码 | file_ops, exec |
| `exec` | shell / 部署 / 重型工具（saga 补偿也用） | exec |
| `chat` | 通用 LLM 推理 / 兜底 | file_ops |

统一入口 `simple_run(stage, ...)`，实现：[`paimon/shades/naberius/_simple.py`](../../paimon/shades/naberius/_simple.py)

## 公开 API

```python
from paimon.shades.naberius import plan, produce_spec, produce_design, produce_code, simple_run
```

- `plan(task, model, irminsul, *, previous_plan, verdict, round)` — 编排
- `produce_spec / produce_design / produce_code(task, sub, model, irminsul, prior_results)` — 产物
- `simple_run(stage, task, sub, model, irminsul, prior_results)` — simple_code/exec/chat 共用

## 多轮迭代（轮次控制）

死执 review_* 节点产出 verdict 后回流到生执 plan：
- `pass` → 跳出循环
- `revise` → round+1，保留 completed 节点，重出 problem 节点
- `redo` → round+1，完全采用 LLM 新 plan
- `round_cap_hit` → 强制返回最后一轮产物

cap = 3（生执硬上限），超过即停止迭代。
