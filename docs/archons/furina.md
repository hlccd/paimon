# 水神·芙宁娜

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神

- **主题**：戏剧·游戏
- **核心职能**：游戏业务接口（信息 / 配队 / 账号 / 日常 — FurinaGameService）
- **Web 面板**：✅ `/game` 游戏面板

## 当前状态：archon 本体 namespace 壳 + 游戏服务子包

水神由两部分组成：

### archon 本体（namespace 壳）

`paimon/archons/furina/service.py` ~30 行，archon 本体不参与执行。

### 水神·游戏服务（FurinaGameService，完整保留）

`paimon/archons/furina_game/` 子包：

- `/game` 面板（账号 / 抽卡 / 便笺 / 深渊 / 角色 / 概览，6 mixin）
- cron：`mihoyo_collect`（每日 8:05 签到 + 便笺 + 深渊）/ `mihoyo_game_collect`（早 7 点资讯）
- subscription type：`mihoyo_game`
- 米哈游账号 + stoken + authkey 管理
