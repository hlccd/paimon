# 待办项 / 下一步

> 隶属：[神圣规划](aimon.md)
>
> 只记录**尚未实现 / 待完善**的事项。已完成项请查 git log。
> 更新时间：2026-05-08

## 0. ⚠️ 最高优

- [ ] **体量控制** —— 项目体量已超出工程化工具链阈值
  - **触发**：跑 `/check` 项目体检「深入」档位 → token/时长爆炸 → 多轮 LLM 工作流不稳定
  - **现状体量**：paimon/ ~280 .py / ~48k 行 + docs/ 24 .md + skills/ 9 SKILL
  - **方向**：
    - 单文件硬约束 ≤500 行（部分已落实，新代码继续守；超限走拆子包）
    - 抽公共 base mixin（webui api auth check / pipeline mixin import）减绝对行数
    - docs 路径引用从「具体 .py + 行号」改「目录 + 接口名/锚点」降低同步成本
    - CI/pre-commit 检查文件行数 + 重复模式预警
    - 评估多轮 LLM 工作流的轮数上限——体量决定 max_rounds 不能照搬 methodology

## 1. 职能层面

- [ ] **推送策略深化**
  - **已做**：`march.ring_event` 60s/10 次滑窗限流 + `dedup_per_day=True` 日级 upsert + `push_archive` 持久化 + 审计 + leyline `push.archived` publish + PushHub 进程内 SSE 扇出
  - **未做**：
    - `level='loud'` 的实际打断 UX —— 字段已预留但全仓无差异化
    - 多事件响铃并发时的优先级仲裁（目前 FIFO）
    - 派蒙 crash 后的积压重播
    - 按 source 分级的频率策略

- [ ] **三月·自检 Deep 暂缓**
  - 底层全部实装；`config.selfcheck_deep_hidden=True` 默认隐藏
  - **卡点**：mimo-v2-omni 对 check skill 的多轮迭代执行不充分
  - **预期解**：换 Claude Opus 级模型给 deep pool（1M context + 原生 agentic 长链指令遵循更强）
  - **恢复步骤**：(1) 配 `CLAUDE_OFFICIAL_API_KEY` + `LLM_DEEP_PROVIDER=claude-official` (2) `SELFCHECK_DEEP_HIDDEN=false` (3) 重启 (4) 视观测再启 cron 分派

- [ ] **测试基础设施** —— 仓库零测试：无 `tests/`、无 `conftest.py`、`pyproject.toml` 无 test 配置、全仓 zero import of pytest / unittest、无 CI workflow。需要设计静态契约测试 / 离线冒烟 / 真实 API 测试分层

- [ ] **权限体系 v2 重新设计**
  - **临时缓解已做**：启动时 builtin skill + 9 个 stage 自动 `permanent_allow`（`permanent_deny` 不覆盖；subject_type=stage）
  - **根本设计待重做**：
    - 工具粒度细化：当前 skill 级；需 tool 级 + 参数模式（`Bash(rm:*)` / `Bash(curl http*download*)`）
    - 单用户场景分级：「自用模式」全自动放行 + 真破坏命令依赖 pre_filter ／「严格模式」按现状询问
  - 正式重构等需求更明确后再启动

- [ ] **七神 B 类节点新职能（雷神 / 火神）**
  - **现状**：raiden / mavuika 是 namespace 永久壳（按"七神保留"铁律）
    - 原写代码 4 件套已转生执 produce_design / produce_code / simple_run（simple_code）
    - 原 exec tool-loop 已转生执 simple_run("exec")
  - **当前形态**：~30 行 namespace 壳（class + name + description + execute 兜底）
  - **目标**：找新职能挂上去（不删，按七神铁律保留 7 个名字）
  - 文件：[`paimon/archons/{raiden,mavuika}.py`](../paimon/archons/)

- [ ] **借鉴 gsuid_core/ai_core 重构 paimon 核心能力** —— `/home/mi/code/gsuid_core/gsuid_core/ai_core/` 20k 行是"LLM-native 助手平台"完整 runtime，几个子系统直接对标 paimon：
  - `ai_core/rag/tools.py` **工具向量化**（Qdrant 存工具描述，LLM 动态检索）—— 对标 skill 生态；多起来后解决"工具列表太长 LLM 挑不中"
  - `ai_core/handle_ai.py` **意图分类 + 分流** —— 对标派蒙意图路由
  - `ai_core/memory/` **双路记忆系统** —— 对标世界树 memory 域 + 草神
  - `ai_core/mcp/client.py` **无状态 MCP 客户端** —— skill_loader 加 MCP 源
  - `ai_core/heartbeat/` **心跳自主决策** —— 对标三月主动性
  - 建议：不要整体照搬；按子系统分别评估、独立立项、逐个吸收

- [ ] **水神·ZZZ 临界推演接口修复** —— 已接但 endpoint 返 `404 page not found`，需 F12 抓真实 URL 重新启用

- [ ] **水神·抽卡拓展** —— 当前已做：三游戏 stoken→authkey 自动换 + GS/SR/ZZZ 抽卡同步入库
  - **UIGF 标准导入**：从 Paimon.moe / Snap Hutao / 椰羊 等工具导出的 UIGF JSON 直接导入
  - **本地抽卡模拟器**：基于官方公告概率 + 保底/小保底规则

- [ ] **用户帮助/教程体系** —— 当前 `/help` 是二级目录硬编码 plain text；docs/ 全是开发者文档无新手 onboarding；WebUI 无引导界面入口
  - 二级 `/help <cmd>` 显示子命令详情 + 典型例子
  - WebUI 新手引导（首次空对话 welcome card）
  - `docs/getting-started.md`：用户视角的"30 分钟上手"
  - 隐式 skill 触发提示（intent 命中 skill 时 UI 显示）

- [ ] **四影执行时长优化** —— 复杂任务（`/task`）当前从死执到时执串行 LLM 调用，单次跑分钟级；用户感知慢
  - **管线阶段并发**：派蒙 task_review（仅看用户原文）+ 生执 plan（同样仅需原文）可并发
  - **review-revise 回合压缩**：水神高置信通过早停规则
  - **轻量验证用浅层模型**：派蒙 task_review "明显安全"路径用 shallow LLM
  - **prompt cache 命中率**：feedback 注入已稳态排序，但 system prompt 主体仍每次 from scratch；改用模板化稳定前缀
  - **空执流水线化**：同层 gather 已并发但层间严格串行

## 2. 自进化（独立机制 + 三道闸）

> 见 [evolution.md](evolution.md)。L1 已实装；L3 持久层就位、stage 与触发器待实装；L4 部分实装。

- [ ] **L3 · Skill 自进化提案 stage + 触发器**（持久层 + 面板已就位，调用层未接）
  - **已实装**：世界树 skill_proposals 域（schema + Repo + façade + 状态机保护）+ `/plugins` 面板"自进化提案"tab + 5 API
  - **待实装顺序**：
    1. 死执 `review_proposal` stage（`paimon/shades/jonova/review_proposal.py`）—— 质量审，写 review_verdict
    2. 生执 `propose_skill` stage（`paimon/shades/naberius/propose.py`）—— 凝练 skill 草案落 skill_proposals
    3. 触发器 —— 候选：(a) 时执 archive 收尾事件触发；(b) 三月 cron 周期扫；(c) 用户 `/evolve` 手动触发；至少先做 a + b
    4. 冰神 apply —— 读 status=approved 提案 → 派蒙 skill_review 审 → 写 `.claude/skills/<name>/SKILL.md` + 注册 skill_declarations + mark_applied
  - **不强制频率**：好则有、不好则无；死执严格把关；rejected 三月定期 prune

- [ ] **L4 · 轨迹沉淀（导出 SFT/RL 数据）** —— 长期路线图
  - 时执 archive + summary 已落档完整轨迹
  - 未做：导出 SFT 数据格式 / RL pipeline / reward signal
  - 不搭训练基础设施（当前 ROI 为负）

- [ ] **Prompt 自动调优** —— 长期方向
  - 短期：直接编辑 `.claude/skills/X/SKILL.md` 或 `paimon/templates/paimon.t`
  - 长期：从 feedback 记忆里聚合"高频纠正模式" → 用 L3 提案机制凑成 prompt 改进提案

## 3. 技术选型层面

- [ ] **异常日志落盘方案** —— 当前 [`log.py`](../paimon/log.py) 全文 25 行，全 level 混合、无独立 error-only handler / 无结构化异常归档。待定：加 error 专属 file handler 或接 Sentry

- [ ] **通用日报合成器**（[`paimon/foundation/digest/`](../paimon/foundation/digest/)）—— 只 prompt 层抽好，实装条件**尚未**达成
  - 真正"起抽 `DigestPipeline` 条件"：≥2 个 LLM 驱动日报实现。届时再读两个找共同抽象
  - 当前动作：保持 prompt 层现状

## 4. 四影管线设计缺陷

### 1. 阶段门控缺失（asmoday 全 DAG 跑完才汇总）

- 现状：`asmoday.dispatch` 按拓扑分层并发跑完整 DAG，**不区分 stage 是不是已挂**
- 问题：`review_spec=revise` 时 design/code 仍基于旧 spec 跑完，浪费 LLM token + 产生迷惑性"review_design pass"
- 改进：死执 review_X 出 revise/redo 后立即取消下游 dispatch（plan 内打 skipped），整轮 verdict 直接定 = 该 review_X 的 verdict
- 文件：`paimon/shades/pipeline/_verdict.py:_resolve_verdict`、`paimon/shades/asmoday.py:dispatch`

### 2. revise 不进 round 2，直接 round_cap_hit

- 现状：日志「已达最大轮次」但只跑了 1 轮
- 排查：`config.shades_max_rounds` 实际值（默认 3，可能被设成 1）
- 改进：max_rounds 至少 2-3；review_spec revise 时确保 round 2 修订 spec
- 文件：`paimon/shades/pipeline/_execute.py:execute`

### 3. 轻量 review LLM 严格度 vs 业务可执行性

- 现状：`_LIGHT_REVIEW_SYSTEM` prompt 让 LLM 把 P1 判 revise
- 问题：LLM 倾向找细枝末节的 P1，导致 spec 反复 revise
- 改进：P1 改 warn-only / 阈值「P1 ≥ 2 才 revise」/ 让 LLM 输出"是否阻塞下游"信号
- 文件：`paimon/shades/jonova/review.py:_LIGHT_REVIEW_SYSTEM`

### 4. /dividend rescore 等"立即返回"命令的 web 显示问题

- 现象：bg task 启动 + push_archive 写入完成，但 webui 前端没显示「已触发...」回复
- 排查：前端 SSE handler 在 dedup 跳过持久化时的 race
- 文件：`paimon/core/chat/_persist.py:_persist_turn`、`paimon/channels/webui/static_html/_chat_html_body_*.py`

### 5. /stop 在 skill / /agents 跑期间无效

- 副作用：天使 skill 调用建独立 ephemeral session.id，但 `state.session_tasks` 按 session.id 索引、`/stop` 按当前 channel 主 session.id 反查 → skill 跑时 /stop 找不到 ephemeral 任务
- /agents 同样：`run_council` 在 cmd_agents 里 await，没注册到 state.session_tasks
- 修复路径：`/stop` 扩展为按 channel_key 反查所有活跃任务批量 cancel
- 文件：`paimon/core/chat/session.py:stop_session_task`、`paimon/core/commands/_dispatch.py:_run_skill_isolated`、`paimon/core/commands/agents.py`

### 6. xhs collector 补抓笔记摘要

- 现状：xhs 搜索列表 DOM 卡片只有 title/author/like，没有正文摘要 → topic skill 输出无 50 字摘要
- 升级路径：search 阶段先拿 note_id list → 二次抓详情页 DOM 拿 body
- 复杂度：每条多一次 chromium goto，N=15 多 30-60s
- 文件：`skills/topic/scripts/lib/sources/xhs.py`

### 7. 提高贴吧 collector 覆盖度

- 现状：贴吧 web 搜索 SPA 每 topic 实际只渲染 3-5 个 .threadcardclass
- 改进路径：百度通用搜索 + `site:tieba.baidu.com/p/` 拿更多链接
- 障碍：百度搜索结果 URL 是跳转链，要 follow；命中率不稳
- 文件：`skills/topic/scripts/lib/sources/tieba.py`
