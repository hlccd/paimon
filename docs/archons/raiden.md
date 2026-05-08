# 雷神·巴尔泽布

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神

- **主题**：永恒·造物
- **核心职能**：（namespace 永久壳，新职能待挂）
- **Web 面板**：—

## 当前状态：B 类 namespace 壳

按"七神 7 名永久保留"铁律，本节点保留 class + name + description + execute 兜底（约 30 行）。

archon 本体当前**无具体职能**：
- 移除：原 `execute()` 内部业务 / `write_design` / `write_code` / `_write_code_simple` / `self_check`
- 已搬到生执 `paimon/shades/naberius/produce.py`（stage = `design` / `code`）+ `_simple.py`（stage = `simple_code`）+ 死执 `jonova/self_check.py`

**新职能待挂** — 跟踪：见 [`docs/todo.md`](../todo.md)。

## 历史职能（已迁移）

写代码（含自检）+ 评审协作终端，已 100% 移交四影各 stage：
- 生执 produce_design：产 design.md（原雷神 write_design）
- 生执 produce_code：产 code/（原雷神 write_code）
- 生执 simple_run("simple_code")：trivial 任务直接 LLM 写代码（原 _write_code_simple）
- 死执 self_check：py_compile + ruff + pytest（原雷神 self_check）
