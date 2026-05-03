"""神之心 LLM Profile 面板 API — Profile CRUD + 路由 + 测试探针。"""
from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def llm_page(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.Response(text=channel._get_login_html(), content_type="text/html")
    from paimon.channels.webui.llm_html import build_llm_html
    return web.Response(
        text=build_llm_html(),
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def llm_list_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"profiles": []})
    profiles = await irminsul.llm_profile_list(include_keys=False)
    return web.json_response({
        "profiles": [_llm_profile_to_json(p) for p in profiles],
    })


async def llm_create_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
    try:
        data = await request.json()
        profile = _llm_json_to_profile(data)
        if not profile.name or not profile.model or not profile.base_url:
            return web.json_response(
                {"ok": False, "error": "name / model / base_url 必填"}, status=400,
            )
        profile_id = await irminsul.llm_profile_create(profile, actor="WebUI")
        await _llm_publish_profile_event(channel, profile_id, "create")
        return web.json_response({"ok": True, "id": profile_id})
    except Exception as e:
        logger.error("[神之心·LLM 面板] 创建 profile 异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def llm_update_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
    profile_id = request.match_info["profile_id"]
    try:
        data = await request.json()
        fields = _llm_json_to_update_fields(data)
        ok = await irminsul.llm_profile_update(profile_id, actor="WebUI", **fields)
        if ok:
            await _llm_publish_profile_event(channel, profile_id, "update")
        return web.json_response({"ok": ok})
    except Exception as e:
        logger.error("[神之心·LLM 面板] 更新 {} 异常: {}", profile_id, e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def llm_delete_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    # USB-007 破坏性操作 server-side 确认
    from paimon.channels.webui.api import check_confirm, confirm_required_response
    if not check_confirm(request):
        return confirm_required_response()
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
    profile_id = request.match_info["profile_id"]
    try:
        ok = await irminsul.llm_profile_delete(profile_id, actor="WebUI")
        if ok:
            await _llm_publish_profile_event(channel, profile_id, "delete")
        return web.json_response({"ok": ok})
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    except Exception as e:
        logger.error("[神之心·LLM 面板] 删除 {} 异常: {}", profile_id, e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def llm_set_default_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
    profile_id = request.match_info["profile_id"]
    try:
        ok = await irminsul.llm_profile_set_default(profile_id, actor="WebUI")
        if ok:
            await _llm_publish_profile_event(channel, profile_id, "set_default")
        return web.json_response({"ok": ok})
    except Exception as e:
        logger.error("[神之心·LLM 面板] 设默认 {} 异常: {}", profile_id, e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def llm_test_api(channel, request: web.Request) -> web.Response:
    """编辑/新增表单里的「测试连接」：用前端提交的字段临时构造 client 冒烟。"""
    if not channel._check_auth(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    try:
        data = await request.json()
        # 如果 api_key 是掩码占位，回退到已存的那条 profile
        if data.get("api_key") == "***" and data.get("id"):
            stored = await channel.state.irminsul.llm_profile_get(
                data["id"], include_key=True,
            )
            if stored:
                data["api_key"] = stored.api_key
        return await _llm_probe_ping(data)
    except Exception as e:
        logger.error("[神之心·LLM 面板] 测试连接异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)})


async def llm_test_existing_api(channel, request: web.Request) -> web.Response:
    """列表里已有 profile 的「测连接」：从世界树取完整 profile（含 key）冒烟。"""
    if not channel._check_auth(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
    profile_id = request.match_info["profile_id"]
    profile = await irminsul.llm_profile_get(profile_id, include_key=True)
    if not profile:
        return web.json_response({"ok": False, "error": "profile 不存在"}, status=404)
    return await _llm_probe_ping({
        "provider_kind": profile.provider_kind,
        "api_key": profile.api_key,
        "base_url": profile.base_url,
        "model": profile.model,
        "max_tokens": profile.max_tokens,
        "reasoning_effort": profile.reasoning_effort,
        "extra_body": profile.extra_body or {},
    })


async def llm_routes_list_api(channel, request: web.Request) -> web.Response:
    """列路由表 + 已知调用点 + 默认 profile 名 + 最近命中快照（面板用）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    router = channel.state.model_router
    if not irminsul or not router:
        return web.json_response({
            "routes": {}, "callsites": [], "default": None, "hits": {},
        })
    # 已配路由快照（用 router 内存版，免打 DB）
    routes = router.snapshot()
    hits = router.get_hits()  # {route_key: {profile_id, model_name, provider_source, timestamp}}
    from paimon.foundation.model_router import KNOWN_CALLSITES
    default = await irminsul.llm_profile_get_default()
    # skills：天使段下纯展示用；当前 architecture skill 不直接调 LLM，故面板 disabled
    skills_list: list[dict] = []
    try:
        decls = await irminsul.skill_list(include_orphaned=False)
        skills_list = [
            {"name": s.name, "description": (s.description or "")[:100]}
            for s in decls
        ]
    except Exception as e:
        logger.debug("[神之心·LLM 面板] skill_list 失败: {}", e)
    return web.json_response({
        "routes": routes,
        "callsites": [
            {"component": c, "purpose": p} for c, p in KNOWN_CALLSITES
        ],
        "default": (
            {"id": default.id, "name": default.name} if default else None
        ),
        "hits": hits,
        "skills": skills_list,
    })


async def llm_route_set_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    if not channel.state.model_router or not channel.state.irminsul:
        return web.json_response(
            {"ok": False, "error": "路由器/世界树未就绪"}, status=500,
        )
    try:
        data = await request.json()
        route_key = (data.get("route_key") or "").strip()
        profile_id = (data.get("profile_id") or "").strip()
        if not route_key or not profile_id:
            return web.json_response(
                {"ok": False, "error": "route_key / profile_id 必填"},
                status=400,
            )
        # 校验 profile_id 存在，避免写入悬挂引用
        profile = await channel.state.irminsul.llm_profile_get(
            profile_id, include_key=False,
        )
        if profile is None:
            return web.json_response(
                {"ok": False, "error": f"profile 不存在: {profile_id}"},
                status=400,
            )
        await channel.state.model_router.set_route(
            route_key, profile_id, actor="WebUI",
        )
        await _llm_publish_route_event(channel, route_key)
        return web.json_response({"ok": True})
    except Exception as e:
        logger.error("[神之心·LLM 面板] 设路由异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def llm_route_delete_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    # USB-007 破坏性操作 server-side 确认
    from paimon.channels.webui.api import check_confirm, confirm_required_response
    if not check_confirm(request):
        return confirm_required_response()
    if not channel.state.model_router:
        return web.json_response(
            {"ok": False, "error": "路由器未就绪"}, status=500,
        )
    try:
        data = await request.json()
        route_key = (data.get("route_key") or "").strip()
        if not route_key:
            return web.json_response(
                {"ok": False, "error": "route_key 必填"}, status=400,
            )
        ok = await channel.state.model_router.delete_route(
            route_key, actor="WebUI",
        )
        if ok:
            await _llm_publish_route_event(channel, route_key)
        return web.json_response({"ok": ok})
    except Exception as e:
        logger.error("[神之心·LLM 面板] 删路由异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def llm_route_cascade_clear_api(channel, request: web.Request,
) -> web.Response:
    """清空 component 下所有 purpose 级路由（让它们全继承组级）。"""
    if not channel._check_auth(request):
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    if not channel.state.model_router:
        return web.json_response(
            {"ok": False, "error": "路由器未就绪"}, status=500,
        )
    try:
        data = await request.json()
        component = (data.get("component") or "").strip()
        if not component:
            return web.json_response(
                {"ok": False, "error": "component 必填"}, status=400,
            )
        keys = await channel.state.model_router.cascade_clear_purposes(
            component, actor="WebUI",
        )
        for k in keys:
            await _llm_publish_route_event(channel, k)
        return web.json_response(
            {"ok": True, "cleared": keys, "count": len(keys)},
        )
    except Exception as e:
        logger.error("[神之心·LLM 面板] cascade-clear 异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def _llm_probe_ping(data: dict) -> web.Response:
    """按 provider_kind 临时构造 client 发一条 ping，10s 超时。"""
    import asyncio
    import time as _time
    kind = (data.get("provider_kind") or "openai").strip().lower()
    api_key = (data.get("api_key") or "").strip()
    base_url = (data.get("base_url") or "").strip()
    model = (data.get("model") or "").strip()
    if not api_key or not base_url or not model:
        return web.json_response(
            {"ok": False, "error": "api_key / base_url / model 必填"},
        )
    t0 = _time.time()
    try:
        if kind == "anthropic":
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=api_key, base_url=base_url)
            resp = await asyncio.wait_for(
                client.messages.create(
                    model=model, max_tokens=10,
                    messages=[{"role": "user", "content": "ping"}],
                ),
                timeout=10.0,
            )
            # Anthropic 返回 resp.content[0].text
            sample = ""
            if resp.content:
                block = resp.content[0]
                sample = getattr(block, "text", "") or ""
        else:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            kwargs: dict = {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 10,
            }
            eff = (data.get("reasoning_effort") or "").strip()
            if eff:
                kwargs["reasoning_effort"] = eff
            eb = data.get("extra_body") or {}
            if eb:
                kwargs["extra_body"] = eb
            resp = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=10.0,
            )
            sample = resp.choices[0].message.content or ""
        latency_ms = int((_time.time() - t0) * 1000)
        return web.json_response({
            "ok": True,
            "latency_ms": latency_ms,
            "sample": (sample or "")[:120],
        })
    except asyncio.TimeoutError:
        return web.json_response({"ok": False, "error": "请求超时（>10s）"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)[:500]})


def _llm_profile_to_json(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "provider_kind": p.provider_kind,
        "api_key": p.api_key,   # 已在 repo 层做掩码
        "base_url": p.base_url,
        "model": p.model,
        "max_tokens": p.max_tokens,
        "reasoning_effort": p.reasoning_effort,
        "extra_body": p.extra_body or {},
        "is_default": p.is_default,
        "notes": p.notes,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _llm_json_to_profile(data: dict):
    """前端 JSON → LLMProfile（用于 create）。"""
    from paimon.foundation.irminsul.llm_profile import LLMProfile
    eb = data.get("extra_body") or {}
    if not isinstance(eb, dict):
        eb = {}
    return LLMProfile(
        name=(data.get("name") or "").strip(),
        provider_kind=(data.get("provider_kind") or "openai").strip(),
        api_key=(data.get("api_key") or "").strip(),
        base_url=(data.get("base_url") or "").strip(),
        model=(data.get("model") or "").strip(),
        max_tokens=int(data.get("max_tokens") or 64000),
        reasoning_effort=(data.get("reasoning_effort") or "").strip(),
        extra_body=eb,
        notes=(data.get("notes") or "").strip(),
    )


def _llm_json_to_update_fields(data: dict) -> dict:
    """前端 JSON → update fields。api_key='***' 表示保留不动。"""
    fields: dict = {}
    for key in ("name", "provider_kind", "base_url", "model",
                "reasoning_effort", "notes"):
        if key in data:
            fields[key] = (data.get(key) or "").strip()
    if "api_key" in data:
        fields["api_key"] = data.get("api_key") or ""  # "***" 由 repo 层识别
    if "max_tokens" in data:
        fields["max_tokens"] = int(data.get("max_tokens") or 64000)
    if "extra_body" in data:
        eb = data.get("extra_body") or {}
        fields["extra_body"] = eb if isinstance(eb, dict) else {}
    return fields


async def _llm_publish_profile_event(channel, profile_id: str, action: str,
) -> None:
    """Profile 写入后 publish leyline，供 Gnosis 失效缓存。"""
    if not channel.state.leyline:
        return
    try:
        await channel.state.leyline.publish(
            "llm.profile.updated",
            {"profile_id": profile_id, "action": action},
            source="WebUI·LLM面板",
        )
    except Exception as e:
        logger.debug("[神之心·LLM 面板] publish profile event 失败: {}", e)


async def _llm_publish_route_event(channel, route_key: str) -> None:
    if not channel.state.leyline:
        return
    try:
        await channel.state.leyline.publish(
            "llm.route.updated",
            {"route_key": route_key},
            source="WebUI·LLM面板",
        )
    except Exception as e:
        logger.debug("[神之心·LLM 面板] publish route event 失败: {}", e)


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 llm 面板的 12 个路由。"""
    app.router.add_get("/llm", lambda r, ch=channel: llm_page(ch, r))
    app.router.add_get("/api/llm/list", lambda r, ch=channel: llm_list_api(ch, r))
    app.router.add_post("/api/llm/create", lambda r, ch=channel: llm_create_api(ch, r))
    app.router.add_post("/api/llm/test", lambda r, ch=channel: llm_test_api(ch, r))
    app.router.add_post("/api/llm/{profile_id}/update", lambda r, ch=channel: llm_update_api(ch, r))
    app.router.add_post("/api/llm/{profile_id}/delete", lambda r, ch=channel: llm_delete_api(ch, r))
    app.router.add_post("/api/llm/{profile_id}/set-default", lambda r, ch=channel: llm_set_default_api(ch, r))
    app.router.add_post("/api/llm/{profile_id}/test", lambda r, ch=channel: llm_test_existing_api(ch, r))
    app.router.add_get("/api/llm/routes", lambda r, ch=channel: llm_routes_list_api(ch, r))
    app.router.add_post("/api/llm/routes/set", lambda r, ch=channel: llm_route_set_api(ch, r))
    app.router.add_post("/api/llm/routes/delete", lambda r, ch=channel: llm_route_delete_api(ch, r))
    app.router.add_post("/api/llm/routes/cascade-clear", lambda r, ch=channel: llm_route_cascade_clear_api(ch, r))
