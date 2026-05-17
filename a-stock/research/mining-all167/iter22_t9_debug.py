#!/usr/bin/env python3
"""T9 Debug: Test various SQL patterns"""
import sys; sys.path.insert(0, '.')
from ch_helper import ch_query

# Test 1: Simple pattern - single table
print("=== Test 1: Simple single table ===")
sql1 = """
SELECT COUNT(*) AS n, round(AVG(pct_chg), 2) AS avg_pct
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date = toDate('2026-05-06')
  AND pct_chg >= 4
  AND amplitude >= 7
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
"""
r = ch_query(sql1)
print(r)

# Test 2: With subquery IN pattern
print("\n=== Test 2: IN subquery with daily_basic ===")
sql2 = """
SELECT COUNT(*) AS n
FROM tushare.tushare_stock_daily FINAL s
WHERE s.trade_date = toDate('2026-05-06')
  AND s.pct_chg >= 4
  AND s.amplitude >= 7
  AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
  AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = toDate('2026-05-06')
        AND pe > 0 AND pe <= 15
        AND pb > 0 AND pb <= 2
        AND circ_mv <= 300000
  )
"""
r = ch_query(sql2)
print(r)

# Test 3: date format - '2020-01-01' vs toDate()
print("\n=== Test 3: date range with string vs toDate ===")
sql3 = """
SELECT COUNT(*) AS n
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '2020-01-01'
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
LIMIT 1
"""
r = ch_query(sql3)
print(r)

# Test 4: WITH + window function + JOIN
print("\n=== Test 4: Basic backtest pattern ===")
sql4 = """
WITH stock_filter AS (
    SELECT ts_code, trade_date, close, pct_chg, amount, amplitude,
           lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2020-01-01'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
      AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
)
SELECT
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct
FROM stock_filter
WHERE pct_chg >= 4
  AND amplitude >= 7
  AND trade_date <= '2026-05-06'
  AND ret_5d IS NOT NULL
"""
r = ch_query(sql4)
print(r)

# Test 5: WITH + window function + daily_basic subquery
print("\n=== Test 5: WITH + subquery for basic ===")
sql5 = """
WITH stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '2020-01-01'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
SELECT COUNT(*) AS n
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
        AND circ_mv <= 300000
  )
"""
r = ch_query(sql5)
print(r)

# Test 6: moneyflow subquery
print("\n=== Test 6: moneyflow subquery ===")
sql6 = """
SELECT COUNT(*) AS n
FROM tushare.tushare_stock_daily FINAL s
WHERE s.trade_date = toDate('2026-05-06')
  AND s.pct_chg >= 4
  AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
  AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_moneyflow FINAL
      WHERE trade_date = toDate('2026-05-06')
        AND net_mf_amount >= 5000000
  )
"""
r = ch_query(sql6)
print(r)
