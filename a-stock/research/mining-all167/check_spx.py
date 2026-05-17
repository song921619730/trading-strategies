#!/usr/bin/env python3
"""Test SPX data availability."""
import urllib.request, json

CH_HOST = "172.24.224.1"
CH_PORT = 8123
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

def ch_query(sql, timeout=60):
    url = f"http://{CH_HOST}:{CH_PORT}/?user={CH_USER}&password={CH_PASS}&database=tushare&default_format=JSON"
    data = sql.encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("data", [])

# Check SPX data
rows = ch_query("SELECT count() AS cnt FROM (SELECT * FROM tushare.tushare_index_global FINAL) WHERE ts_code='SPX' AND trade_date >= '20190101' AND trade_date <= '20260513'")
print("SPX count:", rows)

# Check latest dates
rows2 = ch_query("SELECT trade_date, pct_chg FROM (SELECT * FROM tushare.tushare_index_global FINAL) WHERE ts_code='SPX' AND trade_date >= '20260501' ORDER BY trade_date DESC LIMIT 10")
print("SPX recent dates:", rows2)

# Check if there's also a tushare_index_daily table
rows3 = ch_query("SELECT name FROM system.tables WHERE database='tushare' AND name LIKE '%index%' ORDER BY name")
print("Index tables:", [r['name'] for r in rows3])
