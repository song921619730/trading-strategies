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
sql = f"""
SELECT count() AS n FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
  AND {BOARD}
"""
    r = ch_query(sql)
print(f"Step 1 - Raw count: {r}")

# Step 2: Count with pct_chg >= 4 (one condition)
sql2 = f"""
SELECT count() AS n FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
  AND {BOARD}
  AND sd.pct_chg >= 4
"""
r2 = ch_query(sql2, timeout=30)
print(f"Step 2 - pct_chg>=4: {r2}")

# Step 3: Count with pct_chg >= 4 AND amplitude >= 7
sql3 = f"""
SELECT count() AS n FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
  AND {BOARD}
  AND sd.pct_chg >= 4
  AND (sd.high - sd.low) / NULLIF(sd.pre_close, 0) * 100 >= 7
"""
r3 = ch_query(sql3, timeout=30)
print(f"Step 3 - pct_chg>=4 AND ampl>=7: {r3}")

# Step 4: LEFT JOIN daily_basic - count rows
sql4 = f"""
WITH sd_windowed AS (
    SELECT sd.ts_code, sd.trade_date, sd.close, sd.pct_chg, sd.high, sd.low, sd.pre_close,
           (sd.high - sd.low) / NULLIF(sd.pre_close, 0) * 100 AS amplitude
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
    WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
      AND {BOARD}
)
SELECT count() AS n_total, 
       count(b.ts_code) AS n_with_basic,
       countIf(b.pe IS NOT NULL AND b.pe > 0) AS n_with_pe,
       countIf(b.circ_mv <= 300000) AS n_small_cap
FROM sd_windowed w
LEFT JOIN (
    SELECT ts_code, trade_date, volume_ratio, pe, pb, circ_mv
    FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
) b ON w.ts_code = b.ts_code AND w.trade_date = b.trade_date
WHERE w.pct_chg >= 4 AND w.amplitude >= 7
"""
r4 = ch_query(sql4, timeout=60)
print(f"Step 4 - WITH + basic JOIN: {r4}")

# Step 5: Add volume_ratio filter
sql5 = f"""
WITH sd_windowed AS (
    SELECT sd.ts_code, sd.trade_date, sd.close, sd.pct_chg, sd.high, sd.low, sd.pre_close,
           (sd.high - sd.low) / NULLIF(sd.pre_close, 0) * 100 AS amplitude
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
    WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
      AND {BOARD}
)
SELECT count() AS n
FROM sd_windowed w
LEFT JOIN (
    SELECT ts_code, trade_date, volume_ratio, pe, pb, circ_mv
    FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
) b ON w.ts_code = b.ts_code AND w.trade_date = b.trade_date
WHERE w.pct_chg >= 4 AND w.amplitude >= 7
  AND b.volume_ratio >= 1.3
  AND b.pe > 0 AND b.pe <= 15 AND b.pb > 0 AND b.pb <= 2 AND b.circ_mv <= 300000
"""
r5 = ch_query(sql5, timeout=60)
print(f"Step 5 - WITH + PE/PB/CM filter: {r5}")

# Step 6: Same but as CTE chaining (like the backtest template)
sql6 = f"""
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
      AND b.volume_ratio >= 1.3
      AND b.pe > 0 AND b.pe <= 15 AND b.pb > 0 AND b.pb <= 2 AND b.circ_mv <= 300000
)
SELECT count() AS n, 
       countIf(ret_5d IS NOT NULL) AS n_with_ret,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(countIf(ret_5d > 0) * 100.0 / count(), 2) AS wr
FROM combo
"""
r6 = ch_query(sql6, timeout=120)
print(f"Step 6 - Full CTE chain: {r6}")

# Step 7: Debug moneyflow JOIN - just count matching rows
sql7 = f"""
SELECT count() AS n_total,
       count(m.ts_code) AS n_with_mf,
       countIf(m.sell_sm_vol > m.buy_sm_vol AND m.buy_elg_vol > m.sell_elg_vol) AS n_dual_fundflow
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
LEFT JOIN (
    SELECT ts_code, trade_date, sell_sm_vol, buy_sm_vol, buy_elg_vol, sell_elg_vol
    FROM (SELECT * FROM tushare.tushare_moneyflow FINAL) AS m
) mf ON sd.ts_code = mf.ts_code AND sd.trade_date = mf.trade_date
WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
  AND {BOARD}
  AND sd.pct_chg >= 4
LIMIT 1
"""
r7 = ch_query(sql7, timeout=30)
print(f"Step 7 - MF JOIN count (limit 1): {r7}")
