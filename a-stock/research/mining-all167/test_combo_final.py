#!/usr/bin/env python3
"""Test with FINAL to fix duplicates"""
import subprocess, json, sys

sql = """WITH daily_rn AS (
    SELECT ts_code, trade_date, close AS c, pct_chg AS p, open AS o, pre_close AS pc, high AS h, low AS l,
           ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date) AS rn
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
    WHERE trade_date >= '2020-01-01' AND trade_date <= '2026-05-13'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
),
b AS (SELECT ts_code, trade_date, volume_ratio AS vr, circ_mv AS cmv FROM tushare.tushare_daily_basic FINAL),
mf AS (SELECT ts_code, trade_date, sell_sm_amount AS sm_s, buy_sm_amount AS sm_b, buy_lg_amount AS lg_b, sell_lg_amount AS lg_s FROM tushare.tushare_moneyflow FINAL),
spx1 AS (SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX')
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
WHERE n5.c IS NOT NULL AND d.c > 0
  AND d.p >= 1 AND d.p < 11
  AND pp1.p <= -2 AND pp2.p <= -2 AND pp3.p <= -2
  AND b.vr >= 1.3 AND b.cmv <= 300000
  AND mf.sm_s > mf.sm_b AND mf.lg_b > mf.lg_s
  AND spx1.pct_chg > 0
LIMIT 5
"""

proc = subprocess.run(
    ["docker", "exec", "-i", "tushare_db-clickhouse-1", "clickhouse-client", "--format", "JSONEachRow"],
    input=sql, capture_output=True, text=True, timeout=120
)
print("Return code:", proc.returncode)
if proc.stderr:
    print("STDERR:", proc.stderr[:500])
if proc.stdout:
    lines = [l for l in proc.stdout.strip().split('\n') if l.strip()]
    print(f"Got {len(lines)} lines")
    for line in lines[:5]:
        print(line)
