#!/usr/bin/env python3
"""Iter22 T9: Cross-school combination backtest - Debug-first approach"""
import json, subprocess, sys

CH_SCRIPT = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def ch_query_sql(sql):
    """Run SQL via the working ch_query.py script"""
    result = subprocess.run(
        [sys.executable, CH_SCRIPT, "sql", sql],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr[:500]}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}, stdout: {result.stdout[:500]}", file=sys.stderr)
        return []

# First, debug simple patterns
print("="*80)
print("DEBUG: Testing SQL patterns")
print("="*80)

# Test A: Simple single-table filter
print("\n--- Test A: Single table filter ---")
sql_a = """
SELECT count() AS n
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '2020-01-01'
  AND pct_chg >= 4
  AND amplitude >= 7
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
  AND trade_date <= '2026-05-06'
"""
r = ch_query_sql(sql_a)
print(f"Simple filter: {r}")

# Test B: WITH + window function for ret_5d
print("\n--- Test B: WITH + window ---")
sql_b = """
WITH stock_filter AS (
    SELECT ts_code, trade_date, close, pct_chg, amount, amplitude,
           lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2020-01-01'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
)
SELECT count() AS n,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
FROM stock_filter
WHERE pct_chg >= 4
  AND amplitude >= 7
  AND trade_date <= '2026-05-06'
  AND ret_5d IS NOT NULL
"""
r = ch_query_sql(sql_b)
print(f"WITH+window: {r}")

# Test C: IN subquery with daily_basic (same date)
print("\n--- Test C: IN subquery daily_basic (same date ref) ---")
sql_c = """
WITH stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '2020-01-01'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
SELECT count() AS n,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
FROM stock_filter s
WHERE s.pct_chg >= 4
  AND s.amplitude >= 7
  AND s.trade_date <= '2026-05-06'
  AND s.ret_5d IS NOT NULL
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND pe > 0 AND pe <= 15
        AND pb > 0 AND pb <= 2
  )
"""
r = ch_query_sql(sql_c)
print(f"IN subquery (correlated): {r}")

# Test D: IN subquery with hardcoded date (non-correlated)
print("\n--- Test D: IN subquery non-correlated ---")
sql_d = """
WITH stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '2020-01-01'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
),
value_stocks AS (
    SELECT DISTINCT ts_code FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date >= '2020-01-01'
      AND pe > 0 AND pe <= 15
      AND pb > 0 AND pb <= 2
      AND circ_mv <= 300000
)
SELECT count() AS n,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
FROM stock_filter s
INNER JOIN value_stocks v ON s.ts_code = v.ts_code
WHERE s.pct_chg >= 4
  AND s.amplitude >= 7
  AND s.trade_date <= '2026-05-06'
  AND s.ret_5d IS NOT NULL
"""
r = ch_query_sql(sql_d)
print(f"JOIN vs correlated: {r}")

# Test E: SPX join
print("\n--- Test E: SPX join ---")
sql_e = """
WITH spx AS (
    SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL
    WHERE ts_code = 'SPX' AND trade_date >= '2019-12-01'
),
spx_lag AS (
    SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS spx_prev_pct
    FROM spx
),
stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '2020-01-01'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
SELECT count() AS n,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
FROM stock_filter s
INNER JOIN spx_lag sp ON s.trade_date = sp.trade_date
WHERE sp.spx_prev_pct > 0
  AND s.pct_chg >= 4
  AND s.amplitude >= 7
  AND s.trade_date <= '2026-05-06'
  AND s.ret_5d IS NOT NULL
"""
r = ch_query_sql(sql_e)
print(f"SPX join: {r}")

# Test F: Moneyflow join
print("\n--- Test F: Moneyflow join ---")
sql_f = """
WITH moneyflow_stocks AS (
    SELECT DISTINCT ts_code, trade_date FROM tushare.tushare_moneyflow FINAL
    WHERE trade_date >= '2020-01-01'
      AND sell_sm_vol > buy_sm_vol
      AND buy_elg_vol > sell_elg_vol
),
stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '2020-01-01'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
SELECT count() AS n,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
FROM stock_filter s
INNER JOIN moneyflow_stocks m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
WHERE s.pct_chg >= 4
  AND s.amplitude >= 7
  AND s.trade_date <= '2026-05-06'
  AND s.ret_5d IS NOT NULL
"""
r = ch_query_sql(sql_f)
print(f"Moneyflow join: {r}")
