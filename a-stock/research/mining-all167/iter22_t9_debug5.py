#!/usr/bin/env python3
"""Debug: test lead window function"""
import json, urllib.request

HOST = "172.24.224.1"
HTTP_PORT = "8123"
USER = "ai_reader"
PASSWORD = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

def ch_post(sql):
    url = f"http://{HOST}:{HTTP_PORT}/?user={USER}&password={PASSWORD}&database=tushare&default_format=JSONEachRow"
    data = sql.encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'text/plain'})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode('utf-8')
            if not body.strip():
                return []
            return [json.loads(line) for line in body.strip().split('\n') if line.strip()]
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8')
        print(f"HTTP {e.code}: {err[:400]}", file=sys.stderr)
        return None

# Test 1: Simple lead
print("=== Test 1: Simple lead with explicit window ===")
sql1 = """
SELECT ts_code, trade_date, close,
       lead(close) OVER (PARTITION BY ts_code ORDER BY trade_date) AS next_close
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
WHERE s.ts_code = '000001.SZ' AND s.trade_date >= '2026-05-01'
ORDER BY trade_date
LIMIT 5
"""
r = ch_post(sql1)
print(f"Result: {r}")

# Test 2: Check ClickHouse version
print("\n=== Test 2: Version ===")
sql2 = "SELECT version() AS v"
r = ch_post(sql2)
print(f"Version: {r}")

# Test 3: Try lagInFrame first
print("\n=== Test 3: lagInFrame ===")
sql3 = """
SELECT ts_code, trade_date, close,
       lagInFrame(close, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) AS prev_close
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
WHERE s.ts_code = '000001.SZ' AND s.trade_date >= '2026-05-01'
ORDER BY trade_date
LIMIT 5
"""
r = ch_post(sql3)
print(f"Result: {r}")

# Test 4: Try anyWindowFrame(lead)
print("\n=== Test 4: any(lead) ===")
sql4 = """
SELECT ts_code, trade_date, close,
       leadInFrame(close, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) AS next_close
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
WHERE s.ts_code = '000001.SZ' AND s.trade_date >= '2026-05-01'
ORDER BY trade_date
LIMIT 5
"""
r = ch_post(sql4)
print(f"Result: {r}")
