# 雷神·巴尔泽布

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神

- **主题**：永恒·造物
- **核心职能**：（解耦后暂无具体职能 / namespace 保留）
- **Web 面板**：—

## ⚠️ 当前状态（2026-05 解耦后）

本节点 archon 本体跟四影解耦后**暂无具体职能**：

- 移除：`execute()` 内部业务 / `write_design` / `write_code` / `_write_code_simple` / `self_check`
- 已搬到：`paimon/shades/worker/`（stage = `design` / `code` / `simple_code`）
- 保留：class `RaidenArchon` + `name` + `description` + `execute` 兜底（namespace 壳）

**待用户后续安排**：删除整个文件 / 重写新职能 / 保留等待。
跟踪：见 [`docs/todo.md`](../todo.md)。

## 历史职能（已迁移）

写代码（含自检）+ 评审协作终端，已 100% 移交工人 stage：
- `design` 工人：产 design.md（原雷神 write_design）
- `code` 工人：产 code/ + self-check.log（原雷神 write_code）
- `simple_code` 工人：trivial 任务直接 LLM 写代码（原 _write_code_simple）
