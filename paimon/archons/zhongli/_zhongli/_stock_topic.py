"""岩神·关注股 topic 资讯 collector：跑 topic skill 拉 UGC，落 push_archive。

binding_kind='stock_watch' 的订阅走这里：
- 直接调 skills/topic/scripts/research.py subprocess（同水神 furina/news.py），跳 LLM 综合
- query 直接用股票名（不再加'公告 资讯'后缀）
- markdown 通过 march.ring_event 落 push_archive，source='岩神·stock_watch:CODE'
- 前端 /wealth 资讯 tab 按 source 过滤展示

时间预算：topic subprocess 30-60s（bili+xhs UGC 抓取）。
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from uuid import uuid4

from loguru import logger


_TOPIC_TIMEOUT_S = 300


async def _run_topic_subprocess(query: str) -> tuple[str, str]:
    """跑 skills/topic/scripts/research.py，返 (stdout, stderr)。"""
    repo_root = Path(__file__).resolve().parents[4]
    script = repo_root / "skills" / "topic" / "scripts" / "research.py"

    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(script), query,
        "--sources", "bili,xhs", "--days", "30", "--emit", "md",
        cwd=str(repo_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_TOPIC_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"topic 超时（>{_TOPIC_TIMEOUT_S}s）：{query!r}")
    if proc.returncode != 0:
        raise RuntimeError(
            f"topic exit={proc.returncode}: "
            f"{stderr.decode('utf-8', errors='replace')[:500]}"
        )
    return (
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def run_stock_topic_collect(sub, state) -> None:
    """关注股 topic 资讯订阅 cron 入口。

    sub.binding_id = stock_code；用 user_watch_get 拿 stock_name 当 query。
    走 push_archive，source 形如 '岩神·stock_watch:600519'，前端按此过滤。
    """
    if not state.irminsul or not state.march:
        logger.error("[岩神·关注股 topic] state 未就绪 sub={}", sub.id)
        return
    if not sub.enabled:
        logger.info("[岩神·关注股 topic] 订阅已禁用 sub={}", sub.id)
        return

    irminsul = state.irminsul
    march = state.march
    code = (sub.binding_id or "").strip()
    if not code:
        logger.warning("[岩神·关注股 topic] 无 stock_code sub={}", sub.id)
        await irminsul.subscription_update(
            sub.id, actor="岩神", last_run_at=time.time(),
            last_error="binding_id 为空",
        )
        return

    stock_name = ""
    try:
        entry = await irminsul.user_watch_get(code)
        if entry:
            stock_name = (entry.stock_name or "").strip()
    except Exception as e:
        logger.warning("[岩神·关注股 topic] 拿股票名失败 code={} err={}", code, e)

    query = stock_name or code
    if not query:
        await irminsul.subscription_update(
            sub.id, actor="岩神", last_run_at=time.time(),
            last_error="股票名 + 代码均为空",
        )
        return

    source_label = f"岩神·stock_watch:{code}"
    logger.info(
        "[岩神·关注股 topic] 开始采集 sub={} code={} query={!r}",
        sub.id, code, query,
    )
    t0 = time.time()
    try:
        markdown, _stderr = await _run_topic_subprocess(query)
    except Exception as e:
        logger.error("[岩神·关注股 topic] topic 失败 code={} err={}", code, e)
        await irminsul.subscription_update(
            sub.id, actor="岩神", last_run_at=time.time(),
            last_error=str(e)[:500],
        )
        return

    duration_s = int(time.time() - t0)
    markdown = (markdown or "").strip()
    if not markdown:
        logger.warning("[岩神·关注股 topic] topic 返回空 sub={}", sub.id)
        await irminsul.subscription_update(
            sub.id, actor="岩神", last_run_at=time.time(),
            last_error="topic 返回空内容",
        )
        return

    # topic brief 末尾的「## 各源采集情况」段对前端展示噪声大，截掉（同水神资讯）
    idx = markdown.find("## 各源采集情况")
    display_md = markdown[:idx].rstrip() + "\n" if idx >= 0 else markdown

    digest_id = uuid4().hex[:12]
    try:
        await march.ring_event(
            channel_name=sub.channel_name,
            chat_id=sub.chat_id,
            source=source_label,
            message=display_md,
            extra={
                "sub_id": sub.id,
                "binding_kind": sub.binding_kind,
                "binding_id": sub.binding_id,
                "stock_code": code,
                "stock_name": stock_name,
                "query": query,
                "digest_id": digest_id,
                "duration_s": duration_s,
            },
            dedup_per_day=True,
        )
    except Exception as e:
        logger.error("[岩神·关注股 topic] ring_event 失败 sub={} err={}", sub.id, e)

    await irminsul.subscription_update(
        sub.id, actor="岩神", last_run_at=time.time(), last_error="",
    )
    logger.info(
        "[岩神·关注股 topic] 完成 sub={} code={} markdown={} chars duration={}s",
        sub.id, code, len(display_md), duration_s,
    )
