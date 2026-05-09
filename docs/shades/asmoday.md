# 空执·阿斯莫代

> 隶属：[神圣规划](../aimon.md) / 四影

**定位**：skill 域写入与管理。

## 职能

- **提案落盘**：用户在 `/plugins` 面板同意 skill 草案后，过派蒙安全审 → 写 `skills/<name>/SKILL.md` → 注册到 skill 声明域 → 立即热加载（运行时即可用）
- **启动装载**：服务启动时扫 `skills/` 目录，把所有内置 / 外部 skill 装入内存 `SkillRegistry` 并同步到世界树声明
- **元数据派生**：装载时按 skill 的 `allowed_tools` 命中清单自动派生 sensitivity（normal / sensitive），manifest 不需要手填

## 边界

- skill **写入**归空执；skill **热重载**（监听文件变化触发 reload）归时执
- 安全审（防恶意 prompt / 工具越权）归派蒙安全模块，不归空执
- skill 域是空执唯一写入者；其他模块只从世界树读
- `/plugins` 面板的代码层 API 直读世界树 + 内存 `SkillRegistry`，不经 archon 实例
