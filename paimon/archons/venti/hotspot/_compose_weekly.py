"""近期回顾 LLM 综合：汇总过去 7 天的 daily_hotspot markdown，输出回顾。

输入：每天 ≤2 条 daily markdown（每条已是综合后的 Top 20 + 各源 Top 3）
输出：近期 Top 30 + 持续发酵主题 + 领域演进 + 一句话总结
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.llm.model import Model


_SYSTEM_PROMPT = """\
你是回顾编辑。下面是 {range_start} ~ {range_end} 这 7 天里风神共采集到 {n_dailies} 次的
每日热点综合 markdown（每条都是当天某时段的 Top 20 + 各源 Top 3 + 趋势观察）。

数据可能不足 14 次（理论最大）—— 例如系统启动只跑了 N 次，照实合成即可。

## 任务

写近期热点回顾。维度：
1. **跨日合并**：同一事件可能在多日多时段重复出现 → 合并为一条
2. **持续度优先**：跨多日上榜的事件比单日爆点更重要（持续话题 = 真正影响近期）
3. **时间线清晰**：标注事件首次上榜 / 爆发点 / 余热的时间节点

## 输出结构（严格遵守，不要加章节、不要加 emoji 开场）

```markdown
## 近期热点 Top 30 · {range_start} ~ {range_end}

（按"窗口内累积曝光度 + 持续度"排序；数据不足时按实际条数）

1. **[事件标题](url)** — 1 句话事件回顾 + 时间节点
2. ...
... 最多 30 条 ...

## 持续发酵主题

（≥3 天上榜的事件单独列；少于 3 天就省略此段）

- **主题 X**：5/8 首发 → 5/10 爆点 → 5/12 平息（关键时间点 + 1 句话）
...

## 领域演进

- 🔬 科技：近期关键发展（1-2 句）
- 🎭 娱乐：（1-2 句）
- 🏛️ 社会 / 时事：（1-2 句）
- 💼 财经 / 商业：（1-2 句）
- 其他...

## 一句话总结

（这 7 天最值得记住的 1 件事，30 字内）
```

## 严禁

- ❌ 顶部加任何开场白（"近期回顾来了" / "🔥 ..." 等）
- ❌ 自创章节
- ❌ 主观评价词（"必看 / 炸裂 / 牛逼 / 引爆"）
- ❌ 凭空捏造时间节点（必须基于 daily 数据里出现的日期）
- ❌ Top 超过 30 条
- ❌ 把 daily 的"今日趋势观察"原样复述
- ❌ 数据不足时编造内容（只 1 次 daily 就老老实实基于那 1 次写）
- ❌ 标题后加任何源/次数标注（`(出现 N 次)` / `(N/6 源)` / `(M 源讨论)` 等都不要，标题主体即可）
"""


async def compose_weekly(
    daily_records: list[dict], model: Model,
    range_start: str, range_end: str,
) -> str:
    """跑深池 LLM 综合 ≤14 条 daily markdown 写近期回顾。

    daily_records 顺序：按 captured_at 升序（最早 → 最新），LLM 才能识时间线。
    数据不足（如 daily_records 只有 1 条）也照样能跑，prompt 已说明。
    """
    if not daily_records:
        raise RuntimeError("窗口内无 daily_hotspot 记录")

    # 拼接每条 daily（标日期 + slot 让 LLM 看清时间线）
    parts: list[str] = []
    for rec in daily_records:
        slot_label = "11:00" if rec.get("capture_slot") == "morning" else "17:00"
        parts.append(
            f"# === {rec.get('capture_date')} {slot_label} ===\n\n"
            + (rec.get("markdown") or "")
        )
    body = "\n\n".join(parts)

    n_dailies = len(daily_records)
    system = _SYSTEM_PROMPT.format(
        n_dailies=n_dailies, range_start=range_start, range_end=range_end,
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": body},
    ]
    raw, usage = await model._stream_text(
        messages, component="风神", purpose="近期回顾",
    )
    await model._record_primogem("", "风神", usage, purpose="近期回顾")
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
    if not text:
        raise RuntimeError("LLM 返回空")
    logger.info(
        "[hotspot·近期回顾] LLM 综合完成 n_dailies={} 输出={} chars",
        n_dailies, len(text),
    )
    return text
