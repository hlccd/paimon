"""站点 cookies 管理：~/.paimon/cookies/{site}.json。

paimon 全项目共用（不限 topic-research）。playwright 写入 / 各 skill 读取。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

COOKIES_BASE = Path.home() / ".paimon" / "cookies"


def cookies_path(site: str) -> Path:
    """返回 site 的 cookies 文件路径。"""
    return COOKIES_BASE / f"{site}.json"


def cookies_exists(site: str) -> bool:
    return cookies_path(site).exists()


def load_storage_state(site: str) -> dict[str, Any]:
    """读 cookies 文件（playwright storage_state 格式）。无文件抛 FileNotFoundError。"""
    p = cookies_path(site)
    if not p.exists():
        raise FileNotFoundError(f"cookies 不存在：{p}")
    return json.loads(p.read_text(encoding="utf-8"))


def cookies_to_header(site: str) -> str | None:
    """读 cookies → 转成 HTTP `Cookie` header 字符串。无 cookie 返回 None。"""
    if not cookies_exists(site):
        return None
    state = load_storage_state(site)
    cookies = state.get("cookies") or []
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))


def cookies_age_days(site: str) -> float | None:
    """cookies 文件距今天数（落盘时间），无文件返回 None。"""
    p = cookies_path(site)
    if not p.exists():
        return None
    return (time.time() - p.stat().st_mtime) / 86400.0


def list_sites() -> list[str]:
    """列出所有已存的 cookies 站点（按文件名）。"""
    if not COOKIES_BASE.exists():
        return []
    return sorted(p.stem for p in COOKIES_BASE.glob("*.json"))
