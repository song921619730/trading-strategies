#!/usr/bin/env python3
"""
Volatility Compression Study — v2 (Multi-threshold + Release Analysis)
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json

if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    exit(1)

rates = mt5.copy_rates_from_pos("XAUUSDm", mt5.TIMEFRAME_H1, 0, 8760)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)

# ATR
hl = df['high'] - df['low']
hc = abs(df['high'] - df['close'].shift(1))
lc = abs(df['low'] - df['close'].shift(1))
tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
df['atr'] = tr.rolling(window=14).mean()
df['atr_median'] = df['atr'].rolling(window=20).median()
df['atr_ratio'] = df['atr'] / df['atr_median']

# Forward returns
for h in [4, 8, 12, 24]:
    df[f'ret_{h}h'] = (df['close'].shift(-h) - df['close']) / df['close'] * 100
df['ret_8h_abs'] = df['ret_8h'].abs()

results = {}

for threshold in [0.5, 0.6, 0.7, 0.8, 0.9]:
    print(f"\n{'='*50}")
    print(f"THRESHOLD: ATR < {int(threshold*100)}% of 20-bar median")
    
    valid = df.dropna(subset=['atr_ratio', 'ret_4h', 'ret_8h'])
    comp = valid[valid['atr_ratio'] < threshold]
    norm = valid[valid['atr_ratio'] >= threshold]
    
    pct = len(comp) / len(valid) * 100
    print(f"  Compression bars: {len(comp)}/{len(valid)} ({pct:.1f}%)")
    
    # Forward 8H stats
    comp_ret = comp['ret_8h'].mean()
    norm_ret = norm['ret_8h'].mean()
    comp_abs = comp['ret_8h'].abs().mean()
    norm_abs = norm['ret_8h'].abs().mean()
    
    # Big move detection (> 1 std of normal)
    big_threshold = norm['ret_8h'].std()
    comp_big = (comp['ret_8h'].abs() > big_threshold).mean() * 100
    norm_big = (norm['ret_8h'].abs() > big_threshold).mean() * 100
    
    print(f"  8H mean return: comp={comp_ret:.4f}% vs norm={norm_ret:.4f}%")
    print(f"  8H avg |move|: comp={comp_abs:.4f}% vs norm={norm_abs:.4f}%")
    print(f"  Big move rate (>1σ): comp={comp_big:.1f}% vs norm={norm_big:.1f}%")
    
    results[f"threshold_{threshold}"] = {
        "count": len(comp),
        "pct": round(pct, 1),
        "8h_mean_return": round(comp_ret, 4),
        "8h_avg_abs_move": round(comp_abs, 4),
        "8h_big_move_rate": round(comp_big, 1),
        "normal_8h_mean": round(norm_ret, 4),
        "normal_big_move_rate": round(norm_big, 1),
    }

# RELEASE analysis: what happens when compression ENDS?
print(f"\n{'='*50}")
print(f"COMPRESSION RELEASE ANALYSIS (threshold < 0.8)")

valid = df.dropna(subset=['atr_ratio', 'ret_4h', 'ret_8h'])
compressed = valid['atr_ratio'] < 0.8
release = (~compressed) & compressed.shift(1)  # was compressed, now released
release_bars = valid[release == True]

print(f"  Release events: {len(release_bars)}")
if len(release_bars) > 5:
    print(f"  4H return after release: {release_bars['ret_4h'].mean():.4f}%")
    print(f"  8H return after release: {release_bars['ret_8h'].mean():.4f}%")
    print(f"  12H return after release: {release_bars['ret_12h'].mean():.4f}%")
    
    avg_move = valid['ret_8h'].abs().mean()
    release_big = (release_bars['ret_8h'].abs() > avg_move).mean() * 100
    print(f"  Big move rate after release: {release_big:.1f}%")
    
    results['release_08'] = {
        "count": len(release_bars),
        "4h_return": round(release_bars['ret_4h'].mean(), 4),
        "8h_return": round(release_bars['ret_8h'].mean(), 4),
        "12h_return": round(release_bars['ret_12h'].mean(), 4),
        "8h_big_move_rate": round(release_big, 1),
    }

# Trade Gate simulation: what if we lowered the vol filter?
print(f"\n{'='*50}")
print(f"TRADE GATE SIMULATION")
print("Pure AI CIO Trade Gate filters bars with ATR < 70% of daily avg.")
print("How many bars would be allowed at different thresholds?")

daily_avg_atr = df['atr'].rolling(24).mean()
df['atr_vs_daily'] = df['atr'] / daily_avg_atr

for threshold in [0.3, 0.5, 0.7, 0.9]:
    valid_bars = df.dropna(subset=['atr_vs_daily'])
    passed = valid_bars[valid_bars['atr_vs_daily'] >= threshold]
    print(f"  ATR >= {int(threshold*100)}% of daily avg: {len(passed)}/{len(valid_bars)} bars ({len(passed)/len(valid_bars)*100:.1f}%)")

with open("results.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\n✅ Results saved to results.json")

mt5.shutdown()
