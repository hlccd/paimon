"""晨星调度 LLM 的四个 prompt：assemble / dispatch / speak / synthesize。

晨星每次调用都用 single-turn `model._stream_text(messages, ...)`，不走 session.messages
共享上下文（讨论 history 通过 prompt 拼字符串传，避免污染派蒙的会话状态）。
"""
from __future__ import annotations

import json

from .roles import list_roles_for_assemble


def _format_history(history: list[dict], tail_n: int = 6) -> str:
    """讨论 history 拼字符串：取最近 tail_n 条避免 token 爆炸。"""
    if not history:
        return "（暂无发言）"
    return "\n\n".join(
        f"[{h['role_name']}]：{h['content']}"
        for h in history[-tail_n:]
    )


def build_assemble_prompt(topic: str) -> list[dict[str, str]]:
    """晨星 assemble：根据议题挑 3-5 角色 + 写开题陈述。"""
    roles_brief = list_roles_for_assemble()
    roles_str = json.dumps(roles_brief, ensure_ascii=False, indent=2)
    user = (
        f"议题：{topic}\n\n"
        f"可选天使：\n{roles_str}\n\n"
        "请挑 3-5 个最能贡献多视角讨论的天使，给出召集列表 + 开题陈述。"
    )
    system = (
        "你是「晨星」，多视角讨论的主持。"
        "你只输出严格 JSON，不要 markdown 代码块、不要 ```、不要任何额外说明。\n"
        'Schema: {"members": ["role_key", ...], "opening": "≤200 字开题陈述"}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_dispatch_prompt(
    topic: str, opening: str, history: list[dict],
    members: list[str], turn: int, max_turns: int,
) -> list[dict[str, str]]:
    """晨星 dispatch：决定下一发言者 / 指令 / 是否收敛。"""
    history_str = _format_history(history, tail_n=6)
    members_str = ", ".join(members)
    user = (
        f"议题：{topic}\n开题：{opening}\n\n"
        f"参与天使（key）：{members_str}\n\n"
        f"最近发言：\n{history_str}\n\n"
        f"当前轮次：{turn} / 上限 {max_turns} 轮发言\n\n"
        "请决定：(1) 下一个谁发言（role_key）+ 给他什么具体指令"
        "（针对当前讨论焦点，不重复指令）；"
        "(2) 是否可以收敛（共识形成 / 死锁 / 议题已穷尽）"
    )
    system = (
        "你是「晨星」，主持下一轮发言。"
        "你只输出严格 JSON，不要 markdown 代码块。\n"
        'Schema: {"next_speaker": "role_key" | null, '
        '"instruction": "针对当前焦点的具体指令", '
        '"should_converge": false, "reason": "决策理由（≤80 字）"}\n'
        "约束：避免连续 2 轮指派同一天使；should_converge=true 时 next_speaker=null。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _format_background(background: str = "") -> str:
    """把 scout 阶段收集的信息包格式化为发言前置背景段。空串时返空。"""
    if not background.strip():
        return ""
    return (
        "\n\n# 背景资料（晨星·调研收集，可在发言中引用，引用时打 [依据] 标）\n"
        f"{background.strip()}\n"
    )


def build_speak_prompt(
    role_system: str, topic: str, opening: str,
    history: list[dict], instruction: str,
    background: str = "",
) -> list[dict[str, str]]:
    """单个天使发言 prompt。background 由晨星 scout 阶段收集，注入发言前置 system context。"""
    history_str = _format_history(history, tail_n=6)
    user = (
        f"议题：{topic}\n开题：{opening}\n\n"
        f"已有发言：\n{history_str}\n\n"
        f"晨星给你的指令：{instruction}\n\n"
        "请发言（≤120 字，1-2 个具体观点 + 简短论据；不要客套；不要复述他人）。"
    )
    return [
        {"role": "system", "content": role_system + _format_background(background)},
        {"role": "user", "content": user},
    ]


def build_synthesize_prompt(
    topic: str, opening: str, history: list[dict],
    background: str = "",
) -> list[dict[str, str]]:
    """晨星综合：把讨论浓缩成最终结论。background 一并参考，引用时打 [依据]。"""
    history_str = "\n\n".join(
        f"[{h['role_name']}]：{h['content']}"
        for h in history
    )
    user = (
        f"议题：{topic}\n开题：{opening}\n\n"
        f"完整讨论历史：\n{history_str}\n\n"
        "请输出最终结论（markdown），结构：\n"
        "## 共识\n（达成一致的判断 1-3 条）\n\n"
        "## 分歧（如有）\n（保留双方观点，不强制收敛）\n\n"
        "## 建议下一步\n（1-2 条可执行行动）"
    )
    system = (
        "你是「晨星」，整理本次讨论结论。"
        "保持中立、忠实代表各方观点，不强行收敛或脑补未讨论的内容。"
        "若引用了背景资料，在相应判断后打 [依据] 标记。"
    )
    return [
        {"role": "system", "content": system + _format_background(background)},
        {"role": "user", "content": user},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# scout 阶段：plan_info（拆议题 → 信息需求清单）+ collect（调 tool 收资料）
# ─────────────────────────────────────────────────────────────────────────────

def build_plan_info_prompt(topic: str) -> list[dict[str, str]]:
    """晨星·拆议题：分析要做这个决策需要什么外部信息，输出 JSON 清单。"""
    user = (
        f"议题：{topic}\n\n"
        "请分析：要支撑后续多视角讨论，是否需要外部信息？默认倾向是 **skip=false（去收集）**，"
        "只有以下两类才 skip=true：\n\n"
        "**判 skip=true 的两类（很窄）**：\n"
        "1. **纯个人内省 / 情感偏好**：「我喜欢什么颜色」「我该不该原谅 X」「我现在心情好不好」"
        "  —— 答案完全在用户自己脑子里，外部信息无法贡献\n"
        "2. **极小范围个人事务**：「我下周二要不要请假」「我今晚吃啥」"
        "  —— 信息全在用户日常生活，无外部可查\n\n"
        "**其他全部 skip=false（要收集）**：\n"
        "- 推荐 / 调研 / 综述 / 选型类（「推荐 3 本理财书」「选哪台 NAS」「self-hosted LLM 框架现状」）"
        "  —— 即使有主观成分，候选 / 流派 / 数据点也是客观信息\n"
        "- 决策类（「跳槽 X 厂利弊」「该不该买 mac」）—— 行业现状 / 价格 / 趋势是客观信息（但生活影响主观，由 lifestyle 等天使展开）\n"
        "- 复盘类（「上次重构哪做错了」）—— 项目内事实（source_hint=project）\n"
        "- 时事 / 行情类 —— web-search\n\n"
        "info_needs 最多 4 条，每条 ≤30 字主题。"
        "source_hint 可选值：web-search / topic / knowledge / project（读项目代码）。"
    )
    system = (
        "你是「晨星」，正在准备多视角讨论的资料。"
        "你只输出严格 JSON，不要 markdown 围栏、不要任何额外文字。\n"
        'Schema: {"skip": bool, "reason": "≤60 字", '
        '"info_needs": [{"topic": "...", "source_hint": "web-search|topic|knowledge|project"}]}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_collect_system(info_needs: list[dict]) -> str:
    """collect 阶段的 system prompt（tool-loop 模式，让 LLM 自己调 tool 收集）。"""
    needs_str = "\n".join(
        f"  {i+1}. {n.get('topic','')}（建议来源：{n.get('source_hint','')}）"
        for i, n in enumerate(info_needs)
    )
    return (
        "你是「晨星」，正在为多视角讨论收集背景资料。\n\n"
        f"需要收集的信息（共 {len(info_needs)} 项）：\n{needs_str}\n\n"
        "工作要求：\n"
        "1. 按清单逐项调用 tool 收集（web_search / topic / file_ops 等可用工具）\n"
        "2. 每项 1-2 次 tool 调用即可，不要过度展开\n"
        "3. 全部收集完后，整理成一份**信息包**，markdown 列表格式：\n"
        "   - **<topic>**：核心事实 + 数字（≤200 字摘要，不要长引用）\n"
        "4. 信息包总长度 ≤ 4000 字。超长时优先保留核心数据点\n"
        "5. **不要**给出主观判断或建议（那是后续天使的职责）"
    )
