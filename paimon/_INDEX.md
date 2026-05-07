# paimon 代码索引

> **用途**：让分析工具 / Claude / 新人**只 read 必要文件**而不是全扫 283 个 .py。
> **不是**：产品架构文档（看 [docs/aimon.md](../docs/aimon.md) 神圣规划全图）。
>
> 本文件**只写代码定位 + 关键约束**，每模块 1-3 行。改动文件后顺手更新本表。

---

## 顶层入口

| 路径 | 一句话 | 关键 |
|---|---|---|
| `__main__.py` | 进程入口 + 三月守护进程式重启（指数退避 + 健康重置） | `entry()` / `main()` / `_install_signal_handlers` |
| `config.py` | pydantic Settings（所有 .env 配置；~40 项） | `Config` 类 / `provider`/`api_key`/`model` property |
| `state.py` | 全局 RuntimeState 单例（持各服务句柄） | `state = RuntimeState()` 全局共享 |
| `session.py` | SessionManager（内存缓存 + 落盘委托世界树） | `Session` / `SessionManager` |
| `log.py` | loguru 配置 | `setup_logging()` |

---

## bootstrap/ — 启动 phases

| 文件 | 职责 |
|---|---|
| `main.py` | `create_app(config)` 主入口；按顺序起 irminsul → gnosis → leyline → march → channels |
| `_phases.py` | 启动 phase（米哈游账号订阅 ensure / 红利 cron / 收集 cron 兜底） |
| `_handlers.py` | 订阅 `march.ring*` 事件（推送/cron 分派/[SELFCHECK] 等） |
| `_llm.py` | 启动时按 .env api_key 自动 seed LLM Profile（首次） |

---

## channels/ — 多渠道（QQ / Telegram / WebUI）

- `base.py` — `Channel` ABC + `IncomingMessage` + `ChannelReply`（统一契约）
- `_chunk.py` — `smart_chunk()` 跨渠道消息切分（markdown 友好边界）

| 子包 | 职责 | 关键 |
|---|---|---|
| `qq/` | QQ 频道（4 文件 channel/handlers/middleware/reply）；seq 窗口 290s + 5 条预算 | `QQChannel` |
| `telegram/` | TG 频道（4 文件，比 QQ 简单） | `TelegramChannel` |
| `webui/` | aiohttp + SSE | `WebUIChannel`（见下方 webui/ 详解） |

### webui/ 子结构

```
webui/
├── channel.py            主类（路由注册委托给 api/ 子包；默认 access_code 认证）
├── _login_html.py        登录页 HTML
├── _reply.py             WebUIChannelReply
├── push_hub.py           SSE 长连接消息扇出
├── theme/                THEME_COLORS / BASE_CSS / NAV_LINKS_CSS（共享样式常量）
├── api/                  18 个 handler（每面板 1-2 文件，路由统一通过 register_all_routes 注册）
│   ├── main.py           核心：/ /dashboard /api/auth /api/chat (SSE)
│   ├── authz.py /api/authz/answer
│   ├── feed.py / sentiment.py 风神
│   ├── wealth.py / wealth_user_watch.py / wealth_stock_subs.py 岩神
│   ├── game.py 水神游戏
│   ├── knowledge.py / knowledge_kb.py / knowledge_archives.py 草神
│   ├── llm.py 神之心
│   ├── plugins.py 冰神
│   ├── selfcheck.py 三月
│   ├── session.py 会话 CRUD
│   ├── tasks.py 任务面板
│   ├── push.py /api/push 长连接
│   └── token.py 原石
└── *_html/               7 个面板的 HTML/CSS/JS 字符串切片
    └── 形如 _xxx_css_1.py + _xxx_script_1.py + main.py（build_xxx_html）
```

> **⚠ 切片约束**：`_xxx_html/_xxx_script_N.py` 每片 ~450 行是**硬约束**——为 LLM 编辑 token 预算保留余量；**不要合并切片**。

---

## core/ — 派蒙入口业务

| 子包/文件 | 职责 | 关键 |
|---|---|---|
| `chat/entry.py` | `on_channel_message()` — 所有渠道消息总入口 | 权限答复 / 入口过滤 / 命令分流 / 意图分发 |
| `chat/_handler.py` | `run_session_chat()` — 闲聊/skill 路径 | tool loop |
| `chat/_persist.py` | 会话落盘 helper |  |
| `chat/_runtime.py` | `_require_runtime()` 模式：从 state 取 cfg/session_mgr/model |  |
| `chat/_prompt.py` | 系统提示词 |  |
| `chat/session.py` | 会话级 chat helper |  |
| `chat/shades_bridge.py` | 四影路径桥接 → `enter_shades_pipeline_background` |  |
| `commands/_dispatch.py` | `/cmd` 总分发器 | `dispatch_command()` |
| `commands/{session,task,subscribe,dividend,memory,selfcheck,stat,help}.py` | 各命令实现 | 一文件一命令 |
| `commands/task_index.py` / `task_workspace.py` | 任务编号缓存 / 任务工作区 |  |
| `intent.py` | LLM 意图分类 → complex/skill/chat | `classify_intent()` |
| `safety.py` | 敏感信息正则（密钥/卡号/身份证） | `detect_sensitive()` |
| `pre_filter.py` | 入口轻量安全过滤（shell danger/prompt injection；NFKC 归一化防绕过） | `pre_filter()` |
| `authz/` | 权限缓存（AuthzCache + 决策） |  |
| `memory_classifier/memory.py` | 记忆分类 + 重整（含 130 行 LLM prompt 内联） |  |

---

## foundation/ — 基础设施

### irminsul/ — 世界树（SQLite 唯一存储层）

```
irminsul/
├── irminsul.py           7 行 wrapper：from ._irminsul import Irminsul
├── _irminsul/            主类
│   ├── service.py        Irminsul 类 + 4 mixin 组合 + initialize/close
│   └── _basics.py / _runtime.py / _finance.py / _observability.py    166 个域方法分组
├── _db/                  _schema.sql + _migrations.py
└── 19 个域 Repo .py       authz / skill / knowledge / memory / task / token / audit /
                          dividend / dividend_event / user_watchlist / mihoyo / session /
                          schedule / subscription / feed_event / push_archive / selfcheck /
                          llm_profile / llm_route
```

> **⚠ Schema 约束**：task_subtasks/flow/progress 的 FK **没声明 ON DELETE CASCADE**，靠 `task.purge_expired()` 手动级联；新写清理路径要按顺序 progress→flow→subtasks→edicts。

### 其他 foundation 模块

| 路径 | 一句话 |
|---|---|
| `bg.py` | `bg(coro, label=...)` — fire-and-forget 任务防 GC + 异常可见 + shutdown 协作 |
| `march/service.py` | 三月女神：守护轮询（30s）+ 调度任务执行 + ring_event 推送限流 |
| `leyline/` | 全局事件总线（地脉，发布/订阅模式） |
| `gnosis/` | 神之心：LLM 资源池（shallow / deep concurrency 限流） |
| `primogem/` | 原石：token 统计 + 花费聚合（费率表 + 缓存折扣） |
| `selfcheck/_probes.py` | Quick 自检：9 组件秒级探针 |
| `selfcheck/_deep.py` | Deep 自检：调 check skill（默认 selfcheck_deep_hidden=True 隐藏入口；保留代码） |
| `digest/composer.py + prompts.py` | 通用摘要 prompt 工厂（venti/zhongli 都用） |
| `model_router.py` | LLM profile 路由（按 component+purpose 选 profile） |
| `task_workspace.py` | 任务产物目录 .paimon/workspace/<task_id>/ helper |

---

## archons/ — 七神（v6 解耦后：cron / 面板 / 概念归属；业务执行已转 shades/worker/）

`base.py` — `Archon` ABC + `_invoke_skill_workflow`（保留：venti/zhongli digest 等内部 LLM 调用仍用）

**A 类（保留非四影功能）：**

| 子包/文件 | 神 | 业务 |
|---|---|---|
| `venti/` | 风神 | 订阅采集 cron + LLM digest（订阅型 + 事件型）+ `/feed` 面板 + 站点登录代理（_LoginMixin）；execute 内部已删 |
| `venti_event/` | 风神 | L1 事件级舆情聚类（_LLM/_Process Mixin → EventClusterer） |
| `zhongli/` | 岩神 | 红利股扫描 + scorer + `/wealth` cron + watchlist + dividend cron；execute 内部已删 |
| `furina/` | 水神 | namespace 壳（archon 本体 review 段已删）；FurinaGameService 在 `furina_game/` |
| `furina_game/` | 水神 | 米哈游游戏（账号/签到/便笺/抽卡 + 6 mixin）；保留 |
| `nahida.py` | 草神 | namespace 壳；概念归属 `/knowledge` 面板（webui 直读 irminsul） |
| `tsaritsa.py` | 冰神 | namespace 壳；概念归属 `/plugins` 面板（webui 直读 skill_loader） |

**B 类（archon 本体暂无具体职能 / namespace 壳，待用户后续安排）：**

| 文件 | 神 | 状态 |
|---|---|---|
| `raiden.py` | 雷神 | namespace 壳，~30 行；原写代码 4 件套已转 worker/（design / code / simple_code） |
| `mavuika.py` | 火神 | namespace 壳，~30 行；原 exec tool-loop 已转 worker/（exec） |

---

## shades/ — 四影（流程框架）+ 工人（v6 新增）

| 路径 | 影 | 职责 |
|---|---|---|
| `pipeline/` | — | 主控（prepare 入口审 + execute DAG 跑） |
| `naberius/` | 生执 | DAG 拆分（assignee 字段值=stage 名）+ 拓扑 + 多轮迭代 + saga 补偿 |
| `jonova.py` | 死执 | 安全审（subject_type="stage"）+ plan 敏感扫 + 运行时 skill 审 |
| `asmoday.py` | 空执 | 动态路由（按 stage 派发到 `worker.run_stage`）+ gather 并发 + 故障切换 |
| `istaroth/` | 时执 | 活跃压缩 + 生命周期清扫 + 最终归档 |
| `worker/` | — | 9 stage 工人体系（spec/design/code/review_*/simple_code/exec/chat）；asmoday 通过 `run_stage` 派发 |

---

## skill_loader/ — Skill 加载器

| 文件 | 职责 |
|---|---|
| `registry.py` | skill 注册器（装载时 grep allowed_tools 派生 sensitivity） |
| `parser.py` | SKILL.md frontmatter 解析 |
| `watcher.py` | watchdog 热重载（默认关，`SKILLS_HOT_RELOAD=true` 启用） |

---

## morningstar/ — 天使体系（多视角讨论）

| 文件 | 职责 |
|---|---|
| `morningstar.py` | /agents 主入口：流式 reply + merge 主 session |
| `council.py` | 讨论循环：assemble → dispatch+speak loop → synthesize；含上限 / 死锁检测 |
| `roles.py` | 11 个协同天使 system prompt（结构性 5 / 评估性 4 / 对抗性 2） |
| `prompts.py` | 晨星 4 个 prompt：assemble / dispatch / speak / synthesize |

---

## llm/ — LLM 抽象

| 文件 | 职责 |
|---|---|
| `base.py` | `Model` ABC（chat / stream / count_tokens） |
| `anthropic_client.py` | Claude 实现（小米内网 / 官方两套 base_url） |
| `openai_client.py` | OpenAI 兼容（含 deepseek-pro / deepseek-flash 双档） |

---

## tools/ — 内置工具

| 文件 | 职责 |
|---|---|
| `base.py` / `registry.py` | `BaseTool` + `ToolRegistry` |
| `builtin/exec.py` | shell 执行（黑名单防破坏 + cwd 强制项目根 + audit；ask_user 授权） |
| `builtin/file_ops.py` | 读写文件（路径白名单 SEC-003） |
| `builtin/glob_tool.py` | 跨平台文件通配（兼容 Windows） |
| `builtin/web_fetch.py` | URL 抓取 |
| `builtin/knowledge.py` | 知识库读写 |
| `builtin/memory_tool.py` | 记忆 CRUD |
| `builtin/schedule.py` | 定时任务 CRUD |
| `builtin/skill_manage.py` / `skill.py` | skill 元操作 |
| `builtin/dividend.py` | 红利数据查询 |
| `builtin/subscribe.py` | 订阅 CRUD |

`tools/audio_process.py` / `video_process.py` — 音视频处理（被 bili skill 用）

---

## 跨模块约束速查

| 约束 | 出处 |
|---|---|
| **派蒙是唯一渠道出入口**：三月/七神/死执都不直接调 channel | docs/aimon.md §响应流 |
| **世界树是唯一存储层**：其他模块不自建 SQLite/文件库 | docs/aimon.md §一 |
| **`bg(coro)` 是唯一 fire-and-forget 入口**：直接 `asyncio.create_task` 任务可能被 GC | foundation/bg.py |
| **task FK 无 ON DELETE CASCADE**：手动 progress→flow→subtasks→edicts 顺序 | irminsul/_db/_schema.sql |
| **webui _xxx_html 切片 ≤ 450 行**：LLM 编辑 token 预算约束 | (本约束) |
| **selfcheck Deep 默认隐藏**：mimo-v2-omni 跑不动 N+M+K；保留代码待 Opus 启用 | config.py: `selfcheck_deep_hidden=True` |

---

## 模块依赖速记（高层）

```
__main__ → bootstrap → 各服务初始化
       ↓
渠道层 (qq/tg/webui) → core.chat.entry → core.intent
                              ↓
                  ├─ chat: model 直接答
                  ├─ skill: angels.registry → core.chat._handler
                  └─ complex: shades.pipeline → archons.* (subprocess skill)
                                    ↑
                  全部读写都经 → foundation.irminsul（世界树）
                  全部 LLM 都经 → foundation.gnosis + llm.*
                  全部后台 task → foundation.bg
                  调度 / 推送响铃 → foundation.march
```

---

更新原则：**目录/文件搬动后要改本表**。本表只记代码定位，不记产品概念（产品概念归 docs/）。
