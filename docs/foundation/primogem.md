# 原石

> 隶属：[神圣规划](../aimon.md) / 基础层 · **服务层**
> 存储层归属：[世界树 · token 域](irminsul.md)

**定位**：旅行者的行动消耗计量器，**token 消耗 + 花费统计的业务服务方**。

## 分层位置

原石是**服务层模块**，持有 token 业务的全部逻辑（费率查表、缓存折扣计算、多维聚合、dashboard 组装），**数据落盘统一调世界树 `token_*` API**，不自建 SQLite 或独立文件库。

| 留在原石的 | 交给世界树的 |
|---|---|
| 费率表（`_RATES`，按模型名匹配） | token_usage 表的建表 / schema 迁移 |
| `compute_cost()`（缓存折扣计算） | 单条写入 / 批量查询的 SQL |
| `get_session_stats` / `get_timeline_stats` 等聚合逻辑 | 查询原始行 |
| dashboard HTML 组装 | — |
| 订阅地脉 `vision.chat_complete` 事件 | — |

调用世界树时传 `actor="原石"`，世界树写日志形如：`[世界树] 原石·写入 Token 记录  session=abc123, 消耗=$0.0123`。

## 核心能力

- **调用记录**：每次 LLM 调用的 token 用量 + 金额换算 + 双维度标签（`module` + `purpose`）
- **多维度聚合**：
  - 按**模块**：派蒙 / 生执 / 草神 / 天使·bili ...
  - 按**用途**：闲聊 / 意图分类 / DAG 编排 / 推理挑刺 / 视频总结 ...
  - 按**会话**：单次对话总花费
  - 按**时间**：日 / 周 / 月 聚合
- **样例记录**：
  ```
  { module: "派蒙",      purpose: "闲聊",       tokens: 150,  cost: 0.003 }
  { module: "派蒙",      purpose: "意图分类",    tokens: 80,   cost: 0.001 }
  { module: "生执",      purpose: "DAG 编排",    tokens: 900,  cost: 0.018 }
  { module: "草神",      purpose: "推理挑刺",    tokens: 2400, cost: 0.048 }
  { module: "天使·bili", purpose: "视频总结",    tokens: 1200, cost: 0.024 }
  ```
- **Web 展示**：接入三月的观测面板

## 与岩神的边界

- 原石 = **系统资源消耗**（token / 花费）
- 岩神 = **用户个人财富**（股票 / 资产 / 退休），和 LLM 消耗无关
