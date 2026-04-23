#!/usr/bin/env python3
"""web-search skill · 主入口。

用法：
    python3 search.py "query"                              # 默认双引擎并发
    python3 search.py "query" --engine bing --limit 5
    python3 search.py "query" --engines bing,baidu --limit 10
    python3 search.py --fetch "https://..."                # 抓取单 URL 正文

输出：
    默认 stdout 一个 JSON 数组（fields: title/url/description/engine）
    数组可能为空但格式保持合法；stderr 给引擎级错误

退出码：
    0  正常结束（引擎成功返回，但结果可能为空）
    2  参数错误
    3  所有引擎都失败
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# Windows 控制台默认 GBK，输出里的 Unicode 空格 / 特殊字符会直接炸；
# 强制 stdout/stderr 用 UTF-8（Python 3.7+ 可 reconfigure）
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

# 允许脚本直接跑（不依赖 PYTHONPATH）
sys.path.insert(0, str(Path(__file__).parent))
from engines import ENGINES  # noqa: E402


def _normalize_url(url: str) -> str:
    """URL 规范化用于跨引擎去重。

    - 去 fragment / trailing slash
    - utm_* / spm_* / 等跟踪参数剥掉
    - scheme 归一 http→https（多数主站已强制 HTTPS）
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    # 过滤跟踪参数
    if parts.query:
        kept = []
        for pair in parts.query.split("&"):
            if not pair:
                continue
            key = pair.split("=", 1)[0].lower()
            if key.startswith(("utm_", "spm_")) or key in ("fr", "from", "ref", "source"):
                continue
            kept.append(pair)
        query = "&".join(kept)
    else:
        query = ""

    path = parts.path.rstrip("/")
    scheme = "https" if parts.scheme == "http" else parts.scheme

    return urlunsplit((scheme, parts.netloc.lower(), path, query, ""))


async def _run_engine(engine_mod, query: str, limit: int) -> tuple[str, list[dict], str | None]:
    """跑一个引擎，返回 (engine_name, results, error_msg)。吞所有异常。"""
    name = engine_mod.__name__.rsplit(".", 1)[-1]
    try:
        results = await engine_mod.search(query, limit)
        return name, results, None
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        if os.getenv("WEBSEARCH_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
        return name, [], err


async def search(
    query: str, engine_keys: list[str], limit: int,
) -> tuple[list[dict], bool]:
    """跨引擎并发 + 合并去重。

    返回 (results, all_failed)：
      - all_failed=True 表示所有引擎都抛异常（调用方应返退出码 3）
      - all_failed=False 且 results=[] 表示引擎们都正常但恰好没命中结果
    """
    engines_mods = []
    for k in engine_keys:
        mod = ENGINES.get(k)
        if mod is None:
            print(f"[search.py] 未知引擎: {k}", file=sys.stderr)
            continue
        engines_mods.append(mod)

    if not engines_mods:
        # 没有可用引擎等同于"全失败"
        return [], True

    # 每个引擎拉 limit 条，合并后再截 limit
    tasks = [_run_engine(e, query, limit) for e in engines_mods]
    outcomes = await asyncio.gather(*tasks)

    # 打印错误到 stderr（每个引擎一行）
    failed_count = 0
    for name, results, err in outcomes:
        if err:
            print(f"[search.py] engine={name} 失败: {err}", file=sys.stderr)
            failed_count += 1

    all_failed = failed_count == len(outcomes)

    # 合并 + 按 URL 规范化去重，保留首次出现的（按 engine_keys 顺序优先）
    seen: set[str] = set()
    merged: list[dict] = []
    # 按请求顺序遍历每个引擎的结果，保持引擎偏好
    for requested in engine_keys:
        for name, results, _ in outcomes:
            if name != requested:
                continue
            for r in results:
                key = _normalize_url(r.get("url", ""))
                if not key or key in seen:
                    continue
                seen.add(key)
                merged.append(r)

    return merged[:limit], all_failed


async def fetch_url(url: str, max_chars: int = 20000) -> dict:
    """抓取单个 URL 正文（简版，和 paimon.tools.builtin.web_fetch 能力对等）。"""
    import httpx
    from bs4 import BeautifulSoup

    async with httpx.AsyncClient(
        timeout=30.0, follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/133.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "lxml")
    # 去脚本 / 样式
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n... [truncated，共 {len(text)} 字符]"

    title_el = soup.find("title")
    title = title_el.get_text(strip=True) if title_el else ""

    return {
        "url": str(resp.url),
        "title": title,
        "content": text,
    }


def parse_engines(engine: str | None, engines: str | None) -> list[str]:
    """解析 --engine / --engines 参数。默认双引擎。"""
    if engines:
        return [e.strip() for e in engines.split(",") if e.strip()]
    if engine:
        return [engine.strip()]
    return ["bing", "baidu"]


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="search.py",
        description="web-search skill 主入口",
    )
    ap.add_argument("query", nargs="?", help="搜索查询（若无则必须用 --fetch）")
    ap.add_argument("--engine", help="单引擎：bing / baidu")
    ap.add_argument("--engines", help="多引擎逗号分隔，如 bing,baidu")
    ap.add_argument("--limit", type=int, default=10, help="返回结果数（1-50，默认 10）")
    ap.add_argument("--fetch", help="改为抓取指定 URL 正文（忽略 query/engine）")
    args = ap.parse_args()

    # 参数校验
    if args.fetch:
        if not args.fetch.startswith(("http://", "https://")):
            print("[search.py] --fetch 必须是 http(s) URL", file=sys.stderr)
            return 2
        result = asyncio.run(fetch_url(args.fetch))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if not args.query:
        print("[search.py] 缺少 query 参数（或使用 --fetch）", file=sys.stderr)
        return 2

    if not (1 <= args.limit <= 50):
        print("[search.py] --limit 必须在 [1, 50] 范围", file=sys.stderr)
        return 2

    engine_keys = parse_engines(args.engine, args.engines)
    if not engine_keys:
        print("[search.py] 必须至少指定一个引擎", file=sys.stderr)
        return 2

    results, all_failed = asyncio.run(search(args.query, engine_keys, args.limit))

    # 始终输出合法 JSON；空结果并非失败，引擎级异常才是
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 3 if all_failed else 0


if __name__ == "__main__":
    sys.exit(main())
