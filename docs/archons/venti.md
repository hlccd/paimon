# 风神·巴巴托斯

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神

- **主题**：自由·歌咏
- **核心职能**：
  - **topic 调研订阅**：用户在 `/feed` 面板手填关键词，每天 cron 跑 `topic.research.py` 拉 5 源 UGC（B 站 / 小红书 / 知乎 / 贴吧 / 微博）30 天调研，覆盖式落 `feed_topic_research` 表
  - **站点登录代理**：webui `/feed` 站点登录 tab，扫码取 cookies 给 topic / 其他登录态 collector 用
- **Web 面板**：`/feed`（订阅管理 + 站点登录两个 tab）

## 当前实装清单

- `feed_collect` cron（订阅采集）
- `/feed` 面板（订阅管理 + 站点登录）
- 3 个 mixin：`_CollectMixin` / `_DigestMixin` / `_LoginMixin`
- 订阅类型 `topic_research`（默认）；岩神 stock_watch 走自己的 `run_stock_topic_collect`

archon 本体 `execute()` 不参与执行，业务接口完全通过 mixin + cron + webui 面板体现。

## 数据流（topic_research 订阅）

```
三月 cron / 手动 run → collect_subscription(sub_id)
  └ dispatcher 按 sub.binding_kind 路由 → run_topic_research_collect(sub, state)
     ├ invoke_skill_workflow(skill_name="topic", component="topic", purpose="topic")
     │    ├ topic skill 跑 exec → research.py 拉 5 源 UGC 30 天
     │    └ LLM 综合 brief stdout → 输出三段 markdown
     │       (情绪分析 → 各源讨论重点 → 综合 Top {N})
     └ feed_topic_research_upsert（每订阅一条最新；不累加，不推送）
  前端 /feed 进面板时拉 GET /api/feed/topic_research/{sub_id} 渲染 markdown
```

每次跑约 1-2 分钟（topic 子进程 30-60s + LLM 综合 20-40s）；不走 `push_archive`（覆盖式落 feed_topic_research 表）。

## 数据模型

- 世界树域 11：subscriptions 表（共用，binding_kind='topic_research' 标识）
- 世界树域 11.6：[feed_topic_research 表](../../paimon/foundation/irminsul/_db/_schema.sql)（PK=subscription_id，覆盖式存最新一份；FK→subscriptions(id)，由 SubscriptionRepo.delete 级联清）

## 关键文件

- [paimon/archons/venti/topic_collect.py](../../paimon/archons/venti/topic_collect.py) `run_topic_research_collect`
- [paimon/archons/venti/_register.py](../../paimon/archons/venti/_register.py) 注册 binding_kind=topic_research
- [paimon/archons/venti/_collect.py](../../paimon/archons/venti/_collect.py) `collect_subscription` dispatcher
- [paimon/channels/webui/api/feed.py](../../paimon/channels/webui/api/feed.py) WebUI 接口
- [paimon/channels/webui/feed_html.py](../../paimon/channels/webui/feed_html.py) 面板
