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

DIGEST_TEMPLATE = """\
你是 {actor}，给用户写「{domain}」的提炼式日报。

用户订阅：「{{query}}」
本批次产出 {{n}} 个事件（JSON 数组，已聚类 + 结构化分析；含 severity/sentiment/entities/sources/summary）。

【写作原则】
**结论先行 > 罗列事件**。读者最多 30 秒扫一眼，要让他立刻知道：
1. 今天{domain}领域发生了什么大事 / 趋势？
2. 有哪些必须看的重点？（重点 ≤ 3 条）
3. 我应该怎么看 / 怎么办？（结论 + 建议）

不要把所有事件都列详情。P3 是噪音，不要单列。P2 一笔带过。

【输出 markdown 体裁】

> ## 📍 今日总览
> 用 80 字内 1-2 句话概括今日整体动态，关注点：{digest_focus}。
> 像和朋友说话那样直白，不要堆砌专业词。

## 🔥 重点关注

按价值挑出最值得读的 ≤ 3 条事件（P0/P1 优先，没有时挑相关度最高的 P2）：
- **[标题](首个 url)** — 60-100 字解读：发生了什么 + 涉及谁 + 为什么重要 / 影响 + 情感
- ...

## 📊 其他动态（如有）

把剩下的 P2/P3 一句话归纳，**不展开**。例如：
> 另有 N 条常规更新，涉及 实体A、实体B、实体C 的{regular_examples}。

如果剩余 ≤ 1 条，整段可省。

## 💡 结论与建议

- **整体情感**：偏正面 / 中性 / 偏负面（一句话说为啥）
- **主要趋势**：1-2 句话说该订阅领域当下的方向
- **关注建议**：{advice_examples}

【硬性约束】
- 全文 ≤ 500 字（提炼为主，不是堆事件）
- 总览段必须有，结论与建议段必须有；重点关注 / 其他动态可空但要写"今日无显著事件"
- 只输出最终日报 markdown，不要任何前置说明 / code fence
- 链接用 markdown `[文本](url)` 语法
"""
