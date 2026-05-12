# Paimon

个人 AI 助手系统，代号"神圣规划"(AIMON)，从 fairy 项目迁移重构。

## 协作规范（每次执行任何任务都要遵守，违背任一条都是 anti-pattern）

1. **不确定就问，别猜**
   需求里有任何模糊（"加个验证"、"优化一下"、"顺手处理一下"、"再完善点"），先问清楚要什么，不要脑补一份方案就开干。表现出犹豫不丢人，装懂才丢人。

2. **没要求的不写**
   要个小功能就实现小功能。不顺手搭企业级抽象、不预留"未来可能要的"扩展点、不补完没要求的边界处理、不写超出需求范围的兜底逻辑。"三行相似代码"也比"过早抽象"强。

3. **只改被要求的部分**
   修 bug 就只改 bug 路径上的代码。旁边代码风格不爽不改、变量名不顺眼不改、注释看着冗余不删。diff 要干净到一眼能 review — 30 行改动里只能有 30 行跟需求相关，不能有"顺手"。

4. **给验收标准，按标准达标即停**（最大杠杆）
   当用户给"终点"（如：先写测试 + 所有测试通过、截图肉眼对得上、跑起来不报错就算成功），跑到达标停下；不要被中间步骤拆解分散变成无限补充。"擅长跑到达标"是 agent 的强项，要利用。

## 项目状态
- 当前阶段：架构规划完成，代码尚未开始
- 源项目：/home/mi/code/fairy（Python 3.12，三省六部架构）
- 分期方案：docs/migration-plan.md

## 架构
- 架构文档入口：docs/aimon.md
- 四层架构：派蒙(入口) → 天使(简单任务) / 四影+七神(复杂任务) → 基础设施层
- 命名主题：原神

## 技术栈
- Python 3.12, async throughout
- LLM: Anthropic (Claude) + OpenAI
- Channels: WebUI (aiohttp), Telegram (aiogram), QQ (qq-botpy)
- DB: SQLite (aiosqlite)
- 语言：中文

## 项目地图（涉及代码/架构改动必读）

paimon 5w+ 行代码 / 387 文件，超出单 context window 一次吃完规模。**做以下任一类工作前必须先读 `graphify-out/GRAPH_REPORT.md`**（不要自己判断要不要看，触发即读）：
- 增/改/删 paimon 或 skills 的代码
- 重构 / 模块归属调整 / 跨模块依赖修改
- 清理废弃代码 / 排查影响面

报告含：48 个 community 的中文命名（archon/世界树/skill/WebUI 等）、God Nodes（核心抽象 + 度数）、跨模块惊喜连接、孤立点。

更细查询走命令：
- `graphify query "..."` — BFS 子图
- `graphify path "A" "B"` — 节点最短路径
- `graphify explain "X"` — 节点 + 邻居详情

## 项目地图维护规则

### 何时重跑 graphify

**大更新后必须重跑** `graphify update .`（2 秒，纯 AST，不烧 LLM）。触发：
- 增/删多个文件 / 重构 / 改架构
- 改 archon、task_types、subscription_types 等注册体系
- 任何会让"项目结构"变化的改动

不重跑 = 图谱跟代码偏离 → 后续基于图谱的分析得到错误结论。

**过期判断**：`git rev-parse HEAD` 对比 `GRAPH_REPORT.md` 顶部 `Built from commit`，不一致就跑。

### graphify 涉及调 LLM 时（强约束）

**禁止走 graphify 自己的 backend 体系** — 不装 ollama、不申请 gemini/kimi/anthropic 独立 key、不跑 `graphify extract --backend X`。

**做法**：由**当前 Claude 会话**用自己的能力直接做（复用 paimon 现在已经在用的 LLM 通道，不另起锅灶）。常见场景：
- **community 命名**（`### Community N - "X"` 起中文名）→ 读 `graph.json` 拿每个 cid 的 god node + 样例节点 + 主目录，Claude 起名写到 `graphify-out/.graphify_labels.json`
- **文档语义节点抽取**（让 docs/PDFs 进图谱）→ Claude 读文件后按 graphify schema 写 JSON 节点，merge 进 `graph.json`
- **实体去重 LLM tiebreak**（dedup 80–92 分灰色区间）→ Claude 实时判断，不调外部 API

理由：避免 paimon 项目里出现"两套 LLM 配置"。
