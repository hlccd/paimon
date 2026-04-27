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
# 动态 purpose（skill_name / check·{stage} / 生执的 2 种）也需在此列齐。
KNOWN_CALLSITES: list[tuple[str, str]] = [
    # 系统职能
    ("march", "定时任务"),
    ("chat", "闲聊"),
    ("paimon", "意图分类"),
    ("remember", "记忆分类"),
    ("title", "标题生成"),
    ("compress", "上下文压缩"),
    ("extract", "L1 记忆提取"),
    # 七神
    ("水神", "评审"),
    ("水神", "check·review_spec"),
    ("水神", "check·review_design"),
    ("水神", "check·review_code"),
    ("雷神", "代码生成"),
    ("雷神", "写技术方案"),
    ("雷神", "代码实现"),
    ("草神", "推理执行"),
    ("草神", "写产品方案"),
    ("风神", "信息采集"),
    ("风神", "订阅早报"),
    ("风神", "事件日报"),
    ("风神", "事件聚类"),
    ("风神", "事件分析"),
    ("冰神", "Skill管理"),
    ("火神", "执行部署"),
    ("岩神", "理财分析"),
    # 四影
    ("死执", "安全审查"),
    ("死执", "skill 声明审查"),
    ("生执", "任务编排"),
    ("生执", "任务修订编排"),
]

KNOWN_COMPONENTS: list[str] = sorted({c for c, _ in KNOWN_CALLSITES})


class ModelRouter:
    """路由内存索引 + 世界树持久化薄壳。

    内存结构：_routes: dict[route_key, profile_id]。启动 `load()` 从世界树
    拉一次，之后靠 leyline `llm.route.updated` 事件 → `reload()` 同步。
    """

    def __init__(self, irminsul: "Irminsul"):
        self._irminsul = irminsul
        self._routes: dict[str, str] = {}

    async def load(self) -> None:
        rows = await self._irminsul.llm_route_list_all()
        self._routes = {r.route_key: r.profile_id for r in rows}
        logger.info("[神之心·路由] 加载完成 routes={}", len(self._routes))

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

    def snapshot(self) -> dict[str, str]:
        """返回当前路由表副本（面板展示用）。"""
        return dict(self._routes)
