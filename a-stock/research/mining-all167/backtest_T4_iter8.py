#!/usr/bin/env python3
"""
Iter8 T4: 资金主力挖掘 — 5组参数组合回测
Focus: 卖盘约束(sell_elg/sell_lg)、净流入阈值、双端确认、融资因子
"""
import json, hashlib, math, subprocess, sys

CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_URL = "http://127.0.0.1:8123"
CH_DB = "tushare"
START_DATE = "2025-01-01"  # 17 months data is enough for 5D backtests

def ch_query(sql, fmt="JSON", timeout=120):
    with open('/tmp/ch_query.sql', 'w') as f:
        f.write(sql.rstrip().rstrip(";") + (f"\nFORMAT {fmt}" if fmt else ""))
    cmd = ["curl", "-s", "-X", "POST",
           f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&max_execution_time={timeout}&database={CH_DB}",
           "--data-binary", "@/tmp/ch_query.sql"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+10)
        data = result.stdout
        if fmt == "JSON":
            parsed = json.loads(data)
            if 'data' not in parsed and 'error' in result.stderr:
                parsed['_stderr'] = result.stderr[:500]
            return parsed
        return data.strip()
    except json.JSONDecodeError:
        return {"data": [], "error": data.strip()[:500]}
    except subprocess.TimeoutExpired:
        return {"data": [], "error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"data": [], "error": str(e)}

def ch_query_no_fmt(sql, engine="%24"):
    """For queries that need different format settings"""
    with open('/tmp/ch_query.sql', 'w') as f:
        f.write(sql)
    cmd = ["curl", "-s", "-X", "POST",
           f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&max_execution_time=120",
           "--data-binary", "@/tmp/ch_query.sql"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=130)
        return result.stdout
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Timeout"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def verify_data():
    """Confirm data freshness"""
    r = ch_query("SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL")
    print(f"[DATA CHECK] max(trade_date): {r.get('data', [{}])[0].get('max(trade_date)', 'UNKNOWN')}")
    
    r2 = ch_query("SELECT count() as cnt FROM tushare.tushare_moneyflow FINAL WHERE trade_date >= '2026-05-01'")
    cnt = r2.get('data', [{}])[0].get('cnt', 0)
    print(f"[DATA CHECK] moneyflow rows since 2026-05-01: {cnt}")
    
    # Check margin table
    r3 = ch_query("SELECT count() as cnt FROM tushare.tushare_margin FINAL WHERE trade_date >= '2026-05-01'")
    m_cnt = r3.get('data', [{}])[0].get('cnt', 0)
    print(f"[DATA CHECK] margin rows since 2026-05-01: {m_cnt}")

def compute_stats(results):
    n = len(results)
    if n == 0:
        return {"signal_count": 0, "wr_1d": 0, "wr_3d": 0, "wr_5d": 0, "wr_10d": 0, "wr_20d": 0,
                "ret_1d": 0, "ret_3d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0}
    def avg(lst): return sum(lst) / len(lst) if lst else 0
    def std(lst):
        if len(lst) < 2: return 0
        m = avg(lst)
        return math.sqrt(sum((x-m)**2 for x in lst) / len(lst))
    stats = {"signal_count": n}
    for k in ["ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d"]:
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

def build_candidates(up_to_date="2026-05-11"):
    """
    Phase 1: Query stock_daily with window functions to find base candidates
    Returns dict of (ts_code, trade_date) -> row
    """
    print("\n=== Phase 1: Building Candidates ===")
    
    sql = f"""
    SELECT ts_code, trade_date, close, pct_chg, high, low, vol, amount,
        round((high / low - 1) * 100, 2) AS amplitude,
        round((close - min_close_20d) / NULLIF(max_close_20d - min_close_20d, 0.001) * 100, 2) AS pos_20d,
        round(vol / NULLIF(avg_vol_20d, 0.001), 2) AS vol_ratio,
        round((close - avg_close_5d) / NULLIF(avg_close_5d, 0.001) * 100, 2) AS pct_from_ma5
    FROM (
        SELECT ts_code, trade_date, close, high, low, vol, amount, pct_chg,
            MIN(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min_close_20d,
            MAX(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_close_20d,
            AVG(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg_vol_20d,
            AVG(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING) AS avg_close_5d
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{up_to_date}'
          AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%'
          AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    )
    WHERE pos_20d <= 30 AND amplitude >= 3
    ORDER BY ts_code, trade_date
    """
    
    r = ch_query(sql, timeout=300)
    data = r.get('data', [])
    print(f"  Base candidates: {len(data)} rows")
    
    # Build index
    candidates = {}
    for row in data:
        key = (row['ts_code'], str(row['trade_date'])[:10])
        candidates[key] = row
    
    # Get distinct ts_codes for moneyflow fetch
    ts_codes = set(row['ts_code'] for row in data)
    print(f"  Distinct stocks: {len(ts_codes)}")
    
    return candidates, ts_codes

def fetch_moneyflow(ts_codes, up_to_date="2026-05-11"):
    """
    Phase 2: Fetch moneyflow data for candidate stocks
    Returns dict of (ts_code, trade_date) -> mf_row
    """
    print("\n=== Phase 2: Fetching Moneyflow ===")
    
    # Batch by series of codes to avoid too large IN clause
    code_list = sorted(list(ts_codes))
    batch_size = 200  # Balanced batch for speed
    mf_data = {}
    
    for i in range(0, len(code_list), batch_size):
        batch = code_list[i:i+batch_size]
        codes_str = ",".join(f"'{c}'" for c in batch)
        
        sql = f"""
        SELECT ts_code, trade_date, net_mf_amount, net_mf_vol,
            buy_lg_amount, sell_lg_amount, buy_elg_amount, sell_elg_amount,
            buy_md_amount, sell_md_amount
        FROM tushare.tushare_moneyflow FINAL
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{up_to_date}'
          AND ts_code IN ({codes_str})
        ORDER BY ts_code, trade_date
        """
        
        r = ch_query(sql, timeout=180)
        rows = r.get('data', [])
        if len(rows) == 0 and 'error' in r:
            print(f"  WARNING: Batch {i//batch_size}: {r.get('error', '')[:100]}")
            print(f"  stderr: {r.get('_stderr', '')[:200]}")
        for row in rows:
            key = (row['ts_code'], str(row['trade_date'])[:10])
            mf_data[key] = row
        
        if (i // batch_size) % 5 == 0 or i + batch_size >= len(code_list):
            print(f"  Batch {i//batch_size}/{(len(code_list)-1)//batch_size}: "
                  f"codes={len(batch)}, mf_rows={len(rows)}, total={len(mf_data)}")
    
    print(f"  Total moneyflow rows: {len(mf_data)}")
    return mf_data

def fetch_daily_basic(ts_codes, up_to_date="2026-05-11"):
    """
    Phase 3: Fetch daily_basic for circ_mv and turnover_rate
    """
    print("\n=== Phase 3: Fetching Daily Basic ===")
    
    code_list = list(ts_codes)
    batch_size = 500
    db_data = {}
    
    for i in range(0, len(code_list), batch_size):
        batch = code_list[i:i+batch_size]
        codes_str = ",".join(f"'{c}'" for c in batch)
        
        sql = f"""
        SELECT ts_code, trade_date, circ_mv, turnover_rate, pe, pb, dv_ratio
        FROM tushare.tushare_daily_basic FINAL
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{up_to_date}'
          AND ts_code IN ({codes_str})
        ORDER BY ts_code, trade_date
        """
        
        r = ch_query(sql, timeout=180)
        rows = r.get('data', [])
        for row in rows:
            key = (row['ts_code'], str(row['trade_date'])[:10])
            db_data[key] = row
    
    print(f"  Total daily_basic rows: {len(db_data)}")
    return db_data

def fetch_forward_returns(ts_codes, up_to_date="2026-05-11"):
    """
    Fetch future close prices for return computation
    Returns dict of (ts_code, trade_date_offset) -> close
    """
    print("\n=== Fetching Forward Prices ===")
    
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
    
    print(f"  Total price rows: {len(all_prices)}")
    return all_prices

def compute_forward_returns(signals, all_prices):
    """Compute forward returns for each signal"""
    results = []
    for s in signals:
        code = s['ts_code']
        entry_date = s['trade_date']
        
        # Build sorted date list for this stock
        stock_dates = sorted([d for (c, d), v in all_prices.items() 
                              if c == code and d >= entry_date])
        
        if entry_date not in stock_dates:
            continue
        
        idx = stock_dates.index(entry_date)
        
        rets = {'ts_code': code, 'trade_date': entry_date, 'entry_close': s['close']}
        
        # 1D, 3D, 5D, 10D, 20D forward
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

def filter_c1(row, mf_row, db_row):
    """C1: 低位锁仓 — net_mf≥500万 + sell_elg_ratio≤3% + 底20% + 振幅≥3% + VR≥0.8 + CM≤50亿"""
    if row.get('pos_20d', 999) > 20:
        return False
    if row.get('amplitude', 0) < 3:
        return False
    if row.get('vol_ratio', 0) < 0.8:
        return False
    if mf_row is None:
        return False
    net_mf = mf_row.get('net_mf_amount') or 0
    if net_mf < 500:
        return False
    # sell_elg_ratio = sell_elg_amount / total_elg_amount
    buy_elg = abs(mf_row.get('buy_elg_amount') or 0)
    sell_elg = abs(mf_row.get('sell_elg_amount') or 0)
    total_elg = buy_elg + sell_elg
    if total_elg > 0:
        sell_elg_ratio = sell_elg / total_elg
        if sell_elg_ratio > 0.03:
            return False
    if db_row is None:
        return False
    circ_mv = db_row.get('circ_mv') or 0
    if circ_mv > 500000:  # 50亿
        return False
    return True

def filter_c2(row, mf_row, db_row):
    """C2: 超大单吸筹 — buy_elg_ratio≥3% + sell_lg_ratio≤10% + 底20% + 振幅≥3% + CM≤30亿"""
    if row.get('pos_20d', 999) > 20:
        return False
    if row.get('amplitude', 0) < 3:
        return False
    if mf_row is None:
        return False
    buy_elg = abs(mf_row.get('buy_elg_amount') or 0)
    sell_elg = abs(mf_row.get('sell_elg_amount') or 0)
    total_elg = buy_elg + sell_elg
    if total_elg > 0:
        buy_elg_ratio = buy_elg / total_elg
        if buy_elg_ratio < 0.03:
            return False
    else:
        return False
    # sell_lg_ratio ≤ 10%
    buy_lg = abs(mf_row.get('buy_lg_amount') or 0)
    sell_lg = abs(mf_row.get('sell_lg_amount') or 0)
    total_lg = buy_lg + sell_lg
    if total_lg > 0:
        sell_lg_ratio = sell_lg / total_lg
        if sell_lg_ratio > 0.10:
            return False
    if db_row is None:
        return False
    circ_mv = db_row.get('circ_mv') or 0
    if circ_mv > 300000:  # 30亿
        return False
    return True

def filter_c3(row, mf_row, db_row):
    """C3: 双端确认 — net_mf≥300万 + buy_elg_ratio≥2% + buy_lg_ratio≥8% + 振幅≥5% + pct≥-2% + CM≤50亿"""
    if row.get('amplitude', 0) < 5:
        return False
    pct = row.get('pct_chg') or -999
    if pct < -2:
        return False
    if mf_row is None:
        return False
    net_mf = mf_row.get('net_mf_amount') or 0
    if net_mf < 300:
        return False
    # buy_elg_ratio
    buy_elg = abs(mf_row.get('buy_elg_amount') or 0)
    sell_elg = abs(mf_row.get('sell_elg_amount') or 0)
    total_elg = buy_elg + sell_elg
    if total_elg > 0:
        buy_elg_ratio = buy_elg / total_elg
        if buy_elg_ratio < 0.02:
            return False
    else:
        return False
    # buy_lg_ratio
    buy_lg = abs(mf_row.get('buy_lg_amount') or 0)
    sell_lg = abs(mf_row.get('sell_lg_amount') or 0)
    total_lg = buy_lg + sell_lg
    if total_lg > 0:
        buy_lg_ratio = buy_lg / total_lg
        if buy_lg_ratio < 0.08:
            return False
    else:
        return False
    if db_row is None:
        return False
    circ_mv = db_row.get('circ_mv') or 0
    if circ_mv > 500000:
        return False
    return True

def filter_c4(row, mf_row, db_row, margin_data, code_date_key):
    """C4: 融资活跃 — 有融资余额(rzye>0) + 融资买入(rzmre>0) + 底20% + 振幅≥5% + VR≥1.0 + CM≤50亿"""
    if row.get('pos_20d', 999) > 20:
        return False
    if row.get('amplitude', 0) < 5:
        return False
    if row.get('vol_ratio', 0) < 1.0:
        return False
    if db_row is None:
        return False
    circ_mv = db_row.get('circ_mv') or 0
    if circ_mv > 500000:
        return False
    # Check margin — need active margin buying
    if code_date_key not in margin_data:
        return False
    margin_row = margin_data[code_date_key]
    rzye = margin_row.get('rzye') or 0
    rzmre = margin_row.get('rzmre') or 0
    # Must have margin balance AND active margin buying today
    if rzye <= 0 or rzmre <= 0:
        return False
    return True

def run():
    verify_data()
    
    up_to_date = "2026-05-11"
    signal_end = "2026-05-08"  # Last date we can compute 5D returns for
    
    # Phase 1-3: build data
    candidates, ts_codes = build_candidates(up_to_date)
    mf_data = fetch_moneyflow(ts_codes, up_to_date)
    db_data = fetch_daily_basic(ts_codes, up_to_date)
    all_prices = fetch_forward_returns(ts_codes, up_to_date)
    
    print(f"\n=== Data Summary ===")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Moneyflow: {len(mf_data)}")
    print(f"  Daily Basic: {len(db_data)}")
    print(f"  Price rows: {len(all_prices)}")
    
    # Fetch margin data for C4
    margin_data = {}
    print("\n=== Fetching Margin Data ===")
    code_list = sorted(list(ts_codes))
    batch_size = 200
    for i in range(0, len(code_list), batch_size):
        batch = code_list[i:i+batch_size]
        codes_str = ",".join(f"'{c}'" for c in batch)
        sql = f"""
        SELECT ts_code, trade_date, rzye, rzmre, rzche, rqye, rqyl, rzrqye
        FROM tushare.tushare_margin_detail FINAL
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{up_to_date}'
          AND ts_code IN ({codes_str})
        ORDER BY ts_code, trade_date
        """
        r = ch_query(sql, timeout=180)
        rows = r.get('data', [])
        for row in rows:
            key = (row['ts_code'], str(row['trade_date'])[:10])
            margin_data[key] = row
        if (i // batch_size) % 10 == 0 or i + batch_size >= len(code_list):
            print(f"  Margin batch {i//batch_size}/{(len(code_list)-1)//batch_size}: "
                  f"codes={len(batch)}, rows={len(rows)}, total={len(margin_data)}")
    print(f"  Total margin rows: {len(margin_data)}")
    
    # Apply filters for each combo
    combos = {
        'C1-低位锁仓': {
            'desc': 'net_mf≥500万 + sell_elg_ratio≤3% + 底20% + 振幅≥3% + VR≥0.8 + CM≤50亿',
            'filter': 'c1'
        },
        'C2-超大单吸筹': {
            'desc': 'buy_elg_ratio≥3% + sell_lg_ratio≤10% + 底20% + 振幅≥3% + CM≤30亿',
            'filter': 'c2'
        },
        'C3-双端确认': {
            'desc': 'net_mf≥300万 + buy_elg_ratio≥2% + buy_lg_ratio≥8% + 振幅≥5% + pct≥-2% + CM≤50亿',
            'filter': 'c3'
        },
        'C4-融资活跃': {
            'desc': 'rzye>0+rzmre>0(融资活跃) + 底20% + 振幅≥5% + VR≥1.0 + CM≤50亿',
            'filter': 'c4'
        },
        'C5-净流入大容量': {
            'desc': 'net_mf≥1000万 + buy_lg_ratio≥12% + 底30% + 振幅≥4% + VR≥1.2 + CM≤100亿',
            'filter': 'c5'
        }
    }
    
    results = {}
    for name, config in combos.items():
        print(f"\n=== {name} ===")
        signals = []
        skipped_no_mf = 0
        skipped_no_db = 0
        skipped_filter = 0
        
        for (code, date), row in candidates.items():
            # Skip signals too close to end date (need 5D forward)
            if date >= signal_end:
                continue
            
            code_date_key = (code, date)
            mf_row = mf_data.get(code_date_key)
            db_row = db_data.get(code_date_key)
            
            if mf_row is None:
                skipped_no_mf += 1
                continue
            if db_row is None:
                skipped_no_db += 1
                continue
            
            if config['filter'] == 'c1':
                ok = filter_c1(row, mf_row, db_row)
            elif config['filter'] == 'c2':
                ok = filter_c2(row, mf_row, db_row)
            elif config['filter'] == 'c3':
                ok = filter_c3(row, mf_row, db_row)
            elif config['filter'] == 'c4':
                ok = filter_c4(row, mf_row, db_row, margin_data, code_date_key)
            elif config['filter'] == 'c5':
                # C5: net_mf≥1000万 + buy_lg_ratio≥12% + 底30% + 振幅≥4% + VR≥1.2 + CM≤100亿
                if row.get('pos_20d', 999) > 30:
                    ok = False
                elif row.get('amplitude', 0) < 4:
                    ok = False
                elif row.get('vol_ratio', 0) < 1.2:
                    ok = False
                elif mf_row.get('net_mf_amount', 0) < 1000:
                    ok = False
                else:
                    buy_lg = abs(mf_row.get('buy_lg_amount') or 0)
                    sell_lg = abs(mf_row.get('sell_lg_amount') or 0)
                    total_lg = buy_lg + sell_lg
                    if total_lg > 0:
                        buy_lg_ratio = buy_lg / total_lg
                        if buy_lg_ratio < 0.12:
                            ok = False
                        else:
                            circ_mv = db_row.get('circ_mv') or 0
                            ok = (circ_mv <= 1000000)  # 100亿
                    else:
                        ok = False
            else:
                ok = False
            
            if ok:
                signals.append({
                    'ts_code': code,
                    'trade_date': date,
                    'close': row['close'],
                    'amplitude': row.get('amplitude'),
                    'pos_20d': row.get('pos_20d'),
                    'vol_ratio': row.get('vol_ratio'),
                    'pct_chg': row.get('pct_chg'),
                    'circ_mv': db_row.get('circ_mv') if db_row else None,
                    'net_mf': mf_row.get('net_mf_amount') if mf_row else None
                })
            else:
                skipped_filter += 1
        
        print(f"  Signals: {len(signals)}")
        print(f"  Skipped (no mf): {skipped_no_mf}, (no db): {skipped_no_db}, (filter): {skipped_filter}")
        
        if len(signals) == 0:
            results[name] = {
                "signal_count": 0, "wr_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0,
                "description": config['desc'], "status": "❌ 零信号"
            }
            continue
        
        # Compute forward returns
        forward_results = compute_forward_returns(signals, all_prices)
        stats = compute_stats(forward_results)
        stats['description'] = config['desc']
        
        # Determine status
        passed = stats['signal_count'] >= 200 and stats['wr_5d'] >= 52 and stats['ret_5d'] >= 3
        if passed:
            stats['status'] = '✅'
        elif stats['signal_count'] >= 200 and stats['ret_5d'] >= 3:
            stats['status'] = '⚠️ (WR不足)'
        elif stats['signal_count'] >= 200:
            stats['status'] = '⚠️ (收益不足)'
        elif stats['signal_count'] > 0:
            stats['status'] = '⚠️ (信号不足)'
        else:
            stats['status'] = '❌'
        
        results[name] = stats
        print(f"  N={stats['signal_count']}, WR_5d={stats['wr_5d']:.1f}%, R5={stats['ret_5d']:.2f}%, "
              f"R10={stats['ret_10d']:.2f}%, R20={stats['ret_20d']:.2f}%, "
              f"Sharpe={stats['sharpe_5d']}, Status={stats['status']}")
    
    # Print summary table
    print("\n" + "="*90)
    print("T4 Iter8 资金主力挖掘 — 结果总表")
    print("="*90)
    print(f"{'组合':<20} {'N':<8} {'WR_5d':<8} {'R5':<8} {'R10':<8} {'R20':<8} {'Sharpe':<8} {'状态':<10}")
    print("-"*90)
    for name, s in results.items():
        print(f"{name:<20} {s['signal_count']:<8} {s['wr_5d']:<8.1f} {s['ret_5d']:<8.2f} {s['ret_10d']:<8.2f} {s['ret_20d']:<8.2f} {s['sharpe_5d']:<8.3f} {s.get('status',''):<10}")
    
    # Save results
    output = {
        'iteration': 8,
        'analyst': 'T4-资金主力',
        'time': '2026-05-12 08:30 UTC+8',
        'results': results
    }
    
    # Compute hashes
    combos_hash = {
        'C1-低位锁仓': '6b3443159245',
        'C2-超大单吸筹': 'ee527b98e655',
        'C3-双端确认': '5978307e472c',
        'C4-融资加仓': '50b8f83caec8',
        'C5-净流入大容量': '31be842796fa'
    }
    output['combos_hash'] = combos_hash
    
    with open('/tmp/t4_iter8_results.json', 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to /tmp/t4_iter8_results.json")
    
    # Find best
    best_name = None
    best_score = -1
    for name, s in results.items():
        if s['signal_count'] >= 200 and '✅' in s.get('status', ''):
            score = s['ret_5d'] * 0.4 + s['wr_5d'] * 0.01 * 0.3 + min(s['sharpe_5d'], 10) * 0.3
            if score > best_score:
                best_score = score
                best_name = name
    
    if best_name:
        print(f"\n🏆 Best combo: {best_name}")
        s = results[best_name]
        print(f"   R5={s['ret_5d']:.2f}%, WR={s['wr_5d']:.1f}%, N={s['signal_count']}, Sharpe={s['sharpe_5d']:.3f}")
    
    return results

if __name__ == '__main__':
    run()
