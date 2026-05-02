"""话题订阅指令（风神域）：/subscribe 创建 + /subs list/rm/on/off/run 管理。

`create_subscription` 抽出来给 WebUI feed.py / tools/builtin/subscribe.py 共用，
保证命令路径和工具路径产生一致的订阅 + scheduled_task 双记录。
"""
from __future__ import annotations

from loguru import logger

from paimon.state import state

from ._dispatch import CommandContext, command


_DEFAULT_SUBSCRIBE_CRON = "0 7 * * *"   # 每天 7 点（按服务器本地时间；中国大陆即北京时间）
_MAX_SUBSCRIBE_QUERY_LEN = 200
_VALID_ENGINES = {"", "baidu", "bing"}


def _parse_subscribe_args(args: str) -> tuple[str, str, str] | str:
    """解析 /subscribe 参数。返回 (query, cron, engine) 或错误字符串。

    支持格式：
      "<query>"                         → cron=默认, engine=默认
      "<query> | <cron>"                → engine=默认
      "<query> | <cron> | <engine>"     → 全指定
    """
    if not args or not args.strip():
        return (
            "用法: /subscribe <关键词> [| <cron表达式>] [| <engine>]\n"
            "例: /subscribe Claude 4.7\n"
            "    /subscribe 小米 SU7 | 0 10 * * *\n"
            "    /subscribe 大模型 | */6 * * * * | bing\n"
            f"默认 cron: {_DEFAULT_SUBSCRIBE_CRON} (每日 7 点)\n"
            "engine 可选: baidu / bing / 留空=双引擎"
        )

    parts = [p.strip() for p in args.split("|")]
    query = parts[0].strip()
    cron = parts[1].strip() if len(parts) > 1 and parts[1].strip() else _DEFAULT_SUBSCRIBE_CRON
    engine = parts[2].strip().lower() if len(parts) > 2 else ""

    if not query:
        return "关键词不能为空"
    if len(query) > _MAX_SUBSCRIBE_QUERY_LEN:
        return f"关键词过长（{len(query)} 字），上限 {_MAX_SUBSCRIBE_QUERY_LEN}"
    if engine not in _VALID_ENGINES:
        return f"engine 必须是 baidu / bing / 留空，收到: {engine}"

    try:
        from croniter import croniter
        croniter(cron)
    except Exception as e:
        return f"cron 表达式无效 '{cron}': {e}"

    return query, cron, engine


async def create_subscription(
    *, query: str, cron: str, engine: str,
    channel_name: str, chat_id: str,
    supports_push: bool = True,
) -> tuple[bool, str]:
    """订阅创建的核心逻辑（命令 / WebUI 共用）。返回 (ok, message)。

    成功时 message 是"订阅已创建 #xxx ..."的用户回显文本；失败时是错误描述。
    """
    if not state.irminsul or not state.march:
        return False, "世界树 / 三月未就绪"

    query = (query or "").strip()
    cron = (cron or "").strip() or _DEFAULT_SUBSCRIBE_CRON
    engine = (engine or "").strip().lower()

    if not query:
        return False, "关键词不能为空"
    if len(query) > _MAX_SUBSCRIBE_QUERY_LEN:
        return False, f"关键词过长（{len(query)} 字），上限 {_MAX_SUBSCRIBE_QUERY_LEN}"
    if engine not in _VALID_ENGINES:
        return False, f"engine 必须是 baidu / bing / 留空，收到: {engine}"
    try:
        from croniter import croniter
        croniter(cron)
    except Exception as e:
        return False, f"cron 表达式无效 '{cron}': {e}"

    if not supports_push:
        return False, (
            f"当前频道 {channel_name} 不支持主动推送，无法订阅。\n"
            "订阅推送依赖推送能力，可改用 WebUI 或 Telegram 频道订阅。"
        )

    from paimon.foundation.irminsul.subscription import Subscription

    sub = Subscription(
        query=query,
        channel_name=channel_name,
        chat_id=chat_id,
        schedule_cron=cron,
        engine=engine,
        # /subscribe 命令永远建 manual 订阅；业务衍生订阅走 archon ensure_for
        binding_kind="manual",
        binding_id="",
    )
    sub_id = await state.irminsul.subscription_create(sub, actor="派蒙")

    try:
        task_id = await state.march.create_task(
            chat_id=chat_id,
            channel_name=channel_name,
            prompt="",  # 内部任务不需要 LLM prompt；UI 由 task_types.description_builder 实时构造
            trigger_type="cron",
            trigger_value={"expr": cron},
            task_type="feed_collect",
            source_entity_id=sub_id,
        )
    except Exception as e:
        await state.irminsul.subscription_delete(sub_id, actor="派蒙")
        return False, f"定时任务创建失败，订阅已回滚: {e}"

    await state.irminsul.subscription_update(
        sub_id, actor="派蒙", linked_task_id=task_id,
    )

    # 首次采集：创建即跑一次，免等 cron（复用手动「运行」按钮链路）
    # fire-and-forget：不阻塞 API 返回，失败落 last_error，空跑走占位公告
    if state.venti and sub.enabled:
        from paimon.foundation.bg import bg
        bg(state.venti.collect_subscription(
            sub_id,
            irminsul=state.irminsul,
            model=state.model,
            march=state.march,
        ), label=f"venti·订阅采集·{sub_id[:8]}·首次")

    task = await state.irminsul.schedule_get(task_id)
    import time as _time
    next_str = (
        _time.strftime("%Y-%m-%d %H:%M", _time.localtime(task.next_run_at))
        if task and task.next_run_at > 0 else "-"
    )
    engine_label = engine or "双引擎"
    message = (
        f"订阅已创建 #{sub_id[:8]}（已启动首次采集）\n"
        f"  关键词: {query}\n"
        f"  周期: {cron}\n"
        f"  引擎: {engine_label}\n"
        f"  下次运行: {next_str}\n"
        f"可用 /subs list 查看全部，/subs rm {sub_id[:8]} 删除"
    )
    return True, message


@command("subscribe")
async def cmd_subscribe(ctx: CommandContext) -> str:
    """创建话题订阅。

    /subscribe <关键词> [| <cron>] [| <engine>]

    风神会按 cron 定时调 web-search 采集，过滤已见 URL 后交 LLM 写日报，
    推送给当前频道。
    """
    parsed = _parse_subscribe_args(ctx.args)
    if isinstance(parsed, str):
        return parsed
    query, cron, engine = parsed

    ok, msg = await create_subscription(
        query=query, cron=cron, engine=engine,
        channel_name=ctx.msg.channel_name,
        chat_id=ctx.msg.chat_id,
        supports_push=getattr(ctx.channel, "supports_push", True),
    )
    return msg


async def _resolve_subscription(prefix: str):
    """按 id 前缀解析订阅，要求精确 12 字 id 或唯一前缀。"""
    if not state.irminsul:
        return None, "世界树未就绪"
    prefix = prefix.strip()
    if not prefix:
        return None, "缺少订阅 ID"
    sub = await state.irminsul.subscription_get(prefix)
    if sub:
        return sub, ""
    # 前缀匹配
    all_subs = await state.irminsul.subscription_list()
    matches = [s for s in all_subs if s.id.startswith(prefix)]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        return None, f"前缀 '{prefix}' 匹配到 {len(matches)} 个订阅，请输入更长 ID"
    return None, f"未找到订阅: {prefix}"


@command("subs")
async def cmd_subs(ctx: CommandContext) -> str:
    """订阅管理：
      /subs list                 列全部订阅
      /subs rm <id>              删订阅（级联清 feed_items + scheduled_tasks）
      /subs on <id>              启用
      /subs off <id>             停用
      /subs run <id>             手动触发一次采集（立即执行，便于验证）
    """
    if not state.irminsul:
        return "世界树未就绪"

    args = ctx.args.strip()
    if not args:
        return cmd_subs.__doc__ or "用法: /subs list | rm <id> | on <id> | off <id> | run <id>"

    parts = args.split(maxsplit=1)
    action = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if action == "list":
        subs = await state.irminsul.subscription_list()
        if not subs:
            return "暂无订阅。用 /subscribe <关键词> 创建"
        import time as _time
        lines = ["订阅列表:"]
        for s in subs:
            status = "启用" if s.enabled else "停用"
            last_run = (
                _time.strftime("%m-%d %H:%M", _time.localtime(s.last_run_at))
                if s.last_run_at > 0 else "-"
            )
            count = await state.irminsul.feed_items_count(sub_id=s.id)
            err = f" [错: {s.last_error[:30]}]" if s.last_error else ""
            lines.append(
                f"  #{s.id[:8]} | {status} | {s.query[:30]} | "
                f"{s.schedule_cron} | 累计 {count} 条 | 上次 {last_run}{err}"
            )
        return "\n".join(lines)

    if action == "rm":
        sub, err = await _resolve_subscription(rest)
        if not sub:
            return err
        # 同步删 scheduled_task
        if sub.linked_task_id and state.march:
            try:
                await state.march.delete_task(sub.linked_task_id)
            except Exception as e:
                logger.warning("[派蒙·订阅] 删定时任务失败 {}: {}", sub.linked_task_id, e)
        ok = await state.irminsul.subscription_delete(sub.id, actor="派蒙")
        return f"已删除订阅 #{sub.id[:8]} ({sub.query})" if ok else "删除失败"

    if action in ("on", "off"):
        sub, err = await _resolve_subscription(rest)
        if not sub:
            return err
        enable = action == "on"
        await state.irminsul.subscription_update(
            sub.id, actor="派蒙", enabled=enable,
        )
        # 同步 scheduled_task 启停
        if sub.linked_task_id and state.march:
            try:
                if enable:
                    await state.march.resume_task(sub.linked_task_id)
                else:
                    await state.march.pause_task(sub.linked_task_id)
            except Exception as e:
                logger.warning("[派蒙·订阅] 同步定时任务启停失败: {}", e)
        return f"订阅 #{sub.id[:8]} 已{'启用' if enable else '停用'}"

    if action == "run":
        sub, err = await _resolve_subscription(rest)
        if not sub:
            return err
        if not state.venti:
            return "风神未初始化"
        # 后台异步跑，不阻塞指令返回
        from paimon.foundation.bg import bg
        bg(state.venti.collect_subscription(
            sub.id, irminsul=state.irminsul, model=state.model, march=state.march,
        ), label=f"venti·订阅采集·{sub.id[:8]}·手动")
        return f"已手动触发采集 #{sub.id[:8]} ({sub.query})，稍后查看推送"

    return f"未知子命令: {action}。可用: list / rm / on / off / run"
