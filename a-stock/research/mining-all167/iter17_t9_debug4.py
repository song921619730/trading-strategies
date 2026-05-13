"""Check raw HTTP response."""
import json, urllib.request, urllib.parse

HOST, PORT, USER, PWD = '172.24.224.1', '8123', 'ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ'

# Test 1: Simple query that worked before
sql1 = "SELECT count() AS cnt FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= '2025-01-01' LIMIT 5"
params = {"user": USER, "password": PWD, "database": "tushare", "query": sql1, "default_format": "JSONEachRow"}
url = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode(params)
print(f"Test 1 - Simple query")
print(f"URL length: {len(url)}")
try:
    with urllib.request.urlopen(url, timeout=30) as resp:
        print(f"Status: {resp.status}")
        body = resp.read().decode("utf-8")
        print(f"Body: {body[:200]}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: With CTE and concept join
sql2 = """
WITH base AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
        (s.high - s.low) / NULLIF(s.pre_close, 0) * 100 AS amp
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low, pre_close
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '2025-01-01' AND trade_date <= '2025-12-31'
        LIMIT 1000
    ) s
    LEFT JOIN (
        SELECT con_code, count(*) AS concept_count
        FROM tushare.tushare_ths_member FINAL
        GROUP BY con_code
    ) cc ON cc.con_code = s.ts_code
)
SELECT * FROM base
LIMIT 5
"""
params2 = {"user": USER, "password": PWD, "database": "tushare", "query": sql2, "default_format": "JSONEachRow"}
url2 = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode(params2)
print(f"\nTest 2 - With CTE + concept join")
print(f"URL length: {len(url2)}")
try:
    with urllib.request.urlopen(url2, timeout=30) as resp:
        print(f"Status: {resp.status}")
        body = resp.read().decode("utf-8")[:500]
        print(f"Body: {body}")
except Exception as e:
    print(f"Error: {e}")

# Test 3: With CTE but no concept join
sql3 = """
WITH base AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
        (s.high - s.low) / NULLIF(s.pre_close, 0) * 100 AS amp
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low, pre_close
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '2025-01-01' AND trade_date <= '2025-12-31'
        LIMIT 1000
    ) s
)
SELECT * FROM base
LIMIT 5
"""
params3 = {"user": USER, "password": PWD, "database": "tushare", "query": sql3, "default_format": "JSONEachRow"}
url3 = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode(params3)
print(f"\nTest 3 - With CTE, no concept join")
print(f"URL length: {len(url3)}")
try:
    with urllib.request.urlopen(url3, timeout=30) as resp:
        print(f"Status: {resp.status}")
        body = resp.read().decode("utf-8")[:500]
        print(f"Body: {body}")
except Exception as e:
    print(f"Error: {e}")
