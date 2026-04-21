# 实现进度对照表

> 隶属：[神圣规划](aimon.md)
>
> 对照 docs/ 架构设计文档，梳理当前代码实现状态。
> 更新时间：2026-04-21

---

## 总览

| 状态 | 数量 | 说明 |
|------|------|------|
| 已实现 | 5 | 三频道、神之心、原石 |
| 部分实现 | 2 | 派蒙核心、时执(上下文压缩) |
| 未开始 | 14 | 天使体系、四影、七神、地脉、世界树、三月、权限、进化 |

---

## 一、派蒙入口层 — `docs/paimon/paimon.md`

| 规划职责 | 状态 | 实现位置 | 备注 |
|----------|------|----------|------|
| 统一入口网关 | **已实现** | `paimon/core/chat.py` | 所有频道消息汇入 `on_channel_message()` |
| 频道轻认证 | **已实现** | 各 `channel.py` + `middleware.py` | WebUI ACCESS_CODE、TG OWNER_ID、QQ OWNER_IDS |
| 会话管理 | **已实现** | `paimon/session.py` | JSON 文件持久化，绑定 channel_key |
| 指令系统 | **已实现** | `paimon/core/commands.py` | /new /sessions /switch /stop /clear /rename /delete /stat /help |
| 人格包装 | **已实现** | `templates/paimon.t` | 系统 prompt 每轮注入 |
| 意图粗分类 | **未开始** | — | 三分类：闲聊 / 简单任务 / 复杂任务 |
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

| 规划职责 | 状态 |
|----------|------|
| Skill 解析器 (SKILL.md YAML) | **未开始** |
| Skill 注册表 | **未开始** |
| 天使调度器 | **未开始** |
| 魔女会桥 (失败→四影) | **未开始** |
| 现有 skills 迁移 (bili/xhs/web/dividend) | **未开始** |

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

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| SQLite 持久化记录 | **已实现** | `paimon/foundation/primogem.py` |
| 缓存 token 明细 (写入/命中) | **已实现** | 同上 |
| 缓存感知费用估算 | **已实现** | 同上 |
| 按 component 聚合 | **已实现** | 同上 |
| 按 session 聚合 | **已实现** | 同上 |
| /stat 指令展示 | **已实现** | `paimon/core/commands.py` |
| 双维度标签 (module + purpose) | **已实现** | `paimon/foundation/primogem.py` |
| 按时间段聚合 (日/周/月) | **已实现** | 同上 `get_timeline_stats()` |
| Web 面板集成 | **已实现** | `paimon/channels/webui/dashboard_html.py` |

### 6.3 地脉 · Leyline (事件总线) — `docs/foundation/leyline.md`

| 规划职责 | 状态 |
|----------|------|
| 全局事件总线 | **未开始** |
| 消息有序保证 | **未开始** |
| 异常日志广播 | **未开始** |

### 6.4 世界树 · Irminsul (存储) — `docs/foundation/irminsul.md`

| 规划职责 | 状态 |
|----------|------|
| 知识持久化 | **未开始** |
| 缓存层 | **未开始** |
| Skill 注册表 | **未开始** |
| 用户授权记录 | **未开始** |
| 数据域访问控制 | **未开始** |

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
templates/
  paimon.t                           派蒙人格 prompt
```

---

## 九、建议的下一步优先级

基于当前进度和依赖关系：

1. **工具系统 + tool calling loop** — Model 层补齐工具调用循环，这是天使体系和七神的前置
2. **天使体系 (Skill)** — 解析器 + 注册表 + 调度器，让派蒙能"做事"
3. **意图分类** — 区分闲聊/简单任务/复杂任务，接入天使路由
4. **地脉事件总线** — 后续所有模块间通信的基础
5. **世界树存储** — 知识/任务/授权的统一持久化
