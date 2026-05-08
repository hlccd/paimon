# 自进化能力

> 隶属：[神圣规划](aimon.md)
> 相关：[世界树](foundation/irminsul.md) · [时执](shades/istaroth.md) · [草神](archons/nahida.md) · [三月](foundation/march.md) · [权限与契约](permissions.md)

**定位**：在现有架构之上"跨会话经验积累 → 行为自我调整"，**不新增主干轨道** —— 各能力分散到既有模块（草神 / 时执 / 派蒙 / 四影），不再是独立体系。

## v7 后能力分层

| 层级 | 能力 | 当前状态 | 业务接口 / 归属 |
|---|---|---|---|
| L1 · 经验记忆 | 跨会话记忆积累与召回 | ✅ **已实装** | **草神**（memory 域唯一写入者 + 业务接口）；时执触发 extract / hygiene cron 周一整理 / 派蒙 prefetch / `/knowledge` 面板 |
| L2 · Prompt 进化 | 派蒙人设 / skill prompt 自调 | 🟡 由四影 `/task` 承接 | "优化 X 的 prompt 表达"作为写代码任务（生执 produce_*）|
| L3 · Skill 自举 | AI 生成新 skill | 🟡 由四影 `/task` 承接 | 写代码任务走生执 produce_spec → design → code → 死执 review_code；落盘归**冰神**（skill 唯一写入者）|
| L4 · 轨迹沉淀 | 为未来 SFT / RL 留原料 | 🟡 部分实装 | 时执 archive + summary 已落档；导出 SFT/RL pipeline 未做 |

> v7 关键变化：原"L2 prompt 进化 / L3 skill 自举"是独立轨道（草神 + 冰神 + 死执联动）；v7 后这些都是**写代码任务**，走 `/task` 即可，不再需要独立机制。

## 设计原则

1. **不新增主干**：能力落在已定义组件上（世界树 / 时执 / 派蒙 / 草神 / 四影），只扩能力边界
2. **进化只发生在会话边界**：严禁 mid-turn 自改 prompt / skill / 记忆。所有写入在时执收尾或三月定时触发
3. **只存不推**：记忆写入世界树遵循"只存不推"原则；派蒙按"启动读 + 四影通知"两条路径感知
4. **草神是业务接口，世界树是存储**：记忆读写业务接口由草神收口，落盘走世界树
5. **写入者单一**：每一类记忆只有一个写入者，避免冲突
6. **安全闸门继承**：AI 自举 skill 走 `/task` 路径，自动经死执 review_code + 派蒙 skill_review

## L1 · 经验记忆（已实装）

### 记忆四分类

| 类型 | 含义 | 典型内容 | 召回时机 |
|---|---|---|---|
| `user` | 用户画像 | 角色 / 长期偏好 / 知识背景 | 每次请求前 prefetch（派蒙 system prompt 注入）|
| `feedback` | 用户对 AI 行为的显式纠正或确认 | "别再主动修测试" / "就这样保持" | 相关话题出现时 |
| `project` | 项目/话题级非显然事实 | 仓库内部约定、跨会话延续的任务状态 | 主题命中时 |
| `reference` | 外部系统指针 | "bug 在 Linear INGEST 项目" / "面板地址" | 主题命中时 |

### 实装链路

```
【时执收尾 - 经验提炼】
  时执 _experience.extract_experience()
    ├─ 浅池 LLM 抽取候选记忆（按四分类）
    ├─ 去重 / 合并
    └─ 写世界树 memory/

【三月定时 - hygiene】
  cron: 周一 00:00 草神 memory_hygiene
    └─ 扫记忆库去重 / 检测冲突 / 过期清理

【派蒙 prefetch】
  派蒙 _build_system_prompt → _load_l1_memories
    ├─ 读 user 类（每次都注）
    └─ 读 feedback 类（每次都注）

【用户主动写】
  /remember 命令 → 草神写 memory 域
  webui /knowledge 面板 → 用户编辑 / 删除
```

实装位置：
- 世界树 memory 域：[`paimon/foundation/irminsul/memory.py`](../paimon/foundation/irminsul/memory.py)
- 时执提取：[`paimon/shades/istaroth/_experience.py`](../paimon/shades/istaroth/_experience.py)
- 派蒙 prefetch：[`paimon/core/chat/_prompt.py`](../paimon/core/chat/_prompt.py) `_load_l1_memories`
- 草神 hygiene：bootstrap cron 周一触发
- 面板：webui `/knowledge`

## L2 · Prompt 进化（由 `/task` 承接）

**v7 设计变化**：原方案是"草神反思 + 三月定时 + 写 persona_patch"独立机制。v7 后**简化为写代码任务**：

- 想优化派蒙人设？→ `/task 调优 templates/paimon.t 让 X 类回复更精炼`
- 想优化某 skill 的 prompt？→ `/task 调优 skills/check/SKILL.md，强调 P0 阈值`
- 想加 feedback 驱动的自动调优？→ 走 `/task` 写一个 cron skill 跑这个流程

走生执 produce_spec → design → code → 死执 review，质量门完整。**不需要独立 persona_patch 机制**。

## L3 · Skill 自举（由 `/task` 承接）

**v7 设计变化**：原方案是"冰神 AI 自举生成 + 死执审查"独立机制。v7 后**直接走 `/task`**写代码（落盘仍归冰神 skill 域唯一写入者地位）：

- "写一个查我 GitHub 提交统计的 skill"
- "把现有的 dividend-tracker 改造成支持港股"
- "做一个 commit-checker skill"

走完整四影管线：
```
/task → 派蒙 task_review
  → 生执 plan（complex 6 节点 DAG）
  → 派蒙 plan_scan + 批量授权（涉及 file_ops/exec 写 skills/）
  → 生执 produce_spec → 死执 review_spec
  → 生执 produce_design → 死执 review_design
  → 生执 produce_code（写 SKILL.md + main.py）
  → 死执 review_code + self_check
  → 时执 archive
  → 冰神热加载（skill_loader）→ 派蒙 skill_review 过审 → 冰神写世界树 skill 域
```

新生成的 skill 经派蒙 `core/safety/skill_review` 自动审查（见 [permissions.md](permissions.md)）。**冰神仍是 skill 生态业务接口 + 世界树 skill 域唯一写入者**（生成动作走 /task 写代码，落盘归冰神）。

## L4 · 轨迹沉淀（部分实装）

时执 archive 已落档完整 DAG + flow_history + progress_log，但**未结构化成 SFT/RL 训练数据**。

**已做**：
- 任务全链路审计入世界树 task 域
- summary.md 写归档目录
- 各 LLM 调用 token / 耗时入原石

**未做**（长期路线图，见 [todo.md](todo.md)）：
- 导出 SFT 数据格式（messages / tool_calls / labels）
- RL 数据 pipeline（success/fail label / reward signal）
- 不搭训练基础设施（成本 ROI 当前阶段为负）

## 权限与安全

| 场景 | 归属 | 说明 |
|---|---|---|
| 记忆写入 | **草神**（memory 域唯一写入者）| 时执触发 / 面板编辑 / cron hygiene 三条来源都收口于草神 |
| 记忆读取 | 派蒙 prefetch / 草神 hygiene / 草神 `/knowledge` 面板 | 派蒙只读本地缓存 |
| 记忆撤销 | 用户通过草神 `/knowledge` 面板 | UI 入口归草神，落盘走世界树 |
| AI 自举 skill | 四影 `/task` 写代码 → 冰神写世界树 skill 域 | 经派蒙 task_review + skill_review；冰神仍是 skill 唯一写入者 |
| Prompt 调优 | 四影 `/task` | 写代码任务，自检 + review 同其他 code |

## 明确不做

- **mid-turn 自改**：不允许 agent 在当前回合修改自己的 prompt / skill / 记忆
- **RL / 微调主循环**：当前阶段纯原料化，不建训练基础设施
- **主动事件推送**：记忆写入不触发事件广播；唯一运行时更新路径是 leyline 通知
- **绕过 review**：任何 AI 自举产物必经四影 review；prompt 调优同样走死执 review_code
- **独立的 persona_patch 机制**：v7 简化为"想调谁的 prompt 就发 `/task`"
