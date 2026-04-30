#!/usr/bin/env python3
"""mihoyo skill · 米游社 I/O CLI

输入输出契约：
- 多数子命令接 stdin JSON 参数（cookie 太长不适合 argv）
- stdout 输出紧凑 JSON（UTF-8，ensure_ascii=False），水神 `json.loads` 解析
- stderr 日志 / 错误
- 退出码：0 成功 / 2 参数错 / 3 米游社错误

子命令：
  gen-fp                  生成设备指纹（无参）
  qr-create               创建扫码登录 QR（无参，返 {ticket, device, url}）
  qr-poll                 stdin: {app_id, ticket, device}
  stoken-exchange         stdin: {account_id, game_token}
  cookie-exchange         stdin: {game_token, account_id}
  refresh-cookie          stdin: {stoken, mys_id}
  sign                    stdin: {game, uid, cookie, fp, device_id}
  sign-info               stdin: {game, uid, cookie, fp, device_id}
  daily-note              stdin: {uid, cookie, fp, device_id}
  spiral-abyss            stdin: {uid, cookie, fp, device_id, schedule?}
  poetry-abyss            stdin: {uid, cookie, fp, device_id}
  gacha-log               stdin: {authkey, gacha_type, is_os?, since_id?, max_pages?}
  parse-authkey           stdin: {url}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))


def _configure_runtime_logging() -> None:
    if os.environ.get("PAIMON_SKILL_RUNTIME") != "1":
        return
    try:
        from loguru import logger as _lg
        _lg.remove()
        _lg.add(sys.stderr, format="{message}", level="INFO")
    except Exception:
        pass


def _read_stdin_json() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"stdin JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(2)


async def _dispatch(cmd: str, payload: dict) -> dict:
    from mihoyo import actions, device as _dev

    if cmd == "gen-fp":
        return await _dev.generate_fp()
    if cmd == "qr-create":
        return await actions.qr_create()
    if cmd == "qr-poll":
        return await actions.qr_poll(payload["app_id"], payload["ticket"], payload["device"])
    if cmd == "stoken-exchange":
        return await actions.stoken_by_game_token(payload["account_id"], payload["game_token"])
    if cmd == "cookie-exchange":
        # 用 stoken + mys_id + mid 换 Cookie（米游社 2024 年后废弃了 game_token 直换路径）
        cookie = await actions.cookie_by_stoken(
            payload["stoken"], payload["mys_id"], payload["mid"],
        )
        return {"cookie": cookie}
    if cmd == "refresh-cookie":
        cookie = await actions.refresh_cookie_by_stoken(payload["stoken"], payload["mys_id"])
        return {"cookie": cookie}
    if cmd == "device-login":
        # 扫码后注册设备避免陌生设备风控
        return await actions.device_login(
            payload["device_id"], payload["fp"], payload["device_info"],
            payload["app_cookie"],
        )
    if cmd == "game-record":
        return await actions.game_record_card(
            payload["mys_id"], payload["cookie"],
            fp=payload.get("fp"), device_id=payload.get("device_id"),
            is_os=bool(payload.get("is_os", False)),
        )
    if cmd == "sign":
        return await actions.sign_in(
            payload["game"], payload["uid"], payload["cookie"],
            payload["fp"], payload["device_id"],
        )
    if cmd == "sign-info":
        return await actions.sign_info(
            payload["game"], payload["uid"], payload["cookie"],
            payload["fp"], payload["device_id"],
        )
    if cmd == "daily-note":
        return await actions.daily_note(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
        )
    if cmd == "spiral-abyss":
        return await actions.spiral_abyss(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
            schedule=int(payload.get("schedule", 1)),
        )
    if cmd == "poetry-abyss":
        return await actions.poetry_abyss(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
        )
    if cmd == "gs-characters":
        return await actions.gs_character_list(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
            character_ids=payload.get("character_ids"),
        )
    if cmd == "hard-challenge":
        return await actions.hard_challenge(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
        )
    if cmd == "sr-note":
        return await actions.sr_daily_note(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
        )
    if cmd == "sr-forgotten-hall":
        return await actions.sr_forgotten_hall(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
            schedule=int(payload.get("schedule", 1)),
        )
    if cmd == "sr-pure-fiction":
        return await actions.sr_pure_fiction(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
            schedule=int(payload.get("schedule", 1)),
        )
    if cmd == "sr-apocalyptic":
        return await actions.sr_apocalyptic(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
            schedule=int(payload.get("schedule", 1)),
        )
    if cmd == "zzz-note":
        return await actions.zzz_daily_note(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
        )
    if cmd == "zzz-shiyu":
        return await actions.zzz_shiyu(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
            schedule=int(payload.get("schedule", 1)),
        )
    if cmd == "zzz-mem":
        return await actions.zzz_mem_detail(
            payload["uid"], payload["cookie"], payload["fp"], payload["device_id"],
            schedule=int(payload.get("schedule", 1)),
        )
    if cmd == "gacha-log":
        items = await actions.gacha_log_all(
            payload["authkey"],
            gacha_type=str(payload.get("gacha_type", "301")),
            is_os=bool(payload.get("is_os", False)),
            max_pages=int(payload.get("max_pages", 100)),
            since_id=str(payload.get("since_id", "")),
        )
        return {"items": items, "count": len(items)}
    if cmd == "parse-authkey":
        r = actions.parse_authkey_from_url(payload["url"])
        if r is None:
            return {"ok": False}
        return {"ok": True, "authkey": r[0], "is_os": r[1]}

    raise ValueError(f"未知子命令: {cmd}")


async def _async_main(cmd: str) -> int:
    # 无参子命令
    no_stdin = {"gen-fp", "qr-create"}
    payload = {} if cmd in no_stdin else _read_stdin_json()
    try:
        result = await _dispatch(cmd, payload)
    except KeyError as e:
        print(f"参数缺失: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        # 响应不是合法 JSON（米游社偶尔返回空/HTML/\0 垃圾）—— 打到 stderr 方便定位
        print(f"[skill·mihoyo] 响应 JSON 解析失败: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"[skill·mihoyo] 执行异常: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    try:
        print(json.dumps(result, ensure_ascii=False, default=str))
    except TypeError as e:
        print(f"[skill·mihoyo] 结果 JSON 序列化失败: {e}", file=sys.stderr)
        return 3
    return 0


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    _configure_runtime_logging()

    p = argparse.ArgumentParser(prog="mihoyo", description="米游社 I/O skill")
    p.add_argument("cmd", choices=[
        "gen-fp", "qr-create", "qr-poll",
        "stoken-exchange", "cookie-exchange", "refresh-cookie", "device-login", "game-record",
        "sign", "sign-info", "daily-note",
        "spiral-abyss", "poetry-abyss", "hard-challenge", "gs-characters",
        "sr-note", "sr-forgotten-hall", "sr-pure-fiction", "sr-apocalyptic",
        "zzz-note", "zzz-shiyu", "zzz-mem",
        "gacha-log", "parse-authkey",
    ])
    args = p.parse_args()
    return asyncio.run(_async_main(args.cmd))


if __name__ == "__main__":
    sys.exit(main())
