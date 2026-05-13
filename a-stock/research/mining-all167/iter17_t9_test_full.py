"""Test X01 combo with 2025 data only."""
import json, urllib.request, urllib.parse, math, time

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

# Test X01: T3恐慌 × T4资金 with 2025-01-01 to 2025-12-31
print("=== X01 Test: 2025 full year ===")
t0 = time.time()

sql = """
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
        WHERE trade_date >= '2024-06-01' AND trade_date <= '2025-12-31'
          AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%' AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    ) s
    WINDOW w AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
)
SELECT b.*, db.volume_ratio, db.turnover_rate, db.circ_mv, db.pe
FROM base b
JOIN (SELECT * FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) WHERE trade_date >= '2024-06-01' AND trade_date <= '2025-12-31') db
    ON b.ts_code = db.ts_code AND b.trade_date = db.trade_date
JOIN (SELECT * FROM (SELECT * FROM tushare.tushare_moneyflow FINAL) WHERE trade_date >= '2024-06-01' AND trade_date <= '2025-12-31') mf
    ON b.ts_code = mf.ts_code AND b.trade_date = mf.trade_date
WHERE b.pct_chg <= -5
  AND b.close_pos <= 0.20
  AND b.amp >= 6.0
  AND db.volume_ratio >= 1.2
  AND db.circ_mv > 0 AND db.circ_mv <= 300000
  AND db.pe > 0 AND db.pe <= 20
  AND mf.buy_elg_amount > mf.sell_elg_amount
LIMIT 20
"""

rows = ch_q(sql)
elapsed = time.time() - t0
print(f"Rows: {len(rows)}, Time: {elapsed:.1f}s")
for r in rows[:5]:
    print(f"  {r['ts_code']} {r['trade_date']} pct={r['pct_chg']} amp={r['amp']} pos={r['close_pos']} r5={r.get('ret_5d')}%")
