# Module: extensibility（可扩展性）

## 核心问题

能不能加新功能？缺什么？——分析扩展能力、功能缺口、拓展方向。

## 适用输入模式

| 输入模式 | 激活检查项 |
|---------|-----------|
| code | EXT-001 ~ EXT-015 |
| docs | 不适用 |
| code-vs-docs | EXT-001 ~ EXT-015（仅审查代码侧） |

**特殊性**：本 module 不使用问题发现引擎（Discovery-Validation），改用**机会发现引擎**（Scan → Analyze → Recommend → Validate）。

---

## 检查项

### 代码输入

**EXT-001 ~ EXT-010（代码层扩展模式识别）**：

| ID | 机会类型 | 识别方法 |
|----|---------|---------|
| EXT-001 | 接口已抽象但仅一种实现 | ABC/Protocol + 单实现 |
| EXT-002 | Hook/事件机制已存在 | EventEmitter/signals |
| EXT-003 | 配置驱动行为 | 大量从 config 读取的分支 |
| EXT-004 | 插件/注册表模式 | register/plugin 字样 |
| EXT-005 | 策略模式已就位 | Strategy/Policy 对象 |
| EXT-006 | 命令/工具注册中心 | 统一命令分发 |
| EXT-007 | Channel/Adapter 模式 | 多通道共用核心 |
| EXT-008 | 数据源抽象 | Repository/DAO |
| EXT-009 | 中间件管道 | WSGI/Express middleware |
| EXT-010 | 模板/主题系统 | template 渲染层 |

**EXT-011 ~ EXT-015（功能层缺口分析）**：

| ID | 分析类型 | 方法 |
|----|---------|------|
| EXT-011 | 核心功能边界 | 梳理当前做了什么、边界在哪 |
| EXT-012 | 同类工具对比缺口 | 与同领域工具对比缺什么 |
| EXT-013 | 用户工作流断点 | 用户使用中哪些地方需手动补全 |
| EXT-014 | 数据/输出复用机会 | 产出物是否能被其他工具消费 |
| EXT-015 | 配置/定制化不足 | 硬编码行为是否应可配置 |

### 文档输入

不适用。扩展性是代码结构特性。

### 交叉输入（code-vs-docs）

仅审查代码侧。

---

## 严重度分级（机会发现引擎专用）

P0-P3 标记**推荐紧迫度**，非问题严重度：

| 级别 | 含义 | 对应场景 |
|------|------|---------|
| P0 | 核心缺失 | 不做会严重限制项目价值；用户核心工作流有明显断裂 |
| P1 | 重要缺口 | 显著影响用户体验或竞争力；同类工具普遍已有 |
| P2 | 排期实施 | 有价值但非紧迫；改善特定场景 |
| P3 | 锦上添花 | 按需考虑；成本可能高于收益 |

### 综合评分

每个推荐附 difficulty(1-5)、value(1-5)、score = value × (6 - difficulty)：

| score 范围 | 含义 |
|-----------|------|
| 20-25 | 强烈推荐——高价值 + 低成本 |
| 15-19 | 推荐——需权衡 |
| 10-14 | 值得考虑——取决于优先级 |
| 5-9 | 暂不建议——成本 vs 收益不划算 |

> severity 和 score 独立评估。P0 可以 score=8（必须做但难度大），P3 可以 score=20（锦上添花但成本极低）。

---

## 输出格式

### Scan 阶段

```
MODULE | {path} | {职责一句话} | {对外契约} | {依赖模块列表} | {被依赖模块列表} | {已识别扩展点}
```

### Analyze 阶段

```
GAP | {EXT-xxx} | {module} | {描述} | {影响面} | {潜在价值}
```

### Recommend 阶段

```
OPPORTUNITY | {module} | {direction} | {difficulty:1-5} | {value:1-5} | {score} | {rationale} | {suggested-approach}
```

### Validate 阶段

```
CONFIRMED | {severity} | {module} | {direction} | {difficulty} | {value} | {score} | {验证依据}
REJECTED  | {module} | {direction} | {驳回理由}
DEFERRED  | {module} | {direction} | {需要什么上下文}
SUMMARY | 校验 {N} | 确认 {c} | 驳回 {r} | 待定 {d}
```

---

## 四阶段流程指令

### Scan（扫描）

按模块/包分组，每组：
1. 读取所有文件
2. 理解职责：对外提供什么？依赖谁？被谁依赖？
3. 识别扩展点（EXT-001~010）
4. 识别功能边界（EXT-011）

**视角轮换**：
- 第 1 轮：全面阅读，识别接口/hook/config/plugin/策略/命令/adapter/数据源/中间件/模板等模式
- 第 2 轮（≥ standard）：换角度——新增同类能力需改几个文件？改动越集中扩展性越好

### Analyze（分析）

输入：architecture-map.md。任务：
1. 分析核心功能边界和天花板（EXT-011）
2. 与同领域工具对比，找缺失功能（EXT-012）
3. 梳理用户工作流中的手动补全环节（EXT-013）
4. 评估产出物的复用/集成潜力（EXT-014）
5. 找出应可配置但被硬编码的行为（EXT-015）

**分析原则**：
- 功能缺口要具体——不能只说"缺少 X"，要说"当用户做 Y 时需手动 Z"
- 同类对比要有依据——列出具体的同类工具名
- 工作流断点从用户视角——不是代码视角
- 复用机会要有场景——"X 工具可以读取这个输出来做 Y"

### Recommend（推荐）

输入：architecture-map.md + gaps.jsonl。任务：
1. 对每个扩展机会评估 difficulty/value/score
2. 给出具体实施路径和前置条件
3. 标注风险点

**评估原则**：
- difficulty 必须量化——需修改的文件数、是否涉及数据迁移、是否破坏兼容性
- value 要结合项目定位——解决用户实际问题价值高
- 建议方向要具体——不能只说"可以加新 channel"
- 避免推荐烂方向

### Validate（验证）

每轮：
1. 重新阅读模块代码，确认推荐基于正确的架构理解
2. 验证 difficulty/value 评估合理性
3. 判定 CONFIRMED / REJECTED / DEFERRED
4. 为 CONFIRMED 分配 P0-P3

**验证原则**：
- 必须重新读代码——不能仅凭 rationale 判断
- difficulty 验证要量化——Glob/Grep 确认需改的文件数
- value 验证要有用户视角——真实用户会因此受益吗？
- severity 与 score 独立评估
- 存疑时 DEFERRED 而非 REJECTED

---

## 报告侧重

使用 **extensibility-template.md**。报告包含：
1. 架构概览（一段话）
2. 模块地图（表格 + ASCII 依赖图）
3. 功能缺口分析
4. 扩展机会排行榜（先按 severity 分组，同组按 score 降序）
5. 验证结果摘要
6. Top 5 详细推荐（实施路径、difficulty/value、预估工作量、风险）
7. 低价值机会清单
