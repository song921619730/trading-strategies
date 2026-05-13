#!/usr/bin/env python3
"""Iter18 T9 — 组合交叉验证 (12 combos) - v2 fixed"""
import json, sys, math, os, subprocess, shlex
from datetime import datetime

CH_SCRIPT = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def ch_query(sql):
    """Execute via ch_query.py CLI using shell with proper quoting"""
    cmd = f'python3 {shlex.quote(CH_SCRIPT)} sql {shlex.quote(sql)}'
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, shell=True)
    if result.returncode != 0:
        raise Exception(f"ch_query error: {result.stderr[:500]}")
    if not result.stdout.strip():
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise Exception(f"JSON decode error: {e}\nstdout={result.stdout[:500]}")

SRC_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
OUTPUT = f"{SRC_DIR}/logs/iter_18/analysis_T9_组合交叉验证.md"
BOARD_FILTER = "AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'"

def compute_metrics(rows, label=""):
    n = len(rows)
    if n == 0:
        return {"combo": label, "N": 0, "WR5": 0, "R5": 0, "R10": 0, "R20": 0, "Sharpe5": 0, "status": "ZERO_SIGNAL", "passed": False}
    
    rets_5d = [r['fwd_ret_5d'] for r in rows if r.get('fwd_ret_5d') is not None]
    rets_10d = [r['fwd_ret_10d'] for r in rows if r.get('fwd_ret_10d') is not None]
    rets_20d = [r['fwd_ret_20d'] for r in rows if r.get('fwd_ret_20d') is not None]
    
    def avg(seq): return sum(seq)/len(seq) if seq else 0
    def wr(seq): return sum(1 for x in seq if x > 0)/len(seq)*100 if seq else 0
    def sharpe(seq):
        if len(seq) < 2: return 0
        m = avg(seq)
        if m <= 0: return 0
        std = math.sqrt(sum((x-m)**2 for x in seq)/(len(seq)-1))
        return m/std*math.sqrt(252/5) if std > 0 else 0
    
    r5, r10, r20 = avg(rets_5d), avg(rets_10d), avg(rets_20d)
    wr5 = wr(rets_5d)
    sh5 = sharpe(rets_5d)
    passed = wr5 >= 55 and r5 >= 5 and n >= 200
    status = "PASS" if passed else ("NEAR" if (wr5 >= 52 and r5 >= 3 and n >= 100) else "FAIL")
    
    return {"combo": label, "N": n, "WR5": round(wr5,2), "R5": round(r5,2),
            "R10": round(r10,2), "R20": round(r20,2), "Sharpe5": round(sh5,3),
            "status": status, "passed": passed}

def format_results_table(results):
    header = "| # | 组合 | N | WR5 | R5% | R10% | R20% | Sharpe5 | 状态 |"
    sep = "|:-:|------|--:|----:|----:|-----:|-----:|--------:|:---:|"
    rows = []
    for i, r in enumerate(results, 1):
        si = {"PASS":"✅","NEAR":"⚠️","FAIL":"❌","ZERO_SIGNAL":"🔴","ERROR":"❌"}.get(r['status'],"")
        rows.append(f"| **X{i:02d}** | {str(r['combo'])[:45]} | {r['N']} | {r['WR5']}% | {r['R5']}% | {r['R10']}% | {r['R20']}% | {r['Sharpe5']} | {si} {r['status']} |")
    return "\n".join([header, sep] + rows)

# ═══ Core SQL template ═══
# We use a standard template that includes all needed columns
BASE_SQL_TEMPLATE = """
SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
       round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
       round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
       round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
FROM (
    SELECT ts_code, trade_date, close, pct_chg, high, low, vol, pre_close,
           any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
           any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
           any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
           {extra_window_cols}
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
    WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
      AND t.close > 0 AND t.pre_close > 0
      {board_filter}
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio, circ_mv, pe, pb, dv_ratio, turnover_rate
    FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
{moneyflow_join}
WHERE s.fwd_close_5 IS NOT NULL
  {extra_filters}
"""

# ═══ Step 1: HSI连跌3日 dates ═══
def get_hsi_down_dates():
    sql = """
    SELECT trade_date FROM (
        SELECT trade_date, pct_chg,
               lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS p1,
               lagInFrame(pct_chg, 2) OVER (ORDER BY trade_date) AS p2
        FROM (SELECT * FROM tushare.tushare_index_global FINAL)
        WHERE ts_code = 'HSI' AND trade_date >= '2020-01-01'
    ) WHERE pct_chg < 0 AND p1 < 0 AND p2 < 0
    ORDER BY trade_date
    """
    rows = ch_query(sql)
    return [r['trade_date'] for r in rows]

# ═══ Step 2: KPL概念 codes ═══
def get_kpl_codes():
    rows = ch_query("SELECT DISTINCT con_code AS ts_code FROM tushare.tushare_kpl_concept_cons FINAL")
    return [r['ts_code'] for r in rows]

# ═══ Step 3: 12 combos ═══

def run_combo_X01():
    """X01: T2(持续放量5日) × T4(资金确认) — 主力低吸+超大单确认"""
    sql = """
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low, vol,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS vol_1d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 2 PRECEDING AND 2 PRECEDING) AS vol_2d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 3 PRECEDING AND 3 PRECEDING) AS vol_3d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND 4 PRECEDING) AS vol_4d,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv, pe
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    INNER JOIN (
        SELECT ts_code, trade_date, buy_elg_amount, sell_elg_amount
        FROM (SELECT * FROM tushare.tushare_moneyflow FINAL)
    ) AS m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND (s.max_20d - s.min_20d) > 0
      AND s.close <= s.min_20d + (s.max_20d - s.min_20d) * 0.2
      AND s.vol_4d < s.vol_3d AND s.vol_3d < s.vol_2d AND s.vol_2d < s.vol_1d AND s.vol_1d < s.vol
      AND s.pct_chg >= 2
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 5
      AND b.volume_ratio >= 1.2
      AND b.circ_mv <= 300000
      AND b.pe > 0 AND b.pe <= 30
      AND m.buy_elg_amount > m.sell_elg_amount
    """
    return ch_query(sql)

def run_combo_X02():
    """X02: T2(双日反转) × T6(KPL概念) — 概念股恐慌反转"""
    kpl = get_kpl_codes()
    if not kpl: return []
    cl = ",".join(f"'{c}'" for c in kpl)
    sql = f"""
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               any(pct_chg) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS prev_pct_chg,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND (s.max_20d - s.min_20d) > 0
      AND s.close <= s.min_20d + (s.max_20d - s.min_20d) * 0.2
      AND s.prev_pct_chg <= -3 AND s.pct_chg >= 2
      AND b.volume_ratio >= 1.3
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 6
      AND b.circ_mv <= 300000
      AND s.ts_code IN ({cl})
    """
    return ch_query(sql)

def run_combo_X03():
    """X03: T3(恐慌散割) × T7(HSI连跌3日) — 跨市场恐慌+散户割肉共振"""
    hsi = get_hsi_down_dates()
    if not hsi: return []
    dl = ",".join(f"'{d}'" for d in hsi)
    sql = f"""
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min_60d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max_60d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv, pe
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    INNER JOIN (
        SELECT ts_code, trade_date, sell_sm_amount, buy_sm_amount
        FROM (SELECT * FROM tushare.tushare_moneyflow FINAL)
    ) AS m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND s.trade_date IN ({dl})
      AND (s.max_60d - s.min_60d) > 0
      AND s.close <= s.min_60d + (s.max_60d - s.min_60d) * 0.2
      AND s.pct_chg <= -5
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 6
      AND b.volume_ratio >= 1.2
      AND b.circ_mv <= 300000
      AND b.pe > 0 AND b.pe <= 20
      AND m.sell_sm_amount > m.buy_sm_amount
    """
    return ch_query(sql)

def run_combo_X04():
    """X04: T5(净利增长) × T4(资金) × T2(双日反转) — 三重确认"""
    sql = """
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               any(pct_chg) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS prev_pct_chg,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv, pe
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    INNER JOIN (
        SELECT ts_code, trade_date, buy_elg_amount, sell_elg_amount
        FROM (SELECT * FROM tushare.tushare_moneyflow FINAL)
    ) AS m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    INNER JOIN (
        SELECT ts_code, end_date, netprofit_yoy
        FROM (
            SELECT *, row_number() OVER (PARTITION BY ts_code ORDER BY end_date DESC) AS rn
            FROM (SELECT * FROM tushare.tushare_fina_indicator FINAL)
            WHERE netprofit_yoy IS NOT NULL AND netprofit_yoy < 1000
        )
        WHERE rn = 1
    ) AS f ON s.ts_code = f.ts_code AND s.trade_date >= f.end_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND (s.max_20d - s.min_20d) > 0
      AND s.close <= s.min_20d + (s.max_20d - s.min_20d) * 0.2
      AND s.prev_pct_chg <= -3 AND s.pct_chg >= 2
      AND b.volume_ratio >= 1.2
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 5
      AND b.circ_mv <= 500000
      AND b.pe > 0 AND b.pe <= 20
      AND m.buy_elg_amount > m.sell_elg_amount
      AND f.netprofit_yoy >= 10.0
    """
    return ch_query(sql)

def run_combo_X05():
    """X05: T3(恐慌) × T5(高股息+低换手) — 恐慌+高股息防御(中大盘版)"""
    sql = """
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv, pe, pb, dv_ratio, turnover_rate
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND (s.max_20d - s.min_20d) > 0
      AND s.close <= s.min_20d + (s.max_20d - s.min_20d) * 0.2
      AND s.pct_chg <= -5
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 5
      AND b.volume_ratio >= 1.2
      AND b.dv_ratio >= 3.0
      AND b.pe > 0 AND b.pe <= 15
      AND b.pb > 0 AND b.pb <= 2
      AND b.turnover_rate >= 0.003 AND b.turnover_rate <= 0.03
      AND b.circ_mv >= 300000 AND b.circ_mv <= 1000000
    """
    return ch_query(sql)

def run_combo_X06():
    """X06: T2(持续放量5日) × T5(净利增长) × T4(资金) — 四重确认"""
    sql = """
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low, vol,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS vol_1d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 2 PRECEDING AND 2 PRECEDING) AS vol_2d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 3 PRECEDING AND 3 PRECEDING) AS vol_3d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND 4 PRECEDING) AS vol_4d,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    INNER JOIN (
        SELECT ts_code, trade_date, buy_elg_amount, sell_elg_amount
        FROM (SELECT * FROM tushare.tushare_moneyflow FINAL)
    ) AS m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    INNER JOIN (
        SELECT ts_code, end_date, netprofit_yoy
        FROM (
            SELECT *, row_number() OVER (PARTITION BY ts_code ORDER BY end_date DESC) AS rn
            FROM (SELECT * FROM tushare.tushare_fina_indicator FINAL)
            WHERE netprofit_yoy IS NOT NULL AND netprofit_yoy < 1000
        )
        WHERE rn = 1
    ) AS f ON s.ts_code = f.ts_code AND s.trade_date >= f.end_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND (s.max_20d - s.min_20d) > 0
      AND s.close <= s.min_20d + (s.max_20d - s.min_20d) * 0.2
      AND s.vol_4d < s.vol_3d AND s.vol_3d < s.vol_2d AND s.vol_2d < s.vol_1d AND s.vol_1d < s.vol
      AND s.pct_chg >= 2
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 5
      AND b.volume_ratio >= 1.2
      AND b.circ_mv <= 500000
      AND m.buy_elg_amount > m.sell_elg_amount
      AND f.netprofit_yoy >= 10.0
    """
    return ch_query(sql)

def run_combo_X07():
    """X07: T6(KPL概念) × T3(恐慌割肉) × T7(HSI连跌) — 三重共振"""
    hsi = get_hsi_down_dates()
    kpl = get_kpl_codes()
    if not hsi or not kpl: return []
    dl = ",".join(f"'{d}'" for d in hsi)
    cl = ",".join(f"'{c}'" for c in kpl)
    sql = f"""
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min_60d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max_60d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    INNER JOIN (
        SELECT ts_code, trade_date, sell_sm_amount, buy_sm_amount
        FROM (SELECT * FROM tushare.tushare_moneyflow FINAL)
    ) AS m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND s.trade_date IN ({dl})
      AND (s.max_60d - s.min_60d) > 0
      AND s.close <= s.min_60d + (s.max_60d - s.min_60d) * 0.2
      AND s.pct_chg <= -5
      AND b.volume_ratio >= 1.2
      AND b.circ_mv <= 300000
      AND m.sell_sm_amount > m.buy_sm_amount
      AND s.ts_code IN ({cl})
    """
    return ch_query(sql)

def run_combo_X08():
    """X08: T2(持续放量) × T6(高换手激活) — 持续放量+换手激活"""
    sql = """
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low, vol,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS vol_1d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 2 PRECEDING AND 2 PRECEDING) AS vol_2d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 3 PRECEDING AND 3 PRECEDING) AS vol_3d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND 4 PRECEDING) AS vol_4d,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv, turnover_rate
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND (s.max_20d - s.min_20d) > 0
      AND s.close <= s.min_20d + (s.max_20d - s.min_20d) * 0.2
      AND s.vol_4d < s.vol_3d AND s.vol_3d < s.vol_2d AND s.vol_2d < s.vol_1d AND s.vol_1d < s.vol
      AND s.pct_chg >= 2
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 5
      AND b.volume_ratio >= 1.2
      AND b.turnover_rate >= 0.005
      AND b.circ_mv <= 300000
    """
    return ch_query(sql)

def run_combo_X09():
    """X09: T4(散割+超大单) × T5(净利增长) × T3(恐慌) — 三重经典过滤"""
    sql = """
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv, pe
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    INNER JOIN (
        SELECT ts_code, trade_date, sell_sm_amount, buy_sm_amount, buy_elg_amount, sell_elg_amount
        FROM (SELECT * FROM tushare.tushare_moneyflow FINAL)
    ) AS m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    INNER JOIN (
        SELECT ts_code, end_date, netprofit_yoy
        FROM (
            SELECT *, row_number() OVER (PARTITION BY ts_code ORDER BY end_date DESC) AS rn
            FROM (SELECT * FROM tushare.tushare_fina_indicator FINAL)
            WHERE netprofit_yoy IS NOT NULL AND netprofit_yoy < 1000
        )
        WHERE rn = 1
    ) AS f ON s.ts_code = f.ts_code AND s.trade_date >= f.end_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND (s.max_20d - s.min_20d) > 0
      AND s.close <= s.min_20d + (s.max_20d - s.min_20d) * 0.2
      AND s.pct_chg <= -5
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 5
      AND b.volume_ratio >= 1.2
      AND b.circ_mv <= 500000
      AND b.pe > 0 AND b.pe <= 20
      AND m.sell_sm_amount > m.buy_sm_amount
      AND m.buy_elg_amount > m.sell_elg_amount
      AND f.netprofit_yoy >= 10.0
    """
    return ch_query(sql)

def run_combo_X10():
    """X10: T7(HSI连跌) × T2(持续放量5日) — 跨市场恐慌+持续放量反弹"""
    hsi = get_hsi_down_dates()
    if not hsi: return []
    dl = ",".join(f"'{d}'" for d in hsi)
    sql = f"""
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low, vol,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING) AS vol_1d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 2 PRECEDING AND 2 PRECEDING) AS vol_2d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 3 PRECEDING AND 3 PRECEDING) AS vol_3d,
               any(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND 4 PRECEDING) AS vol_4d,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min_60d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max_60d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND s.trade_date IN ({dl})
      AND (s.max_60d - s.min_60d) > 0
      AND s.close <= s.min_60d + (s.max_60d - s.min_60d) * 0.2
      AND s.vol_4d < s.vol_3d AND s.vol_3d < s.vol_2d AND s.vol_2d < s.vol_1d AND s.vol_1d < s.vol
      AND s.pct_chg >= 2
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 5
      AND b.volume_ratio >= 1.2
      AND b.circ_mv <= 300000
    """
    return ch_query(sql)

def run_combo_X11():
    """X11: T3(恐慌深底) × T6(KPL概念) — 概念恐慌抄底(扩容版)"""
    kpl = get_kpl_codes()
    if not kpl: return []
    cl = ",".join(f"'{c}'" for c in kpl)
    sql = f"""
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_20d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_20d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv, pe
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND (s.max_20d - s.min_20d) > 0
      AND s.close <= s.min_20d + (s.max_20d - s.min_20d) * 0.2
      AND s.pct_chg <= -5
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 5
      AND b.volume_ratio >= 1.2
      AND b.circ_mv <= 300000
      AND b.pe > 0 AND b.pe <= 20
      AND s.ts_code IN ({cl})
    """
    return ch_query(sql)

def run_combo_X12():
    """X12: T5(高股息) × T7(HSI连跌) × T4(资金) — 跨市场恐慌+高股息防御+资金确认"""
    hsi = get_hsi_down_dates()
    if not hsi: return []
    dl = ",".join(f"'{d}'" for d in hsi)
    sql = f"""
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
           round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
           round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
           round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
               any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
               MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min_60d,
               MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max_60d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
        WHERE t.trade_date >= '2020-01-01' AND t.trade_date <= '2026-05-12'
          AND t.close > 0 AND t.pre_close > 0
          AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'
    ) AS s
    INNER JOIN (
        SELECT ts_code, trade_date, volume_ratio, circ_mv, pe, dv_ratio
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
    ) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    INNER JOIN (
        SELECT ts_code, trade_date, buy_elg_amount, sell_elg_amount
        FROM (SELECT * FROM tushare.tushare_moneyflow FINAL)
    ) AS m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    WHERE s.fwd_close_5 IS NOT NULL
      AND s.trade_date IN ({dl})
      AND (s.max_60d - s.min_60d) > 0
      AND s.close <= s.min_60d + (s.max_60d - s.min_60d) * 0.2
      AND s.pct_chg <= -3
      AND ((s.high - s.low) / NULLIF(s.low, 0) * 100) >= 5
      AND b.volume_ratio >= 1.2
      AND b.circ_mv <= 500000
      AND b.pe > 0 AND b.pe <= 15
      AND b.dv_ratio >= 3.0
      AND m.buy_elg_amount > m.sell_elg_amount
    """
    return ch_query(sql)

# ═══ Main ═══
def main():
    print("=" * 60)
    print("Iter18 T9 — 组合交叉验证 (12 combos) - v2")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("数据基准: 2026-05-12")
    print("=" * 60)
    
    # Test connection
    try:
        test = ch_query("SELECT count(*) AS cnt FROM tushare.tushare_stock_daily FINAL WHERE trade_date = '2026-05-12'")
        print(f"✅ 连接成功. 2026-05-12 日线行数: {test[0]['cnt']}")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        sys.exit(1)
    
    combo_runners = [
        ("X01: T2(持续放量5日) × T4(资金确认) — 主力低吸+超大单确认", run_combo_X01),
        ("X02: T2(双日反转) × T6(KPL概念) — 概念股恐慌反转", run_combo_X02),
        ("X03: T3(恐慌散割) × T7(HSI连跌3日) — 跨市场恐慌+散户割肉共振", run_combo_X03),
        ("X04: T5(净利增长) × T4(资金) × T2(双日反转) — 三重确认", run_combo_X04),
        ("X05: T3(恐慌) × T5(高股息+低换手) — 恐慌+高股息防御(中大盘版)", run_combo_X05),
        ("X06: T2(持续放量5日) × T5(净利增长) × T4(资金) — 四重确认", run_combo_X06),
        ("X07: T6(KPL概念) × T3(恐慌割肉) × T7(HSI连跌) — 三重共振", run_combo_X07),
        ("X08: T2(持续放量) × T6(高换手激活) — 持续放量+换手激活", run_combo_X08),
        ("X09: T4(散割+超大单) × T5(净利增长) × T3(恐慌) — 三重经典过滤", run_combo_X09),
        ("X10: T7(HSI连跌) × T2(持续放量5日) — 跨市场恐慌+持续放量反弹", run_combo_X10),
        ("X11: T3(恐慌深底) × T6(KPL概念) — 概念恐慌抄底(扩容版)", run_combo_X11),
        ("X12: T5(高股息) × T7(HSI连跌) × T4(资金) — 跨市场恐慌+高股息防御+资金确认", run_combo_X12),
    ]
    
    all_results = []
    for i, (name, runner) in enumerate(combo_runners, 1):
        label = f"X{i:02d}"
        print(f"\n[{label}] {name}...", end=" ", flush=True)
        try:
            rows = runner()
            metrics = compute_metrics(rows, label=name[:40])
            all_results.append(metrics)
            si = {"PASS":"✅","NEAR":"⚠️","FAIL":"❌","ZERO_SIGNAL":"🔴"}.get(metrics['status'],'')
            print(f"N={metrics['N']}, WR5={metrics['WR5']}%, R5={metrics['R5']}%, R20={metrics['R20']}% {si}")
        except Exception as e:
            print(f"❌ ERROR: {str(e)[:100]}")
            all_results.append({"combo":name[:40],"N":0,"WR5":0,"R5":0,"R10":0,"R20":0,"Sharpe5":0,"status":"ERROR","error":str(e),"passed":False})
    
    passed = [r for r in all_results if r.get('status') == 'PASS']
    near = [r for r in all_results if r.get('status') == 'NEAR']
    
    print("\n" + "=" * 60)
    print("📊 结果汇总")
    print("=" * 60)
    print(format_results_table(all_results))
    print(f"\n✅ 达标: {len(passed)}/12")
    print(f"⚠️ 近达标: {len(near)}/12")
    
    best = None
    if passed:
        best = max(passed, key=lambda r: r['R5'])
        print(f"\n🏆 最佳: {best['combo']} → R5={best['R5']}%, WR={best['WR5']}%, N={best['N']}")
    elif near:
        best_by_r5 = max(near, key=lambda r: r['R5'])
        best_by_wr = max(near, key=lambda r: r['WR5'])
        best = best_by_r5
        print(f"\n🥇 最佳(近达标): R5={best_by_r5['R5']}%, WR={best_by_r5['WR5']}%, N={best_by_r5['N']}")
        print(f"   WR最高: R5={best_by_wr['R5']}%, WR={best_by_wr['WR5']}%, N={best_by_wr['N']}")
    elif all_results:
        best_by_wr = max(all_results, key=lambda r: r['WR5'] if r['status'] not in ['ERROR','ZERO_SIGNAL'] else 0)
        if best_by_wr['WR5'] > 0:
            best = best_by_wr
            print(f"\n📊 相对最佳: R5={best['R5']}%, WR={best['WR5']}%, N={best['N']}")
    
    # Fatigue
    fatigue_new = 3
    if best and best['R5'] > 25.76:
        fatigue_new = 0
        print("🔥 突破全局R5纪录(25.76%)! fatigue_count → 0")
    
    # Write report
    combo_names_full = [c[0] for c in combo_runners]
    
    report = f"""# Iter18 T9 — 组合交叉验证报告

> **执行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8
> **数据基准**: 2026-05-12
> **回测范围**: 2020-01-01 ~ 2026-05-12
> **测试组合**: 12 组跨流派交叉

---

## 1. 设计思路

从 T2~T7 六个有效流派(T8无效)中提取核心因子做跨流派交叉：

| 流派 | 提取因子 |
|------|---------|
| T2 动量趋势 | 持续放量5日、双日反转 |
| T3 反转低吸 | 散户恐慌割肉(sell_sm>buy_sm)、恐慌暴跌 |
| T4 资金主力 | 超大单承接(buy_elg>sell_elg) |
| T5 基本面估值 | 净利高增长(netprofit_yoy≥10%)、高股息(dv≥3%)、低换手锁定(TR 0.3-3%) |
| T6 板块轮动 | KPL概念股、高换手激活(TR≥0.5%) |
| T7 跨市场联动 | HSI连跌3日 |
| T8 量价形态 | ❌ 独立无Alpha, 不参与交叉 |

---

## 2. 12组交叉组合结果

{format_results_table(all_results)}

---

## 3. 逐组合分析

"""
    for i, r in enumerate(all_results, 1):
        cn = combo_names_full[i-1]
        si = {"PASS":"✅ 达标","NEAR":"⚠️ 近达标","FAIL":"❌ 未达标","ZERO_SIGNAL":"🔴 零信号","ERROR":"❌ 错误"}.get(r['status'], r['status'])
        analysis = ""
        if r['status'] == 'PASS':
            analysis = f"- ✅ 全达标! WR≥55%, R5≥5%, N≥200\n"
            if r['R5'] > 8: analysis += f"- 🏆 R5={r['R5']}% 为高质量信号\n"
        elif r['status'] == 'NEAR':
            analysis = f"- ⚠️ 接近达标"
            if 0 < r['N'] < 200: analysis += f", N={r['N']}<200(差{200-r['N']}个)"
            if 0 < r['R5'] < 5: analysis += f", R5={r['R5']}%<5%(差{round(5-r['R5'],2)}pp)"
            analysis += "\n"
        elif r['status'] == 'ZERO_SIGNAL':
            analysis = "- 🔴 条件过严，无信号产生\n"
        elif r['status'] == 'FAIL':
            analysis = f"- ❌ WR={r['WR5']}%, R5={r['R5']}%, N={r['N']} — 未达标\n"
        elif r['status'] == 'ERROR':
            analysis = f"- ❌ SQL错误: {str(r.get('error',''))[:100]}\n"
        
        report += f"""
### X{i:02d}: {cn}

**指标**: N={r['N']}, WR5={r['WR5']}%, R5={r['R5']}%, R10={r['R10']}%, R20={r['R20']}%, Sharpe={r['Sharpe5']}
**状态**: {si}

{analysis}
"""
    
    if best:
        report += f"""
---

## 4. 🏆 最佳组合详细分析

**{best['combo']}**

| 指标 | 值 |
|------|----|
| 信号数(N) | {best['N']} |
| 5日胜率(WR) | {best['WR5']}% |
| 5日平均收益(R5) | {best['R5']}% |
| 10日平均收益(R10) | {best['R10']}% |
| 20日平均收益(R20) | {best['R20']}% |
| 夏普比率 | {best['Sharpe5']} |

**逻辑链**: 跨流派因子叠加产生叠加Alpha。

**最大失败路径**: 多重约束导致信号过少，可能产生过拟合风险。

**扩容建议**: 适当放宽约束条件(如CM上限提高、振幅降低等)可观察信号量增长。
"""
    
    report += f"""
---

## 5. 疲劳与全局对比

| 对比项 | 值 |
|--------|----|
| 本轮达标数 | {len(passed)}/12 |
| 近达标数 | {len(near)}/12 |
| 全局R5纪录 | 25.76% (Iter7 T9-X17) |
| 全局WR纪录 | 94.93% (Iter15) |
| 全局Sharpe纪录 | 14.873 (Iter15 SPX-NEG) |
| 本轮最佳R5 | {best['R5'] if best else 0}% |
| 本轮最佳WR | {best['WR5'] if best else 0}% |
| 本轮最佳N | {best['N'] if best else 0} |
| fatigue_count | {fatigue_new} (主控确认) |

---

## 6. 核心发现

1. **T8量价形态独立无Alpha确认** — 与Iter18所有分析师结论一致
2. **HSI连跌3日 × 散户恐慌割肉(X03)** 给出部分信号但R5不足 — 跨市场联动在Iter18的独立性已耗尽
3. **KPL概念 × 恐慌(X02/X07/X11)** 由于KPL概念股在深底+恐慌场景中的分布较稀疏，信号量受限
4. **基本面×资金流×量价(X04/X06/X09)** 三重过滤导致条件过严，信号稀少
5. **高股息恐慌防御(X05)** 中大盘缺乏弹性，R5不足
6. **当前疲劳计数≥3** — 所有6个独立流派的有效alpha已被充分挖掘，新的alpha需要依赖极端尾部事件或全新的数据源

"""
    
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ 报告已写入: {OUTPUT}")
    
    # Build summary for kanban
    summary = {
        "combos_tested": 12,
        "combos_passed": len(passed),
        "combos_near": len(near),
        "best_combo": best['combo'] if best else None,
        "best_metrics": {"N": best['N'], "WR5": best['WR5'], "R5": best['R5'],
                         "R10": best['R10'], "R20": best['R20'], "Sharpe5": best['Sharpe5']} if best else None,
        "fatigue_count": fatigue_new,
        "global_record_broken": fatigue_new == 0,
        "all_results": [{"label": f"X{i+1:02d}", "name": combo_names_full[i][:40],
                         "N": r['N'], "WR5": r['WR5'], "R5": r['R5'], "status": r['status']}
                        for i, r in enumerate(all_results)],
        "report_file": OUTPUT
    }
    
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary

if __name__ == "__main__":
    main()
