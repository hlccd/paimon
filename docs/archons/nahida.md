# 草神·纳西妲

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神
> 相关：[世界树](../foundation/irminsul.md) · [权限与契约](../permissions.md)

- **主题**：智慧·文书
- **核心职能**：
  - **memory 域唯一写入者**（业务接口层面）
  - **概念归属**：知识 / 偏好（个人画像）
  - **Web 面板语义负责人**：`/knowledge` 面板（草神·智识，2 tab：📖 记忆 / 📚 知识库）
- **Web 面板**：✅ `/knowledge` 面板（代码层 webui/api/{knowledge_kb,knowledge,authz}.py 直读 irminsul，不经草神实例）

## 当前状态：archon 本体 namespace 壳

archon 本体 `execute()` 不参与执行；草神语义负责人身份完全通过 `/knowledge` 面板 + memory 域唯一写入者契约体现。

待用户后续安排：是否给草神实例挂新职能（如 webui 改成走草神实例做面板代理）。

## 与世界树的边界

- 世界树 = **底层存储**
- 草神 = 概念上的"知识 / 偏好 / 个人记忆"语义负责人；当前实现 webui 面板代码直读 irminsul（绕过实例）
