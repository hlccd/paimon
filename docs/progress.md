# 实现进度对照表

> 隶属：[神圣规划](aimon.md)
>
> 对照 docs/ 架构设计文档，梳理当前代码实现状态。
> 更新时间：2026-04-22

> **架构变更通告（2026-04-22）**：世界树从 peer 支撑模块升级为**全系统唯一存储层**，原石 / 时执 / 岩神 / 派蒙会话等所有持久化数据统一走世界树 API。详见 [aimon.md §存储/服务分层原则](aimon.md) 和 [irminsul.md](foundation/irminsul.md)。
> 本次变更尚未落代码；原石当前仍自持 SQLite，后续实现世界树时需一并重构。

---

## 总览

| 状态 | 数量 | 说明 |
|------|------|------|
| 已实现 | 7 | 三频道、神之心、原石(待重构为服务层)、天使体系(部分)、意图粗分类 |
| 部分实现 | 2 | 派蒙核心、时执(上下文压缩) |
| 未开始 | 13 | 世界树、四影、七神、地脉、三月、权限、进化 |

---

## 一、派蒙入口层 — `docs/paimon/paimon.md`

| 规划职责 | 状态 | 实现位置 | 备注 |
|----------|------|----------|------|
| 统一入口网关 | **已实现** | `paimon/core/chat.py` | 所有频道消息汇入 `on_channel_message()` |
| 频道轻认证 | **已实现** | 各 `channel.py` + `middleware.py` | WebUI ACCESS_CODE、TG OWNER_ID、QQ OWNER_IDS |
| 会话管理 | **已实现**（待迁世界树） | `paimon/session.py` | 当前 JSON 文件持久化，绑定 channel_key；架构升级后需迁入世界树 `sessions` 表 |
| 指令系统 | **已实现** | `paimon/core/commands.py` | /new /sessions /switch /stop /clear /rename /delete /stat /help |
| 人格包装 | **已实现** | `templates/paimon.t` | 系统 prompt 每轮注入 |
| 意图粗分类 | **已实现** | `paimon/core/intent.py` | 三分类：chat / skill:<name> / complex |
| 轻量安全过滤 | **未开始** | — | 关键词过滤、恶意参数拦截 |
| 天使调度 | **未开始** | — | skill 匹配 → 天使执行 → 30s 超时 |
| 任务路由 | **未开始** | — | `/task` 指令、复杂任务 → 四影 |
| 权限查询/授权 | **未开始** | — | 本地缓存 + 世界树永久授权 |

---

## 二、频道层

| 频道 | 状态 | 实现位置 |
|------|------|----------|
| WebUI (aiohttp + SSE) | **已实现** | `paimon/channels/webui/` |
| Telegram (aiogram) | **已实现** | `paimon/channels/telegram/` |
| QQ (qq-botpy) | **已实现** | `paimon/channels/qq/` |

---

## 三、天使体系 (Track 1) — `docs/angels/angels.md`

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| Skill 解析器 (SKILL.md YAML) | **已实现** | `paimon/angels/parser.py` |
| Skill 注册表 | **已实现** | `paimon/angels/registry.py` |
| 天使调度器 (tool calling loop) | **已实现** | `paimon/llm/model.py` + `paimon/core/commands.py` |
| 工具系统 (exec/video_process/audio_process) | **已实现** | `paimon/tools/` + `tools/` |
| 魔女会桥 (失败→四影) | **未开始** | — |
| 现有 skills 迁移: bili/xhs | **已实现** | `skills/bili/` + `skills/xhs/` |
| 现有 skills 迁移: web/dividend | **未开始** | — |

---

## 四、四影 (Track 2 骨架)

### 4.1 死执 · Jonova (安全审查) — `docs/shades/jonova.md`

| 规划职责 | 状态 |
|----------|------|
| LLM 深度内容审查 | **未开始** |
| 提权拦截 | **未开始** |
| 规则合规检查 | **未开始** |
| DAG 批量敏感操作扫描 | **未开始** |
| 新 skill/插件审查 | **未开始** |

### 4.2 生执 · Naberius (任务编排) — `docs/shades/naberius.md`

| 规划职责 | 状态 |
|----------|------|
| DAG 任务分解 | **未开始** |
| 依赖环检测 | **未开始** |
| 多轮迭代控制 | **未开始** |
| 失败回滚 | **未开始** |

### 4.3 空执 · Asmoday (动态路由) — `docs/shades/asmoday.md`

| 规划职责 | 状态 |
|----------|------|
| 子任务 → 七神路由 | **未开始** |
| 服务发现 | **未开始** |
| 故障切换 | **未开始** |
| 多任务并发 | **未开始** |

### 4.4 时执 · Istaroth (生命周期) — `docs/shades/istaroth.md`

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 上下文压缩 | **部分实现** | `paimon/llm/model.py` `compress_session_context()` |
| 会话超时管理 | **未开始** | — |
| 归档分层 (热/冷/过期) | **未开始** | — |
| 审计复盘 | **未开始** | — |

> 注：上下文压缩目前嵌在 Model 类中，尚未作为独立的时执模块存在。

---

## 五、七神 (Track 2 能力)

| 七神 | 文档 | 核心能力 | 状态 |
|------|------|----------|------|
| 草神 · Nahida | `docs/archons/nahida.md` | 推理、知识整合、方案起草、偏好管理 | **未开始** |
| 火神 · Mavuika | `docs/archons/mavuika.md` | Shell/代码执行、沙箱、技术重试 | **未开始** |
| 雷神 · Raiden | `docs/archons/raiden.md` | 代码生成、自检 | **未开始** |
| 水神 · Furina | `docs/archons/furina.md` | 评审、游戏信息 | **未开始** |
| 风神 · Venti | `docs/archons/venti.md` | 新闻采集、推送 | **未开始** |
| 岩神 · Zhongli | `docs/archons/zhongli.md` | 理财、红利股、资产管理 | **未开始** |
| 冰神 · Tsaritsa | `docs/archons/tsar.md` | Skill 生态管理、AI 自举 | **未开始** |

---

## 六、基础设施层

### 6.1 神之心 · Gnosis (LLM) — `docs/foundation/gnosis.md`

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| Provider 抽象 + 流式输出 | **已实现** | `paimon/llm/base.py` |
| Anthropic Provider | **已实现** | `paimon/llm/anthropic.py` |
| OpenAI Provider | **已实现** | `paimon/llm/openai.py` |
| Model 封装 (chat/压缩/标题) | **已实现** | `paimon/llm/model.py` |
| MiMo 配置预留 | **已实现** | `paimon/config.py` |
| 浅层/深层资源池 | **已实现** | `paimon/foundation/gnosis.py` |
| 非抢占式调度 | **已实现** | 同上 (Semaphore 并发控制) |
| 负载均衡 + 故障切换 | **已实现** | 同上 (健康检查 + 自动切换) |

### 6.2 原石 · Primogem (Token 追踪) — `docs/foundation/primogem.md`

> **架构升级（2026-04-22）**：原石定位为服务层，SQLite 持久化职责将剥离到世界树的 `token_*` 域；下表中"SQLite 持久化记录"行在世界树落地后需搬迁。其他业务逻辑（费率、聚合、dashboard）留原石不变。

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| SQLite 持久化记录（待剥离） | **已实现** | `paimon/foundation/primogem.py`（世界树落地后迁移） |
| 缓存 token 明细 (写入/命中) | **已实现** | 同上 |
| 缓存感知费用估算 | **已实现** | 同上 |
| 按 component 聚合 | **已实现** | 同上 |
| 按 session 聚合 | **已实现** | 同上 |
| /stat 指令展示 | **已实现** | `paimon/core/commands.py` |
| 双维度标签 (module + purpose) | **已实现** | `paimon/foundation/primogem.py` |
| 按时间段聚合 (日/周/月) | **已实现** | 同上 `get_timeline_stats()` |
| Web 面板集成 | **已实现** | `paimon/channels/webui/dashboard_html.py` |

### 6.3 地脉 · Leyline (事件总线) — `docs/foundation/leyline.md`

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 全局事件总线 | **已实现** | `paimon/foundation/leyline.py` |
| 消息有序保证 | **已实现** | 同上（单 Queue 顺序消费） |
| 异常日志广播 | **已实现** | 同上（handler 异常自动广播 `error.log` topic） |

### 6.4 世界树 · Irminsul (存储层) — `docs/foundation/irminsul.md`

> **架构升级（2026-04-22）**：世界树为**全系统唯一存储层**，持有 9 个数据域。其他所有模块（含原石 / 时执 / 岩神 / 派蒙会话）为服务层，数据落盘统一走世界树 API。

| 数据域 | 状态 | 业务服务方 |
|---|---|---|
| 用户授权记录 | **未开始** | 派蒙 / 草神面板 |
| Skill 生态声明 | **未开始** | 冰神 |
| 知识库 | **未开始** | 草神 |
| 记忆（含个人偏好/习惯） | **未开始** | 草神 |
| 活跃任务记录 | **未开始** | 生执 / 空执 / 七神 |
| Token 记录 | **部分**（服务层已有，待剥离 DB） | 原石 |
| 审计 / 归档 | **未开始** | 时执 |
| 理财数据 | **未开始** | 岩神 |
| 聊天会话 | **部分**（当前派蒙自持 JSON，待迁移） | 派蒙 |
| 通用能力：路径安全 / 写入日志 / snapshot | **未开始** | 世界树自身 |

### 6.5 三月 · March (守护) — `docs/foundation/march.md`

| 规划职责 | 状态 |
|----------|------|
| 守护进程 (崩溃恢复) | **未开始** |
| 定时调度 (cron) | **未开始** |
| 推送响铃 (定时+事件) | **未开始** |
| 自检系统 | **未开始** |
| 任务观测面板 | **未开始** |
| 测试基础设施 | **未开始** |

---

## 七、跨模块机制

| 机制 | 文档 | 状态 |
|------|------|------|
| 权限体系 | `docs/permissions.md` | **未开始** |
| 自进化 | `docs/evolution.md` | **未开始** |

---

## 八、当前已实现的文件清单

```
main.py                              入口
paimon/
  __init__.py, __main__.py           包定义
  config.py                          全局配置 (pydantic-settings)
  log.py                             日志 (loguru)
  state.py                           运行时状态单例
  session.py                         会话模型 + JSON 持久化
  bootstrap.py                       启动组装
  core/
    __init__.py
    chat.py                          对话核心 (入口/流式/压缩/标题)
    commands.py                      指令系统 (9条指令)
  llm/
    __init__.py
    base.py                          Provider ABC + StreamChunk
    anthropic.py                     Anthropic Provider
    openai.py                        OpenAI Provider
    model.py                         Model 封装
  angels/
    __init__.py
    parser.py                        SKILL.md 解析器
    registry.py                      Skill 注册表
  tools/
    __init__.py
    base.py                          BaseTool ABC + ToolContext
    registry.py                      工具注册表
    builtin/
      __init__.py
      exec.py                        Shell 执行工具
      skill.py                       use_skill 工具
  foundation/
    __init__.py
    gnosis.py                        神之心 (LLM 资源池管理)
    primogem.py                      原石 (SQLite token 追踪)
  channels/
    __init__.py
    base.py                          Channel ABC
    webui/                           WebUI 频道 (aiohttp + SSE)
    telegram/                        Telegram 频道 (aiogram)
    qq/                              QQ 频道 (qq-botpy)
tools/
  video_process.py                   MiMo 视频处理 (外部工具)
  audio_process.py                   MiMo 音频处理 (外部工具)
skills/
  bili/SKILL.md                      B站视频分析 Skill
  xhs/SKILL.md                       小红书内容分析 Skill
templates/
  paimon.t                           派蒙人格 prompt
```

---

## 九、建议的下一步优先级（2026-04-22 修订）

架构升级后优先级重排：

1. **世界树 · 存储层骨架** — 9 个域的 API、schema、路径安全、写入日志；是后续权限/授权/skill声明/记忆/任务一切的前置（本次工作重点）
2. **原石重构为服务层** — 剥离 `primogem.py` 的 DB 代码，改为调世界树 `token_*` API，作为服务层改造的首个样本
3. **派蒙会话迁移** — 把 `paimon_home/sessions/*.json` 导入世界树 `sessions` 表
4. **权限询问 MVP** — 派蒙本地缓存 + 单项询问 + "永久"关键词识别（靠世界树 authz 域）
5. **地脉事件总线** — 后续服务层之间通信的基础
6. **天使 30s 超时 + 魔女会桥** — 天使体系收尾
