"""岩神主类 ZhongliArchon：__init__ + 小方法 + 4 mixin（scan/skill/watch/digest）组合。

另有查询 API：`get_recommended / get_top / get_changes / get_stock_history / handle_query`
供 WebUI `/wealth` 面板、`dividend` tool 和 LLM 自然语言调用。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from paimon.archons.base import Archon
from paimon.archons.zhongli.scorer import (
    build_advice,
    build_reasons,
    classify_stock,
    score_stock,
)
from paimon.foundation.irminsul import (
    ChangeEvent,
    Irminsul,
    ScoreSnapshot,
    UserWatchPrice,
    WatchlistEntry,
)
from paimon.foundation.irminsul.task import Subtask, TaskEdict

from ._zhongli._digest import _DigestMixin
from ._zhongli._scan import _ScanMixin
from ._zhongli._skill import _SkillMixin
from ._zhongli._watch import _WatchMixin

# 模块级 helper 留在 _zhongli/_helpers.py 但可通过 paimon.archons.zhongli.zhongli re-export
from ._zhongli._helpers import (
    _aggregate_events, _apply_sector_caps, _classify_event_severity,
    _detect_changes, _result_to_snapshot, _score_single,
)

from paimon.llm.model import Model
from paimon.session import Session

if TYPE_CHECKING:
    from paimon.foundation.march import MarchService


# ============================================================
# 业务常量（属于岩神，不属于 skill）
# ============================================================

# 股息率硬门槛（full_scan 全市场扫描筛选）
MIN_DIVIDEND_YIELD = 0.04
# 连续分红年数硬门槛
MIN_HISTORY_COUNT = 5
# 流通市值前置过滤（元；full_scan 全市场扫描用，避免给 5800 只全拉 dividend）
MIN_MARKET_CAP = 100_0000_0000     # 100 亿
# watchlist 容量 + 行业均衡
WATCHLIST_SIZE = 25
MAX_PER_INDUSTRY = 5
MAX_INDUSTRIES = 10

# skill CLI 入口
_SKILL_MAIN_PY = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "skills" / "dividend-tracker" / "main.py"
)

# subprocess 活性超时：连续 5 分钟无 stderr 活动才 kill。
# 旧版用全程死线（fetch-board 1800s），但 BaoStock 单连接串行 + 网络方差大 →
# 5500 只行情快则 6 分钟、慢则 60 分钟，单一阈值无法兼顾。改为活性判定后，
# 只要 skill 还在打进度日志（每 500 只一条 board / 每 20 只一条 dividend）
# 就续命；真卡住才 kill。
_SKILL_IDLE_TIMEOUT = 5 * 60


_SYSTEM_PROMPT = """\
你是岩神·摩拉克斯，掌管契约与财富。你的职责是理财分析。

能力：
1. 红利股分析、资产配置建议、退休规划
2. 用 exec 工具执行 curl 查询市场数据（备用；主要数据由岩神自动采集）

规则：
1. 所有投资建议必须注明"仅供参考，不构成投资建议"
2. 数据要标明来源和时间
3. 输出结构化结果
4. 调用工具时不要输出过程描述，只输出最终结果
"""


# ============================================================
# 业务辅助函数（原 tracker.py）


class ZhongliArchon(_ScanMixin, _SkillMixin, _WatchMixin, _DigestMixin, Archon):
    """岩神·摩拉克斯：契约与财富——红利股扫描 + 评分 + 推送 archon。"""

    name = "岩神"
    description = "红利股扫描 + 评分 + /wealth 面板 + dividend cron"
    allowed_tools: set[str] = set()

    # 最近一次扫描错误的展示窗口（超过此时间的旧错误不再返给前端）
    # e037ba1 拆子包时漏定义此属性，但 get_last_error() 引用它 → wealth_running_api 崩
    _LAST_ERROR_WINDOW_SECONDS = 3600  # 1 小时

    # 用户关注股首次建底拉取多少年的历史日 K（_watch.py:100 引用）
    # 同一拆子包漏迁移问题：常量定义遗失，调到首次添加股票路径就 AttributeError
    _USER_WATCH_INIT_YEARS = 5

    def __init__(self):
        self._scan_lock = asyncio.Lock()
        # 当前扫描进度（供 /api/wealth/running 暴露给前端状态条）。
        # None = 未在扫描；扫描中至少包含 {stage, cur, total, started_at, updated_at}，
        # 各阶段（board/board_codes/dividend/financial/scoring）可附带额外字段如
        # valid/success/mode 等。
        self._progress: dict | None = None
        # 最近一次扫描失败信息（供前端红色横幅展示）。
        # 成功完成会清空；超过 _LAST_ERROR_WINDOW_SECONDS 不再返回。
        self._last_error: dict | None = None

    def is_scanning(self) -> bool:
        """是否正在跑扫描（supply 给 WebUI/tool 做并发保护）。"""
        return self._scan_lock.locked()

    def get_progress(self) -> dict | None:
        """当前扫描进度快照（None 表示未在跑）。"""
        return self._progress

    def get_last_error(self) -> dict | None:
        """最近窗口内的扫描失败信息；超出窗口返回 None。"""
        if not self._last_error:
            return None
        age = time.time() - self._last_error.get("ts", 0)
        if age > self._LAST_ERROR_WINDOW_SECONDS:
            return None
        return {**self._last_error, "age_seconds": int(age)}

    def _set_progress(self, stage: str, cur: int, total: int, **extra) -> None:
        now = time.time()
        prev = self._progress or {}
        self._progress = {
            "stage": stage,
            "cur": cur,
            "total": total,
            "started_at": prev.get("started_at", now),
            "updated_at": now,
            **extra,
        }

    # ---------- 事件持久化（供 _full_scan/_daily_update/_rescore 调）----------

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        # v6 解耦：execute 内部"通用理财 tool-loop"已移除（搬到 paimon/shades/worker/）
        # asmoday 不再调本节点；保留方法签名仅为满足 Archon ABC 约定
        # 非四影功能（collect_dividend / scorer / handle_query / cron / /wealth 面板）全部保留
        return f"[{self.name}] execute 路径已解耦（v6），请参考 docs/archons/zhongli.md"

    # ---------- 红利股采集主入口（cron 驱动）----------

    async def collect_dividend(
        self, *, mode: str,
        irminsul: Irminsul,
        march: "MarchService",
        chat_id: str = "", channel_name: str = "",
    ) -> None:
        """采集入口。mode ∈ 'full' / 'daily' / 'rescore'。"""
        if mode not in ("full", "daily", "rescore"):
            logger.error("[岩神·采集] 未知 mode: {}", mode)
            return

        async with self._scan_lock:
            logger.info("[岩神·采集] 开始 mode={}", mode)
            self._set_progress("init", 0, 0, mode=mode)
            # 进入新扫描时清空上次失败记录（成功覆盖；失败再 set 也行）
            self._last_error = None
            try:
                try:
                    if mode == "full":
                        result = await self._full_scan(irminsul)
                    elif mode == "daily":
                        result = await self._daily_update(irminsul)
                    else:
                        result = await self._rescore(irminsul)
                except Exception as e:
                    logger.exception("[岩神·采集] 失败 mode={}: {}", mode, e)
                    self._last_error = {
                        "ts": time.time(),
                        "mode": mode,
                        "message": str(e)[:500],
                    }
                    return

                if not result or not result.get('stocks'):
                    logger.info("[岩神·采集] 完成（无新数据） mode={}", mode)
                    return

                # 推送日报（digest · markdown）—— source="岩神·理财日报"
                # dedup_per_day=True：当日多次扫描（cron 19:00 + 手动日更/重评分）
                # 复用同一条公告卡片，内容变就更新+置顶+重置未读，不变只 bump 时间戳。
                # extra 塞 {p0_count, p1_count, ...} 供 /api/wealth/stats 查近 7 天统计
                if channel_name and chat_id:
                    try:
                        events = result.get('events') or {'p0': [], 'p1': [], 'p2': []}
                        digest_md, meta = self._compose_daily_digest(mode, result, events)
                        await march.ring_event(
                            channel_name=channel_name, chat_id=chat_id,
                            source="岩神·理财日报", message=digest_md,
                            extra=meta, dedup_per_day=True,
                        )
                    except Exception as e:
                        logger.error("[岩神·推送] 失败: {}", e)

                p0n = len((result.get('events') or {}).get('p0') or [])
                p1n = len((result.get('events') or {}).get('p1') or [])
                logger.info(
                    "[岩神·采集] 完成 mode={} qualified={} recommended={} changes={} p0={} p1={}",
                    mode, len(result['stocks']), len(result.get('recommended', [])),
                    len(result.get('changes', [])), p0n, p1n,
                )

                # 用户关注股：full/daily 触网才抓；rescore 纯 cache 跳过
                if mode in ("full", "daily"):
                    try:
                        await self.collect_user_watchlist(
                            irminsul, march=march,
                            chat_id=chat_id, channel_name=channel_name,
                        )
                    except Exception as e:
                        logger.exception("[岩神·关注股] 采集失败: {}", e)
            finally:
                # 任何路径结束（成功/失败/无数据）都清进度，避免前端一直"采集中"
                self._progress = None

    async def get_recommended(self, irminsul: Irminsul) -> list[ScoreSnapshot]:
        return await irminsul.snapshot_latest_for_watchlist()

    async def get_top(self, n: int, irminsul: Irminsul) -> list[ScoreSnapshot]:
        return await irminsul.snapshot_latest_top(n)

    async def get_changes(self, days: int, irminsul: Irminsul) -> list[ChangeEvent]:
        return await irminsul.change_recent(days)

    async def get_stock_history(
        self, code: str, days: int, irminsul: Irminsul,
    ) -> list[ScoreSnapshot]:
        return await irminsul.snapshot_history(code, days)

    async def handle_query(self, text: str, irminsul: Irminsul) -> str:
        """自然语言查询分派（/dividend 指令 + dividend tool 共用）。
        与 fairy tracker.py handle_query 等价（改为读世界树）。"""
        desc = (text or "").lower()

        if "排行" in desc or "排名" in desc or "top" in desc:
            rows = await self.get_top(100, irminsul)
            return self._format_ranking(rows) if rows else "暂无数据，请先跑 /dividend run-daily"

        if "推荐" in desc or "选股" in desc:
            recs = await self.get_recommended(irminsul)
            return self._format_recommended_snapshots(recs) if recs else "暂无推荐，请先跑 /dividend run-full"

        if "变化" in desc or "动态" in desc:
            chs = await self.get_changes(7, irminsul)
            return self._format_changes_list(chs) if chs else "最近 7 天无显著变化"

        if "详情" in desc or "趋势" in desc or "历史" in desc:
            code = _extract_code(desc)
            if code:
                history = await self.get_stock_history(code, 90, irminsul)
                return self._format_history(code, history)
            return "请指定 6 位股票代码（如：601988 历史）"

        # 默认：推荐 + 排行
        recs = await self.get_recommended(irminsul)
        top = await self.get_top(100, irminsul)
        parts: list[str] = []
        if recs:
            parts.append(self._format_recommended_snapshots(recs))
        if top:
            parts.append(self._format_ranking(top))
        return '\n\n'.join(parts) if parts else "暂无数据，请先跑 /dividend run-daily"

    # ---------- snapshot 文本格式化（handle_query 用）----------

    @staticmethod
    def _format_recommended_snapshots(rows: list[ScoreSnapshot]) -> str:
        n = len(rows)
        lines = [f"推荐选股（{n} 只，行业均衡）", "=" * 40]
        for i, r in enumerate(rows, 1):
            dy = r.dividend_yield * 100
            cap_yi = (r.market_cap or 0) / 1e8
            lines.append(
                f"{i}. {r.stock_name}({r.stock_code}) {r.industry} "
                f"· 评分{r.total_score:.1f} · 股息率{dy:.1f}% "
                f"· PE{r.pe:.1f} · 市值{cap_yi:.0f}亿"
            )
            if r.advice:
                lines.append(f"   {r.advice}")
        return '\n'.join(lines)

    @staticmethod
    def _format_ranking(rows: list[ScoreSnapshot]) -> str:
        n = len(rows)
        lines = [f"评分排行 TOP {n}", "=" * 40]
        for i, r in enumerate(rows, 1):
            dy = r.dividend_yield * 100
            cap_yi = (r.market_cap or 0) / 1e8
            lines.append(
                f"{i}. {r.stock_name}({r.stock_code}) {r.industry} "
                f"· {r.total_score:.1f} · 股息率{dy:.1f}% "
                f"· PE{r.pe:.1f} · PB{r.pb:.2f} · 市值{cap_yi:.0f}亿"
            )
            if r.reasons:
                for reason in r.reasons.split('\n'):
                    if reason.strip():
                        lines.append(f"     {reason.strip()}")
        return '\n'.join(lines)

    @staticmethod
    def _format_changes_list(changes: list[ChangeEvent]) -> str:
        lines = ["红利股最近变化"]
        for c in changes:
            lines.append(
                f"[{c.event_type}] {c.stock_name}({c.stock_code}) — {c.description}"
            )
        return '\n'.join(lines)

    @staticmethod
    def _format_history(code: str, history: list[ScoreSnapshot]) -> str:
        if not history:
            return f"{code} 无历史评分数据"
        lines = [f"{code} 历史评分趋势（近 {len(history)} 条）"]
        for h in history:
            lines.append(
                f"  {h.scan_date} · 总分 {h.total_score:.1f}"
                f" | 可持续 {h.sustainability_score:.0f}"
                f" | 财务 {h.fortress_score:.0f}"
                f" | 估值 {h.valuation_score:.0f}"
                f" | 记录 {h.track_record_score:.0f}"
                f" | 动能 {h.momentum_score:.0f}"
            )
        return '\n'.join(lines)



# ---- 模块级注册函数（实现在 _zhongli/_register.py）----
from ._zhongli._register import (  # noqa: E402
    _extract_code,
    clear_stock_subscriptions,
    ensure_stock_subscriptions,
    register_subscription_types,
    register_task_types,
)
