# 自进化能力

> 隶属：[神圣规划](aimon.md)
> 相关：[世界树](foundation/irminsul.md) · [四影](shades/naberius.md) · [冰神](archons/tsaritsa.md) · [草神](archons/nahida.md) · [时执](shades/istaroth.md) · [三月](foundation/march.md) · [权限与契约](permissions.md)

**定位**：在现有架构之上"跨会话经验积累 → 行为自我调整"，**不新增主干轨道** —— 各能力分散到既有模块（草神 / 时执 / 派蒙 / 四影），不是独立体系。

**核心原则**：所有自进化产物**必须经人工审批**才能生效。AI 自己提案、AI 自己审，但**最后一道闸由用户在面板上手动放行**——避免 AI 自我强化进入循环或 silently 改写自身。

## 能力分层

| 层级 | 能力 | 当前状态 | 业务接口 / 归属 |
|---|---|---|---|
| L1 · 经验记忆 | 跨会话记忆积累与召回 | ✅ **已实装** | **草神**（memory 域唯一写入者 + 业务接口）；时执触发 extract / hygiene cron 周一整理 / 派蒙 prefetch / `/knowledge` 面板 |
| L3 · Skill 自进化提案 | AI 凝练新 / 改进 skill → 待审 → 落盘 | 🟡 **持久层就位 / 调用层未接** | 四影 propose → 死执 review_proposal → `/plugins` 面板待审 → 冰神 apply 落 `.claude/skills/`；写盘仍归**冰神**（skill 域唯一写入者）|
| L4 · 轨迹沉淀 | 为未来 SFT / RL 留原料 | 🟡 部分实装 | 时执 archive + summary 已落档；导出 SFT/RL pipeline 未做 |

> L2 槽位空着——派蒙人设 / skill prompt 调优属于一次性维护工作，不需要独立机制（直接编辑 `.claude/skills/X/SKILL.md` 或 `paimon/templates/paimon.t`）。

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

## L3 · Skill 自进化提案

### 设计意图

让 AI 从「跨会话使用规律」里凝练出**可复用的 skill 草案**，但**不直接落盘**——必经死执质量审 + 用户面板手动确认 + 派蒙安全审才能装入 `.claude/skills/`。三道闸保证：

- **质量门**（死执 review_proposal）：drop 没价值 / 描述空泛 / 跟现有 skill 重叠的提议
- **意愿门**（用户面板）：用户决定要不要这个能力，AI 不能 silently 给自己加技能
- **安全门**（派蒙 skill_review）：tool 越权 / sensitive 命中等安全问题

### 数据流

```
【触发（待实装）】
  方案 A：时执 archive 收尾时浅池 LLM 判 should_propose（事件触发）
  方案 B：三月 cron（如月度）扫一批 task 找模式（cron 兜底）
  方案 C：用户主动 /evolve（手工触发）

【提案产生（待实装）】
  四影·生执 propose_skill stage
    └─ 凝练 skill 草案：name / description / triggers / system_prompt /
       allowed_tools / rationale → 写世界树 skill_proposals 域（status=pending）

【质量审（待实装）】
  四影·死执 review_proposal stage
    └─ 审 skill_prompt 完整度 / 跟现有 skill 是否重叠 / 边界是否清晰
       → 写 review_verdict ∈ {pass, needs_revise, reject}（reject 时联动 status=rejected）

【用户审（已实装）】
  webui `/plugins` → "自进化提案" tab
    ├─ 列待审提案 + 死执评语
    ├─ 同意 → status=approved（死执说 needs_revise 时按钮 disabled）
    └─ 拒绝 → status=rejected + 用户备注

【落盘（待实装）】
  冰神 apply：读 status=approved 提案
    ├─ 派蒙 core/safety/skill_review 跑 tool 越权 / sensitive 检查
    ├─ 写 .claude/skills/<name>/SKILL.md
    ├─ skill_loader 装载 + skill_declarations 注册（source='ai_gen', origin=session）
    └─ skill_proposals.mark_applied(prop_id)
```

### 当前实装状态

| 子项 | 状态 | 实装位置 |
|---|---|---|
| 世界树·skill_proposals 域（schema + Repo + façade）| ✅ 实装 | [`paimon/foundation/irminsul/skill_proposals.py`](../paimon/foundation/irminsul/skill_proposals.py) |
| `/plugins` 面板"自进化提案"tab + 5 个 API | ✅ 实装 | [`paimon/channels/webui/api/plugins.py`](../paimon/channels/webui/api/plugins.py) / [`plugins_html.py`](../paimon/channels/webui/plugins_html.py) |
| 状态机保护（同名去重 / approve 卡 needs_revise / applied 不可 reject）| ✅ 实装 | Repo 层 |
| 生执 propose_skill stage | ❌ 未实装 | 待加 `paimon/shades/naberius/propose.py` |
| 死执 review_proposal stage | ❌ 未实装 | 待加 `paimon/shades/jonova/review_proposal.py` |
| 触发器（archive hook / cron）| ❌ 未实装 | 待加 |
| 冰神 apply（读 approved 写盘 + 注册）| ❌ 未实装 | 待加 |

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
        │       │   冰神 mark_applied
        │       │           │
        ▼       ▼           ▼
     rejected  rejected   applied （永不可删，作为 skill 起源审计）
        │
   三月 prune（N 天后清理）
```

**关键保护**：
- 同名 + 同 kind + status=pending 提案去重（避免模型反复刷同一 skill 形成 spam）
- `approve()` 校验 `review_verdict != 'needs_revise'`：死执说要修就必须先重产再审，用户硬批等于绕过质量门
- `delete()` 拒绝 `applied`：已落盘 skill 的起源审计不可删
- `prune_old()` 默认仅清 `rejected`；`applied` 永不清

### 频率约束（重要）

**自进化不强制**——不是每天/每周必须有新 skill。设计意图是：

- 没好的提案 → 一条都不出（死执 reject 严格把关）
- 有好的提案 → 用户决定要不要
- 用户长期不审 → 提案在 `pending` 沉淀，不影响系统运行
- `rejected` 提案三月定期 prune（避免表膨胀）；`applied` 永久保留

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
| **Skill 提案产生** | 四影·生执 `propose_skill` stage | 凝练草案落 skill_proposals 域（pending）|
| **Skill 提案质量审** | 四影·死执 `review_proposal` stage | 写 review_verdict + notes |
| **Skill 提案用户审** | 用户通过冰神 `/plugins` 面板 | UI 入口归冰神（同 skill 生态）|
| **Skill 提案落盘** | **冰神**（skill 域唯一写入者）| 读 approved 提案 → 派蒙 safety 审 → 写 `.claude/skills/` + 注册 skill_declarations |

**冰神 vs 自进化的边界**：冰神是 skill 生态的语义负责人 + skill 域唯一写入者；自进化只是给冰神**加了一条新的 skill 来源**（除 builtin / plugin / 现有 ai_gen 之外的新流程）。冰神依然是看门人——`apply` 调用冰神接口，写盘动作都在冰神这边。

## 明确不做

- **mid-turn 自改**：不允许 agent 在当前回合修改自己的 prompt / skill / 记忆
- **绕过用户审**：自进化提案**必须**经面板审批，不允许"AI 自己审 AI 自己提"全自动落盘
- **绕过 review**：任何自进化产物必经死执 review_proposal + 派蒙 skill_review 双重质量+安全审
- **强制频率**：不规定"每天/每周必须有 X 条新 skill"；好则有、不好则无
- **RL / 微调主循环**：当前阶段纯原料化，不建训练基础设施
- **主动事件推送**：记忆写入不触发事件广播；唯一运行时更新路径是 leyline 通知
