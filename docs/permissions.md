# 权限与契约体系（跨模块协作机制）

> 隶属：[神圣规划](aimon.md)
> 相关：[派蒙](paimon/paimon.md) · [世界树](foundation/irminsul.md) · [冰神](archons/tsaritsa.md)

跨派蒙 / 四影 / 世界树的统一权限机制。安全审职能在派蒙 `core/safety/`；skill 生态业务接口归空执。

## 核心角色分工

| 角色 | 职责 |
|---|---|
| **世界树**（authz / skills 域） | 唯一存储层：用户授权记录 + skill 声明（只存不推）|
| **空执** | skill 生态实现 — 启动装载 / 提案落盘 / 声明注册；唯一写世界树 skill 域；`/plugins` 面板归属 |
| **派蒙 `core/safety/`** | 全程安全闸：task_review（入口审）+ scan_plan（DAG 敏感扫描）+ skill_review（skill 装载审）+ sensitive_filter（敏感串过滤）|
| **派蒙 AuthzCache** | 本地缓存（启动读世界树；运行时通知刷新）|
| **空执（`paimon/shades/asmoday/`）** | skill 物理装载实现（扫盘 + 注册 + 提案落盘） |
| **空执 `/plugins` 面板** | 授权查看 / 撤销 UI 入口（webui 直读 + 写世界树）|

## 敏感度分级

| 等级 | 定义 | 举例 |
|---|---|---|
| **普通** | 纯读 / 本地无副作用 / 低风险 | `web_search` / wiki 查询 / 知识库读 |
| **敏感** | 系统 / 外部 / 凭据 / 可导致副作用的写 | `exec` shell / 账号登录 / 文件系统写 / 未授权抓取 / 定时任务注册 |

**派生规则**（空执装载时自动）：`sensitivity` 不由 manifest 手填，而是按 `allowed_tools` 中是否命中敏感工具清单自动派生。`Bash(git:*)` 类受限声明归一化到 `Bash` 后再判断。清单：`paimon/core/authz/sensitive_tools.py`。

## 启动流程

```
1. 世界树启动
2. 空执启动：
   a. 扫 skills/ 目录 → 派生 sensitivity → 同步声明到世界树（空执唯一写入者）
   b. 从世界树加载历史 plugin 声明
3. 派蒙启动：
   a. 从世界树一次性读 skill 声明 + 用户授权记录 → AuthzCache
   b. 自动放行：自进化 stage（propose_skill / review_proposal）+ builtin skill
```

## 运行时决策

`/skill` 单步路径：派蒙运行前查 AuthzCache → 命中即放行 / 未记录则单项询问。

`/evolve` 自进化触发路径：派蒙 task_review 入口审 → propose+review 链直跑（stage 启动时已 permanent_allow，无需运行时询问）。

## 用户答复识别（派蒙铁律）

| 用户说法 | 处理 | 入库 |
|---|---|---|
| 放行 / 同意 / OK | 本次放行 | ❌ |
| 拒绝 / 不要 | 本次拒绝 | ❌ |
| **永久放行** / 以后都允许 | 放行 + 写世界树 + 更新缓存 | ✅ |
| **永久禁止** / 以后都不要 | 拒绝 + 写世界树 + 更新缓存 | ✅ |

只有"永久 / 以后都..."类持久副词触发入库。

## 画像更新链路

派蒙感知画像变化只有两条路径，不订阅世界树变更：

| 路径 | 触发 | 链路 |
|---|---|---|
| 内部自更新 | 用户永久授权 | 派蒙识别 → 写世界树 → 自更新缓存（同模块）|
| 运行时通知 | 空执装载新 plugin / AI 生成 skill | 空执装载提交 → 派蒙安全审 → 通过 → 空执写世界树 + leyline 通知派蒙刷新缓存 |

预装 skill（启动扫入）视为预审通过，不走运行时审查。

## Skill 自进化提案的三道闸

跟「用户主动 `/skill` 装载」的运行时审查不同，**AI 自动提议的 skill** 需要经"质量 + 意愿 + 安全"三道独立闸，**任一闸阻断即不落地**：

| 闸 | 角色 | 输出 | 阻断条件 |
|---|---|---|---|
| **1. 质量闸** | 四影·死执 `review_proposal` stage | `review_verdict ∈ {pass, needs_revise, reject}` 落 skill_proposals 域 | `reject` → 自动联动 status=rejected；`needs_revise` → 用户面板 approve 按钮 disabled，必须先重产再审 |
| **2. 意愿闸** | 用户在 `/plugins` 面板"自进化提案"tab | status: pending → approved / rejected | AI 不能自审自批；status=approved 必须用户主动点同意 |
| **3. 安全闸** | 派蒙 `core/safety/skill_review`（apply 时跑）| 跟普通 skill 装载共用同一道审查 | tool 越权 / sensitive 命中 / manifest 不合规等 → 阻装，标记 applied 失败 |

**写盘归属**：三道闸全过后，空执才执行落盘（写 `skills/<name>/SKILL.md` + 注册声明，source='ai_gen'，origin=proposed_by_session）。skill_proposals.status=applied，作为 skill 起源审计**永不可删**。

**写入者分工（自进化域的特例）**：
- 四影·生执 → propose_skill stage 写新提案
- 四影·死执 → review_proposal stage 写 review_verdict
- 空执 → apply 时标 mark_applied + 写 skill_declarations
- 用户面板 → approve / reject / delete（rejected 限定）

详见 [自进化](evolution.md) §L3。

## 用户体验

- **不重复打断**：单 task 内一次批量问完
- **透明提示**：放行时告知用什么能力；命中永久记录时说明"按之前授权放行"
- **可撤回**：空执 `/plugins` 面板查 + 撤销永久记录
