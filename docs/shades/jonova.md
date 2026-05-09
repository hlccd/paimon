# 死执·若纳瓦

> 隶属：[神圣规划](../aimon.md) / 四影 — **审**

**定位**：自进化提案质量审。当前唯一 stage：**review_proposal**。

> 安全审（`task_review` / `review_skill_declaration` / `detect_sensitive`）在派蒙
> [`paimon/core/safety/`](../../paimon/core/safety/)，不归死执。

## 职能

输入：从 prior_results 解析的 prop_id → 读 skill_proposals 域里的草案。

LLM 审 4 维度：
1. 草案完整度（system_prompt 不空泛 / triggers 清晰 / 步骤可执行）
2. 跟现有 skill 是否重叠（拉 skill_declarations 列表对比）
3. allowed_tools 是否最小权限（敏感工具是否真需要）
4. 边界是否清晰（什么时候用 / 不该用）

输出 ReviewVerdict 协议 JSON：
```json
{"level": "pass|revise|redo", "summary": "≤150 字总评", "issues": [...]}
```

同步写 skill_proposals.review_verdict + review_notes（用户面板展示用）：
- `level=pass` → verdict='pass'
- `level=revise` → verdict='needs_revise'（用户面板 approve 按钮 disabled）
- `level=redo` → verdict='reject'（联动 status=rejected）

## 公开 API

```python
from paimon.shades.jonova import review_proposal
verdict_text = await review_proposal(task, subtask, model, irminsul, prior_results)
# 返 JSON 字符串
```

实现：[`paimon/shades/jonova/review_proposal.py`](../../paimon/shades/jonova/review_proposal.py)

## SKIP 短路

prior_results 含 `SKIP:`（生执判定不值得做）→ 死执直接返 `{"level":"pass","summary":"生执判定无需提案"}`，不发 LLM。
