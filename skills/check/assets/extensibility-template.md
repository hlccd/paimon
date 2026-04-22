# 功能拓展分析报告

> module: **extensibility** · 档位: **{level}** · 验证轮: **{validation_rounds_completed}**
> 生成时间: {generated_at} · 耗时: {duration}

---

## 1. 元信息

| 项 | 值 |
|----|----|
| 源码目录 | `{src_path}` |
| 模块总数 | {modules_identified} |
| 扫描文件数 | {scanned_files} |
| 语言构成 | {breakdown} |
| 扫描轮次 | 1 |
| 分析轮次 | 1 |
| 推荐轮次 | 1 |
| 验证轮次 | {validation_rounds_completed} |

<!-- 轮次计数为运行时统计，orchestrator 在各阶段完成后记录 -->

---

## 2. 架构概览

> {architecture_summary}

<!-- 生成规则：从 architecture-map.md 提取模块清单，综合为 1-2 段话描述项目整体架构。 -->

<!--
一段话描述项目整体架构：分几层、核心模块、主要数据流。
-->

---

## 3. 模块地图

### 3.1 模块清单

| 模块 | 职责 | 对外契约 | 依赖 | 被依赖 | 已识别扩展点 |
|------|------|---------|------|--------|-------------|
{module_map_table}

### 3.2 依赖关系图

```
{dependency_graph}
```

<!-- 生成规则：从 architecture-map.md 的 MODULE 行提取依赖关系，生成 ASCII 有向图。模块数 >15 时仅展示核心模块。 -->

---

## 4. 功能缺口分析

### 4.1 功能边界与天花板

{functional_boundary}

### 4.2 缺口清单

| # | 类型 | 模块 | 缺口描述 | 影响面 | 潜在价值 |
|---|------|------|---------|--------|---------|
{gap_table}

---

## 5. 扩展机会排行榜（经验证）

按严重度 P0→P3、同级内按 score 降序排列：

| # | 严重度 | 模块 | 扩展方向 | 难度 | 价值 | 评分 | 推荐度 |
|---|--------|------|---------|------|------|------|--------|
{opportunity_ranking_table}

<!--
严重度含义（extensibility module）：
- P0: 核心功能缺失——不做会严重限制项目价值
- P1: 重要缺口——显著影响用户体验或竞争力
- P2: 有价值但非紧迫——可排期实施
- P3: 锦上添花——按需考虑

推荐度仍由 score 决定：
- 20-25: 强烈推荐（高价值 + 低成本）
- 15-19: 推荐（需权衡）
- 10-14: 值得考虑
- 5-9: 暂不建议
-->

---

## 6. 验证结果摘要

| 指标 | 值 |
|------|----|
| 验证轮数 | {validation_rounds_completed} |
| 原始推荐数 | {opportunities_count} |
| 验证通过 | {confirmed_opportunities} |
| 验证驳回 | {rejected_opportunities} |
| 待定 | {deferred_opportunities} |

### 被驳回的推荐

| 模块 | 方向 | 原始评分 | 驳回理由 |
|------|------|---------|---------|
{rejected_opportunities_table}

---

## 7. Top 5 详细推荐

{top_5_details}

<!--
对评分最高的 5 个经验证机会，给出具体实施路径：

### TOP-1 · 添加 Discord Channel · 评分 20 · **P0**

**目标**：...
**难度拆解**（difficulty=2）：...
**价值拆解**（value=5）：...
**实施步骤**：...
**预计工时**：...
**风险**：...
-->

---

## 8. 中等价值机会（评分 10-19）

{mid_value_section}

---

## 9. 低价值机会（评分 < 10）

{low_value_section}

---

## 10. 架构健康度观察

> {architecture_observations}

<!--
从 Scan 阶段沉淀的观察（非问题，而是结构性观察）：
- 抽象最干净的模块：_____
- 依赖最复杂的模块：_____
- 可替换性最强的层：_____
- 可替换性最弱的层：_____
-->

---

## 附录 A · 本次运行参数

配置记录：输入模式=`{input_mode}` · 质量维度=`extensibility` · 源码=`{src_path}` · 档位=`{level}`

## 附录 B · 原始数据

- 模块地图：`.check/architecture-map.md`
- 功能缺口清单：`.check/gaps.jsonl`
- 扩展机会清单（含验证结果）：`.check/opportunities.jsonl`
- 运行状态快照：`.check/state.json`
