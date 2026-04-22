# 执行指南（Execution Guide）

本文档定义两种执行引擎的详细流程。根据选中的 module 和输入模式路由。

---

## 引擎选择

| 选中的 module | 使用引擎 |
|-------------|---------|
| accuracy, clarity, consistency, security, hygiene, completeness, usability, freshness, compliance, reliability, performance, architecture, project-health, feasibility, alignment, coherence, testability, observability, robustness, portability, maintainability | 问题发现引擎 |
| extensibility | 机会发现引擎 |

同时选中两类 module → 先运行问题发现引擎（所有问题型 module），再运行机会发现引擎（extensibility）。

---

## 问题发现引擎（Discovery Engine）

适用 module：accuracy / clarity / consistency / security / hygiene / completeness / usability / freshness / compliance / reliability / performance / architecture / project-health / feasibility / alignment / coherence / testability / observability / robustness / portability / maintainability

> 使用**迭代-至-clean** 模式。每次迭代是一个完整的「发现→验证→[修复]」周期。重复迭代直到连续 clean 或达最大迭代，最后生成报告。

### 迭代主循环

```
for iteration = 1 to max_iter:

    ── 输出迭代开始标记 ──
    print "══ 迭代 {iteration}/{max_iter} 开始 (已确认: {累计confirmed}, clean: {consecutive_clean}) ══"

    ── 发现阶段（每轮覆盖全部 5 种视角） ──
    for round = 1 to discovery_rounds:
        → 必须 Read 文件（不可凭上下文记忆替代）
        → 从全部 5 种视角（数据流/错误路径/并发/契约/运维）逐一审查
        → 必须输出 SUMMARY 行
        → 追加本轮 CANDIDATE 到 candidates.jsonl

    ── 验证阶段 ──
    for round = 1 to validation_rounds:
        → 必须 Read 文件确认每个候选（不可仅凭发现阶段描述）
        → 必须输出 SUMMARY 行
    → 共识合并

    ── 修复阶段（仅 fix 模式且有 CONFIRMED） ──
    → 串行修复 → 独立复查 → 回归检查

    ── 迭代结算（gate） ──
    → Write state.json → Read state.json → 停止判断
    → 输出: "── 迭代 {iteration} 结束: 新确认 {n}, clean={consecutive_clean} ──"

    if 停止条件满足: break
```

**不可省略的环节**：
- 每次迭代必须完整执行发现和验证两个阶段，不可因"上轮已读过文件"而跳过
- 每个发现轮次必须用 Read 工具实际读取该组文件，不可仅从上下文回忆
- 每个发现轮次必须覆盖全部 5 种视角，不可只用其中几种
- 每个轮次必须产出 SUMMARY 行（即使 0 候选也要输出 `SUMMARY | 扫描 {N} 文件 | 候选 0 个`）
- 多次迭代的意义是用同样的全视角重新扫描抓遗漏，不是换视角

### 发现阶段（每迭代 N 轮）

每轮执行：

1. **分组**（首次迭代确定分组，后续迭代复用）：
   - 代码文件：按目录/模块分组，每组 10-30 文件，相关文件同组
   - 文档文件：按 5-8 篇一组分配
   - code-vs-docs 模式：代码和文档分别分组

2. **逐组 Read 文件并扫描**。每组必须用 Read 工具实际读取文件（确保视角切换后重新聚焦），然后按以下指令扫描：

```
【发现阶段指令】第 {round}/{N} 轮。

## 本轮视角（全部 5 种，逐一审查）
1. 数据流：输入如何流经系统，哪里变形、丢失、污染
2. 错误路径：异常分支、失败回退、资源清理
3. 并发：共享状态、race condition、顺序依赖
4. 契约：函数/模块边界的输入输出约定
5. 运维：可观测性、升级路径、故障恢复
{各 module 的「发现指令 → 专有关注点」作为补充}

## Module 配置
{当前 module 的：核心问题 + 检查项（按当前输入模式筛选）+ 严重度调整 + 专有关注点}
{多 module 时，逐个列出所有选中 module 的配置}

## 检查项目录（仅选中 module 在当前输入模式下激活的条目）
{check-catalog.md 对应段}

## 严重度标准
{severity-guidelines.md}

## 通用原则
- 简洁凝练：冗余/臃肿/废话也是 finding
- 结构化表达：能用表格/枚举/常量的不应散落 magic value

## 用户关注点
{若 config.user_context 非空则注入，否则省略此段}

## 待审查文件
{文件路径列表}
{code-vs-docs 模式时额外注明：## 对照源码/文档目录 {对应路径}}

## 输出格式（严格 pipe-delimited）
CANDIDATE | {severity} | {check-id} | {file}:{line} | {description} | {evidence}
SUMMARY | 扫描 {N} 文件 | 候选 {M} 个
```

3. **逐轮汇总**（每轮完成后立即执行，不可攒到所有轮次结束后批量处理）：
   - 提取本轮 CANDIDATE 行，按 `file:line + check-id` 去重
   - **追加写入** `candidates.jsonl`（不可覆盖，追加模式）
   - 输出本轮 SUMMARY：`SUMMARY | 迭代 {iter} 发现轮 {round} | 扫描 {N} 文件 | 新候选 {M} 个 | 累计候选 {total} 个`
   - 文档输入/code-vs-docs 且首次迭代首轮：合并 `link-checker.py` 输出（LNK-001/002）
   - link-checker.py JSON 转换规则：每个 issue → `CANDIDATE | {P0 if BROKEN_LINK, P1 if BROKEN_ANCHOR} | {LNK-001 or LNK-002} | {file}:{line} | {issue} | link-checker`

### 验证阶段（每迭代 M 轮）

每轮执行：

1. **分批**：~10 个候选一批，同文件同批
2. **逐批 Read 文件校验**。必须用 Read 工具实际读取相关源文件确认（不可仅凭发现阶段描述判断），按以下指令执行：

```
【验证阶段指令】第 {round}/{M} 轮。

## 任务
逐一校验以下候选：
1. 实际读文件确认（不能仅凭发现阶段描述）
2. 判定：CONFIRMED / REJECTED / DEFERRED
3. CONFIRMED 给出 P0-P3 分级 + 修复建议

## 严重度标准 + Module Overrides
{severity-guidelines.md + 各 module 的严重度调整}

## 验证要求
{各 module 的「验证指令」段内容，按当前输入模式筛选}

## 用户关注点
{若 config.user_context 非空则注入，否则省略此段}

## 候选清单
{CANDIDATE 行}

## 输出格式
CONFIRMED | {severity} | {check-id} | {file}:{line} | {description} | {fix-suggestion}
REJECTED  | {check-id} | {file}:{line} | {reason}
DEFERRED  | {check-id} | {file}:{line} | {context-needed}
SUMMARY | 校验 {N} | 确认 {c} | 误报 {r} | 待定 {d}
```

3. **逐轮汇总**（每轮完成后立即执行）：
   - 输出本轮 SUMMARY：`SUMMARY | 迭代 {iter} 验证轮 {round} | 校验 {N} | 确认 {c} | 误报 {r} | 待定 {d}`

4. **共识合并**（全部验证轮次完成后）：≥2 轮独立确认 = 真问题，严重度取多数决（平局取较高级别）

### 多 Module 合并处理

当选中多个 module 时，验证阶段完成后、报告生成前执行：

1. **跨 module 去重**：同一 `file:line` 被多个 module 标记 → 保留主归属 module 的严重度（见 check-catalog.md 跨 module 归属表），合并 check-id 列表
2. **根因关联**：同 `file:line` 不同 check-id 指向同一根因 → 合并为单个 finding，列出所有 check-id
3. **重复升级**：同一 finding 被 ≥3 个 module 独立标记为 P2 → 升级为 P1

### Fix 模式（仅文档输入 / code-vs-docs 文档侧）

当 `--fix=p0|p0+p1|all` 时，验证阶段产出 CONFIRMED findings 后：

1. **Fix-First 分类**：每个 CONFIRMED finding 按以下规则分类

| 分类 | 准入条件（3 条同时满足） | 动作 |
|------|----------------------|------|
| **AUTO-FIX** | (1) 修复只有唯一正确答案 (2) 影响范围仅当前文件当前位置 (3) 不改变语义/业务含义 | 直接修复 |
| **REPORT-ONLY** | 涉及设计决策、语义变更、跨文件影响、或不确定是否正确 | 仅记录到报告 |

AUTO-FIX 示例：格式修正、缺失标点、表格对齐、链接修复、章节编号修正
REPORT-ONLY 示例：内容重写、逻辑重组、缺失章节补写、接口定义修改

> 安全原则：拿不准时归入 REPORT-ONLY。保持确认后零交互。

2. **按严重度 P0→P3 串行修复**（仅 AUTO-FIX 项）
3. Edit 保持原文档格式
4. 修复原则：以源码为准改文档，不改代码
5. 修复涉及链接变更时重跑 link-checker.py
6. REPORT-ONLY 项在报告中标注建议修复方式但不自动修改
7. **每次修复完成后追加写入 `fixes.jsonl`**，格式：`{"check_id": "...", "file": "...", "line": ..., "before": "...", "after": "...", "classification": "AUTO-FIX|REPORT-ONLY", "status": "FIXED|FIX-FAILED|REPORT-ONLY", "timestamp": "ISO8601"}`

#### 独立复查

每个修复完成后，切换视角复查。执行指令：

```
【修复复查指令】

## 任务
验证以下修复是否正确——读修改后的文件，确认：
1. 原问题已修复
2. 未引入新问题
3. 文档格式/结构未被破坏

## 修复记录
{fix_record: file, line, before, after, check-id}

## 输出格式
PASS | {check-id} | {file}:{line}
FAIL | {check-id} | {file}:{line} | {失败原因}
SUMMARY | 复查 {N} | 通过 {p} | 失败 {f}
```

复查失败 → 回滚修复 + 标记 FIX-FAILED。

#### 回归检查

当一轮修复完成后（至少 1 个成功修复），执行回归扫描。执行指令：

```
【回归检查指令】

## 任务
扫描修复涉及的文件及周边文件，检查：
1. 修复是否引入新的不一致
2. 修复是否破坏交叉引用
3. 修复是否导致链接/锚点失效

## 本轮修复记录
{fix_records}

## 对照源码目录
{--src 路径}

## 输出格式
REGRESSION | {severity} | {check-id} | {file}:{line} | {description}
CLEAN | {file}
SUMMARY | 检查 {N} 文件 | 发现 {M} 个回归问题
```

发现回归问题 → 进入下一轮修复（最多 3 次迭代）。

### 迭代结算（每次迭代结束时强制执行，是下一步的前置条件）

1. **Write** state.json，更新以下字段：
   - `iteration_state.current_iteration` + 1
   - `iteration_state.iterations` 追加 `{iteration, confirmed, fixed, status: clean|has_findings}`
   - `cumulative` 各计数累加
   - `severity_counts` 更新
   - `updated_at` → 当前时间

2. **Read** state.json，提取（后续步骤必须使用此处读到的值，不可凭记忆）：
   - `current_iteration`
   - `consecutive_clean`（从 iterations 数组尾部计算连续 status=clean 的数量）

3. **停止判断**（输入来自第 2 步读取结果）：
   - `current_iteration >= min_iter` 且 `consecutive_clean >= clean_iter` → 停止
   - `current_iteration >= max_iter` → 强制停止，标注未收敛
   - 否则 → 进入下一次迭代

### Report-only vs Fix 模式小结

| 输入模式 | Report-only | Fix | 决定方 |
|---------|-------------|-----|--------|
| code | 固定 | — | 系统 |
| pr | 固定 | — | 系统 |
| docs | 可选 | 用户选择 `p0\|p0+p1\|all` | 用户（调用 3） |
| spec | 可选 | 用户选择 `p0\|p0+p1\|all`（仅改方案） | 用户（调用 3） |
| code-vs-docs | 代码侧固定 | 文档侧用户选择 | 用户（调用 3） |
| docs-vs-docs | 可选 | 用户选择（需指定修复哪一份） | 用户（调用 3） |
| code-vs-spec | 固定 | — | 系统 |
| change-vs-spec | 固定 | — | 系统 |

---

## 方案要点提取引擎（Spec Extraction，alignment 模块前置步骤）

适用输入模式：code-vs-spec, change-vs-spec。在标准发现阶段前执行一次。

### 目的

从方案文档中提取所有可验证的设计要点，生成结构化的 `spec-points.jsonl`，供后续发现阶段逐点比对。

### 执行指令

```
【方案要点提取指令】

## 任务
全面阅读方案文档，提取所有可验证的设计要点。每个要点必须是可在代码中验证的具体声明。

## 提取维度
1. 接口定义：函数/API/端点名称、入参、出参、错误码
2. 数据模型：类/表/结构体名称、字段列表、类型、约束
3. 架构决策：模块划分、分层归属、职责边界
4. 外部依赖：调用的服务/API、超时/降级要求
5. 配置项：配置键名、默认值、环境差异
6. 业务流程：正常流程步骤、分支条件、异常分支
7. 测试要求：测试场景、覆盖率目标、验收标准
8. 错误处理：异常类型、降级策略、兜底行为

## 方案文档
{spec_files}

## 输出格式（严格 pipe-delimited）
SPEC-POINT | {dimension} | {id} | {description} | {verifiable_criteria} | {source_location}
SUMMARY | 提取 {N} 个设计要点 | 维度分布: {breakdown}
```

### 产出

- 写入 `.check/spec-points.jsonl`
- 更新 `state.json` 的 `engines.alignment.spec_points_count`
- 零要点 → 记录错误，跳过 alignment 模块，不中止流程

### 后续使用

发现阶段的 alignment 模块从 `spec-points.jsonl` 逐点比对代码。每个 CANDIDATE 附带 spec-point ID 用于追溯。

CANDIDATE 格式扩展（alignment 专用）：
```
CANDIDATE | {severity} | {ALN-xxx} | {file}:{line} | {描述} | spec-point:{id} | {方案要求} → {实际实现}
```

---

## 变更范围处理（change-vs-spec 模式）

适用输入模式：change-vs-spec。在分组前执行。

### 变更来源解析

```
【变更范围解析指令】

## 任务
确定变更涉及的文件列表，作为审查范围。

## 变更来源
{change_source}

## 解析方式
1. git diff 模式：`git diff {base}...{head} --name-only` 获取变更文件列表
2. 文件列表模式：直接使用用户提供的文件路径列表
3. 未提交变更模式：`git diff --name-only` + `git diff --staged --name-only` 合并去重

## 输出格式
CHANGE-FILE | {path} | {change_type: added|modified|deleted}
SUMMARY | 变更 {N} 个文件 | 新增 {a} | 修改 {m} | 删除 {d}
```

### 范围限定规则

- 发现阶段的文件分组仅包含变更文件（+ 直接依赖文件作为上下文）
- alignment 模块仅验证变更涉及的方案要点（通过 spec-point 与变更文件的关联过滤）
- 删除文件：验证删除是否符合方案要求的重构/清理
- 新增文件：验证是否属于方案要求的新模块

---

## 机会发现引擎（Opportunity Engine）

适用 module：extensibility。始终 report-only。

使用 **Scan → Analyze → Recommend → Validate** 四阶段。

### Scan（扫描阶段）

**目的**：全面理解项目架构，产出模块地图。

1. **分组**：按目录/模块/包分组，逐组顺序扫描
2. **执行指令**：

```
【扫描阶段指令】

## 任务
全面阅读分配到的模块代码，理解其职责和扩展能力。

## 待分析模块
{模块路径和文件列表}

## 分析维度
1. 模块职责：对外提供什么能力？
2. 对外契约：接口/ABC/协议定义
3. 依赖关系：依赖谁？被谁依赖？
4. 扩展机制：hook/plugin/config/interface/注册表等
5. 功能边界：当前做了什么、不做什么

## 扩展模式识别（EXT-001~010）
- 接口抽象、注册表、事件/hook、配置驱动、策略模式、命令注册、Channel/Adapter、数据源抽象、中间件管道、模板/主题

## 用户关注点
{若 config.user_context 非空则注入，否则省略此段}

## 输出格式（严格 pipe-delimited）
MODULE | {path} | {职责一句话} | {对外契约} | {依赖模块列表} | {被依赖模块列表} | {已识别扩展点}
SUMMARY | 扫描 {N} 文件 | 识别 {M} 个模块
```

3. **汇总**：合并 MODULE 输出到 `.check/architecture-map.md`
4. **空结果处理**：0 个 MODULE → 记录错误，输出空报告，终止

### Analyze（分析阶段）

**目的**：基于模块地图分析功能缺口。

```
【分析阶段指令】

## 任务
基于模块地图，分析项目的功能缺口和拓展方向。

## 模块地图
{architecture-map.md 内容}

## 分析维度（EXT-011~015）
1. 核心功能边界（EXT-011）
2. 同类工具对比缺口（EXT-012）
3. 用户工作流断点（EXT-013）
4. 数据/输出复用机会（EXT-014）
5. 配置/定制化不足（EXT-015）

## 输出格式（严格 pipe-delimited）
GAP | {EXT-xxx} | {module} | {描述} | {影响面} | {潜在价值}
SUMMARY | 分析 {N} 个模块 | 发现 {M} 个功能缺口
```

汇总到 `.check/gaps.jsonl`。

### Recommend（推荐阶段）

**目的**：综合产出带优先级的拓展建议。

```
【推荐阶段指令】

## 任务
综合模块地图和功能缺口分析，输出带优先级的拓展建议。

## 模块地图
{architecture-map.md}

## 功能缺口清单
{gaps.jsonl}

## 评估维度
- difficulty（1-5）：实施难度
- value（1-5）：业务/技术价值
- score = value × (6 - difficulty)，范围 5-25

## 输出格式（严格 pipe-delimited）
OPPORTUNITY | {module} | {direction} | {difficulty:1-5} | {value:1-5} | {score} | {rationale} | {suggested-approach}
SUMMARY | 评估 {N} 个方向 | 推荐 {M} 个（score≥15）
```

按 score 降序写入 `.check/opportunities.jsonl`。

### Validate（验证阶段，V 轮）

**目的**：多轮交叉校验推荐，过滤不合理建议，分配 P0-P3。

轮数由档位决定：quick=1, standard=2, deep=3。

每轮执行：

1. **分批**：~8 个 OPPORTUNITY 一批
2. **执行指令**：

```
【拓展验证指令】第 {round}/{V} 轮。

## 任务
逐一校验以下拓展推荐：
1. 重新阅读相关模块代码，确认基于正确的架构理解
2. 验证 difficulty/value 评估合理性
3. 判定：CONFIRMED / REJECTED / DEFERRED
4. CONFIRMED 分配 P0-P3 严重度

## 模块地图
{architecture-map.md}

## 待验证推荐
{OPPORTUNITY 行}

## 输出格式（严格 pipe-delimited）
CONFIRMED | {severity} | {module} | {direction} | {difficulty} | {value} | {score} | {验证依据}
REJECTED  | {module} | {direction} | {驳回理由}
DEFERRED  | {module} | {direction} | {需要什么上下文}
SUMMARY | 校验 {N} | 确认 {c} | 驳回 {r} | 待定 {d}
```

3. **共识合并**：≥2 轮确认 = 保留，严重度多数决（平局取较高），score 保留原始值
4. **更新 opportunities.jsonl**：追加 severity 和 validation_status

### 生成报告

使用 `extensibility-template.md`。

---

## 项目体检编排

适用于项目体检模式。在标准引擎执行前，先进行项目扫描和子审查编排。

### 扫描与推荐

1. 扫描项目目录，按类型识别文件：代码（`.py`/`.js`/`.ts` 等）、文档（`.md`）、方案（`SKILL.md`/`design.md`/`spec.md` 等）、配置（`.json`/`.yaml`/`.toml`）
2. 推荐审查组合（如：方案审查 + 文档审查 + 代码审查 + 代码↔文档对齐）
3. 在调用 3 中由用户确认；修复策略同样由用户选择

### 执行顺序

方案审查 → 文档审查 → 代码审查（从规格到实现，后续审查可利用前序上下文）

### 结果合并

- 各子审查共享同一 `.check/` 目录
- `candidates.jsonl` 追加写入，id 按子审查前缀区分（`S-`=方案、`D-`=文档、`C-`=代码、`A-`=对齐）
- `state.json` 记录整体进度，`sub_checks` 数组追踪各子审查状态
- 报告合并为统一报告，按子审查分段展示

### 迭代配置

各子审查独立迭代（各自独立的连续 clean 计数和停止判断），但共享调用 3 选择的深度档位。

### sub_checks 状态更新

| 时机 | 状态变更 |
|------|---------|
| 开始执行某子审查前 | `sub_checks[i].status` → `"running"` |
| 该子审查停止条件满足后 | `sub_checks[i].status` → `"completed"` |
| 所有子审查完成后 | 进入报告生成阶段 |

---

## state.json 更新规则

> 迭代结算和报告生成中的 Write→Read 是 gate：下一步的输入依赖上一步写入的文件值，不可凭记忆替代。

| 时机 | 更新字段 | 执行方式 |
|------|---------|---------|
| 初始化完成 | `status`→`"running"`, `started_at`→`Bash(date -u +%Y-%m-%dT%H:%M:%SZ)`, `config`+`iteration_config`→实际参数 | Write |
| 每次迭代结束 | 见上方「迭代结算」——Write 后 Read 回来用于停止判断 | Write→Read gate |
| extensibility 各阶段 | `engines.opportunity` 对应字段更新 | Write |
| 异常发生 | `errors` 数组追加 `{phase, iteration, round, message, timestamp}` | Write |
| 报告生成前 | 见下方「报告生成」——Write 终态后 Read 回来填充模板 | Write→Read gate |
