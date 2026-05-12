"""风神 · 每日热点子包。

模块结构：
- _models.py     —— HotItem / CollectResult / SOURCE_LABELS
- sources/       —— 各源 collector（bili/hn/zhihu/weibo）
- _compose_daily.py —— 每日 LLM 综合
- service.py     —— run_daily_hotspot_collect cron 入口
"""
from .service import run_daily_hotspot_collect, run_weekly_hotspot_collect

__all__ = ["run_daily_hotspot_collect", "run_weekly_hotspot_collect"]
