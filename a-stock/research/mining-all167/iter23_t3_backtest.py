#!/usr/bin/env python3
"""Iter23 T3 反转低吸 — 纯SQL回测 (ClickHouse)
5组全新参数组合 — 新维度: gap_down, amplitude≥10%, no-VR, PB≤1+dv, dual-day panic+LG
"""
import json, hashlib, sys, math, os
from datetime import datetime
sys.path.insert(0, '/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts')
from ch_query import _ch_query as ch_query

BASE = '2026-05-12'
HIST = '2020-01-01'
BOARD = "sd.ts_code NOT LIKE '30%' AND sd.ts_code NOT LIKE '688%' AND sd.ts_code NOT LIKE '920%' AND sd.ts_code NOT LIKE '%ST%'"
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
    selects = ["sd.ts_code", "sd.trade_date", "sd.close", "sd.pct_chg",
               "sd.pre_close", "sd.high", "sd.low", "sd.open"]
    window_clauses = []
    window_clauses.append(
        f"leadInFrame(sd.close, 5) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WINDOW}) AS close_5d"
    )
    window_clauses.append(
        f"leadInFrame(sd.close, 10) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WINDOW}) AS close_10d"
    )
    window_clauses.append(
        f"leadInFrame(sd.close, 20) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WINDOW}) AS close_20d"
    )
    # 20d position windows
    window_clauses.append(
        f"MIN(sd.low) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d"
    )
    window_clauses.append(
        f"MAX(sd.high) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d"
    )
    # 60d position windows (if needed)
    if any('60日' in str(v) for v in params.values() if isinstance(v, str)):
        window_clauses.append(
            f"MIN(sd.low) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS low_60d"
        )
        window_clauses.append(
            f"MAX(sd.high) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS high_60d"
        )
    # LAG for dual-day panic
    if params.get('two_day_panic'):
        window_clauses.append(
            f"lagInFrame(sd.pct_chg, 1) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date {WINDOW}) AS prev_pct_chg"
        )
    window_sql = ",\n            ".join(window_clauses)
    sql = f"""
    WITH sd_windowed AS (
        SELECT 
            {selects[0]}, {selects[1]}, {selects[2]}, {selects[3]}, {selects[4]}, {selects[5]}, {selects[6]}, {selects[7]},
            {window_sql}
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS sd
        WHERE sd.trade_date >= '{HIST}' AND sd.trade_date <= '{BASE}'
          AND {BOARD}
    )
    """
    # Joins
    joins = []
    joins.append(f"""
    LEFT JOIN (
        SELECT ts_code, trade_date, volume_ratio, turnover_rate, pe, pb, circ_mv, dv_ttm
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
    ) b ON w.ts_code = b.ts_code AND w.trade_date = b.trade_date
    """)
    if params.get('spx_up'):
        joins.append(f"""
    INNER JOIN (
        SELECT trade_date FROM (SELECT * FROM tushare.tushare_index_global FINAL)
        WHERE ts_code = 'SPX' AND pct_chg > 0 AND trade_date >= '{HIST}'
    ) spx ON w.trade_date = spx.trade_date
        """)
    join_sql = "\n        ".join(joins)

    # Filters
    filters = ["w.close_5d IS NOT NULL"]
    if 'pct_chg_min' in params:
        filters.append(f"w.pct_chg <= {params['pct_chg_min']}")
    if 'pct_chg_max' in params:
        filters.append(f"w.pct_chg >= {params['pct_chg_max']}")
    if 'amplitude_min' in params:
        filters.append(f"((w.high - w.low) / w.pre_close * 100) >= {params['amplitude_min']}")
    if 'gap_down' in params and params['gap_down']:
        filters.append("w.open < w.pre_close")
    if params.get('close_position') == '底20%':
        filters.append("w.close <= w.low_20d + 0.2 * (w.high_20d - w.low_20d)")
    elif params.get('close_position') == '底10%':
        filters.append("w.close <= w.low_20d + 0.1 * (w.high_20d - w.low_20d)")
    elif params.get('close_position') == '底40%':
        filters.append("w.close <= w.low_40d + 0.4 * (w.high_40d - w.low_40d)")
    elif params.get('close_position') == '底20%60日':
        filters.append("w.close <= w.low_60d + 0.2 * (w.high_60d - w.low_60d)")
    elif params.get('close_position') == '底10%60日':
        filters.append("w.close <= w.low_60d + 0.1 * (w.high_60d - w.low_60d)")
    elif params.get('close_position') == '底40%60日':
        filters.append("w.close <= w.low_60d + 0.4 * (w.high_60d - w.low_60d)")
    if 'volume_ratio_min' in params:
        filters.append(f"b.volume_ratio >= {params['volume_ratio_min']}")
    if 'turnover_min' in params:
        filters.append(f"b.turnover_rate >= {params['turnover_min']}")
    if 'turnover_max' in params:
        filters.append(f"b.turnover_rate <= {params['turnover_max']}")
    if 'circ_mv_max' in params:
        v = params['circ_mv_max'] / 10000
        filters.append(f"b.circ_mv <= {v}")
    if 'pe_max' in params and params['pe_max'] is not None:
        filters.append(f"b.pe <= {params['pe_max']}")
    if 'pb_max' in params and params['pb_max'] is not None:
        filters.append(f"b.pb <= {params['pb_max']}")
    if 'dv_ttm_min' in params:
        filters.append(f"b.dv_ttm >= {params['dv_ttm_min']}")
    if params.get('two_day_panic'):
        filters.append("w.prev_pct_chg IS NOT NULL")
        filters.append("w.prev_pct_chg <= -3")
    where = " AND ".join(filters)

    # Moneyflow JOIN (replaces EXISTS due to ClickHouse scope limitations)
    mf_join_sql = ""
    mf_filter_sql = ""
    has_mf = any(k in params for k in ['sm_bearish', 'elg_bullish', 'lg_bullish'])
    if has_mf:
        mf_conds = []
        if params.get('sm_bearish'):
            mf_conds.append("m.sell_sm_amount > m.buy_sm_amount")
        if params.get('elg_bullish'):
            mf_conds.append("m.buy_elg_amount > m.sell_elg_amount")
        if params.get('lg_bullish'):
            mf_conds.append("m.buy_lg_amount > m.sell_lg_amount")
        mf_where = " AND ".join(mf_conds)
        mf_join_sql = f"""
    INNER JOIN (
        SELECT ts_code, trade_date, buy_sm_amount, sell_sm_amount, 
               buy_elg_amount, sell_elg_amount, buy_lg_amount, sell_lg_amount
        FROM (SELECT * FROM tushare.tushare_moneyflow FINAL)
    ) m ON w.ts_code = m.ts_code AND w.trade_date = m.trade_date
        """
        mf_filter_sql = f" AND {mf_where}"
    full_sql = f"""{sql}
    SELECT 
        w.ts_code, w.trade_date, w.close, w.pct_chg,
        ((w.high - w.low) / w.pre_close * 100) AS amplitude,
        w.close_5d, w.close_10d, w.close_20d,
        b.volume_ratio, b.turnover_rate, b.pe, b.pb, b.circ_mv, b.dv_ttm
    FROM sd_windowed w
    {join_sql}
    {mf_join_sql}
    WHERE {where}{mf_filter_sql}
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

# ===== 5 COMBOS =====
combos = [
    {
        'name': 'C1:缺口恐慌散户割肉低换手微盘',
        'params': {
            'gap_down': True, 'pct_chg_min': -5, 'close_position': '底20%',
            'amplitude_min': 5, 'volume_ratio_min': 1.0,
            'turnover_min': 0.003, 'turnover_max': 0.08,
            'sm_bearish': True,
            'circ_mv_max': 5000000000,
        },
    },
    {
        'name': 'C2:极端振幅10%超大单净买入无VR中小盘',
        'params': {
            'pct_chg_min': -7, 'close_position': '底20%60日',
            'amplitude_min': 10,
            'elg_bullish': True,
            'circ_mv_max': 10000000000,
        },
    },
    {
        'name': 'C3:破净高息恐慌散户割肉宽底40%扩容',
        'params': {
            'pct_chg_min': -5, 'close_position': '底40%60日',
            'amplitude_min': 5, 'volume_ratio_min': 1.0,
            'sm_bearish': True,
            'pb_max': 1, 'dv_ttm_min': 3,
            'circ_mv_max': 10000000000,
        },
    },
    {
        'name': 'C4:SPX恐慌双资金流60日深底无VR',
        'params': {
            'spx_up': True, 'pct_chg_min': -5, 'close_position': '底20%60日',
            'amplitude_min': 5,
            'sm_bearish': True, 'lg_bullish': True,
            'circ_mv_max': 5000000000,
        },
    },
    {
        'name': 'C5:双日恐慌LG大单净买入深价值微盘',
        'params': {
            'two_day_panic': True, 'pct_chg_min': -3,
            'close_position': '底20%',
            'amplitude_min': 5, 'volume_ratio_min': 1.0,
            'lg_bullish': True,
            'pe_max': 15, 'pb_max': 2,
            'circ_mv_max': 5000000000,
        },
    },
]

# Run all 5
results = []
best_r5 = 0
best_combo = None
for c in combos:
    print(f"\n=== {c['name']} ===")
    try:
        result = run_backtest(c['name'], c['params'])
    except Exception as e:
        print(f"  ERROR on {c['name']}: {e}")
        result = {
            'combo': c['name'], 'params': c['params'], 'hash': combo_hash(c['params']),
            'error': str(e), 'signals': 0, 'win_rate_5d': 0, 'avg_ret_5d': 0,
            'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0,
        }
    results.append(result)
    if result['avg_ret_5d'] > best_r5:
        best_r5 = result['avg_ret_5d']
        best_combo = result
    print(f"  -> Signals={result['signals']}, WR={result['win_rate_5d']}%, R5={result['avg_ret_5d']}%")

print(f"\n{'='*60}")
print(f"RESULTS SUMMARY:")
print(f"{'='*60}")
print(f"{'Combo':40s} {'N':>6s} {'WR%':>7s} {'R5%':>7s} {'R10%':>7s} {'R20%':>7s} {'Sharpe':>8s} {'P10%':>7s}")
print(f"{'-'*90}")
for r in results:
    n = r.get('signals', 0)
    wr = r.get('win_rate_5d', 0)
    r5 = r.get('avg_ret_5d', 0)
    r10 = r.get('avg_ret_10d', 0)
    r20 = r.get('avg_ret_20d', 0)
    sh = r.get('sharpe_5d', 0)
    p10 = r.get('p10_5d', 0)
    name = r['combo'][:40]
    print(f"{name:40s} {n:6d} {wr:7.2f} {r5:7.2f} {r10:7.2f} {r20:7.2f} {sh:8.3f} {p10:7.2f}")

print(f"\nBest R5: {best_combo['combo']} — R5={best_combo['avg_ret_5d']}%, WR={best_combo['win_rate_5d']}%, N={best_combo['signals']}")
print(f"Pass criteria: WR≥52% AND R5≥3% AND N≥200")
print(f"Excellent: WR≥58% AND R5≥7% AND N≥1000")
for r in results:
    passed = r['signals'] >= 200 and r['win_rate_5d'] >= 52 and r['avg_ret_5d'] >= 3
    excellent = r['signals'] >= 1000 and r['win_rate_5d'] >= 58 and r['avg_ret_5d'] >= 7
    status = "✅ PASS" if passed else "❌ FAIL"
    if excellent:
        status = "🏆 EXCELLENT"
    print(f"  {r['combo']:40s} — {status}")

# Save results
output = {
    'iteration': 23,
    'analyst': 'T3_反转低吸',
    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
    'base_date': BASE,
    'results': results,
}
with open(f'/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_23/analysis_T3_反转低吸.md', 'w') as f:
    f.write(f"# Iter23 T3 反转低吸分析报告\n\n")
    f.write(f"**时间**: {output['timestamp']}\n")
    f.write(f"**数据基准**: {BASE}\n")
    f.write(f"**流派**: 反转低吸 (T3)\n\n")
    f.write(f"## 测试组合\n\n")
    f.write(f"| 编号 | 参数组合 | N | WR% | R5% | R10% | R20% | Sharpe | P10% | 通过 |\n")
    f.write(f"|------|---------|--:|----:|----:|-----:|-----:|------:|-----:|:---:|\n")
    for r in results:
        n = r.get('signals', 0)
        wr = r.get('win_rate_5d', 0)
        r5 = r.get('avg_ret_5d', 0)
        r10 = r.get('avg_ret_10d', 0)
        r20 = r.get('avg_ret_20d', 0)
        sh = r.get('sharpe_5d', 0)
        p10 = r.get('p10_5d', 0)
        passed = n >= 200 and wr >= 52 and r5 >= 3
        status = "✅" if passed else "❌"
        ext = ""
        if passed and r5 >= 7 and wr >= 58 and n >= 1000:
            status = "🏆"
        if 'error' in r:
            f.write(f"| {r['combo'][:38]} | ERROR | - | - | - | - | - | - | ❌ |\n")
        else:
            f.write(f"| {r['combo'][:38]} | {n} | {wr:.2f} | {r5:.2f} | {r10:.2f} | {r20:.2f} | {sh:.3f} | {p10:.2f} | {status} |\n")
    f.write(f"\n## 详细SQL\n\n")
    for c in combos:
        f.write(f"### {c['name']}\n")
        f.write(f"```sql\n{build_sql(c['name'], c['params'])}\n```\n\n")
    f.write(f"\n## 结论\n\n")
    best = max(results, key=lambda r: r['avg_ret_5d'])
    f.write(f"**本轮最佳**: {best['combo']}\n")
    f.write(f"**指标**: N={best['signals']}, WR={best['win_rate_5d']}%, R5={best['avg_ret_5d']}%")
    if best.get('sharpe_5d'):
        f.write(f", Sharpe={best['sharpe_5d']}")
    f.write(f"\n\n")
    passed_any = any(r['signals'] >= 200 and r['win_rate_5d'] >= 52 and r['avg_ret_5d'] >= 3 for r in results)
    if passed_any:
        f.write(f"**本轮测试结论**: 有通过组合，建议纳入T9跨流派交叉验证。\n")
    else:
        f.write(f"**本轮测试结论**: 未通过组合，需要调整参数方向。\n")
    
    # Compare to best T3 from Iter22
    f.write(f"\n**对比Iter22 T3最佳(C2: R5=11.08%, WR=80.49%)**: ")
    if best['avg_ret_5d'] > 11.08:
        f.write(f"🏆 超越！新T3流派最佳！\n")
    else:
        f.write(f"未超越。差距: R5差距={11.08 - best['avg_ret_5d']:.2f}pp\n")

print(f"\n\nSummary file written to analysis_T3_反转低吸.md")
print(json.dumps(output, ensure_ascii=False, indent=2))
