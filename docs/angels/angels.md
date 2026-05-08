# 天使体系（多视角讨论）

> 隶属：[神圣规划](../aimon.md) / 多视角讨论 [`/agents`]
> 实现：[`paimon/morningstar/`](../../paimon/morningstar/)

## 定义

**天使体系** = 一个 leader 天使（**晨星**） + 11 个协同天使。

- **晨星**：天使中的 leader，负责**全程主持**（拆议题 → 调研 → 召集 → 调度发言 → 综合）；本身也是天使的一员，但不发言、只主持 + 调研。
- **协同天使**：11 个预定义角色，由晨星按议题挑 3-5 个参与讨论；纯文本发言，无 tool 权限。

## 11 个协同天使

按职能分 3 类（**专为分析决策设计，写代码相关挖掘走 `/task` 四影管线**）：

| 类别 | 天使 | 职责 |
|---|---|---|
| **信息加工 3**（scout 收料 → 可讨论素材）| 综述者 / 对比者 / 求证者 | 提炼事实 / 结构化对比 / 质疑信源 |
| **决策视角 5**（多角度权衡）| 经济视角 / 风险视角 / 体验视角 / 生活视角 / 历史复盘 | 成本 / 失败模式 / 易用 / 生活影响 / 过往教训 |
| **推动讨论 3**（突破 / 收敛）| 挑刺者 / 提议者 / 时机视角 | 找毛病 / 推动落地 / 现在做还是等等 |

每个协同天使 = 一段 system prompt（在 [`roles.py`](../../paimon/morningstar/roles.py) 里定义）。同一个底层 LLM 戴上不同 prompt 输出不同视角观点。

## 运作流程（5 阶段）

```text
用户 → /agents <议题> → 派蒙 → 晨星
   │
[scout 阶段 · 可跳过]
   晨星 plan_info：拆议题，输出信息需求清单（JSON，含 skip 标志）
     ↓ skip=true（主观偏好议题）→ 跳过 collect
     ↓ skip=false
   晨星 collect：tool-loop 调 web_search / topic / knowledge / file_ops 收资料 → 信息包
   │
晨星 assemble：LLM 看议题挑 3-5 个协同天使 + 写开题
   │
loop（最多 12 轮发言 / 30 LLM 上限）
   晨星 dispatch（看 history 决定下个发言者 + 给指令 / 是否收敛）
     ↓
   协同天使 speak（专属角色 prompt + 历史上下文 + scout 信息包注入 system context）
     ↓
   收敛？（共识 / 死锁 / 上限）
   │
晨星 synthesize：综合发言 → 共识 / 分歧 / 建议下一步（引用资料时打 [依据] 标）
   │
派蒙 → channel → 用户
```

### scout 阶段

**意图**：议题需要外部数据时（"Redis vs Postgres" / "Sora 现状如何"），先收集再讨论，避免天使凭印象瞎扯。

**实现**：[`paimon/morningstar/_scout.py`](../../paimon/morningstar/_scout.py)

| 子步骤 | 输入 | 输出 | 备注 |
|---|---|---|---|
| plan_info | 议题文本 | JSON `{skip, reason, info_needs:[{topic, source_hint}]}` | 1 次 LLM 调用，浅池 |
| collect | info_needs 清单 | 信息包 markdown（≤4000 字硬截断）| tool-loop 模式，浅池 |

**skip 判定**（plan_info 自己决定）：
- 主观偏好（"我该不该换工作"）→ skip
- 个人范围（"下周二请假吗"）→ skip
- 依赖外部事实（"Redis vs Postgres"）→ collect
- 项目内事实（"我现在 paimon 架构合理吗"）→ collect（指 `source_hint=project` 读项目代码）

**工具白名单**：`web_search / topic / knowledge / memory / file_ops / glob`。**禁 exec**（议题讨论不触副作用）；要 exec 的事走 `/task`。

**信息需求最多 4 条**；超 4 条时 plan_info 自己挑最重要的。

**信息包注入位置**：speak / synthesize 阶段的 system prompt 末尾「# 背景资料」段。dispatch 阶段不注入（晨星调度决策不需要资料）。

## 召集协议

晨星 assemble 阶段 LLM 看议题 + 11 角色清单，挑 3-5 个最相关的返 JSON：

```json
{"members": ["requirement", "architecture", "review"], "opening": "..."}
```

例：
- "群晖 NAS vs 自建 unraid" → 对比者 + 经济 + 生活 + 风险
- "我该不该跳槽到 X 厂" → 经济 + 风险 + 生活 + 历史 + 时机
- "推荐 3 本理财书" → 综述 + 对比 + 求证 + 体验
- "现在该不该买 Mac" → 经济 + 体验 + 时机 + 生活
- "调研 self-hosted 笔记软件" → 综述 + 对比 + 体验 + 生活

## 收敛规则

任一触发即结束讨论：
1. **共识**：晨星 dispatch 时 `should_converge=true`
2. **死锁**：连续 3 轮被指派同一协同天使发言（说明无新视角）
3. **轮次上限**：12 轮发言
4. **LLM 调用上限**：30 次（含 assemble + dispatch + speak + synthesize）

## 输出契约

晨星 synthesize 输出固定 3 段 markdown：
- `## 共识`：1-3 条
- `## 分歧（如有）`：保留双方观点不强制收敛
- `## 建议下一步`：1-2 条可执行行动

## 适用场景

5 类典型场景：
- **决策**：要不要做 X
- **选型权衡**：A vs B 选哪个
- **需求澄清**：用户要的 X 边界在哪
- **复盘对抗**：上次哪做错了
- **方案评估**：这个设计有什么坑

议题没标准答案、需要权衡时走 `/agents`。

## 不适用 / 限制

- **不写代码 / 不调外部 API**：纯讨论引擎，输出纪要给人看；用户拿结论自己 `/task` 落地
- **慢 + 贵**：典型 3 角色 × 4 轮 ≈ 9 LLM 调用 / 1-2 分钟 / ~¥0.003；scout 阶段不 skip 时 +30~50% token（plan_info 1 次 + collect tool-loop 1 次 + 各天使 system context 多 ~3-4k 字背景）
- **同 LLM 扮多角色 mode collapse 风险**：靠 system prompt 拉视角差异，理论上不同模型实例对抗深度更大但 MVP 不做
- **/stop 跑期间无效**：见 [todo §6](../todo.md#6-stop-在-skill--agents-跑期间无效)

## 与四影的边界

| 维度 | 四影（/task）| 天使（/agents）|
|---|---|---|
| 出口语义 | 落产物（写代码 / 文档） | 出纪要（决策辅助） |
| 流程结构 | DAG 多节点串/并行 | 圆桌讨论循环 |
| 角色 | 9 stage（生 / 审 / 派 / 收）| 11 协同天使（视角发言） |
| 主持 | 派蒙·安全审 → 生执·plan → 空执·dispatch（生执 produce / 死执 review）→ 时执·archive | 晨星 |
| 中断 | /stop 可中断 prepare 阶段 | /stop 暂不生效 |
| 典型耗时 | 几分钟（含工具调用） | 1-3 分钟 |

四影**落地**、天使**讨论**，互不交叉。

## 跨模块参考

- [神圣规划总文档](../aimon.md) §2.4 多视角讨论流
