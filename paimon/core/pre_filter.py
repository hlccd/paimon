"""派蒙入口轻量安全过滤

按 docs/paimon/paimon.md §轻量安全校验：
  - 关键词/正则级快速识别明显恶意输入
  - 深度语义审查由死执承担（本模块只管"明显的"）

两档处置：
  - block: 直接拒绝（shell 破坏性指令这种无歧义恶意）
  - warn: 放行但记 audit（prompt injection 这种高误伤风险的）

未来扩展：支持从世界树 memory 域读取 `mem_type=feedback` + `tag=filter_pattern`
的用户自定义规则。本轮只内置最小集（6 shell + 4 prompt），让模块成为纯函数。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

Verdict = Literal["pass", "warn", "block"]


@dataclass(frozen=True)
class FilterHit:
    verdict: Verdict   # "block" / "warn" / "pass"
    category: str      # "shell_danger" / "prompt_injection" / ""
    reason: str        # 简短描述
    pattern: str       # 命中的 pattern 源串（debug 用）


# 档一：明显破坏性 shell 命令（verdict=block）
# 宁少勿多，只拦"根路径 / 物理设备 / fork bomb" 这种无歧义恶意。
# 普通操作（rm -rf old_backup/、> /tmp/xxx）不命中。
#
# **拦"执行"不拦"讨论"**：命令尾部要求 shell 终结符（EOF / ; / & / | / 换行），
# 避免误伤 "rm -rf / 是什么意思" 这类讨论场景。
# shell 终结符集：($|[;&|]) 覆盖 EOF / ; / && / || / 管道。
_END = r"\s*($|[;&|])"

_BLOCK_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\brm\s+-[rfRF]+\s+/" + _END), "rm -rf /"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"), "fork bomb"),
    (re.compile(r"\bmkfs\.[a-z0-9]+\s+/dev/[a-z0-9]+" + _END), "mkfs 格式化块设备"),
    (re.compile(r"\bdd\s+[^|]*?\bof=/dev/(sd[a-z]|nvme|hd|vd)[0-9a-z]*" + _END), "dd 写入物理块设备"),
    # 注意：>\s*/dev/...  `>` 不是 word char，`\b>` 会匹配失败
    (re.compile(r">\s*/dev/(sd[a-z]|nvme|hd|vd)[0-9a-z]*" + _END), "重定向到块设备"),
    (re.compile(r"\b(chmod|chown)\s+-[rR]+\s+[^\s]+\s+/" + _END), "递归修改 / 权限"),
    # ROB-001 加固：远程脚本管道直跑（社工攻击载体）+ chmod 777 顶层
    (re.compile(r"\bcurl\s+[^|]+\|\s*(sh|bash|zsh|ash)\b"), "curl|sh 远程脚本直跑"),
    (re.compile(r"\bwget\s+(-[a-zA-Z]+\s+)*[^|]+\|\s*(sh|bash|zsh)\b"), "wget|sh 远程脚本直跑"),
    (re.compile(r"\bchmod\s+777\s+/" + _END), "chmod 777 /"),
    # Windows: format C: / del /q /s C:\
    (re.compile(r"\bformat\s+[A-Z]:" + _END, re.IGNORECASE), "format 系统盘"),
    (re.compile(r"\bdel\s+(/[a-zA-Z]\s+){1,3}[A-Z]:\\\s*\*?", re.IGNORECASE), "del 系统盘"),
]


# 档二：prompt injection 模板（verdict=warn）
# 这档只记 audit 不拦截，因为误伤率高。
# 例如用户正常说"我想忽略以前的错误重新开始"—— 不构成 prompt injection。
_WARN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(
        r"(?i)(ignore|forget|disregard)\s+(all\s+|the\s+)?"
        r"(previous|prior|above|earlier|system)\s+"
        r"(instructions?|prompts?|rules?|commands?|messages?)"
    ), "ignore previous instructions"),
    (re.compile(
        r"(?i)you\s+are\s+now\s+"
        r"(dan|jailbroken|a\s+different\s+(ai|assistant|model)|an?\s+unrestricted)"
    ), "role reset / jailbreak"),
    (re.compile(
        r"忽略(之前|前面|以上|上面)(所有)?(的)?(指令|规则|提示|命令|系统)"
    ), "中文 ignore previous"),
    (re.compile(
        r"你现在是[^。,，]{0,30}(DAN|越狱|不受限|无限制|没有任何限制)"
    ), "中文角色越狱"),
]


def pre_filter(text: str) -> FilterHit:
    """入口轻量过滤。

    返回：
      - `block`：调用方应立即拒绝，不进入后续流程
      - `warn`：调用方应记 audit，但仍正常处理
      - `pass`：无命中

    ROB-001：先做 NFKC 归一化再匹配。否则全角空格 / 同形 unicode（如全角 ｒｍ）
    可绕过 ASCII 正则。NFKC 把全角字母数字、兼容字符折叠回 ASCII 等价形态。
    """
    if not text:
        return FilterHit("pass", "", "", "")
    norm = unicodedata.normalize("NFKC", text)
    for pat, reason in _BLOCK_PATTERNS:
        if pat.search(norm):
            return FilterHit("block", "shell_danger", reason, pat.pattern)
    for pat, reason in _WARN_PATTERNS:
        if pat.search(norm):
            return FilterHit("warn", "prompt_injection", reason, pat.pattern)
    return FilterHit("pass", "", "", "")
