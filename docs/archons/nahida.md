# 草神·纳西妲

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神
> 相关：[世界树](../foundation/irminsul.md) · [权限与契约](../permissions.md)

- **主题**：智慧·文书
- **核心职能**：
  - **概念归属**：知识 / 偏好 / 文书归档
  - **Web 面板语义负责人**：`/knowledge` 面板（草神·智识，3 tab）
- **Web 面板**：✅ `/knowledge` 面板（代码层 webui/api/knowledge_kb,knowledge_archives,authz 直读 irminsul，不经草神实例）

## ⚠️ 当前状态（2026-05 解耦后）

archon 本体 `execute()` 跟四影解耦后**内部业务已移除**，但**保留概念归属**：

- 移除：`execute()` 内部 `[STAGE:spec]` 路由 + `write_spec` + 通用 tool-loop + `_extract_issues_*` helpers
- 已搬到生执 `paimon/shades/naberius/produce.py`（stage=`spec`）+ `_simple.py`（stage=`chat`），公共 helper 在 `paimon/shades/_helpers/`
- **保留概念归属**：草神语义负责 `/knowledge` 面板（知识 / 偏好 / 文书归档），代码层 webui 直读 irminsul **不经过本实例**——但**语义上**归草神

**待用户后续安排**：是否给草神实例挂新职能（如 webui 改成走草神实例做面板代理）。

## 与世界树的边界

- 世界树 = **底层存储**
- 草神 = 概念上的"知识 / 偏好 / 文书归档"语义负责人；当前实现 webui 面板代码直读 irminsul（绕过实例）
