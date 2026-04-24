"""风神 · Venti — 自由·歌咏

新闻采集、舆情分析与追踪、推送整理。

两条入口：
1. `execute()` —— 四影管线复杂任务入口（LLM tool-loop，走 web_fetch/exec）
2. `collect_subscription()` —— 话题订阅后台采集入口（subprocess 直调 web-search skill，
   批量 LLM 早报，交三月响铃推送）
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session

if TYPE_CHECKING:
    from paimon.foundation.march import MarchService

# web-search skill 脚本路径（文件存在则订阅能力可用；不存在仅告警不阻塞启动）
_SKILL_SEARCH_PY = (
    Path(__file__).resolve().parent.parent.parent / "skills" / "web-search" / "search.py"
)

# subprocess 超时：双引擎并发 + 反爬偶发慢，默认 60s
_WEB_SEARCH_TIMEOUT = 60.0

# 去重窗口：过去 30 天的 url 视为已见
_DEDUP_WINDOW_SECONDS = 30 * 24 * 3600


_SYSTEM_PROMPT = """\
你是风神·巴巴托斯，掌管自由与歌咏。你的职责是信息采集与分析。

能力：
1. 用 web_fetch 工具抓取网页内容（新闻、文章、搜索结果）
2. 用 exec 工具执行 curl 等命令做补充抓取
3. 新闻摘要和舆情分析

规则：
1. 优先用 web_fetch 工具，它更安全且输出更干净
2. 输出结构化结果：标题、来源、摘要
3. 舆情分析时标注情感倾向（正面/中性/负面）
4. 调用工具时不要输出过程描述，只输出最终结果
"""


_DIGEST_PROMPT = """\
你是风神·巴巴托斯，负责给用户整理关注话题的日报。

用户订阅主题：「{query}」
下面是刚采集到的 {n} 条新条目（JSON），请整理成一段中文日报，体裁要求：

1. 开头一句 40 字内的总体概述（当前这些新内容的主要看点）
2. 之后用 1-3 级 bullet 列出条目，每条「标题 + 1 句话要点 + 来源 URL」
3. 末尾一句话点出情感倾向（正面 / 中性 / 负面 / 混合）和建议（要不要深读）
4. 全篇控制在 500 字内
5. 保留 URL 的 markdown 链接格式: [标题](URL)
6. 只输出最终日报文本，不要任何前置说明
"""


def _build_fallback_digest(query: str, items: list[dict]) -> str:
    """LLM 失败时的降级模板：直接列条目。"""
    lines = [f"【订阅·{query}】刚刚采集到 {len(items)} 条新内容："]
    for it in items:
        title = (it.get("title") or "").strip() or "(无标题)"
        url = (it.get("url") or "").strip()
        if url:
            lines.append(f"- [{title}]({url})")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


class VentiArchon(Archon):
    name = "风神"
    description = "新闻采集、舆情分析、推送整理"
    allowed_tools = {"web_fetch", "exec"}

    # ---------- 四影管线入口（原有能力）----------

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[风神] 执行子任务: {}", subtask.description[:80])

        system = _SYSTEM_PROMPT
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"

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

    # ---------- 订阅采集入口（新增）----------

    async def collect_subscription(
        self, sub_id: str, *,
        irminsul: Irminsul,
        model: Model,
        march: MarchService,
    ) -> None:
        """主题订阅单次采集 + 推送。由三月 cron 触发（bootstrap 分派）。

        步骤：
        1. 读订阅（禁用/缺失直接退出）
        2. subprocess 调 web-search skill
        3. 过滤已见 url（30 天窗口）
        4. 落 feed_items
        5. 浅池 LLM 写日报 digest；失败降级模板
        6. 交三月 ring_event 推送
        7. 标记 feed_items pushed + 更新订阅 last_run_at
        """
        logger.info("[风神·订阅] 开始采集 sub_id={}", sub_id)

        sub = await irminsul.subscription_get(sub_id)
        if not sub:
            logger.warning("[风神·订阅] 订阅不存在 sub_id={}", sub_id)
            return
        if not sub.enabled:
            logger.info("[风神·订阅] 订阅已禁用 sub_id={}", sub_id)
            return

        # Step 2: 搜索
        try:
            results = await self._run_web_search(sub.query, sub.max_items, sub.engine)
        except Exception as e:
            logger.error("[风神·订阅] 搜索失败 sub={} err={}", sub_id, e)
            await irminsul.subscription_update(
                sub_id, actor="风神", last_error=str(e)[:500],
            )
            return

        if not results:
            logger.info("[风神·订阅] 搜索无结果 sub={} query='{}'", sub_id, sub.query)
            await irminsul.subscription_update(
                sub_id, actor="风神",
                last_run_at=time.time(), last_error="",
            )
            return

        # Step 3: 去重
        since_ts = time.time() - _DEDUP_WINDOW_SECONDS
        existing = await irminsul.feed_items_existing_urls(sub_id, since_ts=since_ts)
        new_items = [r for r in results if (r.get("url") or "") not in existing]

        if not new_items:
            logger.info(
                "[风神·订阅] 无新条目（全部已见） sub={} total={}",
                sub_id, len(results),
            )
            await irminsul.subscription_update(
                sub_id, actor="风神",
                last_run_at=time.time(), last_error="",
            )
            return

        logger.info(
            "[风神·订阅] 新条目 {} 条 / 总 {} 条 sub={}",
            len(new_items), len(results), sub_id,
        )

        # Step 4: 落库
        inserted_ids = await irminsul.feed_items_insert(
            sub_id, new_items, actor="风神",
        )
        if not inserted_ids:
            logger.warning("[风神·订阅] 条目入库 0 条 sub={}", sub_id)
            return

        # Step 5: LLM 日报
        digest = await self._compose_digest(sub.query, new_items, model)

        # Step 6: 推送
        digest_id = uuid4().hex[:12]
        try:
            ok = await march.ring_event(
                channel_name=sub.channel_name,
                chat_id=sub.chat_id,
                source="风神",
                message=digest,
            )
        except Exception as e:
            logger.error("[风神·订阅] 响铃失败 sub={} err={}", sub_id, e)
            ok = False

        if not ok:
            logger.warning("[风神·订阅] 响铃被拒/失败 sub={}（条目仍落盘）", sub_id)

        # Step 7: 标记 + 订阅 tick
        await irminsul.feed_items_mark_pushed(
            inserted_ids, digest_id, actor="风神",
        )
        await irminsul.subscription_update(
            sub_id, actor="风神",
            last_run_at=time.time(), last_error="",
        )

        logger.info(
            "[风神·订阅] 采集完成 sub={} 新增={} digest={}",
            sub_id, len(inserted_ids), digest_id,
        )

    async def _run_web_search(
        self, query: str, limit: int, engine: str,
    ) -> list[dict]:
        """调用 web-search skill 的 search.py，返回 JSON list。"""
        if not _SKILL_SEARCH_PY.exists():
            raise RuntimeError(
                f"web-search skill 不存在: {_SKILL_SEARCH_PY}；"
                "请确认 skills/web-search 已安装"
            )

        args: list[str] = [
            sys.executable, str(_SKILL_SEARCH_PY),
            query, "--limit", str(max(1, min(limit, 50))),
        ]
        if engine:
            args.extend(["--engine", engine])

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(), timeout=_WEB_SEARCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"web-search 超时 > {_WEB_SEARCH_TIMEOUT}s")

        rc = proc.returncode or 0
        if rc != 0:
            err_txt = (err_b or b"").decode("utf-8", "ignore").strip()
            # rc=3 = 所有引擎都挂；rc=2 = 参数错
            raise RuntimeError(f"web-search 退出码 {rc}: {err_txt[:200]}")

        out_txt = (out_b or b"").decode("utf-8", "ignore").strip()
        if not out_txt:
            return []
        try:
            data = json.loads(out_txt)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"web-search 输出非 JSON: {e}") from e

        if not isinstance(data, list):
            return []
        # 规范化：只保留必要字段 + 去空 url
        out: list[dict] = []
        for it in data:
            if not isinstance(it, dict):
                continue
            url = (it.get("url") or "").strip()
            if not url:
                continue
            out.append({
                "url": url,
                "title": (it.get("title") or "").strip(),
                "description": (it.get("description") or "").strip(),
                "engine": (it.get("engine") or "").strip(),
            })
        return out

    async def _compose_digest(
        self, query: str, items: list[dict], model: Model,
    ) -> str:
        """浅池 LLM 写早报；失败降级到模板。"""
        system = _DIGEST_PROMPT.format(query=query, n=len(items))
        # 给 LLM 的条目裁剪 description，避免过长
        trimmed = [
            {
                "title": it.get("title", "")[:200],
                "url": it.get("url", ""),
                "description": it.get("description", "")[:400],
                "engine": it.get("engine", ""),
            }
            for it in items
        ]
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(trimmed, ensure_ascii=False)},
        ]
        try:
            raw, usage = await model._stream_text(messages)
            await model._record_primogem(
                "", "风神", usage, purpose="订阅早报",
            )
        except Exception as e:
            logger.warning("[风神·订阅] LLM 早报失败，降级模板: {}", e)
            return _build_fallback_digest(query, items)

        text = raw.strip()
        # 清理可能的 code fence
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 2 and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()
        if not text:
            return _build_fallback_digest(query, items)
        return text
