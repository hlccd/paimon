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


def build_speak_prompt(
    role_system: str, topic: str, opening: str,
    history: list[dict], instruction: str,
) -> list[dict[str, str]]:
    """单个天使发言 prompt。"""
    history_str = _format_history(history, tail_n=6)
    user = (
        f"议题：{topic}\n开题：{opening}\n\n"
        f"已有发言：\n{history_str}\n\n"
        f"晨星给你的指令：{instruction}\n\n"
        "请发言（≤120 字，1-2 个具体观点 + 简短论据；不要客套；不要复述他人）。"
    )
    return [
        {"role": "system", "content": role_system},
        {"role": "user", "content": user},
    ]


def build_synthesize_prompt(
    topic: str, opening: str, history: list[dict],
) -> list[dict[str, str]]:
    """晨星综合：把讨论浓缩成最终结论。"""
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
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
