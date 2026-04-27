"""跨渠道共用的智能拆分：按 markdown 友好边界拆分长消息。

QQ 单消息 ~2000 字限制，Web 长消息 UX 上也希望分气泡（避免一气泡塞 5k 字）。
统一接入点 `smart_chunk(text, max_len=1500)`：
  - 代码块（```...```）和表格（|...| 连续行）当作原子单元，不切内部
  - 段落（空行分隔）作为最小拆分粒度
  - 单原子块 > max_len 时硬切，第二段及后续头部加 "(接上)\\n" 前缀
  - 整段贪心拼装，每段 ≤ max_len（除非单块超限）
"""
from __future__ import annotations

import re

CONTINUATION_PREFIX = "(接上)\n"


def smart_chunk(text: str, max_len: int = 1500) -> list[str]:
    """按 markdown 友好边界拆分。空字符串/纯空白返回空列表。

    返回每段 ≤ max_len（除非单原子块超限，会被硬切并加前缀）。
    """
    if not text or not text.strip():
        return []
    if len(text) <= max_len:
        return [text]

    blocks = _parse_blocks(text)

    chunks: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > max_len:
            # 单块超限：先 flush，再硬切这个块
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split_with_continuation(block, max_len))
            continue

        if not current:
            current = block
            continue

        # 段落之间用 \n\n 重新拼接
        joined = current + "\n\n" + block
        if len(joined) <= max_len:
            current = joined
        else:
            chunks.append(current)
            current = block

    if current:
        chunks.append(current)
    return chunks


# 表格行：行首可能有空白，然后 | 开头
_TABLE_LINE_RE = re.compile(r"^\s*\|")
# 表格分隔行：|---|---|... 形式
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s\-:|]+\|?\s*$")


def _parse_blocks(text: str) -> list[str]:
    """把文本切成 md 块列表：代码块/表格保持原子性，普通段落按空行分组。"""
    lines = text.split("\n")
    blocks: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # 代码块开始：``` 起始
        if line.lstrip().startswith("```"):
            j = i + 1
            while j < n and not lines[j].lstrip().startswith("```"):
                j += 1
            # j 此刻指向收尾 ``` 或越界
            end = j + 1 if j < n else n
            blocks.append("\n".join(lines[i:end]))
            i = end
            continue

        # 表格起始：当前行是表格行 + 下一行是分隔行
        if (
            _TABLE_LINE_RE.match(line)
            and i + 1 < n
            and _TABLE_SEP_RE.match(lines[i + 1])
        ):
            j = i
            while j < n and _TABLE_LINE_RE.match(lines[j]):
                j += 1
            blocks.append("\n".join(lines[i:j]))
            i = j
            continue

        # 空行：跳过（段落分隔）
        if not line.strip():
            i += 1
            continue

        # 普通段落：累积到下一个空行 / 代码块 / 表格 起始
        j = i
        while j < n and lines[j].strip():
            if lines[j].lstrip().startswith("```"):
                break
            if (
                _TABLE_LINE_RE.match(lines[j])
                and j + 1 < n
                and _TABLE_SEP_RE.match(lines[j + 1])
            ):
                break
            j += 1
        blocks.append("\n".join(lines[i:j]))
        i = j

    return blocks


def _hard_split_with_continuation(block: str, max_len: int) -> list[str]:
    """单原子块超限时硬切。第一段满 max_len，后续段头部加 (接上)\\n 前缀。

    实际容量：第一段 = max_len；后续段 = max_len - len(前缀)。
    """
    out: list[str] = []
    out.append(block[:max_len])
    rest = block[max_len:]
    cap = max_len - len(CONTINUATION_PREFIX)
    if cap <= 0:
        # 极端情况 max_len 比前缀还短，退回纯硬切（不加前缀以免无意义）
        while rest:
            out.append(rest[:max_len])
            rest = rest[max_len:]
        return out
    while rest:
        out.append(CONTINUATION_PREFIX + rest[:cap])
        rest = rest[cap:]
    return out
