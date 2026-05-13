#!/usr/bin/env python3
"""
Iter18 T5 基本面估值流派 — 5组新参数组合回测
探索基本面因子的新维度组合
"""
import json, hashlib, math, subprocess, sys, os
from datetime import datetime, timedelta

# ── ClickHouse 连接 ──
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_URL = "http://127.0.0.1:8123"
CH_DB = "tushare"
START_DATE = "2023-01-01"
END_DATE = "2026-05-12"  # Latest trade date from T1 check

def ch_query(sql, fmt="JSON", timeout=300):
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
        return {"signal_count": 0, "n_5d": 0, "wr_5d": 0, "wr_10d": 0, "wr_20d": 0,
                "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0}
    def avg(lst): return sum(lst) / len(lst) if lst else 0
    def std(lst):
        if len(lst) < 2: return 0
        m = avg(lst)
        return math.sqrt(sum((x-m)**2 for x in lst) / len(lst))
    stats = {"signal_count": n}
    for k in ["ret_5d", "ret_10d", "ret_20d"]:
        vals = [r[k] for r in results if r[k] is not None]
        suffix = k.replace('ret_', '')
        stats[f"wr_{suffix}"] = round(sum(1 for v in vals if v > 0) / len(vals) * 100, 2) if vals else 0
        stats[k] = round(avg(vals) * 100, 4) if vals else 0
    key = "ret_5d"
    vals5 = [r[key] for r in results if r[key] is not None]
    stats["n_5d"] = len(vals5)
    if len(vals5) > 1:
        sd = std(vals5)
        stats["sharpe_5d"] = round((avg(vals5) / sd) * math.sqrt(252/5), 4) if sd > 0 else 0
    else:
        stats["sharpe_5d"] = 0
    return stats

def combo_hash(params):
    return hashlib.md5(json.dumps(sorted(params.items()), ensure_ascii=False).encode()).hexdigest()[:12]

def run():
    t0 = datetime.now()
    print(f"=== Iter18 T5 基本面估值回测 ===")
    print(f"Start: {t0}")
    print(f"Data range: {START_DATE} ~ {END_DATE}")

    # ── Phase 0: Data Freshness ──
    print(f"\n{'='*60}")
    print("Phase 0: Data Freshness Check")
    print(f"{'='*60}")
    r = ch_query("SELECT max(trade_date) AS max_dt FROM tushare.tushare_stock_daily FINAL")
    max_date = r.get('data', [{}])[0].get('max_dt', 'UNKNOWN')
    print(f"  max(trade_date): {max_date}")
    
    r2 = ch_query("SELECT count() AS cnt FROM tushare.tushare_daily_basic FINAL WHERE trade_date >= '2026-05-01'")
    db_cnt = r2.get('data', [{}])[0].get('cnt', 0)
    print(f"  daily_basic rows since 2026-05-01: {db_cnt}")

    # ── Phase 1: Build Candidates (one big SQL with position and vol) ──
    print(f"\n{'='*60}")
    print("Phase 1: Building Candidates (full history)")
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
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
          AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%'
          AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    )
    WHERE pos_20d <= 40  -- wider net to capture all bottom positions
      AND amplitude >= 3
    ORDER BY ts_code, trade_date
    """
    
    r = ch_query(sql, timeout=600)
    data = r.get('data', [])
    print(f"  Raw candidates: {len(data)} rows")
    
    candidates = {}
    for row in data:
        key = (row['ts_code'], str(row['trade_date'])[:10])
        candidates[key] = row
    
    ts_codes = set(row['ts_code'] for row in data)
    print(f"  Distinct stocks: {len(ts_codes)}")
    print(f"  Distinct dates: {len(set(str(r['trade_date'])[:10] for r in data))}")

    # ── Phase 2: Fetch daily_basic (PE, PB, dv_ratio, circ_mv, volume_ratio, turnover_rate) ──
    print(f"\n{'='*60}")
    print("Phase 2: Fetching Daily Basic (PE/PB/dv/circ_mv/TR)")
    print(f"{'='*60}")
    
    code_list = list(ts_codes)
    batch_size = 500
    db_data = {}
    
    for i in range(0, len(code_list), batch_size):
        batch = code_list[i:i+batch_size]
        codes_str = ",".join(f"'{c}'" for c in batch)
        
        sql = f"""
        SELECT ts_code, trade_date, pe, pb, dv_ratio, volume_ratio, circ_mv, turnover_rate
        FROM tushare.tushare_daily_basic FINAL
        WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
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

    # ── Phase 3: Fetch fina_indicator (netprofit_yoy, tr_yoy, roe) ──
    print(f"\n{'='*60}")
    print("Phase 3: Fetching Financial Indicators")
    print(f"{'='*60}")
    
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
                  f"codes={len(batch)}, fina_rows={len(rows)}, unique={len(fina_data)}")
    
    print(f"  Total fina_indicator (latest per stock): {len(fina_data)}")

    # ── Phase 3.5: Fetch moneyflow for buy_elg > sell_elg ──
    print(f"\n{'='*60}")
    print("Phase 3.5: Fetching Moneyflow (buy_elg/sell_elg)")
    print(f"{'='*60}")
    
    mf_data = {}
    for i in range(0, len(code_list), batch_size):
        batch = code_list[i:i+batch_size]
        codes_str = ",".join(f"'{c}'" for c in batch)
        
        sql = f"""
        SELECT ts_code, trade_date, buy_elg_amount, sell_elg_amount
        FROM tushare.tushare_moneyflow FINAL
        WHERE trade_date >= '2024-01-01' AND trade_date <= '{END_DATE}'
          AND ts_code IN ({codes_str})
        ORDER BY ts_code, trade_date
        """
        
        r = ch_query(sql, timeout=300)
        rows = r.get('data', [])
        for row in rows:
            key = (row['ts_code'], str(row['trade_date'])[:10])
            mf_data[key] = row
        
        if (i // batch_size) % 10 == 0 or i + batch_size >= len(code_list):
            print(f"  Batch {i//batch_size}/{(len(code_list)-1)//batch_size}: "
                  f"codes={len(batch)}, mf_rows={len(rows)}, total={len(mf_data)}")
    
    print(f"  Total moneyflow rows: {len(mf_data)}")

    # ── Phase 4: Fetch Forward Prices ──
    print(f"\n{'='*60}")
    print("Phase 4: Fetching Forward Prices (for return computation)")
    print(f"{'='*60}")
    
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
    
    # Build price lookup: for each stock, sorted list of dates
    stock_prices = {}
    for (code, date), close in all_prices.items():
        if code not in stock_prices:
            stock_prices[code] = []
        stock_prices[code].append((date, close))
    for code in stock_prices:
        stock_prices[code].sort(key=lambda x: x[0])

    # ── Signal cutoff: need at least 5D forward data ──
    # We need 5 trading days after the last signal date
    # END_DATE is 2026-05-12, so last signal date is 2026-05-05 (5 trading days back)
    signal_end = "2026-05-05"
    print(f"  Signal cutoff (need 5D forward): {signal_end}")

    # ===== 5 COMBO DEFINITIONS =====
    combos = [
        {
            'id': 'C1',
            'name': 'C1-净利高增长≥15%+极致微盘15亿+大阳放量',
            'params': {
                'netprofit_yoy_min': 15,       # 净利润增长≥15% (更严格)
                'pct_chg_min': 3,               # 涨幅≥3% (大阳方向确认)
                'pos_max': 20,                  # 底20%
                'vr_min': 1.5,                  # 放量≥1.5
                'amp_min': 6,                   # 振幅≥6%
                'cm_max_wan': 150000,           # CM≤15亿 (极致微盘)
                'tr_min': 1,                    # 换手≥1% (活跃度)
            },
            'desc': '更高增长阈值(15%)×极致微盘(15亿)×大阳放量方向确认',
        },
        {
            'id': 'C2',
            'name': 'C2-营收高增长≥20%+高ROE≥15%+底部中小盘',
            'params': {
                'tr_yoy_min': 20,               # 营收增长≥20% (首次单独使用)
                'roe_min': 15,                  # ROE≥15% (高盈利能力)
                'pe_max': 20,                   # PE≤20
                'pos_max': 30,                  # 底30% (更宽松)
                'vr_min': 1.0,                  # VR≥1.0
                'amp_min': 4,                   # 振幅≥4% (更宽松)
                'cm_min_wan': 300000,           # CM≥30亿
                'cm_max_wan': 1000000,          # CM≤100亿 (中小盘)
            },
            'desc': '营收增长单独使用(非净利)+高ROE+中小盘新范围',
        },
        {
            'id': 'C3',
            'name': 'C3-极致低估值PE≤8+dv≥4%+高VOL共振+低换手',
            'params': {
                'pe_max': 8,                    # PE≤8 (极致低估)
                'pb_max': 1,                    # PB≤1 (破净)
                'dv_min': 4,                    # 股息率≥4%
                'pos_max': 20,                  # 底20%
                'pct_chg_min': 1,               # 小幅上涨确认
                'vr_min': 1.5,                  # 放量≥1.5 (VOL共振)
                'tr_min': 0.3,                  # 换手≥0.3%
                'tr_max': 5,                    # 换手≤5% (控制投机)
                'cm_max_wan': 500000,           # CM≤50亿
            },
            'desc': '极致低估+高股息+高VOL共振+换手控制，无振幅约束增加信号量',
        },
        {
            'id': 'C4',
            'name': 'C4-净利高增长+主力资金流入+中小盘(T5×T4交叉)',
            'params': {
                'netprofit_yoy_min': 10,        # 净利增长≥10%
                'pe_max': 20,                   # PE≤20
                'pos_max': 20,                  # 底20%
                'amp_min': 5,                   # 振幅≥5%
                'vr_min': 1.2,                  # VR≥1.2
                'buy_elg_gt_sell_elg': True,    # 超大单净买入
                'cm_max_wan': 1000000,          # CM≤100亿 (中小盘)
            },
            'desc': '基本面×资金流交叉：净利增长+主力超大户净买入',
        },
        {
            'id': 'C5',
            'name': 'C5-高股息+低换手筹码锁定+深底+中大盘(R5最大容量)',
            'params': {
                'dv_min': 3,                    # 股息率≥3%
                'pe_max': 15,                   # PE≤15
                'pb_max': 2,                    # PB≤2
                'pos_max': 20,                  # 底20%
                'amp_min': 5,                   # 振幅≥5%
                'vr_min': 1.2,                  # VR≥1.2
                'tr_min': 0.3,                  # 换手≥0.3%
                'tr_max': 3,                    # 换手≤3% (筹码锁定)
                'cm_min_wan': 300000,           # CM≥30亿
                'cm_max_wan': 2000000,          # CM≤200亿 (中大盘容量)
            },
            'desc': '高股息+低换手(筹码锁定×T5)首次结合，中大盘容量扩展',
        },
    ]

    # ===== APPLY FILTERS TO CANDIDATES =====
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
        skipped_tr = 0
        skipped_mf = 0
        skipped_cm_min = 0
        skipped_cm_max = 0
        
        for (code, date), row in candidates.items():
            if date >= signal_end:
                continue
            
            k = (code, date)
            db_row = db_data.get(k, {})
            fina = fina_data.get(code, {})
            mf_row = mf_data.get(k, {})
            
            pos = row.get('pos_20d', 999) or 999
            amp = row.get('amplitude', 0) or 0
            vr = row.get('vol_ratio', 0) or 0
            pct = row.get('pct_chg', 0) or 0
            
            pe = db_row.get('pe')
            pb = db_row.get('pb')
            dv = db_row.get('dv_ratio')
            cm = db_row.get('circ_mv')  # 万元
            tr = db_row.get('turnover_rate')  # 小数比例
            
            ny = fina.get('netprofit_yoy')
            tr_yoy = fina.get('tr_yoy')
            roe = fina.get('roe')
            
            buy_elg = mf_row.get('buy_elg_amount', 0) or 0
            sell_elg = mf_row.get('sell_elg_amount', 0) or 0
            
            # ── C1: 净利高增长≥15%+极致微盘15亿+大阳放量 ──
            if combo['id'] == 'C1':
                if pos > 20: skipped_pos += 1; continue
                if amp < 6: skipped_amp += 1; continue
                if vr < 1.5: skipped_vr += 1; continue
                if pct < 3: skipped_pct += 1; continue
                if not cm or cm > 150000: skipped_cm_max += 1; continue
                if not tr or tr < 1: skipped_tr += 1; continue
                if not ny or ny < 15: skipped_fina += 1; continue
            
            # ── C2: 营收高增长≥20%+高ROE≥15%+底部中小盘 ──
            elif combo['id'] == 'C2':
                if pos > 30: skipped_pos += 1; continue
                if amp < 4: skipped_amp += 1; continue
                if vr < 1.0: skipped_vr += 1; continue
                if not pe or pe <= 0 or pe > 20: skipped_db += 1; continue
                if not cm or cm < 300000: skipped_cm_min += 1; continue
                if not cm or cm > 1000000: skipped_cm_max += 1; continue
                if not tr_yoy or tr_yoy < 20: skipped_fina += 1; continue
                if not roe or roe < 15: skipped_fina += 1; continue
            
            # ── C3: 极致低估值PE≤8+dv≥4%+高VOL共振+低换手 ──
            elif combo['id'] == 'C3':
                if pos > 20: skipped_pos += 1; continue
                if vr < 1.5: skipped_vr += 1; continue
                if pct < 1: skipped_pct += 1; continue
                if not pe or pe <= 0 or pe > 8: skipped_db += 1; continue
                if not pb or pb <= 0 or pb > 1: skipped_db += 1; continue
                if not dv or dv < 4: skipped_db += 1; continue
                if not cm or cm > 500000: skipped_cm_max += 1; continue
                if not tr or tr < 0.3 or tr > 5: skipped_tr += 1; continue
            
            # ── C4: 净利高增长+主力资金流入+中小盘(T5×T4) ──
            elif combo['id'] == 'C4':
                if pos > 20: skipped_pos += 1; continue
                if amp < 5: skipped_amp += 1; continue
                if vr < 1.2: skipped_vr += 1; continue
                if not pe or pe <= 0 or pe > 20: skipped_db += 1; continue
                if not cm or cm > 1000000: skipped_cm_max += 1; continue
                if not ny or ny < 10: skipped_fina += 1; continue
                # Money flow: buy_elg > sell_elg (超大单净买入)
                if not (buy_elg and sell_elg and buy_elg > sell_elg): skipped_mf += 1; continue
            
            # ── C5: 高股息+低换手筹码锁定+深底+中大盘 ──
            elif combo['id'] == 'C5':
                if pos > 20: skipped_pos += 1; continue
                if amp < 5: skipped_amp += 1; continue
                if vr < 1.2: skipped_vr += 1; continue
                if not pe or pe <= 0 or pe > 15: skipped_db += 1; continue
                if not pb or pb <= 0 or pb > 2: skipped_db += 1; continue
                if not dv or dv < 3: skipped_db += 1; continue
                if not cm or cm < 300000: skipped_cm_min += 1; continue
                if not cm or cm > 2000000: skipped_cm_max += 1; continue
                if not tr or tr < 0.3 or tr > 3: skipped_tr += 1; continue
            
            # Signal passed
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
                'turnover_rate': tr,
                'netprofit_yoy': ny,
                'tr_yoy': tr_yoy,
                'roe': roe,
            })
        
        print(f"  Signals after filter: {len(signals)}")
        print(f"  Skipped: pos={skipped_pos}, amp={skipped_amp}, vr={skipped_vr}, "
              f"pct={skipped_pct}, db={skipped_db}, fina={skipped_fina}, "
              f"tr={skipped_tr}, mf={skipped_mf}, cm_min={skipped_cm_min}, cm_max={skipped_cm_max}")
        
        if len(signals) == 0:
            results.append({
                'name': combo_name,
                'hash': combo_hash(p),
                'signal_count': 0, 'n_5d': 0,
                'wr_5d': 0, 'wr_10d': 0, 'wr_20d': 0,
                'ret_5d': 0, 'ret_10d': 0, 'ret_20d': 0,
                'sharpe_5d': 0,
                'status': '❌ 零信号',
                'params': p,
                'desc': combo['desc'],
            })
            continue
        
        # ── Compute forward returns ──
        forward_results = []
        for s in signals:
            code = s['ts_code']
            entry_date = s['trade_date']
            
            stock_dates = stock_prices.get(code, [])
            date_strs = [d for d, _ in stock_dates]
            
            if entry_date not in date_strs:
                continue
            
            idx = date_strs.index(entry_date)
            
            rets = {
                'ts_code': code,
                'trade_date': entry_date,
                'close': s['close'],
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
                    future_close = stock_dates[idx + offset][1]
                    if future_close and s['close'] and s['close'] > 0:
                        rets[key] = (future_close - s['close']) / s['close']
                    else:
                        rets[key] = None
                else:
                    rets[key] = None
            
            forward_results.append(rets)
        
        stats = compute_stats(forward_results)
        
        # Success criteria: WR ≥ 55% AND 5D return ≥ 5% AND signal ≥ 200
        wr_5d = stats.get('wr_5d', 0)
        ret_5d = stats.get('ret_5d', 0)
        n_5d = stats.get('n_5d', 0)
        
        passed = wr_5d >= 55 and ret_5d >= 5 and n_5d >= 200
        
        result = {
            'name': combo_name,
            'hash': combo_hash(p),
            'signal_count': stats['signal_count'],
            'n_5d': n_5d,
            'wr_5d': wr_5d,
            'ret_5d': ret_5d,
            'wr_10d': stats.get('wr_10d', 0),
            'ret_10d': stats.get('ret_10d', 0),
            'wr_20d': stats.get('wr_20d', 0),
            'ret_20d': stats.get('ret_20d', 0),
            'sharpe_5d': stats.get('sharpe_5d', 0),
            'status': '✅ 达标' if passed else '❌ 未达标',
            'params': p,
            'desc': combo['desc'],
        }
        
        if passed:
            print(f"  ✅ PASSED! WR={wr_5d:.1f}%, R5={ret_5d:.2f}%, N={n_5d}, Sharpe={stats['sharpe_5d']}")
        else:
            reason = []
            if wr_5d < 55: reason.append(f"WR={wr_5d:.1f}<55%")
            if ret_5d < 5: reason.append(f"R5={ret_5d:.2f}<5%")
            if n_5d < 200: reason.append(f"N={n_5d}<200")
            print(f"  ❌ Failed: {', '.join(reason)}")
        
        results.append(result)
    
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"\n{'='*60}")
    print(f"All combos done! Elapsed: {elapsed:.0f}s")
    print(f"{'='*60}")
    
    return results, combos, ts_codes


def write_report(results, combos):
    report_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_18/analysis_T5_基本面估值_基本面估值.md"
    
    lines = []
    lines.append(f"# Iter18 T5 — 基本面估值 (Fundamental Valuation) 挖掘报告\n")
    lines.append(f"**执行时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n")
    lines.append(f"**数据基准：** 2026-05-12\n")
    lines.append(f"**成功标准：** WR ≥ 55% AND 5D收益 ≥ 5% AND 信号数 ≥ 200\n")
    lines.append(f"**历史最佳(全局)：** WR=94.93%, R5=21.32% (SPX-NEG, Iter15)\n")
    lines.append(f"**历史最佳(T5流派)：** R5=6.70% (T5-C4, Iter10), WR=81.27% (T5-C9, Iter8)\n")
    lines.append(f"**疲劳计数：** 2 (连续未破全局纪录)\n")
    lines.append(f"\n---\n")
    
    # Summary table
    lines.append(f"\n## 5组参数组合结果汇总\n")
    lines.append(f"| 组合 | 信号数(N) | WR-5D | R5 | R10 | R20 | Sharpe | 状态 |")
    lines.append(f"|------|----------|-------|----|----|----|--------|------|")
    
    passed_count = 0
    for r in results:
        status_icon = "✅" if r['wr_5d'] >= 55 and r['ret_5d'] >= 5 and r['n_5d'] >= 200 else "❌"
        if status_icon == "✅":
            passed_count += 1
        lines.append(f"| {r['name']} | {r['n_5d']} | {r['wr_5d']:.1f}% | {r['ret_5d']:.2f}% | {r['ret_10d']:.2f}% | {r['ret_20d']:.2f}% | {r['sharpe_5d']:.3f} | {status_icon} |")
    
    lines.append(f"\n**通过率：** {passed_count}/{len(results)} ({passed_count/len(results)*100:.0f}%)\n")
    
    # Detailed analysis per combo
    lines.append(f"\n---\n")
    lines.append(f"## 各组详细分析\n")
    
    for i, (combo, result) in enumerate(zip(combos, results)):
        lines.append(f"\n### {combo['name']}\n")
        lines.append(f"- **描述：** {combo['desc']}\n")
        lines.append(f"- **参数：** `{json.dumps(combo['params'], ensure_ascii=False)}`\n")
        lines.append(f"- **Hash：** `{result['hash']}`\n")
        lines.append(f"- **信号数：** {result['n_5d']} (总候选: {result['signal_count']})\n")
        lines.append(f"- **胜率(WR-5D)：** {result['wr_5d']:.1f}%\n")
        lines.append(f"- **5日平均收益：** {result['ret_5d']:.2f}%\n")
        lines.append(f"- **10日平均收益：** {result['ret_10d']:.2f}%\n")
        lines.append(f"- **20日平均收益：** {result['ret_20d']:.2f}%\n")
        lines.append(f"- **夏普比率：** {result['sharpe_5d']:.3f}\n")
        lines.append(f"- **状态：** {result['status']}\n")
    
    # Best discovery
    lines.append(f"\n---\n")
    lines.append(f"## 最佳发现\n")
    
    best = max(results, key=lambda r: (r['wr_5d'] if r['wr_5d'] >= 55 and r['ret_5d'] >= 5 and r['n_5d'] >= 200 else 0))
    
    if best['wr_5d'] >= 55 and best['ret_5d'] >= 5 and best['n_5d'] >= 200:
        lines.append(f"\n### 🏆 {best['name']}\n")
        lines.append(f"- **WR-5D：** {best['wr_5d']:.1f}%\n")
        lines.append(f"- **R5：** {best['ret_5d']:.2f}%\n")
        lines.append(f"- **R10：** {best['ret_10d']:.2f}%\n")
        lines.append(f"- **R20：** {best['ret_20d']:.2f}%\n")
        lines.append(f"- **Sharpe：** {best['sharpe_5d']:.3f}\n")
        lines.append(f"- **N：** {best['n_5d']}\n")
        lines.append(f"- **参数详情：** `{json.dumps(best['params'], ensure_ascii=False)}`\n")
        lines.append(f"- **逻辑链：** {best['desc']}\n")
        
        # Compare with historical T5 best
        lines.append(f"\n#### 对比历史T5最佳\n")
        lines.append(f"- Iter10 T5-C4: R5=6.70%, WR=70.01%, N=677, Sharpe=3.963\n")
        lines.append(f"- Iter17 T5-C1: R5=5.41%, WR=73.82%, N=233, Sharpe=4.016\n")
        if best['ret_5d'] >= 6.7:
            lines.append(f"- ✅ R5超越历史T5最佳(6.70%)!\n")
        else:
            lines.append(f"- ❌ R5未超越历史T5最佳(6.70%, 差{6.7-best['ret_5d']:.2f}pp)\n")
    else:
        lines.append(f"\n⚠️ 本轮无达标组合\n")
        lines.append(f"- 所有组合均未同时满足 WR≥55% + R5≥5% + N≥200\n")
        # Show closest
        lines.append(f"\n**最接近达标：**\n")
        for r in sorted(results, key=lambda x: (x['wr_5d']*x['ret_5d']), reverse=True)[:2]:
            lines.append(f"- {r['name']}: WR={r['wr_5d']:.1f}%, R5={r['ret_5d']:.2f}%, N={r['n_5d']}\n")
    
    # Key SQL query (reproducible)
    lines.append(f"\n---\n")
    lines.append(f"## 关键SQL查询（可复现）\n")
    
    # Generate SQL for the best combo
    if best['wr_5d'] >= 55 and best['ret_5d'] >= 5 and best['n_5d'] >= 200:
        p = best['params']
        sql_parts = []
        sql_parts.append(f"-- Iter18 T5 最佳组合SQL: {best['name']}")
        sql_parts.append(f"-- 完整回测脚本: iter18_t5_backtest.py")
        sql_parts.append(f"SELECT ts_code, trade_date, close, pct_chg, amplitude, pos_20d, vol_ratio")
        sql_parts.append(f"FROM (")
        sql_parts.append(f"    SELECT ts_code, trade_date, close, pct_chg, high, low, vol, amount,")
        sql_parts.append(f"        round((high/low-1)*100,2) AS amplitude,")
        sql_parts.append(f"        round((close-MIN(low) OVER w)/NULLIF(MAX(high) OVER w-MIN(low) OVER w,0.001)*100,2) AS pos_20d,")
        sql_parts.append(f"        round(vol/NULLIF(AVG(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING),0.001),2) AS vol_ratio")
        sql_parts.append(f"    FROM tushare.tushare_stock_daily FINAL")
        sql_parts.append(f"    WHERE trade_date>='2023-01-01' AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%')")
        sql_parts.append(f"WHERE 1=1")
        if 'pos_max' in p: sql_parts.append(f"  AND pos_20d <= {p['pos_max']}")
        if 'amp_min' in p: sql_parts.append(f"  AND amplitude >= {p['amp_min']}")
        if 'vr_min' in p: sql_parts.append(f"  AND vol_ratio >= {p['vr_min']}")
        if 'pct_chg_min' in p: sql_parts.append(f"  AND pct_chg >= {p['pct_chg_min']}")
        lines.append(f"\n```sql\n" + "\n".join(sql_parts) + "\n```\n")
    
    # Write report
    with open(report_path, 'w') as f:
        f.write("\n".join(lines))
    
    print(f"\nReport written to: {report_path}")
    return report_path


if __name__ == "__main__":
    results, combos, ts_codes = run()
    report_path = write_report(results, combos)
    print(f"\nDone. Report: {report_path}")
    
    # Print summary to stdout for kanban_complete
    print(f"\n{'='*60}")
    print("SUMMARY FOR KANBAN_COMPLETE")
    print(f"{'='*60}")
    for r in results:
        status = "✅" if r['wr_5d'] >= 55 and r['ret_5d'] >= 5 and r['n_5d'] >= 200 else "❌"
        print(f"{status} {r['name']}: WR={r['wr_5d']:.1f}%, R5={r['ret_5d']:.2f}%, N={r['n_5d']}, Sharpe={r['sharpe_5d']:.3f}")
    
    best = max(results, key=lambda r: (r['wr_5d'] if r['wr_5d'] >= 55 and r['ret_5d'] >= 5 and r['n_5d'] >= 200 else 0))
    print(f"\nBest: {best['name']}")
    print(f"WR={best['wr_5d']:.1f}%, R5={best['ret_5d']:.2f}%, N={best['n_5d']}, Sharpe={best['sharpe_5d']:.3f}")
