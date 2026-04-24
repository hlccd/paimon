"""数据获取层 — 共享工具（缓存 + 重试）

AkShare 已移除，数据源统一使用 BaoStock（provider_baostock.py）。
本模块保留被 provider_baostock.py 导入的共享常量和工具函数。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

# 缓存有效期（小时）
CACHE_TTL = {
    'dividend': 30 * 24,   # 分红数据 30 天
    'financial': 30 * 24,  # 财务数据 30 天
    'price': 7 * 24,       # 行情数据 7 天
}

MAX_RETRIES = 6
RETRY_BASE_DELAY = 3


def _retry(fn, max_retries=MAX_RETRIES, base_delay=RETRY_BASE_DELAY):
    """带重试的同步调用"""
    import requests.exceptions
    from http.client import RemoteDisconnected
    from urllib3.exceptions import ProtocolError

    for attempt in range(max_retries):
        try:
            return fn()
        except (
            ConnectionError, TimeoutError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            RemoteDisconnected, ProtocolError,
        ):
            if attempt < max_retries - 1:
                wait = base_delay * (attempt + 1)
                logger.debug(f"[provider] 网络错误, {wait}s 后重试 ({attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("unreachable")


def _load_cache(path: Path, ttl_hours: int):
    """从缓存文件读取"""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(data["timestamp"])
        if datetime.now() - ts > timedelta(hours=ttl_hours):
            return None
        return data["data"]
    except Exception:
        return None


def _load_cache_any_age(path: Path):
    """读取缓存文件，忽略 TTL（rescore 用）"""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["data"]
    except Exception:
        return None


def _save_cache(path: Path, data):
    """写入缓存文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
