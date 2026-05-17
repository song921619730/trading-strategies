#!/usr/bin/env python3
"""
T9 Cross-Validation (Iter 32) — v6: Shorter date range + FINAL
"""
import subprocess, json, math, time, os

END_DATE = "2026-05-13"
START_DATE = "2022-01-01"

def ch_query(sql):
    fpath = f"/tmp/t9_{hash(sql)%100000}.sql"
    with open(fpath, 'w') as f:
        f.write(sql)
    try:
        proc = subprocess.run(
            ["docker", "exec", "-i", "tushare_db-clickhouse-1", "clickhouse-client", "--format", "JSONEachRow"],
            stdin=open(fpath, 'r'), capture_output=True, text=True, timeout=600
        )
        if proc.returncode != 0:
            err = proc.stderr.strip()[:400] if proc.stderr else "no stderr"
            raise RuntimeError(f"FAIL (exit={proc.returncode}): {err}")
        return [json.loads(l) for l in proc.stdout.strip().split('\n') if l.strip()]
    finally:
        try: os.remove(fpath)
        except: pass

# Simpler approach: use FINAL on each table, shorter date range
BASE_SQL = """WITH
daily_rn AS (
    SELECT ts_code, trade_date, close AS c, pct_chg AS p, open AS o, pre_close AS pc, high AS h, low AS l,
           toInt64(ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date)) AS rn
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL
          WHERE trade_date >= '{START}' AND trade_date <= '{END}'
            AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
            AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%')
),
b AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date >= '{START}'),
mf AS (SELECT * FROM tushare.tushare_moneyflow FINAL WHERE trade_date >= '{START}'),
spx1 AS (SELECT * FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX' AND trade_date >= '{START}'),
spx2 AS (SELECT * FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX' AND trade_date >= '{START}'),
hs300 AS (SELECT * FROM tushare.tushare_index_daily FINAL WHERE ts_code='000300.SH' AND trade_date >= '{START}')
SELECT count(*) AS cnt
FROM daily_rn d
LEFT JOIN daily_rn pp1 ON d.ts_code = pp1.ts_code AND d.rn = pp1.rn + 1
LEFT JOIN daily_rn pp2 ON d.ts_code = pp2.ts_code AND d.rn = pp2.rn + 2
LEFT JOIN daily_rn pp3 ON d.ts_code = pp3.ts_code AND d.rn = pp3.rn + 3
LEFT JOIN daily_rn n5 ON d.ts_code = n5.ts_code AND d.rn = n5.rn - 5
LEFT JOIN daily_rn n10 ON d.ts_code = n10.ts_code AND d.rn = n10.rn - 10
LEFT JOIN daily_rn n20 ON d.ts_code = n20.ts_code AND d.rn = n20.rn - 20
LEFT JOIN b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
LEFT JOIN mf ON d.ts_code = mf.ts_code AND d.trade_date = mf.trade_date
LEFT JOIN spx1 ON spx1.trade_date = addDays(d.trade_date, -1)
LEFT JOIN spx2 ON spx2.trade_date = addDays(d.trade_date, -2)
LEFT JOIN hs300 ON hs300.trade_date = d.trade_date
WHERE n5.c IS NOT NULL AND n10.c IS NOT NULL AND n20.c IS NOT NULL
  AND d.c > 0
  AND d.p >= 1 AND d.p < 11
  AND pp1.p IS NOT NULL AND pp2.p IS NOT NULL AND pp3.p IS NOT NULL
  AND pp1.p <= -2 AND pp2.p <= -2 AND pp3.p <= -2
  AND ((d.h - d.l) / d.pc * 100) >= 7
  AND b.volume_ratio >= 1.3 AND b.circ_mv <= 300000
  AND mf.sell_sm_amount > mf.buy_sm_amount AND mf.buy_lg_amount > mf.sell_lg_amount
  AND spx1.pct_chg > 0 AND spx2.pct_chg > 0
"""

sql = BASE_SQL.format(START=START_DATE, END=END_DATE)
proc = subprocess.run(
    ["docker", "exec", "-i", "tushare_db-clickhouse-1", "clickhouse-client", "--format", "JSONEachRow"],
    input=sql, capture_output=True, text=True, timeout=120
)
print("Return code:", proc.returncode)
if proc.stderr:
    print("STDERR:", proc.stderr[:500])
if proc.stdout:
    print("Output:", proc.stdout[:200])
