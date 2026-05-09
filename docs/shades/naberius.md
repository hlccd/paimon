# 生执·纳贝里士

> 隶属：[神圣规划](../aimon.md) / 四影 — **生**

**定位**：从 task 上下文凝练 skill 草案。当前唯一 stage：**propose_skill**。

## 职能

- 输入：task 标题 + 描述 + 子任务结果 + 现有 skill 列表
- LLM 凝练：name / description / triggers / system_prompt / allowed_tools / rationale
- 严格判定门槛（借鉴 hermes-agent）：判断不值得做时输出 `{"skip":true,"reason":"..."}` 短路退出，**不**写空提案污染面板
- 落档：`irminsul.skill_proposal_create()` 写 skill_proposals 域 status=pending

## 公开 API

```python
from paimon.shades.naberius import propose_skill
result = await propose_skill(task, subtask, model, irminsul, prior_results)
# 落档成功：'prop_id=<12hex>\n<草案概要>'
# 短路：'SKIP: <reason>'
```

实现：[`paimon/shades/naberius/propose.py`](../../paimon/shades/naberius/propose.py)

## 触发路径

- 用户主动 `/evolve` 命令（[`paimon/core/commands/evolve.py`](../../paimon/core/commands/evolve.py)）
- 时执 archive 收尾 hook（[`paimon/shades/istaroth/_propose_trigger.py`](../../paimon/shades/istaroth/_propose_trigger.py)）
- 三月 cron 月度扫描（[`paimon/skill_loader/proposal_cron.py`](../../paimon/skill_loader/proposal_cron.py)）

三条路径都跳过 plan 编排，直接调 `propose_skill` 函数；下游紧跟死执 `review_proposal`。

## 跟死执的衔接

propose_skill 输出首行 `prop_id=<12hex>`，死执 review_proposal 通过 `prior_results` 字符串解析 prop_id 拿到提案。

死执 SKIP 的场景：propose 输出 `SKIP:` 时 review_proposal 短路 pass，不再发起 LLM 评审。
