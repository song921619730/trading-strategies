#!/usr/bin/env python3
"""
Iter22 T3 反转低吸 — 纯SQL回测 (ClickHouse做全部计算)
5组全新参数组合
"""
import json, hashlib, sys, math, os
from datetime import datetime
sys.path.insert(0, '/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts')
from ch_query import _ch_query as ch_query

BASE = '2026-05-12'
HIST = '2020-01-01'
BOARD = "sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%' AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'"
# Board filter applied in the inner WHERE clause (within sd_windowed)
BOARD_INNER = True
WINDOW = "ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING"

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    return hashlib.md5(",".join(f"{k}={v}" for k,v in pairs).encode()).hexdigest()[:12]

def calc_sharpe(returns):
    if len(returns) < 5: return 0
    mean_r = sum(returns) / len(returns)
    if mean_r <= 0: return 0
    var = sum((r-mean_r)**2 for r in returns) / len(returns)
    std = math.sqrt(var) if var > 0 else 0.0001
    return mean_r/std * math.sqrt(252/5) if std > 0 else 0

def build_sql(combo_name, params):
    """Build a single SQL query for this combo with all filters + forward returns"""
    
    selects = ["sd.ts_code", "sd.trade_date", "sd.close", "sd.pct_chg", 
               "sd.pre_close", "sd.high", "sd.low"]
    
    window_clauses = []
    
    # Forward returns
    window_clauses.append(
        f"leadInFrame(sd.close, 5) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WINDOW}) AS close_5d"
    )
    window_clauses.append(
        f"leadInFrame(sd.close, 10) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WINDOW}) AS close_10d"
    )
    window_clauses.append(
        f"leadInFrame(sd.close, 20) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WINDOW}) AS close_20d"
    )
    
    # Position windows
    window_clauses.append(
        f"MIN(sd.low) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d"
    )
    window_clauses.append(
        f"MAX(sd.high) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d"
    )
    
    # Two-day panic needs LAG
    if 'two_day_panic' in params:
        window_clauses.append(
            f"lagInFrame(sd.pct_chg, 1) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WINDOW}) AS prev_pct_chg"
        )
    
    window_sql = ",\n            ".join(window_clauses)
    
    # Base CTE
    sql = f"""
    WITH sd_windowed AS (
        SELECT 
            {selects[0]}, {selects[1]}, {selects[2]}, {selects[3]}, {selects[4]}, {selects[5]}, {selects[6]},
            {window_sql}
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
        WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
          AND {BOARD}
    )
    """
    
    # Add joins: daily_basic, moneyflow (if needed), SPX (if needed), HSI (if needed)
    joins = []
    
    # daily_basic JOIN
    joins.append(f"""
    LEFT JOIN (
        SELECT ts_code, trade_date, volume_ratio, turnover_rate, pe, pb, circ_mv
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
    ) b ON w.ts_code = b.ts_code AND w.trade_date = b.trade_date
    """)
    
    # SPX JOIN
    if 'spx_up' in params:
        joins.append(f"""
    INNER JOIN (
        SELECT trade_date FROM (SELECT * FROM tushare.tushare_index_global FINAL)
        WHERE ts_code = 'SPX' AND pct_chg > 0 AND trade_date >= '{HIST}'
    ) spx ON w.trade_date = spx.trade_date
        """)
    
    # HSI JOIN
    if 'hsi_panic' in params:
        joins.append(f"""
    INNER JOIN (
        SELECT trade_date FROM (SELECT * FROM tushare.tushare_index_global FINAL)
        WHERE ts_code = 'HSI' AND pct_chg <= -1.5 AND trade_date >= '{HIST}'
    ) hsi ON w.trade_date = hsi.trade_date
        """)
    
    # Moneyflow EXISTS (only if needed - it's expensive)
    has_mf = any(k in params for k in ['sm_bearish', 'elg_bullish', 'net_mf_min'])
    
    join_sql = "\n        ".join(joins)
    
    # Filter conditions
    filters = []
    filters.append("w.close_5d IS NOT NULL")
    
    # pct_chg
    if 'pct_chg_min' in params and params['pct_chg_min'] is not None:
        filters.append(f"w.pct_chg <= {params['pct_chg_min']}")
    
    # amplitude = (high-low)/pre_close*100
    if 'amplitude_min' in params:
        filters.append(f"((w.high - w.low) / w.pre_close * 100) >= {params['amplitude_min']}")
    
    # Position
    if 'close_position' in params:
        pos = params['close_position']
        if pos == '底20%':
            filters.append("w.close <= w.low_20d + 0.2 * (w.high_20d - w.low_20d)")
        elif pos == '底10%':
            filters.append("w.close <= w.low_20d + 0.1 * (w.high_20d - w.low_20d)")
        elif pos == '底40%':
            filters.append("w.close <= w.low_40d + 0.4 * (w.high_40d - w.low_40d)")
    
    # VR, TR, CM, PE, PB from daily_basic (use b. prefix)
    if 'volume_ratio_min' in params:
        filters.append(f"b.volume_ratio >= {params['volume_ratio_min']}")
    if 'turnover_min' in params:
        filters.append(f"b.turnover_rate >= {params['turnover_min']}")
    if 'turnover_max' in params:
        filters.append(f"b.turnover_rate <= {params['turnover_max']}")
    if 'circ_mv_max' in params:
        v = params['circ_mv_max'] / 10000
        filters.append(f"b.circ_mv <= {v}")
    if 'circ_mv_min' in params:
        v = params['circ_mv_min'] / 10000
        filters.append(f"b.circ_mv >= {v}")
    if 'pe_max' in params and params['pe_max'] is not None:
        filters.append(f"b.pe <= {params['pe_max']}")
    if 'pb_max' in params and params['pb_max'] is not None:
        filters.append(f"b.pb <= {params['pb_max']}")
    
    # Two-day panic
    if 'two_day_panic' in params:
        filters.append("w.prev_pct_chg IS NOT NULL")
        filters.append("w.prev_pct_chg <= -3")
    
    where = " AND ".join(filters)
    
    # Build moneyflow EXISTS subquery
    mf_exists_sql = ""
    if has_mf:
        mf_conds = []
        if params.get('sm_bearish') == 'sell_sm>buy_sm':
            mf_conds.append("m.sell_sm_amount > m.buy_sm_amount")
        if params.get('elg_bullish') == 'buy_elg>sell_elg':
            mf_conds.append("m.buy_elg_amount > m.sell_elg_amount")
        if 'net_mf_min' in params:
            v = params['net_mf_min'] / 10000
            mf_conds.append(f"m.net_mf_amount >= {v}")
        mf_where = " AND ".join(mf_conds)
        mf_exists_sql = f"""
            AND EXISTS (
                SELECT 1 FROM (
                    SELECT ts_code, trade_date, buy_sm_amount, sell_sm_amount, buy_elg_amount, sell_elg_amount, net_mf_amount
                    FROM (SELECT * FROM tushare.tushare_moneyflow FINAL)
                ) m
                WHERE m.ts_code = w.ts_code AND m.trade_date = w.trade_date AND {mf_where}
            )
        """
    
    full_sql = f"""{sql}
    SELECT 
        w.ts_code, w.trade_date, w.close, w.pct_chg,
        ((w.high - w.low) / w.pre_close * 100) AS amplitude,
        w.close_5d, w.close_10d, w.close_20d,
        b.volume_ratio, b.turnover_rate, b.pe, b.pb, b.circ_mv
    FROM sd_windowed w
    {join_sql}
    WHERE {where}
    {mf_exists_sql}
    ORDER BY w.trade_date, w.ts_code
    """
    
    return full_sql

def run_backtest(combo_name, params):
    sql = build_sql(combo_name, params)
    
    print(f"  [{combo_name}] Running SQL...")
    try:
        rows = ch_query(sql)
    except Exception as e:
        return {
            'combo': combo_name, 'params': params, 'hash': combo_hash(params),
            'error': str(e), 'signals': 0, 'win_rate_5d': 0, 'avg_ret_5d': 0,
            'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0,
        }
    
    if not rows:
        return {
            'combo': combo_name, 'params': params, 'hash': combo_hash(params),
            'signals': 0, 'win_rate_5d': 0, 'avg_ret_5d': 0,
            'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0,
        }
    
    n = len(rows)
    print(f"  [{combo_name}] Got {n} signals")
    
    ret_5d_list, ret_10d_list, ret_20d_list = [], [], []
    
    for r in rows:
        close = r.get('close')
        c5 = r.get('close_5d')
        c10 = r.get('close_10d')
        c20 = r.get('close_20d')
        if close and close > 0 and c5 and c5 > 0:
            ret_5d_list.append((c5 / close) - 1)
        if close and close > 0 and c10 and c10 > 0:
            ret_10d_list.append((c10 / close) - 1)
        if close and close > 0 and c20 and c20 > 0:
            ret_20d_list.append((c20 / close) - 1)
    
    if not ret_5d_list:
        return {
            'combo': combo_name, 'params': params, 'hash': combo_hash(params),
            'signals': 0, 'win_rate_5d': 0, 'avg_ret_5d': 0,
            'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0,
        }
    
    avg_ret_5d = sum(ret_5d_list) / len(ret_5d_list)
    avg_ret_10d = sum(ret_10d_list) / len(ret_10d_list) if ret_10d_list else 0
    avg_ret_20d = sum(ret_20d_list) / len(ret_20d_list) if ret_20d_list else 0
    win_5d = sum(1 for r in ret_5d_list if r > 0) / len(ret_5d_list)
    sharpe = calc_sharpe(ret_5d_list)
    
    sorted_ret = sorted(ret_5d_list)
    p10_idx = max(0, int(len(sorted_ret) * 0.1) - 1)
    p10 = sorted_ret[p10_idx]
    
    return {
        'combo': combo_name, 'params': params, 'hash': combo_hash(params),
        'signals': n, 'win_rate_5d': round(win_5d * 100, 2),
        'avg_ret_5d': round(avg_ret_5d * 100, 2),
        'avg_ret_10d': round(avg_ret_10d * 100, 2),
        'avg_ret_20d': round(avg_ret_20d * 100, 2),
        'sharpe_5d': round(sharpe, 3), 'p10_5d': round(p10 * 100, 2),
    }

# ===== COMBOS =====
combos = [
    {
        'name': 'C1:SPX恐慌筹码锁筹微盘',
        'params': {
            'spx_up': True, 'pct_chg_min': -7, 'close_position': '底20%',
            'amplitude_min': 6, 'volume_ratio_min': 1.3,
            'turnover_min': 0.003, 'turnover_max': 0.05,
            'pe_max': 25, 'circ_mv_max': 5000000000,
        },
    },
    {
        'name': 'C2:HSI恐慌散割超单深价值',
        'params': {
            'hsi_panic': True, 'pct_chg_min': -5, 'close_position': '底20%',
            'amplitude_min': 6, 'volume_ratio_min': 1.2,
            'sm_bearish': 'sell_sm>buy_sm', 'elg_bullish': 'buy_elg>sell_elg',
            'pe_max': 15, 'pb_max': 2, 'circ_mv_max': 5000000000,
        },
    },
    {
        'name': 'C3:双日恐慌放量极低估值50亿',
        'params': {
            'two_day_panic': True, 'pct_chg_min': -5,
            'volume_ratio_min': 1.3, 'amplitude_min': 6,
            'pe_max': 10, 'circ_mv_max': 5000000000,
        },
    },
    {
        'name': 'C4:恐慌净流入散割深价值50亿',
        'params': {
            'pct_chg_min': -5, 'close_position': '底20%',
            'volume_ratio_min': 1.0, 'amplitude_min': 5,
            'net_mf_min': 5000000, 'sm_bearish': 'sell_sm>buy_sm',
            'pe_max': 15, 'pb_max': 2, 'circ_mv_max': 5000000000,
        },
    },
    {
        'name': 'C5:SPX恐慌深跌底10微盘',
        'params': {
            'spx_up': True, 'pct_chg_min': -7, 'close_position': '底10%',
            'amplitude_min': 8, 'volume_ratio_min': 1.3,
            'circ_mv_max': 3000000000, 'pe_max': 20,
        },
    },
]

print("="*60)
print(f"Iter22 T3 反转低吸 — 纯SQL回测")
print(f"Started: {datetime.now()}")
print("="*60)

for c in combos:
    print(f"  {c['name']}: hash={combo_hash(c['params'])}")

results = []
for combo in combos:
    h = combo_hash(combo['params'])
    print(f"\n{'='*60}")
    print(f"Running: {combo['name']} (hash={h})")
    print(f"{'='*60}")
    
    result = run_backtest(combo['name'], combo['params'])
    results.append(result)
    
    if 'error' in result:
        print(f"  ❌ ERROR: {result['error']}")
    else:
        n = result['signals']; wr = result['win_rate_5d']; r5 = result['avg_ret_5d']
        r10 = result['avg_ret_10d']; r20 = result['avg_ret_20d']
        s = result['sharpe_5d']; p10 = result['p10_5d']
        print(f"  N={n} WR={wr}% R5={r5}% R10={r10}% R20={r20}% S={s} P10={p10}%")
        tag = '❌' if n<200 or wr<55 or r5<5 else '✅'
        print(f"  {tag} {'PASS' if n>=200 and wr>=55 and r5>=5 else 'FAIL'}")

print(f"\n{'='*60}")
print(f"Iter22 T3 FINAL SUMMARY")
print(f"{'='*60}")
pass_count = 0
for r in results:
    if 'error' in r:
        print(f"  ❌ {r['combo']}: ERROR - {r['error']}")
        continue
    n = r['signals']; wr = r['win_rate_5d']; r5 = r['avg_ret_5d']
    passed = n >= 200 and wr >= 55 and r5 >= 5
    if passed:
        pass_count += 1
        print(f"  ✅ {r['combo']}: N={n} WR={wr}% R5={r5}% S={r['sharpe_5d']}")
    else:
        fails = []
        if n < 200: fails.append(f"N={n}")
        if wr < 55: fails.append(f"WR={wr}%")
        if r5 < 5: fails.append(f"R5={r5}%")
        print(f"  ❌ {r['combo']}: N={n} WR={wr}% R5={r5}% — fail: {', '.join(fails)}")

print(f"\nPass: {pass_count}/{len(combos)}")

with open("/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/iter22_t3_results.json", 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"Done: {datetime.now()}")
