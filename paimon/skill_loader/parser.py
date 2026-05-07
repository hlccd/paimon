"""SKILL.md 解析器 — Agent Skills 标准格式"""
from __future__ import annotations

import re
from pathlib import Path

import yaml


def parse_skill_metadata(skill_md: Path, dir_name: str) -> "SkillInfo":
    from .registry import SkillInfo

    content = skill_md.read_text(encoding="utf-8")
    frontmatter, body = _extract_frontmatter(content)

    if not frontmatter:
        raise ValueError("缺少 YAML frontmatter")

    data = yaml.safe_load(frontmatter)
    if not isinstance(data, dict):
        raise ValueError("frontmatter 必须是 YAML 映射")

    name = data.get("name")
    description = data.get("description")

    if not name:
        raise ValueError("缺少必需字段: name")
    if not description:
        raise ValueError("缺少必需字段: description")

    if not _validate_skill_name(name):
        raise ValueError(f"名称 '{name}' 不合法")

    if name != dir_name:
        raise ValueError(f"名称 '{name}' 与目录名 '{dir_name}' 不匹配")

    allowed_tools = data.get("allowed-tools")
    allowed_tools_list = None
    if allowed_tools:
        if isinstance(allowed_tools, str):
            # 同时支持空格分隔 ("Bash Read Write") 和逗号分隔 ("Bash, Read, Write")
            # 以及混合使用；空 token 过滤掉
            allowed_tools_list = [
                t.strip() for t in re.split(r"[,\s]+", allowed_tools)
                if t.strip()
            ]
        elif isinstance(allowed_tools, list):
            allowed_tools_list = [str(t).strip() for t in allowed_tools if str(t).strip()]

    triggers = data.get("triggers", "")
    if isinstance(triggers, list):
        triggers = ", ".join(triggers)

    # user-invocable: 缺省视为 True（老 SKILL.md 没标的默认可调）
    # 显式 false 用于 orchestrator-only skill（code-implementation/requirement-spec/architecture-design 等）
    raw_invocable = data.get("user-invocable", True)
    if isinstance(raw_invocable, str):
        user_invocable = raw_invocable.strip().lower() in ("true", "yes", "1")
    else:
        user_invocable = bool(raw_invocable)

    return SkillInfo(
        name=name,
        description=description,
        triggers=str(triggers),
        allowed_tools=allowed_tools_list,
        skill_md_path=skill_md,
        body=body.strip(),
        user_invocable=user_invocable,
    )


def _extract_frontmatter(content: str) -> tuple[str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if match:
        return match.group(1), match.group(2)
    return "", content


def _validate_skill_name(name: str) -> bool:
    if not name or len(name) > 64:
        return False
    if not re.match(r"^[a-z0-9-]+$", name):
        return False
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return False
    return True
