# 冰神·冰之女皇

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神
> 相关：[天使体系 / Skill vs Plugin](../angels/angels.md#skill-vs-plugin-对比)

- **主题**：反抗·联合
- **核心职能**：**Skill 生态概念归属**
  - **Web 面板语义负责人**：`/plugins` 面板
- **Web 面板**：✅ `/plugins` 面板（代码层 webui/api/plugins.py 直读 skill_loader，不经冰神实例）

## ⚠️ 当前状态（2026-05 解耦后）

archon 本体 `execute()` 跟四影解耦后**内部业务已移除**，但**保留概念归属**：

- 移除：`execute()` 内部 `skill_manage` tool-loop / 通用 exec 推理
- 已搬到：`paimon/shades/worker/`（stage=`exec` / `chat`）
- **保留概念归属**：冰神语义负责 `/plugins` 面板（skill 生态管理 / AI 自举），代码层 webui 直读 `skill_loader` **不经过本实例**——但**语义上**归冰神

**待用户后续安排**：是否给冰神实例挂新职能（如 webui 改成走冰神实例做面板代理）。

## Skill 审查

启动扫入的内置 skill 跳过死执审查（代码审查已把关）；运行时新增（plugin / AI 生成）必须经死执审查。
