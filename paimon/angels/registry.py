"""Skill 注册表 — 自动扫描和加载 skills"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from .parser import parse_skill_metadata

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul


@dataclass
class SkillInfo:
    name: str
    description: str
    triggers: str = ""
    allowed_tools: list[str] | None = None
    skill_md_path: Path | None = None
    body: str = ""
    # 冰神装载时自动派生（基于 allowed_tools 与工具敏感清单）
    sensitivity: str = "normal"                     # 'normal' | 'sensitive'
    sensitive_tools: list[str] = field(default_factory=list)


class SkillRegistry:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills: dict[str, SkillInfo] = {}

    def scan_and_load(self) -> None:
        if not self.skills_dir.exists():
            logger.warning("[天使·注册] skills 目录不存在: {}", self.skills_dir)
            return

        from paimon.core.authz.sensitive_tools import derive_sensitivity

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith((".", "__")):
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                info = parse_skill_metadata(skill_md, skill_dir.name)
                # 冰神装载时自动派生敏感度（docs/permissions.md §敏感度分级）
                info.sensitivity, info.sensitive_tools = derive_sensitivity(
                    info.allowed_tools or []
                )
                self.skills[info.name] = info
                logger.debug(
                    "[冰神·装载] {}: {} (sensitivity={}, hits={})",
                    info.name, info.description[:60],
                    info.sensitivity, info.sensitive_tools,
                )
            except Exception as e:
                logger.warning("[冰神·装载] 加载 {} 失败: {}", skill_dir.name, e)

        sensitive_count = sum(1 for s in self.skills.values() if s.sensitivity == "sensitive")
        logger.info(
            "[冰神·装载] 已加载 {} 个 Skill (敏感 {} / 普通 {})",
            len(self.skills), sensitive_count, len(self.skills) - sensitive_count,
        )

    def get(self, name: str) -> SkillInfo | None:
        return self.skills.get(name)

    def list_all(self) -> list[SkillInfo]:
        return sorted(self.skills.values(), key=lambda s: s.name)

    def exists(self, name: str) -> bool:
        return name in self.skills

    def reload(self) -> None:
        self.skills.clear()
        self.scan_and_load()

    async def reload_one(
        self,
        skill_dir_name: str,
        *,
        irminsul: "Irminsul",
        model,
    ) -> tuple[bool, str]:
        """热重载单个 skill（create / modify 事件）。

        - 解析 SKILL.md → 构造 SkillDecl → 送死执审查
        - 审查通过 → 更新内存 + 世界树 UPSERT + 发 leyline skill.loaded
        - 审查拒绝 → audit + 保留旧版本（如果 modify）或丢弃（如果 create），返回 False
        - parse 失败 → 日志 + 返回 False
        """
        from paimon.core.authz.sensitive_tools import derive_sensitivity
        from paimon.foundation.irminsul.skills import SkillDecl
        from paimon.shades import jonova

        skill_md = self.skills_dir / skill_dir_name / "SKILL.md"
        if not skill_md.exists():
            logger.warning("[冰神·热重载] SKILL.md 不存在: {}", skill_md)
            return False, "SKILL.md 不存在"

        try:
            info = parse_skill_metadata(skill_md, skill_dir_name)
            info.sensitivity, info.sensitive_tools = derive_sensitivity(
                info.allowed_tools or []
            )
        except Exception as e:
            logger.warning("[冰神·热重载] 解析 {} 失败: {}", skill_dir_name, e)
            return False, f"parse 失败: {e}"

        decl = SkillDecl(
            name=info.name,
            source="builtin",
            sensitivity=info.sensitivity,
            description=info.description,
            triggers=info.triggers,
            allowed_tools=list(info.allowed_tools or []),
            sensitive_tools=list(info.sensitive_tools or []),
        )

        # 热重载必过死执审查（docs/aimon.md §2.5 + 用户确认）
        passed, reason = await jonova.review_skill_declaration(decl, model)

        if not passed:
            # 拒绝：写 audit，保留旧版本（如果存在）
            try:
                await irminsul.audit_append(
                    event_type="skill_rejected",
                    payload={
                        "name": decl.name,
                        "reason": reason,
                        "source": decl.source,
                        "allowed_tools": decl.allowed_tools,
                    },
                    actor="死执",
                )
            except Exception as e:
                logger.warning("[冰神·热重载] audit 写入失败: {}", e)
            logger.warning("[冰神·热重载] {} 被死执拒绝: {}", info.name, reason)
            return False, reason

        # 过审：写世界树 + 更新内存
        try:
            await irminsul.skill_declare(decl, actor="冰神")
        except Exception as e:
            logger.error("[冰神·热重载] 写入世界树失败 {}: {}", info.name, e)
            return False, f"落盘失败: {e}"

        self.skills[info.name] = info
        logger.info(
            "[冰神·热重载] {} 已加载 (sensitivity={}, tools={})",
            info.name, info.sensitivity, info.allowed_tools,
        )

        # 通知派蒙失效 authz 缓存
        try:
            from paimon.state import state as _state
            if _state.leyline:
                await _state.leyline.publish("skill.loaded", {"name": info.name}, source="冰神")
        except Exception as e:
            logger.debug("[冰神·热重载] leyline 发布失败: {}", e)

        return True, "ok"

    async def remove_one(
        self,
        skill_dir_name: str,
        *,
        irminsul: "Irminsul",
    ) -> bool:
        """热卸载单个 skill（delete 事件）：内存移除 + DB 标孤儿。"""
        # skill 名通常 = 目录名（parse 时的 fallback）
        name = skill_dir_name
        if name not in self.skills:
            # 也尝试通过 skill_md_path 反查
            for n, info in list(self.skills.items()):
                if info.skill_md_path and info.skill_md_path.parent.name == skill_dir_name:
                    name = n
                    break

        removed = self.skills.pop(name, None)
        if removed is None:
            logger.debug("[冰神·热卸载] 内存 registry 无 {}，跳过", skill_dir_name)

        try:
            await irminsul.skill_mark_orphaned(name, True, actor="冰神")
        except Exception as e:
            logger.warning("[冰神·热卸载] 标孤儿失败 {}: {}", name, e)
            return False

        logger.info("[冰神·热卸载] {} 已移除（内存+DB 标 orphan）", name)

        try:
            from paimon.state import state as _state
            if _state.leyline:
                await _state.leyline.publish("skill.revoked", {"name": name}, source="冰神")
        except Exception as e:
            logger.debug("[冰神·热卸载] leyline 发布失败: {}", e)

        return True

    async def sync_to_irminsul(self, irminsul: "Irminsul") -> None:
        """把内存 registry 同步到世界树 skill_declarations 表（冰神职责）。

        - UPSERT 内存里每个 SkillInfo 为 source="builtin" 的 SkillDecl
        - 扫孤儿：世界树里有 source="builtin" 但内存没有的 → mark_orphaned=True
        - 单条失败降级为 warning，不阻断启动
        """
        from paimon.foundation.irminsul.skills import SkillDecl

        mem_names = set(self.skills.keys())
        declared_count = 0
        orphaned_count = 0

        for info in self.skills.values():
            try:
                decl = SkillDecl(
                    name=info.name,
                    source="builtin",
                    sensitivity=info.sensitivity,
                    description=info.description,
                    triggers=info.triggers,
                    allowed_tools=list(info.allowed_tools or []),
                    sensitive_tools=list(info.sensitive_tools or []),
                )
                await irminsul.skill_declare(decl, actor="冰神")
                declared_count += 1
            except Exception as e:
                logger.warning("[冰神·落盘] 写入 {} 失败: {}", info.name, e)

        try:
            existing = await irminsul.skill_list(source="builtin", include_orphaned=True)
            for d in existing:
                if d.name not in mem_names and not d.orphaned:
                    await irminsul.skill_mark_orphaned(d.name, True, actor="冰神")
                    orphaned_count += 1
        except Exception as e:
            logger.warning("[冰神·落盘] 孤儿扫描失败: {}", e)

        logger.info(
            "[冰神·落盘] UPSERT {} 条声明，标记孤儿 {} 条",
            declared_count, orphaned_count,
        )
