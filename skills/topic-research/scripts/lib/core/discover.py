"""发现 helper：调 paimon/skills/web-search 子进程，按 site: 限定拿候选 URL。

仅用于无公开 API 的平台（小红书 / 知乎部分场景 / 贴吧）。
有官方搜索 API 的平台（B 站 / GitHub 等）走自己的 collector，不调本 helper。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import log

_WEB_SEARCH = Path(__file__).resolve().parents[3] / "web-search" / "search.py"


def discover(
    topic: str,
    site: str,
    *,
    limit: int = 20,
    engine: str = "",
    timeout: float = 30.0,
) -> list[dict]:
    """对单平台做候选发现。

    Args:
        topic:   调研主题
        site:    'bilibili.com' / 'xiaohongshu.com' / ...
        limit:   返回数上限
        engine:  '' (双引擎) / 'baidu' / 'bing'
        timeout: 子进程超时（秒）

    返回 list[{title, url, description, engine}]；失败返回 []。
    """
    if not _WEB_SEARCH.exists():
        log.warn(f"web-search skill 缺失: {_WEB_SEARCH}")
        return []

    query = f"{topic} site:{site}"
    cmd = ["python3", str(_WEB_SEARCH), query, "--limit", str(limit)]
    if engine:
        cmd += ["--engine", engine]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        log.warn(f"discover {site}: web-search 超时（>{timeout}s）")
        return []
    except OSError as e:
        log.warn(f"discover {site}: 调 web-search 失败 {e}")
        return []

    if proc.returncode != 0:
        log.warn(f"discover {site}: rc={proc.returncode} stderr={proc.stderr[:200]}")
        return []

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        log.warn(f"discover {site}: 输出非 JSON: {proc.stdout[:200]}")
        return []

    if not isinstance(data, list):
        return []

    # 百度跳转链 url 含 baidu.com/link，但 title/desc 仍可用——保留
    log.source_log(site, f"discover ({engine or 'auto'}) → {len(data)} 条候选")
    return data
