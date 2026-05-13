"""Debug SQL structure step by step."""
import json, urllib.request, urllib.parse

HOST, PORT, USER, PWD = '172.24.224.1', '8123', 'ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ'

def ch_q(sql):
    params = {"user": USER, "password": PWD, "database": "tushare",
              "query": sql, "default_format": "JSONEachRow"}
    url = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as resp:
        body = resp.read().decode("utf-8")
        if not body.strip():
            return []
        return [json.loads(line) for line in body.strip().split("\n") if line.strip()]

# Step 1: Simple data access
print("=== Step 1: Basic stock daily query ===")
r = ch_q("SELECT count() AS cnt FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= '2026-05-01' AND ts_code='600519.SH'")
print(f"  count: {r}")

# Step 2: Simple query with close_pos
print("\n=== Step 2: Window function test ===")
sql2 = """
SELECT ts_code, trade_date, close, pre_close,
       MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
       MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
WHERE trade_date >= '2026-05-01' AND trade_date <= '2026-05-12'
  AND ts_code LIKE '600519.SH'
LIMIT 5
"""
r2 = ch_q(sql2)
for row in r2:
    print(f"  {row}")

# Step 3: Try with inner subquery pattern
print("\n=== Step 3: Subquery pattern test ===")
sql3 = """
SELECT s.ts_code, s.trade_date, s.close,
       MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
       MAX(s.high) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d
FROM (
    SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2026-05-01' AND trade_date <= '2026-05-12'
      AND ts_code LIKE '600519.SH'
) s
LIMIT 5
"""
r3 = ch_q(sql3)
for row in r3:
    print(f"  {row}")

# Step 4: Simple leadInFrame test 
print("\n=== Step 4: leadInFrame test ===")
sql4 = """
SELECT ts_code, trade_date, close,
       leadInFrame(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS close_5d
FROM (
    SELECT ts_code, trade_date, close
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2026-05-01' AND trade_date <= '2026-05-12'
      AND ts_code LIKE '600519.SH'
) s
LIMIT 10
"""
r4 = ch_q(sql4)
for row in r4:
    print(f"  {row}")
