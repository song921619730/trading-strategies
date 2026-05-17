#!/usr/bin/env python3
"""
T5 基本面估值流派 — Iter23 5组参数组合回测
聚焦: SPX+破净高息、高ROE高息SPX、纯高股息放量、增长放量底30%、SPX深价值微跌
"""
import json, hashlib, math, subprocess, sys, os
from datetime import datetime

CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_URL = "http://127.0.0.1:8123"
CH_DB = "tushare"
START_DATE = "2023-01-01"  # full history
END_DATE = "2026-05-12"    # max available
# Signal cutoff: need at least 5D forward data
SIGNAL_END = "2026-05-06"  # 5 trading days before end of data

def ch_query(sql, fmt="JSON", timeout=180):
    with open('/tmp/ch_query_t5_i23.sql', 'w') as f:
        f.write(sql.rstrip().rstrip(";") + (f"\nFORMAT {fmt}" if fmt else ""))
    cmd = ["curl", "-s", "-X", "POST",
           f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&max_execution_time={timeout}&database={CH_DB}",
           "--data-binary", "@/tmp/ch_query_t5_i23.sql"]
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

def build_candidates():
    """Phase 1: SQL window functions for base candidates with 60日 position"""
    print(f"\n{'='*60}")
    print(f"Phase 1: Building Candidates (up to {SIGNAL_END})")
    print(f"{'='*60}")
    
    sql = f"""
    SELECT ts_code, trade_date, close, pct_chg, high, low, vol, amount,
        round((high / low - 1) * 100, 2) AS amplitude,
        round((close - min_low_20d) / NULLIF(max_high_20d - min_low_20d, 0.001) * 100, 2) AS pos_20d,
        round((close - min_low_60d) / NULLIF(max_high_60d - min_low_60d, 0.001) * 100, 2) AS pos_60d,
        round(vol / NULLIF(avg_vol_20d, 0.001), 2) AS vol_ratio
    FROM (
        SELECT ts_code, trade_date, close, high, low, vol, amount, pct_chg,
            MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_low_20d,
            MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_high_20d,
            MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min_low_60d,
            MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max_high_60d,
            AVG(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg_vol_20d
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{SIGNAL_END}'
          AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%'
          AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    )
    WHERE amplitude >= 3
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

def fetch_daily_basic(ts_codes):
    """Phase 2: Fetch daily_basic for PE, PB, dv_ratio, circ_mv"""
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
        SELECT ts_code, trade_date, pe, pb, dv_ratio, circ_mv, pcf, total_mv
        FROM tushare.tushare_daily_basic FINAL
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{SIGNAL_END}'
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
    """Phase 3: Fetch fina_indicator for netprofit_yoy, roe"""
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
        SELECT ts_code, end_date, netprofit_yoy, tr_yoy, roe
        FROM tushare.tushare_fina_indicator FINAL
        WHERE ts_code IN ({codes_str})
        ORDER BY ts_code, end_date DESC
        """
        
        r = ch_query(sql, timeout=300)
        rows = r.get('data', [])
        for row in rows:
            code = row['ts_code']
            if code not in fina_data:
                fina_data[code] = {
                    'end_date': str(row['end_date'])[:10],
                    'netprofit_yoy': row.get('netprofit_yoy'),
                    'tr_yoy': row.get('tr_yoy'),
                    'roe': row.get('roe'),
                }
        
        if (i // batch_size) % 5 == 0 or i + batch_size >= len(code_list):
            print(f"  Batch {i//batch_size}/{(len(code_list)-1)//batch_size}: "
                  f"codes={len(batch)}, fina_rows={len(rows)}, unique_stocks={len(fina_data)}")
    
    print(f"  Total fina_indicator records (latest per stock): {len(fina_data)}")
    return fina_data

def fetch_spx_data():
    """Fetch SPX daily returns"""
    print(f"\nPhase SPX: Fetching SPX data")
    sql = f"""
    SELECT trade_date, pct_chg 
    FROM tushare.tushare_index_global FINAL
    WHERE ts_code = 'SPX' AND trade_date >= '{START_DATE}' AND trade_date <= '{SIGNAL_END}'
    ORDER BY trade_date
    """
    r = ch_query(sql)
    spx = {}
    for row in r.get('data', []):
        spx[str(row['trade_date'])[:10]] = row.get('pct_chg', 0) or 0
    print(f"  SPX rows: {len(spx)}")
    return spx

def fetch_forward_prices(ts_codes):
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
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
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
    """Compute forward returns for each signal"""
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
            'entry_close': s.get('close'),
            'amplitude': s.get('amplitude'),
            'pos_20d': s.get('pos_20d'),
            'pos_60d': s.get('pos_60d'),
            'vol_ratio': s.get('vol_ratio'),
            'pct_chg': s.get('pct_chg'),
            'circ_mv': s.get('circ_mv'),
            'pe': s.get('pe'),
            'pb': s.get('pb'),
            'dv_ratio': s.get('dv_ratio'),
            'netprofit_yoy': s.get('netprofit_yoy'),
            'roe': s.get('roe'),
        }
        
        for offset, key in [(1, 'ret_1d'), (3, 'ret_3d'), (5, 'ret_5d'),
                            (10, 'ret_10d'), (20, 'ret_20d')]:
            if idx + offset < len(stock_dates):
                future_date = stock_dates[idx + offset]
                future_close = all_prices.get((code, future_date))
                if future_close and s.get('close') and s['close'] > 0:
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
    
    # Data freshness
    print("=== Data Freshness Check ===")
    r = ch_query("SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL")
    max_date = r.get('data', [{}])[0].get('max(trade_date)', 'UNKNOWN')
    print(f"  max(trade_date): {max_date}")
    
    # Build data
    candidates, ts_codes = build_candidates()
    db_data = fetch_daily_basic(ts_codes)
    fina_data = fetch_fina_indicator(ts_codes)
    spx_data = fetch_spx_data()
    all_prices = fetch_forward_prices(ts_codes)
    
    print(f"\n{'='*60}")
    print(f"Data Summary")
    print(f"{'='*60}")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Daily Basic: {len(db_data)}")
    print(f"  Financial Indicators: {len(fina_data)}")
    print(f"  SPX rows: {len(spx_data)}")
    print(f"  Price rows: {len(all_prices)}")
    
    # ===== COMBO DEFINITIONS =====
    combos = [
        {
            'id': 'C1',
            'name': 'C1-SPX+破净高息60日深底: PB≤1+dv≥2%+CM≤50亿+60日底20%+VR≥1.0+SPX前日涨',
            'params': {
                'pb_max': 1, 'dv_min': 2, 'cm_max_wan': 500000,
                'pos_60d_max': 20, 'vr_min': 1.0, 'spx_prev_up': True
            },
            'desc': 'SPX宏观偏暖 + 破净(PB≤1) + 高股息(dv≥2%) + 60日深底 + 放量 + 微盘50亿'
        },
        {
            'id': 'C2',
            'name': 'C2-高ROE高股息SPX: ROE≥10%+dv≥2%+PE≤20+PB≤2+CM30-200亿+底20%+VR≥1.0+SPX',
            'params': {
                'roe_min': 10, 'dv_min': 2, 'pe_max': 20, 'pb_max': 2,
                'cm_min_wan': 300000, 'cm_max_wan': 2000000,
                'pos_max': 20, 'vr_min': 1.0, 'spx_prev_up': True
            },
            'desc': 'ROE≥10%(盈利能力) + 高股息 + 估值过滤(PE≤20+PB≤2) + SPX + 中大盘容量'
        },
        {
            'id': 'C3',
            'name': 'C3-纯高股息放量: dv≥3%+PE≤15+PB≤2+CM≤50亿+VR≥1.3+振幅≥6%（无位置过滤）',
            'params': {
                'dv_min': 3, 'pe_max': 15, 'pb_max': 2, 'cm_max_wan': 500000,
                'vr_min': 1.3, 'amp_min': 6
            },
            'desc': '纯高股息(dv≥3%) + 深价值(PE≤15+PB≤2) + 放量(VR≥1.3) + 无位置过滤 — 纯基本面+量价驱动'
        },
        {
            'id': 'C4',
            'name': 'C4-净利增长放量底30%容量版: np_yoy≥10%+PE≤30+CM≤100亿+底30%+VR≥1.2+振幅≥5%',
            'params': {
                'netprofit_yoy_min': 10, 'pe_max': 30, 'cm_max_wan': 1000000,
                'pos_max': 30, 'vr_min': 1.2, 'amp_min': 5
            },
            'desc': '净利润增长≥10%(成长因子) + PE≤30 + 底30%(宽松位置) + 放量 + 中大盘100亿'
        },
        {
            'id': 'C5',
            'name': 'C5-SPX深价值微跌: PE≤15+PB≤2+dv≥2%+CM≤50亿+SPX前日涨+pct≤-3%（无底过滤）',
            'params': {
                'pe_max': 15, 'pb_max': 2, 'dv_min': 2, 'cm_max_wan': 500000,
                'spx_prev_up': True, 'pct_chg_max': -3
            },
            'desc': 'SPX + 深价值(PE≤15+PB≤2+高股息) + 微跌≤-3%(安全边际) + 无底过滤 — 纯宏观+估值抄底'
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
        skipped_spx = 0
        skipped_roe = 0
        
        for (code, date), row in candidates.items():
            k = (code, date)
            db_row = db_data.get(k, {})
            fina = fina_data.get(code, {})
            
            # Get values
            pos_20d = row.get('pos_20d', 999) or 999
            pos_60d = row.get('pos_60d', 999) or 999
            amp = row.get('amplitude', 0) or 0
            vr = row.get('vol_ratio', 0) or 0
            pct = row.get('pct_chg', 0) or 0
            
            pe = db_row.get('pe')
            pb = db_row.get('pb')
            dv = db_row.get('dv_ratio')
            cm = db_row.get('circ_mv')  # in 万元
            
            ny = fina.get('netprofit_yoy')
            roe_val = fina.get('roe')
            
            # Check SPX condition (if needed)
            if p.get('spx_prev_up'):
                # Need SPX previous day > 0
                # Previous trading day lookup
                all_dates_sorted = sorted(list(spx_data.keys()))
                try:
                    date_idx = all_dates_sorted.index(date)
                except ValueError:
                    # date not in SPX data, find the most recent before it
                    spx_dates_before = [d for d in all_dates_sorted if d < date]
                    if not spx_dates_before:
                        skipped_spx += 1
                        continue
                    date_idx = all_dates_sorted.index(spx_dates_before[-1])
                prev_spx_date = all_dates_sorted[date_idx - 1] if date_idx > 0 else None
                if prev_spx_date is None or prev_spx_date not in spx_data:
                    skipped_spx += 1
                    continue
                spx_prev_chg = spx_data.get(prev_spx_date, 0) or 0
                if spx_prev_chg <= 0:
                    skipped_spx += 1
                    continue
            
            # Apply C1 filter: PB≤1 + dv≥2% + CM≤50亿 + 60日底20% + VR≥1.0 + SPX
            if combo['id'] == 'C1':
                if pos_60d > 20: skipped_pos += 1; continue
                if vr < 1.0: skipped_vr += 1; continue
                if not pb or pb <= 0 or pb > 1: skipped_db += 1; continue
                if not dv or dv < 2: skipped_db += 1; continue
                if not cm or cm > 500000: skipped_db += 1; continue
            
            # Apply C2 filter: ROE≥10% + dv≥2% + PE≤20 + PB≤2 + CM30-200亿 + 底20% + VR≥1.0 + SPX
            elif combo['id'] == 'C2':
                if pos_20d > 20: skipped_pos += 1; continue
                if vr < 1.0: skipped_vr += 1; continue
                if not pe or pe <= 0 or pe > 20: skipped_db += 1; continue
                if not pb or pb <= 0 or pb > 2: skipped_db += 1; continue
                if not dv or dv < 2: skipped_db += 1; continue
                if not cm or cm < 300000 or cm > 2000000: skipped_db += 1; continue
                if not roe_val or roe_val < 10: skipped_roe += 1; continue
            
            # Apply C3 filter: dv≥3% + PE≤15 + PB≤2 + CM≤50亿 + VR≥1.3 + 振幅≥6% (no position filter)
            elif combo['id'] == 'C3':
                if amp < 6: skipped_amp += 1; continue
                if vr < 1.3: skipped_vr += 1; continue
                if not pe or pe <= 0 or pe > 15: skipped_db += 1; continue
                if not pb or pb <= 0 or pb > 2: skipped_db += 1; continue
                if not dv or dv < 3: skipped_db += 1; continue
                if not cm or cm > 500000: skipped_db += 1; continue
            
            # Apply C4 filter: netprofit_yoy≥10% + PE≤30 + CM≤100亿 + 底30% + VR≥1.2 + 振幅≥5%
            elif combo['id'] == 'C4':
                if pos_20d > 30: skipped_pos += 1; continue
                if amp < 5: skipped_amp += 1; continue
                if vr < 1.2: skipped_vr += 1; continue
                if not pe or pe <= 0 or pe > 30: skipped_db += 1; continue
                if not cm or cm > 1000000: skipped_db += 1; continue
                if not ny or ny < 10: skipped_fina += 1; continue
            
            # Apply C5 filter: PE≤15 + PB≤2 + dv≥2% + CM≤50亿 + SPX + pct≤-3%
            elif combo['id'] == 'C5':
                if pct > -3: skipped_pct += 1; continue
                if not pe or pe <= 0 or pe > 15: skipped_db += 1; continue
                if not pb or pb <= 0 or pb > 2: skipped_db += 1; continue
                if not dv or dv < 2: skipped_db += 1; continue
                if not cm or cm > 500000: skipped_db += 1; continue
            
            # Signal passed
            signals.append({
                'ts_code': code,
                'trade_date': date,
                'close': row['close'],
                'amplitude': amp,
                'pos_20d': pos_20d,
                'pos_60d': pos_60d,
                'vol_ratio': vr,
                'pct_chg': pct,
                'circ_mv': cm,
                'pe': pe,
                'pb': pb,
                'dv_ratio': dv,
                'netprofit_yoy': ny,
                'roe': roe_val,
            })
        
        print(f"  Signals after filter: {len(signals)}")
        print(f"  Skipped: pos={skipped_pos}, amp={skipped_amp}, vr={skipped_vr}, "
              f"db={skipped_db}, fina={skipped_fina}, pct={skipped_pct}, spx={skipped_spx}, roe={skipped_roe}")
        
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
    elapsed = datetime.now() - t0
    print(f"\n{'='*90}")
    print(f"📊 T5 基本面估值流派 — Iter23 (5组参数回测, 用时{elapsed})")
    print(f"{'='*90}")
    print(f"{'名称':<60} {'Sig':>6} {'N5d':>5} {'WR5d':>7} {'R5%':>8} {'R10%':>8} {'R20%':>8} {'Sharpe':>8} {'状态':<10}")
    print(f"{'-'*120}")
    
    for r in results:
        st = r['status']
        print(f"{r['name'][:60]:<60} {r['signal_count']:>6} {r['n_5d']:>5} "
              f"{r['win_rate_5d']:>6.1f}% {r['ret_5d']:>7.2f}% "
              f"{r['ret_10d']:>7.2f}% {r['ret_20d']:>7.2f}% "
              f"{r['sharpe_5d']:>7.3f}  {st:<10}")
    
    # Determine best
    passed = [r for r in results if r['status'] == '✅']
    if passed:
        best = max(passed, key=lambda x: x['ret_5d'])
        print(f"\n🏆 最佳通过: {best['name'][:60]}")
        print(f"   R5={best['ret_5d']}%, WR={best['win_rate_5d']}%, N={best['signal_count']}, Sharpe={best['sharpe_5d']}")
    
    best_all = max(results, key=lambda x: x.get('ret_5d', 0))
    print(f"\n📌 最佳(全部): {best_all['name'][:60]}")
    print(f"   R5={best_all['ret_5d']}%, WR={best_all['win_rate_5d']}%, N={best_all['signal_count']}")
    
    # Save results
    output_dir = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_23'
    os.makedirs(output_dir, exist_ok=True)
    
    # Save final output
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
        'iteration': 23,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'start_date': START_DATE,
        'end_date': END_DATE,
        'signal_end': SIGNAL_END,
        'combos': combos_output,
        'best_pass': max([r for r in results if r['status'] == '✅'], key=lambda x: x['ret_5d']) if passed else None,
        'best_all': max(results, key=lambda x: x.get('ret_5d', 0))
    }
    
    with open(f'{output_dir}/t5_iter23_results.json', 'w') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Results saved to {output_dir}/t5_iter23_results.json")
    
    return results

if __name__ == '__main__':
    run()
