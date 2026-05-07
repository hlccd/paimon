"""9 个 stage 的配置：(skill_name, allowed_tools, system_prompt_template)。

stage → 处理函数的路由由 runner.run_stage 按下表分派。
"""
from __future__ import annotations

# 工人产物输出契约（所有 stage 的 system prompt 末尾追加）
FINAL_OUTPUT_RULE = """
⚠️ 输出契约（硬性要求）：
- 无论你是否调用了工具，**最后一轮必须输出一段中文文字**，作为对当前子任务的最终回答或总结。
- 不能只留下 tool_calls 就停止；不能把答案完全寄存在 reasoning 里；不能让最后一条消息是 tool 调用结果。
- 上层（四影 / /task-index 摘要）会从你最末一条「assistant 文本消息」抓取 result，没有就视作产物为空。
"""


# ─────────────────────────────────────────────────────────────────────────────
# Skill 驱动 stage 的配置（spec / design / code → 调 skill workflow）
# ─────────────────────────────────────────────────────────────────────────────

SKILL_STAGES = {
    "spec": {
        "skill": "requirement-spec",
        "allowed_tools": {"file_ops"},
        "purpose": "写产品方案",
        "display_name": "工人·spec",
    },
    "design": {
        "skill": "architecture-design",
        "allowed_tools": {"file_ops"},
        "purpose": "写技术方案",
        "display_name": "工人·design",
    },
    "code": {
        "skill": "code-implementation",
        "allowed_tools": {"file_ops", "exec"},
        "purpose": "代码实现",
        "display_name": "工人·code",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Review stage（review_spec / review_design / review_code）
# 走 _review.py 内部的 light + check skill 双路径，不在此处简单配置
# ─────────────────────────────────────────────────────────────────────────────

REVIEW_STAGES = ("review_spec", "review_design", "review_code")


# ─────────────────────────────────────────────────────────────────────────────
# 纯 LLM tool-loop stage（无 skill）
# ─────────────────────────────────────────────────────────────────────────────

SIMPLE_CODE_PROMPT = """\
你负责"简单代码"任务（trivial / simple DAG 不带 spec/design）。
能力：file_ops 写代码到 workspace/code/、exec 跑测试 / lint。

规则：
1. 当前项目路径是 .
2. 用 file_ops write 写文件，不要用 exec echo
3. 写完后用 exec 跑 py_compile / ruff / pytest 自检
4. 输出结构化结果：文件路径 + 代码要点 + 自检结论
"""

EXEC_PROMPT = """\
你负责重型执行任务（shell / 部署 / 命令行工具）。
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
    "simple_code": {
        "prompt": SIMPLE_CODE_PROMPT,
        "allowed_tools": {"file_ops", "exec"},
        "purpose": "代码生成(简易)",
        "display_name": "工人·simple_code",
    },
    "exec": {
        "prompt": EXEC_PROMPT,
        "allowed_tools": {"exec"},
        "purpose": "shell 执行",
        "display_name": "工人·exec",
    },
    "chat": {
        "prompt": CHAT_PROMPT,
        "allowed_tools": {"file_ops"},
        "purpose": "通用推理",
        "display_name": "工人·chat",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 全部 stage 名（供 naberius _VALID_STAGES 引用）
# ─────────────────────────────────────────────────────────────────────────────

ALL_STAGES = (
    *SKILL_STAGES.keys(),
    *REVIEW_STAGES,
    *SIMPLE_STAGES.keys(),
)


def get_display_name(stage: str) -> str:
    """stage → 工人显示名。日志 / audit / flow_append 用这个标识 from_agent。"""
    if stage in SKILL_STAGES:
        return SKILL_STAGES[stage]["display_name"]
    if stage in SIMPLE_STAGES:
        return SIMPLE_STAGES[stage]["display_name"]
    if stage in REVIEW_STAGES:
        return f"工人·{stage}"
    return f"工人·{stage}"
