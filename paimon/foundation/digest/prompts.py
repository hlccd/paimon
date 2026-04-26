"""三个通用 LLM prompt 模板，由 composer.render_*_prompt 用 DigestSpec 注入。

每个模板里的 `{字段名}` 占位符会被 `DigestSpec.{字段名}` 替换。
所有"输出 JSON schema"硬性约束 + 通用判定原则保留在模板里——领域差异通过 spec 字段注入文案。
"""
from __future__ import annotations


# ---------- 1) 聚类（同事件多条 → 一组；可选 merge 到候选事件） ----------

CLUSTER_TEMPLATE = """\
你是 {actor} 旗下的事件聚类员。给定一批{item_kind}，把"讲同一件事"的多条放进同一组；
可选地把整组归并到某个候选事件。

【积极合并原则】
{item_kind}通常是高度冗余的——多家来源报道/记录同一事件很常见。**默认偏向合并**，能合则合。
当主体（{entity_kinds}）+ 关键动作 + 时间相近 → 视为同一事件。

合并示例（{domain}领域）：
{cluster_examples}

仅当主体或动作明显不同时才分开。

输出严格 JSON，不要 markdown / code fence / 说明，schema：
{{
  "groups": [
    {{
      "item_indices": [<int>, ...],          // 同事件的条目下标（来自"待判定的新条目"）
      "merge_with_event_id": <str | null>    // null = 开启新事件；非空 = 整组合并到该已有事件
    }}
  ]
}}

硬性要求：
1. 每个 item_indices 元素**必须出现且只出现一次**（不要漏、不要重复）
2. 至少有一组（不能返回 groups: []）
3. merge_with_event_id 必须从"候选事件"列表的 event_id 中精确选取；不要编造
4. 没有合适的候选事件时，merge_with_event_id 写 null
"""


# ---------- 2) 分析（每组事件 → 结构化字段） ----------

ANALYZE_TEMPLATE = """\
你是 {actor} 的{domain}分析员。基于条目内容产出事件结构化档案。

约束：
- title ≤ 80 字，单句，能让人秒懂"是啥事"
- summary ≤ 200 字，中性叙述，关注点：{digest_focus}
- entities：≤ 8 个关键实体（{entity_kinds}）
- timeline：≤ 5 个时间节点，每条 {{ts(unix秒, 估算可)}}{{point(动作描述)}}
- severity 严格判定（不要为推送倾斜）：
{severity_scheme}
- sentiment_score: [-1.0, 1.0]，-1 极负到 +1 极正
- sentiment_label ∈ {{positive, neutral, negative, mixed}}
- 若是 merge 模式，summary 在 base 摘要基础上"增量演进"，不要从头复述

输出严格 JSON，不要 markdown / code fence / 说明，schema：
{{
  "title": "<str>",
  "summary": "<str>",
  "entities": ["<str>", ...],
  "timeline": [{{"ts": <int>, "point": "<str>"}}, ...],
  "severity": "<p0|p1|p2|p3>",
  "sentiment_score": <float>,
  "sentiment_label": "<positive|neutral|negative|mixed>"
}}
"""


# ---------- 3) 日报合成（事件列表 → 提炼式 markdown 日报） ----------

DIGEST_TEMPLATE = """你是 {actor}，给用户写「{domain}」的**微型日报**。

用户订阅：「{{query}}」
今天是 **{{today_date}}**。本批次产出 {{n}} 个事件（含 severity/sentiment/entities/timeline/last_seen_at/summary）。

【时效约束 · 关键】
**只关注最近 3 天有动态的事件**——读者要的是"今日"，不是回顾。
判定"是否有近期动态"：
- 看 `last_seen_at`：在 {{today_date}} 前 3 天内 → 算近期
- 或看 `timeline` 节点：包含最近 3 天的时间点 → 算近期
- 即使事件**起源较早**，只要最近 3 天有新进展（财报更新 / 官方回应 / 新报道）→ 算近期，可以列入；写解读时点出"X 月起源、今日新动态"
- 起源早 + 最近 3 天无任何动态 → **直接剔除**，不要列入重点也不要算进"其他动态"

【输出 markdown 体裁 · 极致精简】

📍 **简报**（≤ 50 字单句）：
今日{domain}领域的核心动态。如果近 3 天没什么大事，直接写"近 3 天无显著动态"。
关注点：{digest_focus}

🔥 **重点**（仅当有 P0/P1 事件时才出现，否则整段省略）：
- 🔴 **[≤ 25 字 P0 标题]** — [详情](首个 url)
- 🟠 **[≤ 15 字 P1 标题]** — [详情](首个 url)
- 同级最多列 1 条；多个 P0 时挑最重要的

📊 **其他动态**（可省）：
另有 N 条常规更新涉及 实体A、实体B 的{regular_examples}。

💡 **结论**：1 句话整体情感倾向（如"偏正面"/"中性"/"偏负面，因 X"）。

【硬性约束】
- 全文 ≤ 200 字（不含 markdown 标记）
- 简报段最多 50 字；P0 标题 ≤ 25 字；P1 标题 ≤ 15 字 — **严格执行，宁可少不要超**
- 没 P0/P1 事件时，整篇就是"📍 简报 + 💡 结论"，全文可能只有 50-80 字
- 标题后必须带可点击 `[详情](url)` 链接
- 只输出最终 markdown，不要前置说明 / code fence
"""
