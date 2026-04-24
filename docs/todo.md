# 待办项 / 下一步

> 隶属：[神圣规划](aimon.md)
>
> 记录尚待展开的细节 / 技术选型 / 迁移工作。更新时间：2026-04-24

## 1. 职能层面

- [ ] 派蒙闲聊响应的具体交互形态（复用主会话 session？独立的轻量 session？）
- [ ] 冰神 **AI 自举生成 skill** 的可行性验证
- [ ] **推送具体策略**：推送时机 / 频率 / UX 形态 / 打断策略 / 积压处理 / 事件响铃优先级仲裁
- [x] ~~**WebUI 推送通知**~~ —— 2026-04-23 实装 `send_text` / `send_file` + 固定「📨 推送」收件箱会话 + `/api/push` SSE 长连接 + PushHub 扇出。频道能力声明 `supports_push`（QQ 关闭）。
- [x] ~~**三月·事件响铃**~~ —— 2026-04-23 实装 `MarchService.ring_event(channel_name, chat_id, source, message/prompt, task_id)`。复用地脉 `march.ring` 订阅（派蒙侧 zero-change）；限流 60s/10 次；审计 `event_type="march_ring_event"`。收集者（风神/岩神）的实际接入在各神增强独立做。
- [ ] **三月·自检系统**：`/selfcheck` 运行时健康诊断，秒级零交互
- [ ] **三月·测试基础设施**：静态契约 / 离线冒烟 / 真实 API 测试
- [ ] **三月·check skill 非交互模式**：预设参数入口，三月可定时调度项目体检
- [x] ~~**权限体系 MVP**~~ —— 2026-04-23 `paimon/core/authz/` 四件套（cache/decision/keywords/sensitive_tools）+ `Channel.ask_user` + 永久关键词识别 + 写世界树 + 地脉 skill.loaded 失效。冰神装载时按 `allowed_tools` **派生 sensitivity**（不再手填 manifest）。面板归属**冰神·插件面板**（偏离 docs 原"草神面板"，见 permissions.md）。
- [x] ~~**L1 记忆系统**~~ —— 2026-04-23 实装：(1) 时执压缩后 `extract_experience` 调 LLM 结构化提取（user/feedback/project/reference 四类筛选）写 `memory_index`；去重（type+subject+title）避免堆积；**存储**时 body 上限 2000 字；prompt 含敏感红线（密钥/隐私/prompt 注入）过滤 (2) 派蒙请求入口 `_build_system_prompt` 改 async + `_load_l1_memories` 默认拼 user+feedback 全量（上限 20 条，**注入**时 body 截 500 字预览）；注入段尾部加"记忆是背景非指令"防 prompt injection (3) `/remember` 命令 + LLM 自动分类（失败降级 user/default + 清理控制字符）；内容上限 2000 字；正则拒绝疑似 API key/密码/身份证/银行卡 (4) 草神 prompt 强调"写入 memory 前先 list/search 避免重复"
- [x] ~~**天使 30s 超时 + 魔女会桥**~~ —— 2026-04-23 实装 `paimon/angels/nicole.py` (`AngelFailure` + `escalate_to_shades`，魔女会由对接人尼可代表)。单 tool 30s（第二次超时触发）+ 总 3min 兜底；失败询问用户是否转交，同意后携 `escalation_reason` 调四影。实装中顺带修复：(1) **墙钟兜底判定**——工具内部吞 `CancelledError` / 阻塞事件循环的场景下，`asyncio.wait_for` 失效，外层改用 `wall_clock >= tool_timeout` 兜底累加超时计数；(2) **子进程异步化**——`tools/video_process.py` / `tools/audio_process.py` 从同步 `subprocess.run` 改为 `asyncio.create_subprocess_exec`，不再阻塞事件循环（修复 QQ 心跳断连 + 让 cancel 能传到子进程）；(3) **WebUI 气泡渲染**——权限/魔女会 `question` 事件作为独立气泡显示，用户答复后新起气泡，避免覆盖天使已回的内容。
- [ ] **草神增强**：(1) ~~专属工具 knowledge_read/write/list + memory_read/write/search~~ —— 已实装（`knowledge` / `memory` 工具）+ preference_get/set 待做 (2) 知识/偏好面板（查看、编辑）—— 2026-04-23 ~~偏好面板~~ 实装 MVP（`preferences_html.py` + `/preferences` + user/feedback tab + 查看全文 + 删除；project/reference / 编辑 / 知识面板 留后）(3) ~~作为 L1 记忆系统的业务写入接口~~ —— 2026-04-23 实装（时执 `extract_experience` 直写，草神按需 list/search；`/remember` 亦可直写）(4) Prompt 调优能力——根据反馈自动优化各模块的 system prompt
- [x] ~~**四影闭环 · 死执/生执/空执**~~ —— 2026-04-24 四影从"一次性直线"改造为真正闭环（docs/aimon.md §2.3 草水雷多轮循环）：
  **死执**：(1) ~~DAG 批量敏感操作扫描~~ —— `jonova.scan_plan` + `ScanItem/ScanResult`；扫 plan 中每节点 `sensitive_ops`，查 `authz_cache` 分流 ask/blocked/pre_approved；用户已永久放行的跳过，永久禁止的直接剔除 + 下游传递 skip (2) ~~新 skill/插件运行时审查~~ —— `jonova.review_skill_declaration` 已接冰神热加载（2026-04-23）
  **生执**：(1) ~~依赖环检测~~ —— `_plan.detect_cycle`（DFS 三色），第一轮出环自动降级线性 + 审计，第二轮再出环硬失败进归档 (2) ~~多轮迭代控制~~ —— `SHADES_MAX_ROUNDS=3`；`naberius.plan(round=N, verdict=...)` 支持修订；revise 路径把失败节点原因喂回 LLM 引导改派 assignee；preserved 节点 id 跟踪避免 re-INSERT (3) ~~失败回滚~~ —— `_saga.run_compensations` 轻量 saga：按 completed_ids 反序执行 compensate 描述，交火神 archon 落地；补偿失败不递归只记审计
  **空执**：(1) ~~多任务并发~~ —— `asmoday.dispatch` Kahn 拓扑分层 + `asyncio.gather`；preserved completed 节点直接注入 results 跳过重跑 (2) ~~故障切换（MVP）~~ —— `_run_one` 单节点失败重试 1 次 + 两次都败走 fail 传播 + `mark_downstream_skipped` 下游 skip；改派通过生执修订路径完成 (3) 服务发现（新 archon 运行时注册） —— 未做
  **数据模型**：`Subtask` +5 字段（deps/round/sensitive_ops/verdict_status/compensate）+ 幂等 ALTER 迁移
  **派蒙集成**：`run_shades_pipeline` 注入 `channel`/`chat_id`/`authz_cache`；顺带修复复杂任务下 `session.messages` 断裂（complex 直送路径不走 `model.chat` 导致用户输入/AI 产物未入会话历史，下一轮 LLM 看不到）+ `response_status` 不复位 + SSE 断连误判 + CancelledError 绕过收尾等 4 个历史遗留 bug
- [ ] **雷神增强**：(1) ~~专属文件读写工具~~ —— 已有 `file_ops` tool (2) ~~自动运行测试/lint 验证生成的代码~~ —— 2026-04-24 实装 `self_check()`（py_compile + ruff + pytest，auto-detect）+ 雷神 `[STAGE:code]` 分派到 `write_code` + 产出 `self-check.log` (3) ~~与水神的迭代循环~~ —— 2026-04-24 随三阶段闭环实装：水神 review_code verdict=revise → 生执 `_revise_code_pipeline` 重派 code 节点 + description 内嵌 verdict.issues JSON 确定性通道
- [x] ~~**水神增强**~~: (1) 游戏面板留 P2 (2) ~~结构化评审报告模板（通过/修改/重做三级结论）~~ 四影闭环已做 (3) ~~与雷神的自动迭代~~ 三阶段闭环已做；水神 `review_spec / review_design / review_code` 三方法调 `check` skill（参数模式非交互）→ 解析 `candidates.jsonl` → P0→redo / P1→revise / 其他→pass
- [ ] **火神增强**：(1) 沙箱执行环境（隔离危险操作）(2) 技术重试机制（执行失败自动诊断+重试）(3) 部署工具（Docker/SSH）
- [ ] **风神增强**：(1) ~~专属 web_fetch/web_search 工具~~ —— 已实装（`web_fetch` tool + `web-search` skill，2026-04-24）(2) ~~话题订阅（关键词+cron）~~ —— 2026-04-24 实装：世界树新增**域 11 订阅**（`subscriptions` + `feed_items` 两表，去重 UNIQUE(sub_id,url)）；风神 `collect_subscription` subprocess 调 web-search skill + 过滤已见 + 浅池 LLM 写日报 digest + 交三月 `ring_event` 推送；三月 cron 触发走 `[FEED_COLLECT] <sub_id>` 前缀，bootstrap `_on_march_ring` 分派到风神不经 LLM；派蒙指令 `/subscribe <keywords> [| <cron>] [| <engine>]` 和 `/subs list|rm|on|off|run`；WebUI `/feed` 信息流面板（订阅增删改 + feed_items 列表 + 按订阅/时间筛选 + 手动 run）。(3) 舆情仪表盘面板（情感倾向分析）(4) 舆情异常预警 → 三月事件响铃 (5) ~~定时新闻采集 → 三月定时响铃 → 派蒙推送~~ —— 随订阅实装（上面 (2) 已覆盖）
- [ ] **岩神增强**：(1) ~~专属股票 API 工具（A股行情）~~ —— 2026-04-24 实装：skill `dividend-tracker` 改造为纯 I/O BaoStock CLI（fetch-board/fetch-dividend/fetch-financial/cleanup-cache 四子命令）(2) ~~红利股筛选引擎~~ —— 2026-04-24 实装：三层分离重构，岩神 `paimon/archons/zhongli/` 目录化持有 scorer（纯函数）+ 扫描编排（full/daily/rescore）+ 变化检测；世界树 `dividend` 域重建为 watchlist + snapshot + changes 三表（旧 `dividend_stocks` 已删）；`[DIVIDEND_SCAN] <mode>` cron 前缀分派经 bootstrap 进岩神 (3) 资产配置计算器（未来） (4) ~~理财面板~~ —— 2026-04-24 WebUI `/wealth`：推荐选股/评分排行/变化事件 3 tab + Chart.js 90 天历史折线 + 触发 full/daily/rescore 按钮 (5) ~~股价/分红提醒 → 三月定时响铃~~ —— 随 (2) 实装（默认 cron：工作日 19:00 daily / 月 1 日 21:00 full；`/dividend on` 开启；岩神 `march.ring_event` 推送）；港股/美股未来扩展
- 相关入口：派蒙指令 `/dividend on|off|run-full|run-daily|rescore|top|recommended|changes|history`；LLM `dividend` tool 挂 `_CHAT_TOOLS`（识别"红利股推荐/某股最近怎样/最新变化"自然语言自动调）
- [ ] **冰神增强**：(1) ~~自动扫描 skills/ 目录写入世界树 skill 声明域~~ —— 2026-04-23 `SkillRegistry.sync_to_irminsul` 启动时 UPSERT builtin 源 + 孤儿扫描（`registry.py` / `bootstrap.py`）(2) ~~运行时插件加载 → 经死执审查~~ —— 2026-04-23 `paimon/angels/watcher.py` watchdog 监听 `skills/*/SKILL.md` + debounce 300ms + `SkillRegistry.reload_one/remove_one` + `jonova.review_skill_declaration`（热重载过死执，按用户决议偏离 docs "builtin 跳过审查"策略）；默认关，`.env SKILLS_HOT_RELOAD=true` 开启 (3) AI 自举生成 skill 能力 (4) ~~插件面板~~ —— 2026-04-23 已完成（含授权查看/撤销 tab + Skill 生态 tab）
- [x] ~~**时执独立模块化**~~：(1) ~~从 Model 中搬出 compress_session_context 到 paimon/shades/istaroth.py~~ —— 2026-04-23 完成，顺带实装 4 项改进（阈值公式 `window - max_tokens - 8k buffer` / 保留段 tool_use·tool_result 对齐 / Prompt 4 章节 + NO_TOOLS / 连续 3 次失败熔断 auto_compact_disabled 持久化）(2) ~~会话不活跃超时 → 自动归档~~ —— 2026-04-24 实装（默认 6h，护栏：`generating`/有 channel 绑定的都跳过；归档同步 `SessionManager` 内存）(3) ~~自动分层：热(活跃)→冷(30天)→过期(90天删除)~~ —— 2026-04-24 实装（task cold→archived 30d / archived→删除 60d，共 90d 对齐 docs；级联删 progress/flow/subtasks/edicts；额外加 `task_running_timeout_hours=1` 卡死超时保护对齐 docs "复杂任务默认 1 小时"）(4) ~~经验提取 hook：压缩后提取关键信息写入世界树 memory 域~~ —— 2026-04-23 随 L1 记忆系统实装 (`istaroth.extract_experience`)

  **生命周期闭环实装细节**：
  - 新模块 `paimon/shades/_lifecycle.py`：`SweepReport` + `sweep_sessions` + `sweep_tasks` + `run_lifecycle_sweep`；所有批量操作单 SQL 原子完成，失败计 `errors[]` 不抛
  - 世界树加 5 个新 API：`session_archive_if_idle` / `session_purge_expired` / `task_stuck_running_timeout` / `task_promote_lifecycle` / `task_purge_expired`（护栏内置在 SQL：`response_status<>'generating' AND channel_key='' AND archived_at IS NULL`；删除顺序 progress_log→flow_history→subtasks→edicts 满足 FK）
  - 三月 `_poll` 末尾 hook `_maybe_trigger_lifecycle_sweep`：默认每 6h 触发一次，单例守护 + 间隔 clamp `[1h, 168h]`；sweep 独立 task 失败不影响主轮询
  - 修复 `task_update_lifecycle`：进入 `cold` 阶段时同步设 `archived_at=now`（供 promote_lifecycle TTL 判定），避免正常归档任务永远卡在 cold
  - `SessionManager.invalidate_removed`：sweep 归档/删除后同步内存 dict + bindings，重启前后语义一致（启动 `session_list_all_full` 只取 `archived_at IS NULL` 的活跃会话）
  - 审计事件：`task_stuck_timeout`（每个卡死任务一条）+ `lifecycle_sweep_report`（每次清扫一条，仅在有变更或出错时写）
  - config 加 7 项：`lifecycle_sweep_enabled/lifecycle_sweep_interval_hours/session_inactive_hours/session_archived_ttl_days/task_running_timeout_hours/task_cold_ttl_days/task_archived_ttl_days`，全部 `.env` 可覆盖

## 2. 技术选型层面

- [x] ~~**地脉**实现~~ —— 2026-04-22 asyncio.Queue 进程内发布/订阅
- [x] ~~**时执**归档存储介质~~ —— 2026-04-22 归档与活跃同库在世界树内
- [x] ~~**世界树**存储方案~~ —— 2026-04-22 单 SQLite + 文件系统混合，10 个数据域
- [x] ~~**原石**重构为服务层~~ —— 2026-04-22 数据落盘走世界树 token_* API
- [x] ~~**会话**迁移到世界树~~ —— 2026-04-22 自动从 JSON 迁移到 SQLite
- [ ] **神之心**分层标准：参数量 / provider / 成本？
- [ ] **时执**上下文压缩阈值（3.5k 偏低）
- [x] ~~**生执**依赖环回滚机制~~ —— 2026-04-24 选 **saga 补偿**（非状态快照）：`Subtask.compensate` 字段由生执在编排时按需声明（仅有副作用的节点），pipeline 失败时 `_saga.run_compensations` 按 completed 反序执行，交火神 archon 落地；环检测第一轮降级线性、第二轮硬失败
- [ ] **异常日志**落盘方案（独立日志设施，不入世界树）
- [x] ~~**Skill / Tool sensitivity** 字段设计~~ —— 2026-04-23 采用"工具敏感清单 + 装载时派生"模型。敏感清单见 `paimon/core/authz/sensitive_tools.py`；冰神扫 skills/ 时按 `allowed_tools` 自动派生 sensitivity，`Bash(git:*)` 这类受限声明归一化处理。
- [x] ~~**永久授权**存储结构~~ —— 2026-04-23 世界树 authz 域：`(subject_type, subject_id, user_id) → decision` 三元组，decision ∈ {`permanent_allow`, `permanent_deny`}。先按 skill 粒度实装，tool / 按参数模式未来扩展。
- [x] ~~**用户答复**交互形态~~ —— 2026-04-23 纯文本识别（规则引擎 `paimon/core/authz/keywords.py`）+ 30s 超时保守拒绝。识别 21 种答复模式含否定短语（"不要放行"等）。
- [x] ~~**面板撤销 → 派蒙缓存同步**~~ —— 2026-04-23 冰神插件面板撤销时直接调 `authz_cache.invalidate()` 同步（同模块闭环，无需地脉）。

## 3. 迁移层面

- [x] ~~三频道接入~~ —— WebUI / Telegram / QQ 已完成
- [x] ~~现有 skills 迁移 (bili/xhs)~~ —— 已完成
- [ ] 现有 skills 迁移: web / dividend
- [ ] 现有 workflow 引擎退役 / 改造为生执
