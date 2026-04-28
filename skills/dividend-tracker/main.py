#!/usr/bin/env python3
"""dividend-tracker skill · 纯 I/O CLI

**职责边界**：只做 BaoStock 数据抓取 + JSON 输出，不含任何业务规则。
- 市值门槛 / 连续分红年数 / 行业分类权重 / 评分算法 → 全部归属岩神（paimon/archons/zhongli/）
- 本 CLI 只提供"抓数据"能力，由岩神 subprocess 调用并做业务判断

三个子命令：
  fetch-board                       抓全市场行情（industry + price/pe/pb/market_cap）
  fetch-dividend --codes=600519,...  批量抓股息历史（可传 --cached-only 只读缓存）
  fetch-financial --codes=...        批量抓财务指标（ROE/负债率/现金流等）

输出：UTF-8 JSON 到 stdout；日志 / 错误到 stderr
退出码：0 成功 / 2 参数错 / 3 BaoStock 失败
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 让脚本直接跑时能 import tracker.provider_baostock
_SKILL_DIR = Path(__file__).resolve().parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))


def _configure_runtime_logging() -> None:
    """被 paimon 拉起时（PAIMON_SKILL_RUNTIME=1）切极简 loguru format，
    让 paimon 主进程包前缀/时间戳，不再双重输出；
    独立调试时（无环境变量）保持丰富格式不变。"""
    if os.environ.get("PAIMON_SKILL_RUNTIME") != "1":
        return
    try:
        from loguru import logger as _bs_logger
        _bs_logger.remove()
        _bs_logger.add(sys.stderr, format="{message}", level="INFO")
    except Exception:
        pass


def _default_cache_dir() -> Path:
    return _SKILL_DIR / "data" / "cache"


async def _cmd_board(cache_dir: Path, codes: list[str] | None = None) -> dict:
    """抓行情（industry_map + market_data）。

    - codes 为空：全 A 股（~5800 只，耗时 15+ 分钟）
    - codes 非空：只抓指定股票（daily_update 场景，≤1 分钟）

    不做业务过滤——岩神自己按市值 / 股票代码前缀等筛选。
    """
    from tracker.provider_baostock import BaoStockDataProvider
    provider = BaoStockDataProvider(cache_dir)
    if codes:
        # 用 watchlist 精简列表抓（fairy fetch_stocks_by_codes 模式）
        stocks = [{"stock_code": c, "stock_name": "", "industry": ""} for c in codes]
        industry_map, market_data = await provider.fetch_stocks_by_codes(stocks)
    else:
        industry_map, market_data = await provider.fetch_board_stocks()
    return {
        "industry_map": industry_map,
        "market_data": market_data,
        "count": len(market_data),
    }


async def _cmd_dividend(cache_dir: Path, codes: list[str], cached_only: bool) -> dict:
    """批量抓股息历史。cached_only=True 时只读缓存（rescore 用）。"""
    from tracker.provider_baostock import BaoStockDataProvider
    provider = BaoStockDataProvider(cache_dir)
    if cached_only:
        results: dict[str, dict] = {}
        for code in codes:
            r = provider.load_cached_dividend(code)
            if r is not None:
                results[code] = r
        return {"dividends": results, "count": len(results), "total": len(codes)}

    results = await provider.fetch_dividend_batch(codes)
    return {"dividends": results, "count": len(results), "total": len(codes)}


async def _cmd_financial(cache_dir: Path, codes: list[str], cached_only: bool) -> dict:
    """批量抓财务指标。"""
    from tracker.provider_baostock import BaoStockDataProvider
    provider = BaoStockDataProvider(cache_dir)
    if cached_only:
        results: dict[str, dict] = {}
        for code in codes:
            r = provider.load_cached_financial(code)
            if r is not None:
                results[code] = r
        return {"financials": results, "count": len(results), "total": len(codes)}

    results = await provider.fetch_financial_batch(codes)
    return {"financials": results, "count": len(results), "total": len(codes)}


async def _cmd_cleanup_cache(cache_dir: Path) -> dict:
    """清过期缓存文件。"""
    from tracker.provider_baostock import BaoStockDataProvider
    provider = BaoStockDataProvider(cache_dir)
    provider.cleanup_expired_cache()
    return {"ok": True}


def _parse_codes(s: str) -> list[str]:
    codes = [c.strip() for c in (s or "").split(",")]
    return [c for c in codes if c]


async def _async_main(args: argparse.Namespace) -> int:
    cache_dir = Path(args.cache_dir).expanduser() if args.cache_dir else _default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        if args.cmd == "fetch-board":
            codes = _parse_codes(args.codes) if args.codes else None
            result = await _cmd_board(cache_dir, codes)
        elif args.cmd == "fetch-dividend":
            codes = _parse_codes(args.codes)
            if not codes:
                print("fetch-dividend: --codes 必填", file=sys.stderr)
                return 2
            result = await _cmd_dividend(cache_dir, codes, args.cached_only)
        elif args.cmd == "fetch-financial":
            codes = _parse_codes(args.codes)
            if not codes:
                print("fetch-financial: --codes 必填", file=sys.stderr)
                return 2
            result = await _cmd_financial(cache_dir, codes, args.cached_only)
        elif args.cmd == "cleanup-cache":
            result = await _cmd_cleanup_cache(cache_dir)
        else:
            print(f"未知子命令: {args.cmd}", file=sys.stderr)
            return 2
    except ConnectionError as e:
        # BaoStock 登录失败
        print(f"[skill·dividend-tracker] BaoStock 连接失败: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"[skill·dividend-tracker] 执行异常: {e}", file=sys.stderr)
        return 3

    # JSON 到 stdout；ensure_ascii=False 保留中文；无 indent 紧凑输出（岩神解析）
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


def main() -> int:
    # stdout/stderr 强制 UTF-8（防 Windows cp936 炸中文）
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    _configure_runtime_logging()

    parser = argparse.ArgumentParser(
        prog="dividend-tracker",
        description="红利股数据抓取（纯 I/O；业务规则归岩神）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_board = sub.add_parser(
        "fetch-board",
        help="抓行情（industry + price/pe/pb/市值）；--codes 为空时抓全市场",
    )
    p_board.add_argument(
        "--codes", default="",
        help="逗号分隔股票代码；留空则全 A 股扫描（耗时 15+ 分钟）",
    )
    p_board.add_argument("--cache-dir", default=None, help="缓存目录（默认 skill 自带 data/cache）")

    p_div = sub.add_parser("fetch-dividend", help="批量抓股息历史")
    p_div.add_argument("--codes", required=True, help="逗号分隔股票代码，如 600519,600900")
    p_div.add_argument("--cached-only", action="store_true", help="只读缓存（rescore 用）")
    p_div.add_argument("--cache-dir", default=None)

    p_fin = sub.add_parser("fetch-financial", help="批量抓财务指标")
    p_fin.add_argument("--codes", required=True, help="逗号分隔股票代码")
    p_fin.add_argument("--cached-only", action="store_true")
    p_fin.add_argument("--cache-dir", default=None)

    p_clean = sub.add_parser("cleanup-cache", help="清过期缓存文件")
    p_clean.add_argument("--cache-dir", default=None)

    args = parser.parse_args()

    import asyncio
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
