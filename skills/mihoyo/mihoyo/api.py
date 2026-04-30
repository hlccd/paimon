"""米游社 URL 常量。抄自 gsuid_core/utils/api/mys/api.py，精简到当前用到的。"""
from __future__ import annotations

# 基础域名
GS_BASE = "https://api-takumi.mihoyo.com"
RECORD_BASE = "https://api-takumi-record.mihoyo.com"
BBS_URL = "https://bbs-api.mihoyo.com"
HK4_URL = "https://hk4e-api.mihoyo.com"
PASSPORT_URL = "https://passport-api.mihoyo.com"
HK4_SDK_URL = "https://hk4e-sdk.mihoyo.com"
NEW_BBS_URL = "https://bbs-api.miyoushe.com"

# 国际服
GS_BASE_OS = "https://api-os-takumi.mihoyo.com"
RECORD_BASE_OS = "https://bbs-api-os.hoyolab.com"
HK4_URL_OS = "https://hk4e-api-os.hoyoverse.com"
SIGN_BASE_OS = "https://sg-hk4e-api.hoyolab.com"
SIGN_SR_BASE_OS = "https://sg-public-api.hoyolab.com"

# 设备指纹
URL_GET_FP = "https://public-data-api.mihoyo.com/device-fp/api/getFp"
# 设备注册（防止新 device_id+fp 被米游社标为陌生设备 → 10035）
URL_DEVICE_LOGIN = f"{NEW_BBS_URL}/apihub/api/deviceLogin"
URL_SAVE_DEVICE = f"{NEW_BBS_URL}/apihub/api/saveDevice"

# QR 扫码登录
URL_CREATE_QRCODE = f"{HK4_SDK_URL}/hk4e_cn/combo/panda/qrcode/fetch"
URL_CHECK_QRCODE = f"{HK4_SDK_URL}/hk4e_cn/combo/panda/qrcode/query"
URL_STOKEN_BY_GAMETOKEN = f"{PASSPORT_URL}/account/ma-cn-session/app/getTokenByGameToken"
URL_COOKIE_BY_GAMETOKEN = f"{GS_BASE}/auth/api/getCookieAccountInfoByGameToken"
URL_COOKIE_BY_STOKEN = f"{PASSPORT_URL}/account/auth/api/getCookieAccountInfoBySToken"

# 原神
URL_DAILY_NOTE_GS = f"{RECORD_BASE}/game_record/app/genshin/api/dailyNote"
URL_DAILY_NOTE_GS_OS = f"{RECORD_BASE_OS}/game_record/genshin/api/dailyNote"
URL_PLAYER_INDEX_GS = f"{RECORD_BASE}/game_record/app/genshin/api/index"
URL_PLAYER_INDEX_GS_OS = f"{RECORD_BASE_OS}/game_record/genshin/api/index"
URL_PLAYER_DETAIL_INFO_GS = f"{RECORD_BASE}/game_record/app/genshin/api/character/list"
URL_PLAYER_DETAIL_INFO_GS_OS = f"{RECORD_BASE_OS}/game_record/genshin/api/character"
URL_SPIRAL_ABYSS = f"{RECORD_BASE}/game_record/app/genshin/api/spiralAbyss"
URL_SPIRAL_ABYSS_OS = f"{RECORD_BASE_OS}/game_record/genshin/api/spiralAbyss"
URL_POETRY_ABYSS = f"{RECORD_BASE}/game_record/app/genshin/api/role_combat"
# 幽境危战（5.6+，GenshinUID 里叫 hard_challenge，用户俗称"璃月深渊"）
URL_HARD_CHALLENGE = f"{RECORD_BASE}/game_record/app/genshin/api/hard_challenge"
URL_HARD_CHALLENGE_OS = f"{RECORD_BASE_OS}/game_record/genshin/api/hard_challenge"

# 崩坏星穹铁道
URL_DAILY_NOTE_SR = f"{RECORD_BASE}/game_record/app/hkrpg/api/note"
URL_DAILY_NOTE_SR_OS = f"{RECORD_BASE_OS}/game_record/hkrpg/api/note"
URL_SR_FORGOTTEN_HALL = f"{RECORD_BASE}/game_record/app/hkrpg/api/challenge"
URL_SR_FORGOTTEN_HALL_OS = f"{RECORD_BASE_OS}/game_record/hkrpg/api/challenge"
URL_SR_PURE_FICTION = f"{RECORD_BASE}/game_record/app/hkrpg/api/challenge_story"
URL_SR_APOCALYPTIC = f"{RECORD_BASE}/game_record/app/hkrpg/api/challenge_boss"
# 崩铁角色列表 + 面板
URL_SR_AVATAR_INFO = f"{RECORD_BASE}/game_record/app/hkrpg/api/avatar/info"
URL_SR_AVATAR_INFO_OS = f"{RECORD_BASE_OS}/game_record/hkrpg/api/avatar/info"

# 绝区零（ZZZ_BASE 域名独立）
URL_ZZZ_BASE_CN = f"{RECORD_BASE}/event/game_record_zzz/api/zzz"
URL_ZZZ_BASE_OS = "https://sg-act-nap-api.hoyolab.com/event/game_record_zzz/api/zzz"
URL_ZZZ_NOTE = f"{URL_ZZZ_BASE_CN}/note"
URL_ZZZ_NOTE_OS = f"{URL_ZZZ_BASE_OS}/note"
URL_ZZZ_SHIYU = f"{URL_ZZZ_BASE_CN}/challenge"        # 式舆防卫战（旧版）
URL_ZZZ_SHIYU_OS = f"{URL_ZZZ_BASE_OS}/challenge"
URL_ZZZ_HADAL = f"{URL_ZZZ_BASE_CN}/hadal_info_v2"    # 第五防线（新版式舆替代接口，1.x→2.0 改版后的实际路径）
URL_ZZZ_HADAL_OS = f"{URL_ZZZ_BASE_OS}/hadal_info_v2"
URL_ZZZ_MEM = f"{URL_ZZZ_BASE_CN}/mem_detail"         # 危局强袭战
URL_ZZZ_MEM_OS = f"{URL_ZZZ_BASE_OS}/mem_detail"
# 绝区零代理人列表（basic = 所有代理人基础信息；info 是单个代理人详情，需要 id_list[]）
URL_ZZZ_AVATAR_BASIC = f"{URL_ZZZ_BASE_CN}/avatar/basic"
URL_ZZZ_AVATAR_BASIC_OS = f"{URL_ZZZ_BASE_OS}/avatar/basic"

# 米游社玩家卡片（mys_id → 所有游戏 UID）
URL_MYS_GAME_RECORD = f"{RECORD_BASE}/game_record/card/wapi/getGameRecordCard"
URL_MYS_GAME_RECORD_OS = f"{RECORD_BASE_OS}/game_record/card/wapi/getGameRecordCard"

# 抽卡（authkey 方式）
# 原神
URL_GACHA_LOG = "https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog"
URL_GACHA_LOG_OS = f"{HK4_URL_OS}/gacha_info/api/getGachaLog"
# 崩坏星穹铁道
URL_SR_GACHA_LOG = "https://public-operation-hkrpg.mihoyo.com/common/gacha_record/api/getGachaLog"
URL_SR_GACHA_LOG_OS = "https://public-operation-hkrpg-sg.hoyoverse.com/common/gacha_record/api/getGachaLog"
# 绝区零
URL_ZZZ_GACHA_LOG = "https://public-operation-nap.mihoyo.com/common/gacha_record/api/getGachaLog"
URL_ZZZ_GACHA_LOG_OS = "https://public-operation-nap-sg.hoyoverse.com/common/gacha_record/api/getGachaLog"

# stoken → authkey 自动换（参考 gsuid_core get_authkey_by_cookie）
URL_GEN_AUTHKEY = f"{GS_BASE}/binding/api/genAuthKey"

# 签到 —— 路径拼 SIGN_BASE_CN/OS
SIGN_BASE_CN_GS = "https://api-takumi.mihoyo.com"  # 原神签到走这个域
PATH_SIGN_HOME_GS = "/event/luna/home"
PATH_SIGN_INFO_GS = "/event/luna/info"
PATH_SIGN_GS = "/event/luna/sign"

PATH_SIGN_HOME_SR = "/event/luna/home"
PATH_SIGN_INFO_SR = "/event/luna/info"
PATH_SIGN_SR = "/event/luna/sign"

PATH_SIGN_INFO_ZZZ = "/event/luna/zzz/info"
# 绝区零签到实际 act_id 走 zzz 专属，见 sign.py

# act_id（签到活动 ID）
ACT_ID_GS = "e202311201442471"
ACT_ID_SR = "e202304121516551"
ACT_ID_ZZZ = "e202406242138391"
# 国际服
ACT_ID_GS_OS = "e202102251931481"
ACT_ID_SR_OS = "e202303301540311"
ACT_ID_ZZZ_OS = "e202406031448091"
