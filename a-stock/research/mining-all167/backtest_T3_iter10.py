#!/usr/bin/env python3
"""T3 iter10: 反转低吸挖掘 — 5组全新方向"""
import json, hashlib, subprocess, sys, math, os
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START_DATE = '20250101'
END_DATE = '20260511'

def ch_query(sql):
    r = subprocess.run(["python3", CH_QUERY, "sql", sql], capture_output=True, text=True, timeout=300)
    if r.returncode != 0: 
        print(f"[WARN] ch_query failed: {r.stderr[:200]}", file=sys.stderr)
        return []
    try:
        data = json.loads(r.stdout)
        return data if isinstance(data, list) else data.get("data", [])
    except:
        print(f"[WARN] ch_query parse error: {r.stdout[:200]}", file=sys.stderr)
        return []

def combo_hash(params):
    return hashlib.md5(json.dumps(sorted(params.items()), ensure_ascii=False).encode()).hexdigest()[:12]

def calc_sharpe(returns):
    if len(returns) < 10: return 0
    mean_r = sum(returns) / len(returns)
    if mean_r <= 0: return 0
    var = sum((r-mean_r)**2 for r in returns) / len(returns)
    std = math.sqrt(var) if var > 0 else 1e-10
    return mean_r/std * math.sqrt(252/5)

t0 = datetime.now()

# ═══ Step 1: Load stock daily ═══
print(f"[{datetime.now()-t0}] Loading stock daily...")
rows = ch_query(f"""
SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol, amount
FROM tushare.tushare_stock_daily AS s FINAL
WHERE s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
  AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
  AND s.trade_date >= '{START_DATE}' AND s.trade_date <= '{END_DATE}'
ORDER BY s.ts_code, s.trade_date
""")
print(f"[{datetime.now()-t0}] Daily: {len(rows)} rows from {len(set(r['ts_code'] for r in rows))} stocks")

stock_bars = defaultdict(list)
for r in rows:
    code = r['ts_code']
    dt = str(r['trade_date']).replace('-','')
    stock_bars[code].append({
        'dt': dt,
        'open': float(r['open'] or 0),
        'high': float(r['high'] or 0),
        'low': float(r['low'] or 0),
        'close': float(r['close'] or 0),
        'pre_close': float(r['pre_close'] or 0),
        'pct_chg': float(r['pct_chg'] or 0),
        'vol': float(r['vol'] or 0),
        'amount': float(r['amount'] or 0),
    })

# ═══ Step 2: Load daily_basic (PE/PB/VR/TR/CM) ═══
print(f"[{datetime.now()-t0}] Loading daily_basic...")
basic_rows = ch_query(f"""
SELECT ts_code, trade_date, pe_ttm, pb, dv_ratio, turnover_rate_f, volume_ratio, circ_mv
FROM tushare.tushare_daily_basic AS b FINAL
WHERE b.trade_date >= '{START_DATE}' AND b.trade_date <= '{END_DATE}'
ORDER BY b.ts_code, b.trade_date
""")
print(f"[{datetime.now()-t0}] Daily_basic: {len(basic_rows)} rows")

stock_basic = defaultdict(dict)
for r in basic_rows:
    code = r['ts_code']
    dt = str(r['trade_date']).replace('-','')
    stock_basic[code][dt] = {
        'pe_ttm': float(r['pe_ttm'] or 0) if r['pe_ttm'] is not None else None,
        'pb': float(r['pb'] or 0) if r['pb'] is not None else None,
        'dv_ratio': float(r['dv_ratio'] or 0) if r['dv_ratio'] is not None else 0,
        'tr': float(r['turnover_rate_f'] or 0) if r['turnover_rate_f'] is not None else 0,
        'vr': float(r['volume_ratio'] or 0) if r['volume_ratio'] is not None else 0,
        'cm': float(r['circ_mv'] or 0) if r['circ_mv'] is not None else 0,
    }

# ═══ Step 3: Load moneyflow ═══
print(f"[{datetime.now()-t0}] Loading moneyflow...")
mf_rows = ch_query(f"""
SELECT ts_code, trade_date, net_mf_amount, net_mf_vol,
       buy_lg_amount, sell_lg_amount, buy_elg_amount, sell_elg_amount,
       buy_sm_amount, sell_sm_amount, buy_sm_vol, sell_sm_vol
FROM tushare.tushare_moneyflow AS m FINAL
WHERE m.trade_date >= '{START_DATE}' AND m.trade_date <= '{END_DATE}'
ORDER BY m.ts_code, m.trade_date
""")
print(f"[{datetime.now()-t0}] Moneyflow: {len(mf_rows)} rows")

stock_mf = defaultdict(dict)
for r in mf_rows:
    code = r['ts_code']
    dt = str(r['trade_date']).replace('-','')
    stock_mf[code][dt] = {
        'net_mf': float(r['net_mf_amount'] or 0),
        'buy_elg': float(r['buy_elg_amount'] or 0),
        'sell_elg': float(r['sell_elg_amount'] or 0),
        'buy_lg': float(r['buy_lg_amount'] or 0),
        'sell_lg': float(r['sell_lg_amount'] or 0),
        'sell_sm': float(r['sell_sm_amount'] or 0),
        'buy_sm': float(r['buy_sm_amount'] or 0),
    }

# ═══ Step 4: Load cyq_perf (筹码获利比例) ═══
print(f"[{datetime.now()-t0}] Loading cyq_perf...")
cyq_rows = ch_query(f"""
SELECT ts_code, trade_date, profit_ratio, concentration
FROM tushare.tushare_cyq_perf AS c FINAL
WHERE c.trade_date >= '{START_DATE}' AND c.trade_date <= '{END_DATE}'
ORDER BY c.ts_code, c.trade_date
""")
print(f"[{datetime.now()-t0}] Cyq_perf: {len(cyq_rows)} rows")

stock_cyq = defaultdict(dict)
for r in cyq_rows:
    code = r['ts_code']
    dt = str(r['trade_date']).replace('-','')
    stock_cyq[code][dt] = {
        'profit_ratio': float(r['profit_ratio'] or 0) if r['profit_ratio'] is not None else None,
        'concentration': str(r['concentration'] or '') if r['concentration'] is not None else '',
    }

# ═══ Step 5: Compute features per stock ═══
print(f"[{datetime.now()-t0}] Computing features...")
all_signals = []

n_stocks = len(stock_bars)
si = 0
for code, bars in stock_bars.items():
    si += 1
    if si % 500 == 0:
        print(f"  ...{si}/{n_stocks} stocks processed, {len(all_signals)} signals found so far")
    
    n = len(bars)
    basic_d = stock_basic.get(code, {})
    mf_d = stock_mf.get(code, {})
    cyq_d = stock_cyq.get(code, {})
    
    # Pre-compute forward returns
    fwd = [(None, None, None)] * n
    fwd_close = [None] * n
    for i in range(n):
        c5 = bars[i+4]['close'] if i+4 < n else None
        c10 = bars[i+9]['close'] if i+9 < n else None
        c20 = bars[i+19]['close'] if i+19 < n else None
        if c5:
            fwd[i] = ((c5 / bars[i]['close'] - 1) * 100,
                      (c10 / bars[i]['close'] - 1) * 100 if c10 else None,
                      (c20 / bars[i]['close'] - 1) * 100 if c20 else None)
    
    for i in range(n):
        if i < 25: continue  # Need 20 days for position + 5 for fwd
    
        bar = bars[i]
        dt = bar['dt']
        close = bar['close']
        pct = bar['pct_chg']
        vol = bar['vol']
        amount = bar['amount']
        
        # Get basic data
        bd = basic_d.get(dt, {})
        pe = bd.get('pe_ttm')
        pb = bd.get('pb')
        dv = bd.get('dv_ratio', 0)
        tr = bd.get('tr', 0) * 100  # Convert to %
        vr = bd.get('vr', 0)
        cm = bd.get('cm', 0) / 10000  # Convert 万元→亿
        
        # Get moneyflow
        mf = mf_d.get(dt, {})
        net_mf = mf.get('net_mf', 0)
        buy_elg = mf.get('buy_elg', 0)
        sell_elg = mf.get('sell_elg', 0)
        sell_sm = mf.get('sell_sm', 0)
        buy_sm = mf.get('buy_sm', 0)
        buy_lg = mf.get('buy_lg', 0)
        sell_lg = mf.get('sell_lg', 0)
        
        # Get cyq
        cyq = cyq_d.get(dt, {})
        profit_ratio = cyq.get('profit_ratio')
        
        # ── Position ──
        window = bars[i-19:i+1]
        min_low = min(b['low'] for b in window)
        max_high = max(b['high'] for b in window)
        rng = max_high - min_low
        if rng <= 0: continue
        pos_pct = (close - min_low) / rng * 100  # 0=20日最低, 100=20日最高
        
        # ── Amplitude ──
        amp = (bar['high'] - bar['low']) / bar['pre_close'] * 100 if bar['pre_close'] > 0 else 0
        
        # ── 5日持续放量检查 (前5日 vol 逐日放大, 不含今日) ──
        vol_5d_increasing = True
        if i >= 5:
            # 检查 i-5..i-1 共5日, 4个比较: vol[i-5] < vol[i-4] < ... < vol[i-1]
            for j in range(4):
                if bars[i-4+j]['vol'] <= bars[i-5+j]['vol']:
                    vol_5d_increasing = False
                    break
        else:
            vol_5d_increasing = False
        
        # ── 20日最低量检查 (今日量是20日最低) ──
        is_min_vol_20d = True
        if i >= 19:
            for j in range(1, 20):
                if bars[i-j]['vol'] < vol:
                    is_min_vol_20d = False
                    break
        else:
            is_min_vol_20d = False
        
        fwd_ret_5d, fwd_ret_10d, fwd_ret_20d = fwd[i] if i < n and fwd[i][0] is not None else (None, None, None)
        if fwd_ret_5d is None:
            continue
        
        signal = {
            'dt': dt, 'code': code, 'pct': pct, 'pos': pos_pct, 'amp': amp,
            'cm': cm, 'vr': vr, 'tr': tr, 'pe': pe, 'pb': pb,
            'fwd5': fwd_ret_5d, 'fwd10': fwd_ret_10d, 'fwd20': fwd_ret_20d,
            'vol_5d_inc': vol_5d_increasing,
            'vol_min_20d': is_min_vol_20d,
            'net_mf': net_mf, 'buy_elg': buy_elg, 'sell_elg': sell_elg,
            'sell_sm': sell_sm, 'buy_sm': buy_sm,
            'profit_ratio': profit_ratio,
        }
        all_signals.append(signal)

print(f"[{datetime.now()-t0}] Total signal candidates: {len(all_signals)}")

# ═══ Step 6: Define 5 strategies ═══

strategies = []

# C1: 恐慌+5日持续放量(主力提前埋伏) — 恐慌日前主力已持续吸筹5日, 今日恐慌放量
# Parameters: 底20% + 跌≤-5% + 前5日持续放量 + 振幅≥5% + VR≥1.0 + CM≤30亿
strategies.append({
    'name': 'C1_恐慌持续放量_微盘',
    'desc': '恐慌≤-5%+前5日持续放量+底20%+振幅≥5%+VR≥1.0+CM≤30亿',
    'filter': lambda s: (
        s['pct'] <= -5.0 and
        s['pos'] <= 20.0 and
        s['vol_5d_inc'] and  # 前5日持续放量
        s['amp'] >= 5.0 and
        s['vr'] >= 1.0 and
        s['cm'] <= 30
    )
})

# C2: 恐慌+中盘弹性(50-200亿) — 中盘股恐慌反弹, 无市值下界
strategies.append({
    'name': 'C2_恐慌中盘反弹',
    'desc': '恐慌≤-7%+底20%+振幅≥7%+VR≥1.0+CM 50-200亿',
    'filter': lambda s: (
        s['pct'] <= -7.0 and
        s['pos'] <= 20.0 and
        s['amp'] >= 7.0 and
        s['vr'] >= 1.0 and
        50 <= s['cm'] <= 200
    )
})

# C3: 恐慌+亏损股反弹(PE为负) — 亏损股恐慌到极致, 纯技术反弹
strategies.append({
    'name': 'C3_恐慌亏损股反弹',
    'desc': '恐慌≤-5%+亏损(pe<0)+底20%+振幅≥5%+VR≥1.2+CM≤50亿',
    'filter': lambda s: (
        s['pct'] <= -5.0 and
        s['pe'] is not None and s['pe'] < 0 and  # 亏损股(PE为负)
        s['pos'] <= 20.0 and
        s['amp'] >= 5.0 and
        s['vr'] >= 1.2 and
        s['cm'] <= 50
    )
})

# C4: 恐慌+极端振幅(≥10%)+巨量 — 极端博弈型
strategies.append({
    'name': 'C4_恐慌极端振幅巨量',
    'desc': '恐慌≤-7%+底20%+振幅≥10%+VR≥1.5+CM≤100亿',
    'filter': lambda s: (
        s['pct'] <= -7.0 and
        s['pos'] <= 20.0 and
        s['amp'] >= 10.0 and
        s['vr'] >= 1.5 and
        s['cm'] <= 100
    )
})

# C5: 恐慌+筹码深度亏损(获利比例≤10%) — 所有人都被套, 反弹阻力最小
strategies.append({
    'name': 'C5_恐慌筹码深度亏损',
    'desc': '恐慌≤-5%+底20%+获利比例≤10%+振幅≥5%+VR≥1.2+CM≤50亿',
    'filter': lambda s: (
        s['pct'] <= -5.0 and
        s['pos'] <= 20.0 and
        s['profit_ratio'] is not None and s['profit_ratio'] <= 10.0 and  # 筹码获利比例极低
        s['amp'] >= 5.0 and
        s['vr'] >= 1.2 and
        s['cm'] <= 50
    )
})

# ═══ Step 7: Run all strategies ═══
results = []
print(f"\n[{datetime.now()-t0}] Running strategies...")
for strat in strategies:
    signals = [s for s in all_signals if strat['filter'](s)]
    n = len(signals)
    
    if n == 0:
        results.append({**strat, 'signals': 0, 'wr': 0, 'ret5': 0, 'ret10': 0, 'ret20': 0, 'sharpe': 0, 'result': '无信号'})
        print(f"  {strat['name']}: 0 signals ❌")
        continue
    
    ret5_list = [s['fwd5'] for s in signals if s['fwd5'] is not None]
    ret10_list = [s['fwd10'] for s in signals if s['fwd10'] is not None]
    ret20_list = [s['fwd20'] for s in signals if s['fwd20'] is not None]
    
    wr = sum(1 for r in ret5_list if r > 0) / len(ret5_list) * 100 if ret5_list else 0
    r5 = sum(ret5_list) / len(ret5_list) if ret5_list else 0
    r10 = sum(ret10_list) / len(ret10_list) if ret10_list else 0
    r20 = sum(ret20_list) / len(ret20_list) if ret20_list else 0
    sharpe = calc_sharpe(ret5_list)
    
    passed = wr >= 52 and r5 >= 3.0 and n >= 200
    status = "✅ 全达标" if passed else "❌ 未达标"
    
    results.append({
        **strat,
        'signals': n,
        'wr': round(wr, 2),
        'ret5': round(r5, 2),
        'ret10': round(r10, 2),
        'ret20': round(r20, 2),
        'sharpe': round(sharpe, 3),
        'result': status,
    })
    print(f"  {strat['name']}: N={n}, WR={wr:.1f}%, R5={r5:.2f}%, R10={r10:.2f}%, R20={r20:.2f}%, Sharpe={sharpe:.3f} — {status}")

# ═══ Step 8: Output summary ═══
t_elapsed = datetime.now() - t0
print(f"\n{'='*60}")
print(f"Total time: {t_elapsed}")
print(f"{'='*60}")
print(f"\n{'Name':20s} {'N':>6s} {'WR%':>6s} {'R5%':>7s} {'R10%':>8s} {'R20%':>8s} {'Sharpe':>8s} {'Status':>12s}")
print('-'*75)
for r in results:
    print(f"{r['name']:20s} {r['signals']:>6d} {r['wr']:>5.1f}% {r['ret5']:>6.2f}% {r['ret10']:>7.2f}% {r['ret20']:>7.2f}% {r['sharpe']:>7.3f} {r['result']:>12s}")

# ═══ Step 9: Show top signal examples ═══
print(f"\n{'='*60}")
print("Top signals by 5D return for each strategy:")
print(f"{'='*60}")
for r in results:
    if r['signals'] == 0: continue
    print(f"\n--- {r['name']} (N={r['signals']}) ---")
    matching = [s for s in all_signals if r['filter'](s)]
    matching_sorted = sorted(matching, key=lambda s: -s['fwd5'])[:5]
    for s in matching_sorted:
        print(f"  {s['dt']} {s['code']} pct={s['pct']:.1f}% pos={s['pos']:.0f}% amp={s['amp']:.1f}% cm={s['cm']:.0f}亿 → R5={s['fwd5']:.1f}%")

# Output JSON for parsing
print(f"\n\n### JSON_OUTPUT ###")
print(json.dumps(results, ensure_ascii=False))
