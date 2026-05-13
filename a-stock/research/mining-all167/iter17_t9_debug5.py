"""Test one query exactly as cross.py would build it."""
import json, urllib.request, urllib.parse

HOST, PORT, USER, PWD = '172.24.224.1', '8123', 'ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ'

def ch_q(sql, timeout=600):
    params = {"user": USER, "password": PWD, "database": "tushare",
              "query": sql, "default_format": "JSONEachRow"}
    url = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode(params)
    print(f"SQL length: {len(sql)}, URL length: {len(url)}")
    print(f"Query preview: {sql[:150]}...")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        print(f"Status: {resp.status} {resp.reason}")
        body = resp.read().decode("utf-8")
        print(f"Body length: {len(body)}")
        print(f"Body preview: {body[:200]}")
        if not body.strip():
            return []
        return [json.loads(line) for line in body.strip().split("\n") if line.strip()]

# Build a query like cross.py does
base_cte = """
WITH base AS (
    SELECT
        s.ts_code, s.trade_date,
        s.close, round(s.pct_chg, 2) AS pct_chg,
        round((s.high - s.low) / NULLIF(s.pre_close, 0) * 100, 2) AS amp,
        round((s.close - s.low_20d) / NULLIF(s.range_20d, 0.0001), 4) AS close_pos,
        round((leadInFrame(s.close, 5) OVER w / s.close - 1) * 100, 2) AS ret_5d,
        round((leadInFrame(s.close, 10) OVER w / s.close - 1) * 100, 2) AS ret_10d,
        round((leadInFrame(s.close, 20) OVER w / s.close - 1) * 100, 2) AS ret_20d
    FROM (
        SELECT *,
            MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
            MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d,
            MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
            - MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS range_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
        WHERE trade_date >= '2020-01-01' AND trade_date <= '2026-05-12'
          AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%' AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    ) s
    WINDOW w AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
)
SELECT * FROM base WHERE ret_5d IS NOT NULL AND close > 0
"""

# Try with a simple query first - just the base CTE with no joins
print("=== Test A: Base CTE no join ===")
a_sql = base_cte + " LIMIT 3"
try:
    rows = ch_q(a_sql)
    print(f"Rows: {len(rows)}")
    for r in rows:
        print(f"  {r.get('ts_code')} {r.get('trade_date')}")
except Exception as e:
    print(f"Error: {e}")

# Try without FINAL
print("\n=== Test B: Without FINAL ===")
b_cte = base_cte.replace("FINAL)", ")")
b_sql = b_cte + " LIMIT 3"
try:
    rows = ch_q(b_sql)
    print(f"Rows: {len(rows)}")
    for r in rows:
        print(f"  {r.get('ts_code')} {r.get('trade_date')}")
except Exception as e:
    print(f"Error: {e}")
