"""米游社 DS 签名 —— 抄自 gsuid_core/utils/api/mys/tools.py

salt 常量 + mys_version 需要跟 gsuid_core 上游同步（米游社改了版本号就得跟）。
"""
from __future__ import annotations

import hashlib
import json
import random
import string
import time
from typing import Any

# 保持与 gsuid_core 上游一致，失效时同步升级
MYS_VERSION = "2.102.1"

_SALTS = {
    "2.102.1": {
        "K2": "lX8m5VO5at5JG7hR8hzqFwzyL5aB1tYo",   # web
        "LK2": "yBh10ikxtLPoIhgwgPZSv5dmfaOTSJ6a",  # web (login)
        "22": "t0qEgfub6cvueAPgR5m9aQWWVciEer7v",   # app
        "25": "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs",   # app (new)
    },
    "os": "6cqshh5dhw73bzxn20oexa9k516chk7s",
    "PD": "JwYDpKvLj6MrMqqYU6jTKF17KNO2PXoS",       # passport
}


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _random_text(n: int) -> str:
    return "".join(random.sample(string.ascii_lowercase + string.digits, n))


def get_ds_token(q: str = "", b: dict | None = None, salt_id: str = "25") -> str:
    """国服 app 签名（签到/便笺等大多数接口用它）。"""
    salt = _SALTS[MYS_VERSION][salt_id]
    body_json = json.dumps(b) if b else ""
    t = str(int(time.time()))
    r = str(random.randint(100000, 200000))
    c = _md5(f"salt={salt}&t={t}&r={r}&b={body_json}&q={q}")
    return f"{t},{r},{c}"


def get_web_ds_token(web: bool = False) -> str:
    """web DS（抽卡 authkey 等需要）。web=True 用 LK2，否则 K2。"""
    salt = _SALTS[MYS_VERSION]["LK2" if web else "K2"]
    t = str(int(time.time()))
    r = _random_text(6)
    c = _md5(f"salt={salt}&t={t}&r={r}")
    return f"{t},{r},{c}"


def generate_os_ds(salt: str = "") -> str:
    """国际服 DS。"""
    t = str(int(time.time()))
    r = "".join(random.sample(string.ascii_letters, 6))
    c = _md5(f"salt={salt or _SALTS['os']}&t={t}&r={r}")
    return f"{t},{r},{c}"


def generate_passport_ds(q: str = "", b: dict[str, Any] | None = None) -> str:
    """passport-api（登录/GameToken→Stoken）专用 DS。"""
    salt = _SALTS["PD"]
    t = str(int(time.time()))
    r = "".join(random.sample(string.ascii_letters, 6))
    body_json = json.dumps(b) if b else ""
    c = _md5(f"salt={salt}&t={t}&r={r}&b={body_json}&q={q}")
    return f"{t},{r},{c}"


def random_hex(length: int) -> str:
    v = hex(random.randint(0, 16**length)).replace("0x", "").upper()
    return v.rjust(length, "0")
