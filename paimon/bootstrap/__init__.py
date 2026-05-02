"""派蒙启动子包 — re-export create_app 保持 from paimon.bootstrap import create_app 不变。"""
from __future__ import annotations

from .main import create_app

__all__ = ["create_app"]
