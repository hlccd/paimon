# 岩神·摩拉克斯

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神

- **主题**：契约·财富
- **核心职能**：理财（红利股扫描 + 评分 + 推送 + 用户关注股 watchlist）+ `/wealth` 面板
- **Web 面板**：✅ `/wealth` 理财面板

## ⚠️ 当前状态（2026-05 解耦后）

`execute()` 内部业务已移除（原"代四影通用执行"职能转 `paimon/shades/{naberius,jonova}/`），**非四影功能完整保留**：

### 保留（非四影功能）

- `dividend_scan` cron（full / daily / rescore 三档扫描）+ `stock_watch_collect` cron（用户关注股）
- `/wealth` 面板（推荐 / 排行 / 变化 / 历史趋势）
- `collect_dividend` 主入口（红利股采集 + 评分 + 日报 digest）
- `scorer`（红利股评分体系：可持续 / 财务 / 估值 / 记录 / 动能 5 维度）
- `handle_query`（`/dividend` 命令 + dividend tool 共用）
- 4 个 mixin：`_ScanMixin` / `_SkillMixin` / `_WatchMixin` / `_DigestMixin`

### 移除

- `zhongli.py:execute()` 内部"通用理财 tool-loop"（asmoday 不再调本节点 execute）

## 与原石的边界

- 原石 = **系统资源消耗**（LLM token / 花费）
- 岩神 = **用户个人财富**（股票 / 资产 / 退休），和 LLM 消耗无关
