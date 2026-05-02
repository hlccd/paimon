"""LLM 多轮 tool-loop 实现：流式聚合 / provider 故障切换 / 强制收尾。

抽出来让 model.py 的 Model 类不超 500 行；行为与原 Model.chat 完全一致。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncIterator

from loguru import logger

from paimon.llm.base import ToolCallFragment
from paimon.session import Session

if TYPE_CHECKING:
    from .model import Model


class _ToolCallAccumulator:
    """流式 tool_call 聚合器：按 index 拼分片成完整 tool_calls 列表。"""

    def __init__(self):
        self._calls: dict[int, dict[str, str]] = {}

    def update(self, frag: ToolCallFragment) -> None:
        """合并单个分片到对应 index：id/name 覆盖一次，arguments 文本累加。"""
        idx = frag.index
        if idx not in self._calls:
            self._calls[idx] = {"id": "", "name": "", "arguments": ""}
        if frag.id:
            self._calls[idx]["id"] = frag.id
        if frag.name:
            self._calls[idx]["name"] = frag.name
        if frag.arguments:
            self._calls[idx]["arguments"] += frag.arguments

    def get_tool_calls(self) -> list[dict]:
        """按 index 排序返回完整 tool_calls；过滤 name 为空的脏分片。"""
        if not self._calls:
            return []
        return [
            {
                "id": v["id"],
                "type": "function",
                "function": {"name": v["name"], "arguments": v["arguments"]},
            }
            for _, v in sorted(self._calls.items())
            if v["name"]
        ]


async def chat_impl(
    model: "Model",
    session: Session,
    user_input: str,
    tools: list[dict] | None = None,
    tool_executor: Any = None,
    component: str = "chat",
    purpose: str = "闲聊",
) -> AsyncIterator[str]:
    """多轮 tool-loop 主流程：append user → for 15 轮 → 拼 tool_calls → 强制收尾 → 计费。"""
    model.last_chat_cost_usd = 0.0
    model.last_chat_model_name = ""
    model.last_chat_provider_source = ""
    total_usage = model._empty_usage()
    model._sanitize_session_messages(session.messages)
    session.messages.append({"role": "user", "content": user_input})

    max_rounds = 15
    tool_calls: list = []   # 防御：for 0 次时外层检查不会 NameError
    text_buf = ""
    active_provider = None
    for round_idx in range(max_rounds):
        runtime_messages = model._build_runtime_messages(session)
        text_buf = ""
        usage = model._empty_usage()
        tc_acc = _ToolCallAccumulator()

        active_provider, provider_source = await model._pick_provider(component, purpose)
        model.last_chat_model_name = active_provider.model_name
        model.last_chat_provider_source = provider_source
        if round_idx == 0:
            logger.debug(
                "[神之心·路由] {} / {} → {} ({})",
                component, purpose, active_provider.model_name, provider_source,
            )
        try:
            stream_iter = active_provider.chat_stream(runtime_messages, tools=tools)
        except Exception as e:
            if model.gnosis:
                # 按 provider_source 精确上报：profile 级走 _by_profile，
                # env/default 走 _providers（按 model_name）
                if provider_source.startswith("profile:"):
                    model.gnosis.report_failure_by_profile(
                        provider_source.split(":", 1)[1],
                    )
                else:
                    model.gnosis.report_failure(active_provider.model_name)
                # 重新走 _pick_provider：三级 fallback 会自动跳过刚才标记
                # 不健康的那条，拿到语义正确的备用（或 env 兜底）
                fallback, fallback_source = await model._pick_provider(component, purpose)
                if fallback is not active_provider:
                    logger.warning(
                        "[神之心·故障切换] {} / {} {} → {} ({})",
                        component, purpose, provider_source,
                        fallback.model_name, fallback_source,
                    )
                    active_provider = fallback
                    provider_source = fallback_source
                    model.last_chat_model_name = active_provider.model_name
                    model.last_chat_provider_source = provider_source
                    try:
                        stream_iter = active_provider.chat_stream(runtime_messages, tools=tools)
                    except Exception as e2:
                        logger.error("[神之心·模型] 备用也失败: {}", e2)
                        if round_idx == 0:
                            session.messages.pop()
                        yield f"\n\n> [错误] {e2}"
                        return
                else:
                    logger.error("[神之心·模型] 流式初始化失败: {}", e)
                    if round_idx == 0:
                        session.messages.pop()
                    yield f"\n\n> [错误] {e}"
                    return
            else:
                logger.error("[神之心·模型] 流式初始化失败: {}", e)
                if round_idx == 0:
                    session.messages.pop()
                yield f"\n\n> [错误] {e}"
                return

        # 推理 token 流聚合：LLM 思考过程是运行时重要信号（INFO 级），
        # 但按 token 逐片打日志会刷屏 → 累积到"切产出 / 流结束"时一次性 flush。
        # 超长（>800 字）只留首尾，中间省略（多为重复推理步骤）。
        reasoning_buf = ""
        # 整轮累积的 reasoning（供 tool_calls assistant 消息回传）
        # DeepSeek thinking + tool_use 硬约束：工具调用轮的 assistant 消息
        # 必须带 reasoning_content，否则下一轮 API 返回 400。OpenAI 忽略
        # 未知字段，所以无条件塞入 tool_calls 消息里无副作用。
        full_reasoning = ""

        def _flush_reasoning():
            """切产出 / 流结束时把累积的 reasoning_buf 一次性 INFO 输出（>800 字截首尾）。"""
            nonlocal reasoning_buf
            if not reasoning_buf:
                return
            n = len(reasoning_buf)
            if n > 800:
                shown = (
                    reasoning_buf[:400].rstrip()
                    + f"\n... [省略中间 {n - 600} 字] ...\n"
                    + reasoning_buf[-200:].lstrip()
                )
            else:
                shown = reasoning_buf
            logger.info("[神之心·模型] 推理 ({} 字):\n{}", n, shown)
            reasoning_buf = ""

        try:
            async for chunk in stream_iter:
                if chunk.usage:
                    model._merge_usage(usage, chunk.usage)
                    continue
                if chunk.reasoning_content:
                    reasoning_buf += chunk.reasoning_content
                    full_reasoning += chunk.reasoning_content
                # 切到产出阶段（tool_call 或 content）→ flush 先前推理
                if chunk.tool_calls or chunk.content:
                    _flush_reasoning()
                if chunk.tool_calls:
                    for frag in chunk.tool_calls:
                        tc_acc.update(frag)
                if chunk.content:
                    text_buf += chunk.content
                    yield chunk.content
            # 流正常结束后可能还有未 flush 的推理（没 content / tool_call 的情况）
            _flush_reasoning()
        except Exception as e:
            _flush_reasoning()  # 异常也不要丢推理日志
            logger.error("[神之心·模型] 流式传输异常: {}", e)
            if text_buf:
                # DeepSeek thinking 硬约束：所有 assistant 消息都需带 reasoning_content
                session.messages.append({
                    "role": "assistant", "content": text_buf,
                    "reasoning_content": full_reasoning,
                })
            elif round_idx == 0:
                session.messages.pop()
            yield f"\n\n> [错误] {e}"
            return

        if model.gnosis:
            if provider_source.startswith("profile:"):
                model.gnosis.report_success_by_profile(
                    provider_source.split(":", 1)[1],
                )
            else:
                model.gnosis.report_success(active_provider.model_name)
        model._merge_usage(total_usage, usage)

        tool_calls = tc_acc.get_tool_calls()

        if not tool_calls:
            # DeepSeek thinking 硬约束：assistant 消息必须带 reasoning_content
            # （非 thinking provider 忽略未知字段；空串不会触发问题）。
            # 末轮无 tool_calls 也要带，否则下一轮以本会话历史发请求时会 400。
            session.messages.append({
                "role": "assistant", "content": text_buf,
                "reasoning_content": full_reasoning,
            })
            break

        assistant_msg: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
        if text_buf:
            assistant_msg["content"] = text_buf
        # DeepSeek thinking + tool_use 硬约束：带 tool_calls 的 assistant
        # 消息必须带 reasoning_content 字段（可空），否则下一轮 400。
        # 非 thinking provider 下 full_reasoning 为空也要塞空串——避免
        # 后续 session 切到 DeepSeek 时历史消息缺字段翻车。
        assistant_msg["reasoning_content"] = full_reasoning
        session.messages.append(assistant_msg)

        if not tool_executor:
            logger.warning("[神之心·模型] 有 tool_calls 但无 executor")
            break

        for tc in tool_calls:
            fn = tc["function"]
            tc_id = tc["id"]
            logger.debug("[天使·工具调用] {}({})", fn["name"], fn["arguments"][:100])
            try:
                result = await tool_executor(fn["name"], fn["arguments"])
            except Exception as e:
                # 魔女会信号：让 AngelFailure 穿过 tool-call 异常兜底，
                # 由 run_session_chat 接住并转交四影。
                from paimon.angels.nicole import AngelFailure
                if isinstance(e, AngelFailure):
                    raise
                result = f"工具执行错误: {e}"
                logger.error("[天使·工具调用] {} 失败: {}", fn["name"], e)
            session.messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": str(result),
            })
            logger.debug("[天使·工具结果] {} -> {}字符", fn["name"], len(str(result)))

    # for 循环结束判定：
    # - 正常 break（最后一轮无 tool_calls）→ 循环内 if not tool_calls 分支已把 assistant 文本
    #   append 到 session.messages，tool_calls 变量为空列表
    # - 耗尽 max_rounds → tool_calls 仍有值，session.messages 末尾是 tool results，
    #   最后一条 assistant 消息带 tool_calls 且 content 只是过渡语
    # 后者场景下 _extract_result 只能 L2 fallback 抓过渡语几十字符的垃圾 →
    # 强制再跑一次 LLM（不传 tools）让它基于已有信息给纯文字最终答复。
    if tool_calls:
        logger.warning(
            "[神之心·模型] tool loop 达上限 {} 轮仍在调工具，强制收尾一次",
            max_rounds,
        )
        forced_messages = model._build_runtime_messages(session) + [
            {"role": "user",
             "content": (
                f"工具调用已达上限（{max_rounds} 轮）。请基于已有信息直接给出"
                "最终答复，不要再调用工具。"
             )},
        ]
        forced_text = ""
        forced_reasoning = ""
        forced_usage = model._empty_usage()
        try:
            # 关键：tools=None 强制 LLM 走纯文本输出
            async for chunk in active_provider.chat_stream(forced_messages, tools=None):
                if chunk.usage:
                    model._merge_usage(forced_usage, chunk.usage)
                    continue
                if chunk.reasoning_content:
                    forced_reasoning += chunk.reasoning_content
                if chunk.content:
                    forced_text += chunk.content
                    yield chunk.content
        except Exception as e:
            logger.error("[神之心·模型] 强制收尾轮失败: {}", e)
        model._merge_usage(total_usage, forced_usage)
        if forced_text:
            # 进 session.messages 让 _extract_result 走 L1 命中（纯 assistant content）；
            # 带 reasoning_content 字段对齐 DeepSeek thinking 硬约束。
            session.messages.append({
                "role": "assistant",
                "content": forced_text,
                "reasoning_content": forced_reasoning,
            })
            logger.info("[神之心·模型] 强制收尾产出 {} 字", len(forced_text))

    if total_usage["input_tokens"] == 0 and total_usage["output_tokens"] == 0:
        runtime_messages = model._build_runtime_messages(session)
        total_usage["input_tokens"] = model.estimate_messages_tokens(runtime_messages)
        total_usage["output_tokens"] = max(1, (len(text_buf) + 3) // 4)

    total = total_usage["input_tokens"] + total_usage["output_tokens"]
    cost = await model._compute_and_record(session.id, component, total_usage, purpose=purpose)
    model.last_chat_cost_usd = cost
    cache_info = ""
    cw, cr = total_usage["cache_creation_tokens"], total_usage["cache_read_tokens"]
    if cw or cr:
        cache_info = f" 缓存写入={cw} 缓存命中={cr}"
    logger.info(
        "[神之心·模型] token统计: 输入={} 输出={} 总计={}{} 模型={}",
        total_usage["input_tokens"], total_usage["output_tokens"], total,
        cache_info, active_provider.model_name,
    )
