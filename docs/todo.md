# 待办项 / 下一步

> 隶属：[神圣规划](aimon.md)
>
> 只记录**尚未实现 / 待完善**的事项。已完成项请查 git log。
> 更新时间：2026-05-15

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

- [ ] **三月·自检 Deep 暂缓**
  - 底层全部实装；`config.selfcheck_deep_hidden=True` 默认隐藏
  - **卡点**：mimo-v2-omni 对 check skill 的多轮迭代执行不充分
  - **预期解**：换 Claude Opus 级模型给 deep pool（1M context + 原生 agentic 长链指令遵循更强）
  - **恢复步骤**：(1) 配 `CLAUDE_OFFICIAL_API_KEY` + `LLM_DEEP_PROVIDER=claude-official` (2) `SELFCHECK_DEEP_HIDDEN=false` (3) 重启 (4) 视观测再启 cron 分派

- [ ] **测试基础设施** —— 仓库零测试：无 `tests/`、无 `conftest.py`、`pyproject.toml` 无 test 配置、全仓 zero import of pytest / unittest、无 CI workflow。需要设计静态契约测试 / 离线冒烟 / 真实 API 测试分层

- [ ] **权限体系重新设计**
  - **根本设计待重做**：
    - 工具粒度细化：当前 skill 级；需 tool 级 + 参数模式（`Bash(rm:*)` / `Bash(curl http*download*)`）
    - 单用户场景分级：「自用模式」全自动放行 + 真破坏命令依赖 pre_filter ／「严格模式」按现状询问
  - 正式重构等需求更明确后再启动

- [ ] **七神 B 类节点新职能（雷神 / 火神）**
  - **现状**：raiden / mavuika 是 namespace 永久壳（按"七神保留"铁律），~30 行 class + name + description + execute 兜底
  - **目标**：找新职能挂上去（不删，按七神铁律保留 7 个名字）
  - 文件：[`paimon/archons/{raiden,mavuika}.py`](../paimon/archons/)

- [ ] **借鉴 gsuid_core/ai_core 重构 paimon 核心能力** —— `/home/mi/code/gsuid_core/gsuid_core/ai_core/` 20k 行是"LLM-native 助手平台"完整 runtime，几个子系统直接对标 paimon：
  - `ai_core/rag/tools.py` **工具向量化**（Qdrant 存工具描述，LLM 动态检索）—— 对标 skill 生态；多起来后解决"工具列表太长 LLM 挑不中"
  - `ai_core/handle_ai.py` **意图分类 + 分流** —— 对标派蒙意图路由
  - `ai_core/memory/` **双路记忆系统** —— 对标世界树 memory 域 + 草神
  - `ai_core/mcp/client.py` **无状态 MCP 客户端** —— 空执加 MCP 源
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

- [ ] **自进化执行时长优化** —— `/evolve` 调 propose+review 串行 LLM
  - **轻量验证用浅层模型**：派蒙 task_review "明显安全"路径用 shallow LLM
  - **prompt cache 命中率**：feedback 注入已稳态排序，但 system prompt 主体仍每次 from scratch；改用模板化稳定前缀

## 2. 自进化

> 见 [evolution.md](evolution.md)。

- [ ] **轨迹沉淀 → SFT/RL 数据导出** —— 长期路线图
  - 未做：导出 SFT 数据格式 / RL pipeline / reward signal
  - 不搭训练基础设施（当前 ROI 为负）

- [ ] **Prompt 自动调优** —— 长期方向
  - 短期：直接编辑 `skills/X/SKILL.md` 或 `paimon/templates/paimon.t`
  - 长期：从 feedback 记忆里聚合"高频纠正模式" → 用自进化提案机制凑成 prompt 改进提案

## 3. 技术选型层面

- [ ] **异常日志落盘方案** —— 当前 [`log.py`](../paimon/log.py) 全文 25 行，全 level 混合、无独立 error-only handler / 无结构化异常归档。待定：加 error 专属 file handler 或接 Sentry

## 4. 已知 bug

### 1. /stop 在 skill / /agents 跑期间无效

- 副作用：天使 skill 调用建独立 ephemeral session.id,但 `state.session_tasks` 按 session.id 索引、`/stop` 按当前 channel 主 session.id 反查 → skill 跑时 /stop 找不到 ephemeral 任务
- /agents 同样：`run_council` 在 cmd_agents 里 await，没注册到 state.session_tasks
- 修复路径：`/stop` 扩展为按 channel_key 反查所有活跃任务批量 cancel
- 文件：`paimon/core/chat/session.py:stop_session_task`、`paimon/core/commands/_dispatch.py:_run_skill_isolated`、`paimon/core/commands/agents.py`

### 2. 提高贴吧 collector 覆盖度

- 现状：贴吧 web 搜索 SPA 每 topic 实际只渲染 3-5 个 .threadcardclass
- 改进路径：百度通用搜索 + `site:tieba.baidu.com/p/` 拿更多链接
- 障碍：百度搜索结果 URL 是跳转链，要 follow；命中率不稳
- 文件：`skills/topic/scripts/lib/sources/tieba.py`
