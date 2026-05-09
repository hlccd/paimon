# 交互架构：用户视角的消息流

> 隶属：[神圣规划](aimon.md)
>
> 本文档从**用户视角**描述派蒙与用户的交互时间线：在 chat / skill / /agents / /evolve 各路径下，用户在 WebUI 和 QQ 分别会看到哪些消息、以什么样的节奏送达。
>
> 实施情况见各模块 docs。


---

## 一、核心思想

### 1.1 两层分离

```
业务层（path 决定打什么标签）
  ┌──────────────────────────────────┐
  │ 闲聊 / skill / 四影 的 notice 序列 │   渠道无关
  └──────────────────────────────────┘
                 ↓
渠道层（channel 决定能不能送达）
  ┌──────────────────────────────────┐
  │ Web: 尽量送达 + 弱化样式          │
  │ QQ:  seq 预算内送达 + 窗口外丢弃  │   按能力 degrade
  └──────────────────────────────────┘
```

- **业务代码只打标签**（ack / milestone / tool / thinking / done_recap），不关心 channel 是谁。
- **渠道代码只管送达**：Web 基本全发；QQ 按 5 条 `msg_seq` 预算 + 290s 被动窗口做过滤。
- **同一事件在两渠道的文案完全一致**，差别只在"Web 收到 / QQ 因窗口关而没收到"。

### 1.2 notice 种类速览

| kind | 含义 |
|---|---|
| `ack` | 任务接收即时回执（含任务短标题） |
| `milestone` | 关键阶段切换（死执通过 / 已编排 / 已派发 / 等）|
| `tool` | 单次工具调用（仅 Web） |
| `thinking` | 25s 静默兜底（仅 Web） |
| `done_recap` | 完成 / 失败的最终摘要 |

### 1.3 视觉样式

- **Web**：`notice` 一律渲染为**浅灰小字、无头像、轻缩进**，和正文气泡视觉分层；多条 `thinking` 覆盖同一元素，不堆积。
- **QQ**：每条 notice 都是一条独立 QQ 消息（QQ 没气泡样式可做弱化），所以只发关键事件，不发工具/watchdog 这类琐碎的。

---

## 二、场景时间线

### 2.1 闲聊（chat）

用户说："你好派蒙"

**Web**：
```
[typing 动画闪烁]
→ 「你」「好」「呀」「，」「旅」「行」「者」...（逐字蹦出）
→ ---
   0.82秒 | ~$0.0003 · 🧠 deepseek-chat
```
若首 token 超 25 秒未出 → 浅灰小字"…还在忙，已工作 25s…"（后续 token 把它覆盖）。

**QQ**：
```
（等 2-3 秒）
↓
你好呀，旅行者！我是派蒙，有什么可以帮你的？
```

闲聊**没有 ack / milestone**。意图分类 < 1s，直接回复正文即可。

---

### 2.2 skill 直调

用户粘贴："https://www.bilibili.com/video/BV..."

**Web**：
```
┌ [浅灰] 🎯 走 bili，通常 10-30 秒 —— 做：抓取视频信息
├ [浅灰] 🔧 正在调用 web_fetch
├ [正文] 这个视频是...（逐字流式）
└ ---
   12.3秒 | ~$0.002 · 🧠 deepseek-chat
```

若工具静默超 25s → 浅灰"…还在忙，已工作 25s…"。

**QQ**（`tool` / `thinking` 渠道层丢弃）：
```
[seq 1] 🎯 走 bili，通常 10-30 秒 —— 做：抓取视频信息
[seq 2] 这个视频是...（完整一段）
```

skill 的"短标题"（上例中"抓取视频信息"）来自 skill description。

---

### 2.3 自进化提案（/evolve）

用户发：`/evolve 把刚才那段流程沉淀为 skill`

不走多轮 DAG 编排——直接调 propose_skill + review_proposal 函数链，30 秒到 1 分钟内反馈。

**Web / QQ**：
```
用户: /evolve [可选提示]

派蒙·入口安全审 → 生执·propose_skill 凝练 → 死执·review_proposal 审

✓ 已产出新提案：**paper-summary**（死执·通过）

把长论文压成 3 段：背景 / 方法 / 结论 + 关键数字

前往 `/plugins#proposals` 查看完整草案 + 同意/拒绝。
```

判定不值得做时：
```
✓ 自进化判定**未产出新提案**——LLM 看完最近对话认为没有值得沉淀的 skill。
你也可以加 `/evolve <更具体的提示>` 引导方向。
```

后续在 `/plugins#proposals` 面板：
- 看死执评语 + 草案全文
- 同意 → 空执 apply 落 `<repo>/skills/<name>/SKILL.md` + 注册 → 立即可用
- 拒绝 → status=rejected（30 天后 cron 清）

chat 每 5 条消息浅判触发 + 月度 cron 触发的提案直接落 `/plugins` 面板待审，无对话流提示。

---

## 三、渠道能力对照

| 方面 | WebUI | QQ |
|---|---|---|
| 正文样式 | 逐字流式 | 整段一次性 |
| `ack` / `milestone` 样式 | 浅灰小字、无头像、视觉弱化 | 独立消息条（QQ 无样式区分能力） |
| 工具调用提示 `🔧` | 有 | 无 |
| `…还在忙…` watchdog | 有（25s，上限 3 条，同元素覆盖） | 无（seq 宝贵） |
| 自进化提案产出反馈 | 一条文本回复指向 `/plugins#proposals` | 同 |
| 权限询问 `ask_user` | 支持（独立气泡 + 输入框） | 支持（发询问消息 + 等下条入站消息作答；30s 超时保守拒绝） |

---

## 四、task-list（两渠道共用）

主动查询历史任务的能力。数据同源（世界树 task 表），展现形式按渠道最优。

### QQ

```
```

- 最多 20 条，按 `updated_at DESC`
- 筛选：`creator startswith '派蒙'` + `lifecycle_stage != 'archived'` + 7 天内
- 索引仅一次 list 后短暂有效（TTL 10 分钟），重新 list 自动重编号
- 按 channel_key 隔离（不同会话各自的编号缓存互不影响）

### WebUI

`/tasks` 面板双 tab："定时任务" / "系统任务"：
- 定时任务：用户主动创建的 cron/interval/once
- 系统任务：archon 注册的内部周期任务（feed_collect / dividend_scan / mihoyo_collect / hygiene / skill_evolve_monthly / skill_proposal_prune 等）

1. workspace `summary.md`（archive 时生成）
2. `push_archive` 里 `actor='时执'` 且 `extra.task_id` 匹配的最终消息
3. 拼接所有 `completed` subtask.result（逐节点兜底）
4. 诊断兜底：区分空状态原因

---

## 五、常见误解澄清

- **"QQ 上为什么不做 watchdog？"**——5 条 msg_seq 预算宝贵，每条 "…还在忙…" 都是吃正文名额，不值当。QQ 用户本来就习惯 bot 有 10-30s 等待。
- **"自进化提案产出怎么知道？"**——派蒙在 /evolve 命令完成后回一条文本指向 `/plugins#proposals`；chat 累积 / 月度 cron 自动触发的提案直接落面板，无对话流提示。

---

> 本文档描述交互**方式**（用户看到什么），不描述实现细节。
