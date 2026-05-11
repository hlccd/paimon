"""水神·游戏资讯（覆盖式 cron collector）。

跑 topic skill subprocess 拿 bili+xhs 30 天 UGC markdown，按 game 写入
mihoyo_game_news 单条覆盖表。**不**走 push_archive / ring_event / feed_items —
不再"按天累加推送给用户"，只在 /game 面板展示最新一份。

每个绑定的米哈游账号都挂 mihoyo_game_collect cron 调本函数；
按 game 主键覆盖意味着多账号场景下后跑的会覆盖前面的（内容相同所以无副作用，
但用户场景没多账号——本次设计假设单账号）。
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from loguru import logger


# game 代号 → 中文名（与 furina_game/_register.py:_GAME_DISPLAY 同步）
_GAME_DISPLAY: dict[str, str] = {
    "gs": "原神",
    "sr": "崩坏:星穹铁道",
    "zzz": "绝区零",
}

# topic 跑得慢，给 5 分钟超时（subprocess 内部调用 bili/xhs 网络可能卡）
_TOPIC_TIMEOUT_S = 300


async def _run_topic_subprocess(query: str) -> tuple[str, str]:
    """跑 skills/topic/scripts/research.py，返 (stdout, stderr)。

    超时直接 kill；失败抛异常给上层处理。
    """
    repo_root = Path(__file__).resolve().parents[3]
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
            f"topic exit={proc.returncode}: {stderr.decode('utf-8', errors='replace')[:500]}"
        )
    return (
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def run_furina_news_collect(sub, state) -> None:
    """水神·游戏资讯 cron 入口。

    替代原 venti.run_web_search_collect：用 topic（30 天 UGC）替代 SERP，
    覆盖式落 mihoyo_game_news 表（不再推 chat / 不按天累加）。

    sub.binding_id 形如 'gs:113975833'；本函数只取 game 部分。
    """
    if not state.irminsul:
        logger.error("[水神·资讯] state.irminsul 未就绪 sub={}", sub.id)
        return

    irminsul = state.irminsul
    binding_id = sub.binding_id or ""
    game = binding_id.split(":", 1)[0] if ":" in binding_id else binding_id
    if game not in _GAME_DISPLAY:
        logger.warning("[水神·资讯] 未知 game={} sub={}", game, sub.id)
        await irminsul.subscription_update(
            sub.id, actor="水神", last_run_at=time.time(),
            last_error=f"未知 game={game}",
        )
        return

    if not sub.enabled:
        logger.info("[水神·资讯] 订阅已禁用 sub={}", sub.id)
        return

    game_name = _GAME_DISPLAY[game]
    query = f"{game_name} 最新资讯"

    logger.info("[水神·资讯] 开始采集 game={} query={!r} sub={}", game, query, sub.id)
    t0 = time.time()
    try:
        markdown, _stderr = await _run_topic_subprocess(query)
    except Exception as e:
        logger.error("[水神·资讯] topic 失败 game={} err={}", game, e)
        await irminsul.subscription_update(
            sub.id, actor="水神", last_run_at=time.time(),
            last_error=str(e)[:500],
        )
        return

    duration_s = int(time.time() - t0)

    try:
        await irminsul.mihoyo_game_news_upsert(
            game=game, markdown=markdown, sources="bili,xhs", duration_s=duration_s,
        )
    except Exception as e:
        logger.error("[水神·资讯] 落库失败 game={} err={}", game, e)
        await irminsul.subscription_update(
            sub.id, actor="水神", last_run_at=time.time(),
            last_error=f"落库失败: {e}"[:500],
        )
        return

    await irminsul.subscription_update(
        sub.id, actor="水神", last_run_at=time.time(), last_error="",
    )
    logger.info(
        "[水神·资讯] 完成 game={} markdown={} chars duration={}s",
        game, len(markdown), duration_s,
    )
