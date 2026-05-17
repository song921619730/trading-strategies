#!/usr/bin/env python3
"""Test one combo query via subprocess"""
import subprocess, json, sys

sql = """WITH daily_rn AS (
    SELECT ts_code, trade_date, close, pct_chg, open, pre_close, high, low,
           toInt64(ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date)) AS rn
    FROM tushare.tushare_stock_daily
    WHERE trade_date >= '2020-01-01' AND trade_date <= '2026-05-13'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
),
b as (SELECT ts_code, trade_date, volume_ratio AS vr, circ_mv AS cmv FROM tushare.tushare_daily_basic),
mf as (SELECT ts_code, trade_date, sell_sm_amount AS sm_s, buy_sm_amount AS sm_b, buy_lg_amount AS lg_b, sell_lg_amount AS lg_s FROM tushare.tushare_moneyflow),
spx1 as (SELECT trade_date, pct_chg FROM tushare.tushare_index_global WHERE ts_code='SPX'),
spx2 as (SELECT trade_date, pct_chg FROM tushare.tushare_index_global WHERE ts_code='SPX')
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg,
       round((n5.close / d.close - 1) * 100, 2) AS r5
FROM daily_rn d
LEFT JOIN daily_rn pp1 ON d.ts_code = pp1.ts_code AND d.rn = pp1.rn + 1
LEFT JOIN daily_rn pp2 ON d.ts_code = pp2.ts_code AND d.rn = pp2.rn + 2
LEFT JOIN daily_rn pp3 ON d.ts_code = pp3.ts_code AND d.rn = pp3.rn + 3
LEFT JOIN daily_rn n5 ON d.ts_code = n5.ts_code AND d.rn = n5.rn - 5
INNER JOIN b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
INNER JOIN mf ON d.ts_code = mf.ts_code AND d.trade_date = mf.trade_date
LEFT JOIN spx1 ON spx1.trade_date = addDays(d.trade_date, -1)
LEFT JOIN spx2 ON spx2.trade_date = addDays(d.trade_date, -2)
WHERE n5.close IS NOT NULL AND d.close > 0
  AND d.pct_chg >= 1 AND d.pct_chg < 11
  AND pp1.pct_chg <= -2 AND pp2.pct_chg <= -2 AND pp3.pct_chg <= -2
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
    lines = proc.stdout.strip().split('\n')
    print(f"Got {len(lines)} lines output")
    for line in lines[:5]:
        print(line)
