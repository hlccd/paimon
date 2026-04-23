# 实现进度对照表

> 隶属：[神圣规划](aimon.md)
>
> 对照 docs/ 架构设计文档，梳理当前代码实现状态。
> 更新时间：2026-04-24

---

## 总览

| 状态 | 数量 | 说明 |
|------|------|------|
| 已实现 | 28 | 三频道、神之心、原石、天使体系、意图分类、世界树、地脉、三月、守护进程、任务面板、**四影闭环（含多轮/DAG/并发/saga/批量授权）**、七神全部(MVP)、**权限体系(含四影路径批量)**、**WebUI 推送链路**、**插件面板**、**魔女会桥+天使超时**、**时执压缩(4 项改进)**、**L1 记忆系统**、**偏好面板**、**派蒙入口安全过滤**、**三月事件响铃** |
| 部分实现 | 0 | — |
| 未开始 | 1 | 自进化 |

---

## 一、派蒙入口层 — `docs/paimon/paimon.md`

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 统一入口网关 | **已实现** | `paimon/core/chat.py` |
| 频道轻认证 | **已实现** | 各 `channel.py` + `middleware.py` |
| 会话管理 | **已实现** | `paimon/session.py` (数据走世界树) |
| 指令系统 | **已实现** | `paimon/core/commands.py` |
| 人格包装 | **已实现** | `templates/paimon.t` |
| 意图粗分类 | **已实现** | `paimon/core/intent.py` (chat/skill/complex) + 规则引擎前置 + LLM 兜底 + skill 二次校验 |
| 复杂任务路由 | **已实现** | `paimon/core/chat.py` → `run_shades_pipeline()` |
| `/task` 强制指令 | **已实现** | `paimon/core/commands.py` |
| 轻量安全过滤 | **已实现** | `paimon/core/pre_filter.py` (两档：shell_danger=block / prompt_injection=warn 放行；写 audit `input_filtered`) |
| 权限查询/授权 | **已实现** | `paimon/core/authz/` + `Channel.ask_user` + 世界树 authz 域 |

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
| 天使超时保护 (单 tool 30s / 总 3min) | **已实现** | `paimon/core/chat.py` + `paimon/config.py` |
| 魔女会桥 (失败→四影) | **已实现** | `paimon/angels/nicole.py` |
| 现有 skills 迁移: bili/xhs/check | **已实现** | `skills/` |
| 现有 skills 迁移: web/dividend | **未开始** | — |

---

## 四、四影 (Track 2 骨架) — `paimon/shades/pipeline.py`

固定调用链：死执 → 生执 → 空执 → 七神 → 时执

### 4.1 死执 · Jonova (安全审查)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| LLM 安全审查 (pass/reject) | **已实现** | `paimon/shades/jonova.py` |
| DAG 批量敏感操作扫描 | **已实现** | `jonova.scan_plan` + `ScanItem/ScanResult` + `format_scan_prompt`；pipeline `_batch_authorize` 串联派蒙批量询问 |
| 新 skill/插件审查 | **已实现** | `jonova.review_skill_declaration` + 冰神热加载 watchdog 挂接 |

### 4.2 生执 · Naberius (任务编排)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| DAG 任务分解（deps/多轮） | **已实现** | `paimon/shades/naberius.py` + `_plan.Plan`；`plan(round=N)` 支持 round≥2 修订 + preserved 节点跳过 re-INSERT |
| 依赖环检测 | **已实现** | `_plan.detect_cycle` DFS 三色；第一轮降级线性+审计，第二轮再出环硬失败 |
| 多轮迭代控制 | **已实现** | `SHADES_MAX_ROUNDS=3`；pipeline 按 verdict 回炉 + 水神结构化三级裁决；失败节点改派引导 |
| 失败回滚 | **已实现** | `_saga.run_compensations` 反序执行 `Subtask.compensate`；交火神 archon 落地 |

### 4.3 空执 · Asmoday (动态路由)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 子任务 → 七神路由 | **已实现** | `paimon/shades/asmoday.py` |
| 多任务并发 | **已实现** | Kahn 拓扑分层 + `asyncio.gather`；preserved completed 节点预灌 results 不重跑 |
| 故障切换 (MVP) | **已实现** | `_run_one` 重试 1 次 + 两次败后 `mark_downstream_skipped` 传播；改派由生执修订路径完成 |
| 服务发现 | **未开始** | 当前 `_ARCHON_REGISTRY` 静态注册，新 archon 需重启 |

### 4.4 时执 · Istaroth (生命周期)

| 规划职责 | 状态 | 实现位置 |
|----------|------|----------|
| 上下文压缩 | **已实现** | `paimon/shades/istaroth.py` (时执接管 + 4 项改进：阈值公式 / tool pair 补齐 / Prompt 升级 / 熔断) |
| 任务归档 + 审计 | **已实现** | `istaroth.archive` 含 `failure_reason` + `rounds`；成功 / 失败 / 拒绝路径都归档 |
| 会话超时管理 | **未开始** | — |
| 归档分层 (热/冷/过期) | **部分实现** | lifecycle_stage 更新，未做自动分层 |

---

## 五、七神 (Track 2 能力)

| 七神 | 核心能力 | 状态 | 实现位置 |
|------|----------|------|----------|
| 草神 · Nahida | 推理、知识整合、文书起草 | **已实现** (MVP) | `paimon/archons/nahida.py` |
| 雷神 · Raiden | 代码生成、自检 | **已实现** (MVP) | `paimon/archons/raiden.py` |
| 水神 · Furina | 评审、游戏信息 | **已实现** (MVP) | `paimon/archons/furina.py` |
| 火神 · Mavuika | Shell/代码执行、部署 | **已实现** (MVP) | `paimon/archons/mavuika.py` |
| 风神 · Venti | 新闻采集、舆情分析 | **已实现** (MVP) | `paimon/archons/venti.py` |
| 岩神 · Zhongli | 理财、红利股 | **已实现** (MVP) | `paimon/archons/zhongli.py` |
| 冰神 · Tsaritsa | Skill 生态管理 | **已实现** (MVP) | `paimon/archons/tsaritsa.py` |

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
| 用户授权记录 | **已接入** | 派蒙 `paimon/core/authz/` + 启动灌缓存 + 运行时写入 |
| Skill 生态声明 | **已接入** | 冰神启动 sync_to_irminsul 写入 skill_declarations（builtin 源） |
| 知识库 | **API 就绪** | 草神 (待接入) |
| 记忆 | **已接入** | 时执压缩提取 `extract_experience` + 派蒙入口 `_load_l1_memories` 预取 + `/remember` 命令 + 草神按需查 + **草神·偏好面板**（user/feedback 查看+删除） |
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
| 定时调度 (cron/interval/once) | **已实现** | `paimon/foundation/march.py` (按分钟 :00 对齐轮询) |
| 推送响铃 (定时触发) | **已实现** | 走地脉 march.ring → 派蒙投递 |
| 推送响铃 (事件触发) | **已实现** | `MarchService.ring_event`（含 60s/10 条限流 + audit `march_ring_event`；派蒙侧 zero-change 复用 march.ring 订阅） |
| 任务观测面板 | **已实现** | `paimon/channels/webui/tasks_html.py` |
| WebUI 推送通知 | **已实现** | `send_text` / `send_file` 落推送会话 + PushHub 扇出 SSE；QQ 因 API 限制关闭 |
| 自检系统 | **未开始** | — |

---

## 七、跨模块机制

| 机制 | 文档 | 状态 |
|------|------|------|
| 权限体系 | `docs/permissions.md` | **已实现** — 天使路径单项询问 + 四影路径 DAG 批量扫描/询问均已贯通（`classify_batch_reply` 21 种答复模式 + `scan_plan` subject 粒度 `shades_node`）；冰神·插件面板可查/撤 |
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
    chat.py                          对话核心 + 四影管线入口 + 天使路径权限闸
    commands.py                      指令系统
    intent.py                        意图粗分类（规则引擎前置 + LLM 兜底 + skill 二次校验）
    authz/
      __init__.py                    授权体系门面
      sensitive_tools.py             工具敏感清单 + 装载时派生
      keywords.py                    用户答复关键词识别（"永久/以后都..."）
      cache.py                       授权本地缓存（启动灌 + 运行时写）
      decision.py                    天使路径决策树
  llm/
    base.py                          Provider ABC
    anthropic.py / openai.py         LLM Provider
    model.py                         Model 封装 + tool calling loop
  angels/
    parser.py                        SKILL.md 解析器
    registry.py                      Skill 注册表
  shades/
    pipeline.py                      四影管线协调器（三环闭环：入口审 / 主循环 / 归档+saga）
    jonova.py                        死执：安全审查 + DAG 敏感扫描（scan_plan） + skill 声明审查
    naberius.py                      生执：DAG 多轮编排 + 依赖环检测 + 失败改派引导
    asmoday.py                       空执：拓扑分层 gather + 单节点重试 + 下游 skip 传播
    istaroth.py                      时执：归档 + 审计（含 failure_reason/rounds）
    _plan.py                         Plan 数据类 + Kahn/DFS 图算法（环检测/分层/线性化）
    _verdict.py                      水神三级裁决 JSON 解析（pass/revise/redo 容错降级）
    _saga.py                         Saga 轻量补偿（反序 compensate，火神执行）
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
    base.py                          Channel ABC（含 supports_push 能力声明 + ask_user 交互式询问）
    webui/                           WebUI (aiohttp + SSE + 仪表盘 + 任务面板 + 插件面板)
      push_hub.py                    推送扇出器（支持多标签 fan-out）
      plugins_html.py                冰神·插件面板（skill 生态 + 永久授权 tab）
    telegram/                        Telegram (aiogram)
    qq/                              QQ (qq-botpy, supports_push=False)
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
