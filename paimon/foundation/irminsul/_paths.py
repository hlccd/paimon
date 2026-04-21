"""世界树内部路径安全工具。

所有涉及文件存储的 API（knowledge / memory body）必须通过 resolve_safe
校验拼接路径，确保不越出世界树根目录。

消除审计 SEC-003（P1）：知识库路径遍历 + 模板 RCE 链。
"""
from __future__ import annotations

from pathlib import Path


def resolve_safe(root: Path, *parts: str) -> Path:
    """把 parts 逐级拼到 root 下并做 resolve()，确保结果仍在 root 树内。

    安全规则：
    - 拒绝绝对路径参数（parts 中任一 is_absolute() → ValueError）
    - 拒绝 `..` 穿越（resolve 后验证 relative_to(root.resolve()) 成功）
    - 符号链接指向 root 外也拒绝（resolve 会跟随链接后再验证）
    """
    if not parts:
        raise ValueError("至少传一个路径片段")
    for p in parts:
        if not p:
            raise ValueError("路径片段不能为空字符串")
        if Path(p).is_absolute():
            raise ValueError(f"不允许绝对路径片段：{p}")

    root_r = root.resolve()
    target = (root / Path(*parts)).resolve()
    try:
        target.relative_to(root_r)
    except ValueError:
        raise ValueError(f"路径越界：{target} 不在 {root_r} 下")
    return target
