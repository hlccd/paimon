"""UID 首位 → 服务器 ID 映射。抄自 gsuid_core/utils/database/utils.py。"""
from __future__ import annotations

# 原神
SERVER_GS = {
    "1": "cn_gf01", "2": "cn_gf01", "3": "cn_gf01", "4": "cn_gf01", "5": "cn_qd01",
    "6": "os_usa", "7": "os_euro", "8": "os_asia", "9": "os_cht",
}

# 星穹铁道
SERVER_SR = {
    "1": "prod_gf_cn", "2": "prod_gf_cn", "3": "prod_gf_cn", "4": "prod_gf_cn", "5": "prod_qd_cn",
    "6": "prod_official_usa", "7": "prod_official_eur", "8": "prod_official_asia", "9": "prod_official_cht",
}

# 绝区零（UID 长度 ≥10 开头 10/11...，短 UID 走老映射）
SERVER_ZZZ = {
    "10": "prod_gf_cn", "11": "prod_gf_cn", "12": "prod_gf_cn", "13": "prod_gf_cn", "15": "prod_gf_cn",
    "17": "prod_gf_us", "18": "prod_gf_eu", "19": "prod_gf_jp", "20": "prod_gf_sg",
}


def get_server_id(uid: str, game: str = "gs") -> str:
    """UID → server_id。game ∈ 'gs' | 'sr' | 'zzz'。

    zzz 短 UID（len < 10，早期账号/测试号）**默认国服** `prod_gf_cn`，
    绝不回退到 SERVER_GS（原神映射表） —— 那样签到会因 server=cn_gf01
    报 -10002 "未查询到游戏绑定角色"（签到接口以为是原神但 cookie 是 zzz 的）。
    """
    uid = str(uid).strip()
    if game == "gs":
        return SERVER_GS.get(uid[0], "cn_gf01")
    if game == "sr":
        return SERVER_SR.get(uid[0], "prod_gf_cn")
    if game == "zzz":
        if len(uid) >= 10:
            return SERVER_ZZZ.get(uid[:2], "prod_gf_cn")
        return "prod_gf_cn"   # zzz 短 UID 默认国服，别拿 SERVER_GS
    raise ValueError(f"未知 game: {game}")


def is_os(uid: str, game: str = "gs") -> bool:
    """UID → 是否国际服。game 不同判定规则不同。

    - gs/sr：UID 首位 ≥6 是国际服（原神/星铁标准）
    - zzz：长 UID 看前两位（17/18/19/20 国际），短 UID 国服
    """
    uid = str(uid).strip()
    if not uid:
        return False
    if game == "zzz":
        if len(uid) >= 10:
            return uid[:2] in ("17", "18", "19", "20")
        return False
    try:
        return int(uid[0]) >= 6
    except ValueError:
        return False
