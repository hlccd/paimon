# 三月女神

> 隶属：[神圣规划](../aimon.md) / 基础层

**定位**：远古的月之观测者，整个系统的独立底层守护进程，不参与业务。

## 核心能力

- **守护进程**：派蒙或其他模块崩溃时自动拉起，维系系统存续
  - **派蒙挂掉时**：三月拉起派蒙；积压的提醒保留在三月，等派蒙恢复后由派蒙补发（三月不直发用户）
- **任务观测**：全局任务状态可视化 + ✅ **Web 观测面板**（仅展示，不判断）
- **定时调度**：系统级定时任务调度
  - **风神**：定时拉取新闻
  - **岩神**：定时追踪股价 / 分红
  - **时执**：过期数据清理 ✅ —— `_maybe_trigger_lifecycle_sweep` 在 `_poll` 末尾 hook，每 6h 触发 `paimon/shades/_lifecycle.run_lifecycle_sweep`；单例守护 + sweep 独立 task 失败不影响主轮询
  - **世界树**：缓存预热
- **推送响铃**（两种触发方式）：
  - **定时响铃**：三月按预设时间触发 → 通知对应数据收集者整理内容 → 把整理好的内容交给派蒙
    - 实装：[`MarchService._fire_task`](../../paimon/foundation/march/)（`_poll` 扫 `scheduled_tasks` 域）
  - **事件响铃**：接收数据收集者的响铃请求（感知到重要数据） → 把整理好的内容交给派蒙
    - 实装：[`MarchService.ring_event`](../../paimon/foundation/march/)（复用地脉 `march.ring` 订阅路径，派蒙侧零改动）
    - 接入：`await state.march.ring_event(channel_name=..., chat_id=..., source="风神", message="...")`；`message` / `prompt` 至少一个非空
    - 限流：同 `(source, channel, chat_id)` 三元组 60s 内最多 10 次，超限返 False + warning log
    - audit：每次成功推送记 `event_type="march_ring_event"`；限流拒绝不记
- **响铃约束**：
  - 三月是**唯一响铃入口**（数据收集者不直接找派蒙）
  - 三月**不直发**给用户（送达由派蒙承担，详见 [派蒙](../paimon/paimon.md)）
- **自检体系**（Quick ✅ 已上线 / Deep ⏸ 暂缓 · 2026-04-25）：
  - **运行时诊断（Quick）** — ✅ 可用：`/selfcheck` 斜杠命令触发；秒级纯代码
    探针 9 组件（irminsul / leyline / gnosis / march / session_mgr / skill_registry /
    authz_cache / channels / paimon_home），整体状态派生（ok / degraded / critical）。
    实装：[`paimon/foundation/selfcheck/`](../../paimon/foundation/selfcheck/) `SelfCheckService.run_quick`
  - **核心代码体检（Deep）** — ⏸ 暂缓：底层实装完整但默认隐藏入口。
    当前 mimo-v2-omni 对 check skill 的 N+M+K 多轮迭代执行不充分（~30s 就
    返回简短 finding 停止），跑不出可靠体检结果。
    **开关**：`config.selfcheck_deep_hidden=True`（默认）→ WebUI 按钮隐藏、
    `/selfcheck --deep` 返"暂缓"提示、API 返 503。
    **周期性触发已撤销**：`[SELFCHECK_DEEP]` cron 分派从 `bootstrap._on_march_ring`
    删除；Deep 只保留手动入口（但手动入口当前也隐藏）。
    **保留的代码**：`_run_deep_inner` / `_invoke_check_skill` /
    `_progress_watcher` / 世界树域 12 的 progress_json 等字段全部保留。
    **恢复步骤**（详见 [docs/todo.md §三月·自检·Deep 暂缓](../todo.md)）：
    给 deep pool 配 Claude Opus 级模型 → `.env` 设 `SELFCHECK_DEEP_HIDDEN=false`
    → 重启 paimon。预期解：Anthropic 原生对 agentic 长链执行力显著强于 mimo。
  - **paimon 适配 Claude Code 原生 skill**（跨 skill 的基础能力）：
    `paimon/archons/base.py` 的 `_read_skill_body` 把 SKILL.md 里的
    `${CLAUDE_SKILL_DIR}` 字面替换成 skill 绝对路径；Glob 工具
    ([`paimon/tools/builtin/glob_tool.py`](../../paimon/tools/builtin/glob_tool.py))
    提供跨平台文件通配查找。skill 本身 0 修改。
  - **归档 + 面板**：WebUI `/selfcheck` 提供 Quick 历史 + Modal 详情（删除/下载）。
    Deep 相关 UI 在 `selfcheck_deep_hidden=True` 时自动隐藏。世界树域 12
    `selfcheck_runs` 保留策略 `config.selfcheck_*_retention`；GC 同步删 blob。
  - **静态契约 / 离线冒烟 / Deep 周期性调度**（未实装，留后）。

## 明确不做

- 不做审计、不做异常归因（归属见 [边界对照表](../boundaries.md)）
- 不干预任何业务
- 不自己运行 LLM（定时任务需要 LLM 时转发派蒙/七神）

## 实现

### 数据持久化

定时任务存储在世界树 `scheduled_tasks` 表（域 10），通过 `schedule_*` API 访问。

### 任务模型

```python
@dataclass
class ScheduledTask:
    id: str                      # 12 位 hex
    chat_id: str                 # 投递目标
    channel_name: str            # 频道名
    task_prompt: str             # 任务内容/提示词
    trigger_type: str            # "once" | "interval" | "cron"
    trigger_value: dict          # {"at": ts} | {"seconds": n} | {"expr": "cron表达式"}
    enabled: bool
    next_run_at: float
    last_run_at: float
    last_error: str
    consecutive_failures: int
    created_at: float
    updated_at: float
```

### 执行流程

```
三月轮询 (每 30s)
  → 检测 next_run_at <= now 的 enabled 任务
  → 通过地脉发布 march.ring 事件
  → 派蒙订阅 march.ring:
      - 有 prompt → 创建临时会话，跑 model.chat，投递结果
      - 无 prompt → 直接投递 message
  → 三月更新 last_run_at，计算 next_run_at
```

### 失败处理

- 指数退避：`min(60 × 2^(failures-1), 3600)` 秒
- 连续 3 次失败自动 disable
- 恢复：用户通过 `/tasks` 或 ScheduleTool 手动 resume

### 用户接口

- **ScheduleTool** — LLM 通过 tool calling 管理定时任务 (create/list/pause/resume/delete)
- **`/tasks`** — 列出所有定时任务

## 代码位置

- `paimon/foundation/march/` — MarchService
- `paimon/foundation/irminsul/schedule.py` — ScheduleRepo + ScheduledTask
- `paimon/tools/builtin/schedule.py` — ScheduleTool
