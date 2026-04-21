"""Skill 注册表 — 自动扫描和加载 skills"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from .parser import parse_skill_metadata


@dataclass
class SkillInfo:
    name: str
    description: str
    triggers: str = ""
    allowed_tools: list[str] | None = None
    skill_md_path: Path | None = None
    body: str = ""


class SkillRegistry:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills: dict[str, SkillInfo] = {}

    def scan_and_load(self) -> None:
        if not self.skills_dir.exists():
            logger.warning("[天使·注册] skills 目录不存在: {}", self.skills_dir)
            return

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith((".", "__")):
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                info = parse_skill_metadata(skill_md, skill_dir.name)
                self.skills[info.name] = info
                logger.debug("[天使·注册] {}: {}", info.name, info.description[:60])
            except Exception as e:
                logger.warning("[天使·注册] 加载 {} 失败: {}", skill_dir.name, e)

        logger.info("[天使·注册] 已加载 {} 个 Skill", len(self.skills))

    def get(self, name: str) -> SkillInfo | None:
        return self.skills.get(name)

    def list_all(self) -> list[SkillInfo]:
        return sorted(self.skills.values(), key=lambda s: s.name)

    def exists(self, name: str) -> bool:
        return name in self.skills

    def reload(self) -> None:
        self.skills.clear()
        self.scan_and_load()
