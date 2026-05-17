#!/usr/bin/env python3
"""Deep debug: step-by-step verification of each CTE and JOIN"""
import json, sys
sys.path.insert(0, '/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts')
from ch_query import _ch_query as ch_query

BASE = '2026-05-06'
HIST = '2020-01-01'
BOARD = "sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%' AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'"
WF = "ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING"

# Step 1: Count raw rows in date range
sql1 = f"""
SELECT count() AS n FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
  AND {BOARD}
"""
r1 = ch_query(sql1)
print(f"Step 1 - Raw count: {r1}")

# Step 2: Count with pct_chg >= 4
sql2 = f"""
SELECT count() AS n FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
  AND {BOARD}
  AND sd.pct_chg >= 4
"""
r2 = ch_query(sql2)
print(f"Step 2 - pct_chg>=4: {r2}")

# Step 3: Count with pct_chg >= 4 AND amplitude >= 7
sql3 = f"""
SELECT count() AS n FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
  AND {BOARD}
  AND sd.pct_chg >= 4
  AND (sd.high - sd.low) / NULLIF(sd.pre_close, 0) * 100 >= 7
"""
r3 = ch_query(sql3)
print(f"Step 3 - pct_chg>=4 AND ampl>=7: {r3}")

# Step 4: Check daily_basic coverage for these stocks
sql4 = f"""
SELECT count() AS n_total,
       countIf(b.ts_code IS NOT NULL) AS n_with_basic,
       countIf(b.volume_ratio >= 1.3) AS n_vr_ge_13,
       countIf(b.pe > 0 AND b.pe <= 15 AND b.pb > 0 AND b.pb <= 2) AS n_pe_pb,
       countIf(b.circ_mv <= 300000) AS n_small,
       countIf(b.volume_ratio >= 1.3 AND b.pe > 0 AND b.pe <= 15 AND b.pb > 0 AND b.pb <= 2 AND b.circ_mv <= 300000) AS n_all
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
LEFT JOIN (
    SELECT ts_code, trade_date, volume_ratio, pe, pb, circ_mv
    FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
) b ON sd.ts_code = b.ts_code AND sd.trade_date = b.trade_date
WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
  AND {BOARD}
  AND sd.pct_chg >= 4
  AND (sd.high - sd.low) / NULLIF(sd.pre_close, 0) * 100 >= 7
"""
r4 = ch_query(sql4)
print(f"Step 4 - Basic JOIN coverage: {r4}")

# Step 5: Full CTE with ret_5d
sql5 = f"""
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
    WHERE w.pct_chg >= 4 AND w.amplitude >= 7
)
SELECT count() AS n_total,
       countIf(ret_5d IS NOT NULL) AS n_with_ret,
       countIf(b.volume_ratio >= 1.3) AS n_vr,
       countIf(b.pe > 0 AND b.pe <= 15) AS n_pe,
       countIf(b.pb > 0 AND b.pb <= 2) AS n_pb,
       countIf(b.circ_mv <= 300000) AS n_small,
       countIf(b.volume_ratio >= 1.3 AND b.pe > 0 AND b.pe <= 15 AND b.pb > 0 AND b.pb <= 2 AND b.circ_mv <= 300000) AS n_all_filters
FROM combo w
LEFT JOIN (
    SELECT ts_code, trade_date, volume_ratio, pe, pb, circ_mv
    FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
) b ON w.ts_code = b.ts_code AND w.trade_date = b.trade_date
"""
r5 = ch_query(sql5)
print(f"Step 5 - Full chain debug: {r5}")
