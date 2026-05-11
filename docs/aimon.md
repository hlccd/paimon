# 神圣规划

> 整体架构代号：**神圣规划**
> 本文档保留**架构总览 + 交互流程**；各模块详情和待办项见下方索引。
>
> - **AIMON** — *Algorithm of Intransient Matrix of Overseer Network*，**永恒统辖矩阵**，指整个系统本体。
> - **PAIMON** — *Primordial* + AIMON，**原初永恒统辖矩阵**，即派蒙。
>
> 入口模块 [`paimon/paimon.md`](paimon/paimon.md) 承载矩阵与用户的唯一接口。

---

## 一、架构总览

### 存储 / 服务分层（架构铁律）

整个 AIMON 采用**存储层 / 服务层**分离：

- **世界树**是全系统**唯一存储层**。所有持久化数据（会话 / 授权 / skill 声明 / 知识 / 记忆 / token / 审计 / 理财）统一落盘。
- **其他所有模块**（派蒙 / 四影 / 七神 / 晨星 / 三月 / 地脉 / 神之心 / 原石）都是**服务层**。持有业务逻辑，**不自建 SQLite 或独立文件库**。
- 一句话：**世界树管"字节"，服务层管"语义"**。

### 模块层级

- **入口·派蒙**（[paimon/paimon.md](paimon/paimon.md)）— **守门 + 路由 + 出口 + 全程安全闸**
  - 接入：WebUI / Telegram / QQ
  - 意图分类 + 4 出口路由 + 出口人格化
  - **安全闸**（[paimon/core/safety/](../paimon/core/safety/)）
    - `task_review`：入口任务级审（`/evolve` 触发自进化前调用）
    - `review_skill_declaration`：skill 装载审（空执装载 plugin / AI 自进化生成 skill 时调）
    - `detect_sensitive`：敏感串过滤（memory / 知识库写入路径）
- **3 个出口**（按任务类型路由）
  - `chat` —— 闲聊、单问单答、复杂分析（派蒙浅层 LLM 直答）
  - `skill` —— 单步任务（直调 skill：[topic / web-search / bili / xhs / check ...](../skills/)）
  - `/agents` —— **分析 / 调研 / 决策辅助**（天使多视角讨论，输出纪要不落地）
  - `/evolve` —— **自进化提案触发**（凝练当前会话为可复用 skill 草案，进 `/plugins` 待审）
- **【自进化提案管线】四影**（生执 / 死执 / 空执 / 时执）
  - [**生执·纳贝里士**](shades/naberius.md) — 凝练 skill 草案；按用户反馈重写
  - [**死执·若纳瓦**](shades/jonova.md) — 审草案质量并裁决（通过 / 要修 / 直拒）
  - [**空执·阿斯莫代**](shades/asmoday.md) — skill 域写入与管理（提案落盘 + 启动装载 + 声明注册 + `/plugins` 面板）
  - [**时执·伊斯塔露**](shades/istaroth.md) — 自进化触发 + 自进化两个 cron + skill 热重载 + 生命周期清扫
  - 触发路径：用户主动 `/evolve` / 对话每 5 条消息浅判 / 月度扫描
  - 落盘归空执（派蒙安全审 + 写 `skills/<name>/SKILL.md` + 注册声明 + 立即热加载）
- **【议事辅助】天使**（晨星 leader + 11 协同天使，**不落地，只出纪要**）
  - **职能定位**：分析 / 调研 / 决策辅助（"该不该做 X" / "选 A 还是 B" / "评估这个方案"）
  - **晨星**：天使体系的 leader，调度（assemble → dispatch+speak loop → synthesize）；本身也是天使的一员
  - **协同天使**：11 个预定义角色（结构性 5 / 评估性 4 / 对抗性 2），晨星按议题挑 3-5 个参与讨论
  - 实现：[`paimon/morningstar/`](../paimon/morningstar/)
- **【业务模块】七神**（各业务域的业务接口 + 数据域归属 + 面板归属 + cron）
  - **职能定位**：每位七神是对应业务域的**业务接口 + 唯一写入者**；不进 LLM 对话流，跟自进化主链路并行存在
  - 7 个 archon class 全部保留（铁律：七神不删）；按当前是否承接业务分两类
  - **A 类（4 个 · 业务接口 + cron + 面板）**：
    - [风神·巴巴托斯](archons/venti.md)：topic UGC 调研业务接口（feed_topic_research 域）+ `/feed` 面板 + `feed_collect` cron + 站点登录代理
    - [岩神·摩拉克斯](archons/zhongli.md)：红利股业务接口（scoring / dividend 域）+ `/wealth` 面板 + `dividend_scan` `stock_watch` cron + scorer
    - [草神·纳西妲](archons/nahida.md)：知识 / 记忆 / 偏好业务接口（**memory 域唯一写入者**）+ `/knowledge` 面板 + `memory_hygiene` `kb_hygiene` cron + 跨会话记忆经验提取（由时执会话压缩触发，写入归草神）
    - [水神·芙宁娜](archons/furina.md)：游戏业务接口（mihoyo 域）+ `/game` 面板 + `mihoyo_collect` `mihoyo_game_collect` cron + `mihoyo_game` sub type
  - **B 类（3 个 · namespace 永久壳，新职能待挂）**：
    - [冰神·冰之女皇](archons/tsaritsa.md)：原 skill 域职能（skill 写入 / `/plugins` 面板 / 自进化落盘）已全部移交空执
    - [雷神·巴尔泽布](archons/raiden.md) / [火神·玛薇卡](archons/mavuika.md)
    - 按七神保留铁律留 ~30 行壳；新职能待挂（见 [`docs/todo.md`](todo.md)）
- **【全局支撑层】**
  - **存储层（唯一）**：[**世界树**](foundation/irminsul.md) —— 13 个主数据域统一落盘（含域 16 skill 自进化提案）
  - **服务层（无状态）**：[**地脉**](foundation/leyline.md)（事件总线）、[**神之心**](foundation/gnosis.md)（LLM 资源池）
  - **服务层（有状态，落盘走世界树）**：[**三月女神**](foundation/march.md)（守护 + 调度 + 推送响铃）、[**原石**](foundation/primogem.md)（token / 花费统计）

### 出口路由表

| 用户场景 | 出口 |
|---|---|
| 闲聊 / 单问单答 / 复杂分析 / 推理 | `chat` |
| 单步明确动作（粘贴域名链接 / 触发关键词） | `skill` |
| 多视角讨论 / 决策辅助 | `/agents` |
| 凝练当前会话为可复用 skill 草案 | `/evolve` |

#### 边界样例

| 用户消息 | 出口 |
|---|---|
| "装饰器是什么" / "30 分钟后提醒我" / "帮我整理一下这周的 git log" | chat |
| "搜一下 RBAC 库" / "看看米游社签到了" | skill |
| "用 sqlite 还是 postgres" / "应不应该上 RBAC" | /agents |
| "把刚才那段流程沉淀成 skill" | /evolve |

### 跨模块参考

- [权限与契约体系](permissions.md)
- [关键边界对照表](boundaries.md)
- [自进化体系](evolution.md)
- [待办项](todo.md)

---

## 二、交互流程

### 2.1 请求流（用户 → 系统）

```text
用户 → channel（WebUI / TG / QQ）→ 派蒙
  （意图分类 + 安全过滤）
   │
   ├── chat       → 派蒙浅层 LLM 直答（含复杂分析 / 推理）
   ├── skill      → skill 直调（topic / web-search / bili / xhs ...）
   ├── /agents    → 天使体系讨论（晨星召集协同天使）
   └── /evolve    → 四影自进化提案管线（生执凝练 → 死执质量审 → 进面板待审）
```

skill 路径**单 tool 超时**返错给 LLM 自愈、**整体超时**直接 reply 错误终止。

### 2.2 响应流（系统 → 用户）

```text
chat / skill:    LLM 输出 ───────────→ 派蒙 → channel → 用户
/agents:         协同天使发言（流式）→ 晨星综合 → 派蒙 → channel → 用户
/evolve:         生执凝练 + 死执审完毕 → 派蒙提示"已落 /plugins 待审" → 用户
三月提醒:        定时任务触发 → 三月 → 派蒙 → channel → 用户
```

**派蒙是用户对话的唯一出入口**——三月响铃 / 晨星 / 自进化提案等需要回话给用户时都经派蒙人格化送达；派蒙挂掉时三月只做拉起 + 暂存，绝不代发。

> Web 面板交互（`/feed` / `/wealth` / `/game` / `/knowledge` / `/plugins` / `/tasks` 等）不走对话流，是独立的 webui API 直读 irminsul + 空执 SkillRegistry 路径，跟派蒙对话出入口并行存在。

### 2.3 自进化提案流（/evolve / chat 累积 / 月度 cron）

```text
触发源（三选一）：
  - 用户主动 `/evolve` 命令
  - 三月 cron `skill_evolve_monthly`（每月 1 日 04:00 扫近 30 天任务）
   │
派蒙·task_review（入口审，仅 /evolve 显式触发时调）
   │
生执·propose_skill：凝练 skill 草案
   ├─ SKIP（不值得做）→ 短路退出
   └─ 落 skill_proposals 域 status=pending
   │
死执·review_proposal：审 → 写 review_verdict
   - pass        → 用户面板可同意
   - needs_revise → 用户面板 approve 按钮 disabled，要重产
   - reject      → 联动 status=rejected
   │
[用户在 /plugins#proposals 面板审]
   ├─ 同意 → status=approved → **空执 apply**（派蒙安全审 + 写 SKILL.md + 注册声明 + 热加载）
   └─ 拒绝 → status=rejected（时执 cron 30 天后清）
   │
空执 apply 完成 → status=applied（永不可删，作 skill 起源审计依据）
```

**分工铁律**：
- **派蒙** = 守门 + 路由 + 出口 + 全程安全闸（task_review / skill_review）
- **四影** = 自进化提案管线（生执凝练 / 死执质量审 / 空执落盘装载 / 时执归档+触发+热重载）
- **空执** = skill 域写入与管理（提案落盘 + 启动装载 + 声明注册 + `/plugins` 面板）
- **天使** = 议事辅助（不落地，只出纪要）
- **三月** = 调度（cron / 响铃 / 自进化定时触发）

实现位置：`paimon/shades/{naberius,jonova,asmoday,istaroth}/`

### 2.4 多视角讨论流（/agents）

天使体系负责讨论：晨星是 leader（调度），协同天使是参与者（发言）。

```text
用户 → /agents <议题> → 派蒙 → 晨星（leader 天使）
   │
晨星 assemble：LLM 看议题挑 3-5 个协同天使（11 角色池里）+ 写开题
   │
loop（最多 12 轮发言 / 30 LLM 上限）
   晨星 dispatch（看 history 决定下个发言者 + 指令 / 是否收敛）
     ↓
   协同天使 speak（用专属角色 prompt + 历史上下文发言）
     ↓
   收敛？（共识 / 死锁 / 上限）
   │
晨星 synthesize：综合发言 → 共识 / 分歧 / 建议下一步
   │
派蒙 → channel → 用户
```

输出是**纪要**（给人看的），不写代码、不调外部 API；用户拿结论自己决定下一步。

### 2.5 权限询问流程

**skill 路径**（派蒙单项询问）：
```text
调用 skill 前 → 派蒙查本地缓存
  ├── 永久放行 → 直调 + 提示
  ├── 永久禁止 → 拒绝 + 说明
  ├── 普通权限 → 放行 + 友好告知
  └── 敏感权限无记录 → 询问用户，按答复处理
```

**自进化路径**（启动期已 permanent_allow）：
```text
/evolve 命令 → 派蒙 task_review 入口审 → propose+review 直跑（chat 累积浅判命中后直跑，不过 task_review）
  （propose_skill / review_proposal stage 启动期 permanent_allow，无需运行时询问）
  → 落 skill_proposals 待用户面板审 → approved → 空执 apply 时再过派蒙安全审
```

**永久授权关键词**：用户必须明确说"永久 / 以后都..."才入库；只说"放行 / 同意 / 拒绝"仅本次有效。

### 2.6 新 skill 上线流程

```text
启动期：空执扫 skills/ 目录 → 装载内存 SkillRegistry + 注册声明（代码已把关，跳过死执）
运行时：
  ├─ 用户在面板同意自进化提案 → 空执 apply（派蒙安全审 + 写盘 + 注册 + 热加载）
  └─ 文件变化（手动改 / git pull）
     → 时执 watcher 监听到 → 调 reload → 死执审权限声明
        ├── 通过 → 写世界树 + 失效派蒙 authz 缓存
        └── 拒绝 → 拒绝装载 + 写 audit
```

空执是 skill 域**唯一写入者**（启动装载 + 提案落盘）；时执负责热重载；派蒙只从世界树读，不扫 skills 目录。

### 2.7 推送流程（三段式 + 两种触发）

推送链路由**三个角色**分工：

| 角色 | 职责 |
|---|---|
| **数据收集者**（风神 / 岩神 / 其他）| 收集 + 整理推送内容 |
| **三月** | 响铃：决定"什么时候推" |
| **派蒙** | 送达：人格包装 + channel 送达 |

```text
定时触发: 三月(到点) → 数据收集者整理 → 派蒙 → channel → 用户
事件触发: 数据收集者(感知重要 + 整理好) → 三月响铃 → 派蒙 → channel → 用户
```

**规则**：三月不直发；派蒙挂掉时三月保留积压提醒，派蒙恢复后由派蒙补发；数据收集者必经三月响铃。

### 2.8 永不绕过派蒙（铁律）

**对话流**（用户 ↔ 派蒙的消息往返）：
- 所有**对话回复**必须经派蒙（统一人格 / 格式化 / 打断判断）
- 三月响铃 / 四影产物 / 晨星纪要等需要回话时都经派蒙
- channel 的对话路径是派蒙独占的出入口

**Web 面板**（用户在浏览器查数据 / 改配置）：
- 不走对话流，是独立的交互通道（webui api 直读 irminsul + 空执 SkillRegistry）
- 不经派蒙人格化（拿数据展示而已，不需要包装）
- 跟派蒙对话出入口**并行存在**，互不干扰

---

> 本文档为神圣规划的入口与总览，各模块详情、跨模块机制、待办项均在同级目录 / 子目录下展开。
