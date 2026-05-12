# Paimon

个人 AI 助手系统，代号"神圣规划"(AIMON)，从 fairy 项目迁移重构。

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
