#!/usr/bin/env python3
"""Test with FINAL on individual tables only"""
import subprocess, json, sys

# Use group by to dedup instead of FINAL
sql = """WITH daily_rn AS (
    SELECT ts_code, trade_date, 
           argMax(close, last_updated) AS c,
           argMax(pct_chg, last_updated) AS p,
           argMax(open, last_updated) AS o,
           argMax(pre_close, last_updated) AS pc,
           argMax(high, last_updated) AS h,
           argMax(low, last_updated) AS l
    FROM tushare.tushare_stock_daily
    WHERE trade_date >= '2020-01-01' AND trade_date <= '2026-05-13'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
    GROUP BY ts_code, trade_date
)
SELECT count(*) AS cnt
FROM (
    SELECT d.ts_code, d.trade_date,
           ROW_NUMBER() OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) AS rn
    FROM daily_rn d
) rn_query
"""

proc = subprocess.run(
    ["docker", "exec", "-i", "tushare_db-clickhouse-1", "clickhouse-client", "--format", "JSONEachRow"],
    input=sql, capture_output=True, text=True, timeout=30
)
print("Return code:", proc.returncode)
if proc.stderr:
    print("STDERR:", proc.stderr[:500])
if proc.stdout:
    lines = [l for l in proc.stdout.strip().split('\n') if l.strip()]
    for line in lines[:3]:
        print(line)
