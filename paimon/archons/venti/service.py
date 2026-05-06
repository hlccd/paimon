"""风神主类 VentiArchon：__init__ + is_running + execute + 4 mixin（采集/日报/预警/...）。"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul.task import Subtask, TaskEdict

from ._alert import _AlertMixin
from ._collect import _CollectMixin
from ._digest import _DigestMixin
from ._login import _LoginMixin
from ._models import _SYSTEM_PROMPT

from paimon.session import Session

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.llm.model import Model


class VentiArchon(_CollectMixin, _DigestMixin, _AlertMixin, _LoginMixin, Archon):
    """风神·巴巴托斯：舆情采集 + 日报组装 + P0 即时预警 + 站点 cookies 登录管理。"""

    def __init__(self) -> None:
        # 订阅采集 in-flight 集合：进入 collect_subscription 加入、finally 移除
        # 用途：① 前端卡片显示「采集中」角标 ② 防并发重入（cron + 手动按钮重叠）
        self._inflight: set[str] = set()
        # 站点扫码登录会话池（_LoginMixin 用，惰性初始化但显式声明便于追踪）
        self._pending_login: dict = {}
        self._login_gc_task = None

    def is_running(self, sub_id: str) -> bool:
        return sub_id in self._inflight

    # ---------- 四影管线入口（原有能力）----------

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[风神] 执行子任务: {}", subtask.description[:80])

        from paimon.archons.base import FINAL_OUTPUT_RULE
        system = _SYSTEM_PROMPT
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"

        # 预搜索：用 task.title 调 web-search skill 拿双引擎候选，注入 prompt。
        # 订阅日报路径用 _run_web_search 跑了几周稳定，这里复用同款 subprocess。
        # 失败不阻塞——LLM 仍可走 web_fetch 兜底（prompt 没禁止）。
        # 这是为了解决"风神 LLM 不知道 web-search skill 存在 → 只用 web_fetch 命中
        # baidu/google/zhihu 等搜索页全反爬"的历史 bug。
        pre_search_query = (task.title or subtask.description[:30]).strip()
        if pre_search_query:
            try:
                pre_results = await self._run_web_search(
                    query=pre_search_query, limit=30, engine="",
                )
                logger.info(
                    "[风神·预搜索] query={!r} 返回 {} 条",
                    pre_search_query[:40], len(pre_results),
                )
                if pre_results:
                    system += (
                        "\n\n## 预搜索结果（web-search skill 双引擎候选，已为你跑过）\n"
                        "你的工作流：先消化下面这 N 条候选，按需用 web_fetch 进具体 URL 抓正文，"
                        "再整理成结构化报告。**不要再调用搜索引擎首页类 URL**（baidu/google/zhihu 搜索页几乎全反爬）。\n"
                    )
                    for i, r in enumerate(pre_results, 1):
                        title = (r.get("title") or "").strip()[:100]
                        url = (r.get("url") or "").strip()
                        desc = (r.get("description") or "").strip()[:250]
                        eng = (r.get("engine") or "").strip()
                        system += f"\n{i}. **{title}** ({eng})\n   URL: {url}\n   摘要: {desc}\n"
            except Exception as e:
                logger.warning(
                    "[风神·预搜索] 失败（不阻塞，LLM 回退 web_fetch tool loop）: {}", e,
                )

        system += await self._load_feedback_memories_block(irminsul)
        system += FINAL_OUTPUT_RULE

        temp_session = Session(id=f"venti-{task.id[:8]}", name="风神采集")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="风神", purpose="信息采集",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="风神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="风神",
        )
        logger.info("[风神] 子任务完成, 结果长度={}", len(result))
        return result
