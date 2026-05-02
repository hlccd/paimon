"""米哈游账号 5 个 dataclass + 三游戏 UP 池 / 常驻 / 硬保底常量表。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MihoyoAccount:
    """单游戏单 UID 的账号凭证 + 签到 / authkey 状态。"""
    game: str                        # gs | sr | zzz
    uid: str
    mys_id: str = ""
    cookie: str = ""
    stoken: str = ""
    fp: str = ""
    device_id: str = ""
    device_info: str = ""
    authkey: str = ""
    authkey_ts: float = 0.0
    note: str = ""
    added_date: str = ""
    last_sign_at: float = 0.0
    enabled: bool = True


@dataclass
class MihoyoNote:
    """实时便笺：树脂 / 委托 / 周本 / 派遣 / 参量质变仪状态。"""
    game: str
    uid: str
    scan_ts: float = 0.0
    current_resin: int = 0
    max_resin: int = 160
    resin_full_ts: float = 0.0
    finished_tasks: int = 0
    total_tasks: int = 4
    daily_reward: int = 0
    remain_discount: int = 3
    current_expedition: int = 0
    max_expedition: int = 5
    expeditions: list[dict] = field(default_factory=list)
    transformer_ready: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class MihoyoAbyss:
    """深渊期次记录（GS 螺旋 / SR 诗歌；ZZZ 待支持）。"""
    game: str
    uid: str
    abyss_type: str                 # spiral | poetry
    schedule_id: str
    scan_ts: float = 0.0
    max_floor: str = ""
    total_star: int = 0
    total_battle: int = 0
    total_win: int = 0
    start_time: str = ""
    end_time: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class MihoyoCharacter:
    """角色仓库条目：等级 / 命座 / 武器 / 圣遗物。"""
    game: str
    uid: str
    avatar_id: str
    name: str = ""
    element: str = ""
    rarity: int = 4
    level: int = 1
    constellation: int = 0
    fetter: int = 0
    weapon: dict = field(default_factory=dict)   # {name, level, affix, rarity}
    relics: list = field(default_factory=list)
    icon_url: str = ""
    scan_ts: float = 0.0
    raw: dict = field(default_factory=dict)


@dataclass
class MihoyoGacha:
    """单条抽卡记录：跨游戏共用此结构（gacha_type 由游戏侧解读）。"""
    id: str
    uid: str
    gacha_type: str                 # gs:301/302/200/100/500 sr:1/2/11/12 zzz:1/2/3/5
    game: str = "gs"
    item_id: str = ""
    item_type: str = ""
    name: str = ""
    rank_type: int = 3
    time: str = ""
    time_ts: float = 0.0
    raw: dict = field(default_factory=dict)


# 三游戏的常驻 5 星名单 —— UP 池里出常驻名字 = "歪了"
# 米哈游偶尔加新常驻，过期后手动补；一时落后影响不大（顶多 UP 标错）
PERMANENT_TOP_TIER: dict[str, set[str]] = {
    "gs": {
        # 常驻角色（标准池）
        "迪卢克", "琴", "莫娜", "七七", "刻晴", "提纳里", "迪希雅",
        # 常驻武器（标准池）
        "风鹰剑", "天空之刃", "天空之傲",
        "天空之翼", "阿莫斯之弓",
        "天空之卷", "四风原典",
        "天空之脊", "和璞鸢",
        "狼的末路", "无工之剑",
    },
    "sr": {
        # 常驻 5 星角色
        "克拉拉", "希儿", "姬子", "布洛妮娅", "瓦尔特",
        "白露", "彦卿", "杰帕德", "银狼", "符玄",
        # 常驻 5 星光锥
        "拂晓之前", "时节不居", "无可取代的东西", "以世界之名", "如泥酣眠",
        "唯有沉默", "制胜的瞬间", "记一位星神的陨落", "在蓝天之下",
    },
    "zzz": {
        # 常驻 S 级代理人
        "莱卡恩", "格莉丝", "丽娜", "青衣", "11 号", "莱特", "苍角",
        # 常驻 S 级音擎（部分）
        "硫磺石", "燃狱齿轮",
    },
}

# UP 池（区分歪/不歪有意义）；常驻/集录/邦布等不区分（is_up=None）
UP_POOLS: dict[str, set[str]] = {
    "gs": {"301", "302"},
    "sr": {"11", "12"},
    "zzz": {"2", "3"},
}

# 硬保底上限（角色 90 / 武器 80 等）；查不到走 90 默认
HARD_PITY: dict[str, dict[str, int]] = {
    "gs":  {"301": 90, "302": 80, "200": 90, "100": 20, "500": 90},
    "sr":  {"11": 90, "12": 80, "1": 90, "2": 50},
    "zzz": {"2": 90, "3": 80, "1": 90, "5": 90},
}
