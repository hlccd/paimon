"""极薄日志：subprocess 模式下走 stderr，不污染 stdout JSON。"""
from __future__ import annotations

import sys


def info(msg: str) -> None:
    sys.stderr.write(f"[topic] {msg}\n")
    sys.stderr.flush()


def warn(msg: str) -> None:
    sys.stderr.write(f"[topic·warn] {msg}\n")
    sys.stderr.flush()


def source_log(source: str, msg: str) -> None:
    sys.stderr.write(f"[topic·{source}] {msg}\n")
    sys.stderr.flush()
