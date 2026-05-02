"""世界树主门面入口 —— 实际类在 _irminsul/ 子包，本文件保留作 from-import 兼容层。"""
from __future__ import annotations

from ._irminsul import Irminsul

__all__ = ["Irminsul"]
