# 时执·伊斯塔露

> 隶属：[神圣规划](../aimon.md) / 四影 — **收**

**定位**：承担"收" — 任何任务尾声的事都归它。

## 核心能力

| 阶段 | 职能 | 实装 |
|---|---|---|
| 运行中 | 活跃会话上下文压缩 | [`_compress.py`](../../paimon/shades/istaroth/_compress.py)（阈值公式 / tool-pair 对齐 / 4 段 prompt / 3 次失败熔断）|
| 结束后 · 归档 | 任务状态 final + 审计 + summary.md | [`_archive.py`](../../paimon/shades/istaroth/_archive.py) |
| 结束后 · 自进化触发 | archive 末尾浅池 LLM 判 should_propose，触发 propose+review 链 | [`_propose_trigger.py`](../../paimon/shades/istaroth/_propose_trigger.py) |
| 结束后 · 经验提取 | 跨会话 L1 记忆抽取入草神 memory 域 | [`_experience.py`](../../paimon/shades/istaroth/_experience.py) |
| 到期 | 会话/任务生命周期清扫 | [`_lifecycle.py`](../../paimon/shades/_lifecycle.py)（三月 cron 触发） |

## 自进化 archive hook

archive 收尾时调 `maybe_trigger_propose(task, subtasks, summary, irminsul)`：

1. **防递归**：task.description 含 `[propose-triggered]` marker → 跳过（避免自激发）
2. **失败 / 无产出 task** → 跳过
3. **浅池 LLM 1 call** 判 should_propose（严格门槛，绝大多数返 false 短路）
4. yes → 直接调 `propose_skill` + `review_proposal` 函数链落 skill_proposals 表（不走 plan 编排）

成本控制：每次 archive 最多 1 个浅池 call；命中后再 +2 个浅池 call（propose + review）。

## 生命周期闭环

`paimon/shades/_lifecycle.py` 提供 `run_lifecycle_sweep` 给三月每 6h 触发：

```
sweep_sessions
  ├── archive_if_idle   （updated_at 超 6h + channel_key='' + status<>'generating' → 标 archived_at）
  └── purge_expired     （archived 超 90d → 物理 DELETE）

sweep_tasks
  ├── stuck_running_timeout  （running + updated_at 超 1h → failed+cold）
  ├── promote_lifecycle      （cold + archived_at 超 30d → archived）
  └── purge_expired          （archived + archived_at 超 60d → 级联 DELETE）
```

**护栏**：
- `response_status='generating'` 会话绝不归档
- 有 `channel_key` 绑定的会话绝不归档
- `status in ('pending','running')` 任务的 lifecycle 绝不动

**配置**（`.env` 可覆盖）：

| 键 | 默认 | 含义 |
|---|---|---|
| `lifecycle_sweep_enabled` | true | 总开关 |
| `lifecycle_sweep_interval_hours` | 6 | 清扫频率（[1,168] clamp）|
| `session_inactive_hours` | 6 | 会话无更新→归档 |
| `session_archived_ttl_days` | 90 | archived 会话过期删除 |
| `task_running_timeout_hours` | 1 | 运行中任务卡死保护 |
| `task_cold_ttl_days` | 30 | cold → archived |
| `task_archived_ttl_days` | 60 | archived → 删除 |

## 跟死执的边界

- **死执** = 内容维度（评审 skill 提案质量）
- **时执** = 流程维度（archive 审计 + 触发自进化 hook + 生命周期清扫）
