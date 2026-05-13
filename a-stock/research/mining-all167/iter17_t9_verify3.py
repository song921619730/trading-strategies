"""Test X01 full query with all joins."""
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

base_cte = """
SELECT
    s.ts_code, s.trade_date,
    s.close, round(s.pct_chg, 2) AS pct_chg,
    s.open, s.high, s.low, s.pre_close,
    round((s.high - s.low) / NULLIF(s.pre_close, 0) * 100, 2) AS amp,
    round((s.close - s.low_20d) / NULLIF(s.range_20d, 0.0001), 4) AS close_pos,
    round((leadInFrame(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / s.close - 1) * 100, 2) AS ret_5d,
    round((leadInFrame(s.close, 10) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / s.close - 1) * 100, 2) AS ret_10d,
    round((leadInFrame(s.close, 20) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / s.close - 1) * 100, 2) AS ret_20d,
    COALESCE(cc.concept_count, 0) AS concept_cnt
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
LEFT JOIN (
    SELECT con_code, count(*) AS concept_count
    FROM (SELECT * FROM tushare.tushare_ths_member FINAL)
    WHERE con_code NOT LIKE '700001.TI' AND con_code NOT LIKE '700002.TI'
    GROUP BY con_code
) cc ON cc.con_code = s.ts_code
"""

# X01: full query
x01_sql = f"""
WITH base AS ({base_cte}),
basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date >= '2020-01-01'),
mf AS (SELECT * FROM tushare.tushare_moneyflow FINAL WHERE trade_date >= '2020-01-01')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv, d.pe
FROM base b
JOIN basic d ON b.ts_code = d.ts_code AND b.trade_date = d.trade_date
JOIN mf ON b.ts_code = mf.ts_code AND b.trade_date = mf.trade_date
WHERE b.ret_5d IS NOT NULL AND b.close > 0
  AND b.pct_chg <= -5
  AND b.close_pos <= 0.20
  AND b.amp >= 6.0
  AND d.volume_ratio >= 1.2
  AND d.circ_mv > 0 AND d.circ_mv <= 300000
  AND d.pe > 0 AND d.pe <= 20
  AND mf.buy_elg_amount > mf.sell_elg_amount
LIMIT 10
"""

print(f"SQL len: {len(x01_sql)}")
import time
t0 = time.time()
try:
    rows = ch_q(x01_sql)
    et = time.time() - t0
    print(f"Time: {et:.1f}s, Rows: {len(rows)}")
    for r in rows:
        print(f"  {r['ts_code']} {r['trade_date']} pct={r['pct_chg']} amp={r['amp']} pos={r['close_pos']} r5={r['ret_5d']}% VR={r.get('volume_ratio')} CM={r.get('circ_mv')}")
except Exception as e:
    print(f"Error: {e}")
