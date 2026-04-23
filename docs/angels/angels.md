# 天使体系（第一轨·轻量优先）

> 隶属：[神圣规划](../aimon.md) / 第一轨
> 相关流程：[交互流程 2.1 请求流](../aimon.md#21-请求流用户--系统)

## 定义
**天使 = skill 的代名词**，每个 skill 对应一个天使，一一映射。

## 运作方式
1. 派蒙判断任务简单 → 直调对应天使
2. 天使执行结束 → 结果经派蒙返回用户
3. 提示词：「当前为简单任务，正在由【对应 skill】的天使执行，很快就好～」
4. 超时保护：
   - 单次 tool 调用 30s 超时（第一次超时返错给模型自愈，第二次直接触发魔女会）
   - 整体任务 3min 兜底（超时即触发魔女会）
   - 可在 `.env` 以 `ANGEL_TOOL_TIMEOUT_SECONDS` / `ANGEL_TOTAL_TIMEOUT_SECONDS` 覆盖

## 协作流转
- **单天使失败**：反馈派蒙，由派蒙换天使
- **全部天使无果**：通过魔女会通道（尼可对接）流转到四影-七神
- **天使自判复杂**：立即上报，不擅自处理
- **流转前校验**：派蒙再次轻量校验，再交四影做深度审查

## 天使 vs 七神
- **天使**：单一 skill 封装，轻量、可复用
- **七神**：业务域 + 复杂编排，可在内部调用多个天使
- **复用性**：同一个天使既能被派蒙直调（简单路径），也能被七神调用（复杂路径）

## 魔女会通道

**定义**：进入四影审查的**非主路径**通道（派蒙直送是主路径），由魔女会成员 **尼可** 对接。它是"天使路径失败"与"四影深度处理"之间的**桥**，自身不做业务，只负责升级与交接。

**实现**：[`paimon/angels/nicole.py`](../../paimon/angels/nicole.py)（按命名惯例：魔女会由对接人**尼可**代表）
- 异常信号 `AngelFailure(reason, stage)` —— 从天使执行链路向上抛出
- 桥入口 `escalate_to_shades(msg, channel, session, *, reason)` —— 询问用户 + 调四影

### 核心概念：AngelFailure.stage

| stage | 触发场景 | 含义 |
|---|---|---|
| `tool_timeout` | 单 tool 连续 2 次 30s 超时 | 天使自愈一次后仍不行，通常是 skill 设计 / 依赖问题 |
| `total_timeout` | 天使整体超过 3min 未结束 | 任务实际复杂度 > 天使能力 |
| `exec_error` | 其他执行异常（预留） | 天使主动上报 / 运行时错 |

死执可据 `stage` 做差异化审查（`tool_timeout` 偏技术问题，`total_timeout` 偏任务复杂度）—— 当前 MVP 尚未区分。

### 兜底流程

```text
天使异常 → AngelFailure 从 _execute_tool / handle_chat 抛出
   ↓
run_session_chat 捕获 → 调 escalate_to_shades
   ↓
channel.ask_user 向用户询问（附失败原因）：
  「天使处理未完成（原因：xxx）。要转交四影深度处理吗？
   回复「同意 / 放行」即转交，回复「拒绝 / 算了」即终止。」
   ↓ classify_reply 判定
   ├── allow / perm_allow
   │     → 派蒙轻量校验（MVP 占位：仅日志 [派蒙·魔女会] 轻量校验通过）
   │     → run_shades_pipeline(..., escalation_reason=reason)
   │         reason 注入 task.description，creator="派蒙·魔女会"
   ├── deny / perm_deny / unknown → 发一条"已取消转交"，任务终止
   └── NotImplementedError / TimeoutError → 降级提醒（QQ 等无 ask_user 频道）
```

### 兜底场景

- 单 tool 连续 2 次超时 / 整体超时（已实装，见 §运作方式 4）
- 天使发现任务实际复杂，主动上报（尚未实装）
- 派蒙判定高风险 / 敏感操作超出天使能力范围（尚未实装）

### 与派蒙 / 死执的边界

- **派蒙**：入口轻量校验（关键词 / 格式级）—— 进魔女会前再跑一次（MVP 占位）
- **魔女会**：只做"询问 + 转交"，不做内容审查，不持久化状态
- **死执**：四影第一站，负责 LLM 级深度安全审查（包含对魔女会转入任务的增强审查）

魔女会失败原因仅通过 `escalation_reason` 一次性注入四影 `task.description`，由四影后续流程自行处置。

> 冰神新 skill 上线也复用此通道（插件路径，非天使失败路径），详见 [冰神](../archons/tsar.md) 与 [权限与契约](../permissions.md)。

---

## Skill vs Plugin 对比

天使（skill）由冰神动态管理，可随时新增 / 删除（含 AI 自举生成的新 skill）。本节只说明 Skill 与 Plugin 的**跨模块边界**，不列具体清单。

两者均由冰神统一管理，但在启动方式和审查上略有差异：

| 对比项 | Skill（内置天使） | Plugin（第三方 / AI 自生成） |
|---|---|---|
| 来源 | `skills/` 目录下随项目代码提交 | 运行时动态接入 / 冰神 AI 自举 |
| 加载时机 | 启动时加载；`skills_hot_reload=true` 时支持热重载 | 运行时动态装载 |
| 审查 | 启动扫跳过死执（git review 把关）；**热重载过一次死执** | **必过死执审查** |
| 权限声明位置 | 代码 manifest | 装载时写入 |

## 热重载（可选，默认关）

**开关**：`.env` 设置 `SKILLS_HOT_RELOAD=true`

**实现**：[`paimon/angels/watcher.py`](../../paimon/angels/watcher.py)（`SkillHotLoader`）
- watchdog 监听 `skills/*/SKILL.md`
- 300ms debounce 合并 IDE 多次保存
- `create` / `modify` → `SkillRegistry.reload_one` → **送死执 `review_skill_declaration`** → 过审则 UPSERT 世界树 + 更新内存 + 发地脉 `skill.loaded` 事件失效 authz 缓存
- `delete` → `SkillRegistry.remove_one` → 内存移除 + 世界树标 `orphaned=1` + 发地脉 `skill.revoked`
- 拒审的 skill 写 audit 域 `skill_rejected` + reason

**为什么热重载要审？**
`skills_hot_reload` 打开时，用户直接修改 `SKILL.md` 并保存 —— 这是**未 git commit 的 draft**，还没走过 code review；docs 的"git review 把关"前提不成立，故需要过一次死执。

## 工具层（不升级为天使）

`fairy/tools/builtin/` 里的原子工具保留在工具层，被各天使 / 七神按需调用（例：`exec*`、`web_search`、`web_fetch`、`dispatch`、`send_file`、`schedule`、`knowledge_manage`、`tool_refresh` 等）。

**归属注意**（跨模块调用约束）：
- `schedule` 工具的**注册 / 触发**由三月女神独占；其他模块若要定时，通过三月注册任务，不直接调 `schedule`
- `knowledge_manage` 由草神独占（读写走草神，落盘到世界树）
- `dispatch` 由四影（生执 / 空执）使用，天使体系不直接调
