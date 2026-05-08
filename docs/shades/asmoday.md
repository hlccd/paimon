# 空执·阿斯莫代

> 隶属：[神圣规划](../aimon.md) / 四影 — **派**（调度 + 路由）
> 调用关系：生执出 DAG → 派蒙审 → 空执派 → 生执/死执 干活

**定位**：v7 起承担"派" — 拓扑分层 + 按 stage 路由表派给对应影。空执自己**不干活**，只管流转。

## 核心能力

### 1. 拓扑分层 dispatch

按 `subtask.deps` 拓扑排序，分层并发。

```
layer 1: 入度 0 的节点（asyncio.gather）
layer 2: 上层完成后入度 0 的（asyncio.gather）
...
```

### 2. Stage 路由表

`_STAGE_ROUTER`：assignee（stage 名）→ 对应影函数：

```
spec / design / code               → naberius.produce_*
simple_code / exec / chat          → naberius.simple_run
review_spec / review_design / review_code → jonova.review
```

未知 stage → fallback 到 `chat`。

### 3. 失败处理

- 单节点 exception → 重试 1 次（指数 backoff 2s/4s/8s 上限 30s）
- 仍失败 → 标 failed + 传递性下游 skipped + 写审计
- 整个 round 完成后由 pipeline 决定是否触发 saga（`istaroth.run_compensations`）

## 实现

- [`paimon/shades/asmoday.py`](../../paimon/shades/asmoday.py)：约 200 行单文件

## 与其他影的边界

- **生执**：出 DAG / 干"生"的活；空执只读 DAG，不改
- **死执**：干"审"的活；空执只把 review_* 节点派给死执，不解析 verdict（解析在 pipeline._resolve_verdict）
- **时执**：管"收"；空执只在 pipeline 触发 saga 时调时执 run_compensations，不亲自补偿
- **神之心**：LLM 底层实例故障由神之心自处；空执不管 LLM 层
