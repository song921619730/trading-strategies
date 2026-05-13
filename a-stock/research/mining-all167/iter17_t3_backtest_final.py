#!/usr/bin/env python3
"""
Iter17 T3 Reversal Low-Absorption Backtest FINAL
Tests 5 parameter combos against full historical data.
"""
import json, sys, math, urllib.request, urllib.parse, hashlib

HOST, PORT, USER, PWD = '172.24.224.1', '8123', 'ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ'
START, END = "2020-01-01", "2026-05-12"

def ch_q(sql):
    params = {"user": USER, "password": PWD, "database": "tushare",
              "query": sql, "default_format": "JSONEachRow"}
    url = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=600) as resp:
        body = resp.read().decode("utf-8")
        if not body.strip():
            return []
        return [json.loads(line) for line in body.strip().split("\n") if line.strip()]

def make_hash(params_dict):
    raw = ','.join(sorted(f'{k}={v}' for k, v in params_dict.items()))
    return hashlib.md5(raw.encode()).hexdigest()[:10]

def run_backtest(name, params):
    print(f"\n{'='*60}")
    print(f"[{name}] hash={make_hash(params)}")
    print(f"{'='*60}")
    
    # Build the inner query with all window functions
    inner_cols = """
        s.ts_code, s.trade_date, s.close, s.pct_chg, s.high, s.low, s.pre_close,
        (s.high - s.low) / NULLIF(s.pre_close, 0) * 100 AS amp,
        leadInFrame(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS close_5d,
        leadInFrame(s.close, 10) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS close_10d,
        leadInFrame(s.close, 20) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS close_20d,
        (s.close - MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW))
         / NULLIF(MAX(s.high) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
                  - MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 0) AS close_pos,
        CASE WHEN s.low = MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) THEN 1 ELSE 0 END AS low_10d_flag,
        CASE WHEN s.low = MIN(s.low) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) THEN 1 ELSE 0 END AS low_20d_flag
    """.strip().replace('\n        ', '\n           ')
    
    sql = f"""
    WITH signal_data AS (
        SELECT {inner_cols}
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
        WHERE s.trade_date >= '{START}'
          AND s.trade_date <= '{END}'
          AND s.ts_code NOT LIKE '30%%'
          AND s.ts_code NOT LIKE '688%%'
          AND s.ts_code NOT LIKE '920%%'
          AND s.ts_code NOT LIKE '%%ST%%'
    )
    SELECT sd.*
    FROM signal_data sd
    WHERE sd.close_5d IS NOT NULL
    """
    
    # Add conditions
    if 'pct_chg_min' in params:
        sql += f"\n  AND sd.pct_chg <= {params['pct_chg_min']}"
    if 'amplitude_min' in params:
        sql += f"\n  AND sd.amp >= {params['amplitude_min']}"
    if 'close_position' in params:
        p = params['close_position']
        if p == '底20%':
            sql += "\n  AND sd.close_pos <= 0.2"
        elif p == '底40%':
            sql += "\n  AND sd.close_pos <= 0.4"
    if 'n_day_low' in params:
        n = params['n_day_low']
        if n == 10:
            sql += "\n  AND sd.low_10d_flag = 1"
        elif n == 20:
            sql += "\n  AND sd.low_20d_flag = 1"
    
    # Join with daily_basic (done AFTER window functions to avoid complexity)
    # We'll fetch signals first, then enrich with daily_basic and moneyflow
    print("  Phase 1: Signal detection...")
    try:
        signals = ch_q(sql)
    except Exception as e:
        return {'combo': name, 'params': params, 'error': str(e), 'signals': 0,
                'win_rate_5d': 0, 'avg_ret_5d': 0, 'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0}
    
    if not signals:
        print("  Zero signals")
        return {'combo': name, 'params': params, 'signals': 0,
                'win_rate_5d': 0, 'avg_ret_5d': 0, 'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0}
    
    n_signals = len(signals)
    print(f"  Raw signals: {n_signals}")
    
    # Phase 2: Enrich with daily_basic data
    # Create a code+date key to join in Python
    # Since we might have thousands of signals, use batch approach
    # For efficiency, collect unique codes and dates
    code_date_pairs = [(r['ts_code'], r['trade_date']) for r in signals]
    
    # For small signal counts (<100K), just query daily_basic for all signal dates
    dates_str = "','".join(set(d for _, d in code_date_pairs))
    
    has_basic = any(k in params for k in ['volume_ratio_min', 'turnover_min', 'turnover_max', 'circ_mv_max', 'pe_max', 'pb_max'])
    
    if has_basic:
        print("  Phase 2: Enriching with daily_basic...")
        # Batch query - since dates might be many, use a simpler approach
        # Query daily_basic for all signal pairs
        basic_map = {}
        batch_size = 5000
        for i in range(0, len(code_date_pairs), batch_size):
            batch = code_date_pairs[i:i+batch_size]
            # Build WHERE-in for ts_code and trade_date
            codes = list(set(c for c, _ in batch))
            dates = list(set(d for _, d in batch))
            
            code_str = "','".join(codes)
            date_str = "','".join(dates)
            
            if len(codes) > 500:  # Too many for IN clause, do simpler query
                basic_sql = f"""
                SELECT ts_code, trade_date, volume_ratio, turnover_rate, pe, pb, circ_mv
                FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) db
                WHERE db.trade_date IN ('{date_str}')
                """
            else:
                basic_sql = f"""
                SELECT ts_code, trade_date, volume_ratio, turnover_rate, pe, pb, circ_mv
                FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) db
                WHERE db.ts_code IN ('{code_str}') AND db.trade_date IN ('{date_str}')
                """
            
            try:
                rows = ch_q(basic_sql)
                for r in rows:
                    key = (r['ts_code'], r['trade_date'])
                    basic_map[key] = r
            except Exception as e:
                print(f"  ⚠️ daily_basic batch error: {e}")
        
        # Apply filters
        filtered = []
        for sig in signals:
            key = (sig['ts_code'], sig['trade_date'])
            bd = basic_map.get(key, {})
            
            ok = True
            if 'volume_ratio_min' in params:
                val = bd.get('volume_ratio')
                if val is None or val < params['volume_ratio_min']:
                    ok = False
            if ok and 'turnover_min' in params:
                val = bd.get('turnover_rate')
                if val is None or val < params['turnover_min']:
                    ok = False
            if ok and 'turnover_max' in params:
                val = bd.get('turnover_rate')
                if val is not None and val > params['turnover_max']:
                    ok = False
            if ok and 'circ_mv_max' in params:
                val = bd.get('circ_mv')
                if val is None or val > params['circ_mv_max'] / 10000:
                    ok = False
            if ok and 'pe_max' in params and params['pe_max'] is not None:
                val = bd.get('pe')
                if val is None or val > params['pe_max']:
                    ok = False
            if ok and 'pb_max' in params and params['pb_max'] is not None:
                val = bd.get('pb')
                if val is None or val > params['pb_max']:
                    ok = False
            
            if ok:
                filtered.append(sig)
        
        signals = filtered
        print(f"  After basic filters: {len(signals)} signals")
    
    # Phase 3: Moneyflow filter if needed
    has_mf = 'sm_bearish' in params or 'net_mf_required' in params
    if has_mf and signals:
        print("  Phase 3: Moneyflow filter...")
        code_date_pairs = [(r['ts_code'], r['trade_date']) for r in signals]
        codes = list(set(c for c, _ in code_date_pairs))
        dates = list(set(d for _, d in code_date_pairs))
        code_str = "','".join(codes)
        date_str = "','".join(dates)
        
        mf_sql = f"""
        SELECT ts_code, trade_date, buy_sm_amount, sell_sm_amount, net_mf_amount
        FROM (SELECT * FROM tushare.tushare_moneyflow FINAL) mf
        WHERE mf.trade_date IN ('{date_str}')
        """
        
        mf_map = {}
        try:
            rows = ch_q(mf_sql)
            for r in rows:
                key = (r['ts_code'], r['trade_date'])
                mf_map[key] = r
        except Exception as e:
            print(f"  ⚠️ moneyflow error: {e}")
        
        filtered = []
        for sig in signals:
            key = (sig['ts_code'], sig['trade_date'])
            mf = mf_map.get(key, {})
            
            ok = True
            if 'sm_bearish' in params:
                v = params['sm_bearish']
                buy = mf.get('buy_sm_amount', 0)
                sell = mf.get('sell_sm_amount', 0)
                if buy is None: buy = 0
                if sell is None: sell = 0
                if v == 'sell_sm>buy_sm' and not (sell > buy):
                    ok = False
                elif v == 'buy_sm>sell_sm' and not (buy > sell):
                    ok = False
            if ok and 'net_mf_required' in params and params['net_mf_required'] == '负':
                nmf = mf.get('net_mf_amount', 0)
                if nmf is None or nmf >= 0:
                    ok = False
            
            if ok:
                filtered.append(sig)
        
        signals = filtered
        print(f"  After moneyflow filter: {len(signals)} signals")
    
    if not signals:
        print("  All signals filtered out")
        return {'combo': name, 'params': params, 'signals': 0,
                'win_rate_5d': 0, 'avg_ret_5d': 0, 'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0}
    
    # ===== Compute returns =====
    ret_5d = []
    ret_10d = []
    ret_20d = []
    
    for r in signals:
        c = r.get('close')
        if c and c > 0:
            c5 = r.get('close_5d')
            c10 = r.get('close_10d')
            c20 = r.get('close_20d')
            if c5 and c5 > 0: ret_5d.append((c5 / c) - 1)
            if c10 and c10 > 0: ret_10d.append((c10 / c) - 1)
            if c20 and c20 > 0: ret_20d.append((c20 / c) - 1)
    
    if not ret_5d:
        return {'combo': name, 'params': params, 'signals': len(signals),
                'win_rate_5d': 0, 'avg_ret_5d': 0, 'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0}
    
    avg_r5 = sum(ret_5d) / len(ret_5d) * 100
    avg_r10 = sum(ret_10d) / len(ret_10d) * 100 if ret_10d else 0
    avg_r20 = sum(ret_20d) / len(ret_20d) * 100 if ret_20d else 0
    wr = sum(1 for r in ret_5d if r > 0) / len(ret_5d) * 100
    
    mean = sum(ret_5d) / len(ret_5d)
    if len(ret_5d) > 1:
        var = sum((r - mean) ** 2 for r in ret_5d) / (len(ret_5d) - 1)
        std = math.sqrt(var) if var > 0 else 0.001
        sharpe = (mean / std) * math.sqrt(252 / 5)
    else:
        sharpe = 0
    
    sret = sorted(ret_5d)
    p10 = sret[max(0, int(len(sret) * 0.1) - 1)] * 100
    
    print(f"\n  RESULTS:")
    print(f"  Signals: {len(signals)}")
    print(f"  WinRate_5d: {wr:.2f}%")
    print(f"  AvgRet_5d: {avg_r5:.2f}%")
    print(f"  AvgRet_10d: {avg_r10:.2f}%")
    print(f"  AvgRet_20d: {avg_r20:.2f}%")
    print(f"  Sharpe_5d: {sharpe:.3f}")
    print(f"  P10_5d: {p10:.2f}%")
    
    return {'combo': name, 'params': params, 'hash': make_hash(params), 'signals': len(signals),
            'win_rate_5d': round(wr, 2), 'avg_ret_5d': round(avg_r5, 2),
            'avg_ret_10d': round(avg_r10, 2), 'avg_ret_20d': round(avg_r20, 2),
            'sharpe_5d': round(sharpe, 3), 'p10_5d': round(p10, 2)}


# ===== 5 COMBOS =====
combos = [
    {'name': 'C1:恐慌深底筹码集中',
     'params': {'pct_chg_min': -7, 'close_position': '底20%', 'amplitude_min': 6,
                'volume_ratio_min': 1.3, 'circ_mv_max': 3000000000, 'pe_max': 20, 'turnover_max': 10.0}},
    {'name': 'C2:连续恐慌放量微盘',
     'params': {'n_day_low': 20, 'pct_chg_min': -5, 'amplitude_min': 7,
                'volume_ratio_min': 1.2, 'circ_mv_max': 3000000000}},
    {'name': 'C3:恐慌散户逆势大振幅',
     'params': {'pct_chg_min': -7, 'amplitude_min': 8, 'volume_ratio_min': 1.0,
                'sm_bearish': 'buy_sm>sell_sm', 'circ_mv_max': 5000000000,
                'turnover_min': 0.5, 'turnover_max': 5.0}},
    {'name': 'C4:双日恐慌深价值微盘',
     'params': {'n_day_low': 10, 'pct_chg_min': -5, 'amplitude_min': 5,
                'volume_ratio_min': 1.0, 'pe_max': 15, 'pb_max': 2, 'circ_mv_max': 3000000000}},
    {'name': 'C5:恐慌筹码锁定价值',
     'params': {'close_position': '底40%', 'pct_chg_min': -5, 'amplitude_min': 5,
                'volume_ratio_min': 1.3, 'turnover_min': 0.3, 'turnover_max': 3.0,
                'pe_max': 30, 'circ_mv_max': 10000000000}},
]

# ===== RUN ALL =====
results = []
for c in combos:
    r = run_backtest(c['name'], c['params'])
    results.append(r)

# ===== SUMMARY =====
print(f"\n{'='*60}")
print(f"ITER17 T3 REVERSAL LOW-ABSORPTION — RESULTS")
print(f"{'='*60}")

passed = 0
best = None
for r in results:
    if 'error' in r and r['signals'] == 0:
        print(f"  ❌ {r['combo']}: ERROR - {str(r.get('error',''))[:100]}")
        continue
    
    s, wr, r5 = r['signals'], r['win_rate_5d'], r['avg_ret_5d']
    label = "✅ PASS" if s >= 200 and wr >= 52 and r5 >= 3.0 else "❌ FAIL"
    if s >= 200 and wr >= 52 and r5 >= 3.0:
        passed += 1
        if best is None or r5 > best['avg_ret_5d']:
            best = r
    
    reasons = []
    if s < 200: reasons.append(f"N={s}")
    if wr < 52: reasons.append(f"WR={wr}%")
    if r5 < 3.0: reasons.append(f"R5={r5}%")
    
    print(f"  {label} {r['combo']}: N={s} WR={wr}% R5={r5}% R10={r['avg_ret_10d']}% Sharpe={r['sharpe_5d']}" 
          + (f" — {', '.join(reasons)}" if reasons else ""))

print(f"\nPass rate: {passed}/5")
if best:
    b = best
    print(f"\n🏆 BEST: {b['combo']}")
    print(f"   N={b['signals']} WR={b['win_rate_5d']}% R5={b['avg_ret_5d']}% R10={b['avg_ret_10d']}% R20={b['avg_ret_20d']}% Sharpe={b['sharpe_5d']}")

# Save
with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/iter17_t3_results.json', 'w') as f:
    json.dump({
        'timestamp': '2026-05-13 05:30 UTC+8', 'iteration': 17, 'analyst': 'T3',
        'results': results, 'passed': passed, 'best': best
    }, f, indent=2, ensure_ascii=False)
print(f"\nResults saved to iter17_t3_results.json")
