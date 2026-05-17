#!/usr/bin/env python3
"""Iter22 T9: Cross-school combination backtest - Run all 12 combos"""
import sys, json, math, subprocess, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ch_helper import ch_query

BASE_DATE = '2026-05-06'  # signal cutoff (leave 5 days for ret_5d)
BASE_START = '2020-01-01'

def run_backtest(combo_name, combo_desc, where_clause):
    """Run SQL backtest for one combo"""
    sql = f"""
    WITH stock_filter AS (
        SELECT ts_code, trade_date, close, pct_chg, amount, amplitude,
               lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '{BASE_START}'
          AND ts_code NOT LIKE '30%'
          AND ts_code NOT LIKE '688%'
          AND ts_code NOT LIKE '920%'
          AND ts_code NOT LIKE '%ST%'
    )
    SELECT
        '{combo_name}' AS params_hash,
        COUNT(*) AS signal_count,
        round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
        round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
        round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
    FROM stock_filter
    WHERE {where_clause}
      AND trade_date <= '{BASE_DATE}'
      AND ret_5d IS NOT NULL
    """
    try:
        data = ch_query(sql, timeout=180)
        if data and len(data) > 0:
            r = data[0]
            n = int(r['signal_count'])
            r5 = float(r['avg_ret_5d_pct'])
            wr = float(r['win_rate_5d_pct'])
            std = float(r.get('std_5d_pct', 0) or 0)
            sharpe = round(r5 * 100 / std, 2) if std > 0 else 0
            return {
                'name': combo_name,
                'desc': combo_desc,
                'N': n,
                'R5': r5,
                'WR': wr,
                'Sharpe': sharpe,
                'pass': n >= 200 and wr >= 55.0 and r5 >= 5.0
            }
        else:
            return {'name': combo_name, 'desc': combo_desc, 'N': 0, 'R5': 0, 'WR': 0, 'Sharpe': 0, 'pass': False, 'error': 'no data'}
    except Exception as e:
        return {'name': combo_name, 'desc': combo_desc, 'N': 0, 'R5': 0, 'WR': 0, 'Sharpe': 0, 'pass': False, 'error': str(e)}


def run_backtest_with_join(combo_name, combo_desc, sql_template):
    """Run SQL backtest with custom SQL (for JOIN-based combos)"""
    sql = sql_template.format(BASE_DATE=BASE_DATE, BASE_START=BASE_START)
    try:
        data = ch_query(sql, timeout=300)
        if data and len(data) > 0:
            r = data[0]
            n = int(r['signal_count'])
            r5 = float(r['avg_ret_5d_pct'])
            wr = float(r['win_rate_5d_pct'])
            std = float(r.get('std_5d_pct', 0) or 0)
            sharpe = round(r5 * 100 / std, 2) if std > 0 else 0
            return {
                'name': combo_name,
                'desc': combo_desc,
                'N': n,
                'R5': r5,
                'WR': wr,
                'Sharpe': sharpe,
                'pass': n >= 200 and wr >= 55.0 and r5 >= 5.0
            }
        else:
            return {'name': combo_name, 'desc': combo_desc, 'N': 0, 'R5': 0, 'WR': 0, 'Sharpe': 0, 'pass': False, 'error': 'no data'}
    except Exception as e:
        return {'name': combo_name, 'desc': combo_desc, 'N': 0, 'R5': 0, 'WR': 0, 'Sharpe': 0, 'pass': False, 'error': str(e)}


# ============ COMBO DEFINITIONS ============

combos = []

# ---- Simple combos (single table, no JOIN needed) ----

# Combo 1: T2-C7 × T6-C1 — 60日底15%+暴涨+SPX (SPX needs join, so sans SPX first)
# Use daily_basic for 60d position via close_position
# Actually, for 60日底15%, we need position calc which is complex in SQL
# Let me use simpler conditions first

# For close_position, I need a window function subquery
# Let me build a generalized approach

def combo_60d_bottom15pct():
    """60日底15% condition via position calc"""
    return """
    ts_code IN (
        SELECT ts_code
        FROM (
            SELECT ts_code, trade_date, close,
                   MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min_60d,
                   MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max_60d
            FROM tushare.tushare_stock_daily FINAL
            WHERE trade_date >= '2019-12-01'
        ) AS pos
        WHERE pos.trade_date = s.trade_date
          AND (close - min_60d) / NULLIF(max_60d - min_60d, 0) <= 0.15
    )
    """

# Actually, the subquery referencing outer query won't work in ClickHouse.
# Let me use a different approach for position.

# For simplicity, I'll precompute positions or use Python-level filtering
# But that would be very slow. Let me try a different SQL approach.

# The approach used in T2-T8 analysts was:
# position = (close - low_60d) / (high_60d - low_60d) * 100
# This can be done with window functions

# Let me write the full SQL for each combo. For those needing position,
# I'll compute the position in a CTE.

# ======== NEW APPROACH: Build SQL for each combo ========

results = []

# --- Combo 1: T2-C7(deep bottom+surge) × T5-C6(value) deep value momentum ---
# C7: 60日底15%+涨≥4%+VR≥1.3+振幅≥7%+CM≤30亿  
# C6: PE≤15+PB≤2+底20%(60日)+VR≥1.3+振幅≥6%+CM≤50亿
# Merge: PE≤15+PB≤2+60日底15%+涨≥4%+VR≥1.3+振幅≥7%+CM≤30亿
print("Running Combo 1: T2-C7 × T5-C6 Deep Value Momentum...")
r = run_backtest(
    "C01_T2C7×T5C6",
    "深度价值动量: PE≤15+PB≤2+60日底15%+涨≥4%+VR≥1.3+振幅≥7%+CM≤30亿",
    """
    pct_chg >= 4
    AND amplitude >= 7
    AND ts_code IN (
        SELECT ts_code FROM tushare.tushare_daily_basic FINAL
        WHERE trade_date = s.trade_date
          AND pe > 0 AND pe <= 15
          AND pb > 0 AND pb <= 2
          AND circ_mv <= 300000
    )
    AND ts_code IN (
        SELECT ts_code FROM tushare.tushare_daily_basic FINAL
        WHERE trade_date = s.trade_date
          AND volume_ratio >= 1.3
    )
    """.strip()
)
results.append(r)

# --- Combo 2: T4-C7 × T6-C1 — 双资金流+PB≤2+SPX上涨 (need SPX join) ---
# T4-C7: sell_sm>buy_sm+buy_elg>sell_elg+60日底20%+pct≤-5%+振幅≥5%+VR≥1.0+CM≤30亿+PB≤2
# T6-C1: SPX前日涨+60日底20%+涨≥5%+振幅≥8%+VR≥1.5+CM≤30亿
# Wait, these have conflicting directions (pct≤-5% panic vs 涨≥5% up)
# Let me pick one direction - merge T4-C7 with SPX (from T6-C1)
# Combo 2: SPX涨+恐慌+双资金流+PB≤2
# sell_sm>buy_sm+buy_elg>sell_elg + pct≤-5% + 振幅≥5% + VR≥1.0 + CM≤30亿+PB≤2 + SPX涨
print("Running Combo 2: T4-C7 × T7-C1 SPX+双资金流恐慌...")
sql_c2 = """
WITH spx AS (
    SELECT trade_date, pct_chg
    FROM tushare.tushare_index_global FINAL
    WHERE ts_code = 'SPX' AND trade_date >= '2019-12-01'
),
stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '{BASE_START}'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
),
spx_lag AS (
    SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS spx_prev_pct
    FROM spx
)
SELECT
    'C02_T4C7×T7C1' AS params_hash,
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
    round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
FROM stock_filter s
JOIN spx_lag sp ON s.trade_date = sp.trade_date
WHERE s.pct_chg <= -5
  AND s.amplitude >= 5
  AND sp.spx_prev_pct > 0
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_moneyflow FINAL
      WHERE trade_date = s.trade_date
        AND sell_sm_vol > buy_sm_vol
        AND buy_elg_vol > sell_elg_vol
  )
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND pb > 0 AND pb <= 2
        AND circ_mv <= 300000
        AND volume_ratio >= 1.0
  )
  AND s.trade_date <= '{BASE_DATE}'
  AND ret_5d IS NOT NULL
"""
results.append(run_backtest_with_join("C02_T4C7×T7C1", "SPX涨+双资金流恐慌+PB≤2+CM≤30亿", sql_c2))

# --- Combo 3: T8-C3(巨阳线) × T6-C2(高股息低估值) ---
# T8-C3: 底部放量巨阳线 (涨≥5%+振幅≥8%+VR≥1.5+底60日20%+CM≤30亿)
# T6-C2: 60日底20%+涨≥3%+振幅≥6%+VR≥1.2+dv≥2%+PE≤20+PB≤2+CM≤50亿
# Merge: 涨≥5%+振幅≥8%+VR≥1.5+CM≤30亿+dv≥2%+PE≤20+PB≤2+60日底20%
print("Running Combo 3: T8-C3 × T6-C2 巨阳线+高股息低估值...")
r = run_backtest(
    "C03_T8C3×T6C2",
    "巨阳线+高股息低估值: 涨≥5%+振幅≥8%+VR≥1.5+CM≤30亿+dv≥2%+PE≤20+PB≤2",
    """
    pct_chg >= 5
    AND amplitude >= 8
    AND ts_code IN (
        SELECT ts_code FROM tushare.tushare_daily_basic FINAL
        WHERE trade_date = s.trade_date
          AND volume_ratio >= 1.5
          AND circ_mv <= 300000
          AND dv_ttm >= 2
          AND pe > 0 AND pe <= 20
          AND pb > 0 AND pb <= 2
    )
    """.strip()
)
results.append(r)

# --- Combo 4: T3-C2(SPX+恐慌+散户割肉+超大单+60日底10%) ---
# Already cross-school (T3×T7×T4), just verify
print("Running Combo 4: T3-C2 SPX+恐慌+双资金流+60日底10%...")
sql_c4 = """
WITH spx AS (
    SELECT trade_date, pct_chg
    FROM tushare.tushare_index_global FINAL
    WHERE ts_code = 'SPX' AND trade_date >= '2019-12-01'
),
stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d,
           MIN(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min_60d,
           MAX(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max_60d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '2019-11-01'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
),
spx_lag AS (
    SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS spx_prev_pct
    FROM spx
)
SELECT
    'C04_T3C2_T3xT7xT4' AS params_hash,
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
    round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
FROM stock_filter s
JOIN spx_lag sp ON s.trade_date = sp.trade_date
WHERE s.pct_chg <= -5
  AND sp.spx_prev_pct > 0
  AND (s.close - s.min_60d) / NULLIF(s.max_60d - s.min_60d, 0) <= 0.10
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_moneyflow FINAL
      WHERE trade_date = s.trade_date
        AND sell_sm_vol > buy_sm_vol
        AND buy_elg_vol > sell_elg_vol
  )
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND circ_mv <= 300000
        AND volume_ratio >= 1.0
  )
  AND s.trade_date <= '{BASE_DATE}'
  AND ret_5d IS NOT NULL
"""
results.append(run_backtest_with_join("C04_T3C2", "SPX涨+恐慌-5%+sell_sm>buy_sm+buy_elg>sell_elg+60日底10%+CM≤30亿", sql_c4))

# --- Combo 5: T6-C2(高股息低估值) + T7-C2(北向净流出) ---
# Need both SPX-like join pattern + mf
print("Running Combo 5: T6-C2 × T7-C2 北向+高股息低估值...")
sql_c5 = """
WITH north AS (
    SELECT trade_date, net_mf_amount
    FROM tushare.tushare_moneyflow_hsgt FINAL
    WHERE trade_date >= '2019-12-01'
),
north_lag AS (
    SELECT trade_date, lagInFrame(net_mf_amount, 1) OVER (ORDER BY trade_date) AS north_prev_net
    FROM north
),
stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '{BASE_START}'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
SELECT
    'C05_T6C2xT7C2' AS params_hash,
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
    round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
FROM stock_filter s
JOIN north_lag n ON s.trade_date = n.trade_date
WHERE s.pct_chg >= 3
  AND s.amplitude >= 6
  AND n.north_prev_net < 0  -- 北向前日净流出
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND volume_ratio >= 1.2
        AND circ_mv <= 500000
        AND dv_ttm >= 2
        AND pe > 0 AND pe <= 20
        AND pb > 0 AND pb <= 2
  )
  AND s.trade_date <= '{BASE_DATE}'
  AND ret_5d IS NOT NULL
"""
results.append(run_backtest_with_join("C05_T6C2×T7C2", "北向净流出+高股息低估值+放量中阳+CM≤50亿", sql_c5))

# --- Combo 6: T4-C9 × T8-C4 双资金流+曙光初现 ---
print("Running Combo 6: T4-C9 × T8-C4 双资金流+曙光初现...")
sql_c6 = """
WITH stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           s.open, s.high, s.low,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d,
           LAG(s.close, 1) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev_close,
           LAG(s.close, 2) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev2_close
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '{BASE_START}'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
SELECT
    'C06_T4C9xT8C4' AS params_hash,
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
    round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
FROM stock_filter s
WHERE s.pct_chg >= 3  -- 曙光初现: 今日收阳
  AND s.close > s.open  -- 阳线
  AND s.prev_close IS NOT NULL
  AND s.prev_close < s.prev2_close  -- 前日下跌
  AND (s.close - s.low) / NULLIF(s.high - s.low, 0) > 0.5  -- 非长上影
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_moneyflow FINAL
      WHERE trade_date = s.trade_date
        AND sell_sm_vol > buy_sm_vol
        AND buy_elg_vol > sell_elg_vol
  )
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND volume_ratio >= 1.0
        AND circ_mv <= 500000
        AND pb > 0 AND pb <= 2
  )
  AND s.trade_date <= '{BASE_DATE}'
  AND ret_5d IS NOT NULL
"""
results.append(run_backtest_with_join("C06_T4C9×T8C4", "双资金流+曙光初现+PB≤2+CM≤50亿", sql_c6))

# --- Combo 7: T3-C6(深恐慌-7%+SPX+散户割肉) + T5-C1b(破净高股息+CM30-100亿) ---
print("Running Combo 7: T3-C6 × T5-C1b 深恐慌+破净高股息...")
sql_c7 = """
WITH spx AS (
    SELECT trade_date, pct_chg
    FROM tushare.tushare_index_global FINAL
    WHERE ts_code = 'SPX' AND trade_date >= '2019-12-01'
),
stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '{BASE_START}'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
),
spx_lag AS (
    SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS spx_prev_pct
    FROM spx
)
SELECT
    'C07_T3C6xT5C1b' AS params_hash,
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
    round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
FROM stock_filter s
JOIN spx_lag sp ON s.trade_date = sp.trade_date
WHERE s.pct_chg <= -7
  AND sp.spx_prev_pct > 0
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_moneyflow FINAL
      WHERE trade_date = s.trade_date
        AND sell_sm_vol > buy_sm_vol
  )
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND volume_ratio >= 1.0
        AND pb > 0 AND pb <= 1
        AND dv_ttm >= 3
        AND circ_mv >= 300000 AND circ_mv <= 1000000
  )
  AND s.trade_date <= '{BASE_DATE}'
  AND ret_5d IS NOT NULL
"""
results.append(run_backtest_with_join("C07_T3C6×T5C1b", "深恐慌-7%+SPX涨+散户割肉+破净高股息+CM30-100亿", sql_c7))

# --- Combo 8: T7-C1(SPX恐慌底) × T4-C3(双资金流+PE≤20) ---
print("Running Combo 8: T7-C1 × T4-C3 SPX+恐慌+双资金流+PE...")
sql_c8 = """
WITH spx AS (
    SELECT trade_date, pct_chg
    FROM tushare.tushare_index_global FINAL
    WHERE ts_code = 'SPX' AND trade_date >= '2019-12-01'
),
stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '{BASE_START}'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
),
spx_lag AS (
    SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS spx_prev_pct
    FROM spx
)
SELECT
    'C08_T7C1xT4C3' AS params_hash,
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
    round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
FROM stock_filter s
JOIN spx_lag sp ON s.trade_date = sp.trade_date
WHERE s.pct_chg <= -5
  AND s.amplitude >= 6
  AND sp.spx_prev_pct > 0
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_moneyflow FINAL
      WHERE trade_date = s.trade_date
        AND sell_sm_vol > buy_sm_vol
        AND buy_elg_vol > sell_elg_vol
  )
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND volume_ratio >= 1.2
        AND circ_mv <= 500000
        AND pe > 0 AND pe <= 20
  )
  AND s.trade_date <= '{BASE_DATE}'
  AND ret_5d IS NOT NULL
"""
results.append(run_backtest_with_join("C08_T7C1×T4C3", "SPX涨+恐慌-5%+双资金流+PE≤20+CM≤50亿", sql_c8))

# --- Combo 9: T2-C6(底部放量中阳) × T4-C1b(净流入+散户恐慌) ---
print("Running Combo 9: T2-C6 × T4-C1b 净流入+底部放量中阳...")
sql_c9 = """
WITH stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '{BASE_START}'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
SELECT
    'C09_T2C6xT4C1b' AS params_hash,
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
    round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
FROM stock_filter s
WHERE s.pct_chg >= 3
  AND s.amplitude >= 6
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_moneyflow FINAL
      WHERE trade_date = s.trade_date
        AND net_mf_amount >= 5000000
        AND sell_sm_vol > buy_sm_vol
  )
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND volume_ratio >= 1.3
        AND circ_mv <= 500000
  )
  AND s.trade_date <= '{BASE_DATE}'
  AND ret_5d IS NOT NULL
"""
results.append(run_backtest_with_join("C09_T2C6×T4C1b", "净流入≥500万+散户恐慌+涨≥3%+振幅≥6%+VR≥1.3+CM≤50亿", sql_c9))

# --- Combo 10: T8-C1(底部放量大阳线) × T6-C1(SPX暴涨) ---
print("Running Combo 10: T8-C1 × T6-C1 SPX+底部放量大阳线...")
sql_c10 = """
WITH spx AS (
    SELECT trade_date, pct_chg
    FROM tushare.tushare_index_global FINAL
    WHERE ts_code = 'SPX' AND trade_date >= '2019-12-01'
),
stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           s.open, s.high,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '{BASE_START}'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
),
spx_lag AS (
    SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS spx_prev_pct
    FROM spx
)
SELECT
    'C10_T8C1xT6C1' AS params_hash,
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
    round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
FROM stock_filter s
JOIN spx_lag sp ON s.trade_date = sp.trade_date
WHERE s.pct_chg >= 5
  AND s.amplitude >= 8
  AND s.close / NULLIF(s.open, 0) >= 1.05  -- 大阳线
  AND sp.spx_prev_pct > 0
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND volume_ratio >= 1.5
        AND circ_mv <= 300000
  )
  AND s.trade_date <= '{BASE_DATE}'
  AND ret_5d IS NOT NULL
"""
results.append(run_backtest_with_join("C10_T8C1×T6C1", "SPX涨+大阳线≥5%+振幅≥8%+VR≥1.5+CM≤30亿", sql_c10))

# --- Combo 11: T3-C3(HS300恐慌+恐慌+散户割肉+PE) × T8-C2(长脚十字星) ---
# Need HS300 data from tushare_index_daily
print("Running Combo 11: T3-C3 × T8-C2 HS300恐慌+十字星...")
sql_c11 = """
WITH hs300 AS (
    SELECT trade_date, pct_chg
    FROM tushare.tushare_index_daily FINAL
    WHERE ts_code = '000300.SH' AND trade_date >= '2019-12-01'
),
stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           s.open, s.high, s.low,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d,
           LAG(s.close, 1) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev_close,
           LAG(s.close, 2) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) AS prev2_close
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '{BASE_START}'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
SELECT
    'C11_T3C3xT8C2' AS params_hash,
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
    round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
FROM stock_filter s
JOIN hs300 h ON s.trade_date = h.trade_date
WHERE s.pct_chg <= -5
  AND h.pct_chg <= -1.5  -- HS300当日跌≥1.5%
  -- 长脚十字星: 前日下跌 + 今日低开有长下影
  AND s.prev_close IS NOT NULL AND s.prev2_close IS NOT NULL
  AND s.prev_close < s.prev2_close  -- 前日下跌
  AND s.amplitude >= 5
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND volume_ratio >= 1.3
        AND circ_mv <= 500000
        AND pe > 0 AND pe <= 20
  )
  AND s.trade_date <= '{BASE_DATE}'
  AND ret_5d IS NOT NULL
"""
results.append(run_backtest_with_join("C11_T3C3×T8C2", "HS300跌≥1.5%+恐慌-5%+十字星+PE≤20+CM≤50亿", sql_c11))

# --- Combo 12: T6-C3(SPX涨+恐慌跌+双资金流) × T5-C1b(破净高股息) ---
print("Running Combo 12: T6-C3 × T5-C1b SPX+恐慌+双资金流+破净高股息...")
sql_c12 = """
WITH spx AS (
    SELECT trade_date, pct_chg
    FROM tushare.tushare_index_global FINAL
    WHERE ts_code = 'SPX' AND trade_date >= '2019-12-01'
),
stock_filter AS (
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.amount, s.amplitude,
           lead(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date) / s.close - 1 AS ret_5d
    FROM tushare.tushare_stock_daily FINAL s
    WHERE s.trade_date >= '{BASE_START}'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
),
spx_lag AS (
    SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS spx_prev_pct
    FROM spx
)
SELECT
    'C12_T6C3xT5C1b' AS params_hash,
    COUNT(*) AS signal_count,
    round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct,
    round(stddevSamp(ret_5d) * 100, 2) AS std_5d_pct
FROM stock_filter s
JOIN spx_lag sp ON s.trade_date = sp.trade_date
WHERE s.pct_chg >= -5 AND s.pct_chg <= -1  -- 微跌[-5%,-1%]
  AND s.amplitude >= 5
  AND sp.spx_prev_pct > 0
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_moneyflow FINAL
      WHERE trade_date = s.trade_date
        AND sell_sm_vol > buy_sm_vol
        AND buy_elg_vol > sell_elg_vol
  )
  AND s.ts_code IN (
      SELECT ts_code FROM tushare.tushare_daily_basic FINAL
      WHERE trade_date = s.trade_date
        AND volume_ratio >= 1.0
        AND pb > 0 AND pb <= 1
        AND dv_ttm >= 3
        AND circ_mv >= 300000 AND circ_mv <= 1000000
  )
  AND s.trade_date <= '{BASE_DATE}'
  AND ret_5d IS NOT NULL
"""
results.append(run_backtest_with_join("C12_T6C3×T5C1b", "SPX涨+微跌-5~-1%+双资金流+破净高股息+CM30-100亿", sql_c12))

# ============ OUTPUT ============
print("\n" + "="*100)
print("ITER22 T9: CROSS-SCHOOL COMBINATION BACKTEST RESULTS")
print("="*100)
print(f"{'ID':10s} {'N':>8s} {'R5%':>8s} {'WR%':>8s} {'Sharpe':>8s} {'Status':>10s}  Description")
print("-"*100)

passed = []
failed = []

for r in results:
    status = "✅ PASS" if r['pass'] else "❌ FAIL"
    print(f"{r['name']:10s} {r['N']:>8d} {r['R5']:>7.2f}% {r['WR']:>7.2f}% {r['Sharpe']:>7.2f} {status:>10s}  {r['desc']}")
    if r['pass']:
        passed.append(r)
    else:
        failed.append(r)

print("-"*100)
print(f"\nPassed: {len(passed)}/{len(results)}")
print(f"Failed: {len(failed)}/{len(results)}")

# Print details of passed combos
if passed:
    print("\n" + "="*80)
    print("PASSED COMBOS DETAIL:")
    print("="*80)
    passed_sorted = sorted(passed, key=lambda x: x['WR'], reverse=True)
    for i, r in enumerate(passed_sorted, 1):
        print(f"\n{i}. {r['name']}: {r['desc']}")
        print(f"   N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, Sharpe={r['Sharpe']}")

# Save results
output = {
    'results': results,
    'passed': passed,
    'failed': failed,
    'passed_count': len(passed),
    'failed_count': len(failed),
    'total_count': len(results)
}

with open('iter22_t9_results.json', 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\nResults saved to iter22_t9_results.json")
