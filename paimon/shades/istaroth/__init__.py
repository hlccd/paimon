"""时执 · Istaroth — 生命周期管理子包

docs/shades/istaroth.md 职责：
  - 运行中：活跃会话上下文压缩（_compress.compress）
  - 结束后 · 归档：任务归档 + 审计（_archive.archive）
  - 结束后 · 经验提取：跨会话记忆抽取（_experience.extract_experience）

参考 claude-code-deep-dive 的压缩设计：
  1. 阈值考虑 max_output_tokens + safety_buffer（调用方 chat.py 负责计算）
  2. 保留段 tool_use / tool_result 对齐（回溯补齐悬挂 pair）
  3. Prompt 4 章节 + NO_TOOLS 约束
  4. 连续失败 3 次 → session.auto_compact_disabled 熔断

子模块：
- _archive.py    —— archive() + _maybe_write_task_summary()
- _compress.py   —— compress() + _is_tool_related + _adjust_keep_start_for_tool_pairs + _build_memory_block + _strip_code_fence
- _experience.py —— extract_experience()（L1 跨会话记忆提取）
"""
from __future__ import annotations

# 兼容老 `compress` 内部调 `extract_experience`：先 import _compress 再注入
from . import _compress, _experience  # noqa: F401

# compress() 体内调 extract_experience，但 _compress.py 不直接 import _experience
# （_experience.py 反向 import _compress._strip_code_fence，会循环）。
# 解决：把 extract_experience 注入 _compress 的模块名空间作为局部变量。
_compress.extract_experience = _experience.extract_experience

from ._archive import archive
from ._compress import MAX_CONSECUTIVE_COMPACT_FAILURES, compress
from ._experience import extract_experience

__all__ = [
    "MAX_CONSECUTIVE_COMPACT_FAILURES",
    "archive",
    "compress",
    "extract_experience",
]
