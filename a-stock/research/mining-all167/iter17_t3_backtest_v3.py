#!/usr/bin/env python3
"""
Iter17 T3 Reversal Low-Absorption Backtest v3
Tests 5 parameter combos against full historical data.
Uses leadInFrame with subquery wrappers for FINAL+JOIN compatibility.
"""
import json, sys, math, urllib.request, urllib.parse

HOST, PORT, USER, PWD = '172.24.224.1', '8123', 'ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ'
START_DATE = "2020-01-01"
END_DATE = "2026-05-12"

def ch_q(sql):
    """Execute ClickHouse query, return list[dict]"""
    params = {"user": USER, "password": PWD, "database": "tushare",
              "query": sql, "default_format": "JSONEachRow"}
    url = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=300) as resp:
        body = resp.read().decode("utf-8")
        if not body.strip():
            return []
        return [json.loads(line) for line in body.strip().split("\n") if line.strip()]

def run_backtest(name, params):
    print(f"\n{'='*60}")
    print(f"[{name}]")
    print(f"{'='*60}")
    
    # Build base SQL with window functions
    sql = """
    SELECT s.ts_code, s.trade_date, s.close, s.pct_chg, s.high, s.low, s.pre_close,
           -- 20-day range position
           (s.close - MIN(s.low) OVER w_range20) / NULLIF(MAX(s.high) OVER w_range20 - MIN(s.low) OVER w_range20, 0) AS close_pos,
           -- N-day low check
           CASE WHEN s.low = MIN(s.low) OVER w_10d THEN 1 ELSE 0 END AS low_10d_flag,
           CASE WHEN s.low = MIN(s.low) OVER w_20d THEN 1 ELSE 0 END AS low_20d_flag,
           -- Future returns
           leadInFrame(s.close, 5) OVER w_full AS close_5d,
           leadInFrame(s.close, 10) OVER w_full AS close_10d,
           leadInFrame(s.close, 20) OVER w_full AS close_20d,
           -- Basic data
           b.volume_ratio, b.turnover_rate, b.pe, b.pb, b.circ_mv
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    LEFT JOIN (
        SELECT ts_code, trade_date, volume_ratio, turnover_rate, pe, pb, circ_mv
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db
    ) b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WINDOW 
        w_range20 AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
        w_10d AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),
        w_20d AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
        w_full AS (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
    WHERE s.trade_date >= '{START_DATE}'
      AND s.trade_date <= '{END_DATE}'
      AND s.close_5d IS NOT NULL
      AND s.ts_code NOT LIKE '30%%'  -- no ChiNext
      AND s.ts_code NOT LIKE '688%%'  -- no STAR
      AND s.ts_code NOT LIKE '920%%'  -- no BSE
      AND s.ts_code NOT LIKE '%%ST%%'  -- no ST
    """.strip()
    
    # Apply combo filters
    filters = []
    
    # pct_chg
    if 'pct_chg_min' in params:
        filters.append(f"s.pct_chg <= {params['pct_chg_min']}")
    if 'pct_chg_max' in params:
        filters.append(f"s.pct_chg <= {params['pct_chg_max']}")
    
    # amplitude = (high-low)/pre_close*100
    if 'amplitude_min' in params:
        filters.append(f"((s.high - s.low) / NULLIF(s.pre_close, 0) * 100) >= {params['amplitude_min']}")
    
    # volume_ratio
    if 'volume_ratio_min' in params:
        filters.append(f"b.volume_ratio >= {params['volume_ratio_min']}")
    
    # turnover_rate
    if 'turnover_min' in params:
        filters.append(f"b.turnover_rate >= {params['turnover_min']}")
    if 'turnover_max' in params:
        filters.append(f"b.turnover_rate <= {params['turnover_max']}")
    
    # circ_mv (万元)
    if 'circ_mv_max' in params:
        cm = params['circ_mv_max'] / 10000
        filters.append(f"b.circ_mv <= {cm}")
    
    # PE/PB
    if 'pe_max' in params and params['pe_max'] is not None:
        filters.append(f"b.pe <= {params['pe_max']}")
    if 'pb_max' in params and params['pb_max'] is not None:
        filters.append(f"b.pb <= {params['pb_max']}")
    
    # close_position
    if 'close_position' in params:
        p = params['close_position']
        if p == '底20%':
            filters.append("close_pos <= 0.2")
        elif p == '底40%':
            filters.append("close_pos <= 0.4")
    
    # n_day_low (new low)
    if 'n_day_low' in params:
        n = params['n_day_low']
        if n == 10:
            filters.append("low_10d_flag = 1")
        elif n == 20:
            filters.append("low_20d_flag = 1")
    
    # Build the query
    if filters:
        sql += "\n  AND " + "\n  AND ".join(filters)
    
    # For moneyflow conditions, we need to use EXISTS
    has_mf = 'sm_bearish' in params or 'net_mf_required' in params
    
    if has_mf:
        mf_conds = []
        if 'sm_bearish' in params:
            v = params['sm_bearish']
            if v == 'sell_sm>buy_sm':
                mf_conds.append("mf.sell_sm_amount > mf.buy_sm_amount")
            elif v == 'buy_sm>sell_sm':
                mf_conds.append("mf.buy_sm_amount > mf.sell_sm_amount")
        if 'net_mf_required' in params:
            if params['net_mf_required'] == '负':
                mf_conds.append("mf.net_mf_amount < 0")
        
        mf_filter = " AND ".join(mf_conds) if mf_conds else "1=1"
        sql += f"""
  AND EXISTS (
      SELECT 1 FROM (SELECT * FROM tushare.tushare_moneyflow FINAL) AS mf
      WHERE mf.ts_code = s.ts_code AND mf.trade_date = s.trade_date
        AND {mf_filter}
  )"""
    
    sql += "\n  ORDER BY s.trade_date, s.ts_code"
    
    # ===== Execute =====
    print(f"  Executing query...")
    try:
        rows = ch_q(sql)
    except Exception as e:
        print(f"  SQL ERROR: {e}")
        return {'combo': name, 'params': params, 'error': str(e), 'signals': 0,
                'win_rate_5d': 0, 'avg_ret_5d': 0, 'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0}
    
    if not rows:
        print(f"  ⚠️ Zero signals")
        return {'combo': name, 'params': params, 'signals': 0,
                'win_rate_5d': 0, 'avg_ret_5d': 0, 'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0}
    
    n = len(rows)
    print(f"  Raw signals: {n}")
    
    # ===== Compute returns =====
    ret_5d = []
    ret_10d = []
    ret_20d = []
    
    for r in rows:
        c = r.get('close')
        if c and c > 0:
            c5, c10, c20 = r.get('close_5d'), r.get('close_10d'), r.get('close_20d')
            if c5 and c5 > 0:
                ret_5d.append((c5 / c) - 1)
            if c10 and c10 > 0:
                ret_10d.append((c10 / c) - 1)
            if c20 and c20 > 0:
                ret_20d.append((c20 / c) - 1)
    
    if not ret_5d:
        print(f"  ⚠️ No valid return calculations")
        return {'combo': name, 'params': params, 'signals': n,
                'win_rate_5d': 0, 'avg_ret_5d': 0, 'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0}
    
    avg_r5 = sum(ret_5d) / len(ret_5d) * 100
    avg_r10 = sum(ret_10d) / len(ret_10d) * 100 if ret_10d else 0
    avg_r20 = sum(ret_20d) / len(ret_20d) * 100 if ret_20d else 0
    wr = sum(1 for r in ret_5d if r > 0) / len(ret_5d) * 100
    
    # Sharpe
    mean_ret = sum(ret_5d) / len(ret_5d)
    if len(ret_5d) > 1:
        var = sum((r - mean_ret) ** 2 for r in ret_5d) / (len(ret_5d) - 1)
        std = math.sqrt(var) if var > 0 else 0.001
        sharpe = (mean_ret / std) * math.sqrt(252 / 5)
    else:
        sharpe = 0
    
    # P10
    sret = sorted(ret_5d)
    p10 = sret[max(0, int(len(sret) * 0.1) - 1)] * 100
    
    print(f"  Signals: {n}")
    print(f"  WinRate_5d: {wr:.2f}%")
    print(f"  AvgRet_5d: {avg_r5:.2f}%")
    print(f"  AvgRet_10d: {avg_r10:.2f}%")
    print(f"  AvgRet_20d: {avg_r20:.2f}%")
    print(f"  Sharpe_5d: {sharpe:.3f}")
    print(f"  P10_5d: {p10:.2f}%")
    
    return {'combo': name, 'params': params, 'signals': n,
            'win_rate_5d': round(wr, 2), 'avg_ret_5d': round(avg_r5, 2),
            'avg_ret_10d': round(avg_r10, 2), 'avg_ret_20d': round(avg_r20, 2),
            'sharpe_5d': round(sharpe, 3), 'p10_5d': round(p10, 2)}


# ===== 5 COMBOS =====
combos = [
    {'name': 'C1:恐慌深底筹码集中',
     'params': {'pct_chg_min': -7, 'close_position': '底20%', 'amplitude_min': 6,
                'volume_ratio_min': 1.3, 'circ_mv_max': 3000000000, 'pe_max': 20, 'turnover_max': 0.10}},
    {'name': 'C2:连续恐慌放量微盘',
     'params': {'n_day_low': 20, 'pct_chg_min': -5, 'amplitude_min': 7,
                'volume_ratio_min': 1.2, 'circ_mv_max': 3000000000}},
    {'name': 'C3:恐慌散户逆势大振幅',
     'params': {'pct_chg_min': -7, 'amplitude_min': 8, 'volume_ratio_min': 1.0,
                'sm_bearish': 'buy_sm>sell_sm', 'circ_mv_max': 5000000000,
                'turnover_min': 0.005, 'turnover_max': 0.05}},
    {'name': 'C4:双日恐慌深价值微盘',
     'params': {'n_day_low': 10, 'pct_chg_min': -5, 'amplitude_min': 5,
                'volume_ratio_min': 1.0, 'pe_max': 15, 'pb_max': 2, 'circ_mv_max': 3000000000}},
    {'name': 'C5:恐慌筹码锁定价值',
     'params': {'close_position': '底40%', 'pct_chg_min': -5, 'amplitude_min': 5,
                'volume_ratio_min': 1.3, 'turnover_min': 0.003, 'turnover_max': 0.03,
                'pe_max': 30, 'circ_mv_max': 10000000000}},
]

# ===== RUN ALL =====
results = []
for c in combos:
    r = run_backtest(c['name'], c['params'])
    results.append(r)

# ===== SUMMARY =====
print(f"\n{'='*60}")
print(f"ITER17 T3 REVERSAL LOW-ABSORPTION RESULTS")
print(f"{'='*60}")

passed = 0
best = None
for r in results:
    if 'error' in r and r['signals'] == 0:
        print(f"  ❌ {r['combo']}: ERROR - {r.get('error', '?')[:100]}")
        continue
    
    s, wr, r5 = r['signals'], r['win_rate_5d'], r['avg_ret_5d']
    
    if s >= 200 and wr >= 52 and r5 >= 3.0:
        passed += 1
        best = r if best is None or r5 > best['avg_ret_5d'] else best
        print(f"  ✅ {r['combo']}: N={s} WR={wr}% R5={r5}% R10={r['avg_ret_10d']}% Sharpe={r['sharpe_5d']}")
    else:
        reasons = [f"N={s}<200" if s < 200 else "", f"WR={wr}%<52%" if wr < 52 else "", f"R5={r5}%<3%" if r5 < 3.0 else ""]
        reasons = [x for x in reasons if x]
        print(f"  {'⚠️' if s >= 50 else '❌'} {r['combo']}: N={s} WR={wr}% R5={r5}% — {'; '.join(reasons)}")

print(f"\nPass rate: {passed}/5")

if best:
    print(f"\n🏆 BEST: {best['combo']}")
    print(f"  N={best['signals']} WR={best['win_rate_5d']}% R5={best['avg_ret_5d']}% R10={best['avg_ret_10d']}% R20={best['avg_ret_20d']}% Sharpe={best['sharpe_5d']}")

# Save
with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/iter17_t3_results.json', 'w') as f:
    json.dump({'timestamp': '2026-05-13 05:30 UTC+8', 'iteration': 17, 'analyst': 'T3',
               'results': results, 'passed': passed, 'best': best}, f, indent=2, ensure_ascii=False)
print(f"\nSaved to iter17_t3_results.json")
