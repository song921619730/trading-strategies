#!/usr/bin/env python3
"""
Experiment 20260509_v5_auto: Gold Volatility Regimes & Geopolitical Context

H1: Gold volatility compression releases are MORE explosive during geopolitical 
    escalation windows vs calm periods.
H2: Gold-US equity correlation drops during escalation (safe-haven flight).

Data: Tushare ClickHouse (FXCM daily). Gold + Silver full range; equities to 2023-06.
"""

import pandas as pd
import numpy as np
import requests
import warnings
warnings.filterwarnings('ignore')

CH_URL = "http://172.24.224.1:8123/?database=tushare"
CH_AUTH = ("ai_reader", "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ")

def ch_query(sql):
    sql = ' '.join(sql.split())
    r = requests.post(CH_URL, data=sql.encode('utf-8'), auth=CH_AUTH)
    r.raise_for_status()
    lines = r.text.strip().split('\n')
    if not lines or lines == ['']:
        return pd.DataFrame()
    data = [line.split('\t') for line in lines]
    return pd.DataFrame(data)

print("=" * 70)
print("EXPERIMENT 20260509_v5_auto: Gold Volatility Regimes & Geo Context")
print("=" * 70)

# ============================================================
# STEP 1: Fetch Data
# ============================================================
print("\n[1/6] Fetching data from ClickHouse...")

raw_data = {}
for name, code in [('Gold','XAUUSD.FXCM'), ('Silver','XAGUSD.FXCM'), 
                    ('SP500','SPX500.FXCM'), ('Nasdaq','NAS100.FXCM'), ('Dow','US30.FXCM')]:
    sql = f"SELECT trade_date, bid_open, bid_high, bid_low, bid_close FROM tushare_fx_daily WHERE ts_code = '{code}' ORDER BY trade_date"
    df = ch_query(sql)
    if len(df) > 100:
        df.columns = ['date','open','high','low','close']
        for c in ['open','high','low','close']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df['date'] = pd.to_datetime(df['date'])
        df = df.dropna(subset=['close'])
        df = df.drop_duplicates(subset=['date'], keep='first')
        df = df.set_index('date')
        raw_data[name] = df
        print(f"  {name:8s}: {len(df)} bars, {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")

available = list(raw_data.keys())

# Find common dates
common = raw_data[available[0]].index
for s in available[1:]:
    common = common.intersection(raw_data[s].index)
common = pd.DatetimeIndex(sorted(set(common)))
print(f"\n  Common dates: {len(common)} ({common[0].strftime('%Y-%m-%d')} to {common[-1].strftime('%Y-%m-%d')})")

# Build clean aligned DataFrame
ohlc = {}
for s in available:
    ohlc[s] = raw_data[s].loc[common].copy()

close = pd.DataFrame({s: ohlc[s]['close'] for s in available})
high = pd.DataFrame({s: ohlc[s]['high'] for s in available})
low = pd.DataFrame({s: ohlc[s]['low'] for s in available})

# ============================================================
# STEP 2: Compute Features
# ============================================================
print("\n[2/6] Computing features...")

# ATR(14) and compression for all assets
atr_pct = pd.DataFrame()
comp_ratio = pd.DataFrame()
for s in available:
    c, h, l = close[s], high[s], low[s]
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    ap = atr / c * 100
    am = ap.rolling(20).median()
    atr_pct[s] = ap
    comp_ratio[s] = ap / am

is_comp = comp_ratio < 0.7
sync_count = is_comp.sum(axis=1)

# Gold returns and big moves
gold_ret = close['Gold'].pct_change() * 100
gold_abs = gold_ret.abs()
big_thresh = gold_abs.rolling(60).median()
big_move = gold_abs > big_thresh

# Compression release: was compressed, now not
gold_cr = comp_ratio['Gold']
was_comp = gold_cr.shift(1) < 0.7
now_not = gold_cr >= 0.7
release = was_comp & now_not

print(f"  Compression releases detected: {release.sum()}")
print(f"  Big move threshold (median*2): {big_thresh.dropna().median():.2f}%")

# ============================================================
# STEP 3: Geopolitical Regimes
# ============================================================
print("\n[3/6] Defining geopolitical regimes...")

events = [
    ("2020-03-11", "WHO Pandemic Declaration", "esc"),
    ("2020-11-09", "Pfizer Vaccine", "deesc"),
    ("2021-08-15", "Afghanistan Taliban", "esc"),
    ("2022-02-24", "Russia-Ukraine War", "esc"),
    ("2022-03-20", "RU Peace Talks", "deesc"),
    ("2022-09-21", "RU Mobilization", "esc"),
    ("2023-06-23", "Wagner Mutiny", "esc"),
]

geo = pd.DataFrame(events, columns=['date','name','type'])
geo['date'] = pd.to_datetime(geo['date'])
geo = geo[(geo['date'] >= common[0]) & (geo['date'] <= common[-1])]

regime = pd.Series('normal', index=close.index)
for _, ev in geo.iterrows():
    ed = pd.Timestamp(ev['date'])
    diffs = (close.index - ed).to_series().apply(lambda x: abs(x.total_seconds()))
    idx = diffs.values.argmin()
    window = 20 if ev['type'] == 'esc' else 15
    regime.iloc[idx:idx+window] = ev['type']

print(f"  Events: {len(geo)}")
print(f"  Normal: {(regime=='normal').sum()}, Escalation: {(regime=='esc').sum()}, De-escalation: {(regime=='deesc').sum()}")

# ============================================================
# STEP 4: H1 - Compression Release by Regime
# ============================================================
print("\n[4/6] H1: Compression Release Explosiveness by Regime")

rel_dates = close.index[release]
results = []
for rd in rel_dates:
    idx = close.index.get_loc(rd)
    if idx + 5 >= len(close):
        continue
    reg = regime.iloc[idx]
    nxt = gold_abs.iloc[idx+1:idx+6]
    results.append({
        'date': rd, 'regime': reg,
        'big_move': bool(nxt.any()),
        'max_move': float(nxt.max()),
        'avg_move': float(nxt.mean()),
    })

rdf = pd.DataFrame(results)
print(f"\n  Total releases: {len(rdf)}")

h1_valid = False
h1_results = {}
if len(rdf) > 0:
    for reg in ['normal', 'esc', 'deesc']:
        sub = rdf[rdf['regime'] == reg]
        if len(sub) > 0:
            rate = sub['big_move'].mean() * 100
            mx = sub['max_move'].mean()
            print(f"  {reg:10s}: big_move_rate={rate:.1f}%  avg_max_move={mx:.2f}%  (n={len(sub)})")
    
    esc_r = rdf[rdf['regime'] == 'esc']
    norm_r = rdf[rdf['regime'] == 'normal']
    if len(esc_r) > 0 and len(norm_r) > 0:
        esc_rate = esc_r['big_move'].mean()
        norm_rate = norm_r['big_move'].mean()
        esc_max = esc_r['max_move'].mean()
        norm_max = norm_r['max_move'].mean()
        
        h1_valid = esc_max > norm_max * 1.2
        h1_results = {
            'total': len(rdf), 'esc_n': len(esc_r), 'norm_n': len(norm_r),
            'esc_rate': float(esc_rate), 'norm_rate': float(norm_rate),
            'esc_max': float(esc_max), 'norm_max': float(norm_max),
            'h1_validated': h1_valid,
        }
        print(f"\n  Esc vs Norm max move: {esc_max:.2f}% vs {norm_max:.2f}% ({(esc_max/norm_max-1)*100:+.0f}%)")
        print(f"  H1 {'VALIDATED' if h1_valid else 'NOT VALIDATED'}")

# ============================================================
# STEP 5: H2 - Gold-Stock Correlation by Regime
# ============================================================
print("\n[5/6] H2: Gold-Stock Correlation by Regime")

h2_valid = False
h2_results = {}
if 'SP500' in available:
    spx_ret = close['SP500'].pct_change() * 100
    roll_corr = gold_ret.rolling(20).corr(spx_ret)
    
    print(f"\n  Avg 20-day Gold-SP500 correlation by regime:")
    for reg in ['normal', 'esc', 'deesc']:
        mask = regime == reg
        if mask.sum() > 10:
            avg = roll_corr[mask].mean()
            print(f"    {reg:10s}: {avg:+.3f} (n={mask.sum()})")
            h2_results[f'{reg}_corr'] = float(avg)
    
    if 'esc_corr' in h2_results and 'normal_corr' in h2_results:
        delta = h2_results['esc_corr'] - h2_results['normal_corr']
        h2_valid = delta < -0.1
        h2_results['delta'] = float(delta)
        h2_results['h2_validated'] = h2_valid
        print(f"\n  Escalation vs Normal delta: {delta:+.3f}")
        print(f"  H2 {'VALIDATED' if h2_valid else 'NOT VALIDATED'}")
        
        # Per-event correlation
        print(f"\n  Per-event 20-day correlation:")
        for _, ev in geo.iterrows():
            ed = pd.Timestamp(ev['date'])
            diffs = (close.index - ed).to_series().apply(lambda x: abs(x.total_seconds()))
            idx = diffs.values.argmin()
            if idx + 20 < len(close):
                gc = gold_ret.iloc[idx:idx+20].corr(spx_ret.iloc[idx:idx+20])
                icon = "🔴" if ev['type'] == 'esc' else "🟢"
                print(f"    {icon} {ev['date'].strftime('%Y-%m-%d')} {ev['name']:30s}: {gc:+.3f}")
else:
    print("  SKIPPED: No SP500 data")

# ============================================================
# STEP 6: Current Regime
# ============================================================
print("\n[6/6] Current regime assessment...")

latest = close.index[-1]
print(f"  Date: {latest.strftime('%Y-%m-%d')}")
print(f"  Regime: {regime.iloc[-1]}")
print(f"  Gold CR: {gold_cr.iloc[-1]:.2f}")
print(f"  Sync: {sync_count.iloc[-1]:.0f}/{len(available)}")
for s in available:
    print(f"    {s:8s}: ${close[s].iloc[-1]:.2f}  CR={comp_ratio[s].iloc[-1]:.2f}")

# ============================================================
# OUTPUT
# ============================================================
print("\n" + "=" * 70)
print("RESULTS SUMMARY")
print("=" * 70)
print(f"\nH1: {'VALIDATED' if h1_valid else 'NOT VALIDATED'}")
if h1_results:
    print(f"  Releases: {h1_results.get('total',0)} total, {h1_results.get('esc_n',0)} esc, {h1_results.get('norm_n',0)} norm")
    print(f"  Esc max move: {h1_results.get('esc_max',0):.2f}% vs Norm: {h1_results.get('norm_max',0):.2f}%")
print(f"\nH2: {'VALIDATED' if h2_valid else 'NOT VALIDATED'}")
if h2_results.get('delta') is not None:
    print(f"  Correlation delta: {h2_results['delta']:+.3f}")
print("\n" + "=" * 70)
print("EXPERIMENT COMPLETE")
print("=" * 70)
