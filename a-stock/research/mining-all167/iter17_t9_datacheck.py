#!/usr/bin/env python3
"""Quick data check and table structure verification."""
import json, urllib.request, urllib.parse

HOST, PORT, USER, PWD = '172.24.224.1', '8123', 'ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ'

def ch_q(sql):
    params = {"user": USER, "password": PWD, "database": "tushare",
              "query": sql, "default_format": "JSONEachRow"}
    url = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=600) as resp:
        body = resp.read().decode("utf-8")
        if not body.strip():
            return []
        return [json.loads(line) for line in body.strip().split("\n") if line.strip()]

# Check max trade_date
print("=== Data Check ===")
r = ch_q("SELECT max(trade_date) AS max_dt FROM tushare.tushare_stock_daily FINAL")
print(f"stock_daily max trade_date: {r}")

r = ch_q("SELECT max(trade_date) AS max_dt FROM tushare.tushare_index_global FINAL WHERE ts_code='.SPX'")
print(f"SPX max trade_date: {r}")

r = ch_q("SELECT count() AS cnt FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= '2020-01-01' AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'")
print(f"stock_daily filtered count: {r}")

# Check moneyflow table
r = ch_q("SELECT count() AS cnt FROM tushare.tushare_moneyflow FINAL")
print(f"moneyflow count: {r}")

# Check index_global structure
r = ch_q("SELECT name, type FROM system.columns WHERE database='tushare' AND table='tushare_index_global'")
print(f"index_global columns: {r}")

# Check SPX data sample
r = ch_q("SELECT trade_date, ts_code, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code='.SPX' ORDER BY trade_date DESC LIMIT 5")
print(f"SPX recent: {r}")

# Check if index_global has a different structure
r = ch_q("DESCRIBE TABLE tushare.tushare_index_global")
print(f"index_global schema: {r}")

# Check moneyflow column names
r = ch_q("DESCRIBE TABLE tushare.tushare_moneyflow")
print(f"\nmoneyflow schema: {r}")

# Check daily_basic schema
r = ch_q("DESCRIBE TABLE tushare.tushare_daily_basic")
print(f"\ndaily_basic schema: {r}")
