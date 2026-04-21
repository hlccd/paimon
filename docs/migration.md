# 神圣规划 · 分阶段执行

> 隶属：[神圣规划](aimon.md)
> 将现有"三省六部 + 御览 + scheduler"架构迁移到 AIMON 矩阵。
> 已通过 3 轮内审 + 3 轮外审 + 20 轮循环审查 + 代码审计（105 个确认问题）。
> **本文档是执行手册**——每个 Phase 包含「待澄清 → 待执行 → 验收条件」三段式。

---

## 背景速览

### 旧架构核心流转

```text
用户 → channel → chat.py → workflow.engine
  ├── 简单 → ExecutorAgent → handle_chat (LLM + tool)
  └── 复杂 → 中书(起草) → 门下(审议) → 尚书(派发六部) → 御览(圣裁)
```

### 新架构核心流转

```text
用户 → channel → 派蒙
  ├── 闲聊 → 派蒙浅层 LLM
  ├── 简单 → 天使（skill 直调）
  └── 复杂 → 死执 → 生执 → 空执 → 七神 → 时执 → 派蒙送达
```

### 核心映射速查

| 旧 | 新 | 备注 |
|---|---|---|
| `chat.py` + `persona.py` + `session.py` | 派蒙 | 统一入口 |
| `menxia` 安全审议 | 死执 | LLM 深审替代正则 |
| `zhongshu` 起草 + `shangshu` 监控 | 生执 | DAG 编排 |
| `shangshu` 派发 + `DEPARTMENT_MAPPING` | 空执 | 语义路由替代关键词 |
| 六部（礼/吏/户/兵/刑/工） | 七神 | 按领域重组 |
| `workflow.engine._assess_risk` | 派蒙意图粗分类 | LLM 替代启发式 |
| `imperial`（御览） | **废弃** | 前置询问替代 |
| `scheduler/` | 三月 | 不自跑 LLM |
| `llm/` | 神之心 | 浅深分池 |
| `knowledge/` | 世界树 + 草神 | 存储 + 业务接口 |

### SQLite 表归属

**架构铁律**：世界树是**全系统唯一存储层**，所有表物理归属为世界树；**业务服务方**持有业务逻辑并通过世界树 API 读写。

| 旧表 | 物理归属 | 业务服务方 |
|---|---|---|
| `edicts` / `subtasks` / `flow_history` / `progress_log` | 世界树（活跃 + 归档同库，只是由服务方打生命周期标签） | 活跃阶段 → 生执/空执/七神；归档阶段 → 时执 |
| `token_usage` | 世界树 | 原石 |
| `revision_records` | 世界树 | 时执 |
| `dividend_*` | 世界树 | 岩神 |
| `sessions`（原 JSON 文件） | 世界树 | 派蒙 |
| **新增** `authorizations` | 世界树 | 派蒙 / 草神面板 |
| **新增** `skills` | 世界树 | 冰神 |
| **新增** `memory_index` | 世界树 | 草神 |

### 代码审计概况

审计发现 105 个确认问题（P0:6 / P1:25 / P2:45 / P3:29），详见 `fairy/.audit/report.md`。下文每个 Phase 的待执行中以 `⚠️ 审计` 标注对应约束。

---

## Phase 0 · 仓库卫生

> 立即执行，不阻塞后续 Phase。与架构无关的仓库级问题。

### 待澄清

无。

### 待执行

- [ ] **P0-1** `git rm --cached .env` 解除 `.env` 的 git 跟踪
  - ⚠️ 审计 PRJ-015（P0）：`.gitignore` 对已跟踪文件无效，当前 `.env` 在 git 历史中
- [ ] **P0-2** 清理 `.env.example`：
  - 删除已废弃的 `CLI_ENABLED=true`
  - 合并重复的 `WEBUI_ENABLED`（出现两次）
  - 删除 `BRAVE_API_KEY` / `TAVILY_API_KEY`（config.py 无对应字段）
  - ⚠️ 审计 PRJ-003/008（P3）
- [ ] **P0-3** `pyproject.toml`：移除 `ddgs` / `beautifulsoup4` 依赖声明（fairy 包未 import）；description 删除 "CLI"
  - ⚠️ 审计 PRJ-005/001（P2-P3）
- [ ] **P0-4** `README.md`：删除内置工具表中的 `web_search` / `web_fetch`（代码中不存在）
  - ⚠️ 审计 PRJ-001（P2）
- [ ] **P0-5** 补 `LICENSE` 文件（README 声明 MIT 但无文件）
  - ⚠️ 审计 PRJ-010（P3）
- [ ] **P0-6** 默认值对齐：`.env.example` 与 `config.py` 统一
  - `LLM_PROVIDER`：`.env.example` 为 `claude-xiaomi`，`config.py` 为 `openai`
  - `KNOWLEDGE_AUTO_EXTRACT`：`.env.example` 为 `false`，`config.py` 为 `True`
  - ⚠️ 审计 PRJ-004（P2）

### 验收条件

- [ ] `git ls-files .env` 返回空
- [ ] `.env.example` 无重复声明、无废弃项
- [ ] `pyproject.toml` dependencies 只含 fairy 实际 import 的包
- [ ] README 内置工具表与 `fairy/tools/builtin/` 一致
- [ ] `.env.example` 与 `config.py` 中同名配置项默认值一致

---

## Phase A · 基础层骨架

> 新建 `paimon/foundation/leyline/` `paimon/foundation/irminsul/` `paimon/foundation/march/`。
> 世界树是**唯一存储层**，率先落地；原石当前仍自持 SQLite，会在 A3 重构时剥离 DB 代码改为调世界树 `token_*`。
> 仅搭接口骨架 + 服务层骨架调用，暂无上层消费者。

### 待澄清

| # | 问题 | 阻塞 | 备注 |
|---|------|------|------|
| A-Q1 | **地脉实现选型**：进程内（`asyncio.Queue`）还是分布式（Redis Stream）？ | A1 | 两者接口语义差异大（at-most-once vs at-least-once、持久化保证），必须先定 |
| A-Q2 | **神之心分层接口契约**：浅层/深层池的调用方式是 `pool="shallow"` 参数还是不同入口？ | B（接口预留） | B 阶段代理委托需要知道参数形式，A 阶段先定接口、E 阶段实装 |
| A-Q3 | **原石多维度标签 schema**：`module` + `purpose` 的枚举集有哪些值？ | A3 | 影响事件格式设计 |

### 待执行

#### A1 · 地脉 `paimon/foundation/leyline/`

- [ ] 搭 publish/subscribe 接口（暂无订阅者）
- [ ] 定义核心事件名规范（如 `vision.chat_complete`、`task.state_changed`）

#### A2 · 世界树 `paimon/foundation/irminsul/`

**定位**：全系统**唯一存储层**，承载 9 个数据域。其他所有模块的持久化落盘统一走世界树 API，不自建 SQLite / 文件库。详见 [docs/foundation/irminsul.md](foundation/irminsul.md)。

- [ ] 按域分组的语义化 API（9 组，非通用 KV）：
  - [ ] `authz_*`：用户授权（新增 `authorizations` 表）
  - [ ] `skill_*`：Skill 生态声明（新增 `skills` 表）
  - [ ] `knowledge_*`：知识库（文件系统 markdown）
  - [ ] `memory_*`：记忆（新增 `memory_index` 表 + 文件 body，含个人偏好/习惯）
  - [ ] `task_*`：活跃任务（迁移 `edicts` / `subtasks` / `flow_history` / `progress_log` 表；归档不分库，用生命周期字段）
  - [ ] `token_*`：Token 记录（迁移 `token_usage` 表，原石剥离 DB 代码后调本接口）
  - [ ] `audit_*`：审计 / 归档（迁移 `revision_records` 表）
  - [ ] `dividend_*` / `zhongli_*`：理财数据（迁移 `dividend_*` 表）
  - [ ] `session_*`：聊天会话（**新增 `sessions` 表，把 `paimon_home/sessions/*.json` 迁入**）
- [ ] **路径安全**：所有文件 API 内部 `resolve()` 校验，调用方不传路径字符串
  - [ ] ⚠️ 审计 SEC-003（P1）：**所有文件读写 API 必须内置路径校验**——`resolve()` 后确认不超出根目录。不留给调用方自行校验。这是知识库路径遍历 + 模板 RCE 链的根因
- [ ] **写入日志**：每次 `*_set` / `*_delete` 打 INFO 日志，格式 `[世界树] <服务方>·<动作> <对象+参数>`（详见 [irminsul.md §日志约定](foundation/irminsul.md)）
  - [ ] 每个写 / 删方法签名要求调用方传 `actor` 参数（服务方中文名）
- [ ] **三原语**：每个域提供 CRUD / snapshot / list 三类接口；**不提供** subscribe / watch
- [ ] **只存不推**：不发事件、不订阅地脉
- [ ] **schema 集中迁移**：所有表的建表与增量 ALTER 在世界树内部完成，幂等
- [ ] ⚠️ 审计 SEC-027（P2）：`authorizations` 表设计时 session_id 字段延长到 128bit（`uuid4().hex` 全 32 字符）
- [ ] ⚠️ 审计 COR-005（P2）：世界树 API 的序列化 key 与 DB 列名保持一致（`from_agent`/`to_agent`/`progress_pct`/`creator`），不再沿用旧 `to_dict()` 的 `from`/`to`/`progress`/`created_by`
- [ ] **会话迁移脚本**：启动时检测 `paimon_home/sessions/*.json` 存在 → 逐个导入 `sessions` 表 → 标记原 JSON 目录为 `sessions.migrated/`
- [ ] **横向独立**：irminsul 包不 import `gnosis` / `model` / `primogem 业务接口` / `leyline`

#### A3 · 原石 `paimon/foundation/primogem.py`

**定位**：服务层模块。业务逻辑留原石（费率查表 / 缓存折扣计算 / 多维聚合 / dashboard），**数据落盘统一调世界树 `token_*` API**。详见 [foundation/primogem.md](foundation/primogem.md)。

- [ ] **剥离 DB 代码**：原 `Primogem` 类里的 `aiosqlite.connect` / `executescript` / `_migrate` / `_SCHEMA` 全部删除，统一迁到世界树
- [ ] **重构为服务层**：`Primogem` 不再拿 `db_path`，改为 `Primogem(irminsul: Irminsul)` 持有世界树引用
- [ ] `record()` 内部改调 `irminsul.token_write(..., actor="原石")`
- [ ] `get_session_stats()` / `get_global_stats()` / `get_timeline_stats()` 等聚合查询通过世界树的 `token_*` 查询接口拿行，原石做二次聚合 / 格式化
- [ ] 订阅地脉 `vision.chat_complete` 事件累积成本
- [ ] ⚠️ 审计 COR-007（P2）：费用计算**按模型查表**，不硬编码。接口 `model_name` 为必传参数
- [ ] 接入三月 Web 观测面板（A4 之后）

#### A4 · 三月 `paimon/foundation/march/`

- [ ] 吸收 `scheduler/` + `diagnostics.py`，预留响铃接口
- [ ] ⚠️ 审计 OPS-005（P1）：调度循环必须有 **Task 级别健康检查 + 自动重启**，不仅是进程拉起
- [ ] ⚠️ 审计 OPS-015（P2）：健康检查必须验证 `task.done()`，不能仅检查 Task 对象存在性
- [ ] ⚠️ 审计 OPS-017（P2）：心跳 `channel_name` 不再硬编码 `"cli"`
- [ ] 自检体系框架（contract/smoke 由三月定时触发；live 仅按需手动）

### 验收条件

- [ ] 地脉 publish/subscribe 接口可用（单元测试通过）
- [ ] 世界树 API 全部路径操作经 `resolve()` 校验（单测覆盖路径遍历场景）
- [ ] 原石接收事件后按模型名查表计费（单测覆盖 ≥2 种模型）
- [ ] 三月调度循环异常退出后 5s 内自动重启（集成测试）
- [ ] 三月健康检查能检测到"Task 已 done 但对象还在"的场景

---

## Phase B · 七神骨架

> 与 A/C 并行。**代理委托**老代码，不复制。新类持有老实例并包装新接口。

### 待澄清

| # | 问题 | 阻塞 | 备注 |
|---|------|------|------|
| B-Q1 | **冰神 vs 工具层安全边界**：外部工具（`~/.fairy/tools/` 下 .py）的加载归冰神审查还是工具层自管？当前方案写 `ToolRefreshTool` "与冰神无关"，但 `exec_module` 无沙箱 + `_ensure_deps` 任意 pip install 是 P0 级 RCE | B4 | 建议：外部工具加载纳入冰神管理，或在工具层自身加签名校验 |
| B-Q2 | **火神命令执行安全策略**：白名单 / 沙箱 / 用户确认选哪种？三者成本和安全等级不同 | B3 | 建议：至少实现"危险命令 + 用户确认"；长期考虑容器沙箱 |
| B-Q3 | **模板 `$@[cmd]` 处置**：保留（加白名单）/ 沙箱执行 / 废弃（用 LLM tool calling 替代）？ | B5/D1 | 审计 SEC-023（P1）：`template.render` 的 `shell=True` 结合知识库路径遍历可构成 RCE 链 |

### 待执行

#### B1 · 岩神

- [ ] 新类持有老 `HuDepartment` 实例并委托调用
- [ ] 接口按新架构定义（数据收集者角色 → 三月响铃）

#### B2 · 风神

- [ ] 新接口包装 gong + 吏部新闻（两处合并）
- [ ] `gong._handle_web_fetch` 的 aiohttp 抓取**下沉工具层**
- [ ] ⚠️ 审计 ARCH-006（P1）：**SSRF 防护**——URL 解析后校验不是私有 IP（10.x / 172.16-31.x / 192.168.x / 127.x / 169.254.x）/ 云元数据地址

#### B3 · 火神

- [ ] 包装 `_handle_bash` + ExecTool 系列
- [ ] ⚠️ 审计 SEC-005（P0）：新接口**必须加入命令执行安全层**（策略取决于 B-Q2 澄清结果）
- [ ] ⚠️ 审计 SEC-005（P1）：危险命令黑名单不能只有 4 个词，至少复用门下省 `DANGEROUS_PATTERNS` 完整列表
- [ ] ⚠️ 审计 REL-005（P1）：`wait_for` 超时后必须 `proc.kill()` + `await proc.wait()`

#### B4 · 冰神

- [ ] 包装 SkillRegistry + 预装免审 vs 运行时必审分流
- [ ] ⚠️ 审计 SEC-001（P0）：**删除 `_ensure_deps` 自动 pip install**（或改为用户确认 + 包名白名单）
- [ ] ⚠️ 审计 SEC-002（P0）：`exec_module` 加载外部 .py **必须有安全边界**（策略取决于 B-Q1 澄清结果）
- [ ] `allowed_tools` 从解析到实施：SKILL.md 未声明时默认策略——允许普通、禁止敏感（见 permissions.md）

#### B5 · 草神

- [ ] 知识 + 礼部文书 + 中书 LLM
- [ ] 授权面板 UI 骨架（暂不对接世界树数据，D4 上线）
- [ ] ⚠️ 审计 SEC-012（P2）：面板 UI 前端对用户消息做 HTML 转义（`textContent` 或 escape 函数），不用 `innerHTML` 裸插入

#### B6 · 水神

- [ ] 纯新建（内容维度评审接口）

#### B7 · 雷神

- [ ] 纯新建（代码生成 prompt 模板）

#### B 通用

- [ ] ⚠️ 审计 SEC-003（P2）：代理委托老代码时，对老代码的输出做校验/清洗——**不把内部异常信息原样透传**到调用方或用户

### 验收条件

- [ ] 七神各新类可通过代理委托调用老代码完成基本操作
- [ ] 风神 web_fetch 拒绝私有 IP 段 URL（单测覆盖）
- [ ] 火神超时后子进程被 kill（集成测试）
- [ ] 冰神不再自动 pip install（grep `_ensure_deps` 无调用或已删除）
- [ ] 冰神外部工具加载有安全校验（签名/白名单/审查三选一）
- [ ] `allowed_tools` 实施生效（调用未声明工具被拒绝）

---

## Phase C · 四影骨架

> 与 A/B 并行。搭建死执→生执→空执→时执流水线骨架。

### 待澄清

| # | 问题 | 阻塞 | 备注 |
|---|------|------|------|
| C-Q1 | **生执依赖环回滚机制**：saga 补偿 / 状态快照 / 其他？ | C2 | |
| C-Q2 | **时执压缩阈值**：旧 3.5k 偏低，目标阈值是多少？ | C4 | 需调研主流方案 |
| C-Q3 | ~~**时执归档存储介质**：本地 SQLite / 独立归档库 / 对象存储？~~ | — | **已解决**：架构升级为"世界树唯一存储层"后，归档同库，由时执打生命周期字段（热/冷/过期）区分；不分独立库 |

### 待执行

#### C1 · 死执

- [ ] review + 黑名单 + 两次介入接口（① 生执前审请求 ② 生执拆完 DAG 后扫敏感操作）
- [ ] ⚠️ 审计 SEC-003（P2）：安全审查必须覆盖**实际命令**而非自然语言描述。旧 menxia 的 `DANGEROUS_PATTERNS` 检查的是 `subtask.description`（自然语言），死执须对最终执行参数做审查
- [ ] C1 阶段先持有全部安全规则，待 D3 时派蒙复用其中"快速匹配"子集

#### C2 · 生执

- [ ] zhongshu JSON 结构化 + shangshu 监控 + 轮次控制 + 依赖环检测
- [ ] ⚠️ 审计 COR-017（P0）：**输出 key 与下游消费方必须对齐**。旧 shangshu 返回 `outputs`/`errors` 但 engine 访问 `output`/`summary`，结果永远为空。新生执的产出 schema 需与空执/派蒙的消费 schema 在接口定义时一并确定
- [ ] ⚠️ 审计 REL-012（P1）：多轮流程必须有 **try/except 包裹**，异常时将任务状态设为 FAILED 而非卡在中间态

#### C3 · 空执

- [ ] shangshu 派发；关键词表弃用，改语义路由；`DispatchTool` 归空执独占（当前在 `tools/builtin/chat.py`）
- [ ] ⚠️ 审计 ARCH-003（P2）+ OPS-011：路由结果必须有**可观测性日志**——路由到哪个神、为什么

#### C4 · 时执

- [ ] compress_session_context 触发 + revision_records + 归档生命周期（热 30d / 冷 30-90d / 过期删除）
- [ ] ⚠️ 审计 COR-009（P2）：压缩去重不能用 `summary not in session_memory`（永远为 True），改为时间戳窗口或语义相似度

### 验收条件

- [ ] 死执→生执→空执→时执流水线可跑通最简场景
- [ ] 生执产出 schema 与消费方 schema 一致（接口测试）
- [ ] 生执内部异常时任务状态转为 FAILED（非中间态）
- [ ] 空执路由决策有日志记录
- [ ] 时执压缩后不产生重复摘要条目

---

## Phase D · 派蒙统一 + 切流量

> 前置：A + B + C 全部完成。**本阶段才真换线**——engine 入口切到派蒙路由。

### 待澄清

| # | 问题 | 阻塞 | 备注 |
|---|------|------|------|
| D-Q1 | **闲聊 session 形态**：复用主会话 session？独立轻量 session？ | D1 | |
| D-Q2 | **用户答复交互形态**：文本识别 / 按钮 / 默认超时？ | D4 | 影响权限询问闭环实现 |
| D-Q3 | **推送具体策略**：时机 / 频率 / 打断策略 / 积压处理 | D8 | 三段式路径已定，细节待定 |

### 待执行

#### D1 · 新建派蒙

- [ ] 吸收 `handle_chat` + `persona` + 打断机制
- [ ] engine 入口切到"派蒙路由 → 死执 → 生执 → 空执 → 七神 → 时执"
- [ ] ⚠️ 审计 REL-008（P1）：session 加载必须**单文件 try/except**，一个 session 损坏不能导致全部丢失
- [ ] ⚠️ 审计 REL-015（P2）：session `fork_from` 必须**深拷贝** messages
- [ ] ⚠️ 审计 REL-012（P2）：Session 数据类容忍未知字段（前向兼容），构造前过滤多余 key
- [ ] ⚠️ 审计 SEC-023（P1）：吸收 `template.py` 时按 B-Q3 结论处置 `$@[cmd]` 机制
- [ ] ⚠️ 审计 SEC-019（P1）：`SendFileTool` 归派蒙后加**路径白名单**（只允许 fairy_home 下的文件）

#### D1-WebUI · 认证加固

- [ ] ⚠️ 审计 SEC-015（P1）：Cookie 加 `httponly=True, samesite="Lax"`
- [ ] ⚠️ 审计 SEC-014（P1）：认证端点加失败速率限制（如 5 次/分钟）
- [ ] ⚠️ 审计 SEC-027（P2）：session_id 延长到 128bit（`uuid4().hex` 全 32 个十六进制字符，不再截断前 8 个）
- [ ] ⚠️ 审计 SEC-021（P1）：API 层校验 session 归属（WebUI 多用户共享场景）
- [ ] ⚠️ 审计 SEC-005（P1）：默认 bind `127.0.0.1`，外部访问需显式配 `WEBUI_HOST=0.0.0.0`

#### D2 · 意图粗分类

- [ ] LLM 替代 `_assess_risk` 启发式

#### D3 · 轻量关键词过滤

- [ ] 从 C1 死执的安全规则中拆出"快速匹配"子集供派蒙使用

#### D4 · 权限询问闭环

- [ ] 派蒙单项询问 + 死执批量扫描（派蒙转达）+ 世界树存储 + 草神面板 UI **对接世界树并上线**

#### D5 · 魔女会兜底通道

- [ ] 天使失败 → 四影

#### D6 · 冰神→四影→派蒙缓存同步

- [ ] 运行时新 skill 审查通过后通知派蒙更新画像

#### D7 · state.py 字段引用清理

- [ ] `state.workflow_engine` / `task_store` / `hu_department` 等 import 全部切新接口
- [ ] `state.py` 保留为 `RuntimeContext`（DI 容器）
- [ ] ⚠️ 审计 OPS-010（P3）：`session_task_locks` 随 session 删除而清理

#### D8 · 推送链路切换（双推观察期）

- [ ] D8a 新岩神/风神经"数据收集者 → 三月 → 派蒙"发一遍
- [ ] D8b 老 `_push_notification` / `_send_message` 继续直推，对比两路产出
- [ ] D8c 确认一致后关老路径

#### D9 · 三月委托派蒙

- [ ] `_run_prompt` 改为"派蒙按用户意图发起新会话走完整路径"；三月不再跑 LLM

#### D10 · 命令迁移与废弃

**保留命令**（19 条，归属随模块迁移）：
`/new /switch /sessions /stat /clear /cleanup /rename /delete /stop /history`（派蒙会话管理）、`/schedule /selfcheck`（三月）、`/knowledge`（草神）、`/skill /update_skills`（冰神）、`/task /edict`（三月观测 + 时执历史）、`/{skill-name}`（天使体系）

**废弃命令**（4 条）：
- [ ] `/approve /revise /reject`（前置询问替代御览）
- [ ] `/task confirm|reject`（同上）

**别名**：
- [ ] `/workflow` 作 `/task` 别名

### 验收条件

- [ ] 派蒙路由全链路可跑通（闲聊 / 天使 / 四影-七神三条路径）
- [ ] 单个 session 记录（世界树 sessions 表的行）损坏时其他 session 正常加载（测试）
- [ ] WebUI Cookie 含 HttpOnly + SameSite（浏览器 DevTools 确认）
- [ ] 认证失败 5 次/分钟后被限速（测试，与 D1-WebUI 速率限制一致）
- [ ] `session_id` 长度 ≥ 32 hex 字符
- [ ] 枚举其他用户 `session_id` 时返回 403（测试）
- [ ] `SendFileTool` 发送 `/etc/passwd` 被拒绝（测试）
- [ ] 推送双推对比无差异后老路径关闭
- [ ] 三月不再直接调用 LLM（grep `_stream_text` / `chat_stream` 在 march/ 中无调用）
- [ ] 4 条废弃命令返回提示信息而非执行

---

## Phase E · 神之心分层

> 前置：D 完成（派蒙已接管流量）。吸收 `fairy/llm/` 代码，拆双池 + 路由选择器。

### 待澄清

| # | 问题 | 阻塞 | 备注 |
|---|------|------|------|
| E-Q1 | **分层具体标准**：按参数量 / provider / 成本 / 场景？ | E1 | A-Q2 定了接口契约，此处定实装标准 |
| E-Q2 | **熔断策略**：浅层池全挂时是否 fallback 到深层池？延迟 / 成本如何取舍？ | E3 | |

### 待执行

#### E1 · 吸收 llm/

- [ ] 新建 `fairy/vision/`，吸收 `fairy/llm/` 代码
- [ ] ⚠️ 审计 COR-003（P1）：**修复多轮 tool-call 循环中 `session.messages.pop()` 弹错消息的问题**。记录 append 前的 messages 长度，异常时 truncate 回该快照点
- [ ] ⚠️ 审计 REL-005（P1）：streaming 异常后消息链一致性——同上修复方案
- [ ] ⚠️ 审计 COR-005（P2）：`json.loads(arguments)` 对 LLM 返回的畸形 JSON 需 try/except，fallback 空 dict
- [ ] ⚠️ 审计 PERF-010（P2）：streaming 字符串拼接改为 `list.append` + `"".join()`

#### E2 · 配置扩展

- [ ] `.env` 扩展 `shallow_provider` / `deep_provider`（各自指向现有 provider 配置）
- [ ] 旧 `llm_provider` 作 fallback

#### E3 · Fallback + 熔断 + 按池成本

- [ ] ⚠️ 审计 COR-007（P2）：神之心发 `vision.chat_complete` 事件时**必须携带 model_name**，原石按模型查表算费
- [ ] 旧 `Model.chat(...)` 签名保留兼容（默认走深层池）

### 验收条件

- [ ] 双池路由正确分流（浅层请求不打到深层模型）
- [ ] tool-call 多轮循环中 streaming 异常后 session.messages 回退到正确位置（单测覆盖）
- [ ] `json.loads` 畸形 JSON 不崩溃（单测）
- [ ] 事件中 `model_name` 存在且原石按模型计费（集成测试）
- [ ] fallback 机制：浅层池不可用时按策略切换（集成测试）

---

## Phase F · 清理 + 数据迁移

> 前置：D7 已切完 + 新旧并行确认无问题。

### 待澄清

| # | 问题 | 阻塞 | 备注 |
|---|------|------|------|
| F-Q1 | **停服时间窗口**：可接受多长停服？影响迁移 SQL 执行策略 | F1 | SQLite 单文件迁移通常秒级 |

### 待执行

#### F1 · 停服 + 数据迁移

- [ ] 停服 → 跑数据迁移 SQL → 启新版
- [ ] **AgentRole 枚举迁移**：

| 旧 | 新 |
|---|---|
| `user` | `user` |
| `planner` | `naberius`（生执）|
| `reviewer` | `jonova`（死执）|
| `executor` | `asmoday`（空执）|
| `validator` | `istaroth`（时执）|

- [ ] **历史状态清理**：
  - `IMPERIAL_REVIEW` → `completed` 或 `cancelled`（按 metadata 判断）
  - `PENDING_APPROVAL` → `blocked` + reason "旧审批机制废除"
- [ ] ⚠️ 审计 COR-005（P2×3）：确认新代码（世界树/生执）的序列化 key 已统一——旧 `to_dict()` 用 `from`/`to`/`progress`/`created_by`，DB 列用 `from_agent`/`to_agent`/`progress_pct`/`creator`。新代码在 A2/C2 阶段应已统一（见各阶段约束），此处验证一致性

#### F2 · grep 验证

- [ ] 无旧模块引用
- [ ] ⚠️ 额外检查：无硬编码费率、无 `shell=True` 裸调用、无路径拼接无校验、无 `except: pass` 吞关键异常

#### F3-F8 · 代码删除

- [ ] F3 删 `workflow/`（engine/task/store/db/imperial 全部）
- [ ] F4 删 `agents/departments/`
- [ ] F5 删 `agents/{zhongshu,menxia,shangshu,executor}.py` 和 `agents/` 目录
- [ ] F6 删 `application/chat.py` + 拆散 `commands.py`
- [ ] F7 删 `fairy/llm/`（已迁入 vision）
- [ ] F8 `state.py` 瘦身（删 `workflow_engine` / `hu_department` / `task_store` 字段）

### 验收条件

- [ ] 枚举迁移 SQL 执行成功，`edicts.owner` / `flow_history.from_agent` / `progress_log.agent` 值已更新
- [ ] 历史 `IMPERIAL_REVIEW` / `PENDING_APPROVAL` 任务已清理
- [ ] 序列化 key 统一（`from_agent` / `progress_pct` / `created_by`）
- [ ] grep `fairy/agents/` / `fairy/llm/` / `fairy/workflow/` / `application/chat.py` 在新代码中零引用
- [ ] 迁移后所有历史任务/会话可正确读取
- [ ] 性能基线对比（响应时间、token 消耗无显著退化）

---

## 附录

### 全局原则

- A / B / C 的新模块以**代理方式**委托老代码执行，engine 入口不变
- D 才把 engine 切到新派蒙、骨架真正接管流量；E 分池，F 清理
- **自检贯穿全程**：新模块建起时同步新增对应测试；旧模块随 F 阶段一起删测试；D 阶段开始后 `test/` 调度权交三月
- **安全/质量约束嵌入**：各阶段新代码不得复现审计报告中的已确认问题（`fairy/.audit/report.md`），验收时逐项核对

### 风险与回滚

| 改造 | 风险 | 缓解 |
|---|---|---|
| 废御览 + `/task confirm/reject` | 旧待审任务孤立 | 数据迁移时关停历史 |
| 推送链路改造 | 红利 / 定时通知漏推 | 新旧双推观察期 |
| 三月委托 LLM | 旧 `_run_prompt` 行为变化 | 新旧接口并行对比 |
| 枚举迁移 | enum lookup 失败 | D 阶段运行时兼容层，F1 停服 SQL 切换后删兼容层 |
| `state.py` 解耦 | 引用散布 | 字段设 `@deprecated`，grep 归零再删 |
| 神之心分池 | 轻模型能力不足 / 雪崩 | 灰度 + fallback 熔断器 |
| 权限画像缓存 | 缓存 vs 世界树延迟 | 派蒙内部闭环（写+自更新），跨模块走四影通知 |
| 冰神运行时审查 | 装载阻塞 | 异步 + 超时 + 并发限流 |
| 神之心吸收 `llm/` | LLM 调用点需同步改签名 | E 阶段全局替换；旧签名保留兼容 |
| **世界树知识库 API** | **路径遍历 → 模板 RCE 链** | **API 层内置 `resolve()` 校验** |
| **火神包装 ExecTool** | **继承旧 RCE 漏洞** | **新接口强制命令确认 + 超时 kill** |
| **派蒙吸收 channel 层** | **WebUI 认证缺陷带入新架构** | **D1 同步加固认证** |
| **神之心吸收 llm/** | **多轮 tool-call pop bug 搬入** | **E1 同步重写消息回退逻辑** |

**回滚策略**：
- A-C 骨架无侵入，回退 = 删新代码
- **D/E** 设 feature flag（`USE_AIMON_*`）灰度，崩溃即关 flag
- F 前保留至少一版旧代码（git tag 标记）

### 审查记录

#### 第 1 轮（内审 · 初步映射）
粗略归类后未读源码，识别 6 类高层对应。

#### 第 2 轮（内审 · 读码修正）
修正刑部→时执、工部吏部新闻合并、`_push_notification` 违规、御览废弃、state ≠ 地脉、chat.py 四拆。

#### 第 3 轮（内审 · 遗漏核对）
核对六部 / 命令 / 表 / 工具 / Skill / WebUI 路由逐项归属；识别 dividend-tracker 业务代码迁移策略。

#### 第 4 轮（外审 · 对照文档）
12 处：新旧流程顺序反转、死执两次介入、生执轮次控制、派蒙轻量过滤、草神面板 UI、预装免审、冰神→四影→派蒙链路、七神协作、派蒙不扫 skills、启发式→LLM、闲聊路径、数据收集者角色。

#### 第 5 轮（外审 · 对照源码）
8 处：scheduler 直推 + 自跑 LLM、`ToolRefreshTool` 归属错、`Model.compress/title/cost` 拆分、`_try_extract_knowledge` 模式、派蒙打断机制、`allowed_tools` 从解析到实施、heartbeat 跨模块依赖。

#### 第 6 轮（外审 · 内部一致性）
11 处：阶段 A4 依赖倒挂、B/C 可并行、完成判定漏项、风险表缺口、F 阶段前置条件、数据迁移缺失、`/task confirm/reject`、观测划分、"搬"改"复制"、分池实装细节、配置迁移。

#### 循环审查（聚焦可行性；连续 3 轮零真问题才停）

- **R1**（10 查 / 6 真）：A2 逻辑统一措辞、A3 原石通过地脉订阅、B "复制"改"代理委托"、D6 双推时序、D7 定时委托派蒙路径、test/ 本身需重写
- **R2**（10 查 / 7 真）：`_sansheng_liubu_workflow` 调度链归派蒙、风神 web_fetch 下沉工具层、世界树补 skill 声明、草神面板 B5 骨架/D4 上线分离、死执两次介入标顺序、原则段表述精确、数据迁移 fallback
- **R3**（13 查 / 4 真）：**地脉职责边界**（事件总线 ≠ 句柄注册）、D5b 冰神→四影→派蒙同步、D5c state 引用清理、F1 停服流程
- **R4**（9 查 / 2 真）：兼容层 vs SQL 迁移方案澄清、补本轮审查记录
- **R5**（7 查 / 4 真）：§2 地脉 / 原石行表述统一；live 测试按需；测试"跟随重写"改"同步新增+删除"
- **R6**（6 查 / 1 真）：补 §8 R5 记录
- **R7**（8 查 / 2 真）：D 阶段编号重排（D1-D10 规整）；`allowed_tools` 缺省策略补默认
- **R8**（8 查 / 4 真）：自检段上移为贯穿原则；生执"沉淀"改"重新设计"；E1 显式吸收 `llm/`；F 阶段加 "删 `llm/`" 步
- **R9**（7 查 / 4 真）：§7 完成判定修 F 阶段编号引用、补 `llm/` 删除；回滚段精确化到 D/E；风险表加"神之心吸收 llm/"条
- **R10**（9 查 / 2 真）：完成判定补"历史状态清理"；§8 编号语义修正
- **R11**（9 查 / 4 真）：§1 补 `commands.py` 单列；§3 "跨模块" 分类改"权限"；水神"拆 menxia"改"纯新建"；冰神运行时审查与预装免审拆两条
- **R12**（8 查 / 4 真）：§2 冰神行同步拆分表述；时执"归档"改"审计"；事件名 `llm.chat_complete` → `vision.chat_complete`；`executor` 枚举映射单值化
- **R13**（6 查 / 3 真）："前置询问机制"命名修正；C1 黑名单拆两层时序说明；完成判定命令节列出具体废弃项
- **R14**（7 查 / 1 真）：完成判定"推送"条目从"权限"节拆出独立节
- **R15**（6 查 / 3 真）：§8 子标题去死编号；A1 "空事件"改为接口描述；`.env` 扩展简化（复用现有 provider 配置）
- **R16**（7 查 / 0 真）：通读未发现真问题（均为轻微措辞）
- **R17**（7 查 / 2 真）：F 阶段补删 `workflow/` 整目录；§7 完成判定同步
- **R18 / R19 / R20**（各 7 查 / 0 真）：**连续 3 轮零真问题**，循环终止

#### 代码审计（外部工具）
105 个确认问题（P0:6 / P1:25 / P2:45 / P3:29），P0/P1 全部嵌入到对应 Phase 的待执行或验收条件中。详见 `fairy/.audit/report.md`。

---

> 各阶段落地时发现的新问题写入本文档对应 Phase 的待执行中跟踪。
