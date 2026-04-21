# Paimon 分期实施方案

> 隶属：[神圣规划](aimon.md) · [待办项](todo.md)
>
> 本文档规划从 **fairy**（三省六部架构）向 **paimon**（神圣规划架构）的分期迁移路线。
> 核心原则：**参考 fairy 实现重写，而非直接复制或简单改名；每个核心类必须有单元测试覆盖。**
>
> 迁移策略说明：
> - **参考重写**：阅读 fairy 源码理解逻辑，在 paimon 中按新架构重新实现，不做文件级复制
> - **重构**：参考 fairy 实现，但需大幅调整设计（如接口变更、模型变化）
> - **新建**：fairy 中无对应模块，从零实现
> - **测试要求**：每个核心类/模块必须附带单元测试，由三月（March）模块统一管理测试基础设施

---

## 迁移映射总表

> fairy → paimon 各模块对应关系与迁移策略一览。

| fairy 模块 | paimon 模块 | 迁移策略 |
|---|---|---|
| `fairy/config.py` | 基础配置 | **参考重写**，按新架构设计配置结构，扩展 Gnosis / Leyline 等新字段 |
| `fairy/log.py` | 日志 | **参考重写**，适配新项目命名与结构 |
| `fairy/template.py` | 模板引擎 | **参考重写**，理解渲染逻辑后重新实现 |
| `fairy/channels/*` | 派蒙·频道层 | **参考重写**，理解协议逻辑后按新接口重新实现 |
| `fairy/llm/*` | 神之心 (Gnosis) | **重构**：参考 Provider 设计，重写并新增资源池调度层 |
| `fairy/tools/*` | 工具层 | **参考重写**，增加 `sensitivity` 字段 |
| `fairy/skills/*` + `skills/` | 天使体系 + 冰神 | **参考重写** parser/registry，新增天使调度器 |
| `fairy/session.py` | 会话管理 | **参考重写**，归入时执管辖 |
| `fairy/knowledge/*` | 世界树 (Irminsul) | **参考重写**核心逻辑，扩展为全局存储中心 |
| `fairy/scheduler/*` | 三月女神 (March) | **参考重写**调度核心，扩展推送响铃 |
| `fairy/workflow/db.py` | 世界树·存储 | **重构** schema，适配新数据模型 |
| `fairy/workflow/engine.py` | 四影编排 | **重构**：参考状态机设计，重写为 DAG 编排 |
| `fairy/workflow/task.py` | 生执·任务模型 | **重构**：参考任务模型，重写为 DAG 子任务图 |
| `fairy/workflow/store.py` | 世界树·任务持久化 | **重构**，融入世界树 |
| `fairy/workflow/imperial.py` | 权限体系 | **重构**：用户确认迁入派蒙 + 死执 |
| `fairy/agents/zhongshu.py` | 草神 (Nahida) 部分能力 | **参考重写**：理解方案起草逻辑后在草神中重新实现 |
| `fairy/agents/menxia.py` | 死执 (Jonova) | **参考重写 + 增强**：理解审查规则后重新实现 |
| `fairy/agents/shangshu.py` | 空执 (Asmoday) | **参考重写 + 重构**：理解分发逻辑后重写为动态路由 |
| `fairy/agents/executor.py` | 天使直执行路径 | **参考重写**：理解执行逻辑后在天使中重新实现 |
| `fairy/agents/departments/bing.py` | 火神 (Mavuika) | **参考重写**：理解 shell/code 执行后重新实现 |
| `fairy/agents/departments/gong.py` | 风神 (Venti) | **参考重写**：理解搜集逻辑后重新实现 |
| `fairy/agents/departments/hu.py` | 岩神 (Zhongli) | **参考重写**：理解理财/红利股逻辑后重新实现 |
| `fairy/agents/departments/li.py` | 冰神 (Tsaritsa) | **参考重写**：理解 skill 管理后重写为 skill 生态 |
| `fairy/agents/departments/xing.py` | 水神 (Furina) 部分 | **参考重写**：理解评审逻辑后重新实现 |
| `fairy/agents/departments/li_official.py` | 时执 (Istaroth) 部分 | **参考重写**：理解归档逻辑后重新实现 |
| `fairy/persona.py` | 派蒙人格 | **重写**：fairy 人格 → 派蒙人格 |
| `fairy/bootstrap.py` | 启动器 | **重写**：适配新架构 |
| `fairy/state.py` | 运行时状态 | **重写**：适配新组件拓扑 |
| `fairy/diagnostics.py` | 三月·自检 | **参考重写**：理解诊断逻辑后在三月中重新实现 |
| `fairy/application/chat.py` | 派蒙·对话核心 | **重构**：参考对话循环，重写并抽离意图分类 + 路由逻辑 |
| `fairy/application/commands.py` | 派蒙·指令系统 | **参考重写**：理解指令体系后重新实现，`/workflow` → `/task` |

---

## 分期实施

> **核心设计原则**：每个 Phase 完成后系统都是**可运行的**——不是"组件能单独测试"，而是"用户能用"。
> Phase 0 即可闲聊，后续每个 Phase 在已运行的系统上叠加新能力。
> 基础设施**按需引入**，不提前堆砌。

---

### Phase 0：派蒙上线 — 闲聊可用

> **目标**：用户通过 WebUI 能和派蒙聊天，系统端到端跑通。
> **产出**：`python -m paimon` 启动后，打开浏览器即可对话。
>
> 这是最重要的一步——从第一天起就有一个能说话的派蒙。

| 任务 | 来源 | 说明 |
|---|---|---|
| 项目结构 `paimon/` 包 | 新建 | `__init__.py`、`__main__.py` |
| `pyproject.toml` | 参考 fairy 重写 | 入口 `paimon = "main:entry"`，按新架构调整依赖 |
| `paimon/config.py` | **参考重写** fairy/config.py | 理解配置结构后按新架构重新实现 |
| `paimon/log.py` | **参考重写** fairy/log.py | 理解日志方案后重新实现 |
| `paimon/template.py` | **参考重写** fairy/template.py | 理解渲染逻辑后重新实现 |
| LLM Provider | **参考重写** fairy/llm/base.py + anthropic.py | 理解 Provider 抽象后重新实现（先做 Anthropic 一个即可） |
| Model 封装 | **参考重写** fairy/llm/model.py | 最小实现：消息收发 + 流式输出（压缩/工具循环后续加） |
| 派蒙核心 | **参考重写** fairy/application/chat.py | 理解对话循环后重新实现 `paimon.receive(msg) → respond` |
| Channel ABC | **参考重写** fairy/channels/base.py | 理解抽象接口后重新实现 |
| WebUI Channel | **参考重写** fairy/channels/webui/ | 理解 WebSocket 通信后重新实现，对接派蒙 |
| 人格模板 | **重写** | 派蒙人格（fairy.t → paimon.t） |
| 启动器 | **重写** bootstrap.py + state.py | 最小组装：config → log → LLM → paimon → WebUI → run |
| `.env.example` | 参考 fairy 重写 | 按新架构设计环境变量 |
| `templates/` | 参考 fairy/templates | 派蒙人格内容 |
| 测试基础设施 | 新建 | `test/conftest.py`、pytest 配置 |
| **单元测试** | 新建 | config / log / template / LLM Provider / Model / Paimon 核心 各自的单元测试 |

**Phase 0 验收**：
- `python -m paimon` 启动，WebUI 打开能聊天，派蒙能正常回复
- 流式输出正常工作
- 所有核心类有单元测试覆盖，`pytest` 全部通过

---

### Phase 1：多频道 + 会话持久化

> **目标**：三个频道都能用，对话有记忆，token 有记录。
> **依赖**：Phase 0
>
> Phase 0 的派蒙是"金鱼记忆"——每次对话都是全新的。本阶段让她记住你。

| 任务 | 来源 | 说明 |
|---|---|---|
| Telegram Channel | **参考重写** fairy/channels/telegram/ | 理解 aiogram 集成后重新实现 |
| QQ Channel | **参考重写** fairy/channels/qq/ | 理解 qq-botpy 集成后重新实现 |
| 会话管理 | **参考重写** fairy/session.py | 理解会话模型后重新实现（SQLite 持久化） |
| 指令系统 | **参考重写** fairy/application/commands.py | `/new`、`/sessions` 等基础指令 |
| 原石 (Primogem) | **参考重写** fairy/workflow/db.py token 部分 | token 记录 + 多维度查询（轻量实现，hook 进 Model 调用） |
| OpenAI Provider | **参考重写** fairy/llm/openai.py | 补齐第二个 LLM Provider |
| **单元测试** | 新建 | 各 channel mock 测试、会话 CRUD 测试、指令解析测试、Primogem 记录/查询测试 |

**Phase 1 验收**：
- 三个 channel 均可与派蒙聊天
- `/new` 开新会话、`/sessions` 查历史正常
- 关闭重启后对话记录还在
- token 用量有记录
- **所有核心类有单元测试覆盖，全部通过**

---

### Phase 2：天使体系 — 简单任务闭环

> **目标**：派蒙能识别简单任务并通过天使（skill）路径完成。
> **依赖**：Phase 1
>
> 从"只能聊天"进化到"能做事"。同时引入地脉事件总线，为后续四影桥接做准备。

| 任务 | 来源 | 说明 |
|---|---|---|
| 意图粗分类 | **新建** | 三分类：闲聊 / 简单任务 / 复杂任务（关键词 + 浅层 LLM） |
| 工具注册 | **参考重写** fairy/tools/ | 理解工具注册机制后重新实现 |
| Skill 解析器 | **参考重写** fairy/skills/parser.py | 理解 SKILL.md YAML 解析逻辑后重新实现 |
| Skill 注册表 | **参考重写** fairy/skills/registry.py | 理解注册逻辑后重新实现，扫描 `~/.paimon/skills/` |
| 天使调度器 | **新建** | 派蒙判定简单任务 → 查匹配 skill → 注入 context → 调 LLM 执行 → 30s 超时 |
| 地脉 (Leyline) | **新建** | 事件总线（`asyncio.Queue` 实现），供魔女会桥使用 |
| 魔女会桥 | **新建** | 天使失败/超时/判定复杂 → 发地脉事件 → Phase 3 四影接收 |
| 现有 skills 迁移 | **参考重写** skills/bili, skills/xhs, skills/web, skills/dividend-tracker | 理解各 skill 逻辑后在 paimon 中重新实现 |
| **单元测试** | 新建 | 意图分类测试、工具注册测试、Skill 解析器测试、天使调度器测试、地脉 pub/sub 测试、魔女会桥测试 |

**Phase 2 验收**：
- 派蒙能区分闲聊和简单任务
- `/bili <url>` 等 skill 通过天使路径正常执行
- 超时能正确报错
- 地脉事件总线 pub/sub 正常
- **所有核心类有单元测试覆盖，全部通过**

---

### Phase 3：四影 + 核心七神 — 复杂任务闭环

> **目标**：复杂任务通过四影流水线 + 核心七神（火神+草神）真正完成。
> **依赖**：Phase 2
>
> 这是系统复杂度跃升最大的一步：四影编排骨架 + 两个核心执行者同时上线。
> 同时引入世界树（持久化）和神之心资源池（多 LLM 并发），因为复杂任务需要它们。

#### 3A. 基础设施补齐

| 任务 | 来源 | 说明 |
|---|---|---|
| 世界树 (Irminsul) | **参考重写** fairy/knowledge/ + workflow/db.py | 知识存储 + 任务存储 + Skill 注册表 + 授权记录 + 缓存层 |
| 神之心升级 (Gnosis) | **新建** | 在 Phase 0 的单 Provider 基础上增加资源池调度（浅层/深层分层） |
| **单元测试** | 新建 | 世界树各存储模块 CRUD 测试、缓存测试、资源池调度测试 |

#### 3B. 四影骨架

| 任务 | 来源 | 说明 |
|---|---|---|
| 死执 · Jonova | **参考重写** fairy/agents/menxia.py | 危险模式检测 + LLM 深度审查 + DAG 批量权限扫描 |
| 生执 · Naberius | **重构** fairy/workflow/task.py + zhongshu.py | DAG 任务模型 + 编排器 + 环检测 + 多轮迭代控制 |
| 空执 · Asmoday | **参考重写** fairy/agents/shangshu.py | 七神注册表 + 动态路由 + 故障切换 |
| 时执 · Istaroth | **参考重写** fairy/agents/departments/li_official.py + model.py | 上下文压缩 + 会话生命周期 + 归档 + 审计复盘 |
| 四影流水线 | **新建** | 死执→生执→空执→七神→时执 编排 |
| **单元测试** | 新建 | 四影各核心类测试、DAG 模型测试、环检测测试、路由测试 |

#### 3C. 核心七神 (P0)

| 任务 | 来源 | 说明 |
|---|---|---|
| Archon ABC | **新建** | 七神基类：能力标签声明 + 统一接口 |
| 火神 · Mavuika | **参考重写** fairy/tools/builtin/sys.py + agents/departments/bing.py | PTY 执行引擎 + 沙箱策略 + 技术性重试 |
| 草神 · Nahida | **参考重写** fairy/agents/zhongshu.py + knowledge/ | 方案起草 + 意图深度推理 + 知识整合 + 偏好管理 |
| **单元测试** | 新建 | 火神执行引擎测试、草神方案起草测试、知识加载测试 |

**Phase 3 验收**：
- `/task 帮我写一个 Python 脚本` 能走通完整流程：派蒙→死执审查→生执编排→空执路由→草神起草→火神执行→时执归档
- DAG 拆分正确；归档可查
- **所有核心类有单元测试覆盖，全部通过**

---

### Phase 4：七神扩展 — 全能力上线

> **目标**：剩余五个七神上线，覆盖全部业务能力。
> **依赖**：Phase 3
>
> 五神之间无直接依赖，可**并行开发**。

#### 4A. 雷神 · Raiden（代码生成）— P1

| 任务 | 来源 | 说明 |
|---|---|---|
| 代码生成 | **新建** | 深层 Gnosis 生成代码 |
| 自检环节 | **新建** | 生成后自动审查（语法检查 + 逻辑复核） |
| 与火神协作 | **新建** | 生成代码 → 火神执行测试 → 结果反馈 → 迭代修改 |
| **单元测试** | 新建 | 代码生成测试、自检逻辑测试、协作流程测试 |

#### 4B. 水神 · Furina（评审 + 游戏）— P1

| 任务 | 来源 | 说明 |
|---|---|---|
| 成品评审 | **参考重写** fairy/agents/departments/xing.py | 理解评审逻辑后重新实现 |
| 多轮挑刺 | **新建** | 作为生执多轮迭代的收敛判定者（水神通过 = 本轮结束）|
| 游戏信息 | **新建** | 游戏攻略 / 数据查询（后续迭代） |
| **单元测试** | 新建 | 评审逻辑测试、收敛判定测试 |

#### 4C. 风神 · Venti（新闻采集）— P2

| 任务 | 来源 | 说明 |
|---|---|---|
| 信息搜集 | **参考重写** fairy/agents/departments/gong.py | 理解搜集逻辑后重新实现 |
| 新闻推送整理 | **参考重写** fairy/agents/departments/li_official.py 部分 | 理解新闻跟踪逻辑后重新实现 |
| 推送内容产出 | **新建** | 整理好内容 → 交三月响铃 → 派蒙送达（三月 Phase 5 实装前先存队列） |
| **单元测试** | 新建 | 搜集逻辑测试、内容格式化测试 |

#### 4D. 岩神 · Zhongli（理财）— P2

| 任务 | 来源 | 说明 |
|---|---|---|
| 红利股跟踪 | **参考重写** fairy/agents/departments/hu.py + skills/dividend-tracker | 理解跟踪逻辑后重新实现 |
| 资产管理 | **新建** | 资产概览 / 退休规划（后续迭代） |
| 推送内容产出 | **新建** | 分红提醒 / 股价异动 → 交三月响铃 |
| **单元测试** | 新建 | 红利股跟踪测试、推送内容测试 |

#### 4E. 冰神 · Tsaritsa（skill 生态）— P2

| 任务 | 来源 | 说明 |
|---|---|---|
| Skill 生态管理 | **参考重写** fairy/agents/departments/li.py | 理解 skill 管理逻辑后重新实现 |
| 世界树写入 | **新建** | 唯一 skill 注册写入者 |
| AI 自举生成 | **新建**（实验性） | LLM 自动生成新 skill（后续迭代） |
| **单元测试** | 新建 | Skill 管理测试、注册写入测试 |

**Phase 4 验收**：
- P1（雷神+水神）：代码生成 + 评审的多轮迭代正常收敛
- P2（风神+岩神+冰神）：新闻/理财/skill 管理各自独立可用
- **每个七神核心类有单元测试覆盖，全部通过**

---

### Phase 5：三月女神 — 守护 + 推送 + 自检

> **目标**：守护进程 + 定时调度 + 推送响铃 + 自检体系上线。
> **依赖**：Phase 4（推送链路需要七神作为数据收集者）

| 任务 | 来源 | 说明 |
|---|---|---|
| 定时调度核心 | **参考重写** fairy/scheduler/ | 理解调度逻辑后重新实现：cron/interval/once 三种触发 |
| 推送响铃（定时） | **新建** | 三月 cron 到点 → 通知数据收集者整理 → 派蒙送达 |
| 推送响铃（事件） | **新建** | 数据收集者请求三月响铃 → 派蒙送达 |
| 推送积压 | **新建** | 派蒙挂掉时暂存；恢复后补发 |
| 自检系统 | **参考重写** fairy/diagnostics.py | 理解诊断逻辑后重新实现 |
| 守护进程 | **新建** | 监控派蒙存活；异常拉起 |
| 任务观测面板数据 | **新建** | 收集运行状态 → 供 WebUI 观测面板展示 |
| **单元测试** | 新建 | 调度核心测试、响铃机制测试、积压队列测试、自检系统测试、守护进程测试 |

> **三月同时负责全项目测试基础设施**：pytest fixtures、mock 工具、测试数据工厂等由三月模块统一提供和维护。

**Phase 5 验收**：
- 定时推送正常送达；风神新闻 / 岩神股价提醒能通过三月→派蒙送到用户
- 自检能检测并报告异常组件
- **三月自身核心类有单元测试覆盖；测试基础设施可供全项目使用**

---

### Phase 6：权限体系 + WebUI 面板 + 安全加固

> **目标**：权限系统闭环 + WebUI 面板可用 + 安全过滤上线。
> **依赖**：Phase 5

#### 6A. 权限体系

| 任务 | 说明 |
|---|---|
| 永久授权存储 | 世界树中的授权条目 schema 落地 |
| 天使路径权限 | 派蒙单项询问 + 永久关键词识别 + 写世界树 |
| 四影路径权限 | 死执 DAG 批量扫描 + 一次性打包询问 |
| 授权缓存同步 | 面板撤销 → 地脉事件 → 派蒙/死执缓存失效 |

#### 6B. 安全加固

| 任务 | 说明 |
|---|---|
| 轻量安全过滤 | 关键词过滤 + 格式拦截（位于意图分类前） |
| 死执规则强化 | 扩展危险模式规则库、增加误报/漏报反馈机制 |

#### 6C. WebUI 面板

| 面板 | 来源 | 说明 |
|---|---|---|
| 聊天面板 | **参考重写** fairy/channels/webui/static_html.py | 理解前端逻辑后重写为派蒙风格 |
| 观测面板 | **参考重写** fairy/channels/webui/palace_html.py | 理解面板逻辑后重写，对接三月数据源 |
| 知识/偏好面板 | **新建** | 草神提供数据 |
| 理财面板 | **新建** | 岩神提供数据 |
| 游戏面板 | **新建** | 水神提供数据（后续） |
| 插件面板 | **新建** | 冰神提供数据 |
| 信息流面板 | **新建** | 风神提供数据 |

**Phase 6 验收**：
- WebUI 能查看/撤销永久授权；各面板有数据展示
- 安全过滤能拦截危险输入
- **权限体系 + 安全过滤核心逻辑有单元测试覆盖**

---

### Phase 7：高级特性 + 打磨

> **目标**：AI 自举、基础设施升级、全链路打磨。
> **依赖**：Phase 6

| 任务 | 说明 |
|---|---|
| 冰神 AI 自举 | LLM 自动生成 skill → 死执审查 → 上线 |
| 地脉升级 | 评估是否需要 Redis Stream（取决于并发量） |
| 时执压缩优化 | 调研主流上下文压缩方案，优化阈值 |
| 生执回滚增强 | saga 补偿 → 状态快照（按需） |
| 异常日志设施 | 独立日志落盘方案（不入世界树） |
| 全链路测试 | contract + smoke + integration 测试套件；确认所有核心类单测覆盖达标 |
| fairy 退役 | 确认 paimon 功能对齐后，fairy 进入只读归档 |

---

## 基础设施引入时机

> 基础设施不再集中在某一个 Phase，而是在**首次被需要时引入**。

| 基础设施 | 引入阶段 | 原因 |
|---|---|---|
| LLM Provider (Anthropic) + Model | **Phase 0** | 闲聊需要 |
| LLM Provider (OpenAI) | **Phase 1** | 补齐第二个 Provider |
| 原石 (Primogem) | **Phase 1** | token 记录随 LLM 调用同步上线 |
| 地脉 (Leyline) | **Phase 2** | 天使→四影桥接需要事件总线 |
| 世界树 (Irminsul) | **Phase 3** | 复杂任务需要持久化存储 |
| 神之心资源池 (Gnosis Pool) | **Phase 3** | 多 LLM 并发调度（四影+七神同时工作） |
| 三月 (March) | **Phase 5** | 守护 + 推送 + 测试基础设施 |

---

## 测试策略

> **核心原则**：每个核心类必须有单元测试覆盖，不写测试不算完成。
>
> **测试基础设施归属**：三月（March）模块统一负责。

| 层级 | 说明 | 时机 |
|---|---|---|
| **单元测试** | 每个核心类/模块独立测试，mock 外部依赖 | 每个 Phase 随代码同步编写 |
| **集成测试** | 跨模块交互测试（如地脉 pub/sub → 世界树写入） | Phase 2 起逐步添加 |
| **冒烟测试** | 系统启动 + 基本功能验证 | Phase 0 起 |
| **全链路测试** | 完整业务路径端到端测试 | Phase 7 集中完善 |

**测试目录结构**：
```
test/
├── conftest.py              # 全局 fixtures（三月提供）
├── factories.py             # 测试数据工厂（三月提供）
├── unit/                    # 单元测试（按模块组织）
│   ├── test_config.py
│   ├── test_log.py
│   ├── test_template.py
│   ├── foundation/
│   │   ├── test_leyline.py
│   │   ├── test_irminsul.py
│   │   ├── test_gnosis.py
│   │   └── test_primogem.py
│   ├── core/
│   │   ├── test_intent.py
│   │   ├── test_commands.py
│   │   └── test_safety.py
│   ├── channels/
│   ├── angels/
│   ├── shades/
│   └── archons/
├── integration/             # 集成测试
└── smoke/                   # 冒烟测试
```

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
│   ├── channels/                   # 频道层
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
│   ├── llm/                        # LLM Provider
│   │   ├── base.py
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   └── model.py
│   │
│   ├── tools/                      # 工具层
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── external.py
│   │   └── builtin/
│   │
│   └── skills/                     # Skill 解析
│       ├── parser.py
│       └── registry.py
│
├── skills/                         # Skill 插件
├── tools/                          # 外部工具脚本
├── templates/                      # 系统 prompt 模板
├── knowledge/                      # 知识库数据
├── docs/                           # 架构文档（已有）
└── test/                           # 测试套件
```

---

## 里程碑与时间参考

| 里程碑 | Phase | 核心交付 | 用户可感知 |
|---|---|---|---|
| **M0 — 派蒙上线** | Phase 0 | WebUI 闲聊 | 能和派蒙说话了 |
| **M1 — 全频道 + 记忆** | Phase 1 | 三 channel + 会话持久化 | TG/QQ 也能用了，还记得之前聊过啥 |
| **M2 — 简单任务** | Phase 2 | 天使路径 + skill 执行 | 能帮忙干简单活了 |
| **M3 — 复杂任务** | Phase 3 | 四影 + 火神 + 草神 | 能处理复杂需求了 |
| **M4 — 全能力** | Phase 4 | 七神全部上线 | 写代码、搜新闻、看股票都行了 |
| **M5 — 守护推送** | Phase 5 | 三月守护 + 推送 | 会主动推消息了 |
| **M6 — 面板权限** | Phase 6 | WebUI 面板 + 权限 + 安全 | 有管理界面了 |
| **M7 — fairy 退役** | Phase 7 | 高级特性 + 全面测试 | 完全体 |

---

> 每个 Phase 完成后系统都是**可运行、可使用的**，不依赖后续 Phase 才能工作。
> Phase 0~2 为核心路径（聊天→记忆→做事），优先交付；Phase 3~4 为能力跃升；Phase 5~7 为打磨完善。
>
> **迁移纪律**：
> - 不直接复制、不简单改名——参考 fairy 源码理解逻辑后在 paimon 中重新实现
> - 每个核心类必须附带单元测试，不写测试不算完成
> - 测试基础设施由三月（March）模块统一管理
