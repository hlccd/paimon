"""三月通用工具：cron next 计算、当地日期边界、调度服务模块级常量。"""
from __future__ import annotations

import time


# 轮询粒度：每分钟的 :00 对齐
# 设计取舍：多数定时场景（新闻、股价、提醒）精度到分钟已经足够；
# 对齐 :00 之后，`cron * * * * *` / `interval=60` 都会在整分钟触发，日志时间戳整齐好读。
POLL_INTERVAL = 60
MAX_FAILURES = 3
# interval 下限：小于 60s 的设置会被提升到 60s，避免虚假的高精度预期
MIN_INTERVAL = 60

# 事件响铃限流（内存滑动窗口）：每个 (source, channel, chat_id) 60s 最多 10 条
# docs/foundation/march.md §推送响铃
RING_EVENT_WINDOW_SECONDS = 60
RING_EVENT_MAX_PER_WINDOW = 10


def today_local_bounds(now: float | None = None) -> tuple[float, float]:
    """返回当地时区今天 [00:00, 次日 00:00) 的 unix 秒区间。

    用于 ring_event(dedup_per_day=True) 计算日级幂等键。与前端的
    `new Date(Y, M-1, D, 0,0,0).getTime()/1000` 保持一致（同机器时区）。
    """
    t = time.time() if now is None else now
    lt = time.localtime(t)
    midnight = time.mktime(
        (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, lt.tm_isdst)
    )
    return midnight, midnight + 86400


def _cron_next(expr: str, base_ts: float) -> float:
    """计算 cron 表达式相对 base_ts 的下次触发 unix 时间戳。

    必须显式用 timezone-aware datetime 喂给 croniter——否则 croniter 把 cron
    解析为 UTC 而非系统本地时区（即使系统 timezone 已正确配置）。
    举例：cron '0 12 * * *' 在中国大陆 (UTC+8) 应返回北京时间 12:00 unix，
    但如果传 unix timestamp 或 naive datetime，会返回 UTC 12:00 (= 北京 20:00)。
    """
    from datetime import datetime
    from croniter import croniter

    # astimezone() 无参数 = 用系统本地时区，结果是 timezone-aware datetime
    base_dt = datetime.fromtimestamp(base_ts).astimezone()
    nxt_dt = croniter(expr, base_dt).get_next(datetime)
    return nxt_dt.timestamp()
