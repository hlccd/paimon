"""日期窗口：默认严格 30 天 + 中文日期解析。"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Optional


def date_window(days: int = 30) -> tuple[str, str]:
    """返回 (from_date, to_date)，YYYY-MM-DD 字符串。"""
    today = _dt.date.today()
    return (today - _dt.timedelta(days=days)).isoformat(), today.isoformat()


def in_window(published_at: str, range_from: str, range_to: str) -> bool:
    """判定 published_at 是否在 [range_from, range_to] 内。空字符串视为不在窗内。"""
    if not published_at:
        return False
    try:
        d = published_at[:10]
        return range_from <= d <= range_to
    except (TypeError, ValueError):
        return False


def parse_unix(ts: int | float) -> str:
    """Unix 时间戳 → YYYY-MM-DD (本地)。"""
    try:
        return _dt.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""


_CN_DATE = re.compile(r"(\d{4})[-/年.]\s*(\d{1,2})[-/月.]\s*(\d{1,2})日?")


def parse_chinese_date(text: str) -> Optional[str]:
    """从中文文本里粗暴抽 YYYY-MM-DD（'2026年5月6日'/'2026-05-06'/'2026/5/6' 都吃）。"""
    if not text:
        return None
    m = _CN_DATE.search(text)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return _dt.date(y, mo, d).isoformat()
    except ValueError:
        return None
