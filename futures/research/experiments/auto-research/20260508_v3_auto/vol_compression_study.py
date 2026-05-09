#!/usr/bin/env python3
"""
Volatility Compression Breakout Study — Gold (XAUUSD)
Hypothesis: After volatility compression (ATR < 50% of 20-day median),
            gold tends to make directional moves in the next 4-8 H1 bars.
Tests whether the Pure AI CIO Trade Gate volatility filter might be
missing breakout opportunities.
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

WIN_PYTHON = "C:/Users/gj/AppData/Local/Programs/Python/Python310/python.exe"

# Connect to MT5
if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    exit(1)

# Fetch 1 year of H1 gold data
print("Fetching XAUUSDm H1 data...")
rates = mt5.copy_rates_from_pos("XAUUSDm", mt5.TIMEFRAME_H1, 0, 8760)  # ~1 year
if rates is None or len(rates) == 0:
    print("No data from MT5")
    mt5.shutdown()
    exit(1)

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)
print(f"Loaded {len(df)} H1 bars, from {df.index.min()} to {df.index.max()}")

# Calculate ATR (14-period)
high_low = df['high'] - df['low']
high_close = abs(df['high'] - df['close'].shift(1))
low_close = abs(df['low'] - df['close'].shift(1))
tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df['atr'] = tr.rolling(window=14).mean()

# Calculate 20-period rolling median ATR
df['atr_median'] = df['atr'].rolling(window=20).median()

# Volatility compression: ATR < 50% of median
df['compressed'] = df['atr'] < (df['atr_median'] * 0.5)

# Forward returns (4H, 8H, 12H)
for h in [4, 8, 12, 24]:
    df[f'ret_{h}h'] = (df['close'].shift(-h) - df['close']) / df['close'] * 100

# Direction accuracy (absolute move > average move)
avg_move = df['ret_8h'].abs().mean()
df['big_move'] = df['ret_8h'].abs() > avg_move

# Filter: only compressed periods with valid data
valid = df.dropna(subset=['atr', 'atr_median', 'ret_4h', 'ret_8h', 'ret_12h', 'ret_24h'])
compressed = valid[valid['compressed'] == True]
normal = valid[valid['compressed'] == False]

print(f"\n{'='*60}")
print(f"VOLATILITY COMPRESSION ANALYSIS — XAUUSDm H1")
print(f"{'='*60}")
print(f"Total bars: {len(valid)}")
print(f"Compression periods: {len(compressed)} ({len(compressed)/len(valid)*100:.1f}%)")
print(f"Normal periods: {len(normal)}")

print(f"\n--- Forward Returns ---")
for h in [4, 8, 12, 24]:
    col = f'ret_{h}h'
    print(f"\n  {h}H Return:")
    print(f"    Compression: mean={compressed[col].mean():.4f}%, std={compressed[col].std():.4f}%")
    print(f"    Normal:      mean={normal[col].mean():.4f}%, std={normal[col].std():.4f}%")
    
    # T-test approximation (simple)
    diff = compressed[col].mean() - normal[col].mean()
    pooled_std = np.sqrt((compressed[col].std()**2 + normal[col].std()**2) / 2)
    if pooled_std > 0 and len(compressed) > 1:
        t_stat = diff / (pooled_std / np.sqrt(len(compressed)))
        print(f"    Diff: {diff:.4f}%, t-stat: {t_stat:.2f} (>|2| = significant)")

print(f"\n--- Move Magnitude ---")
avg_compressed_move = compressed['ret_8h'].abs().mean()
avg_normal_move = normal['ret_8h'].abs().mean()
print(f"  Compression avg |8H return|: {avg_compressed_move:.4f}%")
print(f"  Normal avg |8H return|: {avg_normal_move:.4f}%")
print(f"  Compression/Normal ratio: {avg_compressed_move/avg_normal_move:.2f}x")

print(f"\n--- Directional Bias ---")
print(f"  Compression: up={compressed['ret_8h'].mean() > 0} (mean={compressed['ret_8h'].mean():.4f}%)")
print(f"  Normal: up={normal['ret_8h'].mean() > 0} (mean={normal['ret_8h'].mean():.4f}%)")

# Save results for report
results = {
    "total_bars": len(valid),
    "compression_count": len(compressed),
    "compression_pct": round(len(compressed)/len(valid)*100, 1),
    "forward_returns": {},
}
for h in [4, 8, 12, 24]:
    col = f'ret_{h}h'
    results["forward_returns"][f"{h}h"] = {
        "comp_mean": round(compressed[col].mean(), 4),
        "comp_std": round(compressed[col].std(), 4),
        "normal_mean": round(normal[col].mean(), 4),
        "normal_std": round(normal[col].std(), 4),
    }
results["big_move_ratio"] = round(avg_compressed_move/avg_normal_move, 2)
results["comp_directional_bias"] = round(compressed['ret_8h'].mean(), 4)

with open("results.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\n✅ Results saved to results.json")

mt5.shutdown()
