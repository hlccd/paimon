"""Irminsul 主类拆分子包：4 mixin + 1 service；callsite 仍 from ..irminsul import Irminsul。"""
from __future__ import annotations

from .service import Irminsul

__all__ = ["Irminsul"]
