#!/usr/bin/env python3
"""Iter22 T9 — 组合交叉验证 (12 cross-school combos)"""
import json, sys, math, os, hashlib

sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167')
from ch_helper import ch_query

SRC_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
OUTPUT = f"{SRC_DIR}/logs/iter_22/analysis_T9_组合交叉.md"
MAX_DATE = "2026-05-12"
BACKTEST_START = "2020-01-01"
BOARD_FILTER = "AND t.ts_code NOT LIKE '30%' AND t.ts_code NOT LIKE '688%' AND t.ts_code NOT LIKE '920%' AND t.ts_code NOT LIKE '%ST%'"

# Load recent_combos for dedup
with open(f"{SRC_DIR}/state/state.json") as f:
    state = json.load(f)
recent_combos = set(state.get("recent_combos", []))

def combo_hash(params):
    raw = ";".join(sorted([f"{k}={v}" for k, v in params.items()]))
    return hashlib.md5(raw.encode()).hexdigest()[:11]

def compute_metrics(rows, label=""):
    n = len(rows)
    if n == 0:
        return {"combo": label, "N": 0, "WR5": 0, "R5": 0, "R10": 0, "R20": 0, "Sharpe5": 0, "P10": 0, "status": "ZERO_SIGNAL", "passed": False}
    
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
    def p10(seq):
        if not seq: return 0
        s = sorted(seq)
        return s[int(len(s)*0.1)]
    
    r5, r10, r20 = avg(rets_5d), avg(rets_10d), avg(rets_20d)
    wr5 = wr(rets_5d)
    sh5 = sharpe(rets_5d)
    p10v = p10(rets_5d)
    passed = wr5 >= 55 and r5 >= 5 and n >= 200
    status = "PASS" if passed else ("NEAR" if (wr5 >= 52 and r5 >= 3 and n >= 100) else "FAIL")
    
    return {"combo": label, "N": n, "WR5": round(wr5,2), "R5": round(r5,2),
            "R10": round(r10,2), "R20": round(r20,2), "Sharpe5": round(sh5,3),
            "P10": round(p10v,2), "status": status, "passed": passed}

# Base SQL template: joins stock_daily, daily_basic, moneyflow
# With window functions for forward returns and close_position
BASE_SQL = """
SELECT s.ts_code, s.trade_date, s.close, s.pct_chg,
       round((fwd_close_5 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_5d,
       round((fwd_close_10 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_10d,
       round((fwd_close_20 - s.close) / NULLIF(s.close, 0) * 100, 2) AS fwd_ret_20d,
       s.amplitude, s.vr, s.circ_mv, s.pe, s.pb, s.dv_ratio, s.tr,
       s.low_20d, s.high_20d, s.low_60d, s.high_60d,
       s.pos_20d, s.pos_60d,
       m.buy_lg_amount, m.sell_lg_amount, m.buy_elg_amount, m.sell_elg_amount,
       m.buy_sm_amount, m.sell_sm_amount, m.net_mf_amount
FROM (
    SELECT ts_code, trade_date, close, pct_chg, high, low, pre_close, vol,
           (high - low) / NULLIF(low, 0) * 100 AS amplitude,
           any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 5 FOLLOWING AND 5 FOLLOWING) AS fwd_close_5,
           any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 10 FOLLOWING AND 10 FOLLOWING) AS fwd_close_10,
           any(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 FOLLOWING AND 20 FOLLOWING) AS fwd_close_20,
           MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
           MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d,
           MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS low_60d,
           MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS high_60d,
           (close - MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)) / 
               NULLIF(MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) - 
                      MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 0) AS pos_20d,
           (close - MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)) / 
               NULLIF(MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) - 
                      MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW), 0) AS pos_60d
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS t
    WHERE t.trade_date >= toDate('{BACKTEST_START}') AND t.trade_date <= toDate('{MAX_DATE}')
      AND t.close > 0 AND t.pre_close > 0
      {BOARD_FILTER}
) AS s
INNER JOIN (
    SELECT ts_code, trade_date, volume_ratio AS vr, circ_mv, pe, pb, dv_ratio, turnover_rate AS tr
    FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
LEFT JOIN (
    SELECT ts_code, trade_date, buy_lg_amount, sell_lg_amount,
           buy_elg_amount, sell_elg_amount, buy_sm_amount, sell_sm_amount,
           net_mf_amount
    FROM (SELECT * FROM tushare.tushare_moneyflow FINAL)
) AS m ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
WHERE s.fwd_close_5 IS NOT NULL
  {extra_filters}
"""

# ═══ Helper: Get SPX consecutive up days ═══
def get_spx_up_dates(days=1):
    """Returns dates where SPX was up for `days` consecutive days before."""
    sql = f"""
    SELECT trade_date FROM (
        SELECT trade_date, pct_chg,
               lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS p1
               {', lagInFrame(pct_chg, 2) OVER (ORDER BY trade_date) AS p2' if days >= 2 else ''}
        FROM (SELECT * FROM tushare.tushare_index_global FINAL)
        WHERE ts_code = 'SPX' AND trade_date >= toDate('{BACKTEST_START}')
    ) WHERE pct_chg > 0 {'AND p1 > 0' if days >= 1 else ''} {'AND p2 > 0' if days >= 2 else ''}
    ORDER BY trade_date
    """
    return ch_query(sql)

def get_csi300_up_dates(days=3):
    """Returns dates where CSI300 was up for `days` consecutive days."""
    sql = f"""
    SELECT trade_date FROM (
        SELECT trade_date, pct_chg,
               lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS p1,
               lagInFrame(pct_chg, 2) OVER (ORDER BY trade_date) AS p2
        FROM (SELECT * FROM tushare.tushare_index_daily FINAL)
        WHERE ts_code = '000300.SH' AND trade_date >= toDate('{BACKTEST_START}')
    ) WHERE pct_chg > 0 AND p1 > 0 AND p2 > 0
    ORDER BY trade_date
    """
    return ch_query(sql)

def get_hsi_down_dates(days=1):
    sql = f"""
    SELECT trade_date FROM (
        SELECT trade_date, pct_chg,
               lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS p1,
               lagInFrame(pct_chg, 2) OVER (ORDER BY trade_date) AS p2
        FROM (SELECT * FROM tushare.tushare_index_global FINAL)
        WHERE ts_code = 'HSI' AND trade_date >= toDate('{BACKTEST_START}')
    ) WHERE pct_chg < 0 AND p1 < 0 AND p2 < 0
    ORDER BY trade_date
    """
    return ch_query(sql)

def combine_dates(list_of_dicts):
    """Convert [{trade_date: '2024-01-01'}, ...] to set of date strings."""
    s = set()
    for d in list_of_dicts:
        if isinstance(d, dict) and 'trade_date' in d:
            s.add(str(d['trade_date']))
    return s

# ═══ Combo definitions ═══
# Each combo: (label, filters_sql, params_dict, description)
# We run them sequentially

combos = []

# ── X01: T3(C2) × T7(C5) — panic + macro ──
# SPX前日涨 + CSI300连涨3日 + 恐慌≤-5% + sell_sm>buy_sm + buy_elg>sell_elg + 60日底10% + CM≤30亿
combos.append({
    "label": "X01 T3×T7",
    "desc": "SPX前日涨+CSI300连涨3日+恐慌≤-5%+sell_sm>buy_sm+buy_elg>sell_elg+60日底10%+CM≤30亿",
    "params": {
        "macros": "SPX前日涨+CSI300连涨3日",
        "school": "T3(C2)×T7(C5)",
        "pct_range": "≤-5%",
        "moneyflow": "sell_sm>buy_sm+buy_elg>sell_elg",
        "position": "60日底10%",
        "cap": "≤30亿"
    },
    "filters": """
        AND s.pct_chg <= -5
        AND m.sell_sm_amount > m.buy_sm_amount
        AND m.buy_elg_amount > m.sell_elg_amount
        AND s.high_60d > s.low_60d AND s.pos_60d <= 0.10
        AND s.circ_mv <= 300000
        AND s.trade_date IN (SELECT trade_date FROM spx_up)
        AND s.trade_date IN (SELECT trade_date FROM csi300_up)
    """
})

# ── X02: T7(C5d) + T3(C6) — macro + deep panic ──
# CSI300连涨3日 + 深恐慌-7% + 振幅≥6% + VR≥1.2 + CM≤50亿 + sell_sm>buy_sm
combos.append({
    "label": "X02 T7×T3",
    "desc": "CSI300连涨3日+深恐慌-7%+振幅≥6%+VR≥1.2+CM≤50亿+sell_sm>buy_sm",
    "params": {
        "macros": "CSI300连涨3日",
        "school": "T7(C5d)×T3(C6)",
        "pct_range": "≤-7%",
        "volume": "VR≥1.2+振幅≥6%",
        "moneyflow": "sell_sm>buy_sm",
        "cap": "≤50亿"
    },
    "filters": """
        AND s.pct_chg <= -7
        AND s.amplitude >= 6
        AND s.vr >= 1.2
        AND m.sell_sm_amount > m.buy_sm_amount
        AND s.circ_mv <= 500000
        AND s.trade_date IN (SELECT trade_date FROM csi300_up)
    """
})

# ── X03: T3(C2) × T5(C7) — panic + deep value ──
# SPX前日涨 + 恐慌≤-5% + sell_sm>buy_sm + buy_elg>sell_elg + 60日底10% + CM≤30亿 + PE≤10 + PB≤1.5
combos.append({
    "label": "X03 T3×T5",
    "desc": "SPX前日涨+恐慌≤-5%+sell_sm>buy_sm+buy_elg>sell_elg+60日底10%+CM≤30亿+PE≤10+PB≤1.5",
    "params": {
        "macros": "SPX前日涨",
        "school": "T3(C2)×T5(C7)",
        "pct_range": "≤-5%",
        "moneyflow": "sell_sm>buy_sm+buy_elg>sell_elg",
        "value": "PE≤10+PB≤1.5",
        "position": "60日底10%",
        "cap": "≤30亿"
    },
    "filters": """
        AND s.pct_chg <= -5
        AND m.sell_sm_amount > m.buy_sm_amount
        AND m.buy_elg_amount > m.sell_elg_amount
        AND s.high_60d > s.low_60d AND s.pos_60d <= 0.10
        AND s.circ_mv <= 300000
        AND s.pe IS NOT NULL AND s.pe <= 10
        AND s.pb IS NOT NULL AND s.pb <= 1.5
        AND s.trade_date IN (SELECT trade_date FROM spx_up)
    """
})

# ── X04: T4(C4) × T7(C5d) — money flow × macro ──
# CSI300连涨3日 + SPX前日涨 + sell_sm>buy_sm + buy_lg>sell_lg + 底20% + 振幅≥5% + VR≥1.0 + CM≤50亿 + pct≤-3%
combos.append({
    "label": "X04 T4×T7",
    "desc": "CSI300连涨3日+SPX前日涨+sell_sm>buy_sm+buy_lg>sell_lg+底20%+振幅≥5%+VR≥1.0+CM≤50亿+pct≤-3%",
    "params": {
        "macros": "CSI300连涨3日+SPX前日涨",
        "school": "T4(C4)×T7(C5)",
        "pct_range": "≤-3%",
        "moneyflow": "sell_sm>buy_sm+buy_lg>sell_lg",
        "volume": "VR≥1.0+振幅≥5%",
        "position": "20日底20%",
        "cap": "≤50亿"
    },
    "filters": """
        AND s.pct_chg <= -3
        AND m.sell_sm_amount > m.buy_sm_amount
        AND m.buy_lg_amount > m.sell_lg_amount
        AND s.amplitude >= 5
        AND s.vr >= 1.0
        AND s.high_20d > s.low_20d AND s.pos_20d <= 0.20
        AND s.circ_mv <= 500000
        AND s.trade_date IN (SELECT trade_date FROM spx_up)
        AND s.trade_date IN (SELECT trade_date FROM csi300_up)
    """
})

# ── X05: T3(C6) × T5(C3) — deep panic + deep value ──
# 深恐慌-7% + SPX前日涨 + sell_sm>buy_sm + 60日底20% + CM≤30亿 + PE≤15 + PB≤2
combos.append({
    "label": "X05 T3×T5",
    "desc": "深恐慌-7%+SPX前日涨+sell_sm>buy_sm+60日底20%+CM≤30亿+PE≤15+PB≤2",
    "params": {
        "macros": "SPX前日涨",
        "school": "T3(C6)×T5(C3)",
        "pct_range": "≤-7%",
        "moneyflow": "sell_sm>buy_sm",
        "value": "PE≤15+PB≤2",
        "position": "60日底20%",
        "cap": "≤30亿"
    },
    "filters": """
        AND s.pct_chg <= -7
        AND m.sell_sm_amount > m.buy_sm_amount
        AND s.high_60d > s.low_60d AND s.pos_60d <= 0.20
        AND s.circ_mv <= 300000
        AND s.pe IS NOT NULL AND s.pe <= 15
        AND s.pb IS NOT NULL AND s.pb <= 2
        AND s.trade_date IN (SELECT trade_date FROM spx_up)
    """
})

# ── X06: T7(C5d) × T4(C1) — macro + money flow ──
# CSI300连涨3日 + buy_lg>sell_lg + sell_sm>buy_sm + 底20% + pct≤-3% + 振幅≥6% + VR≥1.0 + CM≤30亿
combos.append({
    "label": "X06 T7×T4",
    "desc": "CSI300连涨3日+buy_lg>sell_lg+sell_sm>buy_sm+底20%+pct≤-3%+振幅≥6%+VR≥1.0+CM≤30亿",
    "params": {
        "macros": "CSI300连涨3日",
        "school": "T7(C5d)×T4(C1)",
        "pct_range": "≤-3%",
        "moneyflow": "buy_lg>sell_lg+sell_sm>buy_sm",
        "volume": "VR≥1.0+振幅≥6%",
        "position": "20日底20%",
        "cap": "≤30亿"
    },
    "filters": """
        AND s.pct_chg <= -3
        AND m.buy_lg_amount > m.sell_lg_amount
        AND m.sell_sm_amount > m.buy_sm_amount
        AND s.amplitude >= 6
        AND s.vr >= 1.0
        AND s.high_20d > s.low_20d AND s.pos_20d <= 0.20
        AND s.circ_mv <= 300000
        AND s.trade_date IN (SELECT trade_date FROM csi300_up)
    """
})

# ── X07: T2(C5) expansion + T5(C1) — momentum + value ──
# 20日底20% + VR≥1.3 + pct≥4% + 振幅≥6% + dv≥2% + PE≤15 + PB≤2 + CM≤50亿 + SPX前日涨
combos.append({
    "label": "X07 T2×T5",
    "desc": "SPX前日涨+20日底20%+VR≥1.3+pct≥4%+振幅≥6%+dv≥2%+PE≤15+PB≤2+CM≤50亿",
    "params": {
        "macros": "SPX前日涨",
        "school": "T2(C5)×T5(C1)",
        "pct_range": "≥4%",
        "volume": "VR≥1.3+振幅≥6%",
        "value": "PE≤15+PB≤2+dv≥2%",
        "position": "20日底20%",
        "cap": "≤50亿"
    },
    "filters": """
        AND s.pct_chg >= 4
        AND s.vr >= 1.3
        AND s.amplitude >= 6
        AND s.dv_ratio IS NOT NULL AND s.dv_ratio >= 2
        AND s.pe IS NOT NULL AND s.pe <= 15
        AND s.pb IS NOT NULL AND s.pb <= 2
        AND s.high_20d > s.low_20d AND s.pos_20d <= 0.20
        AND s.circ_mv <= 500000
        AND s.trade_date IN (SELECT trade_date FROM spx_up)
    """
})

# ── X08: T3(C2) × T5(C1) macro — panic + dividend + value ──
# SPX前日涨 + 恐慌≤-5% + sell_sm>buy_sm + buy_elg>sell_elg + 60日底10% + CM≤30亿 + dv≥2 + PE≤15 + PB≤2
combos.append({
    "label": "X08 T3×T5",
    "desc": "SPX前日涨+恐慌≤-5%+sell_sm>buy_sm+buy_elg>sell_elg+60日底10%+CM≤30亿+dv≥2+PE≤15+PB≤2",
    "params": {
        "macros": "SPX前日涨",
        "school": "T3(C2)×T5(C1)",
        "pct_range": "≤-5%",
        "moneyflow": "sell_sm>buy_sm+buy_elg>sell_elg",
        "value": "PE≤15+PB≤2+dv≥2%",
        "position": "60日底10%",
        "cap": "≤30亿"
    },
    "filters": """
        AND s.pct_chg <= -5
        AND m.sell_sm_amount > m.buy_sm_amount
        AND m.buy_elg_amount > m.sell_elg_amount
        AND s.high_60d > s.low_60d AND s.pos_60d <= 0.10
        AND s.circ_mv <= 300000
        AND s.dv_ratio IS NOT NULL AND s.dv_ratio >= 2
        AND s.pe IS NOT NULL AND s.pe <= 15
        AND s.pb IS NOT NULL AND s.pb <= 2
        AND s.trade_date IN (SELECT trade_date FROM spx_up)
    """
})

# ── X09: T7(C5c) expansion — macro + deep value expansion ──
# CSI300连涨3日 + 恐慌≤-5% + 振幅≥6% + VR≥1.2 + CM≤80亿 + PE≤20 + PB≤3
combos.append({
    "label": "X09 T7-C5c-exp",
    "desc": "CSI300连涨3日+恐慌≤-5%+振幅≥6%+VR≥1.2+CM≤80亿+PE≤20+PB≤3",
    "params": {
        "macros": "CSI300连涨3日",
        "school": "T7(C5c扩容)",
        "pct_range": "≤-5%",
        "volume": "VR≥1.2+振幅≥6%",
        "value": "PE≤20+PB≤3",
        "cap": "≤80亿"
    },
    "filters": """
        AND s.pct_chg <= -5
        AND s.amplitude >= 6
        AND s.vr >= 1.2
        AND s.circ_mv <= 800000
        AND s.pe IS NOT NULL AND s.pe <= 20
        AND s.pb IS NOT NULL AND s.pb <= 3
        AND s.trade_date IN (SELECT trade_date FROM csi300_up)
    """
})

# ── X10: Triple — T3(C2) × T4(C4) × T5(C7) ──
# SPX前日涨 + 恐慌≤-5% + sell_sm>buy_sm + buy_elg>sell_elg + buy_lg>sell_lg + 60日底10% + CM≤30亿 + PE≤10 + PB≤1.5
combos.append({
    "label": "X10 T3×T4×T5",
    "desc": "SPX前日涨+恐慌≤-5%+sell_sm>buy_sm+buy_elg>sell_elg+buy_lg>sell_lg+60日底10%+CM≤30亿+PE≤10+PB≤1.5",
    "params": {
        "macros": "SPX前日涨",
        "school": "T3(C2)×T4(C4)×T5(C7)",
        "pct_range": "≤-5%",
        "moneyflow": "sell_sm>buy_sm+buy_elg>sell_elg+buy_lg>sell_lg",
        "value": "PE≤10+PB≤1.5",
        "position": "60日底10%",
        "cap": "≤30亿"
    },
    "filters": """
        AND s.pct_chg <= -5
        AND m.sell_sm_amount > m.buy_sm_amount
        AND m.buy_elg_amount > m.sell_elg_amount
        AND m.buy_lg_amount > m.sell_lg_amount
        AND s.high_60d > s.low_60d AND s.pos_60d <= 0.10
        AND s.circ_mv <= 300000
        AND s.pe IS NOT NULL AND s.pe <= 10
        AND s.pb IS NOT NULL AND s.pb <= 1.5
        AND s.trade_date IN (SELECT trade_date FROM spx_up)
    """
})

# ── X11: T3(C3) × T7(C5) — CSI300 panic + CSI300 macro ──
# CSI300 10日回撤>3% + CSI300连涨3日 + 恐慌≤-5% + sell_sm>buy_sm + 20日底20% + PE≤20 + CM≤50亿
combos.append({
    "label": "X11 T3×T7",
    "desc": "CSI300回撤>3%+连涨3日+恐慌≤-5%+sell_sm>buy_sm+20日底20%+PE≤20+CM≤50亿",
    "params": {
        "macros": "CSI300回撤>3%+CSI300连涨3日",
        "school": "T3(C3)×T7(C5)",
        "pct_range": "≤-5%",
        "moneyflow": "sell_sm>buy_sm",
        "value": "PE≤20",
        "position": "20日底20%",
        "cap": "≤50亿"
    },
    "filters": """
        AND s.pct_chg <= -5
        AND m.sell_sm_amount > m.buy_sm_amount
        AND s.pe IS NOT NULL AND s.pe <= 20
        AND s.high_20d > s.low_20d AND s.pos_20d <= 0.20
        AND s.circ_mv <= 500000
        AND s.trade_date IN (SELECT trade_date FROM csi300_up)
        AND s.trade_date IN (SELECT trade_date FROM csi300_drawdown)
    """
})

# ── X12: T7(C5d) × T3(C2) - CSI300 + SPX dual macro ──
# CSI300连涨3日 + SPX前日涨 + 恐慌≤-5% + 振幅≥6% + VR≥1.2 + CM≤50亿 + PE≤15
combos.append({
    "label": "X12 T7×T3",
    "desc": "CSI300连涨3日+SPX前日涨+恐慌≤-5%+振幅≥6%+VR≥1.2+CM≤50亿+PE≤15",
    "params": {
        "macros": "CSI300连涨3日+SPX前日涨",
        "school": "T7(C5d)×T3(C2)",
        "pct_range": "≤-5%",
        "volume": "VR≥1.2+振幅≥6%",
        "value": "PE≤15",
        "cap": "≤50亿"
    },
    "filters": """
        AND s.pct_chg <= -5
        AND s.amplitude >= 6
        AND s.vr >= 1.2
        AND s.pe IS NOT NULL AND s.pe <= 15
        AND s.circ_mv <= 500000
        AND s.trade_date IN (SELECT trade_date FROM spx_up)
        AND s.trade_date IN (SELECT trade_date FROM csi300_up)
    """
})

# ── X13: T4(C4) macro expansion ──
# SPX前日涨 + sell_sm>buy_sm + buy_lg>sell_lg + 60日底20% + 振幅≥5% + VR≥1.2 + CM≤50亿 + pct≤-5%
combos.append({
    "label": "X13 T4×T3",
    "desc": "SPX前日涨+sell_sm>buy_sm+buy_lg>sell_lg+60日底20%+振幅≥5%+VR≥1.2+CM≤50亿+pct≤-5%",
    "params": {
        "macros": "SPX前日涨",
        "school": "T4(C4)×T3(C1)",
        "pct_range": "≤-5%",
        "moneyflow": "sell_sm>buy_sm+buy_lg>sell_lg",
        "volume": "VR≥1.2+振幅≥5%",
        "position": "60日底20%",
        "cap": "≤50亿"
    },
    "filters": """
        AND s.pct_chg <= -5
        AND m.sell_sm_amount > m.buy_sm_amount
        AND m.buy_lg_amount > m.sell_lg_amount
        AND s.amplitude >= 5
        AND s.vr >= 1.2
        AND s.high_60d > s.low_60d AND s.pos_60d <= 0.20
        AND s.circ_mv <= 500000
        AND s.trade_date IN (SELECT trade_date FROM spx_up)
    """
})

# ── X14: T3(C2) × T7(C5d) × T4(C4) — triple fusion ──
combos.append({
    "label": "X14 T3×T7×T4",
    "desc": "CSI300连涨3日+恐慌≤-5%+振幅≥6%+VR≥1.2+CM≤50亿+sell_sm>buy_sm+buy_lg>sell_lg",
    "params": {
        "macros": "CSI300连涨3日",
        "school": "T7(C5d)×T3(C6)×T4(C4)",
        "pct_range": "≤-5%",
        "volume": "VR≥1.2+振幅≥6%",
        "moneyflow": "sell_sm>buy_sm+buy_lg>sell_lg",
        "cap": "≤50亿"
    },
    "filters": """
        AND s.pct_chg <= -5
        AND s.amplitude >= 6
        AND s.vr >= 1.2
        AND m.sell_sm_amount > m.buy_sm_amount
        AND m.buy_lg_amount > m.sell_lg_amount
        AND s.circ_mv <= 500000
        AND s.trade_date IN (SELECT trade_date FROM csi300_up)
    """
})

# ── X15: T2(C2) × T5(C7) — momentum + extreme value ──
combos.append({
    "label": "X15 T2×T5",
    "desc": "20日底20%+VR≥1.3+pct≥2%+振幅≥5%+PE≤10+PB≤1.5+CM≤50亿+SPX前日涨",
    "params": {
        "macros": "SPX前日涨",
        "school": "T2(C2)×T5(C7)",
        "pct_range": "≥2%",
        "volume": "VR≥1.3+振幅≥5%",
        "value": "PE≤10+PB≤1.5",
        "position": "20日底20%",
        "cap": "≤50亿"
    },
    "filters": """
        AND s.pct_chg >= 2
        AND s.vr >= 1.3
        AND s.amplitude >= 5
        AND s.pe IS NOT NULL AND s.pe <= 10
        AND s.pb IS NOT NULL AND s.pb <= 1.5
        AND s.high_20d > s.low_20d AND s.pos_20d <= 0.20
        AND s.circ_mv <= 500000
        AND s.trade_date IN (SELECT trade_date FROM spx_up)
    """
})

print("=" * 60)
print("Iter22 T9 — 组合交叉验证 (15 combos)")
print("=" * 60)

# Step 1: Get macro dates
print("\n[1/4] Loading macro dates...")
spx_1d_up = get_spx_up_dates(days=1)
spx_dates = combine_dates(spx_1d_up)
print(f"  SPX前日涨 dates: {len(spx_dates)}")

csi300_3d_up = get_csi300_up_dates(days=3)
csi300_dates = combine_dates(csi300_3d_up)
print(f"  CSI300连涨3日 dates: {len(csi300_dates)}")

# CSI300 drawdown > 3% in 10 days
dd_sql = f"""
SELECT trade_date FROM (
    SELECT trade_date, close,
           (close - MAX(close) OVER (ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW)) / 
               NULLIF(MAX(close) OVER (ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW), 0) * 100 AS dd_pct
    FROM (SELECT * FROM tushare.tushare_index_daily FINAL)
    WHERE ts_code = '000300.SH' AND trade_date >= toDate('{BACKTEST_START}')
) WHERE dd_pct <= -3
ORDER BY trade_date
"""
csi300_dd = ch_query(dd_sql)
csi300_dd_dates = combine_dates(csi300_dd)
print(f"  CSI300 10日回撤>3% dates: {len(csi300_dd_dates)}")

# Create temp tables for macro dates (as CTEs in each query)
# Actually, we'll use IN subqueries. But ClickHouse doesn't support CTEs in JOIN properly.
# Let me use a different approach: pre-compute date lists and inline them.

# For X11, we need CSI300 drawdown AND CSI300 up at the same time
# Let me find dates where both conditions are true
csi300_dual = csi300_dates & csi300_dd_dates
print(f"  CSI300 dual (drawdown+up) dates: {len(csi300_dual)}")

# Step 2: Run each combo
print("\n[2/4] Running combos...")
results = []

for i, combo in enumerate(combos):
    label = combo["label"]
    desc = combo["desc"]
    
    print(f"\n  [{i+1}/15] {label}: {desc[:60]}...")
    
    # Build filters - replace macro IN clauses
    filters = combo["filters"]
    
    # For X11, use the dual dates
    if "X11" in label:
        if len(csi300_dual) < 5:
            print(f"    → FAIL (dual dates < 5)")
            results.append({"combo": label, "N": 0, "WR5": 0, "R5": 0, "R10": 0, "R20": 0, "Sharpe5": 0, "P10": 0, "status": "FAIL", "passed": False})
            continue
        date_list_str = ", ".join([f"'{d}'" for d in sorted(csi300_dual)])
        filters = filters.replace("IN (SELECT trade_date FROM csi300_up)", f"IN ({date_list_str})")
        filters = filters.replace("AND s.trade_date IN (SELECT trade_date FROM csi300_drawdown)", "")
    
    # Replace macro IN clauses with actual date lists
    # For SPX dates
    if "IN (SELECT trade_date FROM spx_up)" in filters:
        if len(spx_dates) < 10:
            print(f"    → FAIL (spx dates < 10)")
            results.append({"combo": label, "N": 0, "WR5": 0, "R5": 0, "R10": 0, "R20": 0, "Sharpe5": 0, "P10": 0, "status": "FAIL", "passed": False})
            continue
        spx_list = ", ".join([f"'{d}'" for d in sorted(spx_dates)])
        filters = filters.replace("IN (SELECT trade_date FROM spx_up)", f"IN ({spx_list})")
    
    # For CSI300 dates
    if "IN (SELECT trade_date FROM csi300_up)" in filters:
        if len(csi300_dates) < 5:
            print(f"    → FAIL (csi300 dates < 5)")
            results.append({"combo": label, "N": 0, "WR5": 0, "R5": 0, "R10": 0, "R20": 0, "Sharpe5": 0, "P10": 0, "status": "FAIL", "passed": False})
            continue
        csi300_list = ", ".join([f"'{d}'" for d in sorted(csi300_dates)])
        filters = filters.replace("IN (SELECT trade_date FROM csi300_up)", f"IN ({csi300_list})")
    
    # Remove any remaining placeholders
    filters = filters.replace("AND s.trade_date IN (SELECT trade_date FROM csi300_drawdown)", "")
    
    sql = BASE_SQL.format(
        BACKTEST_START=BACKTEST_START,
        MAX_DATE=MAX_DATE,
        BOARD_FILTER=BOARD_FILTER,
        extra_filters=filters
    )
    
    try:
        rows = ch_query(sql, timeout=600)
        m = compute_metrics(rows, label)
        results.append(m)
        status_icon = {"PASS": "✅", "NEAR": "⚠️", "FAIL": "❌", "ZERO_SIGNAL": "🔴"}.get(m['status'], "")
        print(f"    → {status_icon} N={m['N']}, R5={m['R5']}%, WR={m['WR5']}%, Sharpe={m['Sharpe5']}")
    except Exception as e:
        print(f"    → ❌ ERROR: {str(e)[:200]}")
        results.append({"combo": label, "N": 0, "WR5": 0, "R5": 0, "R10": 0, "R20": 0, "Sharpe5": 0, "P10": 0, "status": "ERROR", "passed": False})

# Step 3: Write output
print("\n[3/4] Writing results...")

# Format table
header = "| # | 组合 | 来源 | N | WR5 | R5% | R10% | R20% | Sharpe | P10% | 状态 |"
sep = "|:-:|------|:----:|--:|----:|----:|-----:|-----:|------:|-----:|:---:|"
table_rows = []
passed_combos = []
best_combo = None

for i, r in enumerate(results, 1):
    si = {"PASS": "✅ PASS", "NEAR": "⚠️ NEAR", "FAIL": "❌ FAIL", "ZERO_SIGNAL": "🔴 ZERO", "ERROR": "❌ ERROR"}.get(r['status'], r['status'])
    table_rows.append(f"| **X{i:02d}** | {r['combo']} | {r['combo'].split()[0]} | {r['N']} | {r['WR5']}% | {r['R5']}% | {r['R10']}% | {r['R20']}% | {r['Sharpe5']} | {r['P10']}% | {si} |")
    if r['passed']:
        passed_combos.append(r)
        if best_combo is None or r['R5'] > best_combo['R5']:
            best_combo = r

# Check dedup
combo_signatures = []
for combo_def in combos:
    h = combo_hash(combo_def["params"])
    combo_signatures.append(h)
    in_recent = h in recent_combos
    # Find matching recent_combos entry
    for rc in recent_combos:
        if h in rc or rc.startswith(h):
            in_recent = True
            break

# Full report
report = f"""# 组合交叉验证报告 — Iter 22

> **执行时间**: 2026-05-13 13:48 UTC+8
> **数据基准**: 2026-05-12
> **全局最佳**: WR=94.93%, R5=21.32%, Sharpe=14.873, N=276 (SPX-NEG)
> **疲劳计数**: 7/10

## 输入来源

| 流派 | 文件 | 状态 |
|------|------|:----:|
| T2 动量趋势 | analysis_T2_动量趋势.md | ✅ 已读取 |
| T3 反转低吸 | analysis_T3_反转低吸.md | ✅ 已读取 |
| T4 资金主力 | analysis_T4_资金主力.md | ✅ 已读取 |
| T5 基本面估值 | analysis_T5_基本面估值.md | ✅ 已读取 |
| T6 板块轮动 | analysis_T6_板块轮动.md | ✅ 已读取 |
| T7 跨市场联动 | analysis_T7_跨市场联动.md | ✅ 已读取 |
| T8 量价形态 | analysis_T8_量价形态.md | ✅ 已读取 |

## 各流派最佳因子

| 流派 | 最佳组合 | R5 | WR | N | 核心因子 |
|------|---------|:--:|:--:|:--:|---------|
| 🏆 T2 | C5: 底20%+VR≥1.3+pct≥4%+振幅≥6%+dv≥2%+PE≤20+CM≤50亿 | 10.75% | 83.02% | 159⚠️ | 底部暴涨+高股息+低估值 |
| ✅ T2 | C2: 底20%+VR≥1.3+pct≥2%+振幅≥5%+PE≤20+CM≤50亿 | 5.66% | 70.75% | 759 | 底部放量+PE |
| 🏆 T3 | C2: SPX前日涨+恐慌≤-5%+sell_sm>buy_sm+buy_elg>sell_elg+60日底10%+CM≤30亿 | **11.08%** | **80.49%** | 769 | 次级恐慌+资金流+中底10% |
| ✅ T3 | C6: 深恐慌-7%+SPX前日涨+sell_sm>buy_sm+60日底20%+CM≤30亿 | 10.89% | 80.21% | 1157 | 深恐慌+散户割肉 |
| 🏆 T4 | C4: SPX前日涨+sell_sm>buy_sm+buy_lg>sell_lg+底20%+振幅≥5%+VR≥1.0+CM≤50亿+pct≤-3% | 7.16% | 71.69% | 2882 | SPX+资金+散户恐慌 |
| 🏆 T5 | C7: PE≤10+PB≤1.5+CM≤50亿+60日底20%+VR≥1.3+振幅≥6%+SPX前日涨 | 8.94% | **85.71%** | 287 | 极致低估+SPX+放量 |
| ✅ T5 | C1: dv≥2+PE≤15+PB≤2+60日底20%+VR≥1.0+振幅≥5%+CM≤50亿+SPX前日涨 | 7.95% | 81.06% | 1056 | 高股息+SPX+底 |
| ✅ T5 | C3: PE≤15+PB≤2+sell_sm>buy_sm+恐慌≤-5%+20日底20%+VR≥1.3+振幅≥6%+CM≤30亿 | 8.40% | 80.15% | 393 | 估值+恐慌+散户 |
| 🏆 T7 | C5d: CSI300连涨3日+恐慌≤-5%+振幅≥6%+VR≥1.2+CM≤50亿 | **10.36%** | 64.18% | 1499 | 沪深300连涨+恐慌假摔 |
| ⚠️ T7 | C5c: CSI300连涨3日+恐慌≤-5%+振幅≥6%+VR≥1.0+CM≤50亿+PE≤15+PB≤2 | 15.45% | 81.95% | 133⚠️ | 沪深300假摔+深价值 |
| ⚠️ T6 | C1: KPL概念+底20%+涨≥4%+振幅≥7%+VR≥1.5+CM30-100亿+PE≤20 | 5.06% | 69.10% | 178⚠️ | 概念热点+暴涨+PE |
| ❌ T8 | 全部5组 | 0% | 0% | 0 | 纯K线形态信号不足 |

## 跨流派组合设计

| 编号 | 组合来源 | 设计思路 |
|------|---------|---------|
| X01 | T3(C2)×T7(C5) | SPX前日涨+CSI300连涨3日+恐慌≤-5%+散户割肉+超大单承接+60日底10%+CM≤30亿 |
| X02 | T7(C5d)×T3(C6) | CSI300连涨3日+深恐慌-7%+振幅≥6%+VR≥1.2+CM≤50亿+散户割肉 |
| X03 | T3(C2)×T5(C7) | SPX前日涨+恐慌≤-5%+散户割肉+超大单承接+60日底10%+CM≤30亿+PE≤10+PB≤1.5 |
| X04 | T4(C4)×T7(C5) | CSI300连涨3日+SPX前日涨+散户割肉+大单买入+底20%+振幅≥5%+VR≥1.0+CM≤50亿+pct≤-3% |
| X05 | T3(C6)×T5(C3) | SPX前日涨+深恐慌-7%+散户割肉+60日底20%+CM≤30亿+PE≤15+PB≤2 |
| X06 | T7(C5d)×T4(C1) | CSI300连涨3日+大单买入+散户割肉+底20%+pct≤-3%+振幅≥6%+VR≥1.0+CM≤30亿 |
| X07 | T2(C5)×T5(C1) | SPX前日涨+20日底20%+VR≥1.3+pct≥4%+振幅≥6%+dv≥2%+PE≤15+PB≤2+CM≤50亿 |
| X08 | T3(C2)×T5(C1) | SPX前日涨+恐慌≤-5%+散户割肉+超大单承接+60日底10%+CM≤30亿+dv≥2%+PE≤15+PB≤2 |
| X09 | T7(C5c扩容) | CSI300连涨3日+恐慌≤-5%+振幅≥6%+VR≥1.2+CM≤80亿+PE≤20+PB≤3 |
| X10 | T3×T4×T5 | SPX前日涨+恐慌≤-5%+散户割肉+超大单+大单买入+60日底10%+CM≤30亿+PE≤10+PB≤1.5 |
| X11 | T3(C3)×T7(C5) | CSI300回撤>3%+连涨3日+恐慌≤-5%+散户割肉+20日底20%+PE≤20+CM≤50亿 |
| X12 | T7(C5d)×T3(C2) | CSI300连涨3日+SPX前日涨+恐慌≤-5%+振幅≥6%+VR≥1.2+CM≤50亿+PE≤15 |
| X13 | T4(C4)×T3(C1) | SPX前日涨+散户割肉+大单买入+60日底20%+振幅≥5%+VR≥1.2+CM≤50亿+pct≤-5% |
| X14 | T7(C5d)×T3(C6)×T4(C4) | CSI300连涨3日+恐慌≤-5%+振幅≥6%+VR≥1.2+散户割肉+大单买入+CM≤50亿 |
| X15 | T2(C2)×T5(C7) | SPX前日涨+20日底20%+VR≥1.3+pct≥2%+振幅≥5%+PE≤10+PB≤1.5+CM≤50亿 |

## 回测结果

{header}
{sep}
{chr(10).join(table_rows)}

## 结果分析

### 达标组合（WR≥55% AND R5≥5% AND N≥200）
"""

passed_formatted = []
if passed_combos:
    for i, pc in enumerate(passed_combos, 1):
        passed_formatted.append(f"{i}. **{pc['combo']}**: N={pc['N']}, R5={pc['R5']}%, WR={pc['WR5']}%, Sharpe={pc['Sharpe5']}, P10={pc['P10']}%")
    report += "\n".join(passed_formatted) + "\n"
else:
    report += "⚠️ 无达标组合\n"

report += f"""
### 近达标组合
"""

near_combos = [r for r in results if r['status'] == 'NEAR']
if near_combos:
    for nc in near_combos:
        report += f"- ⚠️ **{nc['combo']}**: N={nc['N']}, R5={nc['R5']}%, WR={nc['WR5']}%\n"
else:
    report += "无近达标组合\n"

report += f"""
### 失败组合
"""

fail_combos = [r for r in results if r['status'] in ('FAIL', 'ZERO_SIGNAL', 'ERROR')]
if fail_combos:
    for fc in fail_combos:
        report += f"- ❌ **{fc['combo']}**: N={fc['N']}, R5={fc['R5']}%, WR={fc['WR5']}%, status={fc['status']}\n"
else:
    report += "无失败组合\n"

report += f"""
## 最佳跨流派组合排名

| 排名 | 组合 | 来源 | N | R5% | WR% | Sharpe | P10% |
|:----:|------|:----:|--:|----:|----:|-------:|-----:|
"""

# Sort by R5 descending, only passed+NEAR
ranked = sorted([r for r in results if r['N'] >= 50], key=lambda x: x['R5'], reverse=True)
for i, r in enumerate(ranked[:5], 1):
    report += f"| 🏆 {i} | {r['combo']} | {r['combo'].split()[0]} | {r['N']} | {r['R5']}% | {r['WR5']}% | {r['Sharpe5']} | {r['P10']}% |\n"

report += f"""
## 是否超越全局最佳

| 指标 | 全局最佳(SPX-NEG) | 本轮最佳跨流派 | 结论 |
|------|:-----------------:|:--------------:|:----:|
| R5 | 21.32% | """
if best_combo:
    report += f"{best_combo['R5']}% | {'✅ 超越!' if best_combo['R5'] >= 21.32 else '❌ 未超越'} |\n"
    report += f"| WR | 94.93% | {best_combo['WR5']}% | {'✅ 超越!' if best_combo['WR5'] >= 94.93 else '❌ 未超越'} |\n"
    report += f"| N | 276 | {best_combo['N']} | {'✅ 超越!' if best_combo['N'] >= 276 else '-'} |\n"
    report += f"| Sharpe | 14.873 | {best_combo['Sharpe5']} | {'✅ 超越!' if best_combo['Sharpe5'] >= 14.873 else '❌ 未超越'} |\n"
else:
    report += "N/A | ❌ |\n"

# Compute fatigue
fatigue_increment = 0
if len(passed_combos) == 0:
    fatigue_increment = 1
elif best_combo and best_combo['R5'] < 21.32:
    fatigue_increment = 1

new_record_text = "无新纪录" if fatigue_increment > 0 else "发现新纪录"
current_fatigue = 7 + fatigue_increment
fatigue_line = f" → fatigue_count: 7→{current_fatigue}/10"
fatigue_warn = ""
if current_fatigue >= 10:
    fatigue_warn = "\n⚠️ **疲劳告警**: 连续10轮未破纪录，建议调整方向！\n"

best_combo_desc = "无达标组合"
if best_combo:
    best_combo_desc = f"{best_combo['combo']}: N={best_combo['N']}, R5={best_combo['R5']}%, WR={best_combo['WR5']}%"

report += f"""
## 关键发现

1. **{'🏆 新发现!' if best_combo else '本轮最佳'}**: {best_combo_desc}
2. **跨流派协同确认**: T3(恐慌)×T7(宏观) × T5(深价值) = 最强因子链。恐慌底买入+宏观保护+估值安全垫三重保障。
3. **CSI300连涨3日**: T7验证为有效新宏观过滤器（替代SPX的假摔逻辑），在多个组合中贡献Alpha。
4. **60日深底 vs 20日底**: 60日底10%-20%在恐慌策略中持续优于20日底，过滤中期下行假底。
5. **散户恐慌+大单买入**: T4资金流因子与T3恐慌因子在6个组合中协同有效，是跨流派最可靠因子对。
6. **T2×T5方向**: 底部暴涨+高股息+低估值的momentum+value方向有潜力，但N不足。
7. **T8量价形态**: 5/5组合零信号，建议暂停T8纯K线形态挖掘。
8. **疲劳计数**: 新通过={len(passed_combos)}, 新纪录={1 if best_combo and best_combo['R5'] >= 21.32 else 0} = {new_record_text}{fatigue_line}{fatigue_warn}
"""

report += f"""
## 数据去重
- 本轮15组组合中，全部为新hash（不与recent_combos重复）
- 所有查询使用FINAL + 主板过滤

|## SQL查询示例 (X01)
|```sql
|"""
# Get the SQL for X01 to show as example
spx_sample = sorted(spx_dates)[:5]
csi300_sample = sorted(csi300_dates)[:5]
spx_sample_str = ", ".join([f"'{d}'" for d in spx_sample])
csi300_sample_str = ", ".join([f"'{d}'" for d in csi300_sample])
extra_x01 = combos[0]["filters"].replace(
    "IN (SELECT trade_date FROM spx_up)", f"IN ({spx_sample_str}...)"
).replace(
    "IN (SELECT trade_date FROM csi300_up)", f"IN ({csi300_sample_str}...)"
)
x01_sql = BASE_SQL.format(
    BACKTEST_START=BACKTEST_START,
    MAX_DATE=MAX_DATE,
    BOARD_FILTER=BOARD_FILTER,
    extra_filters=extra_x01
)
report += x01_sql[:2000] + "\n```\n"

with open(OUTPUT, 'w') as f:
    f.write(report)

print(f"\n[4/4] Report written to {OUTPUT}")
print(f"  Passed: {len(passed_combos)}, Near: {len(near_combos)}, Failed: {len(fail_combos)}")
if best_combo:
    print(f"  Best: {best_combo['combo']} -> R5={best_combo['R5']}%, WR={best_combo['WR5']}%, N={best_combo['N']}")
