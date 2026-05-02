"""派蒙启动期注册的 leyline 事件处理器：三月响铃 / skill 加卸 / LLM 路由热切。

这些都是模块级 async 函数，被 create_app 内 leyline.subscribe 注册一次。
分离出来让 main.py 的 create_app 不被嵌套 def 撑大；行为完全等价。
"""
from __future__ import annotations

from loguru import logger

from paimon.foundation.leyline import Event
from paimon.state import state


async def _on_march_ring(event: Event) -> None:
    """三月触发到期任务 → 按 task_type 走 registry 分派；否则 fallback LLM。"""
    payload = event.payload
    channel_name = payload.get("channel_name", "")
    chat_id = payload.get("chat_id", "")
    prompt = payload.get("prompt", "")
    task_id = payload.get("task_id", "")

    # ---- 方案 D：非 user 类型的周期任务经 task_types registry 分派 ----
    # payload 需带 task_id（由 march._fire_task 注入），拉完整 ScheduledTask
    # 读 task_type 和 source_entity_id；dispatcher 由各 archon 注册时注入。
    if task_id and state.irminsul:
        task = None
        try:
            task = await state.irminsul.schedule_get(task_id)
        except Exception as e:
            logger.debug("[三月·分派] 读任务失败 task_id={}: {}", task_id, e)
        if task and task.task_type and task.task_type != "user":
            from paimon.foundation import task_types as _tt
            meta = _tt.get(task.task_type)
            if meta is None:
                logger.warning(
                    "[三月·分派] 未知 task_type={} task_id={}（未注册；"
                    "不 fallback 到 LLM 以避免把内部任务误当用户 prompt）",
                    task.task_type, task_id,
                )
                return
            try:
                await meta.dispatcher(task, state)
            except Exception as e:
                logger.exception(
                    "[三月·{}] 分派异常 task_id={}: {}",
                    meta.display_label, task_id, e,
                )
            return

    # 三月·Deep 自检的 [SELFCHECK_DEEP] cron 分派已撤销（docs/todo.md §
    # 三月·自检·Deep 暂缓）。当前 LLM 模型对 check skill 跑不充分，
    # 周期性自动触发没意义；底层 SelfCheckService.run_deep 代码保留，
    # 只留手动入口（/selfcheck --deep，受 selfcheck_deep_hidden 开关）。

    channel = state.channels.get(channel_name)
    if not channel:
        logger.warning("[派蒙·响铃] 频道不存在: {}", channel_name)
        return

    # 频道能力分流（docs/aimon.md §2.6）：QQ 等不支持主动推送的频道静默跳过
    if not getattr(channel, "supports_push", True):
        logger.info(
            "[派蒙·响铃] 频道 {} 不支持推送，跳过投递（数据已落盘，用户需主动查询）",
            channel_name,
        )
        return

    if prompt and state.model:
        try:
            from paimon.session import Session
            # 每次响铃用独立 session id，避免并发任务的 token 记录全聚合到 "march-tmp"
            tmp_sid = f"march-{task_id[:12]}" if task_id else "march-tmp"
            temp_session = Session(id=tmp_sid, name="三月任务")
            text_parts = []
            async for chunk in state.model.chat(
                temp_session, prompt,
                component="march", purpose="定时任务",
            ):
                text_parts.append(chunk)
            result = "".join(text_parts)
            if result.strip():
                await channel.send_text(chat_id, result)
        except Exception as e:
            logger.error("[派蒙·响铃] LLM 处理失败 task={}: {}", task_id, e)
            try:
                await channel.send_text(chat_id, f"定时任务执行失败: {e}")
            except Exception as e2:
                logger.error("[派蒙·响铃] 错误信息投递也失败: {}", e2)
    else:
        message = payload.get("message", "")
        if message:
            try:
                await channel.send_text(chat_id, message)
            except Exception as e:
                logger.error("[派蒙·响铃] 无 prompt 投递失败: {}", e)


async def _on_skill_loaded(event: Event) -> None:
    """权限缓存：新 skill 上线 / 卸载时失效对应缓存（避免 dangling 授权被消费）。"""
    payload = event.payload
    name = payload.get("name")
    if state.authz_cache and name:
        state.authz_cache.invalidate("skill", name)


async def _on_llm_profile_updated(event: Event) -> None:
    """M2：profile 热切换 — gnosis 端清掉 profile 缓存；删除时 router 也 reload。"""
    payload = event.payload or {}
    pid = payload.get("profile_id", "")
    action = payload.get("action", "")
    if pid and state.gnosis:
        state.gnosis.invalidate_profile(pid)
    # 删除 profile 时 DB FK CASCADE 已清 llm_routes 的对应行，但
    # ModelRouter 内存缓存还持有旧映射；reload 同步之。set_default
    # 不影响路由表，无需 reload。
    if action == "delete" and state.model_router:
        await state.model_router.reload()


async def _on_llm_route_updated(event: Event) -> None:
    """M2：route 热切换 — 面板保存路由后 router reload 同步内存缓存。"""
    if state.model_router:
        await state.model_router.reload()
