"""神之心 · ModelRouter —— 按 (component, purpose) 路由到 LLMProfile

配合世界树域 15 `llm_routes` 表 + 域 14 `llm_profiles.is_default`。
Model.chat 入口调 `router.resolve(component, purpose)` 拿 profile_id，
再由 Gnosis 的 `get_provider_by_profile_id` 取具体 Provider。

resolve 三级 fallback：
  1. route_key="{component}:{purpose}" 精确命中
  2. route_key="{component}" 粗匹配
  3. None（由上层回落到 Gnosis 默认 profile）

路由热更：Leyline `llm.route.updated` → router.reload()
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul


# ==================== 静态调用点枚举 ====================
# 面板 "路由配置" Tab 按此渲染行；代码里新增调用点时更新此常量。
# 动态来源（不在此列）：
#   - skills：天使技能由 irminsul.skill_list() 实时拉，每个 skill_name 是一个 component
#     （详见 paimon/core/chat/_handler.py:41-42 — skill 路径下 component=skill_name）
#   - 部分 archon 暂未发 LLM（雷神/水神/冰神/火神/岩神/venti.collect），
#     接入路由后再补到此处
KNOWN_CALLSITES: list[tuple[str, str]] = [
    # ── 派蒙 · 主对话入口 / 控制 ──
    ("chat", "闲聊"),
    ("paimon", "意图分类"),
    ("title", "标题生成"),
    ("派蒙", "上下文压缩"),
    ("派蒙·响铃", "定时任务"),
    ("派蒙·安全审", "入口审查"),
    ("派蒙·安全审", "skill 声明审查"),
    # ── 世界树 · 记忆 / 知识 ──
    ("remember", "记忆分类"),
    ("reconcile", "JSON 修复"),
    ("reconcile", "记忆冲突检测"),
    ("hygiene", "记忆批量整理"),
    ("kb_remember", "知识分类"),
    ("kb_remember", "知识冲突检测"),
    ("kb_hygiene", "知识批量整理"),
    # ── 三月 · 自检 ──
    ("三月·自检", "Deep·code-health"),
    # ── 四影 · 自进化提案管线 ──
    ("生执·propose_skill", "凝练 skill 草案"),
    ("生执·revise_proposal", "重写 skill 草案"),
    ("死执·review_proposal", "审 skill 提案"),
    ("自进化触发", "should_propose_chat"),
    ("空执", "namespace 壳"),  # 占位（skill 落盘装载，无独立 LLM）
    # ── 七神 · archon 业务接口（按七神保留铁律全列，未调 LLM 的标 disabled）──
    ("风神", "订阅早报"),
    ("风神", "事件日报"),
    ("风神", "事件聚类"),
    ("风神", "事件分析"),
    ("草神", "L1 记忆提取"),
    ("岩神", "业务接入·不调 LLM"),  # dividend-tracker skill 走 I/O
    ("水神", "业务接入·不调 LLM"),  # 米哈游游戏在 furina_game 子包
    ("火神", "namespace 壳"),       # 新职能待挂
    ("雷神", "namespace 壳"),       # 新职能待挂
    ("冰神", "namespace 壳"),       # skill 域职能已交空执
    # ── 晨星 · 协同天使讨论（component=agents 默认）──
    # 11 角色按 category 三档收口（roles.py 的 info / evaluative / adversarial），
    # 详见 council.py 的 _ROLE_CAT_LABEL
    ("agents", "晨星·拆议题"),
    ("agents", "晨星·调研"),
    ("agents", "晨星·召集"),
    ("agents", "晨星·调度"),
    ("agents", "晨星·综合"),
    ("agents", "天使·信息加工"),
    ("agents", "天使·决策视角"),
    ("agents", "天使·推动讨论"),
    # ── 音视频处理（独立 tool；mimo_key 直连未接 router，面板 disabled）──
    ("video_process", "音视频分析"),
    ("audio_process", "音视频分析"),
]

KNOWN_COMPONENTS: list[str] = sorted({c for c, _ in KNOWN_CALLSITES})


class ModelRouter:
    """路由内存索引 + 世界树持久化薄壳 + 命中记录。

    内存结构：_routes: dict[route_key, profile_id]。启动 `load()` 从世界树
    拉一次，之后靠 leyline `llm.route.updated` 事件 → `reload()` 同步。

    _hits: 按 route_key（component 或 "component:purpose"）记录最近一次命中
    的 profile_id / model_name / provider_source / timestamp，给面板"最近
    命中"小挂件用。重启丢失（不落库，避免热路径开销）。
    """

    def __init__(self, irminsul: "Irminsul"):
        self._irminsul = irminsul
        self._routes: dict[str, str] = {}
        self._hits: dict[str, dict] = {}

    async def load(self) -> None:
        rows = await self._irminsul.llm_route_list_all()
        self._routes = {r.route_key: r.profile_id for r in rows}
        if self._routes:
            logger.info("[神之心·路由] 加载完成 routes={}", len(self._routes))
        else:
            logger.debug("[神之心·路由] 加载完成 routes=0（无自定义路由，全部用默认 profile）")

    async def reload(self) -> None:
        await self.load()

    def resolve(self, component: str, purpose: str) -> str | None:
        """返回 profile_id；None 表示未命中，调用方应回落全局默认 profile。"""
        component = (component or "").strip()
        purpose = (purpose or "").strip()
        if not component:
            return None
        # 细粒度优先
        if purpose:
            pid = self._routes.get(f"{component}:{purpose}")
            if pid:
                return pid
        # 粗粒度
        return self._routes.get(component)

    async def set_route(
        self, route_key: str, profile_id: str, *, actor: str,
    ) -> None:
        await self._irminsul.llm_route_upsert(route_key, profile_id, actor=actor)
        self._routes[route_key] = profile_id

    async def delete_route(self, route_key: str, *, actor: str) -> bool:
        ok = await self._irminsul.llm_route_delete(route_key, actor=actor)
        if ok:
            self._routes.pop(route_key, None)
        return ok

    async def cascade_clear_purposes(
        self, component: str, *, actor: str,
    ) -> list[str]:
        """清空 component 下所有 purpose 级路由，让它们全部回退到组件级继承。

        面板组级 selector 改值时配合使用：先 set component 级，再 cascade 清掉
        子项 override。返回被清空的 route_key 列表（调用方据此发 leyline 事件）。
        """
        keys = await self._irminsul.llm_route_delete_purpose_overrides(
            component, actor=actor,
        )
        for k in keys:
            self._routes.pop(k, None)
        return keys

    def snapshot(self) -> dict[str, str]:
        """返回当前路由表副本（面板展示用）。"""
        return dict(self._routes)

    def record_hit(
        self, component: str, purpose: str,
        *, profile_id: str, model_name: str, provider_source: str,
    ) -> None:
        """记录一次路由命中。同时按 "component:purpose" 和 "component" 两个
        key 记录，面板渲染 component 粗粒度 / component:purpose 细粒度两个
        表时都能查到对应行的最近命中。"""
        import time
        ts = time.time()
        entry = {
            "profile_id": profile_id,
            "model_name": model_name,
            "provider_source": provider_source,
            "timestamp": ts,
        }
        if component:
            self._hits[component] = entry
            if purpose:
                self._hits[f"{component}:{purpose}"] = dict(entry)

    def get_hits(self) -> dict[str, dict]:
        """返回当前命中快照（面板展示用）。"""
        return dict(self._hits)
