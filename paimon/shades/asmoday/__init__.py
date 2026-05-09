"""空执 · 阿斯莫代 — 派

skill 域的实际写入与管理（自进化提案落盘 / 装载 / 注册）。

职能：
- 提案落盘（apply_proposal）：用户在面板同意后写 skills/<name>/SKILL.md，注册声明域
- 启动装载与注册（registry）：扫 skills/ 目录，把内存 SkillRegistry 同步到世界树
- 元数据解析（parser）：YAML frontmatter + Markdown body

热重载（监听文件变化触发 reload）已交给时执 (paimon/shades/istaroth/skill_watcher.py)。
"""
from .registry import SkillInfo, SkillRegistry

__all__ = ["SkillInfo", "SkillRegistry"]
