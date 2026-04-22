# 审查报告

> 输入模式: **{input_mode}** · 质量维度: **{modules}** · 档位: **{level}**<!-- fix 模式追加 --> · 修复策略: **{fix_strategy}**
> 生成时间: {generated_at} · 耗时: {duration}

---

## 1. 元信息

| 项 | 值 |
|----|----|
| 源码目录 | `{src_path}` |
| 文档目录 | `{docs_path}` |
| 扫描文件数 | {scanned_files} |
| 语言/文件构成 | {breakdown} |
| 轮次配置 | {rounds_config} |
| 执行轮次总数 | {total_rounds} |
| 执行引擎 | {engines_used} |

---

## 2. 总体统计

| 阶段 | 输入 | 输出 |
|------|------|------|
| 发现 | {scanned_files} 文件 | {candidates_count} 候选 |
| 验证 | {candidates_count} 候选 | 确认 **{confirmed_count}** · 误报 {rejected_count} · 待定 {deferred_count} |
<!-- 以下两行仅 fix 模式包含 -->
| 修复 | {fixable_count} 符合策略 | 自动修复 {auto_fix_count} · 仅报告 {report_only_count} · 失败 {fix_failed} |
| 回归 | {fix_success} 修复 | 正确 {verified} · 新缺陷 {regression_count} |

### 严重度分布

<!-- report-only 模式：省略"已修"列 -->

| 级别 | 数量 | 已修 |
|------|------|------|
| **P0** | {p0_total} | {p0_fixed} |
| **P1** | {p1_total} | {p1_fixed} |
| **P2** | {p2_total} | {p2_fixed} |
| **P3** | {p3_total} | {p3_fixed} |

<!-- 以下三段仅多 module 审查时包含 -->

### Module 仪表盘

| Module | P0 | P1 | P2 | P3 | 小计 |
|--------|----|----|----|----|------|
{module_dashboard}

### 跨 Module 根因聚合

{cross_module_root_causes}

<!-- /多 module 特殊段结束 -->

---

## 3. 确认问题清单

### P0（{p0_total}）

{p0_findings_table}

### P1（{p1_total}）

{p1_findings_table}

### P2（{p2_total}）

{p2_findings_table}

### P3（{p3_total}）

{p3_findings_table}

<!-- 仅多 module 包含 -->

### 按 Module 分组视图

{per_module_findings}

<!-- /多 module 分组视图结束 -->

---

<!-- 以下第 4、5 节仅 fix 模式包含 -->

## 4. 修复日志

<!-- 表格格式：| # | Check-ID | 文件 | 修复前 | 修复后 | 复查结果 | -->
{fix_log_section}

---

## 5. 回归结果

<!-- 表格格式：| # | 轮次 | 文件 | 回归问题描述 | 处理结果 | -->
{regression_section}

---

<!-- /fix 模式结束 -->

<!-- 以下段仅 alignment 模块包含 -->

## 6. 方案对齐分析

### 对齐评分

| 维度 | 满分 | 得分 | 详情 |
|------|------|------|------|
| 接口定义 | 10 | {aln_interface} | |
| 数据模型 | 10 | {aln_data_model} | |
| 架构落位 | 15 | {aln_architecture} | |
| 外部依赖 | 15 | {aln_dependencies} | |
| 配置项 | 10 | {aln_config} | |
| 流程一致 | 15 | {aln_flow} | |
| 测试覆盖 | 15 | {aln_test} | |
| 错误处理 | 10 | {aln_error_handling} | |
| **总分** | **100** | **{aln_total}** | |

### 质量门禁判定

**判定: {aln_verdict}**（APPROVE / REQUEST_CHANGES / BLOCKED）

<!-- APPROVE: 0 个 P0 且总分 >= 80 | REQUEST_CHANGES: 0 个 P0 但有 P1 或总分 60-79 | BLOCKED: 有 P0 或总分 < 60 -->

### 缺失实现（方案要求但未实现）

{aln_missing_section}

### 超出方案（代码存在但方案未提及）

{aln_excess_section}

### 偏差分析（实现与方案不一致）

{aln_deviation_section}

### 方案待补充（方案模糊区域）

{aln_ambiguous_section}

---

<!-- /alignment 模块结束 -->

## 7. 待定 / 误报

### 待定（需人工判断）

<!-- 表格格式：| # | Check-ID | 位置 | 描述 | 待定原因 | -->
{deferred_table}

### 误报摘要

<!-- 表格格式：| 驳回原因 | 数量 | 典型案例 | -->
{rejected_summary}

---

## 8. 结论

{conclusion}

<!-- 生成规则：综合以下要素撰写 2-4 段结论：
1. 核心发现摘要（最高优先级的 2-3 个问题组）
2. 系统性根因（如有跨 module 聚合）
3. 建议优先行动（按修复影响排序的 Top 5 行动项）
4. 整体评价（项目在选定质量维度的健康度判断）
-->

---

## 附录

- 配置记录：输入模式=`{input_mode}` · 质量维度=`{modules}` · 源码=`{src_path}` · 档位=`{level}`<!-- fix 追加 · 修复策略=`{fix_strategy}` -->
- 原始数据：`.check/candidates.jsonl` · `.check/fixes.jsonl` · `.check/state.json`
