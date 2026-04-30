"""米游社业务函数 —— 抄自 gsuid_core 但改成无状态函数式。

所有函数接受 Cookie/Fp/DeviceId 作参数，返回 dict / 业务数据。
paimon 水神负责读写世界树，skill 只做 I/O。
"""
from __future__ import annotations

import asyncio
import copy
import json
import random
import uuid
from typing import Any
from urllib.parse import urlparse, parse_qs

import httpx

from . import api, device, server, sign


_DEAD_CODES = (10035, 5003, 10041, 1034)

# 游戏 → challenge header 的 3 个字段。抄自 gsuid_core/utils/api/mys/base_request.py
# 米游社 retcode=10035/5003/10041/1034 表示需要"人机验证"，带上这 3 个 header
# 表示"客户端已完成验证"假装过关。对未配置打码平台的场景也常能放行。
_CHALLENGE_HEADERS = {
    "gs":  {"x-rpc-challenge_game": "2", "x-rpc-page": "v4.1.5-ys_#ys",    "x-rpc-tool-verison": "v4.1.5-ys"},
    "sr":  {"x-rpc-challenge_game": "6", "x-rpc-page": "v1.4.1-rpg_#/rpg", "x-rpc-tool-verison": "v1.4.1-rpg"},
    "zzz": {"x-rpc-challenge_game": "8", "x-rpc-page": "v1.1.0-zzz_#/zzz", "x-rpc-tool-verison": "v1.1.0-zzz"},
}


async def _mys_get(
    client: httpx.AsyncClient, url: str, params: dict, headers: dict,
    *, game: str, ctx: str, resign_ds: bool = True,
) -> dict[str, Any]:
    """GET 并处理 _DEAD_CODE 重试：命中时加 challenge header，重签 DS，再试一次。"""
    resp = await client.get(url, params=params, headers=headers)
    data = _parse_json_safe(resp, ctx=ctx)
    if data.get("retcode") not in _DEAD_CODES:
        return data
    # 命中风控：加 challenge header、重签 DS、再试
    new_headers = copy.deepcopy(headers)
    new_headers.update(_CHALLENGE_HEADERS.get(game, {}))
    if resign_ds and "DS" in new_headers:
        q = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        new_headers["DS"] = sign.get_ds_token(q)
    import sys as _sys
    print(f"[skill·mihoyo] {ctx} 命中 _DEAD_CODE={data.get('retcode')}, 加 challenge header 重试",
          file=_sys.stderr)
    resp2 = await client.get(url, params=params, headers=new_headers)
    return _parse_json_safe(resp2, ctx=ctx + " retry")


def _parse_json_safe(resp: httpx.Response, ctx: str = "") -> dict[str, Any]:
    """米游社偶尔返回非 JSON（null 加垃圾 / 空 body / HTML 错误页）——
    解析失败时 stderr 打 response 片段便于定位，返回 retcode=-9999 形式的错误 dict。
    """
    import sys
    text = resp.text
    if not text:
        print(f"[skill·mihoyo] {ctx} 空响应 status={resp.status_code}", file=sys.stderr)
        return {"retcode": -9999, "message": "empty response", "data": None}
    # 米游社某些接口未解锁/权限不足时会返 `null` + 控制字符（\0 等）
    # 先做字符清洗
    stripped = text.strip().rstrip("\0").rstrip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as e:
        # 打前 300 字符定位问题
        snippet = stripped[:300].replace("\0", "\\0").replace("\n", "\\n")
        print(f"[skill·mihoyo] {ctx} JSON 解析失败 err={e} body[:300]='{snippet}'",
              file=sys.stderr)
        return {"retcode": -9999, "message": f"json parse failed: {e}", "data": None,
                "_raw_snippet": snippet}

# ============================================================
# QR 扫码登录
# ============================================================


async def qr_create() -> dict[str, Any]:
    """创建扫码登录二维码。返回 {ticket, device, url}，url 给用户扫。"""
    device_id = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=64))
    body = {"app_id": "2", "device": device_id}
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.post(api.URL_CREATE_QRCODE, json=body)
        data = resp.json()
    if data.get("retcode") != 0:
        raise RuntimeError(f"创建 QR 失败: {data}")
    url = data["data"]["url"]
    ticket = url.split("ticket=")[1]
    return {"app_id": "2", "ticket": ticket, "device": device_id, "url": url}


async def qr_poll(app_id: str, ticket: str, device_id: str) -> dict[str, Any]:
    """轮询扫码状态。返回 {stat, payload?, game_token?, uid?}。

    stat ∈ 'Init'（未扫）/'Scanned'（已扫未确认）/'Confirmed'（已确认 → 拿到 game_token）。
    """
    body = {"app_id": app_id, "ticket": ticket, "device": device_id}
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.post(api.URL_CHECK_QRCODE, json=body)
        data = resp.json()
    if data.get("retcode") != 0:
        return {"stat": "Error", "msg": str(data)}
    d = data["data"]
    stat = d.get("stat", "Init")
    out: dict[str, Any] = {"stat": stat}
    if stat == "Confirmed":
        # payload.raw 是 JSON 字符串 {uid, token}
        import json as _json
        raw = _json.loads(d["payload"]["raw"])
        out["uid"] = raw["uid"]
        out["game_token"] = raw["token"]
    return out


async def stoken_by_game_token(account_id: str, game_token: str) -> dict[str, Any]:
    """GameToken → Stoken（Stoken 是续命 key，用它可以反复换 Cookie）。"""
    body = {"account_id": int(account_id), "game_token": game_token}
    headers = {
        "x-rpc-app_version": "2.41.0",
        "DS": sign.generate_passport_ds(b=body),
        "x-rpc-aigis": "",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-rpc-game_biz": "bbs_cn",
        "x-rpc-sys_version": "11",
        "x-rpc-device_id": uuid.uuid4().hex,
        "x-rpc-device_fp": sign.random_hex(13).lower(),
        "x-rpc-device_name": "paimon_login_device",
        "x-rpc-device_model": "paimon_login_device",
        "x-rpc-app_id": "bll8iq97cem8",
        "x-rpc-client_type": "2",
        "User-Agent": "okhttp/4.8.0",
    }
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.post(api.URL_STOKEN_BY_GAMETOKEN, json=body, headers=headers)
        data = resp.json()
    if data.get("retcode") != 0:
        raise RuntimeError(f"Stoken 获取失败: {data}")
    return data["data"]  # {token:{token}, user_info:{aid, mid, ...}}


async def device_login(
    device_id: str, fp: str, device_info: str, app_cookie: str,
) -> dict[str, Any]:
    """设备注册 —— 抄自 gsuid_core base_request.device_login_and_save。

    扫码绑定后第一次用 app cookie 请求 game_record 接口前必须调这个，否则米游社
    把新 device_id+fp 当陌生设备拒掉，崩铁 note 接口会直接返 retcode=10035。
    app_cookie 格式 `stuid=xxx;stoken=xxx;mid=xxx`。
    """
    info_parts = device_info.split("/")
    brand = info_parts[0] if info_parts else "OnePlus"
    model = info_parts[1] if len(info_parts) > 1 else "PHK110"
    body = {
        "app_version": sign.MYS_VERSION,
        "device_id": device_id,
        "device_name": f"{brand}{model}",
        "os_version": "33",
        "platform": "Android",
        "registration_id": "".join(random.choices("0123456789abcdef", k=19)),
    }
    headers = copy.deepcopy(device._HEADER_APP)
    headers["x-rpc-device_id"] = device_id
    headers["x-rpc-device_fp"] = fp
    headers["x-rpc-device_name"] = f"{brand} {model}"
    headers["x-rpc-device_model"] = model
    headers["x-rpc-csm_source"] = "myself"
    headers["Referer"] = "https://app.mihoyo.com"
    headers["Host"] = "bbs-api.miyoushe.com"
    headers["DS"] = sign.generate_passport_ds("", body)
    headers["Cookie"] = app_cookie

    results: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=30.0) as c:
        for name, url in (("device_login", api.URL_DEVICE_LOGIN),
                          ("save_device", api.URL_SAVE_DEVICE)):
            try:
                resp = await c.post(url, json=body, headers=headers)
                results[name] = _parse_json_safe(resp, ctx=f"{name} device={device_id}")
            except Exception as e:
                results[name] = {"retcode": -9999, "message": f"{type(e).__name__}: {e}"}
    return results


async def cookie_by_stoken(stoken: str, mys_id: str, mid: str) -> str:
    """Stoken + mid → web Cookie（用于签到 / 便笺 / 玩家卡片 等）。

    对齐 gsuid_core/utils/cookie_manager/qrlogin.py 的流程：
    扫码拿到 game_token 后，先调 stoken-exchange 拿 {token, mid}，
    再调本函数（用 stoken + mid 组的 app_cookie 头）拿 cookie_token。
    米游社 2024 年之后废弃了 `getCookieAccountInfoByGameToken`（retcode=-5300），
    **必须走 stoken 路径**。

    返回的 Cookie 字符串包含米游社 app/web 两端都兼容的字段。
    """
    import copy as _copy
    app_cookie = f"stuid={mys_id};stoken={stoken};mid={mid}"
    headers = _copy.deepcopy(device._HEADER_APP)
    headers["Cookie"] = app_cookie
    params = {"stoken": stoken, "uid": mys_id}
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.get(api.URL_COOKIE_BY_STOKEN, params=params, headers=headers)
        data = resp.json()
    if data.get("retcode") != 0:
        raise RuntimeError(f"Cookie 获取失败: {data}")
    ctk = data["data"]["cookie_token"]
    aid = data["data"].get("uid", mys_id)
    # app 签到接口要 stoken_v2 + mid + stuid；web 接口要 cookie_token + ltoken_v2；
    # 一把梭都塞进去就不会各端分别请求失败。
    return (
        f"stoken_v2={stoken};stuid={aid};mid={mid};"
        f"cookie_token={ctk};cookie_token_v2={ctk};"
        f"ltoken_v2={stoken};ltuid_v2={aid};"
        f"account_id={aid};account_id_v2={aid}"
    )


async def game_record_card(
    mys_id: str, cookie: str, *,
    fp: str | None = None, device_id: str | None = None,
    is_os: bool = False,
) -> dict[str, Any]:
    """用 mys_id + Cookie 查米游社账号下所有游戏 UID（原神/星铁/绝区零）。

    返回 {list: [{game_id, game_role_id, region, ...}]}。game_id：
    2 = 原神, 6 = 星穹铁道, 8 = 绝区零。

    fp/device_id 非必须但**强烈建议**给：上游 gsuid_core._mys_request 里对带 uid 的请求
    自动补 x-rpc-device_fp/device_id，不补容易被风控。扫码绑定场景要先 gen-fp 再传进来。
    """
    url = api.URL_MYS_GAME_RECORD_OS if is_os else api.URL_MYS_GAME_RECORD
    params = {"uid": mys_id}
    q = f"uid={mys_id}"
    ds = sign.generate_os_ds() if is_os else sign.get_ds_token(q)
    if fp and device_id:
        headers = device.build_headers(cookie, device_id, fp, ds=ds)
    else:
        # 兜底（没 fp）：用最小 header，风险码 10035 可能触发
        import copy as _copy
        headers = _copy.deepcopy(device._HEADER_APP)
        headers["Cookie"] = cookie
        headers["DS"] = ds
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.get(url, params=params, headers=headers)
        return resp.json()


async def refresh_cookie_by_stoken(stoken: str, mys_id: str) -> str:
    """Cookie 失效时用 Stoken 重新换一次。"""
    headers = copy.deepcopy(device._HEADER_APP)
    headers["Cookie"] = f"stuid={mys_id};stoken={stoken}"
    params = {"stoken": stoken, "uid": mys_id}
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.get(api.URL_COOKIE_BY_STOKEN, params=params, headers=headers)
        data = resp.json()
    if data.get("retcode") != 0:
        raise RuntimeError(f"Cookie 重刷失败: {data}")
    ctok = data["data"]["cookie_token"]
    return f"ltuid={mys_id};ltoken_v2={ctok};cookie_token_v2={ctok};account_id_v2={mys_id}"


# ============================================================
# 便笺（树脂 / 派遣 / 每日委托 / 参量质变仪）—— 原神
# ============================================================


async def daily_note(uid: str, cookie: str, fp: str, device_id: str) -> dict[str, Any]:
    """原神每日便笺。返回米游社原结构，水神自己挑字段。"""
    _is_os = server.is_os(uid, "gs")
    server_id = server.get_server_id(uid, "gs")
    url = api.URL_DAILY_NOTE_GS_OS if _is_os else api.URL_DAILY_NOTE_GS
    params = {"role_id": uid, "server": server_id}
    q = f"role_id={uid}&server={server_id}"
    ds = sign.generate_os_ds() if _is_os else sign.get_ds_token(q)
    headers = device.build_headers(cookie, device_id, fp, ds=ds)
    async with httpx.AsyncClient(timeout=30.0) as c:
        return await _mys_get(c, url, params, headers, game="gs", ctx=f"gs-note uid={uid}")


# ============================================================
# 深境螺旋 / 幻想真境剧诗 —— 原神
# ============================================================


async def spiral_abyss(
    uid: str, cookie: str, fp: str, device_id: str, *, schedule: int = 1
) -> dict[str, Any]:
    """深渊。schedule=1 本期 / 2 上期。"""
    _is_os = server.is_os(uid, "gs")
    server_id = server.get_server_id(uid, "gs")
    url = api.URL_SPIRAL_ABYSS_OS if _is_os else api.URL_SPIRAL_ABYSS
    params = {"role_id": uid, "server": server_id, "schedule_type": schedule}
    q = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    ds = sign.generate_os_ds() if _is_os else sign.get_ds_token(q)
    headers = device.build_headers(cookie, device_id, fp, ds=ds)
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.get(url, params=params, headers=headers)
        return resp.json()


async def poetry_abyss(uid: str, cookie: str, fp: str, device_id: str) -> dict[str, Any]:
    """幻想真境剧诗。国服独占。"""
    server_id = server.get_server_id(uid, "gs")
    params = {"role_id": uid, "server": server_id, "need_detail": "true"}
    q = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    ds = sign.get_ds_token(q)
    headers = device.build_headers(cookie, device_id, fp, ds=ds)
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.get(api.URL_POETRY_ABYSS, params=params, headers=headers)
        return resp.json()


async def gs_character_list(
    uid: str, cookie: str, fp: str, device_id: str,
    character_ids: list[int] | None = None,
) -> dict[str, Any]:
    """原神角色列表 + 详情。POST `/character/list`，body 签名 DS。

    character_ids 空 list 默认拿全部；想只查某几个传具体 ID 列表。
    返回 `{avatars: [{id, name, level, rarity, element, actived_constellation_num, weapon, reliquaries, image, ...}]}`。
    """
    _is_os = server.is_os(uid, "gs")
    server_id = server.get_server_id(uid, "gs")
    url = api.URL_PLAYER_DETAIL_INFO_GS_OS if _is_os else api.URL_PLAYER_DETAIL_INFO_GS
    body = {
        "character_ids": list(character_ids or []),
        "role_id": uid,
        "server": server_id,
    }
    ds = sign.generate_os_ds() if _is_os else sign.get_ds_token("", body)
    headers = device.build_headers(cookie, device_id, fp, ds=ds)

    async with httpx.AsyncClient(timeout=60.0) as c:
        resp = await c.post(url, json=body, headers=headers)
        data = _parse_json_safe(resp, ctx=f"gs-characters uid={uid}")
    # 若命中风控，加 challenge 重试（米游社"角色接口"对风控非常敏感）
    if data.get("retcode") in _DEAD_CODES:
        import sys as _sys
        print(f"[skill·mihoyo] gs-characters 命中风控 rc={data.get('retcode')}，重试", file=_sys.stderr)
        extra_headers = dict(headers)
        extra_headers.update(_CHALLENGE_HEADERS["gs"])
        extra_headers["DS"] = sign.get_ds_token("", body)
        async with httpx.AsyncClient(timeout=60.0) as c:
            resp = await c.post(url, json=body, headers=extra_headers)
            data = _parse_json_safe(resp, ctx=f"gs-characters retry uid={uid}")
    return data


async def hard_challenge(uid: str, cookie: str, fp: str, device_id: str) -> dict[str, Any]:
    """幽境危战（Stygian Onslaught）。原神 5.6+ 新增副本，用户俗称"璃月深渊"。

    接口行为和 role_combat 相似：返回 `{data: {data: [期数], is_unlock, links}}`。
    每期含 `schedule`/`single.best.difficulty/second`/`single.challenge[]`。
    """
    _is_os = server.is_os(uid, "gs")
    server_id = server.get_server_id(uid, "gs")
    url = api.URL_HARD_CHALLENGE_OS if _is_os else api.URL_HARD_CHALLENGE
    params = {"role_id": uid, "server": server_id, "need_detail": "true"}
    q = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    ds = sign.generate_os_ds() if _is_os else sign.get_ds_token(q)
    headers = device.build_headers(cookie, device_id, fp, ds=ds)
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.get(url, params=params, headers=headers)
        return resp.json()


# ============================================================
# 崩坏星穹铁道
# ============================================================


async def sr_daily_note(uid: str, cookie: str, fp: str, device_id: str) -> dict[str, Any]:
    """崩铁便笺：开拓力 / 每日实训 / 委托派遣。"""
    _is_os = server.is_os(uid, "sr")
    server_id = server.get_server_id(uid, "sr")
    url = api.URL_DAILY_NOTE_SR_OS if _is_os else api.URL_DAILY_NOTE_SR
    params = {"role_id": uid, "server": server_id}
    q = f"role_id={uid}&server={server_id}"
    ds = sign.generate_os_ds() if _is_os else sign.get_ds_token(q)
    headers = device.build_headers(cookie, device_id, fp, ds=ds)
    async with httpx.AsyncClient(timeout=30.0) as c:
        return await _mys_get(c, url, params, headers, game="sr", ctx=f"sr-note uid={uid}")


async def _sr_challenge_generic(
    url: str, uid: str, cookie: str, fp: str, device_id: str,
    schedule: int, ctx_label: str,
) -> dict[str, Any]:
    """崩铁三深渊共用的请求模板（URL 不同、参数一致）。"""
    _is_os = server.is_os(uid, "sr")
    server_id = server.get_server_id(uid, "sr")
    params = {
        "role_id": uid, "server": server_id,
        "schedule_type": schedule, "need_all": "true",
    }
    if not _is_os:
        params["isPrev"] = "true"
    q = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    ds = sign.generate_os_ds() if _is_os else sign.get_ds_token(q)
    headers = device.build_headers(cookie, device_id, fp, ds=ds)
    async with httpx.AsyncClient(timeout=30.0) as c:
        return await _mys_get(c, url, params, headers, game="sr",
                              ctx=f"{ctx_label} uid={uid}")


async def sr_forgotten_hall(
    uid: str, cookie: str, fp: str, device_id: str, *, schedule: int = 1,
) -> dict[str, Any]:
    """忘却之庭。"""
    _is_os = server.is_os(uid, "sr")
    url = api.URL_SR_FORGOTTEN_HALL_OS if _is_os else api.URL_SR_FORGOTTEN_HALL
    return await _sr_challenge_generic(url, uid, cookie, fp, device_id, schedule, "sr-fh")


async def sr_pure_fiction(
    uid: str, cookie: str, fp: str, device_id: str, *, schedule: int = 1,
) -> dict[str, Any]:
    """虚构叙事。"""
    return await _sr_challenge_generic(
        api.URL_SR_PURE_FICTION, uid, cookie, fp, device_id, schedule, "sr-pf",
    )


async def sr_apocalyptic(
    uid: str, cookie: str, fp: str, device_id: str, *, schedule: int = 1,
) -> dict[str, Any]:
    """末日幻影。"""
    return await _sr_challenge_generic(
        api.URL_SR_APOCALYPTIC, uid, cookie, fp, device_id, schedule, "sr-apc",
    )


# ============================================================
# 绝区零
# ============================================================


async def zzz_daily_note(uid: str, cookie: str, fp: str, device_id: str) -> dict[str, Any]:
    """绝区零便笺：电量 / 每日活跃 / 录像带 / 悬赏。

    ZZZ 独特：请求**不带 DS**（仅 cookie），命中风控后上游会自动补。这里不实现重试。
    """
    _is_os = server.is_os(uid, "zzz")
    server_id = server.get_server_id(uid, "zzz")
    url = api.URL_ZZZ_NOTE_OS if _is_os else api.URL_ZZZ_NOTE
    params = {"role_id": uid, "server": server_id}
    # ZZZ 专属 header（Origin=act.mihoyo.com + x-rpc-page=zzz + 删 client_type）
    headers = device.build_zzz_headers(cookie, device_id, fp)
    async with httpx.AsyncClient(timeout=30.0) as c:
        return await _mys_get(c, url, params, headers, game="zzz",
                              ctx=f"zzz-note uid={uid}", resign_ds=False)


async def zzz_shiyu(
    uid: str, cookie: str, fp: str, device_id: str, *, schedule: int = 1,
) -> dict[str, Any]:
    """式舆防卫战(ZZZ 深渊)。schedule=1 本期 / 2 上期。

    米游社 2.0 后 `/challenge` 路径可能被废（返回 404 html），新版叫
    "第五防线"接口是 `/hadal_info_v2`。先试旧路径，404 时自动 fallback 到新路径。
    返回字段结构不同：旧 challenge 用 `max_layer/rating_list`；新 hadal 用 `brief.score/zone_id`。
    水神层通过 `_source` 字段区分解析。
    """
    _is_os = server.is_os(uid, "zzz")
    server_id = server.get_server_id(uid, "zzz")
    url_old = api.URL_ZZZ_SHIYU_OS if _is_os else api.URL_ZZZ_SHIYU
    url_new = api.URL_ZZZ_HADAL_OS if _is_os else api.URL_ZZZ_HADAL
    params = {"role_id": uid, "server": server_id, "schedule_type": schedule}
    headers = device.build_zzz_headers(cookie, device_id, fp)

    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await _mys_get(c, url_old, params, headers, game="zzz",
                           ctx=f"zzz-shiyu uid={uid}", resign_ds=False)
        rc = r.get("retcode")
        if rc == 0 and r.get("data"):
            r["_source"] = "challenge"
            return r
        # 404 html → -9999；米游社"网页异常"→ -400005；这两种视为接口废弃，fallback
        if rc in (-9999, -400005):
            import sys as _sys
            print(f"[skill·mihoyo] zzz-shiyu 旧路径挂了(rc={rc})，fallback 到 hadal_info_v2",
                  file=_sys.stderr)
            r2 = await _mys_get(c, url_new, params, headers, game="zzz",
                                ctx=f"zzz-hadal uid={uid}", resign_ds=False)
            r2["_source"] = "hadal"
            return r2
        # 其它失败码（风控 10035 / 参数错等）直接返，不 fallback
        r["_source"] = "challenge"
        return r


async def zzz_mem_detail(
    uid: str, cookie: str, fp: str, device_id: str, *, schedule: int = 1,
) -> dict[str, Any]:
    """危局强袭战（Deadly Assault / MEM / Notorious Hunt 新版）。"""
    _is_os = server.is_os(uid, "zzz")
    server_id = server.get_server_id(uid, "zzz")
    url = api.URL_ZZZ_MEM_OS if _is_os else api.URL_ZZZ_MEM
    # 危局强袭战需要 uid/lang/region（ZZZeroUID 里额外传这三个在 schedule_type 之外）
    params = {
        "uid": uid, "lang": "zh-cn", "region": server_id,
        "role_id": uid, "server": server_id, "schedule_type": schedule,
    }
    headers = device.build_zzz_headers(cookie, device_id, fp)
    async with httpx.AsyncClient(timeout=30.0) as c:
        return await _mys_get(c, url, params, headers, game="zzz",
                              ctx=f"zzz-mem uid={uid}", resign_ds=False)


# ============================================================
# 签到（原神 / 星铁 / 绝区零三合一）
# ============================================================


# 签到路径抄自 gsuid_core/utils/api/mys/sign_request.py
# 国服 act_id 按 server 区分（同游戏 cn_gf01/cn_qd01 共用一个 id）
# x-rpc-signgame 对应游戏标识：gs→hk4e / sr→hkrpg / zzz→zzz
_SIGN_GAME_NAME = {"gs": "hk4e", "sr": "hkrpg", "zzz": "zzz"}
_SIGN_ACT_ID = {
    "gs":  {"cn": api.ACT_ID_GS,  "os": api.ACT_ID_GS_OS},
    "sr":  {"cn": api.ACT_ID_SR,  "os": api.ACT_ID_SR_OS},
    "zzz": {"cn": api.ACT_ID_ZZZ, "os": api.ACT_ID_ZZZ_OS},
}


async def sign_in(
    game: str, uid: str, cookie: str, fp: str, device_id: str,
) -> dict[str, Any]:
    """签到。game ∈ gs/sr/zzz。返回 {ok, retcode, msg, is_risk, is_signed}。

    关键（抄 gsuid_core sign_request.mys_sign）：
    - DS 用 ``get_web_ds_token(True)``（LK2 web salt），**不是** get_ds_token
    - header 必须 x-rpc-signgame=<hk4e|hkrpg|zzz> + x-rpc-client_type=5 + X_Requested_With
    - body 必含 act_id / lang / uid / region 四字段
    - 风控码 10035/5003/10041/1034 是 _DEAD_CODE，需打码平台（本实现不支持，返 is_risk）
    """
    if game not in _SIGN_GAME_NAME:
        return {"ok": False, "retcode": -1, "msg": f"未知游戏: {game}"}
    _is_os = server.is_os(uid, game)
    server_id = server.get_server_id(uid, game)
    act_id = _SIGN_ACT_ID[game]["os" if _is_os else "cn"]

    body = {"act_id": act_id, "lang": "zh-cn", "uid": uid, "region": server_id}

    if _is_os:
        ds = sign.generate_os_ds()
        extra = {"DS": ds}
        base = api.SIGN_BASE_OS if game in ("gs", "zzz") else api.SIGN_SR_BASE_OS
        path = "/event/sol/sign" if game == "gs" else (
            "/event/luna/os/sign" if game == "sr" else "/event/sol/sign"
        )
    else:
        # 国服：web LK2 DS，不用 body 不用 query
        ds = sign.get_web_ds_token(web=True)
        extra = {
            "DS": ds,
            "x-rpc-signgame": _SIGN_GAME_NAME[game],
            "x-rpc-client_type": "5",
            "X_Requested_With": "com.mihoyo.hyperion",
        }
        base = api.GS_BASE
        path = "/event/luna/sign"

    headers = device.build_headers(cookie, device_id, fp, extra=extra)
    url = base + path
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.post(url, json=body, headers=headers)
        data = resp.json()

    rc = int(data.get("retcode", -1) or -1)
    # 风控 dead codes：米游社需要打码平台通过 x-rpc-challenge 重签
    _DEAD = (10035, 5003, 10041, 1034)
    risk_from_data = (
        data.get("data", {}).get("risk_code", 0)
        if isinstance(data.get("data"), dict) else 0
    )
    is_risk = rc in _DEAD or risk_from_data in (375, 5001)
    is_signed = rc in (-5003, -5017)   # 已签到 / ZZZ 已签
    return {
        "ok": (rc == 0 and not is_risk) or is_signed,
        "retcode": rc,
        "msg": data.get("message", ""),
        "is_risk": is_risk,
        "is_signed": is_signed,
        "raw": data,
    }


async def sign_info(
    game: str, uid: str, cookie: str, fp: str, device_id: str,
) -> dict[str, Any]:
    """查询签到状态。国服走 GET + x-rpc-signgame（**无 DS**），国际服走 GET + generate_os_ds。"""
    if game not in _SIGN_GAME_NAME:
        return {"ok": False, "msg": f"未知游戏: {game}"}
    _is_os = server.is_os(uid, game)
    server_id = server.get_server_id(uid, game)
    act_id = _SIGN_ACT_ID[game]["os" if _is_os else "cn"]
    params = {"act_id": act_id, "lang": "zh-cn", "region": server_id, "uid": uid}

    if _is_os:
        extra = {"DS": sign.generate_os_ds()}
        base = api.SIGN_BASE_OS if game in ("gs", "zzz") else api.SIGN_SR_BASE_OS
        path = "/event/sol/info" if game == "gs" else (
            "/event/luna/os/info" if game == "sr" else "/event/sol/info"
        )
    else:
        # 国服：不设 DS（上游 sign_request.get_sign_info 只给 x-rpc-signgame）
        extra = {"x-rpc-signgame": _SIGN_GAME_NAME[game]}
        base = api.GS_BASE
        path = api.PATH_SIGN_INFO_ZZZ if game == "zzz" else api.PATH_SIGN_INFO_GS

    headers = device.build_headers(cookie, device_id, fp, extra=extra)
    url = base + path
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.get(url, params=params, headers=headers)
        return resp.json()


# ============================================================
# 抽卡（authkey 方式）—— 原神
# ============================================================

# 卡池 ID：301=角色活动 / 302=武器 / 200=常驻 / 100=新手 / 500=集录
GACHA_TYPES = {
    "character": "301",
    "weapon": "302",
    "permanent": "200",
    "newbie": "100",
    "chronicled": "500",
}


async def gacha_log(
    authkey: str, gacha_type: str = "301", end_id: str = "0",
    *, is_os: bool = False, lang: str = "zh-cn", size: int = 20,
    page: int = 1,
) -> dict[str, Any]:
    """分页抓抽卡记录。参数对齐上游 gsuid_core.request.get_gacha_log_by_authkey：

    - gacha_id 用上游同款固定 hash（省得米游社风控）
    - device_type=mobile
    - init_type / gacha_type 同步给 gacha_type
    """
    params = {
        "authkey_ver": "1",
        "sign_type": "2",
        "auth_appid": "webview_gacha",
        "init_type": str(gacha_type),
        "gacha_id": "fecafa7b6560db5f3182222395d88aaa6aaac1bc",
        "lang": lang,
        "device_type": "mobile",
        "authkey": authkey,
        "game_biz": "hk4e_global" if is_os else "hk4e_cn",
        "gacha_type": str(gacha_type),
        "page": str(page),
        "size": str(size),
        "end_id": str(end_id),
    }
    url = api.URL_GACHA_LOG_OS if is_os else api.URL_GACHA_LOG
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.get(url, params=params)
        return resp.json()


def parse_authkey_from_url(url: str) -> tuple[str, bool] | None:
    """从游戏内"祈愿历史"页面复制出来的 URL 里提 authkey。返回 (authkey, is_os)。"""
    try:
        qs = parse_qs(urlparse(url).query)
        ak = qs.get("authkey", [None])[0]
        if not ak:
            return None
        host = urlparse(url).netloc
        is_os = "hoyoverse" in host or "hoyolab" in host
        return ak, is_os
    except Exception:
        return None


async def gacha_log_all(
    authkey: str, gacha_type: str = "301", *, is_os: bool = False,
    max_pages: int = 100, since_id: str = "",
) -> list[dict[str, Any]]:
    """翻页抓全量（到上次抓到的 since_id 或到底）。返回 list[gacha_item]。"""
    out: list[dict[str, Any]] = []
    end_id = "0"
    for _ in range(max_pages):
        r = await gacha_log(authkey, gacha_type, end_id, is_os=is_os)
        if r.get("retcode") != 0:
            break
        items = r.get("data", {}).get("list", [])
        if not items:
            break
        for it in items:
            if since_id and it.get("id", "") <= since_id:
                return out
            out.append(it)
        end_id = items[-1].get("id", "0")
        # 米游社限频：每页间 800ms
        await asyncio.sleep(0.8)
    return out
