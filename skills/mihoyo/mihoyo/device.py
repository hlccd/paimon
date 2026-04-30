"""设备指纹 DeviceFp —— 抄自 gsuid_core/utils/api/mys/base_request.py 的 generate_fp。

米游社风控：请求必须带 x-rpc-device_id + x-rpc-device_fp，fp 由米游社 `getFp` 接口发放。
paimon 侧：每个 UID 绑定时生成一次，存世界树；cookie 失效时重新生成。
"""
from __future__ import annotations

import copy
import random
import time
import uuid
from string import ascii_letters, digits
from typing import Any

import httpx

from . import api, sign as _sign

_HEADER_APP = {
    "x-rpc-app_version": _sign.MYS_VERSION,
    "X-Requested-With": "com.mihoyo.hyperion",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; PHK110 Build/SKQ1.221119.001; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/"
        f"126.0.6478.133 Mobile Safari/537.36 miHoYoBBS/{_sign.MYS_VERSION}"
    ),
    "x-rpc-client_type": "5",
    "Referer": "https://webstatic.mihoyo.com/",
    "Origin": "https://webstatic.mihoyo.com/",
}


def new_device_id() -> str:
    return str(uuid.uuid4()).lower()


def _random_id(n: int = 64) -> str:
    return "".join(random.choices("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=n))


def _random_seed(n: int = 16) -> str:
    return "".join(random.choices("0123456789abcdef", k=n))


def _random_fp(n: int = 13) -> str:
    return "".join(random.choices(digits + "abcdef", k=n))


async def generate_fp(device_id: str | None = None) -> dict[str, Any]:
    """向米游社发请求拿 device_fp。模拟一加 PHK110。

    返回 {device_id, fp, device_info, seed_id, seed_time}，调用方存进世界树。
    """
    device_id = device_id or new_device_id()
    seed_id = new_device_id()
    seed_time = str(int(time.time() * 1000))

    model_name = "PHK110"
    device = "PHK110"
    device_type = "OP5913L1"
    board = "taro"
    oaid = "1f1971b188c472f0"
    device_info = (
        "OnePlus/PHK110/OP5913L1:13/SKQ1.221119.001/T.1328291_b9_41:user/release-keys"
    )

    aaid = _random_id()
    vaid = _random_id()
    random_data = random.randint(400000, 600000)
    random_data2 = random.randint(150000, 300000)
    time_diff = int(time.time() * 1000)

    ext_fields = (
        f'{{"proxyStatus":0,"isRoot":1,"romCapacity":"512","deviceName":"私人手机",'
        f'"productName":"{device}","romRemain":"491","hostname":"dg02-pool06-kvm82",'
        f'"screenSize":"1264x2640","isTablet":0,"aaid":"{aaid}","model":"{model_name}",'
        f'"brand":"OnePlus","hardware":"qcom","deviceType":"{device_type}","devId":"REL",'
        f'"serialNumber":"unknown","sdCapacity":{random_data},"buildTime":"1717740969000",'
        f'"buildUser":"root","simState":5,"ramRemain":"{random_data2}",'
        f'"appUpdateTimeDiff":{time_diff},"deviceInfo":"{device_info}","vaid":"{vaid}",'
        f'"buildType":"user","sdkVersion":"34","ui_mode":"UI_MODE_TYPE_NORMAL",'
        f'"isMockLocation":0,"cpuType":"arm64-v8a","isAirMode":0,"ringMode":1,'
        f'"chargeStatus":1,"manufacturer":"OnePlus","emulatorStatus":0,"appMemory":"512",'
        f'"osVersion":"14","vendor":"中国联通","accelerometer":"-1.3004991x6.38764x7.19103",'
        f'"sdRemain":{random_data2},"buildTags":"release-keys","packageName":"com.mihoyo.hyperion",'
        f'"networkType":"WiFi","oaid":"{oaid}","debugStatus":1,"ramCapacity":"{random_data}",'
        f'"magnetometer":"27.1084x-48.5804x-24.8758","display":"{model_name}_14.0.0.810(CN01)",'
        f'"appInstallTimeDiff":"{time_diff}","packageVersion":"2.20.2",'
        f'"gyroscope":"-0.02543317x0.005725792x0.003195791","batteryStatus":50,'
        f'"hasKeyboard":0,"board":"{board}"}}'
    )

    body = {
        "device_id": _random_seed(16),
        "seed_id": seed_id,
        "platform": "2",
        "seed_time": seed_time,
        "ext_fields": ext_fields,
        "app_name": "bbs_cn",
        "bbs_device_id": device_id,
        "device_fp": _random_fp(),
    }

    headers = copy.deepcopy(_HEADER_APP)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(api.URL_GET_FP, json=body, headers=headers)
            data = resp.json()
        if data.get("data", {}).get("code") == 200:
            fp = data["data"]["device_fp"]
        else:
            fp = _sign.random_hex(13).lower()
    except Exception:
        fp = _sign.random_hex(13).lower()

    return {
        "device_id": device_id,
        "fp": fp,
        "device_info": device_info,
        "seed_id": seed_id,
        "seed_time": seed_time,
    }


def build_headers(
    cookie: str,
    device_id: str,
    fp: str,
    *,
    ds: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """构造带 Cookie + 设备头的请求 headers。"""
    h = copy.deepcopy(_HEADER_APP)
    h["Cookie"] = cookie
    h["x-rpc-device_id"] = device_id
    h["x-rpc-device_fp"] = fp
    if ds:
        h["DS"] = ds
    if extra:
        h.update(extra)
    return h


def build_zzz_headers(
    cookie: str,
    device_id: str,
    fp: str,
    *,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """ZZZ 专用 header。对齐 ZZZeroUID 的 ZZZ_HEADER：

    - `Origin/Referer` 是 act.mihoyo.com（zzz web 活动页面），**不是** webstatic.mihoyo.com
    - `x-rpc-page=v1.0.14_#/zzz` + `x-rpc-platform=2`
    - **删除** `x-rpc-client_type`（沿用 app 的 "5" 会导致 challenge/mem_detail 接口 404）
    - 不带 DS（上游 ZZZ 请求不签 DS）

    note 接口宽松能接受 app header，但 challenge / mem_detail / hadal 严格，必须用专属头。
    """
    h = copy.deepcopy(_HEADER_APP)
    # 删掉 app 专用的字段
    h.pop("x-rpc-client_type", None)
    h["Cookie"] = cookie
    h["x-rpc-device_id"] = device_id
    h["x-rpc-device_fp"] = fp
    h["x-rpc-page"] = "v1.0.14_#/zzz"
    h["x-rpc-platform"] = "2"
    h["Origin"] = "https://act.mihoyo.com"
    h["Referer"] = "https://act.mihoyo.com/"
    if extra:
        h.update(extra)
    return h
