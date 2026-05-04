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
    # 派蒙 · 主对话
    ("chat", "闲聊"),
    ("paimon", "意图分类"),
    ("title", "标题生成"),
    # 三月 · 定时调度 + 自检
    ("march", "定时任务"),
    ("三月·自检", "Deep·code-health"),
    # 世界树 · 记忆 / 知识库（语义聚合到存储域）
    ("remember", "记忆分类"),
    ("reconcile", "JSON 修复"),
    ("reconcile", "记忆冲突检测"),
    ("hygiene", "记忆批量整理"),
    ("kb_remember", "知识分类"),
    ("kb_remember", "知识冲突检测"),
    ("kb_hygiene", "知识批量整理"),
    # 四影 · 流程骨架
    ("生执", "任务编排"),
    ("生执", "任务修订编排"),
    ("死执", "安全审查"),
    ("死执", "skill 声明审查"),
    ("时执", "上下文压缩"),
    ("时执", "L1 记忆提取"),
    ("空执", "动态路由"),  # 占位：当前 asmoday 不发 LLM；面板标 ⚠ 未接入 router
    # 七神（嵌四影下）
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
    ("冰神", "Skill 汇总"),
    ("火神", "执行部署"),
    ("岩神", "理财分析"),
    # 音视频处理（独立 tool；当前用 mimo_key 直连不走 router，面板标 ⚠ 未接入）
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
