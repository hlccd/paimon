# Paimon 分期实施方案

> 隶属：[神圣规划](aimon.md) · [待办项](todo.md)
>
> 本文档规划从 **fairy**（三省六部架构）向 **paimon**（神圣规划架构）的分期迁移路线。
> 核心原则：**能复用就复用，需重构就重构，必须新建才新建。**

---

## 迁移映射总表

> fairy → paimon 各模块对应关系与迁移策略一览。

| fairy 模块 | paimon 模块 | 迁移策略 |
|---|---|---|
| `fairy/config.py` | 基础配置 | **直接复用**，扩展 Gnosis / Leyline 等新字段 |
| `fairy/log.py` | 日志 | **直接复用** |
| `fairy/template.py` | 模板引擎 | **直接复用** |
| `fairy/channels/*` | 派蒙·频道层 | **直接复用**，调整回调接口对接派蒙 |
| `fairy/llm/*` | 神之心 (Gnosis) | **重构**：Provider 复用，外包资源池调度层 |
| `fairy/tools/*` | 工具层 | **直接复用**，增加 `sensitivity` 字段 |
| `fairy/skills/*` + `skills/` | 天使体系 + 冰神 | **复用** parser/registry，新增天使调度器 |
| `fairy/session.py` | 会话管理 | **复用**，归入时执管辖 |
| `fairy/knowledge/*` | 世界树 (Irminsul) | **复用**核心，扩展为全局存储中心 |
| `fairy/scheduler/*` | 三月女神 (March) | **复用**核心调度，扩展推送响铃 |
| `fairy/workflow/db.py` | 世界树·存储 | **重构** schema，适配新数据模型 |
| `fairy/workflow/engine.py` | 四影编排 | **重大重构**：状态机 → DAG 编排 |
| `fairy/workflow/task.py` | 生执·任务模型 | **重构**：单线任务 → DAG 子任务图 |
| `fairy/workflow/store.py` | 世界树·任务持久化 | **重构**，融入世界树 |
| `fairy/workflow/imperial.py` | 权限体系 | **拆分**：用户确认迁入派蒙 + 死执 |
| `fairy/agents/zhongshu.py` | 草神 (Nahida) 部分能力 | **迁移**：方案起草 → 草神 |
| `fairy/agents/menxia.py` | 死执 (Jonova) | **迁移 + 增强**：安全审查 → 死执 |
| `fairy/agents/shangshu.py` | 空执 (Asmoday) | **迁移 + 重构**：分发 → 动态路由 |
| `fairy/agents/executor.py` | 天使直执行路径 | **迁移**：简单任务执行 → 天使 |
| `fairy/agents/departments/bing.py` | 火神 (Mavuika) | **迁移**：shell/code 执行 |
| `fairy/agents/departments/gong.py` | 风神 (Venti) | **迁移**：信息搜集 + 新闻 |
| `fairy/agents/departments/hu.py` | 岩神 (Zhongli) | **迁移**：理财 / 红利股 |
| `fairy/agents/departments/li.py` | 冰神 (Tsaritsa) | **迁移**：skill 管理 → skill 生态 |
| `fairy/agents/departments/xing.py` | 水神 (Furina) 部分 | **迁移**：质量评审 |
| `fairy/agents/departments/li_official.py` | 时执 (Istaroth) 部分 | **迁移**：归档 |
| `fairy/persona.py` | 派蒙人格 | **重写**：fairy 人格 → 派蒙人格 |
| `fairy/bootstrap.py` | 启动器 | **重写**：适配新架构 |
| `fairy/state.py` | 运行时状态 | **重写**：适配新组件拓扑 |
| `fairy/diagnostics.py` | 三月·自检 | **迁移**：诊断能力迁入三月 |
| `fairy/application/chat.py` | 派蒙·对话核心 | **重构**：抽离意图分类 + 路由逻辑 |
| `fairy/application/commands.py` | 派蒙·指令系统 | **复用 + 调整**：`/workflow` → `/task` |

---

## 分期实施

### Phase 0：项目脚手架

> **目标**：搭建可运行的空壳项目，所有后续阶段都在此骨架上叠加。
> **产出**：`python -m paimon` 能启动，打印日志后正常退出。

| 任务 | 来源 | 说明 |
|---|---|---|
| 项目结构 `paimon/` 包 | 新建 | `__init__.py`、`__main__.py` |
| `pyproject.toml` | 复用 fairy 的，改名改依赖 | 入口 `paimon = "main:entry"` |
| `main.py` | 复用 fairy | 精简为最小启动 |
| `paimon/config.py` | **直接复制** fairy/config.py | 改类名，先保留所有字段 |
| `paimon/log.py` | **直接复制** fairy/log.py | 改 logger name |
| `paimon/template.py` | **直接复制** fairy/template.py | 无需改动 |
| `.env.example` | 复用 fairy | 补注释 |
| `templates/` | 复用 fairy/templates | 后续改人格内容 |

**验收标准**：`pytest` 能跑通 import 级别的冒烟测试。

---

### Phase 1：基础设施层 (Foundation)

> **目标**：建立四大全局支撑组件，供上层所有模块使用。
> **依赖**：Phase 0

#### 1A. 地脉 (Leyline) — 全局事件总线

| 任务 | 说明 |
|---|---|
| 定义事件协议 | `Event` dataclass：`type`, `source`, `payload`, `timestamp` |
| 实现总线 | **Phase 1 先用 `asyncio.Queue`**（单进程，零依赖）；预留 Redis Stream 接口 |
| 订阅/发布 API | `leyline.publish(event)` / `leyline.subscribe(event_type, handler)` |
| 通配订阅 | `leyline.subscribe("*", handler)` 用于审计 / 日志 |

> fairy 中不存在事件总线，此为纯新建。

#### 1B. 世界树 (Irminsul) — 持久化存储中心

| 任务 | 来源 | 说明 |
|---|---|---|
| 知识库存储 | **复用** fairy/knowledge/ | `detector.py`, `loader.py`, `maintenance.py` 原样迁入 |
| 任务存储 | **重构** fairy/workflow/db.py + store.py | 新 schema：tasks, subtasks(DAG), flow_history, token_usage |
| Skill 生态注册表 | **新建** | skill manifest 存储（名称、sensitivity、授权状态） |
| 用户授权记录 | **新建** | 永久授权条目（按 skill/工具粒度），对应 permissions.md |
| 缓存层 | **新建** | 内存 LRU + SQLite 双层，供派蒙/死执读权限画像 |

> 世界树只存储、不推送。需要推送时通过地脉发事件。

#### 1C. 神之心 (Gnosis) — LLM 资源池

| 任务 | 来源 | 说明 |
|---|---|---|
| Provider 抽象 | **直接复用** fairy/llm/base.py | `Provider` ABC, `StreamChunk`, `ToolCallFragment` |
| Anthropic Provider | **直接复用** fairy/llm/anthropic.py | 含 529 重试逻辑 |
| OpenAI Provider | **直接复用** fairy/llm/openai.py | |
| Model 封装 | **复用** fairy/llm/model.py | 上下文压缩、工具循环、token 估算 |
| 资源池调度 | **新建** | 浅层/深层分层；请求队列；非抢占式调度 |
| 分层策略 | **新建** | 浅层：闲聊/意图分类；深层：方案起草/代码生成/安全审查 |

> fairy 的 LLM 层是单 Model 实例，paimon 需要池化管理多个并发请求。

#### 1D. 原石 (Primogem) — Token + 费用统计

| 任务 | 来源 | 说明 |
|---|---|---|
| 统计模型 | **复用** fairy/workflow/db.py 中 `token_usage` 表 | 扩展标签维度 |
| 多维度标签 | **新建** | `module`（哪个模块）、`purpose`（意图分类/方案起草/...）、`session_id`、`timestamp` |
| 记录 API | **新建** | `primogem.record(module, purpose, input_tokens, output_tokens, model, cost)` |
| 查询 API | **新建** | 按维度聚合查询，供三月面板 / 岩神使用 |

> fairy 的 token tracking 散在 `model.py` 和 `db.py` 中，paimon 收口到原石。

**Phase 1 验收**：四个基础组件各自有单元测试通过；地脉能 pub/sub；世界树能读写知识+任务；神之心能发 LLM 请求；原石能记录+查询。

---

### Phase 2：入口层 (Paimon + Channels)

> **目标**：用户能通过任一 channel 与派蒙对话（闲聊 + 简单命令），系统可用。
> **依赖**：Phase 1

#### 2A. 频道层

| 任务 | 来源 | 说明 |
|---|---|---|
| Channel ABC | **直接复用** fairy/channels/base.py | |
| WebUI Channel | **直接复用** fairy/channels/webui/ | 调整 `_handle_message()` 对接派蒙 |
| Telegram Channel | **直接复用** fairy/channels/telegram/ | 同上 |
| QQ Channel | **直接复用** fairy/channels/qq/ | 同上 |
| 回调统一 | **重构** | 所有 channel 的消息统一交给 `paimon.receive(msg)` |

#### 2B. 派蒙核心

| 任务 | 来源 | 说明 |
|---|---|---|
| 会话管理 | **复用** fairy/session.py | 改命名空间 |
| 意图粗分类 | **新建** | 三分类：闲聊 / 简单任务 / 复杂任务（关键词 + 浅层 LLM） |
| 闲聊响应 | **复用** fairy/application/chat.py 核心循环 | 走浅层 Gnosis |
| 指令系统 | **复用** fairy/application/commands.py | `/new`, `/sessions` 等保留；`/workflow` → `/task` |
| 人格模板 | **重写** | 派蒙人格（fairy.t → paimon.t） |
| 轻量安全 | **新建** | 关键词过滤 + 格式拦截（位于意图分类前） |
| 启动器 | **重写** bootstrap.py | 按新组件拓扑组装 |
| 运行时状态 | **重写** state.py | 持有所有组件引用 |

**Phase 2 验收**：三个 channel 均可与派蒙闲聊；`/new`、`/sessions` 等基础指令正常；浅层 LLM 回复流畅。

---

### Phase 3：天使体系 (Angel System — Track 1)

> **目标**：简单任务走天使路径闭环（1~2 个 skill 即可完成）。
> **依赖**：Phase 2

| 任务 | 来源 | 说明 |
|---|---|---|
| 工具注册 | **直接复用** fairy/tools/ 全套 | 11 个内置工具 + external 加载 |
| Skill 解析器 | **直接复用** fairy/skills/parser.py | SKILL.md YAML 前置 + 正文 |
| Skill 注册表 | **复用** fairy/skills/registry.py | 扫描 `~/.paimon/skills/` |
| 天使调度器 | **新建** | 派蒙判定简单任务 → 查匹配 skill → 注入 context → 调 Gnosis 执行 → 30s 超时 |
| 天使权限检查 | **新建** | 调用前查世界树权限画像；敏感操作询问用户 |
| 魔女会桥 | **新建** | 天使失败/超时/判定复杂 → 发地脉事件 → 转入四影路径（Phase 4 实装） |
| 现有 skills 迁移 | **直接复用** skills/bili, skills/xhs, skills/web, skills/dividend-tracker | 复制到 paimon 项目 |

**Phase 3 验收**：`/bili <url>` 等 skill 通过天使路径正常执行；敏感操作有权限询问；超时能正确报错。

---

### Phase 4：四影骨架 (Four Shades — Track 2)

> **目标**：复杂任务通过四影流水线完成编排、路由、执行、收尾。
> **依赖**：Phase 3（魔女会桥需要四影接收端）

#### 4A. 死执 · Jonova（安全审查）

| 任务 | 来源 | 说明 |
|---|---|---|
| 危险模式检测 | **迁移** fairy/agents/menxia.py 的规则库 | 命令注入 / 越权 / 危险操作模式 |
| LLM 深度审查 | **复用** menxia 的 LLM 审查逻辑 | 走深层 Gnosis |
| DAG 批量权限扫描 | **新建** | 扫描生执产出的 DAG，收集所有敏感操作，一次性询问用户 |
| 新 skill 审查 | **新建** | 运行时新增 skill 的 manifest 合规检查 |
| 审查结果通信 | 通过地脉 | 发事件通知生执（通过/驳回） |

#### 4B. 生执 · Naberius（任务编排）

| 任务 | 来源 | 说明 |
|---|---|---|
| DAG 任务模型 | **重构** fairy/workflow/task.py | 子任务带依赖关系（`depends_on` 列表），非线性 |
| DAG 编排器 | **重构** fairy/agents/zhongshu.py 的方案生成 | LLM 生成 DAG 结构（JSON schema 约束）|
| 静态依赖环检测 | **新建** | 拓扑排序检测环；有环则要求 LLM 重新拆分 |
| 多轮迭代控制 | **新建** | 轮次上限、收敛判定（水神通过 = 收敛） |
| 失败回滚 | **新建** | Phase 4 先用简单 saga 补偿（标记失败 + 通知），后续迭代增强 |
| 持久化 | 存入世界树 | DAG 结构 + 执行状态 |

#### 4C. 空执 · Asmoday（动态路由）

| 任务 | 来源 | 说明 |
|---|---|---|
| 七神注册表 | **新建** | 每个 Archon 声明自己的能力标签 + 接口 |
| 动态路由 | **重构** fairy/agents/shangshu.py | 根据子任务标签匹配七神（取代关键词硬编码） |
| 故障切换 | **新建** | 首选七神不可用 → 降级备选（如雷神忙 → 草神代写简单代码） |
| 负载感知 | **新建** | 查询 Gnosis 当前负载，避免同时给太多七神分配深层 LLM |

#### 4D. 时执 · Istaroth（归档审计）

| 任务 | 来源 | 说明 |
|---|---|---|
| 活跃压缩 | **复用** fairy/llm/model.py 的上下文压缩 | 独立为时执能力 |
| 会话生命周期 | **新建** | 活跃 → 热缓存 → 冷归档 → 过期删除 |
| 最终归档 | **部分迁移** fairy/agents/departments/li_official.py | 执行完成后存入世界树 |
| 审计复盘 | **新建** | 记录完整执行链路（四影调度顺序 + 七神产出 + 耗时 + token） |

**Phase 4 验收**：`/task 帮我分析一下XXX` 能走完 死执→生执→空执→(暂用占位七神)→时执 全流程；DAG 拆分正确；权限批量询问正常；归档可查。

---

### Phase 5：七神能力层 (Seven Archons)

> **目标**：七个业务能力模块上线，复杂任务真正可执行。
> **依赖**：Phase 4
>
> 七神之间无直接依赖，可**并行开发**。按业务优先级排序。

#### 5A. 火神 · Mavuika（shell/code 执行）— 优先级 P0

| 任务 | 来源 | 说明 |
|---|---|---|
| PTY 执行引擎 | **直接迁移** fairy/tools/builtin/sys.py | exec/exec_status/exec_write/exec_signal |
| 执行沙箱策略 | **新建** | 基于死执审查结果决定沙箱级别 |
| 技术性重试 | **新建** | 命令失败自动分析 + 最多 N 次重试 |

> 火神是最核心的执行能力，几乎所有实际操作最终都需要她。

#### 5B. 草神 · Nahida（推理 + 知识）— 优先级 P0

| 任务 | 来源 | 说明 |
|---|---|---|
| 方案起草 | **迁移** fairy/agents/zhongshu.py | LLM 生成方案 + 技术文档 |
| 意图深度推理 | **新建** | 粗分类不够时，草神做深度意图分析 |
| 知识整合 | **复用** fairy/knowledge/loader.py | 动态知识加载 |
| Prompt 调优 | **新建** | 根据用户反馈调整各模块 prompt |
| 偏好管理 | **复用** fairy/knowledge/detector.py | 个人偏好提取 + 存世界树 |

#### 5C. 雷神 · Raiden（代码生成）— 优先级 P1

| 任务 | 来源 | 说明 |
|---|---|---|
| 代码生成 | **新建**（fairy 中无独立代码生成模块） | 深层 Gnosis 生成代码 |
| 自检环节 | **新建** | 生成后自动审查（语法检查 + 逻辑复核） |
| 与火神协作 | **新建** | 生成代码 → 火神执行测试 → 结果反馈 → 迭代修改 |

#### 5D. 水神 · Furina（评审 + 游戏）— 优先级 P1

| 任务 | 来源 | 说明 |
|---|---|---|
| 成品评审 | **迁移** fairy/agents/departments/xing.py | 代码/方案/文档的质量评审 |
| 多轮挑刺 | **新建** | 作为生执多轮迭代的收敛判定者（水神通过 = 本轮结束）|
| 游戏信息 | **新建** | 游戏攻略 / 数据查询（后续迭代） |

#### 5E. 风神 · Venti（新闻采集）— 优先级 P2

| 任务 | 来源 | 说明 |
|---|---|---|
| 信息搜集 | **迁移** fairy/agents/departments/gong.py | web 搜索 + 内容抓取 |
| 新闻推送整理 | **迁移** fairy/agents/departments/li_official.py 部分 | 新闻跟踪 + 内容格式化 |
| 推送内容产出 | **新建** | 整理好内容 → 交三月响铃 → 派蒙送达 |

#### 5F. 岩神 · Zhongli（理财）— 优先级 P2

| 任务 | 来源 | 说明 |
|---|---|---|
| 红利股跟踪 | **直接迁移** fairy/agents/departments/hu.py + skills/dividend-tracker | |
| 资产管理 | **新建** | 资产概览 / 退休规划（后续迭代） |
| 推送内容产出 | **新建** | 分红提醒 / 股价异动 → 交三月响铃 |

#### 5G. 冰神 · Tsaritsa（skill 生态）— 优先级 P2

| 任务 | 来源 | 说明 |
|---|---|---|
| Skill 生态管理 | **迁移** fairy/agents/departments/li.py | 发现 + 注册 |
| 世界树写入 | **新建** | 唯一 skill 注册写入者 |
| AI 自举生成 | **新建**（实验性） | LLM 自动生成新 skill（后续迭代） |

**Phase 5 验收**：
- P0（火神+草神）：`/task 帮我写个Python脚本` 能走通 草神起草→雷神写码→水神评审→火神执行 全链路
- P1（雷神+水神）：代码生成+评审的多轮迭代正常收敛
- P2（风神+岩神+冰神）：新闻/理财/skill 管理各自独立可用

---

### Phase 6：三月女神 (March — Guardian Daemon)

> **目标**：守护进程 + 定时调度 + 推送响铃 + 自检体系上线。
> **依赖**：Phase 5（推送链路需要七神作为数据收集者）

| 任务 | 来源 | 说明 |
|---|---|---|
| 定时调度核心 | **直接复用** fairy/scheduler/ | cron/interval/once 三种触发 |
| 推送响铃（定时） | **新建** | 三月 cron 到点 → 通知数据收集者整理 → 派蒙送达 |
| 推送响铃（事件） | **新建** | 数据收集者请求三月响铃 → 派蒙送达 |
| 推送积压 | **新建** | 派蒙挂掉时暂存；恢复后补发 |
| 自检系统 | **迁移** fairy/diagnostics.py | 定期检查各组件健康状态 |
| 守护进程 | **新建** | 监控派蒙存活；异常拉起 |
| 任务观测面板数据 | **新建** | 收集运行状态 → 供 WebUI 观测面板展示 |

**Phase 6 验收**：定时推送正常送达；风神新闻 / 岩神股价提醒能通过三月→派蒙送到用户；自检能检测并报告异常组件。

---

### Phase 7：权限体系完善 + WebUI 面板

> **目标**：权限系统闭环 + WebUI 面板可用。
> **依赖**：Phase 6

#### 7A. 权限体系

| 任务 | 说明 |
|---|---|
| 永久授权存储 | 世界树中的授权条目 schema 落地 |
| 天使路径权限 | 派蒙单项询问 + 永久关键词识别 + 写世界树 |
| 四影路径权限 | 死执 DAG 批量扫描 + 一次性打包询问 |
| 授权缓存同步 | 草神面板撤销 → 地脉事件 → 派蒙/死执缓存失效 |

#### 7B. WebUI 面板

| 面板 | 来源 | 说明 |
|---|---|---|
| 聊天面板 | **复用** fairy/channels/webui/static_html.py | 改派蒙风格 |
| 观测面板 | **重构** fairy/channels/webui/palace_html.py | 三月数据源 |
| 知识/偏好面板 | **新建** | 草神提供数据 |
| 理财面板 | **新建** | 岩神提供数据 |
| 游戏面板 | **新建** | 水神提供数据（后续） |
| 插件面板 | **新建** | 冰神提供数据 |
| 信息流面板 | **新建** | 风神提供数据 |

**Phase 7 验收**：WebUI 能查看/撤销永久授权；各面板有数据展示。

---

### Phase 8：高级特性 + 打磨

> **目标**：AI 自举、地脉升级、全链路打磨。
> **依赖**：Phase 7

| 任务 | 说明 |
|---|---|
| 冰神 AI 自举 | LLM 自动生成 skill → 死执审查 → 上线 |
| 地脉升级 | 评估是否需要 Redis Stream（取决于并发量） |
| 时执压缩优化 | 调研主流上下文压缩方案，优化阈值 |
| 生执回滚增强 | saga 补偿 → 状态快照（按需） |
| 异常日志设施 | 独立日志落盘方案（不入世界树） |
| 全链路测试 | contract + smoke + integration 测试套件 |
| fairy 退役 | 确认 paimon 功能对齐后，fairy 进入只读归档 |

---

## 项目目录规划

```
paimon/
├── main.py                         # 入口
├── pyproject.toml
├── .env.example
├── paimon/                         # 核心包
│   ├── __init__.py
│   ├── config.py                   # 全局配置
│   ├── log.py                      # 日志
│   ├── template.py                 # 模板引擎
│   ├── state.py                    # 运行时状态
│   ├── bootstrap.py                # 启动组装
│   │
│   ├── core/                       # 派蒙入口
│   │   ├── paimon.py               # 统一入口 (receive / respond / route)
│   │   ├── intent.py               # 意图粗分类
│   │   ├── safety.py               # 轻量安全过滤
│   │   ├── persona.py              # 人格模板
│   │   └── commands.py             # 指令系统
│   │
│   ├── channels/                   # 频道层（复用 fairy）
│   │   ├── base.py
│   │   ├── webui/
│   │   ├── telegram/
│   │   └── qq/
│   │
│   ├── angels/                     # 天使体系
│   │   ├── dispatcher.py           # 天使调度器
│   │   └── witch_assembly.py       # 魔女会兜底桥
│   │
│   ├── shades/                     # 四影
│   │   ├── jonova.py               # 死执·安全审查
│   │   ├── naberius.py             # 生执·DAG 编排
│   │   ├── asmoday.py              # 空执·动态路由
│   │   ├── istaroth.py             # 时执·归档审计
│   │   └── pipeline.py             # 四影流水线编排
│   │
│   ├── archons/                    # 七神
│   │   ├── base.py                 # Archon ABC
│   │   ├── nahida.py               # 草神·推理知识
│   │   ├── mavuika.py              # 火神·执行
│   │   ├── raiden.py               # 雷神·代码生成
│   │   ├── furina.py               # 水神·评审
│   │   ├── venti.py                # 风神·新闻
│   │   ├── zhongli.py              # 岩神·理财
│   │   └── tsaritsa.py             # 冰神·skill 生态
│   │
│   ├── foundation/                 # 基础设施
│   │   ├── leyline.py              # 地脉·事件总线
│   │   ├── irminsul/               # 世界树·存储
│   │   │   ├── __init__.py
│   │   │   ├── db.py               # SQLite 操作
│   │   │   ├── knowledge.py        # 知识存储
│   │   │   ├── tasks.py            # 任务存储
│   │   │   ├── skills.py           # Skill 注册表
│   │   │   └── permissions.py      # 授权记录
│   │   ├── gnosis.py               # 神之心·LLM 资源池
│   │   ├── primogem.py             # 原石·Token 统计
│   │   └── march/                  # 三月女神
│   │       ├── __init__.py
│   │       ├── scheduler.py        # 定时调度
│   │       ├── bell.py             # 推送响铃
│   │       ├── guardian.py         # 守护进程
│   │       └── healthcheck.py      # 自检
│   │
│   ├── llm/                        # LLM Provider（复用 fairy）
│   │   ├── base.py
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   └── model.py
│   │
│   ├── tools/                      # 工具层（复用 fairy）
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── external.py
│   │   └── builtin/
│   │
│   └── skills/                     # Skill 解析（复用 fairy）
│       ├── parser.py
│       └── registry.py
│
├── skills/                         # Skill 插件（复用 fairy）
├── tools/                          # 外部工具脚本
├── templates/                      # 系统 prompt 模板
├── knowledge/                      # 知识库数据
├── docs/                           # 架构文档（已有）
└── test/                           # 测试套件
```

---

## 里程碑与时间参考

| 里程碑 | Phases | 核心交付 |
|---|---|---|
| **M0 — 骨架可运行** | Phase 0 | 空壳启动 + 配置加载 |
| **M1 — 基础设施就绪** | Phase 1 | 地脉 + 世界树 + 神之心 + 原石 |
| **M2 — 闲聊可用** | Phase 2 | 三 channel 对话 + 闲聊回复 |
| **M3 — 简单任务闭环** | Phase 3 | 天使路径跑通，skill 可用 |
| **M4 — 复杂任务骨架** | Phase 4 | 四影流水线跑通（占位七神） |
| **M5 — 全能力上线** | Phase 5 | 七神上线，复杂任务真正可执行 |
| **M6 — 守护推送** | Phase 6 | 三月守护 + 定时推送 + 自检 |
| **M7 — 面板权限** | Phase 7 | WebUI 面板 + 权限闭环 |
| **M8 — fairy 退役** | Phase 8 | 高级特性 + 全面测试 + fairy 归档 |

---

> 每个 Phase 完成后应当**可独立验收**、可运行，不依赖后续 Phase 才能工作。
> Phase 0~3 为核心路径，优先交付；Phase 4~5 为能力扩展；Phase 6~8 为打磨完善。
