"""BaoStock 数据源 — 红利股跟踪的唯一数据提供者

BaoStock 使用独立服务器（public-api.baostock.com），免费无限额，
在本地和云服务器环境均可正常运行。
"""
from __future__ import annotations

import json
import sys
import time
import asyncio
import threading
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd
from loguru import logger

from .provider import CACHE_TTL, _load_cache, _load_cache_any_age, _save_cache


def _emit_progress(stage: str, cur: int, total: int, **extra) -> None:
    """结构化进度行 → stderr，供 paimon 主进程解析（被 paimon 拉起时才有意义）。

    格式：``PROGRESS: {"stage":"board","cur":500,"total":5521,"valid":436}``。
    单独一行，不经 loguru，避免被前缀污染。
    """
    payload = {"stage": stage, "cur": cur, "total": total, **extra}
    try:
        print("PROGRESS: " + json.dumps(payload, ensure_ascii=False),
              file=sys.stderr, flush=True)
    except Exception:
        pass

# ============================================================
# BaoStock 全局会话管理（单连接，需加锁）
# ============================================================

_bs_lock = threading.Lock()
_bs_logged_in = False


def _bs_ensure_login():
    """确保 BaoStock 已登录（在 _bs_lock 内调用）"""
    global _bs_logged_in
    import baostock as bs
    if not _bs_logged_in:
        lg = bs.login()
        if lg.error_code != '0':
            raise ConnectionError(f"BaoStock login failed: {lg.error_msg}")
        _bs_logged_in = True


def _bs_call(fn):
    """线程安全地调用 BaoStock API"""
    with _bs_lock:
        _bs_ensure_login()
        return fn()


def _bs_get_data(rs) -> pd.DataFrame:
    """从 BaoStock ResultData 获取 DataFrame（兼容 pandas 2.0+）"""
    if rs.error_code != '0':
        return pd.DataFrame()
    try:
        return rs.get_data()
    except AttributeError as e:
        if "append" in str(e) and hasattr(rs, 'data') and hasattr(rs, 'fields'):
            if rs.data:
                return pd.DataFrame(rs.data, columns=rs.fields)
            return pd.DataFrame(columns=rs.fields if rs.fields else [])
        raise


# ============================================================
# 代码格式转换
# ============================================================

def _to_bscode(code: str) -> str:
    """601398 → sh.601398"""
    if code.startswith(('6', '5', '9')):
        return f'sh.{code}'
    return f'sz.{code}'


def _from_bscode(bscode: str) -> str:
    """sh.601398 → 601398"""
    return bscode[3:]


# ============================================================
# CSRC 行业 → 简化行业名映射（v3.0: 不再用于过滤，仅做名称映射）
# ============================================================

CSRC_INDUSTRY_MAP = {
    # 金融
    'J66货币金融服务': '银行',
    'J68保险业': '保险',
    'J67资本市场服务': '证券',
    'J69其他金融业': '金融',
    # 能源/资源
    'D44电力、热力生产和供应业': '电力',
    'B06煤炭开采和洗选业': '煤炭',
    'B07石油和天然气开采业': '石油',
    'C25石油、煤炭及其他燃料加工业': '石油',
    'B08黑色金属矿采选业': '钢铁',
    'C31黑色金属冶炼和压延加工业': '钢铁',
    'B09有色金属矿采选业': '有色金属',
    'C32有色金属冶炼和压延加工业': '有色金属',
    # 公用事业/交运
    'D45燃气生产和供应业': '燃气',
    'D46水的生产和供应业': '水务',
    'G54道路运输业': '交通运输',
    'G56管道运输业': '交通运输',
    'G55水上运输业': '交通运输',
    'G53铁路运输业': '交通运输',
    'G58装卸搬运和运输代理业': '交通运输',
    'G57航空运输业': '交通运输',
    # 消费
    'C15酒、饮料和精制茶制造业': '食品饮料',
    'C14食品制造业': '食品饮料',
    'C18纺织服装、服饰业': '纺织服装',
    'C13农副食品加工业': '食品饮料',
    # 制造
    'C38电气机械和器材制造业': '家用电器',
    'C39计算机、通信和其他电子设备制造业': '电子',
    'C26化学原料和化学制品制造业': '化工',
    'C27医药制造业': '医药',
    'C30非金属矿物制品业': '水泥',
    'C33金属制品业': '金属制品',
    'C34通用设备制造业': '机械设备',
    'C35专用设备制造业': '机械设备',
    'C36汽车制造业': '汽车',
    'C37铁路、船舶、航空航天和其他运输设备制造业': '运输设备',
    # 其他
    'K70房地产业': '房地产',
    'E47房屋建筑业': '建筑',
    'E48土木工程建筑业': '建筑',
    'A01农业': '农林牧渔',
    'A03畜牧业': '农林牧渔',
    'A05农、林、牧、渔服务业': '农林牧渔',
    'F51批发业': '商贸',
    'F52零售业': '商贸',
    'I63电信、广播电视和卫星传输服务': '通信',
    'I64互联网和相关服务': '互联网',
    'I65软件和信息技术服务业': '软件',
}


def _simplify_csrc_industry(csrc_name: str) -> str:
    """将 CSRC 行业代码转为简化行业名

    优先查映射表；未匹配时去掉前缀代码（如 'C38电气机械...' → '电气机械'）。
    """
    if csrc_name in CSRC_INDUSTRY_MAP:
        return CSRC_INDUSTRY_MAP[csrc_name]
    # 去掉前缀字母+数字
    import re
    m = re.match(r'^[A-Z]\d{2}(.+)$', csrc_name)
    return m.group(1) if m else csrc_name


# ============================================================
# 同步数据获取函数
# ============================================================

def _fetch_stock_price_sync(bscode: str) -> dict | None:
    """获取单只股票最新行情（价格/PE/PB/成交量/换手率）"""
    import baostock as bs

    today = date.today()
    start = (today - timedelta(days=10)).strftime('%Y-%m-%d')
    end = today.strftime('%Y-%m-%d')

    rs = _bs_call(lambda: bs.query_history_k_data_plus(
        bscode,
        fields='date,close,volume,turn,peTTM,pbMRQ,pcfNcfTTM,isST',
        start_date=start, end_date=end,
        frequency='d', adjustflag='3',
    ))
    df = _bs_get_data(rs)
    if df.empty:
        return None

    row = df.iloc[-1]

    def safe(col):
        v = row.get(col, '')
        if v == '' or pd.isna(v):
            return 0.0
        return float(v)

    close = safe('close')
    volume = safe('volume')
    turn = safe('turn')
    pe = safe('peTTM')
    pb = safe('pbMRQ')
    pcf = safe('pcfNcfTTM')
    is_st = int(safe('isST'))

    # 估算流通市值: BaoStock volume 单位是股（非手），turn 单位是 %
    # float_cap = volume / (turn% / 100) * close
    if turn > 0 and close > 0:
        float_cap = volume / (turn / 100) * close
    else:
        float_cap = 0

    return {
        'price': close,
        'pe': pe,
        'pb': pb,
        'market_cap': float_cap,
        'volume': volume,
        'turn': turn,
        'last_trade_date': str(row.get('date', '')),
        'pcf_ncf_ttm': pcf,
        'is_st': is_st,
    }


def _fetch_dividend_info_sync(code: str, cache_dir: Path) -> dict | None:
    """获取单只股票股息信息

    BaoStock dividend_data 字段：
    - dividCashPsBeforeTax: 每股税前派现金额（元），如 0.3064 = 每股0.3064元
      注意：这已经是每股金额，不需要再除以10
    - dividOperateDate: 除权除息日
    - dividPlanAnnounceDate: 分红方案公告日
    """
    import baostock as bs

    cache_path = cache_dir / f"{code}_dividend_bs.json"
    cached = _load_cache(cache_path, CACHE_TTL["dividend"])
    if cached is not None:
        return cached

    bscode = _to_bscode(code)
    now = date.today()
    current_year = now.year

    # 查最近 5 年的分红记录（用于 history_count 和找完整年度）
    all_records = []
    for year in range(current_year, current_year - 6, -1):
        rs = _bs_call(lambda y=year: bs.query_dividend_data(
            code=bscode, year=str(y), yearType='report',
        ))
        df = _bs_get_data(rs)
        if not df.empty:
            all_records.append(df)

    if not all_records:
        return None

    df = pd.concat(all_records, ignore_index=True)
    if df.empty:
        return None

    # 解析字段
    df['除息日'] = pd.to_datetime(df['dividOperateDate'], errors='coerce')
    df['公告日'] = pd.to_datetime(df['dividPlanAnnounceDate'], errors='coerce')
    df['每股派现'] = pd.to_numeric(df['dividCashPsBeforeTax'], errors='coerce')

    # 去重：同一除息日 + 同一金额只算一次（BaoStock 同一分红在不同阶段会出现多条记录）
    df_dedup = df.dropna(subset=['除息日', '每股派现']).drop_duplicates(
        subset=['dividOperateDate', 'dividCashPsBeforeTax'],
    )

    # --- 按财年归集分红（避免年度+中期跨财年叠加） ---
    # 规则：公告日 <= 6月 → FY(公告年-1) 年度分红；公告日 > 6月 → FY(公告年) 中期分红
    df_dedup = df_dedup.copy()
    df_dedup['announce_month'] = df_dedup['公告日'].dt.month
    df_dedup['announce_year'] = df_dedup['公告日'].dt.year
    df_dedup['fiscal_year'] = df_dedup.apply(
        lambda r: int(r['announce_year'] - 1) if pd.notna(r['announce_month']) and r['announce_month'] <= 6
                  else int(r['announce_year']) if pd.notna(r['announce_year']) else 0,
        axis=1,
    )
    df_dedup['is_annual'] = df_dedup['announce_month'].apply(
        lambda m: True if pd.notna(m) and m <= 6 else False
    )

    # 按财年汇总
    fy_totals: dict[int, float] = {}
    fy_has_annual: dict[int, bool] = {}
    for _, row in df_dedup.iterrows():
        fy = row['fiscal_year']
        dps = row.get('每股派现', 0)
        if fy <= 0 or pd.isna(dps) or dps <= 0:
            continue
        fy_totals[fy] = fy_totals.get(fy, 0) + float(dps)
        if row['is_annual']:
            fy_has_annual[fy] = True

    # 3 年平均 DPS：取最近 3 个有年度分红的完整财年
    annual_fys = sorted(
        [fy for fy in fy_totals if fy_has_annual.get(fy)], reverse=True,
    )[:3]
    avg_3y_dps = (
        sum(fy_totals[fy] for fy in annual_fys) / len(annual_fys)
        if annual_fys else 0.0
    )

    # 取最近两个有年度分红的完整财年（用于 DPS 增长率）
    total_dividend_per_share = 0.0
    prev_dividend_per_share = 0.0
    dividend_fy = 0
    for fy in sorted(fy_totals.keys(), reverse=True):
        if fy_has_annual.get(fy):
            if dividend_fy == 0:
                total_dividend_per_share = fy_totals[fy]
                dividend_fy = fy
            else:
                prev_dividend_per_share = fy_totals[fy]
                break

    # 回退：无完整财年时取最近有数据的
    if total_dividend_per_share <= 0 and fy_totals:
        latest_fy = max(fy_totals.keys())
        total_dividend_per_share = fy_totals[latest_fy]
        dividend_fy = latest_fy

    # --- 派息率：dividend_fy 的 DPS / 该年 EPS ---
    payout_ratio = 0.0
    if dividend_fy > 0 and total_dividend_per_share > 0:
        rs_profit = _bs_call(lambda y=dividend_fy: bs.query_profit_data(
            code=bscode, year=y, quarter=4,
        ))
        df_profit = _bs_get_data(rs_profit)
        if not df_profit.empty:
            eps_ttm = df_profit.iloc[0].get('epsTTM', '')
            if eps_ttm != '' and not pd.isna(eps_ttm):
                eps = float(eps_ttm)
                if eps > 0:
                    payout_ratio = total_dividend_per_share / eps

    # history_count: 去重后的总分红次数
    history_count = len(df_dedup) if not df_dedup.empty else len(df)

    # 该财年的分红记录数
    fy_records = df_dedup[df_dedup['fiscal_year'] == dividend_fy] if dividend_fy > 0 else df_dedup.tail(1)

    result = {
        'dividend_per_share': float(total_dividend_per_share),
        'avg_3y_dps': float(avg_3y_dps),
        'prev_dps': float(prev_dividend_per_share),
        'dividend_yield': 0.0,  # 占位，由 tracker 用当前股价计算
        'payout_ratio': float(payout_ratio),
        'latest_year': str(dividend_fy) if dividend_fy > 0 else '',
        'dividend_fy': str(dividend_fy) if dividend_fy > 0 else '',
        'status': '',
        'history_count': history_count,
        'recent_dividend_count': len(fy_records),
    }
    _save_cache(cache_path, result)
    return result


def _fetch_financial_info_sync(code: str, cache_dir: Path) -> dict | None:
    """获取单只股票财务信息（利润/成长/负债/现金流/业绩预告/盈利稳定性）"""
    import baostock as bs

    cache_path = cache_dir / f"{code}_financial_bs.json"
    cached = _load_cache(cache_path, CACHE_TTL["financial"])
    if cached is not None:
        return cached

    bscode = _to_bscode(code)
    current_year = date.today().year

    # 尝试最近的季度数据（Q4 → Q3 → Q2 → Q1）
    profit_data = None
    growth_data = None
    balance_data = None
    cashflow_data = None
    report_period = ''
    base_year = current_year
    base_quarter = 4

    for year in [current_year, current_year - 1]:
        for quarter in [4, 3, 2, 1]:
            if profit_data is not None:
                break
            rs = _bs_call(lambda y=year, q=quarter: bs.query_profit_data(
                code=bscode, year=y, quarter=q,
            ))
            df = _bs_get_data(rs)
            if not df.empty:
                profit_data = df.iloc[0]
                report_period = str(profit_data.get('statDate', ''))
                base_year = year
                base_quarter = quarter

                # 获取同期的成长、负债、现金流数据
                rs_g = _bs_call(lambda y=year, q=quarter: bs.query_growth_data(
                    code=bscode, year=y, quarter=q,
                ))
                df_g = _bs_get_data(rs_g)
                if not df_g.empty:
                    growth_data = df_g.iloc[0]

                rs_b = _bs_call(lambda y=year, q=quarter: bs.query_balance_data(
                    code=bscode, year=y, quarter=q,
                ))
                df_b = _bs_get_data(rs_b)
                if not df_b.empty:
                    balance_data = df_b.iloc[0]

                rs_cf = _bs_call(lambda y=year, q=quarter: bs.query_cash_flow_data(
                    code=bscode, year=y, quarter=q,
                ))
                df_cf = _bs_get_data(rs_cf)
                if not df_cf.empty:
                    cashflow_data = df_cf.iloc[0]
                break
        if profit_data is not None:
            break

    if profit_data is None:
        return None

    def safe(row, col):
        if row is None:
            return None
        v = row.get(col, '')
        if v == '' or pd.isna(v):
            return None
        return float(v)

    # BaoStock 数值是小数（0.094 = 9.4%），scorer 期望百分比（9.4）
    roe_avg = safe(profit_data, 'roeAvg')
    np_margin = safe(profit_data, 'npMargin')
    gp_margin = safe(profit_data, 'gpMargin')
    yoy_ni = safe(growth_data, 'YOYNI') if growth_data is not None else None
    yoy_revenue = safe(growth_data, 'YOYAsset') if growth_data is not None else None
    eps_yoy = safe(growth_data, 'YOYEPSBasic') if growth_data is not None else None
    # BaoStock 的 liabilityToAsset 字段数值异常（比实际值小100倍），
    # 改用 assetToEquity 反算: debt_ratio = (1 - 1/assetToEquity) * 100
    asset_to_equity = safe(balance_data, 'assetToEquity') if balance_data is not None else None
    current_ratio_val = safe(balance_data, 'currentRatio') if balance_data is not None else None

    # 现金流指标
    cfo_to_np = safe(cashflow_data, 'CFOToNP')
    ebit_to_interest = safe(cashflow_data, 'ebitToInterest')

    debt_ratio = None
    if asset_to_equity is not None and asset_to_equity > 0:
        debt_ratio = (1 - 1 / asset_to_equity) * 100

    # --- 3 年 Q4 净利润（盈利稳定性） ---
    # 如果 base_quarter != 4，说明当年 Q4 还没出，从上一年开始取
    stability_start = base_year if base_quarter == 4 else base_year - 1
    net_profits_3y = []
    for y in [stability_start, stability_start - 1, stability_start - 2]:
        rs_np = _bs_call(lambda yr=y: bs.query_profit_data(
            code=bscode, year=yr, quarter=4,
        ))
        df_np = _bs_get_data(rs_np)
        if not df_np.empty:
            np_val = safe(df_np.iloc[0], 'netProfit')
            net_profits_3y.append(np_val)
        else:
            net_profits_3y.append(None)

    # --- 业绩预告 ---
    forecast_type = None
    try:
        start_fc = f"{current_year - 1}-01-01"
        end_fc = f"{current_year}-12-31"
        rs_fc = _bs_call(lambda: bs.query_forecast_report(
            code=bscode, start_date=start_fc, end_date=end_fc,
        ))
        df_fc = _bs_get_data(rs_fc)
        if not df_fc.empty:
            forecast_type = str(df_fc.iloc[-1].get('profitForcastType', ''))
    except Exception:
        pass

    result = {
        'roe': roe_avg * 100 if roe_avg is not None else None,
        'roe_avg': roe_avg * 100 if roe_avg is not None else None,
        'roa': None,
        'net_margin': np_margin * 100 if np_margin is not None else None,
        'gross_margin': gp_margin * 100 if gp_margin is not None else None,
        'revenue_growth': yoy_revenue * 100 if yoy_revenue is not None else None,
        'profit_growth': yoy_ni * 100 if yoy_ni is not None else None,
        'eps_yoy': eps_yoy * 100 if eps_yoy is not None else None,
        'debt_ratio': debt_ratio,
        'current_ratio': current_ratio_val,
        'cfo_to_np': cfo_to_np,
        'interest_coverage': ebit_to_interest,
        'net_profits_3y': net_profits_3y,
        'forecast_type': forecast_type,
        'report_period': report_period,
    }
    _save_cache(cache_path, result)
    return result


# ============================================================
# BaoStockDataProvider — 异步接口
# ============================================================

class BaoStockDataProvider:
    """BaoStock 数据接口，接口与 DividendDataProvider 一致"""

    def __init__(self, cache_dir: Path):
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def fetch_board_stocks(self) -> tuple[dict[str, str], dict[str, dict]]:
        """获取全市场股票 + 行情数据（v3.0: 去掉行业白名单，全 A 股扫描）

        Returns:
            (industry_map, market_data)
            - industry_map: {code: industry}
            - market_data:  {code: {name, price, pe, pb, market_cap, industry}}
        """
        import baostock as bs
        loop = asyncio.get_running_loop()

        # 1. 获取所有股票的行业分类
        logger.info("[provider-bs] 获取全市场行业分类...")
        rs = await loop.run_in_executor(None, lambda: _bs_call(bs.query_stock_industry))
        all_stocks = _bs_get_data(rs)

        # 2. v3.0: 全 A 股扫描，不再按行业过滤
        dividend_stocks = all_stocks
        logger.info(f"[provider-bs] 全市场 {len(dividend_stocks)} 只股票，开始获取行情")

        industry_map: dict[str, str] = {}
        market_data: dict[str, dict] = {}

        # 3. 逐只获取最新行情（BaoStock 不支持批量查询）
        codes_list = list(dividend_stocks.itertuples(index=False))
        total = len(codes_list)

        for i, row in enumerate(codes_list, 1):
            bscode = row.code
            code = _from_bscode(bscode)
            name = row.code_name
            industry = _simplify_csrc_industry(row.industry)

            try:
                price_info = await loop.run_in_executor(
                    None, _fetch_stock_price_sync, bscode,
                )
            except Exception:
                price_info = None

            if price_info is None or price_info['price'] <= 0:
                continue

            industry_map[code] = industry
            market_data[code] = {
                'name': name,
                'price': price_info['price'],
                'pe': price_info['pe'],
                'pb': price_info['pb'],
                'market_cap': price_info['market_cap'],
                'industry': industry,
                'last_trade_date': price_info.get('last_trade_date', ''),
                'pcf_ncf_ttm': price_info.get('pcf_ncf_ttm', 0),
                'is_st': price_info.get('is_st', 0),
            }

            if i % 500 == 0 or i == total:
                logger.info(f"[provider-bs] 行情进度: {i}/{total}，已获取 {len(market_data)} 只")
                _emit_progress("board", i, total, valid=len(market_data))

        logger.info(f"[provider-bs] 行情获取完成: {total} 只扫描，{len(market_data)} 只有效数据")
        return industry_map, market_data

    async def fetch_stocks_by_codes(
        self, stocks: list[dict],
    ) -> tuple[dict[str, str], dict[str, dict]]:
        """只查指定股票的行情（日常更新用，避免查全行业 1000+ 只）

        Args:
            stocks: watchlist 记录列表，每项须含 stock_code, stock_name, industry
        Returns:
            (industry_map, market_data) — 格式同 fetch_board_stocks
        """
        loop = asyncio.get_running_loop()

        industry_map: dict[str, str] = {}
        market_data: dict[str, dict] = {}
        total = len(stocks)

        logger.info(f"[provider-bs] 获取 {total} 只 watchlist 股票行情...")

        for i, item in enumerate(stocks, 1):
            code = item['stock_code']
            name = item.get('stock_name', '')
            industry = item.get('industry', '未知')
            bscode = _to_bscode(code)

            try:
                price_info = await loop.run_in_executor(
                    None, _fetch_stock_price_sync, bscode,
                )
            except Exception:
                price_info = None

            if price_info is None or price_info['price'] <= 0:
                continue

            industry_map[code] = industry
            market_data[code] = {
                'name': name,
                'price': price_info['price'],
                'pe': price_info['pe'],
                'pb': price_info['pb'],
                'market_cap': price_info['market_cap'],
                'industry': industry,
                'last_trade_date': price_info.get('last_trade_date', ''),
                'pcf_ncf_ttm': price_info.get('pcf_ncf_ttm', 0),
                'is_st': price_info.get('is_st', 0),
            }

            if i % 20 == 0 or i == total:
                logger.info(f"[provider-bs] watchlist 行情: {i}/{total}，已获取 {len(market_data)} 只")
                _emit_progress("board_codes", i, total, valid=len(market_data))

        logger.info(f"[provider-bs] watchlist 行情完成，共 {len(market_data)} 只")
        return industry_map, market_data

    async def fetch_dividend_batch(
        self, codes: list[str], on_progress=None,
    ) -> dict[str, dict]:
        """批量获取股息信息（串行，BaoStock 不支持并发）"""
        loop = asyncio.get_running_loop()
        results: dict[str, dict] = {}
        total = len(codes)

        logger.info(f"[provider-bs] 开始获取股息数据: {total} 只...")

        for i, code in enumerate(codes, 1):
            try:
                r = await loop.run_in_executor(
                    None, _fetch_dividend_info_sync, code, self._cache_dir,
                )
                if r is not None:
                    results[code] = r
            except Exception:
                r = None

            if i % 20 == 0 or i == total:
                logger.info(f"[provider-bs] 股息进度: {i}/{total}，成功 {len(results)}")
                _emit_progress("dividend", i, total, success=len(results))
            if on_progress and r is not None:
                await on_progress(i, total, code, r)

        logger.info(f"[provider-bs] 股息数据完成: {len(results)}/{total} 只成功")
        return results

    async def fetch_financial_batch(
        self, codes: list[str], on_progress=None,
    ) -> dict[str, dict]:
        """批量获取财务信息（串行）"""
        loop = asyncio.get_running_loop()
        results: dict[str, dict] = {}
        total = len(codes)

        logger.info(f"[provider-bs] 开始获取财务数据: {total} 只...")

        for i, code in enumerate(codes, 1):
            try:
                r = await loop.run_in_executor(
                    None, _fetch_financial_info_sync, code, self._cache_dir,
                )
                if r is not None:
                    results[code] = r
            except Exception:
                r = None

            if i % 20 == 0 or i == total:
                logger.info(f"[provider-bs] 财务进度: {i}/{total}，成功 {len(results)}")
                _emit_progress("financial", i, total, success=len(results))
            if on_progress and r is not None:
                await on_progress(i, total, code, r)

        logger.info(f"[provider-bs] 财务数据完成: {len(results)}/{total} 只成功")
        return results

    def load_cached_dividend(self, code: str) -> dict | None:
        """从缓存读取分红数据（忽略 TTL，rescore 用）"""
        path = self._cache_dir / f"{code}_dividend_bs.json"
        return _load_cache_any_age(path)

    def load_cached_financial(self, code: str) -> dict | None:
        """从缓存读取财务数据（忽略 TTL，rescore 用）"""
        path = self._cache_dir / f"{code}_financial_bs.json"
        return _load_cache_any_age(path)

    def cleanup_expired_cache(self):
        """清理过期缓存文件"""
        if not self._cache_dir.exists():
            return
        now = datetime.now()
        removed = 0
        for f in self._cache_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                ts = datetime.fromisoformat(data["timestamp"])
                if now - ts > timedelta(days=60):
                    f.unlink()
                    removed += 1
            except Exception:
                pass
        if removed:
            logger.info(f"[provider-bs] 清理 {removed} 个过期缓存文件")
