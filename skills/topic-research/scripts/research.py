#!/usr/bin/env python3
"""topic-research CLI 入口。

用法：
    python3 research.py "<topic>" [--sources bili,xhs] [--days 30]
                                  [--emit md|json|both] [--output-dir DIR]

示例：
    python3 skills/topic-research/scripts/research.py "Claude 4.7" --emit md
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from lib import bili as bili_mod
from lib import discover as discover_mod
from lib import log
from lib import render as render_mod
from lib import score as score_mod
from lib import xhs as xhs_mod
from lib.dates import date_window
from lib.schema import Item, Report

_SOURCE_TABLE = {
    "bili": bili_mod.collect,
    "xhs":  xhs_mod.collect,
}

_DEFAULT_CACHE = Path.home() / ".paimon" / "skills" / "topic-research" / "cache"


def _slug(topic: str) -> str:
    s = re.sub(r"\s+", "-", topic.strip())
    s = re.sub(r"[^\w一-鿿\-]", "", s, flags=re.UNICODE)
    return s[:60] or "untitled"


def run(
    topic: str,
    sources: list[str],
    days: int,
    output_dir: Path,
    discover_limit: int = 20,
    enrich_limit: int = 15,
) -> Report:
    range_from, range_to = date_window(days)
    log.info(f"topic={topic!r} sources={sources} 窗口={range_from}~{range_to}")

    items_by_source: dict[str, list[Item]] = {}
    errors: dict[str, str] = {}

    for src in sources:
        collect_fn = _SOURCE_TABLE.get(src)
        if not collect_fn:
            errors[src] = f"未知 source: {src}"
            continue
        try:
            items = collect_fn(topic, range_from, range_to, limit=enrich_limit)
            items_by_source[src] = items
            if not items:
                errors[src] = "无结果"
        except Exception as e:
            log.warn(f"{src} collector 异常: {type(e).__name__}: {e}")
            items_by_source[src] = []
            errors[src] = f"{type(e).__name__}: {e}"

    score_mod.score_items(items_by_source, range_from, range_to)
    ranked = score_mod.rank(items_by_source, top_n=30)

    report = Report(
        topic=topic,
        range_from=range_from,
        range_to=range_to,
        generated_at=_dt.datetime.now().isoformat(timespec="seconds"),
        items_by_source=items_by_source,
        ranked=ranked,
        errors=errors,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "report.md"
    json_path = output_dir / "report.json"
    md_path.write_text(render_mod.to_markdown(report), encoding="utf-8")
    json_path.write_text(render_mod.to_json(report), encoding="utf-8")
    log.info(f"产物: {md_path} / {json_path}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="topic-research: 中文多源舆情调研")
    ap.add_argument("topic", help="调研主题")
    ap.add_argument("--sources", default="bili,xhs",
                    help="逗号分隔的 source 列表，默认 bili,xhs")
    ap.add_argument("--days", type=int, default=30, help="时间窗（天），默认 30")
    ap.add_argument("--emit", choices=("md", "json", "both"), default="md",
                    help="标准输出格式：md / json / both")
    ap.add_argument("--output-dir", type=Path, default=None,
                    help="产物落盘目录（默认 ~/.paimon/skills/topic-research/cache/<slug>/）")
    ap.add_argument("--discover-limit", type=int, default=20)
    ap.add_argument("--enrich-limit", type=int, default=15)
    args = ap.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    if not sources:
        ap.error("--sources 不能为空")

    output_dir = args.output_dir or (_DEFAULT_CACHE / _slug(args.topic))
    report = run(
        args.topic, sources, args.days, output_dir,
        discover_limit=args.discover_limit, enrich_limit=args.enrich_limit,
    )

    if args.emit in ("md", "both"):
        sys.stdout.write(render_mod.to_markdown(report))
    if args.emit == "json":
        sys.stdout.write(render_mod.to_json(report))
    elif args.emit == "both":
        sys.stdout.write("\n\n---\n\n")
        sys.stdout.write(render_mod.to_json(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
