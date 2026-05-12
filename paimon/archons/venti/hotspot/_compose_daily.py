"""每日热点 LLM 综合：6 源原料 → 综合 Top 20 + 各源 Top 3 + 趋势观察。

排序原则：
1. 跨源讨论度（多源讨论同一事件 = 全民关注，权重最高）
2. 各源内排名靠前
3. 时新性（用户更关心今天的热度）
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from ._models import SOURCE_LABELS, CollectResult

if TYPE_CHECKING:
    from paimon.llm.model import Model


_SYSTEM_PROMPT = """\
你是热点编辑。下面是今天 {n_sources} 个中文/科技社区的实时热榜原料（每源前 30 条），按 source 字段标识来源。

## 排序原则（按重要度递减）
1. 跨源讨论度：同一事件被越多源讨论越重要（4 源都讨论 ≫ 单源 #1）
2. 各源内排名靠前（rank=1 比 rank=30 重要）
3. 时新性：今天才发酵的优先于持续了几天的余热

## 跨源合并规则
- 标题主体一致（同人物/事件/产品）→ 合并成一条；时间地点冲突就分开
- 例："小米 SU7 Ultra 上市" 和 "雷军直播 SU7 Ultra 性能" 是同事件 → 合并
- "DeepSeek 发布 V4" 和 "OpenAI 发布 GPT-5.5" 是不同事件 → 分开

## 输出结构（严格遵守，不要加章节、不要加 emoji 开场）

### 多源事件展示格式（≥2 源讨论时；下面分源展开就够，标题不加任何源标注）：
```
1. **[标题][主链接]**
   - **B 站**：1 句基于该源 top 内容的事实
   - **知乎**：1 句
   - **微博**：1 句
   - **HackerNews**：1 句
```

### 单源事件展示格式（仅 1 源；标题也不加源标注，url 域名已说明来源）：
```
1. **[标题](url)** — 1 句话定性
```

## 完整输出模板

```markdown
## 今日热点 Top 20

（按重要度排序，多源事件展开各源观点；单源事件单行）

1. ...
2. ...
... 最多 20 条 ...

## 各源 Top 3

### B 站
1. **[标题](url)** — 1 句话
2. ...
3. ...

### 知乎
（同上）

### 微博
（同上）

### HackerNews
（同上）

## 趋势观察
（基于 Top 20 的 1-2 句事实观察，不脑补，不评价）
```

## 严禁
- ❌ 顶部加任何开场白（"今日热点来了！" / "🔥 ..." 等）
- ❌ 自创章节（"## 今日重点" / "## 编辑评论"）
- ❌ 主观评价词（"必看 / 炸裂 / 牛逼 / 值得关注"）
- ❌ 改写标题（必须原文，最多去前后空白）
- ❌ 脑补该源没说过的内容
- ❌ Top 超过 20 条 / 各源 Top 超过 3 条
- ❌ 只有 1 源讨论的事件展开"各源观点"段（必然瞎编）
- ❌ 标题后加任何源标注（`_(B 站)_` / `_(N 源)_` / `_(N/6 源)_` 等都不要，url 域名已显示来源）
"""


def _format_payload(results: list[CollectResult]) -> dict:
    """把各源 CollectResult 转成 LLM 输入 JSON。"""
    by_source: dict[str, list[dict]] = {}
    for r in results:
        if not r.items:
            continue
        by_source[r.source] = [it.for_prompt() for it in r.items]
    return {
        "today": _today_str(),
        "by_source": by_source,
        "source_labels": {k: SOURCE_LABELS.get(k, k) for k in by_source},
    }


def _today_str() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d")


async def compose_daily(
    results: list[CollectResult], model: Model,
) -> str:
    """跑深池 LLM 综合输出 markdown；失败抛异常给上层处理。"""
    ok_results = [r for r in results if r.ok]
    if not ok_results:
        raise RuntimeError("所有源都失败，无原料可综合")

    payload = _format_payload(ok_results)
    n_sources = len(ok_results)
    system = _SYSTEM_PROMPT.format(n_sources=n_sources)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
    raw, usage = await model._stream_text(
        messages, component="风神", purpose="每日热点",
    )
    await model._record_primogem("", "风神", usage, purpose="每日热点")
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
    if not text:
        raise RuntimeError("LLM 返回空")
    logger.info(
        "[hotspot·compose] LLM 综合完成 sources={} 输出={} chars",
        n_sources, len(text),
    )
    return text
