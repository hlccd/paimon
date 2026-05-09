"""四影 stage 配置中心（公共，各影按需引用）。

stage 池：
- 生执 produce：propose_skill（凝练 skill 草案落 skill_proposals 域）
                + exec / chat（兜底 LLM tool-loop，无 skill）
- 死执 review：review_proposal（审 skill 提案，写 verdict）

asmoday 用 ALL_STAGES + 内部路由表派活给各影。
"""
from __future__ import annotations


# 产物 stage 输出契约（所有 LLM tool-loop 路径的 system prompt 末尾追加）
FINAL_OUTPUT_RULE = """
⚠️ 输出契约（硬性要求）：
- 无论你是否调用了工具，**最后一轮必须输出一段中文文字**，作为对当前子任务的最终回答或总结。
- 不能只留下 tool_calls 就停止；不能把答案完全寄存在 reasoning 里；不能让最后一条消息是 tool 调用结果。
- 上层（四影 / /task-index 摘要）会从你最末一条「assistant 文本消息」抓取 result，没有就视作产物为空。
"""


# ─────────────────────────────────────────────────────────────────────────────
# Skill 驱动 stage（生执 propose_skill）
# ─────────────────────────────────────────────────────────────────────────────

# propose_skill 不调 skill，自由 LLM 凝练（见 naberius/propose.py）。
# 留 SKILL_STAGES 接口给未来用 skill 驱动的 stage（暂时空字典）。
SKILL_STAGES: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Review stage（死执 review_proposal）
# ─────────────────────────────────────────────────────────────────────────────

# 评审循环用的 stage 名集合（pipeline/_verdict.py 的 _resolve_verdict 按此过滤
# review 节点的 verdict）。
REVIEW_STAGES = ("review_proposal",)


# ─────────────────────────────────────────────────────────────────────────────
# 纯 LLM tool-loop stage（生执 _simple，无 skill）
# ─────────────────────────────────────────────────────────────────────────────

EXEC_PROMPT = """\
你负责重型执行任务（shell / 部署 / 命令行工具 / saga 补偿）。
能力：exec 执行任意命令。

规则：
1. 当前项目路径是 .
2. 谨慎执行有副作用命令（写盘 / 网络 / 删除）
3. 输出结构化结果：执行步骤 + 关键输出 + 是否成功
"""

CHAT_PROMPT = """\
你负责通用推理 / 总结任务（默认兜底）。
能力：file_ops 读项目文件作参考。

规则：
1. 基于当前任务和子任务的描述给出推理结论
2. 引用 prior_results 中已有的产物
3. 输出最终答案文本
"""


SIMPLE_STAGES = {
    "exec": {
        "prompt": EXEC_PROMPT,
        "allowed_tools": {"exec"},
        "purpose": "shell 执行",
        "display_name": "生执·exec",
    },
    "chat": {
        "prompt": CHAT_PROMPT,
        "allowed_tools": {"file_ops"},
        "purpose": "通用推理",
        "display_name": "生执·chat",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 全部 stage 名（asmoday + naberius._parser 引用）
# ─────────────────────────────────────────────────────────────────────────────
#
# 4 个 stage：
#   - propose_skill（生执，自进化提案产生）
#   - review_proposal（死执，提案质量审）
#   - exec（生执，shell / saga 补偿）
#   - chat（生执，通用兜底）

ALL_STAGES = (
    "propose_skill",
    *REVIEW_STAGES,
    *SIMPLE_STAGES.keys(),
)


def get_display_name(stage: str) -> str:
    """stage → 显示名。日志 / audit / flow_append 用这个标识 from_agent。"""
    if stage == "propose_skill":
        return "生执·propose_skill"
    if stage in SIMPLE_STAGES:
        return SIMPLE_STAGES[stage]["display_name"]
    if stage in REVIEW_STAGES:
        return f"死执·{stage}"
    return f"四影·{stage}"
