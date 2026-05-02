"""水神·芙宁娜 — 评审 archon 子包。

职责（docs/aimon.md §2.3.4 水神）：
- 严格审查方案 / 代码 / 文档 / 架构（_ReviewMixin）
- 输出结构化 verdict（pass / revise / redo + issues 列表）
- 大产物走 check skill；轻量产物走简化 LLM review

子模块：
- _review.py  —— review_spec/design/code + _lightweight_review + check skill 调用
- service.py  —— FurinaArchon 主类 + execute（路由到 review_*）
"""
from __future__ import annotations

from .service import FurinaArchon

__all__ = ["FurinaArchon"]
