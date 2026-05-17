#!/usr/bin/env python3
"""Iter22 T9: Cross-school combination backtest (FIXED SQL)"""
import json, subprocess, sys

CH_SCRIPT = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def ch_query_sql(sql):
    result = subprocess.run(
        [sys.executable, CH_SCRIPT, "sql", sql],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr[:500]}", file=sys.stderr)
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}, stdout: {result.stdout[:500]}", file=sys.stderr)
        return None

def run_backtest(combo_name, combo_desc, where_clause, extra_cte=""):
    """Run SQL backtest - FINAL must use subquery wrapping, no FINAL AS alias"""
    sql = f"""
    WITH stock_filter AS (
        SELECT ts_code, trade_date, close, pct_chg,
               (high - low) / NULLIF(pre_close, 0) * 100 AS ampl,
               lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
        WHERE s.trade_date >= '2020-01-01'
          AND s.ts_code NOT LIKE '30%'
          AND s.ts_code NOT LIKE '688%'
          AND s.ts_code NOT LIKE '920%'
          AND s.ts_code NOT LIKE '%ST%'
    )
    {extra_cte}
    SELECT
        '{combo_name}' AS params_hash,
        COUNT(*) AS signal_count,
        round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
        round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
        round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
    FROM stock_filter
    WHERE {where_clause}
      AND trade_date <= '2026-05-06'
      AND ret_5d IS NOT NULL
    """
    r = ch_query_sql(sql)
    if r is None:
        return {'name': combo_name, 'desc': combo_desc, 'N': 0, 'R5': 0, 'WR': 0, 'Sharpe': 0, 'pass': False, 'error': 'SQL failed'}
    if len(r) == 0:
        return {'name': combo_name, 'desc': combo_desc, 'N': 0, 'R5': 0, 'WR': 0, 'Sharpe': 0, 'pass': False, 'error': 'no rows'}
    rr = r[0]
    n = int(rr['signal_count'])
    r5 = float(rr['avg_ret_5d_pct'])
    wr = float(rr['win_rate_5d_pct'])
    std = float(rr.get('std_5d_pct', 0) or 0)
    sharpe = round(r5 * 100 / std, 2) if std > 0 else 0
    return {
        'name': combo_name, 'desc': combo_desc,
        'N': n, 'R5': r5, 'WR': wr, 'Sharpe': sharpe,
        'pass': n >= 200 and wr >= 55.0 and r5 >= 5.0
    }


# Test with fixed SQL first
print("="*80)
print("DEBUG: Testing FIXED SQL patterns")
print("="*80)

# Test 1: Basic filter (no FINAL AS alias, no amplitude)
print("\n--- Test 1: Basic fixed SQL ---")
sql1 = """
SELECT count() AS n, round(avg(pct_chg), 2) AS avg_pct
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
WHERE s.trade_date >= '2020-01-01'
  AND s.trade_date <= '2026-05-06'
  AND s.pct_chg >= 4
  AND (s.high - s.low) / NULLIF(s.pre_close, 0) * 100 >= 7
  AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
  AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
"""
r1 = ch_query_sql(sql1)
print(f"Test 1: {r1}")

# Test 2: WITH + window function
print("\n--- Test 2: WITH + window (no FINAL AS alias) ---")
sql2 = """
WITH stock_filter AS (
    SELECT ts_code, trade_date, close, pct_chg,
           (high - low) / NULLIF(pre_close, 0) * 100 AS ampl,
           lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    WHERE s.trade_date >= '2020-01-01'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
SELECT count() AS n,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
FROM stock_filter
WHERE pct_chg >= 4
  AND ampl >= 7
  AND trade_date <= '2026-05-06'
  AND ret_5d IS NOT NULL
"""
r2 = ch_query_sql(sql2)
print(f"Test 2: {r2}")

# Test 3: WITH + daily_basic join (using INNER JOIN with subquery wrappers)
print("\n--- Test 3: JOIN with daily_basic ---")
sql3 = """
WITH
stock_filter AS (
    SELECT ts_code, trade_date, close, pct_chg,
           (high - low) / NULLIF(pre_close, 0) * 100 AS ampl,
           lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    WHERE s.trade_date >= '2020-01-01'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
),
basic AS (
    SELECT ts_code, trade_date, pe, pb, circ_mv, volume_ratio
    FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS d
    WHERE d.trade_date >= '2020-01-01' AND d.pe > 0 AND d.pe <= 15 AND d.pb > 0 AND d.pb <= 2 AND d.circ_mv <= 300000
)
SELECT count() AS n,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
FROM stock_filter s
INNER JOIN basic b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
WHERE s.pct_chg >= 4
  AND s.ampl >= 7
  AND s.trade_date <= '2026-05-06'
  AND s.ret_5d IS NOT NULL
"""
r3 = ch_query_sql(sql3)
print(f"Test 3 (value+micro): {r3}")

# Test 4: SPX join
if r2 and len(r2) > 0:
    print("\n--- Test 4: SPX JOIN ---")
    sql4 = """
    WITH
    spx AS (
        SELECT trade_date, pct_chg
        FROM (SELECT * FROM tushare.tushare_index_global FINAL) AS g
        WHERE g.ts_code = 'SPX' AND g.trade_date >= '2019-12-01'
    ),
    spx_lag AS (
        SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS spx_prev_pct
        FROM spx
    ),
    stock_filter AS (
        SELECT ts_code, trade_date, close, pct_chg,
               (high - low) / NULLIF(pre_close, 0) * 100 AS ampl,
               lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
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
      AND s.ampl >= 7
      AND s.trade_date <= '2026-05-06'
      AND s.ret_5d IS NOT NULL
    """
    r4 = ch_query_sql(sql4)
    print(f"Test 4 (SPX+surge): {r4}")
else:
    print("\n--- Skipping Test 4 (depends on Test 2) ---")
