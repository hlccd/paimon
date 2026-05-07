# 待办项 / 下一步

> 隶属：[神圣规划](aimon.md)
>
> 只记录**尚未实现 / 待完善**的事项。已完成项请查 git log / 归档文档。更新时间：2026-04-29 / 2026-05-03（加 §0）

每一条都已对照源码核过一遍；"部分实装"一栏列出哪些已做、哪些没做、哪些是主动舍弃的设计决策。

## 0. ⚠️ 最高优

- [ ] **体量控制** —— 项目体量已超出工程化工具链阈值，触发多重连锁失效（2026-05-03 标记）
  - **触发**：跑 `/check` 项目体检「深入」档位（min 5 迭代 × 每迭代 5 轮 × 5 视角 ≈ 几百轮 Agent 调用）按 methodology 严格走 token/时长爆炸 → AI 被迫降级单轮 discovery + 多 Agent 委派覆盖；finding 仅单轮 candidate，**主观判断（架构/重复/严重度档位）共识缺失**
  - **现状体量**：paimon/ 283 .py / 47889 行 + docs/ 26 .md + skills/ 9 SKILL；典型超大单文件 archons/zhongli/scorer/_score.py 单函数 280 行；webui channel.py 459 行残留 60-220 行注释段未清
  - **连锁失效**：
    - **审查工具失效**：`/check` 严格多轮跑不动；冰神 deep self-check 已暂缓（参见 §1「三月·自检 Deep 暂缓」）也是同根原因——LLM 在数百轮迭代上不稳定
    - **文档同步成本爆炸**：拆子包后 docs/{progress,todo,migration}.md / archons/venti.md / foundation/{march,irminsul}.md 多处单文件路径 404（MNT-005）；progress.md 大量 hardcode `paimon/.../xxx.py:line` 任何子包拆分大批失效
    - **模板放大**：8 archon execute ~140 行复制 + 3 channel auth/chunking + 17 webui/api 子模块重复 auth check + 4 pipeline mixin import paste copy —— 体量越大改一处要改 N 处
  - **方向**（具体阈值/手段待讨论）：
    - 单文件硬约束 ≤500 行（部分已落实，新代码继续守；超限走拆子包）
    - 抽公共 base mixin（archon execute / channel auth / webui api auth check / pipeline mixin import）减绝对行数 + 减少改一处要改 N 处
    - docs 路径引用从「具体 .py + 行号」改「目录 + 接口名/锚点」降低同步成本
    - CI/pre-commit 检查文件行数 + 重复模式预警（同 ≥3 文件相似行触发）
    - 评估「冰神 deep / 死执 review / 草神 hygiene」等多轮 LLM 工作流的轮数上限——体量决定 max_rounds 不能照搬 methodology
  - **关联**：今日 `.check/report.md` §3「跨子审查根因聚合」列 13 类放大效应；附录「代码体量观察」（本文件 §附 115-119 行）列表已陈旧（zhongli/venti 已拆但附录未更新——这本身就是体量管控失效的证据）

## 1. 职能层面

- [ ] **推送策略深化**
  - **已做**：`march.ring_event` 60s/10 次滑窗限流（非 dedup 路径） + `dedup_per_day=True` 日级 upsert + `push_archive` 持久化 + 审计事件 `march_ring_event` + leyline `push.archived` publish + PushHub 进程内 SSE 扇出（满队丢最早） + level 字段预留 `'silent'|'loud'`
  - **未做**：
    - `level='loud'` 的实际打断 UX —— 全仓消费者把 level 当字段存取，但没有任何路径对 `loud` 做差异化（读出来丢前端后前端也没用）
    - 多事件响铃并发时的优先级仲裁（目前 FIFO）
    - 派蒙 crash 后的积压重播（push_hub 内存队列丢失，push_archive 持久化但未读状态不保证按时序重放）
    - 按 source 分级的频率策略（所有 source 共享同一个 60s/10 次窗口）

- [ ] **三月·自检 Deep 暂缓**
  - 底层 `SelfCheckService.run_deep / _invoke_check_skill / _progress_watcher` 全部实装；[`config.py:124`](../paimon/config.py#L124) `selfcheck_deep_hidden=True` 默认隐藏 + [`selfcheck_html.py:639`](../paimon/channels/webui/selfcheck_html/#L639) 按 deep_hidden 关按钮 + Deep Tab + `[SELFCHECK_DEEP]` cron 分派已撤销（[`bootstrap.py:362`](../paimon/bootstrap/#L362)）
  - **卡点**：当前 mimo-v2-omni 对 check skill 的 N+M+K 多轮迭代执行不充分（单轮 ~30s 就返回简短 finding 停止），跑不出可靠体检
  - **预期解**：换 Claude Opus 级模型给 deep pool（1M context + 原生 agentic 长链指令遵循更强）
  - **恢复步骤**：(1) `.env` 配 `CLAUDE_OFFICIAL_API_KEY` + `LLM_DEEP_PROVIDER=claude-official` (2) `SELFCHECK_DEEP_HIDDEN=false` (3) 重启 (4) 视观测再启 `[SELFCHECK_DEEP]` cron 分派

- [ ] **三月·测试基础设施** —— 仓库零测试：无 `tests/`、无 `conftest.py`、`pyproject.toml` 无 test 配置、全仓 zero import of pytest / unittest、无 CI workflow。需要设计静态契约测试 / 离线冒烟 / 真实 API 测试分层

- [ ] **权限体系 v2 重新设计**
  - **临时缓解已做**：[`bootstrap.py:256-284`](../paimon/bootstrap/#L256) 启动时把已加载的 builtin skill + 7 个 archon 自动写 `permanent_allow`（`permanent_deny` 不覆盖）
  - **根本设计待重做**：
    - 工具粒度细化：当前 `AuthzDecision.check_skill` 只支持 skill 级授权；需支持 tool 级 + 参数模式（`Bash(rm:*)` / `Bash(curl http*download*)`）
    - 取消 archon 神名作 subject（当前 bootstrap 把 shades_node 当 subject_type 写，但实际从未在决策路径使用——粒度过粗，徒增存储）
    - 单用户场景分级：「自用模式」全自动放行 + 真破坏命令依赖 pre_filter ／「严格模式」按现状询问
  - 正式重构等需求更明确后再启动

- [ ] **草神增强** —— 2026-04-29 完成 Phase 1 + 2（面板重做 + archon prompt 调优），剩余为 Phase 3 可选扩展
  - ~~(2) **独立知识面板**~~ ✅ 2026-04-29：`/preferences` 升级为 [`/knowledge`](../paimon/channels/webui/knowledge_html/)（草神·智识），3 tab（记忆 / 知识库 / 文书归档）；记忆 tab 含 user/feedback/project/reference 四类 pill 切换；知识库 tab 按 category 分组浏览 + 查看全文；文书归档 tab 扫 `.paimon/tasks/<id>/` 下四影任务产物（spec.md / design.md / code/ / summary.md 等）+ markdown 预览
  - ~~(3) **Archon 的 prompt 调优能力**~~ ✅ 2026-04-29：[`archons/base.py`](../paimon/archons/base.py) 加 `_load_feedback_memories_block()` helper；7 个 archon（venti/nahida/furina/mavuika/raiden/tsaritsa/zhongli）`execute()` 路径在 system prompt 末尾注入 feedback 记忆——`/remember` 的反馈现在对复杂任务路径也生效。cron 后台路径（collect_subscription / collect_dividend）有意**不注入**避免污染采集逻辑
  - (1) `preference_get / preference_set` 专属工具 —— 偏好读写已由 `memory` 工具 `mem_type="user"` 路径覆盖，**能力等价但缺语义化**。是否值得造独立工具，看未来偏好场景是否明显异于 memory（低优先）
  - **Phase 3（可选）** 主动知识管家 + `/write` 指令：
    - 草神 `scan_memory_health()`：扫重复（title 相似）/ 冲突（feedback 相悖）/ 过时（ttl 将至或长期未引用）；结果走方案 D（新 task_type `memory_hygiene`，周一 3:00 cron 触发）写 push_archive(actor="草神")，面板加"健康报告"tab 渲染
    - `/write <需求>` 指令：草神单跑 requirement-spec skill 不走完整四影，产物直接进文书归档
    - 估算 ~4h；需要调试 LLM 相似度判定 prompt
  - **注**：原计划的"project/reference tabs + 编辑 + 手动新增" `preferences_html.py:7-8` 明确"MVP 不做"——Phase 1 把 project/reference tabs 做了（只读+删除），编辑/新增仍不做（走 /remember 指令）

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

- [ ] **借鉴 gsuid_core/ai_core 重构 paimon 核心能力** —— `/home/mi/code/gsuid_core/gsuid_core/ai_core/` 20k 行是"LLM-native 的助手平台"完整 runtime，几个子系统直接对标 paimon 现有模块，值得拆开逐个吸收：
  - `ai_core/rag/tools.py` **工具向量化**（Qdrant 存工具描述，LLM 动态检索）—— 对标**冰神 skill 生态**；skill 多起来后解决"工具列表太长 LLM 挑不中"的经典问题
  - `ai_core/handle_ai.py` **意图分类 + 分流**（闲聊走轻量路径、工具走 Agent、问答走 RAG）—— 对标**派蒙意图路由**；成本与延迟优化的主要抓手
  - `ai_core/memory/`（observer/ingestion/retrieval/vector/scope）**双路记忆系统**：被动观察 → 异步 ingestion → System-1 向量 + System-2 分层图 —— 对标**世界树 memory 域 + 草神**；Scope Key 做会话隔离
  - `ai_core/mcp/client.py` **无状态 MCP 客户端**（`fastmcp + StdioTransport`）—— **冰神**可加一种新的 skill 源，直接接第三方 MCP server
  - `ai_core/heartbeat/`（decision/inspector）**心跳自主决策** —— 对标**三月**；定时 check 要不要主动做事
  - `ai_core/persona/` **Persona × Session** 匹配 —— 多人格场景，paimon 当前单用户，优先级低
  - `ai_core/register.py` `@ai_tools` 装饰器 **自动注入 RunContext/Event/Bot** 参数（栈回溯识别插件名）—— 零配置工具注册，迁移时节省大量仪式
  - `ai_core/gs_agent.py:42-119` **history tool_call/return 配对截断** —— 踩过坑才懂的细节，直接抄
  - `ai_core/configs/` **按任务级别选 provider**（便宜 / 贵模型分工）—— 对标**神之心** profile，已有但按"路由"选不是按"任务级别"选，可增强
  - 建议：不要整体照搬；按上面 8 个子系统分别评估、独立立项，逐个吸收

- [ ] **水神·ZZZ 临界推演接口修复** —— 已接但 endpoint 返 `404 page not found`：[`api.py:URL_ZZZ_VOID`](../skills/mihoyo/mihoyo/api.py)（拼出来 `https://api-takumi-record.mihoyo.com/event/game_record_zzz/api/zzz/void_front_battle_detail` + 参数 `void_front_id=102`）。骨架已就绪（actions.zzz_void / furina.collect_zzz_void / channel 白名单 / _extractTeams ZZZ 兜底），但 [`furina_game.py:_collect_one_account`](../paimon/archons/furina_game/) ZZZ 路径 + [`game_html.py:ABYSS_DEFS.zzz`](../paimon/channels/webui/game_html/) 都已注释禁用。需 F12 抓真实 URL 后改 endpoint 重新启用

- [ ] **水神·抽卡拓展** —— 当前已做：三游戏统一 stoken→authkey 自动换 + GS/SR/ZZZ 抽卡同步入库（[`furina_game.py:auto_sync_gacha`](../paimon/archons/furina_game/) + [`skills/mihoyo/mihoyo/actions.py:gacha_log`](../skills/mihoyo/mihoyo/actions.py)）。扩展方向：
  - **UIGF 标准导入**：支持从 Paimon.moe / Snap Hutao / 椰羊 等工具导出的 UIGF JSON 直接导入（绕过 authkey 有效期 + 补全早期记录米哈游已删的部分）
  - **本地抽卡模拟器**：基于官方公告概率 + 保底/小保底规则，三游戏各自的模拟器：
    - 原神：5★ 基础 0.6%，硬保底 90，软保底 73 开始提升；4★ 基础 5.1%，硬保底 10；角色 UP 50% 小保底
    - 崩铁：类似原神但硬保底 5★=90（6★ 角色）/ 4★=10（5★ 武器），上升轨道从 74 开始
    - 绝区零：S 级 0.6%（硬保底 90），A 级 9%，S 级角色"信号"小保底 50%
    - UI：设定池子/已有保底进度 → 模拟抽 N 次 → 展示历次出货、平均出金抽数、小保底命中率

- [ ] **用户帮助/教程体系** —— 当前 [`/help`](../paimon/core/commands/) 是硬编码 plain text 列 22 个命令名，无场景/示例/分组；docs/ 全是开发者文档无新手 onboarding；WebUI 无引导界面入口；skill 隐式触发（如输入 `bilibili.com` 自动走 bili）用户不知道
  - **二级 `/help`**：`/help <cmd>` 显示子命令详情 + 典型例子（如 `/help dividend` 列 9 个子动作含 cron 写法）；实现：`@command` 装饰器接 `description` + `usage_examples` 字段，`/help` 自动 reflect 而非硬编码
  - **`/help` 分组+排序**：按 会话管理 / 任务 / 订阅 / 理财 / 记忆 / 系统 分组列，常用前置；当前 22 行平铺密度过高
  - **WebUI 新手引导**：首次空对话显示 welcome card（4-5 个按钮例子：发"你好" / 输入 b 站链接 / `/task` 写代码 / 红利股查询 / `/remember`）；输入框旁加 "?" 图标点开帮助 modal
  - **docs/getting-started.md**：用户视角的"30 分钟上手"，5 个典型场景配 GIF/截图（闲聊 / b 站 / 红利股 / 定时提醒 / `/task` 复杂任务）
  - **隐式 skill 触发提示**：intent 命中 skill 时 UI 显示 "🎯 走 X skill — 因为消息含 trigger Y"（[`intent.py`](../paimon/core/intent.py) 已 logger.info，UI 未展示）
  - **`paimon --tutorial` CLI**：交互式上手教程入口（用 ascii art 引导走完 5 个场景）

- [ ] **四影执行时长优化** —— 复杂任务（`/task`）当前从死执到时执串行 LLM 调用，单次跑分钟级；用户感知慢
  - **管线阶段并发**：死执 review（仅看用户原文） + 草神 起草 spec.md（同样仅需原文）可并发，等齐后再进生执 plan；当前 [`shades/pipeline.py`](../paimon/shades/pipeline/) 是死执→草神 串行 ~10s
  - **review-revise 回合压缩**：草→雷→水多轮迭代上限 [`shades_max_rounds=3`](../paimon/config.py#L91)，但 LLM 经常 1 轮就过；可加"水神高置信通过"早停规则避免无意义多跑
  - **轻量验证用浅层模型**：死执"明显安全"路径用 shallow LLM（flash 级），仅疑似危险升级到 deep；当前 [`shades/jonova.py`](../paimon/shades/jonova.py) 都走 deep
  - **prompt cache 命中率**：[`archons/base.py`](../paimon/archons/base.py) feedback 注入已稳态排序（按 created_at ASC），但 system prompt 主体仍每次 from scratch；改用模板化稳定前缀 → 后缀变量段，让 Anthropic / DeepSeek 缓存命中
  - **空执流水线化**：[`shades/asmoday.py`](../paimon/shades/asmoday.py) 同层 gather 已并发但层间严格串行；可流水线（前层未全完，下层无依赖节点开始）— 实现复杂度高，先不做
  - **可观测性**：每段 LLM 调用 elapsed/tokens 已部分入 [`primogem`](../paimon/foundation/primogem.py)，[`tasks_html.py`](../paimon/channels/webui/tasks_html/) 加四影执行甘特图方便定位瓶颈

## 2. 技术选型层面

- [ ] **异常日志落盘方案** —— [`log.py`](../paimon/log.py) 全文 25 行，只 `logger.add(sys.stderr, ...)` + 可选 `logger.add(paimon.log, 10MB rotation / 7 天 retention, level=DEBUG)`，全 level 混合、无独立 error-only handler / 无结构化异常归档 / 无 error 专属路径。待定：加 error 专属 file handler，或接外部聚合（Sentry 之类）

- [ ] **通用日报合成器**（[`paimon/foundation/digest/`](../paimon/foundation/digest/)）—— 只 prompt 层抽好，实装条件**尚未**达成
  - 当前抽象：`DigestSpec` + `render_cluster_prompt` / `render_analyze_prompt` / `render_digest_prompt` 三个函数，均只对 **LLM 驱动**的日报有效
  - 消费者：**只有风神**（`venti_event.py:102-128` + `venti.py:85`）真的调用 render_*
  - **岩神不算同构**：`zhongli._compose_daily_digest` 是**规则驱动**的 markdown 拼接（不调 LLM），无法通过 DigestSpec 参数化
  - 真正"起抽 `DigestPipeline` 条件"：**≥2 个 LLM 驱动**日报实现（比如未来水神 / 草神日报走 LLM）。届时再读两个找共同抽象
  - 当前动作：保持 prompt 层现状，等第二个 LLM 驱动消费者出现

- [ ] **天使体系加「信息收集」成员**
  - 现状：11 协同天使全是"评估 / 推动"型，没有专门"先去查信息"的角色。议题需要外部数据时（如"该上 RBAC 吗"需要查现有授权样本量级），讨论容易凭经验发挥
  - 设想：加一个新天使（暂名「调研员 / scout」），可在讨论前 / 中段被晨星调度去调 web-search / topic / knowledge skill 拿真实数据回填给其他天使
  - 难点：天使发言现在是纯文本，调 skill 需要 tool-loop 能力（跟 chat handler tool 调用类似）；架构上要决定"是普通天使 + 加 tool 权限"还是"独立模式（先收集再讨论）"
  - 关联：`paimon/morningstar/roles.py` 加角色 + `council.py` dispatch 时给它 tool 权限
  - 优先级：中（不少议题都需要先收集再讨论分析）

- [ ] **明确四影定位 + 七神从四影独立**
  - 四影定位：**复杂任务的落地执行管线**（写代码 / 落产物 / 多步执行）。当前对单用户场景命中率低，但保留作为兜底
  - 七神从四影独立：当前 docs 里七神挂在四影下作为"能力模块"；新架构里七神是独立体系——业务模块 + skill 调用代理 + cron + 面板，不再隶属四影
  - 影响：
    - docs/aimon.md / world_formula.md / README.md 七神章节移出四影下
    - 代码上七神已经独立（`paimon/archons/`）但 docs 描述滞后
    - 重新梳理"四影 + 七神"的边界：四影负责管线骨架 / 七神负责执行节点 → 四影通过 dispatch 调七神（保持现状但语义独立）
  - 优先级：低（语义梳理为主，代码已基本对齐）

## 3. 迁移层面

_迁移工作已全部完成（三频道、全部 skills、旧 workflow 引擎 → 生执）。_

- [ ] **七神 B 类空壳节点新职能安排**（v6 解耦后产物，2026-05-08）
  - **现状**：四影 / 七神解耦（v6）后，2 个节点 archon 本体暂无具体职能：
    - `paimon/archons/raiden.py`：原写代码 4 件套已转 `paimon/shades/worker/`（stage=design/code/simple_code）
    - `paimon/archons/mavuika.py`：原 exec tool-loop 已转 `paimon/shades/worker/`（stage=exec）
  - **当前形态**：~30 行 namespace 壳（class + name + description + execute 兜底）
  - **候选方向（待用户决策）**：
    - 删除整个文件（彻底移除 namespace）
    - 重写新职能
    - 保留等待
  - **关联**：A 类 5 个节点（venti / zhongli / nahida / furina / tsaritsa）保留非四影功能（cron / 面板 / 概念归属），无需处理

## 附：代码体量观察（非紧急）

几个核心模块已偏大，短期尚可维护，持续扩展需要考虑拆分：

- [`archons/zhongli/zhongli.py`](../paimon/archons/zhongli/zhongli.py)（已拆子包，但 zhongli.py 仍有 mixin 入口）
- [`archons/venti/`](../paimon/archons/venti/) 多 mixin 子包
- [`shades/naberius/`](../paimon/shades/naberius/) 子包
- [`foundation/selfcheck.py`](../paimon/foundation/selfcheck/) 960 行
- [`foundation/irminsul/irminsul.py`](../paimon/foundation/irminsul/irminsul.py) 852 行

[`archons/base.py:_invoke_skill_workflow`](../paimon/archons/base.py#L175) 仍叫 `workflow`（旧引擎名），实为"skill 驱动的 tool loop"；命名残留，可择期改名。

> v6 解耦后体量变化：archons/ -1300 行（七神瘦身）+ shades/worker/ +800 行（工人体系新增）= 净 -500 行。


---

## 四影管线设计缺陷（2026-05-02 拆分时观察到，非 refactor 引入）

**Bug 现象**：`/task` 跑完整 6 节点 DAG 后，`review_spec=revise / review_design=pass / review_code=pass`，但日志显示「已达最大轮次」，整轮 verdict 仍 = revise，不进 round 2 修订。

### 1. 阶段门控缺失（asmoday 全 DAG 跑完才汇总）

- 现状：`asmoday.dispatch` 按拓扑分层并发跑完整 DAG，**不区分 stage 是不是已挂**
- 问题：`review_spec=revise` 时 design/code 仍基于旧 spec 跑完，浪费 LLM token + 产生迷惑性 "review_design pass"
- 改进：水神 review_X 出 revise/redo 后立即取消下游 dispatch（plan 内打 skipped），整轮 verdict 直接定 = 该 review_X 的 verdict
- 原作者注释明写："MVP 代价：当前 asmoday 仍会跑完所有节点再汇总；阶段门控留 Phase 2"
- 文件：`paimon/shades/pipeline/_verdict.py:_resolve_verdict`、`paimon/shades/asmoday.py:dispatch`

### 2. revise 不进 round 2，直接 round_cap_hit

- 现状：日志「已达最大轮次」但只跑了 1 轮
- 排查：`config.shades_max_rounds` 实际值（默认 3，可能被设成 1）
- 改进：max_rounds 至少 2-3；review_spec revise 时确保 round 2 修订 spec 而不是直接 round_cap_hit
- 文件：`paimon/shades/pipeline/_execute.py:execute`（`max_rounds` 读取处）

### 3. 轻量 review LLM 严格度 vs 业务可执行性

- 现状：`_LIGHT_REVIEW_SYSTEM` prompt 让 LLM 把 P1 判 revise
- 问题：LLM 倾向找细枝末节的 P1（如"性能基准模糊"、"测试方法未定义"），导致 spec 反复 revise → 烧 token / 体验差
- 实测案例：spec 3.8KB 的"Python 阶乘函数"任务，review_spec(轻量) 给 1 P1+1 P2+1 P3 → revise；但下游 design+code+review_code 全 pass
- 改进：P1 改 warn-only（不触发 revise）；或加阈值「P1 ≥ 2 才 revise」；或让 LLM 输出「是否阻塞下游」信号而非纯 severity
- 文件：`paimon/archons/furina/_review.py:_LIGHT_REVIEW_SYSTEM`

### 4. simple 级 DAG 跟 code-implementation skill 不匹配

- 现状：`_classify_code_task` 把短任务（< 40 字）判 simple → 2 节点 DAG（雷神 code → 水神 review_code），无 spec/design 节点
- 但 `RaidenArchon.write_code()` 无脑调 code-implementation skill，需要 spec.md/design.md
- 这两文件不存在 → LLM 兜圈 15 轮 → 强制收尾产出 0 文件 → review pass（0 findings）
- 改进二选一：(a) simple 级跳过 code-implementation skill，让雷神直接 LLM 写代码；(b) simple 级也加 spec/design 节点（跟 complex 一样但每段更轻量）
- 文件：`paimon/archons/raiden.py:write_code`、`paimon/shades/naberius/code_pipeline.py:_build_code_pipeline_dag`

### 5. /dividend rescore 等"立即返回"命令的 web 显示问题

- 现象：`/dividend rescore` 后端日志显示命令分发完整、bg task 启动、push_archive 写入完成，但 webui 前端没显示「已触发红利股 rescore 扫描...」回复
- 排查方向二选一：
  - **A. 前端 SSE handler bug**：reply 已发出（_persist_turn case 1 dedup 跳过 + msg.reply 正常发 SSE message），但前端 `static_html.js` 处理 `data: {"type":"message"}` 在 waitingSessions 状态某种 race 下没触发 DOM 渲染
  - **B. _persist_turn case 1 副作用过头**：dedup 跳过持久化是对的，但前端可能依赖 persist 同步落盘后才查 messages → 应该用 reply 路径展示而不是 reload session
- 触发条件：连续两次发同一命令（reply_text 一样），第二次 case 1 命中
- 影响：用户多次触发同命令时第二次起感觉"无响应"
- 文件：`paimon/core/chat/_persist.py:_persist_turn`、`paimon/channels/webui/static_html/_chat_html_body_*.py`

### 6.4 xhs collector 补抓笔记摘要（body 字段）

- 现状：xhs 搜索列表 DOM 卡片只有 title / author / like，没有正文摘要 → `Item.body=""`
- 影响：topic skill 输出 brief 版「Top N」时 xhs 条目无 50 字摘要，只能降级显示标题
- 升级路径：search 阶段先拿 note_id list → 二次抓 `https://www.xiaohongshu.com/explore/<id>` 详情页 DOM 里的 `.note-content / .desc` 节点拿 body
- 复杂度：每条多一次 chromium goto + 解析，N=15 条多 30-60s；可考虑并发 4-6 个 page
- 优先级：低（短期靠标题足以让用户判断；下版本上 LLM 凝练摘要后此 todo 可降级）
- 文件：`skills/topic/scripts/lib/sources/xhs.py`

### 6.5 提高贴吧 collector 覆盖度

- 现状：贴吧 web 搜索 SPA `tieba.baidu.com/f/search/res?qw=...&pn=1` 每 topic 实际只渲染 3-5 个 .threadcardclass，且无翻页元素（虚拟列表 placeholder 18 个空 slot 不渲染真内容）—— 是贴吧自身限制不是我们 bug
- 当前已接入但每 topic 只贡献 3-5 条作为补充
- 改进路径：百度通用搜索 + `site:tieba.baidu.com/p/` 拿更多帖子链接 → 二次抓单帖详情合并到结果
  - 障碍：百度搜索结果 URL 是 `baidu.com/link?url=...` 跳转链，要 follow 一次拿真实 URL；可能命中非 `/p/<id>` 的吧首页等
  - 复杂度：每个搜索结果要 follow + 单帖详情抓 = N+M 次 chromium 调用，大幅拖慢
- 优先级：低（其他源够丰富，贴吧 3-5 条是补充非主力）
- 文件：`skills/topic/scripts/lib/sources/tieba.py`

### 6. /stop 在 skill / /agents 跑期间无效

- 副作用：天使 skill 调用现在建独立 ephemeral session.id 跑 LLM（解决跨轮污染），
  但 `state.session_tasks` 按 session.id 索引、`/stop` 按当前 channel 主 session.id
  反查任务—— skill 跑时 /stop 找不到 ephemeral 任务
- /agents 同样的问题：`run_council` 在 cmd_agents 里 await，没注册到 state.session_tasks，
  /stop 也无法中断（30 次 LLM call 跑 1-3 分钟）
- 修复路径：`/stop` 扩展为按 channel_key 反查所有活跃任务（主 session + 当前 channel 上的
  ephemeral session + /agents council task）批量 cancel；或 ephemeral / council 创建时
  也注册到 channel_key 副表
- 优先级：低（skill 一般 ≤30s，/agents 跑完自动结束）
- 文件：`paimon/core/chat/session.py:stop_session_task`、`paimon/core/commands/_dispatch.py:_run_skill_isolated`、`paimon/core/commands/agents.py`
