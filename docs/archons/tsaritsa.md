# 冰神·冰之女皇

> 隶属：[神圣规划](../aimon.md) / 第二轨 · 七神
> 相关：[天使体系 / Skill vs Plugin](../angels/angels.md#skill-vs-plugin-对比) · [自进化体系](../evolution.md)

- **主题**：反抗·联合
- **核心职能**：
  - **skill 域唯一写入者**（业务接口层面）
  - **Web 面板语义负责人**：`/plugins` 面板（skill 生态管理 + 授权撤销 + 自进化提案审批）
  - **自进化提案落盘者**：apply approved 提案 → 派蒙 safety 审 → 写 SKILL.md → 注册
- **Web 面板**：✅ `/plugins` 面板（代码层 webui/api/plugins.py 直读 skill_loader + skill_proposals 域，不经冰神实例）

## 当前状态：archon 本体 namespace 壳

archon 本体 `execute()` 不参与执行；冰神语义负责人身份完全通过：
- `/plugins` 面板（webui 直读）
- skill 域唯一写入者契约
- `paimon/skill_loader/apply_proposal.py`（自进化提案落盘）

体现。

## Skill 审查

启动扫入的内置 skill 跳过审查（代码已把关）；运行时新增（plugin / AI 自进化生成）必须经派蒙 `core/safety/skill_review`。

## 自进化提案的三道闸（冰神是落盘执行者）

1. **死执 review_proposal**（质量审）：`paimon/shades/jonova/review_proposal.py`
2. **用户面板审**：`/plugins#proposals` tab approve / reject
3. **派蒙 skill_review**（safety 审）：`paimon/core/safety/skill_review.py`

三道闸全过 → 冰神 apply（`apply_proposal.py`）写 `.claude/skills/<name>/SKILL.md` + 注册 skill_declarations。详见 [自进化](../evolution.md) §L3。
