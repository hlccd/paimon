# 时执·伊斯塔露

> 隶属：[神圣规划](../aimon.md) / 四影 — **收**（任务尾声善后 + 生命周期）

**定位**：v7 起承担"收" — 任何任务尾声的事都归它。

## 核心能力

| 阶段 | 职能 | 实装 |
|---|---|---|
| 运行中 | 活跃会话上下文压缩 | ✅ `paimon/shades/istaroth/_compress.py:compress`（4 项改进：阈值公式 / tool-pair 对齐 / Prompt 4 章节 / 3 次失败熔断） |
| 失败回滚 · saga | 反序对已 completed 节点跑补偿（调生执 exec 反向执行）| ✅ `paimon/shades/istaroth/saga.py:run_compensations`（v7：从 shades/_saga.py 移入） |
| 到期 | 会话生命周期超时管理；复杂任务运行超时 1 小时 | ✅ `sweep_sessions` 不活跃 6h+无 channel 绑定 → archived；`sweep_tasks` running>1h → failed+cold |
| 结束后 · 归档 | 热（<30d）→ 冷（30-90d）→ 过期自动删除 | ✅ `sweep_tasks` cold 30d→archived，archived 60d→物理删除（级联 subtasks/flow/progress） |
| 结束后 · 审计 | 流程复盘、异常归因、执行链路审视 | ✅ `archive(failure_reason, rounds)` + `task_stuck_timeout`/`lifecycle_sweep_report` 事件 |

## 生命周期闭环（2026-04-24）

新模块 [`paimon/shades/_lifecycle.py`](../../paimon/shades/_lifecycle.py)：

```
[三月 _poll 末尾 hook] 每 interval_hours（默认 6h）触发一次 run_lifecycle_sweep
     │
     ├── sweep_sessions
     │     ├── archive_if_idle   （updated_at 过期 + channel_key='' + status<>'generating' → 标 archived_at）
     │     └── purge_expired     （archived 超 90d → 物理 DELETE）
     │     └── SessionManager.invalidate_removed（归档/删除都同步内存）
     │
     └── sweep_tasks
           ├── stuck_running_timeout  （running + updated_at 超 1h → failed+cold+archived_at=now）
           ├── promote_lifecycle      （cold + archived_at 超 30d → archived）
           └── purge_expired          （archived + archived_at 超 60d → 级联 DELETE
                                      progress_log → flow_history → subtasks → edicts）
```

**护栏（SQL 层内置）**：
- `response_status='generating'` 会话绝不归档
- 有 `channel_key` 绑定的会话绝不归档（用户可能随时回来）
- `status in ('pending','running')` 任务的 lifecycle 绝不动

**落盘语义**：
- `archived_at` 代表"当前生命周期阶段的入库时间"
- `task_update_lifecycle(stage='cold')` 会设 archived_at=now（若原先 NULL）——这是 promote TTL 判定的起点
- `task_update_lifecycle(stage='archived')` 会把 archived_at 刷新为 now——这是 purge TTL 判定的起点

**配置**（全部 `.env` 可覆盖）：
| 键 | 默认 | 含义 |
|---|---|---|
| `lifecycle_sweep_enabled` | true | 总开关 |
| `lifecycle_sweep_interval_hours` | 6 | 清扫频率，clamp 到 [1, 168] |
| `session_inactive_hours` | 6 | 会话无更新→归档 |
| `session_archived_ttl_days` | 90 | archived 会话过期删除 |
| `task_running_timeout_hours` | 1 | 运行中任务卡死保护 |
| `task_cold_ttl_days` | 30 | cold → archived |
| `task_archived_ttl_days` | 60 | archived → 删除（30+60=90 对齐 docs） |

## 死执评审 vs 时执审计

同样是"审视"，但维度不同：

- **死执 = 内容维度**：方案 / 代码 / 架构本身好不好（评审循环 + 静态自检）
- **时执 = 流程维度**：执行链路哪一步出问题、为什么失败（archive 审计 + saga 回滚）
