# 水神·芙宁娜

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神

- **主题**：戏剧·评审 + 游戏
- **核心职能**：
  - **游戏（保留）**：信息 / 配队 / 账号 / 日常（FurinaGameService）
  - **成品评审（已移交工人）**：方案 / 文档 / 代码 / 架构挑刺
- **Web 面板**：✅ `/game` 游戏面板

## ⚠️ 当前状态（2026-05 解耦后）

水神跟四影解耦后**整体保留游戏功能**：

### 保留：水神·游戏（`FurinaGameService`）

- `/game` 面板（账号 / 抽卡 / 便笺 / 深渊 / 角色 / 概览，6 mixin 完整保留）
- cron：`mihoyo_collect`（每日 8:05 签到 + 便笺 + 深渊）/ `mihoyo_game_collect`（早 7 点资讯）
- subscription type：`mihoyo_game`
- 代码位置：`paimon/archons/furina_game/` 子包**完全不动**

### 移除：水神·评审（archon 本体 review 段）

- `paimon/archons/furina/_review.py`：**删除整个文件**（420 行）
- `paimon/archons/furina/service.py`：删 `execute()` 内部 `[STAGE:review_*]` 路由 + ReviewMixin，瘦身到 namespace 壳（~30 行）
- 已搬到：`paimon/shades/jonova/review.py`（stage = `review_spec` / `review_design` / `review_code`）

水神整体仍是 paimon 的"游戏 / 评审"业务模块；评审段已移交工人，游戏段完全保留。

## 与时执的分工

同样是"审视"，但维度不同：

- **评审工人（review_*）= 内容维度**：方案 / 代码 / 架构本身好不好
- **时执 = 流程维度**：执行链路哪一步出问题、为什么失败
