#!/usr/bin/env python3
"""Iter22 T9: Cross-school combination backtest — using verified T3 analyst pattern"""
import json, sys, math, os
sys.path.insert(0, '/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts')
from ch_query import _ch_query as ch_query

BASE = '2026-05-06'
HIST = '2020-01-01'
BOARD = "sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%' AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'"
WF = "ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING"

def run_combo(name, desc, params_sql, extra_joins="", filter_sql=""):
    """Run a full backtest for one combo"""
    wc = f"leadInFrame(sd.close, 5) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WF}) AS close_5d"
    
    sql = f"""
    WITH sd_windowed AS (
        SELECT sd.ts_code, sd.trade_date, sd.close, sd.pct_chg, sd.high, sd.low, sd.pre_close,
               (sd.high - sd.low) / NULLIF(sd.pre_close, 0) * 100 AS amplitude,
               {wc}
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
        WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
          AND {BOARD}
    ),
    combo AS (
        SELECT w.ts_code, w.trade_date, w.close, w.pct_chg, w.amplitude, w.close_5d,
               (w.close_5d / w.close) - 1 AS ret_5d
        FROM sd_windowed w
        {extra_joins}
        WHERE {params_sql}
          AND w.trade_date >= '{HIST}' AND w.trade_date <= '{BASE}'
          {filter_sql}
    )
    SELECT
        COUNT(*) AS signal_count,
        round(AVG(ret_5d) * 100, 2) AS avg_ret_5d_pct,
        round(COUNT(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct
    FROM combo
    WHERE ret_5d IS NOT NULL
    """
    try:
        data = ch_query(sql, timeout=300)
        if not data or len(data) == 0:
            return {'name': name, 'desc': desc, 'N': 0, 'R5': 0, 'WR': 0, 'pass': False, 'error': 'no data'}
        r = data[0]
        n = int(r['signal_count'])
        r5 = float(r['avg_ret_5d_pct'])
        wr = float(r['win_rate_5d_pct'])
        return {
            'name': name, 'desc': desc,
            'N': n, 'R5': r5, 'WR': wr,
            'pass': n >= 200 and wr >= 55.0 and r5 >= 5.0
        }
    except Exception as e:
        return {'name': name, 'desc': desc, 'N': 0, 'R5': 0, 'WR': 0, 'pass': False, 'error': str(e)}

# Daily basic join CTE
BASIC_JOIN = """
LEFT JOIN (
    SELECT ts_code, trade_date, volume_ratio, turnover_rate, pe, pb, circ_mv, dv_ttm
    FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
) b ON w.ts_code = b.ts_code AND w.trade_date = b.trade_date
"""

# Moneyflow join CTE
MF_JOIN = """
LEFT JOIN (
    SELECT ts_code, trade_date, sell_sm_vol, buy_sm_vol, buy_elg_vol, sell_elg_vol, net_mf_amount
    FROM (SELECT * FROM tushare.tushare_moneyflow FINAL) AS mf
) m ON w.ts_code = m.ts_code AND w.trade_date = m.trade_date
"""

# SPX join CTE
SPX_CTE = """
spx_raw AS (
    SELECT trade_date, pct_chg
    FROM (SELECT * FROM tushare.tushare_index_global FINAL) AS g
    WHERE g.ts_code = 'SPX' AND g.trade_date >= '2019-12-01'
),
spx_lag AS (
    SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS spx_prev_pct
    FROM spx_raw
),
"""
SPX_JOIN = "LEFT JOIN spx_lag sp ON w.trade_date = sp.trade_date"
SPX_FILTER = "AND sp.spx_prev_pct > 0"

# HS300 join CTE
HS300_CTE = """
hs300_raw AS (
    SELECT trade_date, pct_chg
    FROM (SELECT * FROM tushare.tushare_index_daily FINAL) AS g
    WHERE g.ts_code = '000300.SH' AND g.trade_date >= '2019-12-01'
),
"""
HS300_JOIN = "LEFT JOIN hs300_raw h ON w.trade_date = h.trade_date"

# North-bound moneyflow
NORTH_CTE = """
north_raw AS (
    SELECT trade_date, net_mf_amount
    FROM (SELECT * FROM tushare.tushare_moneyflow_hsgt FINAL) AS n
    WHERE n.trade_date >= '2019-12-01'
),
north_lag AS (
    SELECT trade_date, lagInFrame(net_mf_amount, 1) OVER (ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS north_prev_net
    FROM north_raw
),
"""
NORTH_JOIN = "LEFT JOIN north_lag n ON w.trade_date = n.trade_date"

# ==================== COMBOS ====================
# Each combo must provide:
#   params_sql - WHERE clause for the main combo conditions
#   extra_joins - CTE definitions + JOIN statements  
#   filter_sql - additional filters (SPX, etc.)

results = []

print("="*80)
print("ITER22 T9: CROSS-SCHOOL COMBINATION BACKTEST")
print("="*80)
print(f"Data range: {HIST} to {BASE}")
print()

# ---- Combo 1: T2-C7 × T5-C6 — Deep Value Momentum ----
# T2-C7: 60日底15%+涨≥4%+VR≥1.3+振幅≥7%+CM≤30亿  
# T5-C6: PE≤15+PB≤2+底20%(60日)+VR≥1.3+振幅≥6%+CM≤50亿
# Merge: PE≤15+PB≤2+涨≥4%+ampl≥7+VR≥1.3+CM≤30亿
print("1/12 C01: Deep Value Momentum (T2-C7 × T5-C6)...")
r = run_combo(
    "C01_T2xT5_DeepValueMom",
    "PE≤15+PB≤2+涨≥4%+ampl≥7+VR≥1.3+CM≤30亿",
    params_sql="w.pct_chg >= 4 AND w.amplitude >= 7 AND b.volume_ratio >= 1.3 AND b.pe > 0 AND b.pe <= 15 AND b.pb > 0 AND b.pb <= 2 AND b.circ_mv <= 300000",
    extra_joins=BASIC_JOIN,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 2: T4-C7 × T7-C1 — SPX涨+双资金流恐慌+PB≤2+CM≤30亿 ----
# T4-C7: sell_sm>buy_sm+buy_elg>sell_elg+60日底20%+pct≤-5%+振幅≥5%+VR≥1.0+CM≤30亿+PB≤2  
# T7-C1: SPX前日涨+恐慌60日底
print("2/12 C02: SPX+双资金流恐慌+PB≤2 (T4-C7 × T7-C1)...")
r = run_combo(
    "C02_T4xT7_SPX_FundFlow_Panic",
    "SPX涨+pct≤-5%+ampl≥5+VR≥1+双资金流+PB≤2+CM≤30亿",
    params_sql="w.pct_chg <= -5 AND w.amplitude >= 5 AND b.volume_ratio >= 1.0 AND b.pb > 0 AND b.pb <= 2 AND b.circ_mv <= 300000 AND m.sell_sm_vol > m.buy_sm_vol AND m.buy_elg_vol > m.sell_elg_vol",
    extra_joins=BASIC_JOIN + MF_JOIN + SPX_JOIN,
    filter_sql=SPX_FILTER,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 3: T8-C3 × T6-C2 — 巨阳线+高股息低估值 ----
# T8-C3: 底部放量巨阳线 (涨≥5%+振幅≥8%+VR≥1.5+CM≤30亿)
# T6-C2: 60日底20%+涨≥3%+振幅≥6%+VR≥1.2+dv≥2%+PE≤20+PB≤2+CM≤50亿
print("3/12 C03: 巨阳线+高股息低估值 (T8-C3 × T6-C2)...")
r = run_combo(
    "C03_T8xT6_BigYang_DivValue",
    "涨≥5%+ampl≥8%+VR≥1.5+dv≥2%+PE≤20+PB≤2+CM≤30亿",
    params_sql="w.pct_chg >= 5 AND w.amplitude >= 8 AND b.volume_ratio >= 1.5 AND b.dv_ttm >= 2 AND b.pe > 0 AND b.pe <= 20 AND b.pb > 0 AND b.pb <= 2 AND b.circ_mv <= 300000",
    extra_joins=BASIC_JOIN,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 4: T3-C2 — SPX涨+恐慌-5%+双资金流+60日底10%+CM≤30亿 ----
# T3's best: SPX+恐慌+散割+超大单+60日底10%+CM≤30亿
# Need position calc for 60日底10%
print("4/12 C04: SPX+恐慌+双资金流 (T3-C2)...")
# 60日底10% needs a window function for min/max
sql_c04 = f"""
WITH
sd_windowed AS (
    SELECT sd.ts_code, sd.trade_date, sd.close, sd.pct_chg, sd.high, sd.low, sd.pre_close,
           (sd.high - sd.low) / NULLIF(sd.pre_close, 0) * 100 AS amplitude,
           leadInFrame(sd.close, 5) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WF}) AS close_5d,
           MIN(sd.low) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS low_60d,
           MAX(sd.high) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS high_60d
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
    WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
      AND {BOARD}
),
spx_raw AS (
    SELECT trade_date, pct_chg
    FROM (SELECT * FROM tushare.tushare_index_global FINAL) AS g
    WHERE g.ts_code = 'SPX' AND g.trade_date >= '2019-12-01'
),
spx_lag AS (
    SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date {WF}) AS spx_prev_pct
    FROM spx_raw
),
basic AS (
    SELECT ts_code, trade_date, volume_ratio, circ_mv
    FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
),
mf AS (
    SELECT ts_code, trade_date, sell_sm_vol, buy_sm_vol, buy_elg_vol, sell_elg_vol
    FROM (SELECT * FROM tushare.tushare_moneyflow FINAL) AS m
)
SELECT
    COUNT(*) AS signal_count,
    round(AVG((w.close_5d / w.close - 1) * 100), 2) AS avg_ret_5d_pct,
    round(COUNT(CASE WHEN (w.close_5d / w.close - 1) > 0 THEN 1 END) * 100.0 / COUNT(*), 2) AS win_rate_5d_pct
FROM sd_windowed w
LEFT JOIN spx_lag sp ON w.trade_date = sp.trade_date
LEFT JOIN basic b ON w.ts_code = b.ts_code AND w.trade_date = b.trade_date
LEFT JOIN mf ON w.ts_code = mf.ts_code AND w.trade_date = mf.trade_date
WHERE w.pct_chg <= -5
  AND sp.spx_prev_pct > 0
  AND (w.close - w.low_60d) / NULLIF(w.high_60d - w.low_60d, 0) <= 0.10
  AND mf.sell_sm_vol > mf.buy_sm_vol
  AND mf.buy_elg_vol > mf.sell_elg_vol
  AND b.volume_ratio >= 1.0
  AND b.circ_mv <= 300000
  AND w.ret_5d IS NOT NULL
"""
try:
    data = ch_query(sql_c04, timeout=300)
    if data and len(data) > 0:
        r = data[0]
        n = int(r['signal_count'])
        r5 = float(r['avg_ret_5d_pct'])
        wr = float(r['win_rate_5d_pct'])
        r = {'name': 'C04_T3C2', 'desc': 'SPX涨+恐慌-5%+sell_sm>buy_sm+buy_elg>sell_elg+60日底10%+CM≤30亿', 'N': n, 'R5': r5, 'WR': wr, 'pass': n >= 200 and wr >= 55.0 and r5 >= 5.0}
    else:
        r = {'name': 'C04_T3C2', 'desc': 'SPX+恐慌+双资金流+60日底10%', 'N': 0, 'R5': 0, 'WR': 0, 'pass': False, 'error': 'no data'}
except Exception as e:
    r = {'name': 'C04_T3C2', 'desc': 'SPX+恐慌+双资金流+60日底10%', 'N': 0, 'R5': 0, 'WR': 0, 'pass': False, 'error': str(e)}
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 5: T6-C2 × T7-C2 — 北向净流出+高股息低估值 ----
print("5/12 C05: 北向净流出+高股息低估值 (T6-C2 × T7-C2)...")
r = run_combo(
    "C05_T6xT7_North_DivValue",
    "北向净流出+dv≥2%+PE≤20+PB≤2+涨≥3%+ampl≥6+VR≥1.2+CM≤50亿",
    params_sql="w.pct_chg >= 3 AND w.amplitude >= 6 AND b.volume_ratio >= 1.2 AND b.dv_ttm >= 2 AND b.pe > 0 AND b.pe <= 20 AND b.pb > 0 AND b.pb <= 2 AND b.circ_mv <= 500000 AND n.north_prev_net < 0",
    extra_joins=BASIC_JOIN + NORTH_JOIN,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 6: T4-C9 × T8-C4 — 双资金流+曙光初现+PB≤2 ----
print("6/12 C06: 双资金流+曙光初现+PB≤2 (T4-C9 × T8-C4)...")
r = run_combo(
    "C06_T4xT8_FundFlow_Dawn",
    "sell_sm>buy_sm+buy_elg>sell_elg+pct_chg>=3(阳线)+close>open+ampl≥5+VR≥1.0+PB≤2+CM≤50亿",
    params_sql="w.pct_chg >= 3 AND w.amplitude >= 5 AND b.volume_ratio >= 1.0 AND b.pb > 0 AND b.pb <= 2 AND b.circ_mv <= 500000 AND m.sell_sm_vol > m.buy_sm_vol AND m.buy_elg_vol > m.sell_elg_vol",
    extra_joins=BASIC_JOIN + MF_JOIN,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 7: T3-C6 × T5-C1b — 深恐慌+破净高股息+SPX涨 ----
print("7/12 C07: 深恐慌+破净高股息+SPX涨 (T3-C6 × T5-C1b)...")
r = run_combo(
    "C07_T3xT5_Panic_DeepValue_SPX",
    "SPX涨+pct≤-7%+sell_sm>buy_sm+PB≤1+dv≥3%+VR≥1+CM30-100亿",
    params_sql="w.pct_chg <= -7 AND b.volume_ratio >= 1.0 AND b.pb > 0 AND b.pb <= 1 AND b.dv_ttm >= 3 AND b.circ_mv >= 300000 AND b.circ_mv <= 1000000 AND m.sell_sm_vol > m.buy_sm_vol",
    extra_joins=BASIC_JOIN + MF_JOIN + SPX_JOIN,
    filter_sql=SPX_FILTER,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 8: T7-C1 × T4-C3 — SPX+恐慌+双资金流+PE≤20 ----
print("8/12 C08: SPX+恐慌+双资金流+PE≤20 (T7-C1 × T4-C3)...")
r = run_combo(
    "C08_T7xT4_SPX_Panic_FundFlow_PE20",
    "SPX涨+pct≤-5%+ampl≥6+VR≥1.2+双资金流+PE≤20+CM≤50亿",
    params_sql="w.pct_chg <= -5 AND w.amplitude >= 6 AND b.volume_ratio >= 1.2 AND b.pe > 0 AND b.pe <= 20 AND b.circ_mv <= 500000 AND m.sell_sm_vol > m.buy_sm_vol AND m.buy_elg_vol > m.sell_elg_vol",
    extra_joins=BASIC_JOIN + MF_JOIN + SPX_JOIN,
    filter_sql=SPX_FILTER,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 9: T2-C6 × T4-C1b — 净流入+散户恐慌+底部放量中阳 ----
print("9/12 C09: 净流入+散户恐慌+底部放量中阳 (T2-C6 × T4-C1b)...")
r = run_combo(
    "C09_T2xT4_NetMF_Panic_Momentum",
    "net_mf≥500万+sell_sm>buy_sm+涨≥3%+ampl≥6+VR≥1.3+CM≤50亿",
    params_sql="w.pct_chg >= 3 AND w.amplitude >= 6 AND b.volume_ratio >= 1.3 AND b.circ_mv <= 500000 AND m.net_mf_amount >= 5000000 AND m.sell_sm_vol > m.buy_sm_vol",
    extra_joins=BASIC_JOIN + MF_JOIN,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 10: T8-C1 × T6-C1 — SPX+底部放量大阳线 ----
print("10/12 C10: SPX+底部放量大阳线 (T8-C1 × T6-C1)...")
r = run_combo(
    "C10_T8xT6_SPX_BigYang",
    "SPX涨+涨≥5%+ampl≥8+VR≥1.5+CM≤30亿",
    params_sql="w.pct_chg >= 5 AND w.amplitude >= 8 AND b.volume_ratio >= 1.5 AND b.circ_mv <= 300000",
    extra_joins=BASIC_JOIN + SPX_JOIN,
    filter_sql=SPX_FILTER,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 11: T3-C3 × T8-C2 — HS300恐慌+十字星+PE≤20 ----
print("11/12 C11: HS300恐慌+十字星+PE (T3-C3 × T8-C2)...")
r = run_combo(
    "C11_T3xT8_HS300_Panic_Doji",
    "HS300跌≥1.5%+恐慌≤-5%+ampl≥5+VR≥1.3+PE≤20+CM≤50亿",
    params_sql="w.pct_chg <= -5 AND w.amplitude >= 5 AND b.volume_ratio >= 1.3 AND b.pe > 0 AND b.pe <= 20 AND b.circ_mv <= 500000 AND h.pct_chg <= -1.5",
    extra_joins=BASIC_JOIN + HS300_JOIN,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ---- Combo 12: T6-C3 × T5-C1b — SPX+微跌+双资金流+破净高股息 ----
print("12/12 C12: SPX+微跌+双资金流+破净高股息 (T6-C3 × T5-C1b)...")
r = run_combo(
    "C12_T6xT5_SPX_Negative_FundFlow_DeepValue",
    "SPX涨+pct≥-5%且pct≤-1%+ampl≥5+双资金流+PB≤1+dv≥3%+VR≥1+CM30-100亿",
    params_sql="(w.pct_chg >= -5 AND w.pct_chg <= -1) AND w.amplitude >= 5 AND b.volume_ratio >= 1.0 AND b.pb > 0 AND b.pb <= 1 AND b.dv_ttm >= 3 AND b.circ_mv >= 300000 AND b.circ_mv <= 1000000 AND m.sell_sm_vol > m.buy_sm_vol AND m.buy_elg_vol > m.sell_elg_vol",
    extra_joins=BASIC_JOIN + MF_JOIN + SPX_JOIN,
    filter_sql=SPX_FILTER,
)
results.append(r)
print(f"  N={r['N']}, R5={r['R5']}%, WR={r['WR']}%, PASS={r['pass']}")
sys.stdout.flush()

# ============ OUTPUT ============
print("\n" + "="*100)
print("RESULTS SUMMARY")
print("="*100)
print(f"{'ID':12s} {'N':>8s} {'R5%':>8s} {'WR%':>8s} {'Status':>10s}  Description")
print("-"*100)

passed = []
for r in results:
    st = "✅ PASS" if r['pass'] else "❌ FAIL"
    print(f"{r['name']:12s} {r['N']:>8d} {r['R5']:>7.2f}% {r['WR']:>7.2f}% {st:>10s}  {r['desc']}")
    if r['pass']:
        passed.append(r)

print("-"*100)
print(f"\nPassed: {len(passed)}/{len(results)}")

if passed:
    print("\nPASSED COMBOS (sorted by WR):")
    for i, r in enumerate(sorted(passed, key=lambda x: x['WR'], reverse=True), 1):
        print(f"  {i}. {r['name']}: N={r['N']}, R5={r['R5']}%, WR={r['WR']}%")

# Save
with open('iter22_t9_results.json', 'w') as f:
    json.dump({'results': results, 'passed_count': len(passed), 'total': len(results)}, f, indent=2, ensure_ascii=False)
print("\nSaved to iter22_t9_results.json")
