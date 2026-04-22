---
name: check
description: "多轮迭代审查工具。22 个质量维度模块自由组合，支持代码/文档/方案/交叉等输入模式。基于 N+M+K 多轮方法论，主 orchestrator 多轮视角切换自审，对抗单轮 LLM 审查的假阳性/假阴性。"
argument-hint: "启动后交互式选择配置"
user-invocable: true
allowed-tools: "Read Write Edit Glob Grep AskUserQuestion Bash(python3:*) Bash(mkdir:*) Bash(wc:*) Bash(git:*) Bash(date:*)"
metadata:
  author: hlccd
  version: "4.0"
  date: 2026-04-21
---

# check: 多轮迭代审查

按质量维度挑刺，输入灵活。

## 质量维度模块（22 个）

| # | 模块 | 中文名 | 核心问句 | 范围 | 备注 |
|---|------|--------|---------|------|------|
| 1 | accuracy | 准确性 | 准不准？ | 声明与现实是否一致——方法名/参数/路径/配置值与源码吻合，注释与行为一致 | 审查视角；docs, code-vs-docs, code(注释) |
| 2 | clarity | 清晰度 | 清不清楚？ | 能不能看懂——接口契约可读性、命名表意、嵌套深度；文档简洁性、无空洞废话 | 审查视角；code + docs |
| 3 | consistency | 一致性 | 一不一致？ | 系统内各处是否自相矛盾——跨文档描述矛盾、代码风格/命名约定不统一 | 审查视角；code + docs |
| 4 | security | 安全性 | 安不安全？ | 能不能被攻击——注入、认证/授权缺陷、密钥管理、弱加密、XSS/CSRF | 审查视角；code 主, docs 子集 |
| 5 | hygiene | 卫生度 | 干不干净？ | 代码垃圾——死代码、注释掉的代码块、空文件、过时配置项 | 审查视角；code 主 |
| 6 | completeness | 完整性 | 全不全？ | 该有的有没有——接口文档覆盖、错误场景覆盖、必要分支/边界/default | 审查视角；code + docs |
| 7 | usability | 易用性 | 好不好用？ | 用户使用摩擦——API 错误信息质量、配置复杂度、快速开始示例、文档导航 | 审查视角；code + docs |
| 8 | freshness | 新鲜度 | 新不新？ | 内容是否过时——描述已删功能、已停维依赖、已废弃 API、已下线外部资源 | 审查视角；code + docs |
| 9 | compliance | 合规性 | 合不合规？ | 是否符合规范——Skill 合规、许可证兼容、代码/commit 规范、数据隐私 | 审查视角；code + docs |
| 10 | reliability | 可靠性 | 崩不崩？ | 正常条件下崩溃/丢数据/卡死——异常吞没、资源泄漏、并发竞态、非原子持久化 | 技术维度；code 主 |
| 11 | performance | 性能 | 快不快？ | 运行时效率——N+1 查询、阻塞异步、O(n²) 热路径、缓存问题 | 技术维度；code 主 |
| 12 | architecture | 架构 | 结构好不好？ | 代码结构——循环依赖、上帝对象、分层破坏、紧耦合、重复实现 | 技术维度；code 主 |
| 13 | project-health | 项目健康 | 基础设施能不能跑？ | 项目元数据——README/配置示例/依赖声明/入口文件/CI/Dockerfile | 技术维度；code 主 |
| 14 | extensibility | 可扩展性 | 能不能扩展？ | 扩展能力和功能缺口——扩展模式识别、功能边界、同类对比、工作流断点 | 技术维度；code 主；机会发现引擎 |
| 15 | testability | 可测试性 | 好不好测？ | 测试友好度——硬编码依赖、全局状态污染、副作用深藏、缺少注入点 | 技术维度；code 主 |
| 16 | observability | 可观测性 | 能不能观测？ | 运行时诊断——日志覆盖/上下文、健康检查、请求追踪、异步任务状态 | 技术维度；code 主 |
| 17 | robustness | 健壮性 | 扛不扛得住？ | 意外条件下的韧性——输入验证、熔断、速率限制、级联失败隔离、优雅关闭 | 技术维度；code 主 |
| 18 | portability | 可移植性 | 能不能迁？ | 跨环境运行——硬编码路径/主机名、平台特定调用、DB 方言绑定、编码假设 | 技术维度；code 主 |
| 19 | maintainability | 可维护性 | 好不好改？ | 变更成本——变更放大、魔法值散落、缺少变更隔离、测试脆弱、文档同步成本 | 技术维度；code 主, docs(同步成本) |
| 20 | feasibility | 可实施性 | 做不做得出来？ | 方案能否落地——技术假设可行性、接口/数据模型完整性、异常流程覆盖、模糊词 | 方案维度；spec 主 |
| 21 | alignment | 方案对齐 | 做没做对？ | 实现是否遵循方案——接口/模型/架构/流程对齐、缺失检测、超出检测、偏差分析 | 对齐维度；code-vs-spec, change-vs-spec |
| 22 | coherence | 连贯性 | 各部分连没连对？ | 多文件间引用链闭合/跨文件矛盾/注册一致/孤儿检测/陈旧内容/结构错位 | 结构维度；code + docs + spec |

> **comprehensive** = 当前输入模式下所有兼容模块（extensibility 除外，需显式选择）。
> 21 个模块使用问题发现引擎（alignment 增加方案要点提取前置步骤），extensibility 使用机会发现引擎。

## 审查类型

| 类型 | 含义 | 用户路径 |
|------|------|---------|
| 自检-代码 | 对一份代码质量审查 | 质量审查 → 项目代码 |
| 自检-文档 | 对一份文档质量审查 | 质量审查 → 文档 |
| 自检-方案 | 技术方案/PRD 可实施性与完整性审查 | 质量审查 → 技术方案/PRD |
| 自检-PR | 对一个 PR/MR 的代码质量审查 | 质量审查 → PR/MR 变更 |
| 对比-代码vs文档 | 文档是否准确描述代码 | 对齐检查 → 代码↔文档 |
| 对比-代码vs方案 | 代码实现是否遵循技术方案 | 对齐检查 → 代码↔方案 |
| 对比-变更vs方案 | 特定变更是否按方案执行 | 对齐检查 → 变更↔方案 |
| 对比-代码vs代码 | 两份代码各自打分+找差异 | 对齐检查 → Other |
| 对比-文档vs文档 | 两份文档各自打分+找差异 | 对齐检查 → Other |
| 项目体检 | 自动扫描+智能编排多类型组合审查 | 项目体检 → 自动推荐 |

---

## 第一步：交互式配置

所有路径统一 3 次调用。不解析 `$ARGUMENTS`。

### 配置流程

```
调用 1 → 你想做什么？（1 题）
  ├ ① 质量审查 — "帮我看看这个东西有没有问题"
  ├ ② 对齐检查 — "帮我看看这些东西是否一致"
  └ ③ 项目体检 — "给你一个项目，全面看看"
```

**质量审查（调用 2 → 2 题）**：

```
调用 2：
  ├ Q1 审查什么？
  │    ├ 项目代码
  │    ├ 文档
  │    ├ 技术方案/PRD
  │    └ PR/MR 变更
  │    （Other → 指定文件列表）
  └ Q2 目标
       ├ 当前目录（推荐）
       └ 指定路径
       （PR 时：当前目录 = 当前分支 vs main；需指定 commit 范围/最近N个 → Other 或备注）

→ 打印审查计划
```

**对齐检查（调用 2 → 3 题）**：

```
调用 2：
  ├ Q1 对比什么？
  │    ├ 代码 ↔ 文档 — 文档是否准确描述代码
  │    ├ 代码 ↔ 技术方案 — 代码是否按方案实现
  │    └ 变更 ↔ 技术方案 — 某个变更是否符合方案
  │    （Other → 代码↔代码 / 文档↔文档 / 三者对齐）
  ├ Q2 输入 A 路径（代码目录 / 变更来源，默认 cwd）
  └ Q3 输入 B 路径（文档目录 / 方案文件）

→ 打印审查计划
```

**项目体检（调用 2 → 1 题）**：

```
调用 2：
  └ Q1 项目路径
       ├ 当前目录（推荐）
       └ 指定路径

→ 自动扫描项目结构，识别代码/文档/方案/配置
→ 推荐审查组合，如：
  "发现：src/ (代码) + docs/ (文档) + design.md (方案)
   推荐：
   ① 综合质量审查 → src/ + docs/
   ② 代码↔文档对齐 → src/ vs docs/
   ③ 代码↔方案对齐 → src/ vs design.md"
→ 打印审查计划
```

**调用 3（所有路径统一 → 3-4 题）**：

```
调用 3：
  ├ Q1 质量维度 → 全部（推荐）/ 深入 / 标准 / 核心
  │    （选项数量因审查类型而异，见下方层级详情）
  ├ Q2 审查深度 → 标准（推荐）/ 快速 / 深入 / 全面
  ├ Q3 修复策略 → 仅报告（推荐）/ 修复 P0 / 修复 P0+P1 / 修复全部
  │    （仅当审查类型支持修复时显示；code/code-vs-spec/change-vs-spec 固定仅报告，跳过此题）
  │    （支持修复的类型：自检-文档、自检-方案、代码↔文档的文档侧、文档↔文档）
  └ Q4 确认
       ├ ① 确认开始（推荐）— 此后零交互直至完成
       ├ ② 添加备注
       └ ③ 重新配置 — 回到调用 1 重来

  选 ② 添加备注时：输出"请输入备注内容："等待用户下一条消息作为备注文本
    → 覆盖写入 config.user_context（仅保留最新一条）
    → 重新打印审查计划（末尾追加「备注: {text}」）→ 回到调用 3
```

### 分支总览

```
调用1: 意图
├─ 质量审查 ─ 调用2(2Q: 类型+路径) ─ 计划 ─ 调用3(3-4Q: 维度+深度+[修复]+确认)
├─ 对齐检查 ─ 调用2(3Q: 类型+A+B) ─ 计划 ─ 调用3(3-4Q: 维度+深度+[修复]+确认)
└─ 项目体检 ─ 调用2(1Q: 路径)→扫描 ─ 计划 ─ 调用3(3-4Q: 维度+深度+[修复]+确认)
```

### 模块层级详情

**自检-代码 / 对比-代码vs代码**（19 个可用模块）：

| 层级 | 数量 | 包含 |
|------|------|------|
| **全部（推荐）** | 19 | 准确性、安全性、清晰度、可靠性、一致性、完整性、架构、卫生度、性能、可维护性、健壮性、可测试性、合规性、可观测性、可移植性、新鲜度、易用性、项目健康、连贯性 |
| **深入** | 14 | 准确性、安全性、清晰度、可靠性、一致性、完整性、架构、卫生度、性能、可维护性、健壮性、可测试性、合规性、连贯性 |
| **标准** | 8 | 准确性、安全性、清晰度、可靠性、一致性、完整性、架构、卫生度 |
| **核心** | 4 | 准确性、安全性、清晰度、可靠性 |

**对比-代码vs文档**（19 个可用模块）：

| 层级 | 数量 | 包含 |
|------|------|------|
| **全部（推荐）** | 19 | 18 个代码兼容模块 + 连贯性（双侧） |
| **深入** | 14 | 同自检-代码深入层级 |
| **标准** | 8 | 同自检-代码标准层级 |
| **核心** | 4 | 同自检-代码核心层级 |

**对比-文档vs文档**（9 个可用模块）：

| 层级 | 数量 | 包含 |
|------|------|------|
| **全部（推荐）** | 9 | 准确性、清晰度、一致性、完整性、易用性、新鲜度、合规性、可维护性、连贯性 |
| **深入** | 7 | 准确性、清晰度、一致性、完整性、易用性、新鲜度、连贯性 |
| **标准** | 4 | 准确性、清晰度、一致性、完整性 |
| **核心** | 2 | 准确性、清晰度 |

**自检-文档**（9 个可用模块）：

| 层级 | 数量 | 包含 |
|------|------|------|
| **全部（推荐）** | 9 | 准确性、清晰度、一致性、完整性、易用性、新鲜度、合规性、可维护性、连贯性 |
| **深入** | 7 | 准确性、清晰度、一致性、完整性、易用性、新鲜度、连贯性 |
| **标准** | 4 | 准确性、清晰度、一致性、完整性 |
| **核心** | 2 | 准确性、清晰度 |

**自检-方案**（11 个可用模块）：

| 层级 | 数量 | 包含 |
|------|------|------|
| **全部（推荐）** | 11 | 可实施性、准确性、清晰度、一致性、完整性、易用性、新鲜度、合规性、可维护性、连贯性、安全性(文档子集) |
| **深入** | 8 | 可实施性、准确性、清晰度、一致性、完整性、易用性、新鲜度、连贯性 |
| **标准** | 5 | 可实施性、准确性、清晰度、一致性、完整性 |
| **核心** | 3 | 可实施性、准确性、清晰度 |

**对比-代码vs方案 / 对比-变更vs方案**（20 个可用模块）：

| 层级 | 数量 | 包含 |
|------|------|------|
| **全部（推荐）** | 20 | 方案对齐 + 18 个代码兼容模块 + 连贯性 |
| **深入** | 15 | 方案对齐 + 准确性、安全性、清晰度、可靠性、一致性、完整性、架构、卫生度、性能、可维护性、健壮性、可测试性、合规性、连贯性 |
| **标准** | 9 | 方案对齐 + 准确性、安全性、清晰度、可靠性、一致性、完整性、架构、卫生度 |
| **核心** | 5 | 方案对齐 + 准确性、安全性、清晰度、可靠性 |

> extensibility（可扩展性）不在层级中，后续作为独立功能处理。
> Other 可在任意层级上微调：`标准 +性能 -卫生度`，或直接输入模块列表。

### 深度对照表

| 档位 | 最少迭代 | 连续 clean 停止 | 最大迭代 | 发现轮/迭代 | 验证轮/迭代 |
|------|---------|---------------|---------|------------|------------|
| 快速 | 1 | 不适用（单次强制停止） | 1 | 2 | 3 |
| 标准 | 3 | 2 | 10 | 2 | 3 |
| 深入 | 5 | 3 | 20 | 2 | 3 |
| 全面 | 10 | 4 | 30 | 2 | 3 |

> 每迭代内层轮次固定：发现 2 轮 → 验证 3 轮 → 修复 1 轮（可选，由修复策略控制）。深度仅控制外层迭代次数。

### 校验规则

- 用户选择与审查类型不兼容的模块（如自检-文档选可靠性）→ 警告并忽略
- 层级与单独模块同时选中 → 以层级为基础，叠加/移除单独模块

---

## 第二步：初始化与计划

调用 2 收集路径后、调用 3 之前执行。

1. **加载参考文件**：
   - `${CLAUDE_SKILL_DIR}/references/severity-guidelines.md`
   - `${CLAUDE_SKILL_DIR}/references/methodology.md`
   - `${CLAUDE_SKILL_DIR}/references/check-catalog.md`
   - `${CLAUDE_SKILL_DIR}/references/input-modes.md`
   - `${CLAUDE_SKILL_DIR}/references/modules/{module}.md`（每个选中的 module；extensibility 固定加载）

2. **扫描目标**：
   - 质量审查-代码/PR：枚举目标下文件，按语言统计，按目录分组；PR 模式解析变更范围
   - 质量审查-文档/方案：枚举 .md 文件；运行 `python3 ${CLAUDE_SKILL_DIR}/scripts/link-checker.py {target_dir}` 做首轮链接检查（目标为单文件时传入其所在目录）
   - 对齐检查：同时枚举两侧文件；变更↔方案额外解析变更范围（git diff / 文件列表）
   - 项目体检：扫描项目结构，识别代码目录/文档目录/方案文件/配置文件，自动编排审查组合
   - 若 link-checker.py 执行失败（非零退出且输出非合法 JSON），记录错误到 state.json errors 字段，跳过链接检查，不中止流程

3. **创建状态目录**：`<target>/.check/`，从 `${CLAUDE_SKILL_DIR}/assets/state-template.json` 初始化 `state.json`

4. **打印审查计划**（调用 3 前展示，此时维度和深度尚未选择，显示为待定）：
   ```
   审查计划
   ─────────
   意图:     {intent}               ← 质量审查 / 对齐检查 / 项目体检
   审查类型: {check_type}           ← 如"代码质量审查"、"代码↔方案对齐"
   目标:     {paths} ({N} 个文件)
   修复策略: {fix_strategy}         ← 用户选择（不支持修复的类型固定为仅报告）
   执行引擎: {engines}
   质量维度: [调用 3 选择]
   审查深度: [调用 3 选择]

   （项目体检额外显示）
   推荐组合:
   ① {sub_check_1}
   ② {sub_check_2}
   ...
   ```

5. **调用 3 收集维度+深度+确认后**，补全计划并执行。

---

## 第三步：执行

加载详细执行指南：`${CLAUDE_SKILL_DIR}/references/execution-guide.md`

根据选中 module 路由到对应引擎：

- **问题型 module**（accuracy/clarity/consistency/security/hygiene/completeness/usability/freshness/compliance/reliability/performance/architecture/project-health/feasibility/alignment/coherence/testability/observability/robustness/portability/maintainability）→ 问题发现引擎（Discovery → Validation → [Fix] → [Regression]）
- **alignment module 前置步骤**：code-vs-spec / change-vs-spec 模式下，发现阶段前先执行**方案要点提取**（详见 execution-guide.md）
- **extensibility module** → 机会发现引擎（Scan → Analyze → Recommend → Validate）

同时选中两类 → 先运行问题发现引擎，再运行机会发现引擎。

---

## 第四步：生成报告

1. **Write** state.json 终态：
   - `status` → `"completed"`
   - `generated_at` → 当前时间
   - `duration_seconds` → `generated_at - started_at`（秒数）

2. **Read** state.json（必须从文件读取，不可凭执行记忆），提取所有 template 占位符所需的值：

   **从 state.json 直接读取**：

   | state.json 字段 | template 占位符 | 摘要占位符 |
   |----------------|----------------|-----------|
   | `config.input_mode` | `{input_mode}` | |
   | `config.modules` | `{modules}` | |
   | `config.level` | `{level}` | |
   | `config.fix_strategy` | `{fix_strategy}` | |
   | `config.src_path` | `{src_path}` | |
   | `config.docs_path` | `{docs_path}` | |
   | `generated_at` | `{generated_at}` | |
   | `duration_seconds` → 秒转可读格式 | `{duration}` | `{duration}` |
   | `scope.scanned_files` | `{scanned_files}` | |
   | `scope.breakdown` | `{breakdown}` | |
   | `iteration_config` | `{rounds_config}` | |
   | `iteration_state.iterations` 长度 | | `{iterations}` |
   | 迭代数 × (discovery_rounds + validation_rounds) | `{total_rounds}` | |
   | `severity_counts.p0` ~ `p3` | `{p0_total}` ~ `{p3_total}` | `{p0}` ~ `{p3}` |
   | `fix_counts.p0_fixed` ~ `p3_fixed` | `{p0_fixed}` ~ `{p3_fixed}` | |
   | `cumulative.total_candidates` | `{candidates_count}` | |
   | `cumulative.total_confirmed` | `{confirmed_count}` | `{confirmed}` |
   | `cumulative.total_rejected` | `{rejected_count}` | |
   | `cumulative.total_deferred` | `{deferred_count}` | |
   | `cumulative.total_fixed` | | `{fixed}` |
   | `artifacts.report_file` | | `{report_path}` |

   **从 state.json 派生**：
   - `engines` 活跃引擎列表 → `{engines_used}`

   **（含 extensibility 时额外提取）**：
   - `engines.opportunity.confirmed_opportunities` → `{confirmed_opportunities}` / 摘要 `{recommended}`
   - `engines.opportunity.rejected_opportunities` → `{rejected_opportunities}`
   - `engines.opportunity.deferred_opportunities` → `{deferred_opportunities}`
   - `engines.opportunity.opportunities_count` → `{opportunities_count}`
   - `engines.opportunity.validation_rounds_completed` → `{validation_rounds_completed}`

3. **读取模板**：
   - 问题型 module：`${CLAUDE_SKILL_DIR}/assets/report-template.md`
   - extensibility module：`${CLAUDE_SKILL_DIR}/assets/extensibility-template.md`

4. **填充占位符**：用第 2 步的值 + 产物文件汇总数据

   **从 candidates.jsonl 汇总**：
   - `{module_dashboard}` → 按 module 聚合 CONFIRMED 条目
   - `{p0_findings_table}` ~ `{p3_findings_table}` → 按严重度分组的问题表格
   - `{per_module_findings}` → 按 module 分组视图
   - `{cross_module_root_causes}` → 同 file:line 跨 module 的根因聚合
   - `{deferred_table}` → DEFERRED 条目表格
   - `{rejected_summary}` → REJECTED 按驳回原因聚合

   **从 fixes.jsonl 汇总**（仅 fix 模式）：
   - `{fixable_count}` / `{auto_fix_count}` / `{report_only_count}` / `{fix_failed}` / `{fix_success}` / `{verified}` / `{regression_count}`
   - `{fix_log_section}` / `{regression_section}`

   **综合生成**：
   - `{conclusion}` → 综合最高优先级问题组 + 根因 + Top 5 行动项

5. **写入**：`<target>/.check/report.md`

6. **打印摘要**（值来自第 2 步，不可另行拼凑）：
   ```
   ═══ 审查完成 ═══
   耗时:     {duration} · 迭代: {iterations} 轮
   确认问题: {confirmed} (P0:{p0} P1:{p1} P2:{p2} P3:{p3})
   已修复:   {fixed}              ← 仅 fix 模式显示
   报告:     {report_path}
   ═══════════════

   （含 extensibility module 时额外显示）
   推荐:     {recommended} (P0:{p0} P1:{p1} P2:{p2} P3:{p3})
   验证淘汰: {rejected_opportunities}
   ```

---

## 关键原则

1. **全程中文输出**——所有面向用户的交互必须使用中文。技术标识符保持原样。
2. **单 Agent 顺序执行**——所有发现/验证/修复/回归均由主 orchestrator 自身完成，不启动子 Agent，确保用户确认后全程无人值守无授权弹窗
3. **交互式配置 → 确认 → 之后运行中零交互**（确认后支持无人值守）
4. **多轮全视角扫描**（见 methodology.md）——每轮覆盖全部审查视角，多次迭代重复扫描抓遗漏，替代并行 Agent 的交叉确认
5. **共识阈值 ≥2 轮**（Validation：同一问题在 ≥2 轮独立视角中被标记则确认）
6. **修复后自审**（仅 fix 模式）
7. **回归迭代上限 3 次**（仅 fix 模式）
8. **结构化内部记录**（JSON Lines 格式记录到 candidates.jsonl）
9. **简洁凝练**——冗余/废话/臃肿也是 finding
10. **优先结构化表达**——能用表格/流程图的不用大段文字
11. **comprehensive = 当前输入模式下所有兼容 module（extensibility 除外）**
12. **code/pr/code-vs-code/code-vs-spec/change-vs-spec 固定 report-only；docs/spec/code-vs-docs(文档侧)/docs-vs-docs 由用户在调用 3 选择修复策略（仅改文档/方案不改代码）**
13. **extensibility 推荐经验证**——Recommend 后增加 Validate 阶段，多轮过滤并分配 P0-P3

---

## 错误处理

- 某轮扫描输出格式不符 → 跳过该轮输出，记录到 state.json errors，不中止
- 修复操作失败 → 标记 FIX-FAILED，不重试
- 外层迭代不收敛 → 最大迭代后退出，列入 DEFERRED
- 文件读取失败 → 记录错误，跳过该文件，不中止
