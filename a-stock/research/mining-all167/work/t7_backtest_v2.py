#!/usr/bin/env python3
"""
Iter24 T7: Cross-market linkage backtest — efficient SQL-first approach.
"""
import json, urllib.request, urllib.parse, sys, statistics, base64
from datetime import date, timedelta

CLICKHOUSE_URL = "http://172.24.224.1:8123"
CLICKHOUSE_USER = "ai_reader"
CLICKHOUSE_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

AUTH = base64.b64encode(f"{CLICKHOUSE_USER}:{CLICKHOUSE_PASS}".encode()).decode()

def ch_query(sql):
    url = f"{CLICKHOUSE_URL}/?query={urllib.parse.quote(sql)}&default_format=JSON&max_result_bytes=500000000"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {AUTH}")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read()).get('data', [])
    except Exception as e:
        print(f"  [SQL ERROR] {e}", file=sys.stderr)
        return None

def compute_stats(rets):
    if not rets or len(rets) < 3:
        return {'N': len(rets) if rets else 0, 'WR': 0, 'avg_ret': 0, 'sharpe': 0}
    wr = sum(1 for r in rets if r > 0) / len(rets) * 100
    avg = statistics.mean(rets)
    std = statistics.stdev(rets) if len(rets) > 1 else 0.001
    sharpe = avg / std * (252 / 5) ** 0.5 if std > 0 else 0
    return {'N': len(rets), 'WR': round(wr, 2), 'avg_ret': round(avg, 2), 'sharpe': round(sharpe, 2)}

def load_index_data():
    """Load all global index data once."""
    idx = {}
    for ic in ['SPX', 'HSI', 'N225', 'KS11']:
        rows = ch_query(f"""
            SELECT trade_date, pct_chg 
            FROM (SELECT * FROM tushare.tushare_index_global FINAL) 
            WHERE ts_code = '{ic}' AND trade_date >= toDate('2020-01-01')
            ORDER BY trade_date
        """)
        if rows:
            idx[ic] = {r['trade_date']: r['pct_chg'] for r in rows}
            print(f"  Loaded {ic}: {len(rows)} rows, {rows[0]['trade_date']} to {rows[-1]['trade_date']}")
    # Precompute SPX 3-day rolling sum
    idx['SPX_3D'] = {}
    spx_dates = sorted(idx.get('SPX', {}).keys())
    for i in range(2, len(spx_dates)):
        total = idx['SPX'][spx_dates[i]] + idx['SPX'][spx_dates[i-1]] + idx['SPX'][spx_dates[i-2]]
        idx['SPX_3D'][spx_dates[i]] = total
    return idx

def get_idx_pct(idx_dict, dt_str, fallback_days=2):
    """Get index pct_chg for a given date, with fallback to previous days."""
    if not idx_dict:
        return None
    if dt_str in idx_dict:
        return idx_dict[dt_str]
    dt = date.fromisoformat(dt_str)
    for d in range(1, fallback_days + 1):
        prev = (dt - timedelta(days=d)).isoformat()
        if prev in idx_dict:
            return idx_dict[prev]
    return None

def get_spx_3d(idx, dt_str):
    if not idx.get('SPX_3D'):
        return None
    if dt_str in idx['SPX_3D']:
        return idx['SPX_3D'][dt_str]
    dt = date.fromisoformat(dt_str)
    for d in range(1, 3):
        prev = (dt - timedelta(days=d)).isoformat()
        if prev in idx['SPX_3D']:
            return idx['SPX_3D'][prev]
    return None

def run_backtest(combo, idx, combo_name, combo_desc):
    """Run backtest for one combo using SQL for stock filters, Python for cross-market filters."""
    print(f"\n{'='*60}")
    print(f"📊 {combo_name}: {combo_desc}")
    print(f"    {json.dumps(combo)}")
    print('='*60)
    
    # Build WHERE conditions for stock-level SQL
    stock_conditions = [
        "sd.trade_date >= toDate('2020-01-01')",
        "sd.trade_date <= toDate('2026-05-12')",
        "sd.ts_code NOT LIKE '30%'",
        "sd.ts_code NOT LIKE '688%'",
        "sd.ts_code NOT LIKE '920%'",
        "sd.ts_code NOT LIKE '%ST%'",
        "sd.close > 0",
        "sd.pre_close > 0",
    ]
    
    # Push stock-level conditions into SQL WHERE
    if 'prev_pct_chg_max' in combo:
        # Use outer WHERE for LAG column
        pass  # applied in outer query
    if 'cur_pct_chg_min' in combo:
        stock_conditions.append(f"sd.pct_chg >= {combo['cur_pct_chg_min']}")
    if 'cur_pct_chg_max' in combo:
        stock_conditions.append(f"sd.pct_chg <= {combo['cur_pct_chg_max']}")
    if 'vr_min' in combo:
        stock_conditions.append(f"db.volume_ratio >= {combo['vr_min']}")
    if 'amplitude_min' in combo:
        stock_conditions.append(f"(sd.high - sd.low) / sd.pre_close * 100 >= {combo['amplitude_min']}")
    if 'tr_min' in combo:
        stock_conditions.append(f"db.turnover_rate >= {combo['tr_min']}")
    if 'tr_max' in combo:
        stock_conditions.append(f"db.turnover_rate <= {combo['tr_max']}")
    if 'circ_mv_max' in combo:
        stock_conditions.append(f"db.circ_mv <= {combo['circ_mv_max'] * 10000}")
    if 'circ_mv_min' in combo:
        stock_conditions.append(f"db.circ_mv >= {combo['circ_mv_min'] * 10000}")
    
    where_clause = ' AND '.join(stock_conditions)
    
    # Build the SQL
    sql = f"""
    SELECT *
    FROM (
      SELECT sd.ts_code, sd.trade_date, sd.close, sd.pct_chg,
             (sd.high - sd.low) / sd.pre_close * 100 AS amplitude,
             db.volume_ratio, db.turnover_rate, db.circ_mv,
             lagInFrame(sd.pct_chg) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 1 PRECEDING AND 0 FOLLOWING) AS prev_pct_chg,
             leadInFrame(sd.close, 5) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 0 FOLLOWING AND 5 FOLLOWING) AS close_5d,
             leadInFrame(sd.close, 10) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 0 FOLLOWING AND 10 FOLLOWING) AS close_10d,
             leadInFrame(sd.close, 20) OVER (PARTITION BY sd.ts_code ORDER BY sd.trade_date ROWS BETWEEN 0 FOLLOWING AND 20 FOLLOWING) AS close_20d
      FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) sd
      LEFT JOIN (SELECT ts_code, trade_date, volume_ratio, turnover_rate, circ_mv FROM tushare.tushare_daily_basic FINAL) db
        ON sd.ts_code = db.ts_code AND sd.trade_date = db.trade_date
      WHERE {where_clause}
    ) AS sub
    """
    
    # Add outer WHERE for LAG-based conditions
    outer_conditions = []
    if 'prev_pct_chg_max' in combo:
        outer_conditions.append(f"sub.prev_pct_chg <= {combo['prev_pct_chg_max']}")
    if 'prev_pct_chg_min' in combo:
        outer_conditions.append(f"sub.prev_pct_chg >= {combo['prev_pct_chg_min']}")
    
    if outer_conditions:
        sql += f" WHERE {' AND '.join(outer_conditions)}"
    
    # Execute
    print("  Running SQL...")
    rows = ch_query(sql)
    if rows is None:
        return None
    
    print(f"  SQL returned {len(rows)} candidate rows")
    
    if len(rows) < 20:
        print(f"  ⚠️ Too few candidates")
        return {
            'name': combo_name, 'N': len(rows), 'SQL_N': len(rows),
            'WR_5d': 0, 'ret_5d': 0, 'sharpe_5d': 0,
            'WR_10d': 0, 'ret_10d': 0, 'sharpe_10d': 0,
            'WR_20d': 0, 'ret_20d': 0, 'sharpe_20d': 0,
            'params': combo, 'status': 'INSUFFICIENT'
        }
    
    # Apply cross-market filters in Python
    print("  Applying cross-market filters...")
    signals = []
    for r in rows:
        dt = r['trade_date']
        passed = True
        
        # SPX conditions
        if 'spx_prev_min' in combo:
            spx = get_idx_pct(idx.get('SPX'), dt)
            if spx is None or spx < combo['spx_prev_min']:
                passed = False
        if 'spx_prev_max' in combo:
            spx = get_idx_pct(idx.get('SPX'), dt)
            if spx is None or spx > combo['spx_prev_max']:
                passed = False
        
        # SPX 3D rolling
        if 'spx_3d_min' in combo:
            spx3 = get_spx_3d(idx, dt)
            if spx3 is None or spx3 < combo['spx_3d_min']:
                passed = False
        if 'spx_3d_max' in combo:
            spx3 = get_spx_3d(idx, dt)
            if spx3 is None or spx3 > combo['spx_3d_max']:
                passed = False
        
        # HSI conditions
        if 'hsi_prev_min' in combo:
            hsi = get_idx_pct(idx.get('HSI'), dt)
            if hsi is None or hsi < combo['hsi_prev_min']:
                passed = False
        if 'hsi_prev_max' in combo:
            hsi = get_idx_pct(idx.get('HSI'), dt)
            if hsi is None or hsi > combo['hsi_prev_max']:
                passed = False
        
        # N225 conditions
        if 'n225_prev_min' in combo:
            n225 = get_idx_pct(idx.get('N225'), dt)
            if n225 is None or n225 < combo['n225_prev_min']:
                passed = False
        if 'n225_prev_max' in combo:
            n225 = get_idx_pct(idx.get('N225'), dt)
            if n225 is None or n225 > combo['n225_prev_max']:
                passed = False
        
        # KS11 conditions
        if 'ks11_prev_min' in combo:
            ks11 = get_idx_pct(idx.get('KS11'), dt)
            if ks11 is None or ks11 < combo['ks11_prev_min']:
                passed = False
        if 'ks11_prev_max' in combo:
            ks11 = get_idx_pct(idx.get('KS11'), dt)
            if ks11 is None or ks11 > combo['ks11_prev_max']:
                passed = False
        
        if passed:
            signals.append(r)
    
    print(f"  After cross-market filters: {len(signals)} signals")
    
    if len(signals) < 20:
        print(f"  ⚠️ Too few signals after filter")
        return {
            'name': combo_name, 'N': len(signals), 'SQL_N': len(rows),
            'WR_5d': 0, 'ret_5d': 0, 'sharpe_5d': 0,
            'WR_10d': 0, 'ret_10d': 0, 'sharpe_10d': 0,
            'WR_20d': 0, 'ret_20d': 0, 'sharpe_20d': 0,
            'params': combo, 'status': 'INSUFFICIENT'
        }
    
    # Compute forward returns
    rets_5d, rets_10d, rets_20d = [], [], []
    for s in signals:
        c0 = s.get('close')
        if not c0 or c0 <= 0:
            continue
        for key, lst in [('close_5d', rets_5d), ('close_10d', rets_10d), ('close_20d', rets_20d)]:
            cv = s.get(key)
            if cv and cv > 0:
                lst.append((cv / c0 - 1) * 100)
    
    st5 = compute_stats(rets_5d)
    st10 = compute_stats(rets_10d)
    st20 = compute_stats(rets_20d)
    
    passed = (st5['WR'] >= 52 and st5['avg_ret'] >= 3 and st5['N'] >= 200)
    
    result = {
        'name': combo_name, 'N': len(signals), 'SQL_N': len(rows),
        'N_5d': st5['N'], 'WR_5d': st5['WR'], 'ret_5d': st5['avg_ret'], 'sharpe_5d': st5['sharpe'],
        'N_10d': st10['N'], 'WR_10d': st10['WR'], 'ret_10d': st10['avg_ret'], 'sharpe_10d': st10['sharpe'],
        'N_20d': st20['N'], 'WR_20d': st20['WR'], 'ret_20d': st20['avg_ret'], 'sharpe_20d': st20['sharpe'],
        'params': combo, 'status': '✅ PASS' if passed else '❌ FAIL'
    }
    
    print(f"\n  📊 Results: N={result['N']}")
    print(f"    5D: WR={result['WR_5d']}% ret={result['ret_5d']}% Sharpe={result['sharpe_5d']}")
    print(f"    10D: WR={result['WR_10d']}% ret={result['ret_10d']}% Sharpe={result['sharpe_10d']}")
    print(f"    20D: WR={result['WR_20d']}% ret={result['ret_20d']}% Sharpe={result['sharpe_20d']}")
    print(f"    Status: {result['status']}")
    
    return result


if __name__ == '__main__':
    print("🔄 Iter24 T7: Cross-Market Linkage Backtest")
    print("="*60)
    
    # Load index data once
    print("\n📥 Loading global index data...")
    idx = load_index_data()
    if not idx.get('SPX'):
        print("❌ Failed to load index data!")
        sys.exit(1)
    
    # Define 5 combos
    combos = [
        {
            'id': 'C1',
            'name': 'C1: SPX连涨3日+恐慌底',
            'desc': 'SPX连续3日累计涨幅≥1.5% + A股昨跌≤-5%放量底',
            'params': {
                'prev_pct_chg_max': -5.0,
                'amplitude_min': 6.0,
                'vr_min': 1.3,
                'spx_3d_min': 1.5,
                'circ_mv_max': 30,
            }
        },
        {
            'id': 'C2',
            'name': 'C2: N225+KS11双涨',
            'desc': '亚太多指数风险偏好共振(N225涨+KS11涨) + A股昨跌≤-4%',
            'params': {
                'prev_pct_chg_max': -4.0,
                'amplitude_min': 5.0,
                'vr_min': 1.0,
                'n225_prev_min': 0,
                'ks11_prev_min': 0,
                'circ_mv_max': 50,
            }
        },
        {
            'id': 'C3',
            'name': 'C3: SPX+HSI双涨恐慌反转',
            'desc': '中美两大市场同时risk-on + A股恐慌底反转',
            'params': {
                'prev_pct_chg_max': -5.0,
                'amplitude_min': 6.0,
                'vr_min': 1.2,
                'spx_prev_min': 0,
                'hsi_prev_min': 0,
                'circ_mv_max': 30,
            }
        },
        {
            'id': 'C4',
            'name': 'C4: KS11暴涨+SPX涨跟涨',
            'desc': '韩国暴涨(≥3%)作为新兴市场领先指标, SPX偏多, A股当日跟涨',
            'params': {
                'cur_pct_chg_min': 2.0,
                'amplitude_min': 5.0,
                'vr_min': 1.0,
                'spx_prev_min': 0,
                'ks11_prev_min': 3.0,
                'circ_mv_max': 50,
            }
        },
        {
            'id': 'C5',
            'name': 'C5: SPX跌+N225涨+恐慌底',
            'desc': 'US下跌但日股独立上涨(资本东移) + A股恐慌底抄底',
            'params': {
                'prev_pct_chg_max': -5.0,
                'amplitude_min': 6.0,
                'vr_min': 1.0,
                'spx_prev_max': -0.5,
                'n225_prev_min': 0.5,
                'circ_mv_max': 30,
            }
        },
    ]
    
    results = []
    for c in combos:
        r = run_backtest(c['params'], idx, c['name'], c['desc'])
        if r:
            results.append(r)
    
    # Summary
    print(f"\n\n{'='*70}")
    print(f"📋 ITER24 T7 — CROSS-MARKET LINKAGE FINAL SUMMARY")
    print('='*70)
    header = f"{'Combo':<30} {'N':<6} {'WR5':<7} {'R5':<7} {'WR10':<7} {'R10':<7} {'WR20':<7} {'R20':<7} {'Sharp5':<7} {'Status':<10}"
    print(header)
    print('-' * len(header))
    for r in results:
        name = r['name'][:28]
        print(f"{name:<30} {r['N']:<6} {r['WR_5d']:<7} {r['ret_5d']:<7} {r['WR_10d']:<7} {r['ret_10d']:<7} {r['WR_20d']:<7} {r['ret_20d']:<7} {r['sharpe_5d']:<7} {r['status']:<10}")
    
    passed = [r for r in results if r['status'] == '✅ PASS']
    if passed:
        best = max(passed, key=lambda x: x['WR_5d'])
        print(f"\n🏆 BEST PASS: {best['name']}")
        print(f"   WR_5d={best['WR_5d']}% ret_5d={best['ret_5d']}% Sharpe={best['sharpe_5d']} N={best['N']}")
    else:
        # Show combo closest to passing
        best = max(results, key=lambda x: x['WR_5d'] + x['ret_5d'])
        print(f"\n📌 Best attempt: {best['name']}")
        print(f"   WR_5d={best['WR_5d']}% ret_5d={best['ret_5d']}% N={best['N']} (needs WR≥52% R5≥3% N≥200)")
    
    # Export results for report
    print("\n\n📝 RAW RESULTS FOR REPORT:")
    print(json.dumps(results, ensure_ascii=False, indent=2))
