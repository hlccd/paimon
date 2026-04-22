# 审查类型（Check Types）

定义审查的类型及其行为差异。面向用户的术语为「审查类型」，内部字段名保持 `input_mode`。

---

## 审查类型

### 自检（单源审查）

| 类型 | 含义 | 内部 input_mode | 需要路径 |
|------|------|----------------|---------|
| **自检-代码** | 对一份代码进行质量审查 | code | --src |
| **自检-文档** | 对一份文档进行质量审查 | docs | --docs |
| **自检-方案** | 对技术方案/PRD 进行可实施性与完整性审查 | spec | --spec |
| **自检-PR** | 对一个 PR/MR 的变更代码进行质量审查 | pr | --src（自动通过 git diff 限定范围） |

### 对比校验（双源审查）

| 类型 | 含义 | 内部 input_mode | 需要路径 | 特点 |
|------|------|----------------|---------|------|
| **代码 vs 文档**（默认） | 文档是否准确描述代码 | code-vs-docs | --src + --docs | 以代码为准审文档 |
| **代码 vs 代码** | 两份代码各自打分 + 找差异 | code-vs-code | --src-a + --src-b | 分别审查 + diff 视角 |
| **文档 vs 文档** | 两份文档各自打分 + 找差异 | docs-vs-docs | --docs-a + --docs-b | 分别审查 + diff 视角 |
| **代码 vs 方案** | 代码实现是否遵循技术方案 | code-vs-spec | --src + --spec | 以方案为准审代码 |
| **变更 vs 方案** | 特定变更是否按方案执行 | change-vs-spec | --change + --spec | 以方案为准审变更 |

---

## Module 兼容矩阵

| Module | 自检-代码 | 自检-文档 | 自检-方案 | 代码vs文档 | 代码vs代码 | 文档vs文档 | 代码vs方案 | 变更vs方案 |
|--------|----------|----------|----------|-----------|-----------|-----------|-----------|-----------|
| accuracy | ACC-012~014 | ACC-*,LNK-* | ACC-*,LNK-* | 全部 | ACC-012~014 | ACC-*,LNK-* | 代码侧 ACC-012~014 | 同代码vs方案 |
| clarity | CLR-*+引用 | BRV-*,LNG-* | BRV-*,LNG-* | 全部 | CLR-*+引用 | BRV-*,LNG-* | CLR-*+BRV-*,LNG-* | 同代码vs方案 |
| consistency | CST-* | CON-* | CON-* | 全部 | CST-*+diff | CON-*+diff | CON-*+CST-* | 同代码vs方案 |
| security | SEC-* | SEC-005/006 | SEC-005/006 | SEC-*+SEC-005/006(文档侧) | SEC-* | -- | SEC-* | SEC-*(变更范围) |
| hygiene | DEAD-001~005/007,HYG-* | -- | -- | 代码侧 | DEAD-001~005/007,HYG-* | -- | 代码侧 | 变更范围 |
| completeness | CMP-006~007 | CMP-001~005 | CMP-001~005 | 全部 | CMP-006~007 | CMP-001~005 | CMP-* | CMP-*(变更范围) |
| usability | USB-001/002/005/007 | USB-003/004/006 | USB-003/004/006 | 全部 | USB 代码侧 | USB 文档侧 | USB 全部 | USB 代码侧 |
| freshness | FRS-002/003/006 | FRS-001/004/005 | FRS-001/004/005 | 全部 | FRS 代码侧 | FRS 文档侧 | 全部 | FRS 代码侧 |
| compliance | SKL-*,CPL-002~004 | CPL-001/005 | CPL-001/005 | 全部 | SKL-*,CPL-* | CPL-001/005 | SKL-*,CPL-* | CPL-*(变更范围) |
| reliability | REL-* | -- | -- | REL-*(代码侧) | REL-* | -- | REL-* | REL-*(变更范围) |
| performance | PERF-* | -- | -- | PERF-*(代码侧) | PERF-* | -- | PERF-* | PERF-*(变更范围) |
| architecture | ARCH-*,DEAD-006/008 | -- | -- | ARCH-*(代码侧) | ARCH-*+diff | -- | ARCH-* | ARCH-*(变更范围) |
| project-health | PRJ-* | -- | -- | PRJ-* | PRJ-* | -- | PRJ-* | PRJ-*(变更范围) |
| extensibility | EXT-* | -- | -- | EXT-*(代码侧) | EXT-* | -- | -- | -- |
| **feasibility** | -- | -- | **FEA-*** | -- | -- | -- | FEA-005/006/007/012/015(方案侧) | FEA-005/006/007/012/015(方案侧) |
| **alignment** | -- | -- | -- | -- | -- | -- | **ALN-*** | **ALN-***(变更范围) |
| **coherence** | COH-001~004,006~008,010 | COH-001~002,004~006,009~010 | COH-001~002,004~006,009~010 | **COH-001~010** | COH-001~004,006~008,010 | COH-001~002,004~006,009~010(双侧) | COH-001~004,006~008,010 | COH-001~004,006~008,010(变更范围) |
| testability | TST-* | -- | -- | TST-*(代码侧) | TST-* | -- | TST-* | TST-*(变更范围) |
| observability | OBS-* | -- | -- | OBS-*(代码侧) | OBS-* | -- | OBS-* | OBS-*(变更范围) |
| robustness | ROB-* | -- | -- | ROB-*(代码侧) | ROB-* | -- | ROB-* | ROB-*(变更范围) |
| portability | PRT-* | -- | -- | PRT-*(代码侧) | PRT-* | -- | PRT-* | PRT-*(变更范围) |
| maintainability | MNT-001~004/006 | MNT-005 | MNT-005 | 全部 | MNT-* | MNT-005 | MNT-* | MNT-*(变更范围) |

`--` = 不兼容。`+diff` = 额外启用两份输入之间的差异比对视角。`(变更范围)` = 仅审查变更涉及的文件。

---

## comprehensive 展开

| 审查类型 | comprehensive 展开（extensibility 除外） |
|---------|----------------------------------------|
| 自检-代码 | 18 个代码兼容模块 + coherence（19 个） |
| 自检-PR | 同自检-代码（19 个，限变更范围） |
| 自检-文档 | accuracy, clarity, consistency, completeness, usability, freshness, compliance, maintainability, coherence（9 个） |
| 自检-方案 | feasibility, accuracy, clarity, consistency, completeness, usability, freshness, compliance, maintainability, coherence, security(文档子集)（11 个） |
| 代码 vs 文档 | 18 个代码兼容模块 + coherence（19 个，coherence 覆盖双侧） |
| 代码 vs 代码 | 18 个代码兼容模块 + coherence（19 个） |
| 文档 vs 文档 | 8 个文档兼容模块 + coherence（9 个） |
| 代码 vs 方案 | alignment + 18 个代码兼容模块 + coherence（20 个） |
| 变更 vs 方案 | alignment + 18 个代码兼容模块 + coherence（20 个，限变更范围） |

---

## 各类型行为差异

### 自检-代码

- 扫描 `--src` 下所有代码文件，按语言统计，按目录分组（10-30 文件/组）
- 固定 report-only
- link-checker.py 不运行

### 自检-PR

- 底层复用 code 模式的全部 module 和检查项
- 变更范围：通过 `git diff main...HEAD --name-only`（或用户指定的 base 分支）获取变更文件列表
- 审查范围限定于变更文件 + 直接依赖文件（作为上下文）
- 固定 report-only
- link-checker.py 不运行

### 自检-文档

- 扫描 `--docs` 下所有 .md 文件（5-8 文件/组）
- 首轮运行 `link-checker.py`
- 默认 report-only；可 `--fix=p0|p0+p1|all`
- 修复原则：以源码为准改文档

### 自检-方案

- 扫描 `--spec` 下所有方案文件（.md/.docx/.pdf）
- 首轮运行 `link-checker.py`（仅 .md 文件）
- 默认 report-only；可 `--fix=p0|p0+p1|all`（仅改方案文档）
- 修复原则：补充缺失定义、具体化模糊描述、修正格式问题
- feasibility 模块为核心——其他模块提供辅助审查

### 代码 vs 文档

- 同时扫描 `--src` 和 `--docs`
- 文档侧可 `--fix`（仅改文档）
- link-checker.py 对 `--docs` 运行

### 代码 vs 代码

- 分别扫描 `--src-a` 和 `--src-b`
- 每个模块对两份代码各自执行发现+验证，产出两份 findings
- 额外增加 **diff 视角轮**：比对两份代码在同一模块上的差异（一方有问题另一方没有、两方不同实现方式的优劣）
- 固定 report-only
- 报告分为「A 独有问题」「B 独有问题」「共同问题」「差异分析」四部分

### 文档 vs 文档

- 分别扫描 `--docs-a` 和 `--docs-b`
- 逻辑同代码 vs 代码：各自审查 + diff 视角
- 文档侧可 `--fix`（需指定修复哪一份）
- link-checker.py 对两份文档分别运行

### 代码 vs 方案

- 同时扫描 `--src`（代码）和 `--spec`（方案）
- **方向：以方案为准审代码**（与代码vs文档的方向相反）
- alignment 模块先执行**方案要点提取**，再逐点比对代码
- 固定 report-only（不改代码也不改方案）
- 报告包含对齐评分 + 缺失/超出/偏差分析

### 变更 vs 方案

- 扫描 `--change`（变更范围）和 `--spec`（方案）
- 变更来源支持三种输入：
  1. git diff（分支比较或 commit 范围）
  2. 文件列表（指定具体变更文件）
  3. 当前未提交变更（`git diff` + `git diff --staged`）
- 逻辑同代码 vs 方案，但审查范围限定于变更文件
- alignment 模块仅验证变更涉及的方案要点（非全量对齐）
- 固定 report-only

---

## 执行引擎选择

| Module | 引擎 |
|--------|------|
| 其余 21 个（含 feasibility, alignment, coherence） | 问题发现引擎 |
| extensibility | 机会发现引擎 |

alignment 模块使用问题发现引擎但增加**方案要点提取**前置步骤（详见 execution-guide.md）。

对比校验中同时选中两类 → 先问题发现，再机会发现。

---

## Fix 模式适用性

| 审查类型 | Fix 可用 | 说明 |
|---------|---------|------|
| 自检-代码 | 否 | 固定 report-only |
| 自检-PR | 否 | 固定 report-only |
| 自检-文档 | 是 | 用户在调用 3 选择修复策略 |
| 自检-方案 | 是 | 用户选择，仅改方案文档 |
| 代码 vs 文档 | 文档侧 | 用户选择，仅改文档 |
| 代码 vs 代码 | 否 | 固定 report-only |
| 文档 vs 文档 | 是 | 用户选择，需指定修复哪一份 |
| 代码 vs 方案 | 否 | 固定 report-only |
| 变更 vs 方案 | 否 | 固定 report-only |
| extensibility module | 否 | 固定 report-only |
