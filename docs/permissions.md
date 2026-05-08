# 权限与契约体系（跨模块协作机制）

> 隶属：[神圣规划](aimon.md)
> 相关：[派蒙](paimon/paimon.md) · [世界树](foundation/irminsul.md) · [冰神](archons/tsaritsa.md)

跨派蒙 / 四影 / 冰神 / 世界树的统一权限机制。安全审职能在派蒙 `core/safety/`；skill 生态业务接口归冰神。

## 核心角色分工

| 角色 | 职责 |
|---|---|
| **世界树**（authz / skills 域） | 唯一存储层：用户授权记录 + skill 声明（只存不推）|
| **冰神** | skill 生态业务接口 — 发现 / 注册 / AI 自举的语义负责人；唯一写世界树 skill 域；`/plugins` 面板归属 |
| **派蒙 `core/safety/`** | 全程安全闸：task_review（入口审）+ scan_plan（DAG 敏感扫描）+ skill_review（skill 装载审）+ sensitive_filter（敏感串过滤）|
| **派蒙 AuthzCache** | 本地缓存（启动读世界树；运行时通知刷新）|
| **skill_loader（冰神语义壳）** | skill 物理装载实现（扫盘 + 注册）；语义归冰神 |
| **冰神 `/plugins` 面板** | 授权查看 / 撤销 UI 入口（webui 直读 + 写世界树）|

## 敏感度分级

| 等级 | 定义 | 举例 |
|---|---|---|
| **普通** | 纯读 / 本地无副作用 / 低风险 | `web_search` / wiki 查询 / 知识库读 |
| **敏感** | 系统 / 外部 / 凭据 / 可导致副作用的写 | `exec` shell / 账号登录 / 文件系统写 / 未授权抓取 / 定时任务注册 |

**派生规则**（冰神装载时自动，物理实现在 skill_loader）：`sensitivity` 不由 manifest 手填，而是按 `allowed_tools` 中是否命中敏感工具清单自动派生。`Bash(git:*)` 类受限声明归一化到 `Bash` 后再判断。清单：`paimon/core/authz/sensitive_tools.py`。

## 启动流程

```
1. 世界树启动
2. 冰神（skill_loader 物理实现）启动：
   a. 扫 skills/ 目录 → 派生 sensitivity → 同步声明到世界树（冰神唯一写入者）
   b. 从世界树加载历史 plugin 声明
3. 派蒙启动：
   a. 从世界树一次性读 skill 声明 + 用户授权记录 → AuthzCache
   b. 自动放行：9 个四影 stage + builtin skill（subject_type="stage"）
```

## 运行时决策

`/task` 复杂任务路径：
```
生执 plan 出 DAG（节点带 sensitive_ops）
  ↓
派蒙·core/safety/scan_plan(plan, AuthzCache)
  ├ permanent_deny → 剔除
  ├ permanent_allow → 放行
  └ 无记录 → 派蒙批量询问用户（一次性确认）
  ↓
空执 dispatch 各影
```

`/skill` 单步路径：派蒙运行前查 AuthzCache → 命中即放行 / 未记录则单项询问。

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
| 运行时通知 | 冰神（skill_loader）装载新 plugin / AI 生成 skill | 冰神提交 → 派蒙 skill_review → 通过 → 冰神写世界树 + leyline 通知派蒙刷新缓存 |

预装 skill（启动扫入）视为预审通过，不走运行时审查。

## 用户体验

- **不重复打断**：单 task 内一次批量问完
- **透明提示**：放行时告知用什么能力；命中永久记录时说明"按之前授权放行"
- **可撤回**：冰神 `/plugins` 面板查 + 撤销永久记录
