#!/usr/bin/env python3
"""Test SQL structure for T9 cross-validation."""
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

# First get SPX prev-up dates
print("=== SPX prev-up dates ===")
spx_sql = """
SELECT trade_date, pct_chg,
       lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS prev_pct_chg
FROM (SELECT * FROM tushare.tushare_index_global FINAL)
WHERE ts_code = 'SPX' AND trade_date >= '2020-01-01' AND trade_date <= '2026-05-12'
ORDER BY trade_date
"""
spx = ch_q(spx_sql)
up_dates = [r['trade_date'] for r in spx if r.get('prev_pct_chg') and float(r['prev_pct_chg']) > 0]
print(f"SPX prev-up dates: {len(up_dates)} (first 5: {up_dates[:5]})")

# Test a base CTE
print("\n=== Base CTE test (limit 5) ===")
test_sql = """
WITH base AS (
    SELECT
        s.ts_code, s.trade_date,
        s.close, s.pct_chg,
        round((s.high - s.low) / NULLIF(s.pre_close, 0) * 100, 2) AS amp,
        round((s.close - s.low_20d) / NULLIF(s.range_20d, 0.0001), 4) AS close_pos,
        round((leadInFrame(s.close, 5) OVER w / s.close - 1) * 100, 2) AS ret_5d
    FROM (
        SELECT *,
            MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
            MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d,
            MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
            - MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS range_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
        WHERE trade_date >= '2026-05-01' AND trade_date <= '2026-05-12'
          AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%' AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    ) s
    WINDOW w AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
)
SELECT * FROM base WHERE ret_5d IS NOT NULL AND close > 0 LIMIT 5
"""
rows = ch_q(test_sql)
for r in rows:
    print(f"  {r['ts_code']} {r['trade_date']} close={r['close']} pct={r['pct_chg']} amp={r['amp']} pos={r['close_pos']} r5={r['ret_5d']}")

# Test with join to daily_basic
print("\n=== Full combo test (X01 limited to 2026) ===")
test2_sql = """
WITH base AS (
    SELECT
        s.ts_code, s.trade_date,
        s.close, s.pct_chg, s.open, s.high, s.low, s.pre_close,
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
        WHERE trade_date >= '2026-05-01' AND trade_date <= '2026-05-12'
          AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%' AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    ) s
    WINDOW w AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
)
SELECT b.*, db.volume_ratio, db.turnover_rate, db.circ_mv, db.pe
FROM base b
JOIN (SELECT * FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) WHERE trade_date >= '2026-05-01' AND trade_date <= '2026-05-12') db
    ON b.ts_code = db.ts_code AND b.trade_date = db.trade_date
JOIN (SELECT * FROM (SELECT * FROM tushare.tushare_moneyflow FINAL) WHERE trade_date >= '2026-05-01' AND trade_date <= '2026-05-12') mf
    ON b.ts_code = mf.ts_code AND b.trade_date = mf.trade_date
WHERE b.pct_chg <= -5
  AND b.close_pos <= 0.20
  AND b.amp >= 6.0
  AND db.volume_ratio >= 1.2
  AND db.circ_mv > 0 AND db.circ_mv <= 300000
  AND db.pe > 0 AND db.pe <= 20
  AND mf.buy_elg_amount > mf.sell_elg_amount
LIMIT 10
"""
rows2 = ch_q(test2_sql)
print(f"X01 test (2026 only): {len(rows2)} signals")
for r in rows2:
    print(f"  {r['ts_code']} {r['trade_date']} pct={r['pct_chg']} amp={r['amp']} pos={r['close_pos']} r5={r['ret_5d']}% VR={r.get('volume_ratio')} CM={r.get('circ_mv')}")
