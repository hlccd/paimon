# 风神·巴巴托斯

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神

- **主题**：自由·歌咏
- **核心职能**：
  - **时事新闻采集**：按关键词/领域抓取新闻源，整理摘要
  - **新闻推送整理**：定时或事件触发，整理好内容交给三月响铃
  - **舆情分析与追踪**（✅ L1 已实装）：
    - 对指定话题/品牌/关键词进行持续舆情监控
    - 情感分析：正面/中性/负面倾向判定
    - 趋势追踪：话题热度变化、关键事件时间线
    - 异常预警：舆情突变时通过三月事件响铃推送
  - **数据收集者角色**：向三月请求响铃或被三月按定时器唤起
- **Web 面板**：✅ 信息流面板（`/feed` 条目级）+ ✅ 舆情看板（`/sentiment` 事件级聚合）

## ⚠️ 当前状态（2026-05 解耦后）

`execute()` 内部业务已移除（asmoday 不再调本节点），**非四影功能完整保留**：

### 保留（非四影功能）

- `feed_collect` cron（订阅采集 + LLM digest）
- `/feed` 面板 + `/sentiment` 舆情看板
- LLM digest（订阅型 + 事件型）
- 事件聚类（`venti_event/` 子包）
- `_LoginMixin`（站点扫码 cookies 登录管理）
- `is_running()` 状态查询（前端"采集中"角标 + 防并发重入）
- 4 个 mixin：`_CollectMixin` / `_DigestMixin` / `_AlertMixin` / `_LoginMixin`

### 移除

- `service.py:execute()` 内部"通用采集 tool-loop"（asmoday 不再调本节点 execute）

---

## L1 事件级舆情监测

> 实装日期：2026-04-25

### 数据流（在原订阅链路里插入步骤 4.5）

```
三月 cron / 手动 run → collect_subscription
  Step 1-4  原有：搜索 → 去重 → feed_items 落库（含 records 含 db id）
  Step 4.5  EventClusterer.process(sub, records)
     ├ 聚类 LLM（浅池 mimo-v2-omni） → 决策 new / merge
     ├ 事件分析 LLM（浅池） → 标题/摘要/实体/timeline/severity/情感
     ├ feed_event_create 或 feed_event_update（item_count_inc + sources merge）
     └ feed_items_attach_event 反向挂回 event_id + sentiment 冗余字段
  Step 5    p0 紧急推（含 p1/p2/p3 升级到 p0）
     ├ 升级冷却：30 min 内同事件不重推（config.sentiment_p0_cooldown_minutes）
     └ ring_event(source="风神·舆情预警")
  Step 5.5  事件型 LLM 日报（C 阶段）
     ├ processed_events 非空走 _compose_event_digest
     └ 否则降级旧 _compose_digest
  Step 6    日报推送 ring_event(source="风神")
```

### 数据模型

- 世界树域 11.5 [feed_events 表](../../paimon/foundation/irminsul/_db/)：事件主体；FK→subscriptions(id)，删订阅时级联清
- feed_items 加列：event_id / sentiment_score / sentiment_label

### 浅池 LLM 调用 3 处

| purpose 名 | 触发 | 输出 |
|---|---|---|
| `事件聚类` | force_new=False 且有近 7 天候选事件时 | JSON `{decisions: [{item_idx, decision, event_id}]}` |
| `事件分析` | 每个事件分组 | JSON `{title, summary, entities, timeline, severity, sentiment_*}` |
| `事件日报` | 阶段 C 综合日报合成 | markdown（重要区/常规区/整体情感） |

`config.sentiment_llm_calls_per_run_max` 限制单批最多 LLM 调用次数；超过的事件走 `_fallback_analysis` 模板。

### 严重度推送策略（plan §6 / docs/foundation/march.md）

- **p0** 立即推 `ring_event(source="风神·舆情预警")`，30 min 冷却
- **p1** 升级到 p1 在 digest 顶部高亮（C 阶段实装）；4 h 冷却
- **p2/p3** 仅进 digest 常规位

### 舆情看板（D 阶段）

WebUI `/sentiment` —— 4 张统计卡 + 事件时间线（左主列） + 情感折线（Chart.js）+ 严重度矩阵 + 信源 Top + 事件详情 Modal。

依赖 6 个 API（[paimon/channels/webui/channel.py](../../paimon/channels/webui/channel.py)）：
```
GET  /api/sentiment/overview            概览（events_7d / p0_p1_count / avg_sentiment / sub_count）
GET  /api/sentiment/events?days=&severity=&sub_id=  事件列表（按 last_seen_at 倒序）
GET  /api/sentiment/events/{event_id}   事件详情 + 关联 feed_items
GET  /api/sentiment/timeline?days=&sub_id=   按天聚合（events / avg_sentiment / p0-p3）
GET  /api/sentiment/sources?days=       信源 Top
GET  /sentiment                         面板 HTML
```

### 关键文件

- [paimon/archons/venti_event/](../../paimon/archons/venti_event/) `EventClusterer`
- [paimon/archons/venti/](../../paimon/archons/venti/) `_dispatch_p0_alerts` / `_compose_event_digest`
- [paimon/foundation/irminsul/feed_event.py](../../paimon/foundation/irminsul/feed_event.py) `FeedEventRepo`
- [paimon/channels/webui/sentiment_html/](../../paimon/channels/webui/sentiment_html/) 看板

### 关键 config

`config.sentiment_*`（共 9 项）：enabled / event_lookback_days / cluster_max_candidates / max_items_per_event / p0_cooldown_minutes / p1_cooldown_hours / event_retention_days / llm_calls_per_run_max / fallback_on_llm_fail。

`sentiment_enabled=False` 完全退化到 L0（不写 feed_events，仍走旧 _DIGEST_PROMPT），用于故障排查。
