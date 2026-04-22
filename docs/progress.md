# 实现进度对照表

> 隶属：[神圣规划](aimon.md)
>
> 对照 docs/ 架构设计文档，梳理当前代码实现状态。
> 更新时间：2026-04-22

---

## 总览

| 状态 | 数量 | 说明 |
|------|------|------|
| 已实现 | 12 | 三频道、神之心、原石(服务层)、天使体系、意图分类、世界树、地脉、三月、四影(MVP)、草神(MVP)、守护进程、任务面板 |
| 部分实现 | 2 | 派蒙核心(权限/安全未做)、时执(压缩在Model中未独立) |
| 未开始 | 8 | 六神(火/雷/水/风/岩/冰)、权限体系、自进化 |

---

## 一、派蒙入口层 — `docs/paimon/paimon.md`

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 统一入口网关 | **已实现** | `paimon/core/chat.py` |
| 频道轻认证 | **已实现** | 各 `channel.py` + `middleware.py` |
| 会话管理 | **已实现** | `paimon/session.py` (数据走世界树) |
| 指令系统 | **已实现** | `paimon/core/commands.py` |
| 人格包装 | **已实现** | `templates/paimon.t` |
| 意图粗分类 | **已实现** | `paimon/core/intent.py` (chat/skill/complex) |
| 复杂任务路由 | **已实现** | `paimon/core/chat.py` → `run_shades_pipeline()` |
| `/task` 强制指令 | **已实现** | `paimon/core/commands.py` |
| 轻量安全过滤 | **未开始** | — |
| 权限查询/授权 | **未开始** | — |

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
| 工具系统 (exec/schedule/video_process/audio_process) | **已实现** | `paimon/tools/` + `tools/` |
| 魔女会桥 (失败→四影) | **未开始** | — |
| 现有 skills 迁移: bili/xhs/check | **已实现** | `skills/` |
| 现有 skills 迁移: web/dividend | **未开始** | — |

---

## 四、四影 (Track 2 骨架) — `paimon/shades/pipeline.py`

固定调用链：死执 → 生执 → 空执 → 七神 → 时执

### 4.1 死执 · Jonova (安全审查)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| LLM 安全审查 (pass/reject) | **已实现** | `paimon/shades/jonova.py` |
| DAG 批量敏感操作扫描 | **未开始** | — |
| 新 skill/插件审查 | **未开始** | — |

### 4.2 生执 · Naberius (任务编排)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| DAG 任务分解 | **已实现** | `paimon/shades/naberius.py` |
| 依赖环检测 | **未开始** | — |
| 多轮迭代控制 | **未开始** | — |
| 失败回滚 | **未开始** | — |

### 4.3 空执 · Asmoday (动态路由)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 子任务 → 七神路由 | **已实现** | `paimon/shades/asmoday.py` |
| 服务发现 | **未开始** | — |
| 故障切换 | **未开始** | — |
| 多任务并发 | **未开始** | — |

### 4.4 时执 · Istaroth (生命周期)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 上下文压缩 | **部分实现** | `paimon/llm/model.py` (嵌在 Model 中，未独立) |
| 任务归档 + 审计 | **已实现** | `paimon/shades/istaroth.py` |
| 会话超时管理 | **未开始** | — |
| 归档分层 (热/冷/过期) | **部分实现** | lifecycle_stage 更新，未做自动分层 |

---

## 五、七神 (Track 2 能力)

| 七神 | 核心能力 | 状态 | 实现位置 |
|------|----------|------|----------|
| 草神 · Nahida | 推理、知识整合、文书起草 | **已实现** (MVP) | `paimon/archons/nahida.py` |
| 火神 · Mavuika | Shell/代码执行、沙箱 | **未开始** | — |
| 雷神 · Raiden | 代码生成、自检 | **未开始** | — |
| 水神 · Furina | 评审、游戏信息 | **未开始** | — |
| 风神 · Venti | 新闻采集、推送 | **未开始** | — |
| 岩神 · Zhongli | 理财、红利股 | **未开始** | — |
| 冰神 · Tsaritsa | Skill 生态管理 | **未开始** | — |

---

## 六、基础设施层

### 6.1 神之心 · Gnosis (LLM 资源池)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| Provider 抽象 + 流式输出 | **已实现** | `paimon/llm/base.py` |
| Anthropic / OpenAI Provider | **已实现** | `paimon/llm/anthropic.py` + `openai.py` |
| Model 封装 (chat/压缩/标题/tool loop) | **已实现** | `paimon/llm/model.py` |
| 浅层/深层资源池 + 故障切换 | **已实现** | `paimon/foundation/gnosis.py` |

### 6.2 原石 · Primogem (Token 追踪 — 服务层)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 费率查表 + 缓存折扣 | **已实现** | `paimon/foundation/primogem.py` |
| 多维聚合 (component/purpose/时间/分布) | **已实现** | 同上 |
| Web 仪表盘 | **已实现** | `paimon/channels/webui/dashboard_html.py` |
| 数据落盘 | **已实现** | 走世界树 `token_*` API |

### 6.3 地脉 · Leyline (事件总线)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 全局事件总线 (asyncio.Queue) | **已实现** | `paimon/foundation/leyline.py` |
| 消息有序 + handler 异常隔离 | **已实现** | 同上 |
| 三月响铃 (march.ring) | **已实现** | bootstrap.py 订阅 |

### 6.4 世界树 · Irminsul (存储层)

全系统唯一存储层，10 个数据域。

| 数据域 | 状态 | 业务服务方 |
|--------|------|-----------|
| 用户授权记录 | **API 就绪** | 派蒙 (待接入) |
| Skill 生态声明 | **API 就绪** | 冰神 (待接入) |
| 知识库 | **API 就绪** | 草神 (待接入) |
| 记忆 | **API 就绪** | 草神 (待接入) |
| 活跃任务记录 | **已实现** | 四影管线 |
| Token 记录 | **已实现** | 原石 |
| 审计 / 归档 | **已实现** | 时执 |
| 理财数据 | **API 就绪** | 岩神 (待接入) |
| 聊天会话 | **已实现** | 派蒙 |
| 定时任务 | **已实现** | 三月 |

### 6.5 三月 · March (守护与调度)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 守护进程 (崩溃重启) | **已实现** | `main.py` entry() |
| 定时调度 (cron/interval/once) | **已实现** | `paimon/foundation/march.py` |
| 推送响铃 (定时触发) | **已实现** | 走地脉 march.ring → 派蒙投递 |
| 推送响铃 (事件触发) | **未开始** | — |
| 任务观测面板 | **已实现** | `paimon/channels/webui/tasks_html.py` |
| WebUI 推送通知 | **未开始** | send_text 为空实现 |
| 自检系统 | **未开始** | — |

---

## 七、跨模块机制

| 机制 | 文档 | 状态 |
|------|------|------|
| 权限体系 | `docs/permissions.md` | **未开始** |
| 自进化 | `docs/evolution.md` | **未开始** |

---

## 八、当前文件清单

```
main.py                              入口 + 守护进程
paimon/
  config.py                          全局配置
  log.py                             日志
  state.py                           运行时状态单例
  session.py                         会话管理 (数据走世界树)
  bootstrap.py                       启动组装 + 地脉订阅
  core/
    chat.py                          对话核心 + 四影管线入口
    commands.py                      指令系统
    intent.py                        意图粗分类
  llm/
    base.py                          Provider ABC
    anthropic.py / openai.py         LLM Provider
    model.py                         Model 封装 + tool calling loop
  angels/
    parser.py                        SKILL.md 解析器
    registry.py                      Skill 注册表
  shades/
    pipeline.py                      四影管线协调器
    jonova.py                        死执：安全审查
    naberius.py                      生执：DAG 分解
    asmoday.py                       空执：路由到七神
    istaroth.py                      时执：归档 + 审计
  archons/
    base.py                          Archon 基类
    nahida.py                        草神：推理 + 知识
  tools/
    base.py                          BaseTool + ToolContext
    registry.py                      工具注册表
    builtin/
      exec.py                        Shell 执行
      skill.py                       use_skill
      schedule.py                    定时任务管理
  foundation/
    gnosis.py                        神之心 (LLM 资源池)
    leyline.py                       地脉 (事件总线)
    march.py                         三月 (定时调度)
    primogem.py                      原石 (Token 服务层)
    irminsul/                        世界树 (10 域存储层)
      irminsul.py                    门面 (~50 个 API)
      _db.py                         Schema + 迁移
      _paths.py                      路径安全
      authz.py / skills.py / knowledge.py / memory.py
      task.py / token.py / audit.py / dividend.py
      session.py / schedule.py
  channels/
    base.py                          Channel ABC
    webui/                           WebUI (aiohttp + SSE + 仪表盘 + 任务面板)
    telegram/                        Telegram (aiogram)
    qq/                              QQ (qq-botpy)
tools/
  video_process.py                   MiMo 视频处理
  audio_process.py                   MiMo 音频处理
skills/
  bili/SKILL.md                      B站视频分析
  xhs/SKILL.md                      小红书内容分析
  check/SKILL.md                     多轮迭代审查
templates/
  paimon.t                           派蒙人格 prompt
```
