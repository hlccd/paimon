"""
派蒙·意图粗分类

根据用户消息 + 可用 Skills + 会话上下文，判断任务类型：
- chat: 闲聊/问候/知识问答 → 派蒙直接回复
- skill:<name>: 简单任务，某个 skill 可处理 → 天使调度

**两层架构**：
  1. 规则引擎前置（本文件 _rule_classify）：对高置信度 pattern 直接判定，
     零 LLM 成本、零误判。没命中规则才走 LLM。
  2. LLM 分类兜底：按 prompt 推断。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.shades.asmoday.registry import SkillRegistry
    from paimon.llm.model import Model
    from paimon.session import Session


@dataclass
class IntentResult:
    kind: str  # "chat" | "skill" | "hotspot"
    skill_name: str = ""
    hotspot_kind: str = ""  # "daily" | "weekly"，仅 kind=="hotspot" 有意义


# ============ 规则引擎：常见高置信度 pattern ============

# 风神热点资讯快捷入口（chat 里直接问"今日热点"/"近期回顾"）
# weekly 先匹配（含"近期"/"本周"等明确范围词，daily 触发词更宽容易抢）
_HOTSPOT_WEEKLY_PATTERNS = [
    re.compile(r"近期回顾|这周热点|本周热点|周热点回顾|本周.{0,3}回顾|近期.{0,3}总结"),
    re.compile(r"周末.{0,4}(看什么|有什么|大事)"),
]
_HOTSPOT_DAILY_PATTERNS = [
    re.compile(r"今日热点|今天热点|今日热搜|今日.{0,3}新闻|最近热点|近日热点"),
    re.compile(r"今天.{0,4}(看什么|有什么|大事|新鲜事|热搜)"),
    re.compile(r"(给我|说说|讲讲|来.{0,2})(今日|今天|最近)(的)?热点"),
]

# 定时 / 提醒 / 推送：几乎 100% 是 schedule 工具调用
_SCHEDULE_PATTERNS = [
    re.compile(r"每\s*\d+\s*(秒|分|分钟|小时|天|周)"),
    re.compile(r"每(天|周|小时|分钟|月)"),
    re.compile(r"\d+\s*(秒|分钟|小时|天)(后|之后)"),
    re.compile(r"(提醒|通知|叫)我.{0,15}(做|去|记得|别忘)"),
    re.compile(r"(推送|发送|发给我|告诉我).{0,20}(一次|一条)"),
    re.compile(r"定时(任务|提醒|推送|发送)"),
    re.compile(r"\d+(:|:)\d+\s*(给我|提醒|推送|发)"),  # 9:00 提醒我
    re.compile(r"cron"),
]

# 主流游戏白名单（character skill 触发用，新游戏出现时加一行）
# 同游戏多个常用名 / 简称都列上（"星铁 / 崩铁 / 崩坏星穹铁道"互斥但都常用）
_GAME_NAMES = (
    # 米哈游
    "原神", "星铁", "崩铁", "崩坏星穹铁道", "绝区零", "ZZZ",
    # 鹰角
    "明日方舟", "舟游",
    # 库洛
    "鸣潮",
    # 其他大众二游
    "战双帕弥什", "战双",
    "阴阳师",
    "命运冠位指定", "FGO",
    "公主连结", "公连", "PCR",
    "蔚蓝档案", "碧蓝档案", "BA",
    "碧蓝航线",
    "重返未来1999",
    "少女前线2", "少前2", "少女前线", "少前",
    "白夜极光",
    "无期迷途",
    "尘白禁区",
    "雷索纳斯",
    "幻塔",
)

# 角色查询动词（出现游戏名 + 12 字内此类动词 → character）
# "推荐" / "值得" 高频且 character 语义清晰，"X 推荐抽吗" / "X 值得抽吗" 是典型问法
# "值不值得" 是反问句，跟"值得"分别命中（不含子串关系）
_QUERY_VERBS = (
    "怎么", "强不强", "强度", "值不值得", "值得", "抽不抽", "配队",
    "阵容", "攻略", "推不推", "推荐", "要不要", "怎么样", "如何",
    "搭配", "玩法",
)

# character 组合 pattern：游戏名 + 查询动词 / 配队搭配模式
# 字面 trigger 字面命中是首选；这里是补充——覆盖"原神尼可强不强"这种
# trigger 没列但语义清晰的场景
# IGNORECASE：游戏英文简称（ZZZ / FGO / PCR / BA）大小写都识别（用户常 zzz / Fgo 写）
_CHARACTER_PATTERNS = [
    re.compile(
        rf"({'|'.join(map(re.escape, _GAME_NAMES))})"
        rf".{{0,12}}({'|'.join(_QUERY_VERBS)})",
        re.IGNORECASE,
    ),
    # 反向：查询动词 + 游戏名（"配队推荐 原神"）
    re.compile(
        rf"({'|'.join(_QUERY_VERBS)})"
        rf".{{0,12}}({'|'.join(map(re.escape, _GAME_NAMES))})",
        re.IGNORECASE,
    ),
    # 配队 / 阵容 + 推荐 / 建议（无游戏名也能命中——纯角色查询场景）
    re.compile(r"(配队|阵容|队伍|搭配).{0,6}(推荐|建议|怎么|哪)"),
    # 反向：怎么 / 该 / 要 + 配队 / 阵容（"我该怎么配队"）
    re.compile(r"(怎么|该|要|想).{0,6}(配队|阵容|队伍|搭配)"),
]


def _rule_classify(user_input: str, skill_registry: SkillRegistry) -> IntentResult | None:
    """规则引擎：命中返回结果，未命中返回 None 让 LLM 兜底。"""
    t = user_input.strip()
    if not t:
        return None

    # 0) 风神热点 chat 入口：触发词命中即直接读 daily/weekly_hotspot facade，无需 LLM
    for pat in _HOTSPOT_WEEKLY_PATTERNS:
        if pat.search(t):
            logger.info("[派蒙·意图·规则] 命中近期回顾模式 → hotspot:weekly")
            return IntentResult(kind="hotspot", hotspot_kind="weekly")
    for pat in _HOTSPOT_DAILY_PATTERNS:
        if pat.search(t):
            logger.info("[派蒙·意图·规则] 命中今日热点模式 → hotspot:daily")
            return IntentResult(kind="hotspot", hotspot_kind="daily")

    # 1) 定时 / 提醒类 → chat（派蒙直接调 schedule 工具）
    for pat in _SCHEDULE_PATTERNS:
        if pat.search(t):
            logger.info("[派蒙·意图·规则] 命中定时模式 '{}' → chat", pat.pattern[:30])
            return IntentResult(kind="chat")

    # 2) character 组合 pattern → skill:character
    # 在 trigger 字面扫之前过——覆盖"原神尼可强不强"这种 trigger 没列但语义明确的
    # （新角色名 LLM 不认识也无所谓，看的是游戏名 + 查询动词的字面共现）
    if skill_registry.exists("character"):
        for pat in _CHARACTER_PATTERNS:
            if pat.search(t):
                logger.info("[派蒙·意图·规则] 命中 character 组合模式 '{}' → skill:character",
                            pat.pattern[:40])
                return IntentResult(kind="skill", skill_name="character")

    # 3) Skill 触发特征 → skill:<name>
    # URL/域名类 trigger 优先于关键词类。同层内取最具体（最长）的。
    # 旧版「字母序遍历 + 先命中先 return」会让消息含「搜索」时 web-search 截胡 xhs 的 xhslink.com。
    t_lower = t.lower()

    def _is_url_trigger(trig: str) -> bool:
        tl = trig.lower()
        return any(marker in tl for marker in (".com", ".cn", ".tv", ".net", "://", "http"))

    url_hits: list = []  # [(trigger_len, skill, trigger)]
    kw_hits: list = []
    for s in skill_registry.list_all():
        if not s.triggers:
            continue
        for trig in (tr.strip() for tr in s.triggers.split(",") if tr.strip()):
            if trig.lower() in t_lower:
                bucket = url_hits if _is_url_trigger(trig) else kw_hits
                bucket.append((len(trig), s, trig))
                break

    chosen = url_hits or kw_hits
    if chosen:
        chosen.sort(key=lambda x: -x[0])
        _, s, trig = chosen[0]
        tier = "URL" if url_hits else "关键词"
        logger.info("[派蒙·意图·规则] 命中 skill triggers '{}'({}) → skill:{}", trig, tier, s.name)
        return IntentResult(kind="skill", skill_name=s.name)

    return None


_CLASSIFY_PROMPT = """\
你是意图分类器。只判断 **本次** 用户消息的任务类型，不要被历史对话带偏。

## 可用 Skills
{skill_catalog}

## 二选一

**chat** — 闲聊、问候、知识问答、**定时任务设置**、**URL 抓取**、**读写记忆/知识**、复杂分析
  - 本次消息包含一个或几个单一动作，派蒙自己就能完成（含调用一个内置工具）

**skill:<name>** — **本次消息本身**包含某 skill 的触发特征（例如粘贴了对应域名的链接）
  - ⚠️ 必须：`skill 的 triggers 关键词` 实际出现在本次消息里
  - ❌ 不允许：因为历史对话聊过这个 skill、或因为话题"相关"就返回 skill

## 反例（都应该判 chat）

| 用户消息 | ✗ 错误 | ✓ 正确 |
|---|---|---|
| "每 10 秒推送一条测试给我" | skill:bili | **chat** |
| "帮我抓一下 example.com/x" | skill:任意 | **chat** |
| "记住我老婆叫小红" | skill:xhs | **chat** |
| "30 分钟后提醒我开会" | skill:任意 | **chat** |

即使**历史上**用户用过 bili/xhs skill，如果**本次消息**没有相关链接或明确意图，仍然判 chat。

## character skill 特别说明

`character` 是跨游戏角色调研 skill，覆盖**所有有中文社区攻略的游戏**：
- 米哈游：原神 / 星铁 / 绝区零
- 鹰角：明日方舟
- 库洛：鸣潮
- 其他：战双 / 阴阳师 / FGO / 公主连结 / 蔚蓝档案 / 重返未来1999 / 少女前线 / 白夜极光 / 无期迷途 / 尘白禁区 / 幻塔 等

**关键点**：
- ⚠️ 即使你不认识 query 里的角色名（**很可能是新角色或你不熟悉的游戏**），
  只要消息上下文是上述游戏的角色查询 / 配队 / 抽取 / 机制问题，**一律返回 skill:character**
- 不要因为"我没听过这个角色"或"这个游戏太冷门"就判 chat 让派蒙浅层胡答——
  skill 内部会用 topic 跑爬虫拿真实数据，靠采集结果说话
- 即使 query 里没明显 trigger 词（比如就一句"明日方舟史尔特尔"），
  只要含**游戏名 + 角色查询语境**，仍判 skill:character

## 判定顺序
1. 本次消息是否包含某 skill 的触发关键词？→ skill:<name>
2. 其他一律 → chat

## 输出格式
只输出一个标签：`chat` / `skill:bili`
不要输出 markdown、引号、句号、解释。"""


def _verify_skill_match(user_input: str, skill_registry: SkillRegistry, skill_name: str) -> bool:
    """LLM 说 skill:X 时做二次校验：X 的任一 trigger 是否真的在本次消息里出现。

    防止 LLM 被会话历史污染误选 skill（如历史聊过 bili，当前消息跟 bili 无关时仍判 skill:bili）。

    character 特例：trigger 字面漏的场景，允许 _CHARACTER_PATTERNS 当 verify pass
    （处理"尼可这角色怎么样"这种 LLM 看 catalog 能判 character 但 trigger 没字面命中的）。
    """
    skill = skill_registry.get(skill_name)
    if not skill or not skill.triggers:
        # 无 triggers 声明的 skill，无法校验，保守起见不允许（会回退 chat）
        return False

    triggers = [tr.strip() for tr in skill.triggers.split(",") if tr.strip()]
    t_lower = user_input.lower()
    if any(trig.lower() in t_lower for trig in triggers):
        return True

    # character 特例：跟规则引擎前置用同一套 _CHARACTER_PATTERNS 兜底
    if skill_name == "character":
        return any(p.search(user_input) for p in _CHARACTER_PATTERNS)

    return False


async def classify_intent(
    model: Model,
    session: Session,
    user_input: str,
    skill_registry: SkillRegistry | None,
) -> IntentResult:
    if not skill_registry or not skill_registry.skills:
        return IntentResult(kind="chat")

    # ========== 第一层：规则引擎 ==========
    rule_result = _rule_classify(user_input, skill_registry)
    if rule_result is not None:
        return rule_result

    # ========== 第二层：LLM 兜底分类 ==========
    catalog_lines = []
    for s in skill_registry.list_all():
        line = f"- {s.name}: {s.description}"
        if s.triggers:
            line += f" (触发特征: {s.triggers})"
        catalog_lines.append(line)
    catalog = "\n".join(catalog_lines)

    system = _CLASSIFY_PROMPT.format(skill_catalog=catalog)

    # 注意：不传会话历史——会话历史容易污染分类（历史聊过 bili 就总爱判 skill:bili）
    # 意图分类是单轮任务，只看本次消息
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_input},
    ]

    # REL-012：意图分类应该秒级返回；LLM 卡住时不该让 user 等几十秒，超时即降级 chat
    import asyncio as _asyncio
    try:
        async def _classify() -> str:
            raw, usage = await model._stream_text(messages, component="paimon", purpose="意图分类")
            await model._record_primogem(session.id, "paimon", usage, purpose="意图分类")
            return raw
        raw = await _asyncio.wait_for(_classify(), timeout=15.0)
        label = raw.strip().lower()
        # 有些模型喜欢加句号、引号、markdown 包装——宽容解析
        label = label.strip(" .,!?`\"'")
    except _asyncio.TimeoutError:
        logger.warning("[派蒙·意图] 分类超时（>15s），回退到 chat")
        return IntentResult(kind="chat")
    except Exception as e:
        logger.warning("[派蒙·意图] 分类失败，回退到 chat: {}", e)
        return IntentResult(kind="chat")

    if label.startswith("skill:"):
        skill_name = label[6:].strip()
        if not skill_registry.exists(skill_name):
            logger.warning("[派蒙·意图] 分类返回未知 skill '{}', 回退 chat", skill_name)
            return IntentResult(kind="chat")
        # 关键防御：二次校验 skill trigger 确实出现在本次消息里
        if not _verify_skill_match(user_input, skill_registry, skill_name):
            logger.warning(
                "[派蒙·意图] LLM 判 skill:{} 但本次消息不含其 triggers，回退 chat",
                skill_name,
            )
            return IntentResult(kind="chat")
        logger.info("[派蒙·意图] skill:{}", skill_name)
        return IntentResult(kind="skill", skill_name=skill_name)

    logger.info("[派蒙·意图] chat")
    return IntentResult(kind="chat")
