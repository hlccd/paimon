# 世界式（World-Formula）

> **文档状态**：草案 / 讨论中 / 不影响现有实现
> **创建日期**：2026-05-05
> **关系**：本文档**不替代** [aimon.md](aimon.md)。新架构稳定后再讨论分模块迁移路径。
>
> 命名缘由：「神圣规划」（aimon）描述当前架构骨架；「世界式」描述对世界的运算方式 ——
> 把「派蒙 → 四影 + 七神」的二层结构拆解成 **三种世界式（task / agents / skill）**，
> 让每种世界式各管一类协作形态。

---

## 0. 一句话总结

把当前「四影主控 + 七神扮演执行节点」的耦合架构，**按协作形态拆三条独立路径**，
七神退出对话执行链、回归「业务主管 + 面板 + skill 归属」职责。

```
当前：用户 → 派蒙 → 意图分类 → (chat / skill 天使 / 复杂任务四影+七神)
                                             ↑
                                      七神扮演 archon 跑 LLM 节点

世界式：用户 → 派蒙 → 意图分类 ┬─ chat
                              ├─ /skill X       → 七神主管的 skill 直触发
                              ├─ /task          → 流水线（四影 + skill 链）
                              └─ /agents        → 多 agent 协同（晨星 + 天使群）

七神退出 /task 和 /agents 的执行链；保留：
  · 业务主管（cron / 后台采集 / 状态获取）
  · 面板展示（feed/wealth/game/knowledge/llm/...）
  · skill 归属（每个 skill 标主管的七神）
```

---

## 1. 动机

当前 `/task` 路径里「四影主控 + 七神扮演执行节点」的实际形态：

| 痛点 | 现象 |
|---|---|
| **同模型同提示扮多角色** | 草神/雷神/水神都跑同一个 LLM model，差别只在 system prompt；输出风格几乎一样，**不像真协作** |
| **流水线机械** | 写代码任务永远是 6 节点固定 DAG，没有根据任务难度/类型动态调整 |
| **review 像橡皮图章** | 水神 review 只能看上游的产出物（spec/design/code 文本），看不到草神/雷神**思考过程**；反馈通过 issue JSON 单向传递回 spec 节点，不是讨论 |
| **没有讨论/辩论** | spec → design → code → review 是单向流水线，缺少「我觉得 A 不对，应该 B」「但 B 在 X 场景会..」这种交锋 |
| **agent 边界不清** | 七神既要扮 archon 跑 LLM 节点（在 /task 里），又要管业务采集（cron）和面板。两个身份冲突 |
| **简单/复杂任务一刀切** | 简单需求也走 6 节点 DAG 浪费 LLM 调用；真复杂任务又缺少多 agent 讨论的能力 |

---

## 2. 三入口

### 2.1 入口分流

| 入口 | 路径 | 协作形态 | 适用场景 |
|---|---|---|---|
| 普通对话 | intent 自动路由 | chat / skill / task / agents | 日常闲聊、快速问答、隐式触发 |
| `/skill <name>` | 直接触发 skill | 单一工具调用 | 用户明确知道要跑哪个 skill |
| `/task <需求>` | 流水线（四影 + skill 链） | 单 LLM + skill 顺序执行 | 写代码 / 有明确产物的任务 |
| `/agents <需求>` | 多 agent 协同 | 同 chat history 多角色发言 | 复杂决策 / 需要权衡的方案设计 |

### 2.2 路由判定

`core/intent.py` 当前已做 `chat / skill / complex` 三分类。世界式扩展为：

```
chat        → 浅层 LLM 直接答
skill       → 命中某 skill 的 trigger 关键词 → /skill X
task        → 写代码 / 修复 bug / 重构 等有明确产物的指令
agents      → 模糊需求 / 多方权衡 / 设计讨论 等需要协同的指令
```

具体判定细节（关键词清单 / LLM 提示）TODO，先把骨架拍板再细化。

---

## 3. /task · 流水线

### 3.1 设计原则

四影 = **纯编排**，不再让七神扮 LLM 节点。各阶段直接调专属 skill。

```
死执 jonova   → 入口安全审（保留现状）
生执 naberius → DAG plan（按任务复杂度选 trivial/simple/complex 档位）
空执 asmoday  → dispatch 各 skill（不再 dispatch 给七神扮 LLM）
时执 istaroth → 归档收尾（保留现状）
```

### 3.2 阶段 → skill 映射

写代码任务的 6 节点 DAG（complex 档位）：

| 阶段 | 当前实现 | 世界式实现 |
|---|---|---|
| spec | 草神 LLM 调用 | `requirement-spec` skill 直接产 spec.md |
| review_spec | 水神轻量 review LLM | `check` skill（spec 模式，多轮迭代） |
| design | 雷神调 architecture-design skill | 同（不变） |
| review_design | 水神轻量 review LLM | `check` skill |
| code | 雷神调 code-implementation skill | 同（不变） |
| review_code | 水神轻量 review LLM | `check` skill |

**关键变化**：
- **三个 review 节点**从「水神 LLM 单次调用」→「`check` skill 跑多轮 N+M+K 审查」
- **spec 节点**从「草神 LLM 写」→「调 `requirement-spec` skill」
- 七神**不再参与执行**

### 3.3 trivial / simple 档位

短任务（< 12 字 trivial / < 40 字 simple）走简化路径：

```
trivial: 1 节点 → 直接调 code-implementation skill（已修，2026-05 commit 3901457）
simple:  2 节点 → code-implementation skill + check skill review
complex: 6 节点 → 上面表格
```

### 3.4 verdict / round 机制

- 单 review 出 `revise` → naberius 重写计划进 round 2（保留现状）
- max_rounds = 3（保留现状）
- 阶段门控（spec=revise 时 design/code 不跑；当前 todo §四影管线缺陷 #1） — 待 v2 实施时一并修

---

## 4. /agents · 多 agent 协同（天使）

### 4.1 角色

```
晨星    leader · 接需求 / 召集天使 / 调度发言 / 判收敛 / 给最终输出
天使    动态召集 N 个 · 每个天使带个临时角色标签（由晨星指定）
```

> 「晨星」「天使」沿用 paimon 项目命名体系（与七神 / 四影 / 世界树 / 神之心 / 原石 / 派蒙
> / 三月女神等同源，全部出自《原神》设定）。本文档不引入跨设定的个体专名，各天使身份用
> 「角色标签」体现，标签由晨星按任务动态指定。

不固定天使数量，**晨星根据任务召集 N 个天使**。每个天使的身份用「角色标签」体现（如「天使·需求分析」「天使·架构」「天使·实施」「天使·审查」「天使·测试」），标签由晨星按任务定。

> 这跟现有的「天使 = skill 1:1」语义**完全不同**：旧天使是 skill 代名词，新天使是**对话中的协作角色**。两者会同名冲突，需要在迁移时重新定义「天使」语义。

### 4.2 协议（同 chat history 多发言）

核心：**所有天使共享同一个 chat history**。每个天使有自己的 system prompt（角色 + 任务）；轮到谁发言时，把整个 chat history 喂给那个天使的 LLM。

```
chat history（同一份）：
  [system: 任务 = 用户原始需求]
  [user: 写个 100 用户的 todo 服务]
  [assistant: 晨星: 召集 3 个天使 — 需求分析/架构/审查]
  [assistant: 天使·需求分析: 补需求 — 并发量 / 可靠性目标？]
  [assistant: 天使·架构: aiohttp + sqlite，理由...]
  [assistant: 天使·需求分析: 100 用户 sqlite OK 但 backup 怎么做？]
  [assistant: 天使·审查: 同意需要 backup，提议 cron 备份]
  [assistant: 天使·架构: 反对，初期不需要...]
  [assistant: 晨星: 已收敛 → 方案 X / 风险 Y / 实施 Z]
```

实现：
- 每个天使是**单 LLM 调用**（不是独立进程），但有自己的 system prompt 描述「你是 X 角色」
- 调用时把整个 chat history 作为 messages 传入
- 该天使返回的 message 以 `[天使·X]: ...` 前缀 append 到 chat history
- 下一轮换另一个天使发言

### 4.3 调度规则（晨星职责）

晨星 = **leader 天使**，做三件事：

1. **接需求 + 召集**：根据任务召集 N 个天使（指定角色标签）
2. **调度发言**：决定下一个发言的天使（按需要 / 按用户 @ 指向 / 按收敛信号）
3. **判收敛**：识别讨论已完成或陷入循环 → 给最终输出

调度策略候选（待选）：
- A. 固定轮转：天使 1 → 2 → 3 → 1 → ...
- B. 晨星每轮指定下一个发言者（基于上一发言内容）
- C. 让发言者自己「@下一位」（自由切换）

我倾向 **B**（晨星每轮判断下一个发言者）—— 最贴近「真实会议有 host」感受。

### 4.4 终止条件

任一满足即终止：
- 晨星宣布 `共识达成 / 收敛`
- 最大讨论轮次达到（如 N = 10 轮，每轮一次发言）
- 用户插话 `停 / 算了 / 结束`
- LLM 调用预算达到（如 30 次 LLM 调用）

终止后晨星生成最终输出（综合各方意见 + 用户原始需求）。

### 4.5 用户插话

讨论进行时用户可以插话。处理协议：

```
状态机：
  讨论中 ──[用户输入]──> 暂停当前轮 ──> 晨星接管判断意图
                                             │
                                             ├─ 补需求/澄清    → 加 chat history，恢复讨论
                                             ├─ 「停/收尾」    → 中止 + 晨星给共识输出
                                             ├─ 「@天使·X」    → 直接 dispatch 到 X 发言
                                             └─ 其他           → 当上下文，继续下一轮
```

实现要点：
- 当前正在思考的天使 LLM 调用 → 收到 user 输入立即 cancel
- 晨星收到 user 输入后做意图判定（一次浅层 LLM 调用）
- 不需要复杂的中断协议，重新进入「晨星调度」状态即可

### 4.6 token cost / 性能问题（待解）

多 agent 同 chat history 协议的代价：
- 每轮发言 = 全 chat history × 1 次 LLM 调用
- 4 个天使 × 5 轮 = 20 次 LLM 调用 + 每次 history 越来越长
- 长任务可能跑 50+ 次 LLM，token 涨快

缓解方向（待 v2 实施时设计）：
- 浅层模型走快速天使（如「天使·审查」用 flash）
- 长 history 用 prompt cache（Anthropic / DeepSeek 都支持）
- 收敛后 chat history 压缩 / 只保留摘要再继续

---

## 5. /skill · 七神主管

### 5.1 skill 归属表

| 七神 | 主管的 skill | 业务身份 |
|---|---|---|
| 风神 venti | web-search / bili / xhs | 信息采集 / 舆情聚类 |
| 岩神 zhongli | dividend-tracker | 红利股扫描 / 价格预警 |
| 水神 furina_game | mihoyo | 米哈游账号 / 签到 / 抽卡 |
| 草神 nahida | requirement-spec / architecture-design / code-implementation / check | 写代码 4 件套 + 知识/记忆管家 |
| 火神 mavuika | exec / file_ops / web_fetch（重型工具） | 工具执行 |
| 雷神 raiden | (退出 — 之前的写代码 skill 主管职责给草神) | (无独立业务) |
| 冰神 tsaritsa | （管理者，不持有） | **skill 生态管理**（注册/装载/审查/卸载） |

> 「主管」= 逻辑归属 / 责任主体，不是技术绑定。冰神不持有具体 skill，但管所有 skill 的生态（这是现状不变）。

### 5.2 触发路径（不经七神）

skill 触发的 4 条路径，**都不经过七神 archon**：

```
路径 1：流水线四影 → 直接调 skill（spec/design/code/check）
路径 2：多 agent 天使 → 通过工具调用 skill（如「天使·实施」用 web_fetch）
路径 3：七神自己 cron → 自动触发自己主管的 skill（如 venti cron 跑 web-search）
路径 4：用户 /skill <name> → 命令式直接调
```

**七神不再是「skill 调用经纪人」**，七神是「skill 主管 + 业务路径自调」。

---

## 6. 七神在世界式的位置

七神在新架构的角色 = **业务主管 + 面板 + skill 归属**：

| 职责 | 描述 |
|---|---|
| **cron 业务采集** | venti 订阅采集 / zhongli 红利股扫描 / furina_game 米哈游签到 / nahida hygiene |
| **面板展示** | feed / sentiment / wealth / game / knowledge / plugins / selfcheck（webui 各业务面板） |
| **skill 归属** | 每个 skill 标主管七神（见 §5.1）；skill 出问题时 user 知道找哪个七神负责 |
| **状态获取** | 各 archon 持有自己业务状态（is_running / 进度等），webui 面板拉这些状态 |

七神**不出现的**地方：
- ❌ /task 流水线执行（spec/design/code/review 节点）
- ❌ /agents 多 agent 讨论（讨论中是天使）
- ❌ 用户对话气泡里以「岩神说...」这种身份发言（除非 user 明确 @）

---

## 7. 老架构处理

### 7.1 不替换原则

- [aimon.md](aimon.md) **保留**，描述老架构（神圣规划）
- 现有 `/task` 路径下「四影 + 七神」执行链**不动**
- 新架构通过 `/agents` 入口**新增**功能，不破坏现有

### 7.2 迁移路径（远期）

当世界式稳定后，分模块切流：

1. 先实施 `/agents` 入口（新增，零破坏）
2. 实施新版 `/task`（七神退出执行链，但当前 `/task` 老路径默认仍生效；通过 config flag 灰度切流）
3. 老路径 sunset N 个月后删除
4. 七神 archon 类的 `execute()` 方法（`[STAGE:xxx]` 分派）退役

### 7.3 不需要兼容

按 user 决策：「**基本不存在兼容的情况**」 — 新老路径完全独立，没有「旧数据迁移到新格式」类的工作。新架构上线时 user 可以接受**重置 .paimon 部分数据**（如旧的 `/task` task workspace 不在新路径里读）。

---

## 8. 待解问题（v2 实施前必须拍板）

按依赖顺序：

### Q-A 路由判定细则
- intent 怎么区分 `task` vs `agents`？关键词清单 / LLM 提示样例？
- 用户没明示 `/task` 或 `/agents` 时默认走哪个？

### Q-B 晨星调度具体协议
- 4.3 节列了 3 种调度策略 — 选哪个？
- 晨星召集天使数量上限（避免 N=20 个 token 爆炸）？
- 角色标签清单要不要预定义（避免随机命名「天使·X」）？

### Q-C chat history 共享技术细节
- session_records 表当前是单 session 单 messages 数组，多 agent 用一个 session 的 messages 还是开新 schema？
- 每个 agent 发言带「角色标签」用什么 role 字段（system/user/assistant/notice/agent_xxx）？

### Q-D 用户插话取消机制
- 当前正在跑的 LLM 调用怎么 cancel？asyncio.CancelledError 一路传播？
- cancel 后已 stream 的部分要不要保留（半句话也算发言历史）？

### Q-E /skill 命令具体语法
- `/skill web-search 关键词`？
- `/skill check src/`？
- 参数格式是 freeform / 还是 skill 自己有声明 schema？

### Q-F 多 agent 的最终输出形态
- 给 user 看的是「整段讨论 markdown」/ 「晨星综合后的最终方案」/ 「两个都看」？
- 讨论历史是否持久化到 session_records？

### Q-G 七神面板里要不要有「请晨星帮我看看」按钮
- 比如 wealth 面板里某只股票分析意见冲突，能不能一键发起 `/agents` 让天使群讨论？
- 跨入口的整合点

### Q-H token 预算 / 防失控
- 多 agent 讨论最多消耗多少 token / 多少 LLM 调用 / 多少时间？
- 怎么熔断（防止陷入循环）

---

## 9. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 多 agent token 涨太快 | LLM 成本 + 用户等待时间 | prompt cache + 浅层模型走简单角色 + max 调用次数熔断 |
| 「天使」语义冲突 | 旧文档说「天使 = skill」、新架构说「天使 = 多 agent 角色」 | 迁移时一并改 docs/angels/angels.md |
| 同模型扮多角色仍像换汤不换药 | 解决不了根本痛点 | 不同天使用不同 model_router profile（如「天使·审查」走 deep / 「天使·实施」走专门 code 模型） |
| /task 流水线退化为 skill 链 = 失去多轮迭代价值 | 写代码任务质量下降 | check skill 本身就是多轮审查，review 阶段保留迭代能力 |
| 用户分不清 /task vs /agents | UX 困扰 | intent 自动判定 + `/agents` 失败时降级为 /task |

---

## 10. Mental render（多 agent 讨论例子）

```
User: /agents 写个 100 用户的 todo 服务

晨星: 收到。这是个有架构权衡的活，召集 3 位天使：
       · 天使·需求分析（梳理边界）
       · 天使·架构（技术选型）
       · 天使·审查（风险/合规）
       讨论开始。

天使·需求分析: 我先补需求 — 并发年资？可靠性目标？是否支持多用户隔离？
天使·架构: 100 用户量级我建议 aiohttp + sqlite，单进程足够。
天使·需求分析: 100 用户 sqlite 性能 OK，但 backup 怎么做？数据丢失能容忍多久？
天使·审查: 提议加 cron 备份，至少日级。
天使·架构: 反对每日全量，初期不需要。可用 sqlite WAL + 周级备份。
天使·需求分析: 同意周级。多用户隔离怎么搞？same db 不同 user_id 列就够了？
天使·架构: 是。schema 加 user_id NOT NULL + 索引即可。
天使·审查: 没看到鉴权设计。是不是要 OAuth / token？
天使·需求分析: 不在范围内 — user 没说要鉴权。

晨星: 共识达成。最终方案：
       · 技术栈：aiohttp + sqlite (WAL) + 周级备份
       · 数据：user_id 列做隔离，schema 简单
       · 不在范围：鉴权 / 实时通知 / 多设备同步
       · 风险：单进程性能上限 ~500 QPS
       
       要不要让我把这个写成 spec.md 走 /task 落地？
       
User: 好的，落地吧
```

---

## 11. 实施路线图

待 §8 待解问题逐个拍板后填。当前阶段：**只讨论方案，不动代码**。

---

## 附 A · 概念对照表

| 概念 | 老架构（aimon） | 世界式 |
|---|---|---|
| 天使 | skill 1:1 代名词 | 多 agent 协同中的角色 |
| 七神 | archon = LLM 节点扮演 + 业务采集 + 面板 | 业务主管 + 面板 + skill 归属（不演 LLM） |
| 四影 | 主控 + 七神扮演节点 | 纯编排 + skill 链（无七神参与） |
| 简单/复杂 | 简单走天使（skill）/ 复杂走四影 | 简单 chat / 命中 trigger 走 /skill / 有产物走 /task / 协同设计走 /agents |
