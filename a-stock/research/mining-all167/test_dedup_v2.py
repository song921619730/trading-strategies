#!/usr/bin/env python3
"""Test with argMax dedup instead of FINAL"""
import subprocess, json

sql = """WITH daily_dedup AS (
    SELECT ts_code, trade_date,
           argMax(close, _version) AS c,
           argMax(pct_chg, _version) AS p,
           argMax(open, _version) AS o,
           argMax(pre_close, _version) AS pc,
           argMax(high, _version) AS h,
           argMax(low, _version) AS l
    FROM tushare.tushare_stock_daily
    WHERE trade_date >= '2020-01-01' AND trade_date <= '2026-05-13'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
    GROUP BY ts_code, trade_date
),
b AS (SELECT ts_code, trade_date, argMax(volume_ratio, _version) AS vr, argMax(circ_mv, _version) AS cmv FROM tushare.tushare_daily_basic WHERE trade_date >= '2020-01-01' GROUP BY ts_code, trade_date),
mf AS (SELECT ts_code, trade_date, 
          argMax(sell_sm_amount, _version) AS sm_s, argMax(buy_sm_amount, _version) AS sm_b,
          argMax(buy_lg_amount, _version) AS lg_b, argMax(sell_lg_amount, _version) AS lg_s
       FROM tushare.tushare_moneyflow WHERE trade_date >= '2020-01-01' GROUP BY ts_code, trade_date),
spx1 AS (SELECT trade_date, argMax(pct_chg, _version) AS pct_chg FROM tushare.tushare_index_global WHERE ts_code='SPX' GROUP BY trade_date),
daily_rn AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date) AS rn
    FROM daily_dedup
)
SELECT d.ts_code, d.trade_date, d.c AS close, d.p AS pct_chg,
       round((n5.c / d.c - 1) * 100, 2) AS r5
FROM daily_rn d
LEFT JOIN daily_rn pp1 ON d.ts_code = pp1.ts_code AND d.rn = pp1.rn + 1
LEFT JOIN daily_rn pp2 ON d.ts_code = pp2.ts_code AND d.rn = pp2.rn + 2
LEFT JOIN daily_rn pp3 ON d.ts_code = pp3.ts_code AND d.rn = pp3.rn + 3
LEFT JOIN daily_rn n5 ON d.ts_code = n5.ts_code AND d.rn = n5.rn - 5
INNER JOIN b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
INNER JOIN mf ON d.ts_code = mf.ts_code AND d.trade_date = mf.trade_date
LEFT JOIN spx1 ON spx1.trade_date = addDays(d.trade_date, -1)
WHERE n5.c IS NOT NULL
  AND d.p >= 1 AND d.p < 11
  AND pp1.p <= -2 AND pp2.p <= -2 AND pp3.p <= -2
  AND b.vr >= 1.3 AND b.cmv <= 300000
  AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s
  AND spx1.pct_chg > 0
LIMIT 5
"""

proc = subprocess.run(
    ["docker", "exec", "-i", "tushare_db-clickhouse-1", "clickhouse-client", "--format", "JSONEachRow"],
    input=sql, capture_output=True, text=True, timeout=300
)
print("Return code:", proc.returncode)
if proc.stderr:
    print("STDERR:", proc.stderr[:500])
if proc.stdout:
    lines = [l for l in proc.stdout.strip().split('\n') if l.strip()]
    print(f"Got {len(lines)} rows")
    for line in lines[:5]:
        print(line[:200])
