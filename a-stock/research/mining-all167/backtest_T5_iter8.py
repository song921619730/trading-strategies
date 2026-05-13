#!/usr/bin/env python3
"""T5 iter8: 基本面估值挖掘 — incremental with progress tracking"""
import json, hashlib, subprocess, sys, math, os
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START_DATE = '20250101'
END_DATE = '20260511'

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0: return []
    try:
        data = json.loads(r.stdout)
        return data if isinstance(data, list) else data.get("data", [])
    except: return []

def combo_hash(params):
    return hashlib.md5(json.dumps(sorted(params.items()), ensure_ascii=False).encode()).hexdigest()[:12]

def calc_sharpe(returns):
    if len(returns) < 10: return 0
    mean_r = sum(returns) / len(returns)
    if mean_r <= 0: return 0
    var = sum((r-mean_r)**2 for r in returns) / len(returns)
    std = math.sqrt(var) if var > 0 else 1e-10
    return mean_r/std*math.sqrt(252/5)

t0 = datetime.now()
job = print if True else lambda *a: None

# ═══ Step 1: Load daily data (fast, ~1M rows) ═══
print(f"[{datetime.now()-t0}] Loading stock daily...")
rows = ch_query(f"""
SELECT ts_code, trade_date, high, low, close, pre_close, pct_chg, amount
FROM tushare.tushare_stock_daily AS s FINAL
WHERE s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
  AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
  AND s.trade_date >= '{START_DATE}' AND s.trade_date <= '{END_DATE}'
ORDER BY s.ts_code, s.trade_date
""")
print(f"[{datetime.now()-t0}] Daily: {len(rows)} rows from {len(set(r['ts_code'] for r in rows))} stocks")

# Build: stock → [bar_dict]
stock_bars = defaultdict(list)
for r in rows:
    code = r['ts_code']; dt = str(r['trade_date']).replace('-','')
    stock_bars[code].append({
        'dt':dt, 'high':float(r['high'] or 0), 'low':float(r['low'] or 0),
        'close':float(r['close'] or 0), 'pre_close':float(r['pre_close'] or 0),
        'pct_chg':float(r['pct_chg'] or 0), 'amount':float(r['amount'] or 0),
    })

# ═══ Step 2: Pre-compute position + forward returns per record ═══
print(f"[{datetime.now()-t0}] Computing positions & forward returns...")
all_records = []
n_stocks = len(stock_bars)
for si, (code, bars) in enumerate(stock_bars.items()):
    if si % 500 == 0:
        print(f"  ...{si}/{n_stocks} stocks, {len(all_records)} records")
    
    n = len(bars)
    # Pre-compute forward returns
    fwd = [(None, None, None)] * n
    for i in range(n):
        for j, idx in [(4,0), (9,1), (19,2)]:
            if i + j < n:
                ret = (bars[i+j]['close'] / bars[i]['close'] - 1) * 100
                fwd_i = list(fwd[i] or (None, None, None))
                fwd_i[idx] = ret
                fwd[i] = tuple(fwd_i)
    
    for i, bar in enumerate(bars):
        if i < 20: continue
        window = bars[i-19:i+1]
        min_low = min(b['low'] for b in window); max_high = max(b['high'] for b in window)
        rng = max_high - min_low
        if rng <= 0: continue
        pos_pct = (bar['close'] - min_low) / rng * 100
        pos = ('底20%' if pos_pct <= 20 else '底30%' if pos_pct <= 30 else 
               '底40%' if pos_pct <= 40 else '中位' if pos_pct <= 60 else
               '顶20%' if pos_pct <= 80 else '顶10%')
        pre = bar['pre_close']
        amp = (bar['high'] - bar['low']) / pre * 100 if pre > 0 else 0
        
        all_records.append({
            'code': code, 'dt': bar['dt'], 'close': bar['close'],
            'pct_chg': bar['pct_chg'], 'pos': pos, 'pos_pct': pos_pct,
            'amp': amp, 'amount': bar['amount'],
            'fwd5': fwd[i][0], 'fwd10': fwd[i][1], 'fwd20': fwd[i][2],
        })

print(f"[{datetime.now()-t0}] Total records: {len(all_records)}")
rec_idx = {(r['code'], r['dt']): r for r in all_records}

# ═══ Step 3: Load daily_basic (this is the biggest payload) ═══
# Only load stocks that are in all_records
codes_set = set(r['code'] for r in all_records)
print(f"[{datetime.now()-t0}] Loading daily_basic for {len(codes_set)} stocks...")
rows_b = ch_query(f"""
SELECT ts_code, trade_date, pe, pb, dv_ratio, circ_mv, volume_ratio
FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
WHERE b.trade_date >= '{START_DATE}' AND b.trade_date <= '{END_DATE}'
""")
print(f"[{datetime.now()-t0}] Daily basic: {len(rows_b)}")
daily_basic = {}
for r in rows_b:
    k = (r['ts_code'], str(r['trade_date']).replace('-',''))
    if k in rec_idx:  # only keep records we have position data for
        daily_basic[k] = {'pe': r['pe'], 'pb': r['pb'], 'dv_ratio': r['dv_ratio'],
                          'circ_mv': r['circ_mv'], 'volume_ratio': r['volume_ratio']}
print(f"[{datetime.now()-t0}] Daily basic matched: {len(daily_basic)}")

# ═══ Step 4: Load fina_indicator ═══
print(f"[{datetime.now()-t0}] Loading fina_indicator...")
rows_f = ch_query(f"""
SELECT ts_code, end_date, roe, gross_margin, netprofit_margin, tr_yoy, netprofit_yoy
FROM (SELECT * FROM tushare.tushare_fina_indicator FINAL) AS f
ORDER BY ts_code, end_date
""")
print(f"[{datetime.now()-t0}] Fina: {len(rows_f)}")
latest_fina = {}
for r in rows_f:
    code = r['ts_code']; ed = str(r['end_date']).replace('-','')
    if code not in latest_fina or ed > latest_fina[code]['end_date']:
        latest_fina[code] = {
            'end_date': ed,
            'roe': r['roe'], 'gross_margin': r['gross_margin'],
            'netprofit_margin': r['netprofit_margin'],
            'tr_yoy': r['tr_yoy'], 'netprofit_yoy': r['netprofit_yoy'],
        }
print(f"[{datetime.now()-t0}] Fina unique: {len(latest_fina)}")

# ═══ Step 5: Load forecast ═══
print(f"[{datetime.now()-t0}] Loading forecast...")
rows_fc = ch_query(f"""
SELECT ts_code, end_date, type FROM (SELECT * FROM tushare.tushare_forecast FINAL) AS fc
ORDER BY ts_code, end_date
""")
print(f"[{datetime.now()-t0}] Forecast: {len(rows_fc)}")
latest_fc = {}
for r in rows_fc:
    code = r['ts_code']; ed = str(r['end_date']).replace('-','')
    if code not in latest_fc or ed > latest_fc[code]['end_date']:
        latest_fc[code] = {'end_date': ed, 'type': r['type']}

# ═══ Step 6: Load holder numbers ═══
print(f"[{datetime.now()-t0}] Loading holder numbers...")
rows_h = ch_query(f"""
SELECT ts_code, end_date, holder_num
FROM (SELECT * FROM tushare.tushare_stk_holdernumber FINAL) AS h
ORDER BY ts_code, end_date
""")
print(f"[{datetime.now()-t0}] Holder: {len(rows_h)}")
holder_by_stock = defaultdict(list)
for r in rows_h:
    holder_by_stock[r['ts_code']].append((str(r['end_date']).replace('-',''), r['holder_num']))
holder_chg = {}
for code, recs in holder_by_stock.items():
    recs.sort(key=lambda x: x[0])
    if len(recs) >= 2:
        n1, n2 = recs[-1][1], recs[-2][1]
        chg = (n1 - n2) / n2 * 100 if n2 > 0 else 0
        holder_chg[code] = chg

print(f"[{datetime.now()-t0}] Data loading complete!")
print(f"  records={len(all_records)}, db_matched={len(daily_basic)}, fina={len(latest_fina)}, fc={len(latest_fc)}, holder_chg={len(holder_chg)}")

# ═══ BACKTEST ENGINE ═══
def run(combo_name, params, filter_fn):
    signals = []
    for r in all_records:
        k = (r['code'], r['dt'])
        db = daily_basic.get(k, {})
        fina = latest_fina.get(r['code'], {})
        fc = latest_fc.get(r['code'], {})
        hc = holder_chg.get(r['code'])
        if filter_fn(r, db, fina, fc, hc):
            signals.append(r)
    
    n = len(signals)
    print(f"[{datetime.now()-t0}]  {combo_name}: {n} signals")
    if n < 10:
        return {"name": combo_name, "hash": combo_hash(params),
                "signal_count": n, "n_5d": 0,
                "win_rate_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0,
                "sharpe_5d": 0, "status": "insufficient"}
    
    ret5 = [s['fwd5'] for s in signals if s['fwd5'] is not None]
    ret10 = [s['fwd10'] for s in signals if s['fwd10'] is not None]
    ret20 = [s['fwd20'] for s in signals if s['fwd20'] is not None]
    n5 = len(ret5)
    if n5 < 10:
        return {"name": combo_name, "hash": combo_hash(params),
                "signal_count": n, "n_5d": n5,
                "win_rate_5d": 0, "ret_5d": 0,
                "sharpe_5d": 0, "status": "insufficient_5d"}
    
    wr = sum(1 for r in ret5 if r > 0) / n5 * 100
    r5 = sum(ret5) / n5
    r10 = sum(ret10) / len(ret10) if ret10 else 0
    r20 = sum(ret20) / len(ret20) if ret20 else 0
    sh = calc_sharpe(ret5)
    passed = wr >= 52 and r5 >= 3 and n5 >= 200
    return {"name": combo_name, "hash": combo_hash(params),
            "signal_count": n, "n_5d": n5,
            "win_rate_5d": round(wr, 2), "ret_5d": round(r5, 2),
            "ret_10d": round(r10, 2), "ret_20d": round(r20, 2),
            "sharpe_5d": round(sh, 3),
            "status": "passed" if passed else "failed"}

# ═══ FILTERS ═══
def f1(s, db, fina, fc, hc):
    if s['pos'] not in ('底20%','底30%','底40%'): return False
    pe, pb = db.get('pe'), db.get('pb')
    dv = db.get('dv_ratio'); vr = db.get('volume_ratio'); mv = db.get('circ_mv')
    gm = fina.get('gross_margin')
    if not pe or pe <= 0 or pe > 20: return False
    if not pb or pb <= 0 or pb > 2: return False
    if not dv or dv < 1.0: return False
    if not vr or vr < 1.0: return False
    if not mv or mv > 1000000: return False
    if not gm or gm < 0.30: return False
    return True

def f2(s, db, fina, fc, hc):
    if s['pos'] in ('底20%','底30%','底40%'): return False
    if s['amp'] < 3: return False
    pe, pb = db.get('pe'), db.get('pb')
    mv = db.get('circ_mv'); roe = fina.get('roe')
    if not pe or pe <= 0 or pe > 15: return False
    if not pb or pb <= 0 or pb > 3: return False
    if not mv or mv < 1000000 or mv > 5000000: return False
    if not roe or roe < 0.15: return False
    return True

def f3(s, db, fina, fc, hc):
    if s['pos'] not in ('底20%','底30%'): return False
    dv = db.get('dv_ratio'); pe = db.get('pe'); pb = db.get('pb')
    vr = db.get('volume_ratio'); npm = fina.get('netprofit_margin')
    if not dv or dv < 2.0: return False
    if not pe or pe <= 0 or pe > 15: return False
    if not pb or pb <= 0 or pb > 2: return False
    if not vr or vr < 1.0: return False
    if not npm or npm < 0.05: return False
    if hc is None or hc > -10: return False
    return True

def f4(s, db, fina, fc, hc):
    if s['pos'] not in ('底20%','底30%','底40%'): return False
    pe = db.get('pe'); mv = db.get('circ_mv')
    tr = fina.get('tr_yoy'); npm = fina.get('netprofit_margin'); roe = fina.get('roe')
    if not pe or pe <= 0 or pe > 30: return False
    if not mv or mv < 1000000 or mv > 5000000: return False
    if not tr or tr < 10: return False
    if not npm or npm < 0.10: return False
    if not roe or roe < 0.10: return False
    return True

def f5(s, db, fina, fc, hc):
    if s['pos'] != '底20%': return False
    dv = db.get('dv_ratio'); pe = db.get('pe'); pb = db.get('pb')
    vr = db.get('volume_ratio'); mv = db.get('circ_mv')
    if not dv or dv < 1.5: return False
    if not pe or pe <= 0 or pe > 20: return False
    if not pb or pb <= 0 or pb > 2: return False
    if not vr or vr < 1.2: return False
    if not mv or mv > 1000000: return False
    if not fc or fc.get('type') != '预增': return False
    return True

def f6(s, db, fina, fc, hc):
    """T5-C5 replica: netprofit_yoy≥5% + PE≤20 + PB≤2 + dv≥1.5% + 底20% + VR≥1.5 + 振幅≥5% + CM≤50亿"""
    if s['pos'] != '底20%': return False
    if s['amp'] < 5: return False
    pe = db.get('pe'); pb = db.get('pb'); dv = db.get('dv_ratio')
    vr = db.get('volume_ratio'); mv = db.get('circ_mv'); ny = fina.get('netprofit_yoy')
    if not pe or pe <= 0 or pe > 20: return False
    if not pb or pb <= 0 or pb > 2: return False
    if not dv or dv < 1.5: return False
    if not vr or vr < 1.5: return False
    if not mv or mv > 500000: return False  # ≤50亿
    if not ny or ny < 5: return False
    return True

def f7(s, db, fina, fc, hc):
    """高股息+底部+振幅确认: dv≥2% + PE≤15 + PB≤2 + 底20% + VR≥1.0 + 振幅≥5%"""
    if s['pos'] != '底20%': return False
    if s['amp'] < 5: return False
    pe = db.get('pe'); pb = db.get('pb'); dv = db.get('dv_ratio')
    vr = db.get('volume_ratio')
    if not pe or pe <= 0 or pe > 15: return False
    if not pb or pb <= 0 or pb > 2: return False
    if not dv or dv < 2.0: return False
    if not vr or vr < 1.0: return False
    return True

def f8(s, db, fina, fc, hc):
    """成长+底部激活: netprofit_yoy≥5% + tr_yoy≥5% + 底20% + 振幅≥5% + VR≥1.5 + CM≤50亿"""
    if s['pos'] != '底20%': return False
    if s['amp'] < 5: return False
    vr = db.get('volume_ratio'); mv = db.get('circ_mv'); ny = fina.get('netprofit_yoy')
    tr = fina.get('tr_yoy')
    if not vr or vr < 1.5: return False
    if not mv or mv > 500000: return False
    if not ny or ny < 5: return False
    if not tr or tr < 5: return False
    return True

def f9(s, db, fina, fc, hc):
    """净利增长+估值合理+底部放量振幅: PE≤30 + netprofit_yoy≥10% + 底20% + 振幅≥5% + VR≥1.5 + CM≤100亿"""
    if s['pos'] != '底20%': return False
    if s['amp'] < 5: return False
    pe = db.get('pe'); vr = db.get('volume_ratio'); mv = db.get('circ_mv'); ny = fina.get('netprofit_yoy')
    if not pe or pe <= 0 or pe > 30: return False
    if not vr or vr < 1.5: return False
    if not mv or mv > 1000000: return False
    if not ny or ny < 10: return False
    return True

# ═══ RUN ═══
results = []
for name, params, fn in [
    ("C1 高毛利率估值底部", {"gross_margin_min":0.30,"pe_max":20,"pb_max":2,"close_position":"底40%","volume_ratio_min":1.0,"dividend_yield_min":0.01,"circ_mv_max_wan":1000000}, f1),
    ("C2 高ROE中位中大盘", {"roe_min":0.15,"pe_max":15,"pb_max":3,"close_position":"中位","amplitude_min":3,"circ_mv_min_wan":1000000,"circ_mv_max_wan":5000000}, f2),
    ("C3 筹码集中高股息底部", {"holder_chg":"减少>10%","dividend_yield_min":0.02,"pe_max":15,"pb_max":2,"close_position":"底30%","volume_ratio_min":1.0,"netprofit_margin_min":0.05}, f3),
    ("C4 营收双增中大盘", {"tr_yoy_min":10,"netprofit_margin_min":0.10,"roe_min":0.10,"pe_max":30,"close_position":"底40%","circ_mv_100_500":True}, f4),
    ("C5 预增高股息底部", {"forecast_type":"预增","dividend_yield_min":0.015,"pe_max":20,"pb_max":2,"close_position":"底20%","volume_ratio_min":1.2,"circ_mv_max_wan":1000000}, f5),
    ("C6 净利高股息底部激活", {"netprofit_yoy_min":5,"pe_max":20,"pb_max":2,"dv_min":1.5,"close_position":"底20%","volume_ratio_min":1.5,"amplitude_min":5,"circ_mv_max_wan":500000}, f6),
    ("C7 高股息振幅底部", {"dv_min":2,"pe_max":15,"pb_max":2,"close_position":"底20%","volume_ratio_min":1.0,"amplitude_min":5}, f7),
    ("C8 成长双增底部激活", {"netprofit_yoy_min":5,"tr_yoy_min":5,"close_position":"底20%","volume_ratio_min":1.5,"amplitude_min":5,"circ_mv_max_wan":500000}, f8),
    ("C9 净利增长估值底部", {"netprofit_yoy_min":10,"pe_max":30,"close_position":"底20%","volume_ratio_min":1.5,"amplitude_min":5,"circ_mv_max_wan":1000000}, f9),
]:
    print(f"\n[{datetime.now()-t0}] === {name} ===")
    results.append(run(name, params, fn))

# ═══ REPORT ═══
print("\n\n" + "="*80)
print(f"📊 T5 基本面估值挖掘 Iter8 - 最终结果 ({datetime.now()-t0})")
print("="*80)
hdr = f"{'Name':<28} {'Sig':>6} {'N5d':>5} {'WR%':>7} {'R5%':>8} {'R10%':>8} {'R20%':>8} {'Sharpe':>8} {'Status':<12}"
print(hdr); print("-"*90)
for r in results:
    st = '✅ PASS' if r['status']=='passed' else ('❌ FAIL' if r['status']=='failed' else '⚠️ '+r['status'][:8])
    print(f"{r['name']:<28} {r['signal_count']:>6} {r.get('n_5d',0):>5} {r['win_rate_5d']:>6.1f}% {r['ret_5d']:>7.2f}% {r['ret_10d']:>7.2f}% {r['ret_20d']:>7.2f}% {r['sharpe_5d']:>7.3f}  {st}")

passed = [r for r in results if r['status']=='passed']
best_all = max(results, key=lambda x: x.get('ret_5d', 0))
if passed:
    best = max(passed, key=lambda x: x['ret_5d'])
    print(f"\n🏆 最佳通过: {best['name']} | R5={best['ret_5d']}%, WR={best['win_rate_5d']}%, N={best['signal_count']}, Sharpe={best['sharpe_5d']}")
print(f"\n📌 最佳(全部): {best_all['name']} | R5={best_all['ret_5d']}%, WR={best_all['win_rate_5d']}%, N={best_all['signal_count']}")

# Save
os.makedirs('logs/iter_8', exist_ok=True)
with open('logs/iter_8/results_T5_iter8.json', 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\n✅ Results saved to logs/iter_8/results_T5_iter8.json")
