#!/usr/bin/env python3
"""T3 iter12: 反转低吸回测 — 5组参数组合 (20200101-20260511)"""
import json, subprocess, sys, math, os
from datetime import datetime
from collections import defaultdict

CH_QUERY = "/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py"
START_DATE = '20200101'
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

def calc_sharpe(returns):
    if len(returns) < 10: return 0
    mean_r = sum(returns) / len(returns)
    if mean_r <= 0: return 0
    var = sum((r-mean_r)**2 for r in returns) / len(returns)
    std = math.sqrt(var) if var > 0 else 1e-10
    return mean_r/std * math.sqrt(252/5)

t0 = datetime.now()

# ═══ Step 1: Load stock daily ═══
print(f"[{datetime.now()-t0}] Loading stock daily...", flush=True)
rows = ch_query(f"""
SELECT ts_code, trade_date, open, high, low, close, pre_close, pct_chg, vol, amount
FROM tushare.tushare_stock_daily AS s FINAL
WHERE s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
  AND s.ts_code NOT LIKE '920%'
  AND s.ts_code NOT IN (SELECT ts_code FROM tushare.tushare_stock_basic FINAL WHERE name LIKE '%ST%')
  AND s.trade_date >= '{START_DATE}' AND s.trade_date <= '{END_DATE}'
ORDER BY s.ts_code, s.trade_date
""")
print(f"[{datetime.now()-t0}] Daily: {len(rows)} rows from {len(set(r['ts_code'] for r in rows))} stocks", flush=True)

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

# ═══ Step 2: Load daily_basic (PE/PB/VR/TR/CM/dv) ═══
print(f"[{datetime.now()-t0}] Loading daily_basic...", flush=True)
basic_rows = ch_query(f"""
SELECT ts_code, trade_date, pe_ttm, pb, dv_ratio, turnover_rate_f, volume_ratio, circ_mv
FROM tushare.tushare_daily_basic AS b FINAL
WHERE b.trade_date >= '{START_DATE}' AND b.trade_date <= '{END_DATE}'
ORDER BY b.ts_code, b.trade_date
""")
print(f"[{datetime.now()-t0}] Daily_basic: {len(basic_rows)} rows", flush=True)

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

# ═══ Step 3: Load moneyflow (for buy_elg_ratio) ═══
print(f"[{datetime.now()-t0}] Loading moneyflow...", flush=True)
mf_rows = ch_query(f"""
SELECT ts_code, trade_date, buy_elg_amount, sell_elg_amount
FROM tushare.tushare_moneyflow AS m FINAL
WHERE m.trade_date >= '{START_DATE}' AND m.trade_date <= '{END_DATE}'
ORDER BY m.ts_code, m.trade_date
""")
print(f"[{datetime.now()-t0}] Moneyflow: {len(mf_rows)} rows", flush=True)

stock_mf = defaultdict(dict)
for r in mf_rows:
    code = r['ts_code']
    dt = str(r['trade_date']).replace('-','')
    stock_mf[code][dt] = {
        'buy_elg': float(r['buy_elg_amount'] or 0),
        'sell_elg': float(r['sell_elg_amount'] or 0),
    }

# ═══ Step 4: Compute features per stock ═══
print(f"[{datetime.now()-t0}] Computing features...", flush=True)
all_signals = []

n_stocks = len(stock_bars)
si = 0
for code, bars in stock_bars.items():
    si += 1
    if si % 500 == 0:
        print(f"  ...{si}/{n_stocks} stocks processed, {len(all_signals)} signals found so far", flush=True)

    n = len(bars)
    basic_d = stock_basic.get(code, {})
    mf_d = stock_mf.get(code, {})

    for i in range(n):
        if i < 25: continue  # Need 20d for position + buffer for consecutive checks

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
        tr = bd.get('tr', 0)  # Already in % (e.g. 1.78 = 1.78%)
        vr = bd.get('vr', 0)
        cm = bd.get('cm', 0) / 10000  # Convert 万元→亿

        # Get moneyflow
        mf = mf_d.get(dt, {})
        buy_elg = mf.get('buy_elg', 0)
        buy_elg_ratio = (buy_elg / amount * 100) if amount > 0 else 0  # 超大单占比%

        # ── Position (底20%: 20日位置) ──
        window = bars[max(0,i-19):i+1]
        min_low = min(b['low'] for b in window)
        max_high = max(b['high'] for b in window)
        rng = max_high - min_low
        if rng <= 0: continue
        pos_pct = (close - min_low) / rng * 100
        # pos_pct=0 means lowest in 20d, =100 means highest

        # ── Amplitude (振幅) ──
        amp = (bar['high'] - bar['low']) / bar['pre_close'] * 100 if bar['pre_close'] > 0 else 0

        # ── 连续恐慌: check yesterday also ≤-3% ──
        prev_pct = bars[i-1]['pct_chg'] if i >= 1 else 0
        consecutive_panic = (pct <= -3.0 and prev_pct <= -3.0)

        # ── Forward returns ──
        if i + 4 < n:
            fwd5 = (bars[i+4]['close'] / close - 1) * 100
            fwd10 = (bars[i+9]['close'] / close - 1) * 100 if i+9 < n else None
            fwd20 = (bars[i+19]['close'] / close - 1) * 100 if i+19 < n else None
        else:
            continue

        signal = {
            'dt': dt, 'code': code, 'pct': pct, 'pos': pos_pct, 'amp': amp,
            'cm': cm, 'vr': vr, 'tr': tr, 'pe': pe, 'pb': pb, 'dv': dv,
            'buy_elg_ratio': buy_elg_ratio,
            'prev_pct': prev_pct,
            'consecutive_panic': consecutive_panic,
            'fwd5': fwd5, 'fwd10': fwd10, 'fwd20': fwd20,
        }
        all_signals.append(signal)

print(f"[{datetime.now()-t0}] Total signal candidates: {len(all_signals)}", flush=True)

# ═══ Step 5: Define 5 strategies ═══

strategies = [
    {
        'name': 'C1: 恐慌-6%微调',
        'desc': '恐慌≤-6%+底20%+振幅≥7%+VR≥1.3+PE≤30+PB≤3+CM≤50亿',
        'params': {'pct_chg_max': -6, 'pos_max': 20, 'amp_min': 7, 'vr_min': 1.3, 'pe_max': 30, 'pb_max': 3, 'cm_max': 50},
        'filter': lambda s: (
            s['pct'] <= -6.0 and s['pos'] <= 20.0 and s['amp'] >= 7.0 and
            s['vr'] >= 1.3 and
            s['pe'] is not None and s['pe'] <= 30 and
            s['pb'] is not None and s['pb'] <= 3 and
            s['cm'] <= 50
        )
    },
    {
        'name': 'C2: 连续恐慌×主力承接',
        'desc': '连续2日恐慌≤-3%+底20%+振幅≥5%+VR≥1.0+buy_elg_ratio≥3%+CM≤50亿',
        'params': {'consecutive_panic': True, 'pos_max': 20, 'amp_min': 5, 'vr_min': 1.0, 'buy_elg_ratio_min': 3, 'cm_max': 50},
        'filter': lambda s: (
            s['consecutive_panic'] and s['pos'] <= 20.0 and s['amp'] >= 5.0 and
            s['vr'] >= 1.0 and s['buy_elg_ratio'] >= 3.0 and
            s['cm'] <= 50
        )
    },
    {
        'name': 'C3: 恐慌价值扩容',
        'desc': '恐慌≤-5%+底20%+振幅≥6%+VR≥1.0+PE≤20+PB≤2+dv≥2%+CM≤100亿',
        'params': {'pct_chg_max': -5, 'pos_max': 20, 'amp_min': 6, 'vr_min': 1.0, 'pe_max': 20, 'pb_max': 2, 'dv_min': 2, 'cm_max': 100},
        'filter': lambda s: (
            s['pct'] <= -5.0 and s['pos'] <= 20.0 and s['amp'] >= 6.0 and
            s['vr'] >= 1.0 and
            s['pe'] is not None and s['pe'] <= 20 and
            s['pb'] is not None and s['pb'] <= 2 and
            s['dv'] >= 2.0 and s['cm'] <= 100
        )
    },
    {
        'name': 'C4: 恐慌筹码锁定',
        'desc': '恐慌≤-5%+底20%+振幅≥5%+VR≥1.2+TR 0.3-3%+CM≤50亿',
        'params': {'pct_chg_max': -5, 'pos_max': 20, 'amp_min': 5, 'vr_min': 1.2, 'tr_min': 0.3, 'tr_max': 3, 'cm_max': 50},
        'filter': lambda s: (
            s['pct'] <= -5.0 and s['pos'] <= 20.0 and s['amp'] >= 5.0 and
            s['vr'] >= 1.2 and 0.3 <= s['tr'] <= 3.0 and s['cm'] <= 50
        )
    },
    {
        'name': 'C5: 恐慌放量微盘',
        'desc': '恐慌≤-7%+底15%+振幅≥7%+VR≥1.5+CM≤30亿',
        'params': {'pct_chg_max': -7, 'pos_max': 15, 'amp_min': 7, 'vr_min': 1.5, 'cm_max': 30},
        'filter': lambda s: (
            s['pct'] <= -7.0 and s['pos'] <= 15.0 and s['amp'] >= 7.0 and
            s['vr'] >= 1.5 and s['cm'] <= 30
        )
    },
]

# ═══ Step 6: Run all strategies ═══
results = []
print(f"\n[{datetime.now()-t0}] Running strategies...", flush=True)
for strat in strategies:
    signals = [s for s in all_signals if strat['filter'](s)]
    n = len(signals)

    if n == 0:
        results.append({
            'name': strat['name'],
            'params': strat['params'],
            'signals': 0, 'wr': 0, 'ret5': 0, 'ret10': 0, 'ret20': 0, 'sharpe': 0,
            'result': '无信号'
        })
        print(f"  {strat['name']}: 0 signals ❌", flush=True)
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
        'name': strat['name'],
        'params': strat['params'],
        'signals': n,
        'wr': round(wr, 2),
        'ret5': round(r5, 2),
        'ret10': round(r10, 2),
        'ret20': round(r20, 2),
        'sharpe': round(sharpe, 3),
        'result': status,
    })
    print(f"  {strat['name']}: N={n}, WR={wr:.1f}%, R5={r5:.2f}%, R10={r10:.2f}%, R20={r20:.2f}%, Sharpe={sharpe:.3f} — {status}", flush=True)

# ═══ Step 7: Output summary ═══
t_elapsed = datetime.now() - t0
print(f"\n{'='*80}", flush=True)
print(f"T3 Iter12 反转低吸回测 — Total time: {t_elapsed}", flush=True)
print(f"{'='*80}", flush=True)
print(f"\n{'Name':30s} {'N':>6s} {'WR%':>6s} {'R5%':>7s} {'R10%':>8s} {'R20%':>8s} {'Sharpe':>8s} {'Status':>12s}", flush=True)
print('-'*78, flush=True)
for r in results:
    print(f"{r['name']:30s} {r['signals']:>6d} {r['wr']:>5.1f}% {r['ret5']:>6.2f}% {r['ret10']:>7.2f}% {r['ret20']:>7.2f}% {r['sharpe']:>7.3f} {r['result']:>12s}", flush=True)

# ═══ Step 8: Show top signal examples ═══
print(f"\n{'='*80}", flush=True)
print("Top signals by 5D return for each strategy:", flush=True)
print(f"{'='*80}", flush=True)
for strat, r in zip(strategies, results):
    if r['signals'] == 0: continue
    print(f"\n--- {r['name']} (N={r['signals']}) ---", flush=True)
    matching = [s for s in all_signals if strat['filter'](s)]
    matching_sorted = sorted(matching, key=lambda s: -s['fwd5'])[:5]
    for s in matching_sorted:
        print(f"  {s['dt']} {s['code']} pct={s['pct']:.1f}% pos={s['pos']:.0f}% amp={s['amp']:.1f}% cm={s['cm']:.0f}亿 vr={s['vr']:.1f} → R5={s['fwd5']:.1f}%", flush=True)

# ═══ Step 9: Final JSON output ═══
output_json = {
    "analyst": "T3",
    "time_range": f"{START_DATE}-{END_DATE}",
    "combos": []
}
for r in results:
    combo = {
        "name": r['name'],
        "params": r['params'],
        "sql": f"-- See params in code for T3 iter12",
        "results": {
            "signal_count": r['signals'],
            "wr_5d": r['wr'],
            "ret_5d": r['ret5'],
            "ret_10d": r['ret10'],
            "ret_20d": r['ret20'],
            "sharpe_5d": r['sharpe']
        }
    }
    output_json["combos"].append(combo)

print(f"\n\n### JSON_OUTPUT ###", flush=True)
print(json.dumps(output_json, ensure_ascii=False, indent=2))
