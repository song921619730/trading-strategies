#!/usr/bin/env python3
"""
data_overview.py — A 股数据概览（Researcher 使用）

快速检查 ClickHouse 中 A 股数据的概况：
1. 核心表的最新数据日期
2. 当日市场统计
3. 数据完整性检查

用法:
    python3 data_overview.py              # 全量概览
    python3 data_overview.py --market     # 仅市场状态
    python3 data_overview.py --check      # 仅数据完整性
"""

import json
import subprocess
import sys
from datetime import date, timedelta

CH_SCRIPT = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"


def ch_query(sql: str) -> list[dict]:
    r = subprocess.run(
        ["python3", CH_SCRIPT, "sql", sql],
        capture_output=True, text=True, timeout=30
    )
    idx = r.stdout.find('[')
    if idx >= 0:
        return json.loads(r.stdout[idx:])
    return []


def check_table_range(table: str, date_col: str = "trade_date") -> dict:
    """查一张表的最新数据日期和行数"""
    rows = ch_query(
        f"SELECT min({date_col}) as min_d, max({date_col}) as max_d, "
        f"count() as rows FROM tushare.{table} FINAL"
    )
    if rows:
        r = rows[0]
        return {"table": table, "min": r["min_d"], "max": r["max_d"], "rows": r["rows"]}
    return {"table": table, "min": None, "max": None, "rows": 0}


def market_overview() -> dict:
    """当日市场状态"""
    today = date.today().isoformat()
    
    result = {}
    
    # 涨跌家数
    dc = ch_query(
        f"SELECT up_num, down_num, turnover_rate, total_mv "
        f"FROM tushare.tushare_dc_index FINAL "
        f"WHERE trade_date = '{today}' LIMIT 1"
    )
    if dc:
        result["market_stats"] = dc[0]
    
    # 涨停家数
    limit = ch_query(
        f"SELECT count() as cnt FROM tushare.tushare_limit_list_d FINAL "
        f"WHERE trade_date = '{today}'"
    )
    if limit:
        result["limit_up_count"] = limit[0]["cnt"]
    
    # 北上资金
    hsgt = ch_query(
        f"SELECT hgt, sgt, north_money "
        f"FROM tushare.tushare_moneyflow_hsgt FINAL "
        f"WHERE trade_date = '{today}' LIMIT 1"
    )
    if hsgt:
        result["north_flow"] = hsgt[0]
    
    # 大盘指数
    indices = ch_query(
        f"SELECT ts_code, close, pct_chg "
        f"FROM tushare.tushare_index_daily FINAL "
        f"WHERE trade_date = '{today}' "
        f"AND ts_code IN ('000001.SH', '399001.SZ', '399006.SZ')"
    )
    if indices:
        result["indices"] = indices
    
    # 成交量概览
    vol = ch_query(
        f"SELECT count(DISTINCT ts_code) as stocks, "
        f"sum(amount) as total_amount, sum(vol) as total_vol "
        f"FROM tushare.tushare_stock_daily FINAL "
        f"WHERE trade_date = '{today}'"
    )
    if vol:
        result["market_volume"] = vol[0]
    
    return result


def data_integrity() -> list[dict]:
    """检查核心表的数据完整性"""
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    
    tables_to_check = [
        "tushare_stock_daily",
        "tushare_stk_factor_pro",
        "tushare_daily_basic",
        "tushare_moneyflow",
        "tushare_limit_list_d",
    ]
    
    results = []
    for t in tables_to_check:
        info = check_table_range(t)
        
        # 检查最近交易日是否有数据
        recent = ch_query(
            f"SELECT count() as cnt FROM tushare.{t} FINAL "
            f"WHERE trade_date >= '{yesterday}'"
        )
        recent_cnt = recent[0]["cnt"] if recent else 0
        
        info["recent_rows"] = recent_cnt
        info["has_recent_data"] = recent_cnt > 100  # 粗判断
        results.append(info)
    
    return results


def full_overview() -> dict:
    """全量概览"""
    return {
        "date": date.today().isoformat(),
        "data_ranges": [check_table_range(t) for t in [
            "tushare_stock_daily",
            "tushare_stk_factor_pro",
            "tushare_daily_basic",
            "tushare_moneyflow",
            "tushare_moneyflow_dc",
            "tushare_limit_list_d",
        ]],
        "market": market_overview(),
        "integrity": data_integrity(),
    }


if __name__ == "__main__":
    if "--market" in sys.argv:
        print(json.dumps(market_overview(), ensure_ascii=False, indent=2))
    elif "--check" in sys.argv:
        print(json.dumps(data_integrity(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(full_overview(), ensure_ascii=False, indent=2))
