#!/usr/bin/env python3
"""
T5 基本面估值流派 — 5组参数组合回测
估值(PB/PE)+股息+净利润增长+底部位置组合
"""
import json, hashlib, math, subprocess, sys, os
from datetime import datetime

CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_URL = "http://127.0.0.1:8123"
CH_DB = "tushare"
START_DATE = "2023-01-01"
END_DATE = "2026-05-11"

def ch_query(sql, fmt="JSON", timeout=180):
    with open('/tmp/ch_query_t5.sql', 'w') as f:
        f.write(sql.rstrip().rstrip(";") + (f"\nFORMAT {fmt}" if fmt else ""))
    cmd = ["curl", "-s", "-X", "POST",
           f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&max_execution_time={timeout}&database={CH_DB}",
           "--data-binary", "@/tmp/ch_query_t5.sql"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+10)
        data = result.stdout
        if fmt == "JSON":
            parsed = json.loads(data)
            return parsed
        return data.strip()
    except json.JSONDecodeError:
        return {"data": [], "error": data.strip()[:500]}
    except subprocess.TimeoutExpired:
        return {"data": [], "error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"data": [], "error": str(e)}

def compute_stats(results):
    n = len(results)
    if n == 0:
        return {"signal_count": 0, "wr_5d": 0, "wr_10d": 0, "wr_20d": 0,
                "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0}
    def avg(lst): return sum(lst) / len(lst) if lst else 0
    def std(lst):
        if len(lst) < 2: return 0
        m = avg(lst)
        return math.sqrt(sum((x-m)**2 for x in lst) / len(lst))
    stats = {"signal_count": n}
    for k in ["ret_5d", "ret_10d", "ret_20d"]:
        vals = [r[k] for r in results if r[k] is not None]
        stats[f"wr_{k.replace('ret_', '')}"] = round(sum(1 for v in vals if v > 0) / len(vals) * 100, 2) if vals else 0
        stats[k] = round(avg(vals) * 100, 4) if vals else 0
    ret5_vals = [r["ret_5d"] for r in results if r["ret_5d"] is not None]
    if len(ret5_vals) > 1:
        sd = std(ret5_vals)
        stats["sharpe_5d"] = round((avg(ret5_vals) / sd) * math.sqrt(252/5), 4) if sd > 0 else 0
    else:
        stats["sharpe_5d"] = 0
    return stats

def build_candidates(up_to_date=END_DATE):
    """Phase 1: SQL window functions to find base candidates"""
    print(f"\n{'='*60}")
    print(f"Phase 1: Building Candidates (up to {up_to_date})")
    print(f"{'='*60}")
    
    sql = f"""
    SELECT ts_code, trade_date, close, pct_chg, high, low, vol, amount,
        round((high / low - 1) * 100, 2) AS amplitude,
        round((close - min_low_20d) / NULLIF(max_high_20d - min_low_20d, 0.001) * 100, 2) AS pos_20d,
        round(vol / NULLIF(avg_vol_20d, 0.001), 2) AS vol_ratio
    FROM (
        SELECT ts_code, trade_date, close, high, low, vol, amount, pct_chg,
            MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_low_20d,
            MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_high_20d,
            AVG(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg_vol_20d
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{up_to_date}'
          AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%'
          AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    )
    WHERE pos_20d <= 30 AND amplitude >= 3
    ORDER BY ts_code, trade_date
    """
    
    r = ch_query(sql, timeout=600)
    data = r.get('data', [])
    print(f"  Base candidates: {len(data)} rows")
    
    candidates = {}
    for row in data:
        key = (row['ts_code'], str(row['trade_date'])[:10])
        candidates[key] = row
    
    ts_codes = set(row['ts_code'] for row in data)
    print(f"  Distinct stocks: {len(ts_codes)}")
    
    return candidates, ts_codes

def fetch_daily_basic(ts_codes, up_to_date=END_DATE):
    """Phase 2: Fetch daily_basic for PE, PB, dv_ratio, volume_ratio, circ_mv"""
    print(f"\n{'='*60}")
    print(f"Phase 2: Fetching Daily Basic")
    print(f"{'='*60}")
    
    code_list = list(ts_codes)
    batch_size = 500
    db_data = {}
    
    for i in range(0, len(code_list), batch_size):
        batch = code_list[i:i+batch_size]
        codes_str = ",".join(f"'{c}'" for c in batch)
        
        sql = f"""
        SELECT ts_code, trade_date, pe, pb, dv_ratio, volume_ratio, circ_mv
        FROM tushare.tushare_daily_basic FINAL
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{up_to_date}'
          AND ts_code IN ({codes_str})
        ORDER BY ts_code, trade_date
        """
        
        r = ch_query(sql, timeout=300)
        rows = r.get('data', [])
        for row in rows:
            key = (row['ts_code'], str(row['trade_date'])[:10])
            db_data[key] = row
        
        if (i // batch_size) % 10 == 0 or i + batch_size >= len(code_list):
            print(f"  Batch {i//batch_size}/{(len(code_list)-1)//batch_size}: "
                  f"codes={len(batch)}, db_rows={len(rows)}, total={len(db_data)}")
    
    print(f"  Total daily_basic rows: {len(db_data)}")
    return db_data

def fetch_fina_indicator(ts_codes):
    """Phase 3: Fetch fina_indicator for netprofit_yoy, tr_yoy (latest quarterly)"""
    print(f"\n{'='*60}")
    print(f"Phase 3: Fetching Financial Indicators")
    print(f"{'='*60}")
    
    code_list = list(ts_codes)
    batch_size = 1000
    fina_data = {}
    
    for i in range(0, len(code_list), batch_size):
        batch = code_list[i:i+batch_size]
        codes_str = ",".join(f"'{c}'" for c in batch)
        
        sql = f"""
        SELECT ts_code, end_date, netprofit_yoy, tr_yoy
        FROM tushare.tushare_fina_indicator FINAL
        WHERE ts_code IN ({codes_str})
        ORDER BY ts_code, end_date DESC
        """
        
        r = ch_query(sql, timeout=300)
        rows = r.get('data', [])
        for row in rows:
            code = row['ts_code']
            if code not in fina_data:
                # Keep only the latest record per stock
                fina_data[code] = {
                    'end_date': str(row['end_date'])[:10],
                    'netprofit_yoy': row.get('netprofit_yoy'),
                    'tr_yoy': row.get('tr_yoy'),
                }
        
        if (i // batch_size) % 5 == 0 or i + batch_size >= len(code_list):
            print(f"  Batch {i//batch_size}/{(len(code_list)-1)//batch_size}: "
                  f"codes={len(batch)}, fina_rows={len(rows)}, unique_stocks={len(fina_data)}")
    
    print(f"  Total fina_indicator records (latest per stock): {len(fina_data)}")
    return fina_data

def fetch_forward_prices(ts_codes, up_to_date=END_DATE):
    """Phase 4: Fetch future prices for return computation"""
    print(f"\n{'='*60}")
    print(f"Phase 4: Fetching Forward Prices")
    print(f"{'='*60}")
    
    code_list = list(ts_codes)
    batch_size = 500
    all_prices = {}
    
    for i in range(0, len(code_list), batch_size):
        batch = code_list[i:i+batch_size]
        codes_str = ",".join(f"'{c}'" for c in batch)
        
        sql = f"""
        SELECT ts_code, trade_date, close
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{up_to_date}'
          AND ts_code IN ({codes_str})
        ORDER BY ts_code, trade_date
        """
        
        r = ch_query(sql, timeout=300)
        rows = r.get('data', [])
        for row in rows:
            key = (row['ts_code'], str(row['trade_date'])[:10])
            all_prices[key] = row['close']
        
        if (i // batch_size) % 10 == 0 or i + batch_size >= len(code_list):
            print(f"  Batch {i//batch_size}/{(len(code_list)-1)//batch_size}: "
                  f"codes={len(batch)}, price_rows={len(rows)}, total={len(all_prices)}")
    
    print(f"  Total price rows: {len(all_prices)}")
    return all_prices

def compute_forward_returns(signals, all_prices):
    """Compute forward returns (1D, 3D, 5D, 10D, 20D) for each signal"""
    results = []
    for s in signals:
        code = s['ts_code']
        entry_date = s['trade_date']
        
        stock_dates = sorted([d for (c, d), v in all_prices.items()
                              if c == code and d >= entry_date])
        
        if entry_date not in stock_dates:
            continue
        
        idx = stock_dates.index(entry_date)
        
        rets = {
            'ts_code': code,
            'trade_date': entry_date,
            'entry_close': s['close'],
            'amplitude': s.get('amplitude'),
            'pos_20d': s.get('pos_20d'),
            'vol_ratio': s.get('vol_ratio'),
            'pct_chg': s.get('pct_chg'),
            'circ_mv': s.get('circ_mv'),
            'pe': s.get('pe'),
            'pb': s.get('pb'),
            'dv_ratio': s.get('dv_ratio'),
            'netprofit_yoy': s.get('netprofit_yoy'),
            'tr_yoy': s.get('tr_yoy'),
        }
        
        for offset, key in [(1, 'ret_1d'), (3, 'ret_3d'), (5, 'ret_5d'),
                            (10, 'ret_10d'), (20, 'ret_20d')]:
            if idx + offset < len(stock_dates):
                future_date = stock_dates[idx + offset]
                future_close = all_prices.get((code, future_date))
                if future_close and s['close'] and s['close'] > 0:
                    rets[key] = (future_close - s['close']) / s['close']
                else:
                    rets[key] = None
            else:
                rets[key] = None
        
        results.append(rets)
    
    return results

def combo_hash(params):
    return hashlib.md5(json.dumps(sorted(params.items()), ensure_ascii=False).encode()).hexdigest()[:12]

def run():
    t0 = datetime.now()
    
    # Verify data freshness
    print("=== Data Freshness Check ===")
    r = ch_query("SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL")
    max_date = r.get('data', [{}])[0].get('max(trade_date)', 'UNKNOWN')
    print(f"  max(trade_date): {max_date}")
    
    r2 = ch_query("SELECT count() as cnt FROM tushare.tushare_daily_basic FINAL WHERE trade_date >= '2026-05-01'")
    db_cnt = r2.get('data', [{}])[0].get('cnt', 0)
    print(f"  daily_basic rows since 2026-05-01: {db_cnt}")
    
    # Build data
    candidates, ts_codes = build_candidates()
    db_data = fetch_daily_basic(ts_codes)
    fina_data = fetch_fina_indicator(ts_codes)
    all_prices = fetch_forward_prices(ts_codes)
    
    print(f"\n{'='*60}")
    print(f"Data Summary")
    print(f"{'='*60}")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Daily Basic: {len(db_data)}")
    print(f"  Financial Indicators: {len(fina_data)}")
    print(f"  Price rows: {len(all_prices)}")
    
    # Signal cutoff: need at least 5D forward data
    signal_end = "2026-05-06"  # 5 trading days before end
    
    # ===== COMBO DEFINITIONS =====
    combos = [
        {
            'id': 'C1',
            'name': 'C1-PE≤8+PB≤1+dv≥4%+底20%+VR≥1.0+振幅≥5%+CM≤50亿',
            'params': {
                'pe_max': 8, 'pb_max': 1, 'dv_min': 4, 'pos_max': 20,
                'vr_min': 1.0, 'amp_min': 5, 'cm_max_wan': 500000
            }
        },
        {
            'id': 'C2',
            'name': 'C2-净利增长≥10%+PE≤30+底20%+VR≥1.3+振幅≥5%+CM≤100亿',
            'params': {
                'netprofit_yoy_min': 10, 'pe_max': 30, 'pos_max': 20,
                'vr_min': 1.3, 'amp_min': 5, 'cm_max_wan': 1000000
            }
        },
        {
            'id': 'C3',
            'name': 'C3-np_yoy≥5%+tr_yoy≥5%+底20%+VR≥1.3+振幅≥5%+CM≤50亿',
            'params': {
                'netprofit_yoy_min': 5, 'tr_yoy_min': 5, 'pos_max': 20,
                'vr_min': 1.3, 'amp_min': 5, 'cm_max_wan': 500000
            }
        },
        {
            'id': 'C4',
            'name': 'C4-dv≥3%+PE≤15+PB≤2+底30%+VR≥1.2+振幅≥6%+CM≤50亿',
            'params': {
                'dv_min': 3, 'pe_max': 15, 'pb_max': 2, 'pos_max': 30,
                'vr_min': 1.2, 'amp_min': 6, 'cm_max_wan': 500000
            }
        },
        {
            'id': 'C5',
            'name': 'C5-np_yoy≥10%+前日跌+今日涨≥2%+振幅≥5%+CM≤30亿',
            'params': {
                'netprofit_yoy_min': 10, 'prev_down': True, 'pct_chg_min': 2,
                'amp_min': 5, 'cm_max_wan': 300000
            }
        },
    ]
    
    # ===== APPLY FILTERS =====
    results = []
    
    for combo in combos:
        combo_name = combo['name']
        p = combo['params']
        print(f"\n{'='*60}")
        print(f"Combo: {combo_name}")
        print(f"{'='*60}")
        
        signals = []
        skipped_pos = 0
        skipped_amp = 0
        skipped_vr = 0
        skipped_db = 0
        skipped_fina = 0
        skipped_pct = 0
        
        # Build indexed data for faster lookup
        # Already have candidates, db_data, fina_data
        
        for (code, date), row in candidates.items():
            if date >= signal_end:
                continue
            
            k = (code, date)
            db_row = db_data.get(k, {})
            fina = fina_data.get(code, {})
            
            # Get all needed values (with defaults)
            pos = row.get('pos_20d', 999)
            amp = row.get('amplitude', 0) or 0
            vr = row.get('vol_ratio', 0) or 0
            pct = row.get('pct_chg', 0) or 0
            
            pe = db_row.get('pe')
            pb = db_row.get('pb')
            dv = db_row.get('dv_ratio')
            cm = db_row.get('circ_mv')  # in 万元
            
            ny = fina.get('netprofit_yoy')
            tr = fina.get('tr_yoy')
            
            # Apply C1 filter
            if combo['id'] == 'C1':
                # PE≤8 + PB≤1 + dv≥4% + 底20% + VR≥1.0 + 振幅≥5% + CM≤50亿
                if pos > 20: skipped_pos += 1; continue
                if amp < 5: skipped_amp += 1; continue
                if vr < 1.0: skipped_vr += 1; continue
                if not pe or pe <= 0 or pe > 8: skipped_db += 1; continue
                if not pb or pb <= 0 or pb > 1: skipped_db += 1; continue
                if not dv or dv < 4: skipped_db += 1; continue
                if not cm or cm > 500000: skipped_db += 1; continue
            
            # Apply C2 filter
            elif combo['id'] == 'C2':
                # netprofit_yoy≥10% + PE≤30 + 底20% + VR≥1.3 + 振幅≥5% + CM≤100亿
                if pos > 20: skipped_pos += 1; continue
                if amp < 5: skipped_amp += 1; continue
                if vr < 1.3: skipped_vr += 1; continue
                if not pe or pe <= 0 or pe > 30: skipped_db += 1; continue
                if not cm or cm > 1000000: skipped_db += 1; continue
                if not ny or ny < 10: skipped_fina += 1; continue
            
            # Apply C3 filter
            elif combo['id'] == 'C3':
                # np_yoy≥5% + tr_yoy≥5% + 底20% + VR≥1.3 + 振幅≥5% + CM≤50亿
                if pos > 20: skipped_pos += 1; continue
                if amp < 5: skipped_amp += 1; continue
                if vr < 1.3: skipped_vr += 1; continue
                if not cm or cm > 500000: skipped_db += 1; continue
                if not ny or ny < 5: skipped_fina += 1; continue
                if not tr or tr < 5: skipped_fina += 1; continue
            
            # Apply C4 filter
            elif combo['id'] == 'C4':
                # dv≥3% + PE≤15 + PB≤2 + 底30% + VR≥1.2 + 振幅≥6% + CM≤50亿
                if pos > 30: skipped_pos += 1; continue
                if amp < 6: skipped_amp += 1; continue
                if vr < 1.2: skipped_vr += 1; continue
                if not pe or pe <= 0 or pe > 15: skipped_db += 1; continue
                if not pb or pb <= 0 or pb > 2: skipped_db += 1; continue
                if not dv or dv < 3: skipped_db += 1; continue
                if not cm or cm > 500000: skipped_db += 1; continue
            
            # Apply C5 filter
            elif combo['id'] == 'C5':
                # np_yoy≥10% + 前日跌 + 今日涨≥2% + 振幅≥5% + CM≤30亿
                if amp < 5: skipped_amp += 1; continue
                if not cm or cm > 300000: skipped_db += 1; continue
                if not ny or ny < 10: skipped_fina += 1; continue
                # 前日跌: prev_day pct_chg < 0
                # We need to look up previous day's pct_chg
                # Use the candidates data to find previous day
                if pct < 2: skipped_pct += 1; continue
                # Find prev day data
                prev_date = None
                all_dates = sorted([d for (c, d) in candidates.keys() if c == code])
                if date in all_dates:
                    idx = all_dates.index(date)
                    if idx > 0:
                        prev_date = all_dates[idx - 1]
                        prev_row = candidates.get((code, prev_date), {})
                        prev_pct = prev_row.get('pct_chg', 0) or 0
                        if prev_pct >= 0:  # 前日没跌
                            skipped_pct += 1
                            continue
                    else:
                        skipped_pct += 1
                        continue
                else:
                    skipped_pct += 1
                    continue
            
            # Signal passed all filters
            signals.append({
                'ts_code': code,
                'trade_date': date,
                'close': row['close'],
                'amplitude': amp,
                'pos_20d': pos,
                'vol_ratio': vr,
                'pct_chg': pct,
                'circ_mv': cm,
                'pe': pe,
                'pb': pb,
                'dv_ratio': dv,
                'netprofit_yoy': ny,
                'tr_yoy': tr,
            })
        
        print(f"  Signals after filter: {len(signals)}")
        print(f"  Skipped: pos={skipped_pos}, amp={skipped_amp}, vr={skipped_vr}, "
              f"db={skipped_db}, fina={skipped_fina}, pct={skipped_pct}")
        
        if len(signals) == 0:
            results.append({
                'name': combo_name,
                'hash': combo_hash(p),
                'signal_count': 0,
                'n_5d': 0,
                'win_rate_5d': 0,
                'ret_5d': 0,
                'ret_10d': 0,
                'ret_20d': 0,
                'sharpe_5d': 0,
                'status': '❌ 零信号'
            })
            continue
        
        # Compute forward returns
        forward_results = compute_forward_returns(signals, all_prices)
        stats = compute_stats(forward_results)
        
        # Determine pass/fail
        wr_5d = stats.get('wr_5d', 0)
        ret_5d = stats.get('ret_5d', 0)
        n = stats.get('signal_count', 0)
        n_5d = sum(1 for r in forward_results if r.get('ret_5d') is not None)
        
        passed = wr_5d >= 52 and ret_5d >= 3 and n_5d >= 200
        
        result = {
            'name': combo_name,
            'hash': combo_hash(p),
            'signal_count': n,
            'n_5d': n_5d,
            'win_rate_5d': round(wr_5d, 2),
            'ret_5d': round(ret_5d, 2),
            'ret_10d': round(stats.get('ret_10d', 0), 2),
            'ret_20d': round(stats.get('ret_20d', 0), 2),
            'sharpe_5d': round(stats.get('sharpe_5d', 0), 3),
            'status': '✅' if passed else (
                '⚠️ 不足' if n_5d >= 200 else '❌ 信号不足'
            )
        }
        results.append(result)
        
        print(f"  N={n}, N5d={n_5d}, WR5d={wr_5d:.1f}%, R5={ret_5d:.2f}%, "
              f"R10={stats.get('ret_10d',0):.2f}%, R20={stats.get('ret_20d',0):.2f}%, "
              f"Sharpe={stats.get('sharpe_5d',0):.3f}, Status={result['status']}")
    
    # ===== REPORT =====
    print(f"\n{'='*90}")
    print(f"📊 T5 基本面估值流派 — 5组参数回测 ({datetime.now() - t0})")
    print(f"{'='*90}")
    print(f"{'名称':<38} {'Sig':>6} {'N5d':>5} {'WR5d':>7} {'R5%':>8} {'R10%':>8} {'R20%':>8} {'Sharpe':>8} {'状态':<10}")
    print(f"{'-'*98}")
    
    for r in results:
        st = r['status']
        print(f"{r['name']:<38} {r['signal_count']:>6} {r['n_5d']:>5} "
              f"{r['win_rate_5d']:>6.1f}% {r['ret_5d']:>7.2f}% "
              f"{r['ret_10d']:>7.2f}% {r['ret_20d']:>7.2f}% "
              f"{r['sharpe_5d']:>7.3f}  {st:<10}")
    
    # Determine best
    passed = [r for r in results if r['status'] == '✅']
    if passed:
        best = max(passed, key=lambda x: x['ret_5d'])
        print(f"\n🏆 最佳通过: {best['name']}")
        print(f"   R5={best['ret_5d']}%, WR={best['win_rate_5d']}%, N={best['signal_count']}, Sharpe={best['sharpe_5d']}")
    
    best_all = max(results, key=lambda x: x.get('ret_5d', 0))
    print(f"\n📌 最佳(全部): {best_all['name']}")
    print(f"   R5={best_all['ret_5d']}%, WR={best_all['win_rate_5d']}%, N={best_all['signal_count']}")
    
    # Save to JSON - both debug results and final output format
    output = {
        'analyst': 'T5',
        'iteration': 'final',
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'start_date': START_DATE,
        'end_date': END_DATE,
        'results': results
    }
    
    # Save full results
    os.makedirs('logs/t5', exist_ok=True)
    with open('logs/t5/results_T5.json', 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Full results saved to logs/t5/results_T5.json")
    
    # Save final output format
    combos_output = []
    for r in results:
        combos_output.append({
            'name': r['name'],
            'hash': r['hash'],
            'signal_count': r['signal_count'],
            'n_5d': r['n_5d'],
            'win_rate_5d': r['win_rate_5d'],
            'ret_5d': r['ret_5d'],
            'ret_10d': r['ret_10d'],
            'ret_20d': r['ret_20d'],
            'sharpe_5d': r['sharpe_5d'],
            'status': r['status']
        })
    
    final_output = {
        'analyst': 'T5',
        'combos': combos_output
    }
    
    with open('/tmp/t5_final_results.json', 'w') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    print(f"✅ Final output saved to /tmp/t5_final_results.json")
    
    # Also save to kanban reports dir
    reports_dir = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/kanban/a-stock-research/reports'
    if os.path.exists(reports_dir):
        with open(f'{reports_dir}/t5_final_results.json', 'w') as f:
            json.dump(final_output, f, ensure_ascii=False, indent=2)
        print(f"✅ Report saved to {reports_dir}/t5_final_results.json")
    
    return results

if __name__ == '__main__':
    run()
