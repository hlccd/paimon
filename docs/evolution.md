# 自进化能力

> 隶属：[神圣规划](aimon.md)
> 相关：[世界树](foundation/irminsul.md) · [四影](shades/naberius.md) · [草神](archons/nahida.md) · [时执](shades/istaroth.md) · [三月](foundation/march.md) · [权限与契约](permissions.md)

**定位**：在现有架构之上"跨会话经验积累 → 行为自我调整"，**不新增主干轨道** —— 各能力分散到既有模块（草神 / 时执 / 派蒙 / 四影），不是独立体系。

**核心原则**：所有自进化产物**必须经人工审批**才能生效。AI 自己提案、AI 自己审，但**最后一道闸由用户在面板上手动放行**——避免 AI 自我强化进入循环或 silently 改写自身。

## 能力分层

| 层级 | 能力 | 当前状态 | 业务接口 / 归属 |
|---|---|---|---|
| L1 · 经验记忆 | 跨会话记忆积累与召回 | ✅ **已实装** | **草神**（memory 域唯一写入者 + 业务接口）；时执的会话压缩触发草神 extract_experience 抽取 / hygiene cron 周一整理 / 派蒙 prefetch / `/knowledge` 面板 |
| L3 · Skill 自进化提案 | AI 凝练新 / 改进 skill → 待审 → 落盘 | ✅ **已实装** | 生执 propose → 死执 review → `/plugins` 面板待审 → 空执 apply 落 `<repo>/skills/`。触发器：`/evolve` 用户主动 + chat 每 5 条消息浅判 + 三月 cron 月度扫 + 周度 prune rejected |
| L4 · 轨迹沉淀 | 为未来 SFT / RL 留原料 | 🔴 暂未实装 | task 域已删除；当前没有自进化以外的执行链路产生轨迹。会话压缩归档跟训练原料用途不重合 |

> L2 槽位空着——派蒙人设 / skill prompt 调优属于一次性维护工作，不需要独立机制（直接编辑 `skills/X/SKILL.md` 或 `paimon/templates/paimon.t`）。

## 设计原则

1. **不新增主干**：能力落在已定义组件上（世界树 / 时执 / 派蒙 / 草神 / 四影），只扩能力边界
2. **进化只发生在会话边界**：严禁 mid-turn 自改 prompt / skill / 记忆；所有写入在时执收尾或三月定时触发
3. **只存不推**：记忆写入世界树遵循"只存不推"原则；派蒙按"启动读 + 四影通知"两条路径感知
4. **草神是业务接口，世界树是存储**：记忆读写业务接口由草神收口，落盘走世界树
5. **写入者单一**：每一类记忆只有一个写入者，避免冲突
6. **三道闸**：所有自进化产物经"死执质量审 → 用户面板审 → 派蒙安全审"三道闸，缺一不可；任一闸阻断即不落地

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
【会话压缩 - 经验提炼】
  时执 compress 末尾触发草神 extract_experience()
    ├─ 浅池 LLM 抽取候选记忆（按四分类）
    ├─ 去重 / 合并
    └─ 写世界树 memory/（actor=草神）

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
- 草神提取：[`paimon/core/memory_classifier/experience.py`](../paimon/core/memory_classifier/experience.py)（由时执 _compress 触发）
- 派蒙 prefetch：[`paimon/core/chat/_prompt.py`](../paimon/core/chat/_prompt.py) `_load_l1_memories`
- 草神 hygiene：bootstrap cron 周一触发
- 面板：webui `/knowledge`

## L3 · Skill 自进化提案

### 设计意图

让 AI 从「跨会话使用规律」里凝练出**可复用的 skill 草案**，但**不直接落盘**——必经死执质量审 + 用户面板手动确认 + 派蒙安全审才能装入 `skills/`。三道闸保证：

- **质量门**（死执 review_proposal）：drop 没价值 / 描述空泛 / 跟现有 skill 重叠的提议
- **意愿门**（用户面板）：用户决定要不要这个能力，AI 不能 silently 给自己加技能
- **安全门**（派蒙 skill_review）：tool 越权 / sensitive 命中等安全问题

### 数据流

四个阶段串成一条链：触发 → 生执凝练 → 死执质量审 → 用户面板审 → 空执落盘。

**触发**（四个入口都跳过任务编排，直接调生执 + 死执函数链）：

| 入口 | 触发条件 |
|---|---|
| 普通对话 | 每 5 条用户消息后台浅判一次 |
| 用户主动 | `/evolve` 命令 |
| 月度扫描 | 每月 1 日 04:00（先清 30 天前未审 pending → 再扫近 30 天任务汇总） |

**生执凝练**：LLM 看上下文，值得做就产出 skill 草案落待审队列。一次最多 5 条；同名草案与现有 pending 去重复用；队列总数超过 25 时 LRU 删最早。

**死执质量审**：循环每条草案独立审 4 维度（完整度 / 重叠 / 工具最小权限 / 边界），裁决三档（通过 / 要修 / 直拒）；整体严格度取最严档。

**用户面板审**：`/plugins` 列待审草案 + 死执评语 + 已重写次数。三个动作：同意立刻调空执落盘；拒绝归档；提建议改写则后台让生执按反馈产新版本 + 死执再审一道。重写期间锁同意 / 再提建议按钮，仅留拒绝。

**空执落盘**：派蒙安全审通过后写到 `skills/` 子目录，注册到 skill 声明域；状态标 applied 后永久保留作起源审计。

### 当前实装状态

| 子项 | 状态 | 实装位置 |
|---|---|---|
| 世界树自进化提案域 | ✅ 实装 | [`paimon/foundation/irminsul/skill_proposals.py`](../paimon/foundation/irminsul/skill_proposals.py) |
| `/plugins` 面板"自进化提案" tab | ✅ 实装 | [`paimon/channels/webui/api/plugins.py`](../paimon/channels/webui/api/plugins.py) / [`plugins_html.py`](../paimon/channels/webui/plugins_html.py) |
| 生执凝练 + 按反馈重写 | ✅ 实装 | [`paimon/shades/naberius/`](../paimon/shades/naberius/) |
| 死执质量审 | ✅ 实装 | [`paimon/shades/jonova/review_proposal.py`](../paimon/shades/jonova/review_proposal.py) |
| 空执落盘 + 注册 | ✅ 实装 | [`paimon/shades/asmoday/apply_proposal.py`](../paimon/shades/asmoday/apply_proposal.py) |
| `/evolve` 命令 + 对话累积触发 | ✅ 实装 | [`paimon/core/commands/evolve.py`](../paimon/core/commands/evolve.py) / [`paimon/shades/istaroth/_propose_trigger.py`](../paimon/shades/istaroth/_propose_trigger.py) |
| 月度扫描 + 周度清理 | ✅ 实装 | [`paimon/shades/istaroth/proposal_cron.py`](../paimon/shades/istaroth/proposal_cron.py) |

### 状态机

```text
              create
                ▼
        ┌──── pending ──────┐
        │       │           │
死执 reject     │   用户 approve
        │   死执 needs_revise（approve 按钮 disabled）
        │       │           │
        │       │           ▼
        │       │       approved
        │       │           │
        │       │   空执 mark_applied
        │       │           │
        ▼       ▼           ▼
     rejected  rejected   applied （永不可删，作为 skill 起源审计）
        │
   三月 prune（N 天后清理）
```

**关键保护**：

- 同名同类型 pending 去重，避免反复刷同一草案
- 单次凝练上限 5 条，pending 队列上限 25（满则删最早）
- 死执说要修 / 正在重写中 → 同意按钮不可点
- 已落盘草案的起源审计不可删，月度仅清 30 天前未审 pending（用户一个月没决策 = 大概率不需要了）
- 提建议改写期间用 `revising_at` 时间戳标记，链路完成清空；服务异常重启时启动清扫超 10 分钟的僵尸标记，避免按钮永久锁死

### 频率约束（重要）

**自进化不强制**——不是每天/每周必须有新 skill。设计意图是：

- 没好的提案 → 一条都不出（死执 reject 严格把关）
- 有好的提案 → 用户决定要不要
- 用户长期不审 → 提案在 `pending` 沉淀，不影响系统运行
- `rejected` 提案三月定期 prune（避免表膨胀）；`applied` 永久保留

## L4 · 轨迹沉淀（暂未实装）

task 域已删除；当前自进化以外没有执行链路产生轨迹。会话压缩归档（草神 memory）跟训练原料用途不重合。
如果未来需要 SFT/RL pipeline，需要重建任务编排与轨迹采集机制。

## 权限与安全

| 场景 | 归属 | 说明 |
|---|---|---|
| 记忆写入 | **草神**（memory 域唯一写入者）| 时执触发 / 面板编辑 / cron hygiene 三条来源都收口于草神 |
| 记忆读取 | 派蒙 prefetch / 草神 hygiene / 草神 `/knowledge` 面板 | 派蒙只读本地缓存 |
| 记忆撤销 | 用户通过草神 `/knowledge` 面板 | UI 入口归草神，落盘走世界树 |
| **Skill 提案产生** | 四影·生执 `propose_skill` stage | 凝练草案落 skill_proposals 域（pending）|
| **Skill 提案质量审** | 四影·死执 `review_proposal` stage | 写 review_verdict + notes |
| **Skill 提案用户审** | 用户通过 `/plugins` 面板 | UI 入口归空执|
| **Skill 提案落盘** | **空执**（skill 域唯一写入者）| 读 approved 提案 → 派蒙安全审 → 写 `skills/` 子目录 + 注册声明 |

**空执 vs 自进化的边界**：空执是 skill 域唯一写入者；自进化只是给空执加了一条新的 skill 来源（除内置 / plugin 之外）。落盘动作都收口在空执的 apply。

## 明确不做

- **mid-turn 自改**：不允许 agent 在当前回合修改自己的 prompt / skill / 记忆
- **绕过用户审**：自进化提案**必须**经面板审批，不允许"AI 自己审 AI 自己提"全自动落盘
- **绕过 review**：任何自进化产物必经死执 review_proposal + 派蒙 skill_review 双重质量+安全审
- **强制频率**：不规定"每天/每周必须有 X 条新 skill"；好则有、不好则无
- **RL / 微调主循环**：当前阶段纯原料化，不建训练基础设施
- **主动事件推送**：记忆写入不触发事件广播；唯一运行时更新路径是 leyline 通知
