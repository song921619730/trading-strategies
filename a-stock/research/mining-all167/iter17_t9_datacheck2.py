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

# Check what's in index_global
print("=== index_global ===")
r = ch_q("SELECT count() AS cnt FROM tushare.tushare_index_global FINAL")
print(f"Total rows: {r}")

r = ch_q("SELECT DISTINCT ts_code FROM tushare.tushare_index_global FINAL")
print(f"Distinct codes: {r}")

r = ch_q("SELECT * FROM tushare.tushare_index_global FINAL LIMIT 5")
print(f"Sample rows: {r}")

# Maybe the table has a different tushare name pattern
print("\n=== Search for SPX in other tables ===")
r = ch_q("SELECT name FROM system.tables WHERE database='tushare' AND name LIKE '%global%'")
print(f"Tables matching 'global': {r}")

r = ch_q("SELECT name FROM system.tables WHERE database='tushare' AND name LIKE '%index%'")
print(f"Tables matching 'index': {r}")

# Check fina_indicator 
print("\n=== fina_indicator ===")
r = ch_q("SELECT count() AS cnt FROM tushare.tushare_fina_indicator FINAL")
print(f"Total rows: {r}")

r = ch_q("SELECT ts_code, end_date, netprofit_yoy, tr_yoy FROM tushare.tushare_fina_indicator FINAL LIMIT 5")
print(f"Sample: {r}")

# Check stock_daily counts
print("\n=== stock_daily sample ===")
r = ch_q("SELECT ts_code, trade_date, open, close, high, low, pre_close, pct_chg FROM tushare.tushare_stock_daily FINAL WHERE trade_date='2026-05-12' LIMIT 3")
print(f"Sample 2026-05-12: {r}")
