# 待办项 / 下一步

> 隶属：[神圣规划](aimon.md)
>
> 只记录**尚未实现 / 待完善**的事项。已完成项请查 git log / 归档文档。更新时间：2026-04-29

每一条都已对照源码核过一遍；"部分实装"一栏列出哪些已做、哪些没做、哪些是主动舍弃的设计决策。

## 1. 职能层面

- [ ] **定时任务类型一等公民化（方案 D）** —— 2026-04-29 起草
  - **背景**：风神订阅采集（`[FEED_COLLECT] <sub_id>`）和岩神红利扫描（`[DIVIDEND_SCAN] <mode>`）都是 `scheduled_tasks` 表里的真·cron 任务，但在 `task_prompt` 用魔法前缀编码路由信息，导致 /tasks 面板和 /tasks 命令都要在 [`channel.py:1714`](../paimon/channels/webui/channel.py#L1714) 和 [`commands.py:310`](../paimon/core/commands.py#L310) 两处 startswith 过滤把它们藏起来。副作用：全局定时任务不可盘点、故障可见性分散（/tasks 本可聚合 consecutive_failures 告警但看不到这两类）、未来每加一类周期任务都要记得两处改过滤
  - **目标**：`task_prompt` 回归纯用户自然语言；路由信息走 schema 新字段 `task_type` + `source_entity_id`；分派走 `TaskTypeRegistry` 注册模式
  - **改动**（详细设计见对话记录）：
    - 世界树 `scheduled_tasks` 加 `task_type TEXT DEFAULT 'user'` + `source_entity_id TEXT DEFAULT ''` + type 索引；幂等 backfill 老数据
    - 新模块 [`paimon/foundation/task_types.py`](../paimon/foundation/task_types.py)：`TaskTypeMeta` dataclass（含 display_label/icon/manager_panel/description_builder/anchor_builder/dispatcher）+ `register()` / `get()` / `all_types()` 注册表
    - 每个 archon 在自己模块加 `register_task_types()`：风神注册 `feed_collect`、岩神注册 `dividend_scan`；bootstrap 启动时统一调一轮
    - [`bootstrap._on_march_ring`](../paimon/bootstrap.py#L336) 改为：拉完整 ScheduledTask → 非 user 类型查 registry 调 dispatcher；unknown type 只 warn 不 fallback LLM（防止 `[FEED_COLLECT] xxx` 被误喂 LLM）
    - [`channel.py:1700`](../paimon/channels/webui/channel.py#L1700) `tasks_api` 删过滤 + 为 `task_type != 'user'` 的行注入 `source` 元信息（含 description_builder 异步查出的实时描述 + jump_url）
    - [`tasks_html.py`](../paimon/channels/webui/tasks_html.py) 内部任务行：chip（如"风神订阅"）+ 描述 + 启停/编辑/删除按钮 disabled + tooltip"在 /feed 面板管理" + 行点击跳 `manager_panel#anchor`
    - [`feed_html.py`](../paimon/channels/webui/feed_html.py) 订阅卡加 `data-sub-id` 属性 + scroll-to-hash 脚本（支持 `/feed#sub-abc123` 定位到特定订阅卡）；/wealth 单面板不需 anchor
    - `/subscribe` 和 `/dividend on` 的 `schedule_create` 调用改为传 `task_type` + `source_entity_id`，不再拼 `[PREFIX]` 前缀
    - 撤销 commands.py 和 channel.py 两处前缀过滤；撤销 bootstrap 两处 startswith 分派
  - **未来扩展硬约束**：
    - 任何新神 / 新面板要加周期任务（草神日报、水神评审、任何新的周期采集），**必须**在对应 archon 模块定义唯一 `task_type` 字符串 + 实装 `register_task_types()` + bootstrap 加一行注册调用；对应面板支持 anchor 跳转（如果有多个业务 entity）
    - **禁止**在 `task_prompt` 里塞 `[PREFIX]` 编码（此路 2026-04-29 后废）
    - 新加 task_type 自动在 /tasks 面板获得 chip + 跳转 + 禁用编辑 —— registry 承诺
  - **估算**：实装 2-3h + 手动回归测试 1h（/subscribe 创建 → /tasks 看到 chip + 描述 → 点跳转 /feed → 删订阅 /tasks 同步消失）；schema 向后兼容，回滚安全

- [ ] **推送策略深化**
  - **已做**：`march.ring_event` 60s/10 次滑窗限流（非 dedup 路径） + `dedup_per_day=True` 日级 upsert + `push_archive` 持久化 + 审计事件 `march_ring_event` + leyline `push.archived` publish + PushHub 进程内 SSE 扇出（满队丢最早） + level 字段预留 `'silent'|'loud'`
  - **未做**：
    - `level='loud'` 的实际打断 UX —— 全仓消费者把 level 当字段存取，但没有任何路径对 `loud` 做差异化（读出来丢前端后前端也没用）
    - 多事件响铃并发时的优先级仲裁（目前 FIFO）
    - 派蒙 crash 后的积压重播（push_hub 内存队列丢失，push_archive 持久化但未读状态不保证按时序重放）
    - 按 source 分级的频率策略（所有 source 共享同一个 60s/10 次窗口）

- [ ] **三月·自检 Deep 暂缓**
  - 底层 `SelfCheckService.run_deep / _invoke_check_skill / _progress_watcher` 全部实装；[`config.py:124`](../paimon/config.py#L124) `selfcheck_deep_hidden=True` 默认隐藏 + [`selfcheck_html.py:639`](../paimon/channels/webui/selfcheck_html.py#L639) 按 deep_hidden 关按钮 + Deep Tab + `[SELFCHECK_DEEP]` cron 分派已撤销（[`bootstrap.py:362`](../paimon/bootstrap.py#L362)）
  - **卡点**：当前 mimo-v2-omni 对 check skill 的 N+M+K 多轮迭代执行不充分（单轮 ~30s 就返回简短 finding 停止），跑不出可靠体检
  - **预期解**：换 Claude Opus 级模型给 deep pool（1M context + 原生 agentic 长链指令遵循更强）
  - **恢复步骤**：(1) `.env` 配 `CLAUDE_OFFICIAL_API_KEY` + `LLM_DEEP_PROVIDER=claude-official` (2) `SELFCHECK_DEEP_HIDDEN=false` (3) 重启 (4) 视观测再启 `[SELFCHECK_DEEP]` cron 分派

- [ ] **三月·测试基础设施** —— 仓库零测试：无 `tests/`、无 `conftest.py`、`pyproject.toml` 无 test 配置、全仓 zero import of pytest / unittest、无 CI workflow。需要设计静态契约测试 / 离线冒烟 / 真实 API 测试分层

- [ ] **权限体系 v2 重新设计**
  - **临时缓解已做**：[`bootstrap.py:256-284`](../paimon/bootstrap.py#L256) 启动时把已加载的 builtin skill + 7 个 archon 自动写 `permanent_allow`（`permanent_deny` 不覆盖）
  - **根本设计待重做**：
    - 工具粒度细化：当前 `AuthzDecision.check_skill` 只支持 skill 级授权；需支持 tool 级 + 参数模式（`Bash(rm:*)` / `Bash(curl http*download*)`）
    - 取消 archon 神名作 subject（当前 bootstrap 把 shades_node 当 subject_type 写，但实际从未在决策路径使用——粒度过粗，徒增存储）
    - 单用户场景分级：「自用模式」全自动放行 + 真破坏命令依赖 pre_filter ／「严格模式」按现状询问
  - 正式重构等需求更明确后再启动

- [ ] **草神增强**
  - (1) `preference_get / preference_set` 专属工具 —— 当前偏好读写已由 `memory` 工具 `mem_type="user"` 路径覆盖（nahida 有 memory 工具权限），**能力等价但缺语义化**。是否值得造独立工具，看未来偏好场景是否明显异于 memory
  - (2) **独立知识面板**（`knowledge` 域 CRUD、按 category/topic 浏览）—— 当前 [`preferences_html.py`](../paimon/channels/webui/preferences_html.py) 只管 L1 记忆（user/feedback）；knowledge 域只通过 tool 调用读写，无 WebUI CRUD 入口
  - (3) **Archon 的 prompt 调优能力**（**派蒙闲聊路径已闭环**，此条仅指 archon）
    - 派蒙闲聊路径**已实装**：`/remember` 或 `istaroth.extract_experience` → 写 `feedback` 类记忆 → 每次 chat 时 [`_build_system_prompt`](../paimon/core/chat.py#L860) 经 `_load_l1_memories` 自动注入 feedback 记忆到 system prompt
    - **未做**：venti/nahida/furina/mavuika/raiden/tsaritsa/zhongli 的 `_SYSTEM_PROMPT` 是静态字符串，不读 feedback 记忆——反馈对 archon 行为无动态影响
  - **注**：`preferences_html.py:7-8` 明确"MVP 不做 project/reference tabs + 编辑 + 手动新增"是设计决策，不在此 todo 范围

- [ ] **火神增强** —— [`mavuika.py`](../paimon/archons/mavuika.py) 仅 67 行，`allowed_tools={"exec"}`
  - (1) 沙箱执行环境 —— [`exec.py`](../paimon/tools/builtin/exec.py) 是 `asyncio.create_subprocess_shell(command, ...)` 直出，60s 超时 + 8K 输出截断，**无任何沙箱/Namespace/容器化隔离**
  - (2) 技术重试机制 —— 当前仅 system prompt 里写"最多 2 次"，`mavuika.execute` 里**无任何重试 / 错误诊断代码**
  - (3) 部署工具（Docker/SSH）—— 全仓无 Docker/SSH 工具

- [ ] **冰神·AI 自举生成 skill** —— [`tsaritsa.py`](../paimon/archons/tsaritsa.py) 69 行，`allowed_tools={"skill_manage","exec"}`
  - 现状：
    - `tsaritsa.py:34` description 写"AI 自举"；prompt:22 写"规划新 skill 的设计方案"
    - `skills` 表 `source` 字段预留 `ai_gen` 枚举值 [`skills.py:19`](../paimon/foundation/irminsul/skills.py#L19)
    - `AuthzCache` 注释 [`cache.py:4`](../paimon/core/authz/cache.py#L4) 提到未来失效点
  - 关键缺口：[`skill_manage.py:22-106`](../paimon/tools/builtin/skill_manage.py) 只有 `scan / list / get`，**无 create / write 分支**。[`registry.reload_one`](../paimon/angels/registry.py#L83) 是对已有磁盘 SKILL.md 做热重载，不是 AI 生成
  - 待做：设计生成流程（模板 or LLM 自由生成 SKILL.md）+ 落地 `skill_manage.create` + 生成 skill 强制经死执 review（区别于启动自动放行）+ 可行性验证

## 2. 技术选型层面

- [ ] **异常日志落盘方案** —— [`log.py`](../paimon/log.py) 全文 25 行，只 `logger.add(sys.stderr, ...)` + 可选 `logger.add(paimon.log, 10MB rotation / 7 天 retention, level=DEBUG)`，全 level 混合、无独立 error-only handler / 无结构化异常归档 / 无 error 专属路径。待定：加 error 专属 file handler，或接外部聚合（Sentry 之类）

- [ ] **通用日报合成器**（[`paimon/foundation/digest/`](../paimon/foundation/digest/)）—— 只 prompt 层抽好，实装条件**尚未**达成
  - 当前抽象：`DigestSpec` + `render_cluster_prompt` / `render_analyze_prompt` / `render_digest_prompt` 三个函数，均只对 **LLM 驱动**的日报有效
  - 消费者：**只有风神**（`venti_event.py:102-128` + `venti.py:85`）真的调用 render_*
  - **岩神不算同构**：`zhongli._compose_daily_digest` 是**规则驱动**的 markdown 拼接（不调 LLM），无法通过 DigestSpec 参数化
  - 真正"起抽 `DigestPipeline` 条件"：**≥2 个 LLM 驱动**日报实现（比如未来水神 / 草神日报走 LLM）。届时再读两个找共同抽象
  - 当前动作：保持 prompt 层现状，等第二个 LLM 驱动消费者出现

## 3. 迁移层面

_迁移工作已全部完成（三频道、全部 skills、旧 workflow 引擎 → 生执）。_

## 附：代码体量观察（非紧急）

几个核心模块已偏大，短期尚可维护，持续扩展需要考虑拆分：

- [`archons/zhongli/zhongli.py`](../paimon/archons/zhongli/zhongli.py) 1414 行 + [`scorer.py`](../paimon/archons/zhongli/scorer.py) 764 行
- [`archons/venti.py`](../paimon/archons/venti.py) 939 行 + [`venti_event.py`](../paimon/archons/venti_event.py) 559 行
- [`shades/naberius.py`](../paimon/shades/naberius.py) 872 行
- [`foundation/selfcheck.py`](../paimon/foundation/selfcheck.py) 960 行
- [`foundation/irminsul/irminsul.py`](../paimon/foundation/irminsul/irminsul.py) 852 行

[`archons/base.py:_invoke_skill_workflow`](../paimon/archons/base.py#L175) 仍叫 `workflow`（旧引擎名），实为"skill 驱动的 tool loop"；命名残留，可择期改名。
