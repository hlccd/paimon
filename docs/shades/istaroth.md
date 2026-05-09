# 时执·伊斯塔露

> 隶属：[神圣规划](../aimon.md) / 四影

**定位**：任何任务尾声的事都归它。

## 核心能力

| 阶段 | 职能 | 实装 |
|---|---|---|
| 结束后 · 自进化触发 | 任务归档 + 对话每 5 条消息双路触发生执 / 死执链 | [`_propose_trigger.py`](../../paimon/shades/istaroth/_propose_trigger.py) |
| 持续 · skill 热重载 | 监听 skills/ 文件变化触发 reload（不阻塞主流程） | [`skill_watcher.py`](../../paimon/shades/istaroth/skill_watcher.py) |
| 周度 / 月度 · 自进化 cron | 周一清 30 天前 rejected 提案 + 每月 1 日 04:00 扫近 30 天任务凝练新草案 | [`proposal_cron.py`](../../paimon/shades/istaroth/proposal_cron.py) |
| 到期 | 会话/任务生命周期清扫 | [`_lifecycle.py`](../../paimon/shades/_lifecycle.py)（三月 cron 触发） |

## 自进化触发

两个入口都由本模块负责：

- **任务归档**：任务跑完时浅判一次"是否值得沉淀"，命中就直调生执 + 死执函数链。带防自激发标记，避免触发器产生的 task 反复触发自己。
- **对话累积**：每 5 条用户消息后台浅判一次（看最近 30 条会话历史）。绝大多数情况返 false 短路；命中才进完整链路。

成本上限：单次触发最多 1 次浅判；命中后最多 1 次生执 + 5 次死执（生执单次最多产 5 条草案，死执循环每条审）。

> **会话生命周期清扫** 实际归派蒙（会话域唯一写入者）。代码 `paimon/shades/_lifecycle.py` 留在 shades 目录是历史位置，actor 已改"派蒙·会话清扫"。三月每 6h 触发，逻辑：

```
sweep_sessions
  ├── archive_if_idle   （updated_at 超 6h + channel_key='' + status<>'generating' → 标 archived_at）
  └── purge_expired     （archived 超 90d → 物理 DELETE）
```

**护栏**：
- `response_status='generating'` 会话绝不归档
- 有 `channel_key` 绑定的会话绝不归档

**配置**（`.env` 可覆盖）：

| 键 | 默认 | 含义 |
|---|---|---|
| `lifecycle_sweep_enabled` | true | 总开关 |
| `lifecycle_sweep_interval_hours` | 6 | 清扫频率（[1,168] clamp）|
| `session_inactive_hours` | 6 | 会话无更新→归档 |
| `session_archived_ttl_days` | 90 | archived 会话过期删除 |

## 跟死执的边界

- **死执** = 内容维度（评审 skill 提案质量）
- **时执** = 流程维度（archive 审计 + 触发自进化 hook + 生命周期清扫）
