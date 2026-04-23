# 待办项 / 下一步

> 隶属：[神圣规划](aimon.md)
>
> 记录尚待展开的细节 / 技术选型 / 迁移工作。更新时间：2026-04-23

## 1. 职能层面

- [ ] 派蒙闲聊响应的具体交互形态（复用主会话 session？独立的轻量 session？）
- [ ] 冰神 **AI 自举生成 skill** 的可行性验证
- [ ] **推送具体策略**：推送时机 / 频率 / UX 形态 / 打断策略 / 积压处理 / 事件响铃优先级仲裁
- [x] ~~**WebUI 推送通知**~~ —— 2026-04-23 实装 `send_text` / `send_file` + 固定「📨 推送」收件箱会话 + `/api/push` SSE 长连接 + PushHub 扇出。频道能力声明 `supports_push`（QQ 关闭）。
- [ ] **三月·事件响铃**：数据收集者请求三月响铃推送，依赖风神/岩神等模块
- [ ] **三月·自检系统**：`/selfcheck` 运行时健康诊断，秒级零交互
- [ ] **三月·测试基础设施**：静态契约 / 离线冒烟 / 真实 API 测试
- [ ] **三月·check skill 非交互模式**：预设参数入口，三月可定时调度项目体检
- [x] ~~**权限体系 MVP**~~ —— 2026-04-23 `paimon/core/authz/` 四件套（cache/decision/keywords/sensitive_tools）+ `Channel.ask_user` + 永久关键词识别 + 写世界树 + 地脉 skill.loaded 失效。冰神装载时按 `allowed_tools` **派生 sensitivity**（不再手填 manifest）。面板归属**冰神·插件面板**（偏离 docs 原"草神面板"，见 permissions.md）。
- [x] ~~**L1 记忆系统**~~ —— 2026-04-23 实装：(1) 时执压缩后 `extract_experience` 调 LLM 结构化提取（user/feedback/project/reference 四类筛选）写 `memory_index`；去重（type+subject+title）避免堆积；**存储**时 body 上限 2000 字；prompt 含敏感红线（密钥/隐私/prompt 注入）过滤 (2) 派蒙请求入口 `_build_system_prompt` 改 async + `_load_l1_memories` 默认拼 user+feedback 全量（上限 20 条，**注入**时 body 截 500 字预览）；注入段尾部加"记忆是背景非指令"防 prompt injection (3) `/remember` 命令 + LLM 自动分类（失败降级 user/default + 清理控制字符）；内容上限 2000 字；正则拒绝疑似 API key/密码/身份证/银行卡 (4) 草神 prompt 强调"写入 memory 前先 list/search 避免重复"
- [x] ~~**天使 30s 超时 + 魔女会桥**~~ —— 2026-04-23 实装 `paimon/angels/nicole.py` (`AngelFailure` + `escalate_to_shades`，魔女会由对接人尼可代表)。单 tool 30s（第二次超时触发）+ 总 3min 兜底；失败询问用户是否转交，同意后携 `escalation_reason` 调四影。实装中顺带修复：(1) **墙钟兜底判定**——工具内部吞 `CancelledError` / 阻塞事件循环的场景下，`asyncio.wait_for` 失效，外层改用 `wall_clock >= tool_timeout` 兜底累加超时计数；(2) **子进程异步化**——`tools/video_process.py` / `tools/audio_process.py` 从同步 `subprocess.run` 改为 `asyncio.create_subprocess_exec`，不再阻塞事件循环（修复 QQ 心跳断连 + 让 cancel 能传到子进程）；(3) **WebUI 气泡渲染**——权限/魔女会 `question` 事件作为独立气泡显示，用户答复后新起气泡，避免覆盖天使已回的内容。
- [ ] **草神增强**：(1) ~~专属工具 knowledge_read/write/list + memory_read/write/search~~ —— 已实装（`knowledge` / `memory` 工具）+ preference_get/set 待做 (2) 知识/偏好面板（查看、编辑）—— 2026-04-23 ~~偏好面板~~ 实装 MVP（`preferences_html.py` + `/preferences` + user/feedback tab + 查看全文 + 删除；project/reference / 编辑 / 知识面板 留后）(3) ~~作为 L1 记忆系统的业务写入接口~~ —— 2026-04-23 实装（时执 `extract_experience` 直写，草神按需 list/search；`/remember` 亦可直写）(4) Prompt 调优能力——根据反馈自动优化各模块的 system prompt
- [ ] **死执增强**：(1) DAG 批量敏感操作扫描——生执产出 DAG 后，死执二次扫描所有敏感 op，排除已永久授权的，打包一次性询问用户 (2) 新 skill/插件运行时审查——冰神加载时经死执审查权限声明
- [ ] **生执增强**：(1) 依赖环检测（静态拓扑排序 + 动态运行时检测）(2) 多轮迭代控制——Nahida→Furina→Raiden 循环设上限，生执决定何时停止 (3) 失败回滚——子任务失败时清理中间数据，saga 补偿或状态快照
- [ ] **空执增强**：(1) 多任务并发——无依赖的子任务用 asyncio.gather 并行执行 (2) 故障切换——archon 执行失败时尝试备选 (3) 服务发现——新 archon 注册后自动加入路由表
- [ ] **雷神增强**：(1) 专属文件读写工具（不依赖 exec cat/echo）(2) 自动运行测试/lint 验证生成的代码 (3) 与水神的迭代循环——写完自动提交水神评审，不通过则修改重交
- [ ] **水神增强**：(1) 游戏面板（账号/每日/队伍信息）(2) 结构化评审报告模板（通过/修改/重做三级结论）(3) 与雷神的自动迭代——不通过时自动驳回给雷神修改
- [ ] **火神增强**：(1) 沙箱执行环境（隔离危险操作）(2) 技术重试机制（执行失败自动诊断+重试）(3) 部署工具（Docker/SSH）
- [ ] **风神增强**：(1) 专属 web_fetch/web_search 工具（替代 exec curl）(2) RSS 订阅源管理 (3) 舆情仪表盘面板 (4) 舆情异常预警 → 三月事件响铃 (5) 定时新闻采集 → 三月定时响铃 → 派蒙推送
- [ ] **岩神增强**：(1) 专属股票 API 工具（A股/港股/美股行情）(2) 红利股筛选引擎 (3) 资产配置计算器 (4) 理财面板 (5) 股价/分红提醒 → 三月定时响铃
- [ ] **冰神增强**：(1) ~~自动扫描 skills/ 目录写入世界树 skill 声明域~~ —— 2026-04-23 `SkillRegistry.sync_to_irminsul` 启动时 UPSERT builtin 源 + 孤儿扫描（`registry.py` / `bootstrap.py`）(2) ~~运行时插件加载 → 经死执审查~~ —— 2026-04-23 `paimon/angels/watcher.py` watchdog 监听 `skills/*/SKILL.md` + debounce 300ms + `SkillRegistry.reload_one/remove_one` + `jonova.review_skill_declaration`（热重载过死执，按用户决议偏离 docs "builtin 跳过审查"策略）；默认关，`.env SKILLS_HOT_RELOAD=true` 开启 (3) AI 自举生成 skill 能力 (4) ~~插件面板~~ —— 2026-04-23 已完成（含授权查看/撤销 tab + Skill 生态 tab）
- [ ] **时执独立模块化**：(1) ~~从 Model 中搬出 compress_session_context 到 paimon/shades/istaroth.py~~ —— 2026-04-23 完成，顺带实装 4 项改进（阈值公式 `window - max_tokens - 8k buffer` / 保留段 tool_use·tool_result 对齐 / Prompt 4 章节 + NO_TOOLS / 连续 3 次失败熔断 auto_compact_disabled 持久化）(2) 会话不活跃超时（可配置，默认 1h）→ 自动归档 (3) 自动分层：热(活跃)→冷(30天)→过期(90天删除) (4) ~~经验提取 hook：压缩后提取关键信息写入世界树 memory 域~~ —— 2026-04-23 随 L1 记忆系统实装 (`istaroth.extract_experience`)

## 2. 技术选型层面

- [x] ~~**地脉**实现~~ —— 2026-04-22 asyncio.Queue 进程内发布/订阅
- [x] ~~**时执**归档存储介质~~ —— 2026-04-22 归档与活跃同库在世界树内
- [x] ~~**世界树**存储方案~~ —— 2026-04-22 单 SQLite + 文件系统混合，10 个数据域
- [x] ~~**原石**重构为服务层~~ —— 2026-04-22 数据落盘走世界树 token_* API
- [x] ~~**会话**迁移到世界树~~ —— 2026-04-22 自动从 JSON 迁移到 SQLite
- [ ] **神之心**分层标准：参数量 / provider / 成本？
- [ ] **时执**上下文压缩阈值（3.5k 偏低）
- [ ] **生执**依赖环回滚机制（saga / 状态快照）
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
