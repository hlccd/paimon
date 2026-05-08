# 火神·玛薇卡

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神

- **主题**：战争·冲锋
- **核心职能**：（解耦后暂无具体职能 / namespace 保留）
- **Web 面板**：—

## ⚠️ 当前状态（2026-05 解耦后）

本节点 archon 本体跟四影解耦后**暂无具体职能**：

- 移除：`execute()` 内部 exec tool-loop
- 已搬到生执 `paimon/shades/naberius/_simple.py`（stage = `exec`）
- saga 补偿器（`paimon/shades/istaroth/saga.py:_compensate_one`）从 `MavuikaArchon()` 改用生执 `simple_run("exec")`
- 保留：class `MavuikaArchon` + `name` + `description` + `execute` 兜底（namespace 壳）

**待用户后续安排**：删除整个文件 / 重写新职能 / 保留等待。
跟踪：见 [`docs/todo.md`](../todo.md)。
