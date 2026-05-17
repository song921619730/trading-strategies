#!/usr/bin/env python3
"""Debug: exact SQL from backtest template"""
import sys
sys.path.insert(0, '/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts')
from ch_query import _ch_query as ch_query

BASE = '2026-05-06'
HIST = '2020-01-01'
BOARD = "sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%' AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'"
WF = "ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING"

# Exact SQL from backtest template (simplified to check WHERE clause behavior)
sql = f"""
WITH sd_windowed AS (
    SELECT sd.ts_code, sd.trade_date, sd.close, sd.pct_chg, sd.high, sd.low, sd.pre_close,
           (sd.high - sd.low) / NULLIF(sd.pre_close, 0) * 100 AS amplitude,
           leadInFrame(sd.close, 5) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WF}) AS close_5d
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
    WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
      AND {BOARD}
),
combo AS (
    SELECT w.ts_code, w.trade_date, w.close, w.pct_chg, w.amplitude, w.close_5d,
           (w.close_5d / w.close) - 1 AS ret_5d
    FROM sd_windowed w
    LEFT JOIN (
        SELECT ts_code, trade_date, volume_ratio, pe, pb, circ_mv
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
    ) b ON w.ts_code = b.ts_code AND w.trade_date = b.trade_date
    WHERE w.pct_chg >= 4
      AND w.amplitude >= 7
      AND b.volume_ratio >= 1.3
      AND b.pe > 0 AND b.pe <= 15
      AND b.pb > 0 AND b.pb <= 2
      AND b.circ_mv <= 300000
)
SELECT count() AS n,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(countIf(ret_5d > 0) * 100.0 / count(), 2) AS wr
FROM combo
WHERE ret_5d IS NOT NULL
"""
r = ch_query(sql)
print(f"Exact backtest SQL: {r}")

# Test: what if I move the b.* filters to HAVING or use INNER JOIN?
sql2 = f"""
WITH sd_windowed AS (
    SELECT sd.ts_code, sd.trade_date, sd.close, sd.pct_chg, sd.high, sd.low, sd.pre_close,
           (sd.high - sd.low) / NULLIF(sd.pre_close, 0) * 100 AS amplitude,
           leadInFrame(sd.close, 5) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WF}) AS close_5d
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
    WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
      AND {BOARD}
),
basic AS (
    SELECT ts_code, trade_date, volume_ratio, pe, pb, circ_mv
    FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
    WHERE db.volume_ratio >= 1.3
      AND db.pe > 0 AND db.pe <= 15
      AND db.pb > 0 AND db.pb <= 2
      AND db.circ_mv <= 300000
),
combo AS (
    SELECT w.ts_code, w.trade_date, w.close, w.pct_chg, w.amplitude, w.close_5d,
           (w.close_5d / w.close) - 1 AS ret_5d
    FROM sd_windowed w
    INNER JOIN basic b ON w.ts_code = b.ts_code AND w.trade_date = b.trade_date
    WHERE w.pct_chg >= 4
      AND w.amplitude >= 7
)
SELECT count() AS n,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(countIf(ret_5d > 0) * 100.0 / count(), 2) AS wr
FROM combo
WHERE ret_5d IS NOT NULL
"""
r2 = ch_query(sql2)
print(f"INNER JOIN version: {r2}")
