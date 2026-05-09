#!/usr/bin/env python3
"""
Cross-Asset Volatility Resonance Study (MT5 Data)
Hypothesis: When multiple futures simultaneously enter low-volatility regimes,
            the subsequent breakout is stronger and faster than single-asset compression.
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

UTC8 = timezone(timedelta(hours=8))
print("=== Cross-Asset Volatility Resonance Study (MT5) ===")
print(f"Time: {datetime.now(UTC8).strftime('%Y-%m-%d %H:%M:%S')} UTC+8")
print()

# ============================================================
# 1. CONNECT TO MT5
# ============================================================
if not mt5.initialize():
    print("FAIL: MT5 initialization failed")
    exit(1)
print("OK: MT5 connected")

# ============================================================
# 2. DATA COLLECTION
# ============================================================
# Exness symbols (with 'm' suffix)
SYMBOLS = ["XAUUSDm", "XAGUSDm", "USOILm", "UKOILm", "XCUUSDm", "XNGUSDm", "US100m", "US30m"]
TIMEFRAME = mt5.TIMEFRAME_D1

data = {}
for sym in SYMBOLS:
    rates = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, 800)
    if rates is not None and len(rates) > 100:
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        data[sym] = df
        print(f"  OK {sym}: {len(df)} bars ({df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')})")
    else:
        print(f"  WARN {sym}: insufficient data")

mt5.shutdown()

if len(data) < 3:
    print(f"ERROR: Need at least 3 symbols, got {len(data)}")
    exit(1)

print(f"\nLoaded {len(data)} symbols for analysis.")
print()

# ============================================================
# 3. VOLATILITY REGIME DETECTION
# ============================================================
print("Detecting volatility regimes...")

regime_data = {}
for sym, df in data.items():
    d = df.copy()
    
    # True Range
    d["TR"] = np.maximum(d["high"] - d["low"],
                         np.maximum(abs(d["high"] - d["close"].shift(1)),
                                    abs(d["low"] - d["close"].shift(1))))
    
    # ATR (14-day)
    d["ATR"] = d["TR"].rolling(14).mean()
    
    # Normalized ATR (% of price)
    d["ATR_pct"] = d["ATR"] / d["close"] * 100
    
    # 20-day median of ATR_pct
    d["ATR_median"] = d["ATR_pct"].rolling(20).median()
    
    # Compression ratio
    d["compression_ratio"] = d["ATR_pct"] / d["ATR_median"]
    
    # Low vol regime
    d["is_low_vol"] = d["compression_ratio"] < 0.7
    
    # Forward returns
    d["fwd_return_5d"] = d["close"].shift(-5) / d["close"] - 1
    d["fwd_abs_return_5d"] = abs(d["fwd_return_5d"])
    
    regime_data[sym] = d

# ============================================================
# 4. BUILD CROSS-ASSET PANEL
# ============================================================
print("Building synchronization panel...")

all_dates = set()
for d in regime_data.values():
    all_dates.update(d.index)
all_dates = sorted(all_dates)

panel = pd.DataFrame(index=all_dates)
for sym, d in regime_data.items():
    short = sym.replace("m", "")
    panel[f"{short}_is_low"] = d["is_low_vol"]
    panel[f"{short}_ratio"] = d["compression_ratio"]
    panel[f"{short}_fwd_abs"] = d["fwd_abs_return_5d"]
    panel[f"{short}_fwd_ret"] = d["fwd_return_5d"]

low_vol_cols = [c for c in panel.columns if c.endswith("_is_low")]
panel["low_vol_count"] = panel[low_vol_cols].sum(axis=1)
panel = panel.dropna(subset=low_vol_cols)
print(f"  Panel: {len(panel)} aligned trading days")

# ============================================================
# 5. REGIME ANALYSIS
# ============================================================
print("\nBreakout strength by regime:")
print("=" * 70)

regime_stats = []
for count in range(0, len(low_vol_cols) + 1):
    mask = panel["low_vol_count"] == count
    n = mask.sum()
    if n == 0:
        continue
    
    fwd_cols = [c for c in panel.columns if c.endswith("_fwd_abs")]
    avg_fwd = panel.loc[mask, fwd_cols].mean().mean() * 100
    
    label = {0: "Normal vol", 1: "Single", 2: "Dual sync", 3: "Triple sync", 
             4: "Quad sync", 5: "Penta sync", 6: "Hex sync", 7: "Hepta sync", 8: "Full sync"}
    regime_stats.append({"count": count, "n": int(n), "avg_move": round(avg_fwd, 4)})
    print(f"  {label.get(count, f'{count}-sync')} ({count}): {n} days, avg 5-day move = {avg_fwd:.4f}%")

# ============================================================
# 6. TRANSITION ANALYSIS
# ============================================================
print("\n" + "=" * 70)
print("Transition Analysis: After synchronized compression...")

# Test different sync thresholds
for threshold in [3, 4, 5]:
    sync_mask = panel["low_vol_count"] >= threshold
    if sync_mask.sum() == 0:
        continue
    
    next_not_sync = panel["low_vol_count"].shift(-1) < threshold
    release_mask = sync_mask & next_not_sync
    
    n_sync = sync_mask.sum()
    n_release = release_mask.sum()
    
    print(f"\n  Threshold: {threshold}+ assets in compression")
    print(f"    Sync days: {n_sync}")
    print(f"    Release events: {n_release}")
    
    if n_release > 5:
        fwd_cols = [c for c in panel.columns if c.endswith("_fwd_abs")]
        release_fwd = panel.loc[release_mask, fwd_cols].mean().mean()
        baseline_fwd = panel.loc[~sync_mask, fwd_cols].mean().mean()
        
        print(f"    Baseline move: {baseline_fwd*100:.4f}%")
        print(f"    Release move:  {release_fwd*100:.4f}%")
        print(f"    Enhancement:   {(release_fwd/baseline_fwd - 1)*100:.1f}%")
        
        # Statistical significance (simple t-test approximation)
        from scipy import stats as sp_stats
        release_vals = panel.loc[release_mask, fwd_cols].stack().dropna()
        baseline_vals = panel.loc[~sync_mask, fwd_cols].stack().dropna()
        
        if len(release_vals) > 2 and len(baseline_vals) > 2:
            t_stat, p_value = sp_stats.ttest_ind(release_vals, baseline_vals, equal_var=False)
            print(f"    T-test: t={t_stat:.3f}, p={p_value:.4f} {'*' if p_value < 0.05 else ''}{'**' if p_value < 0.01 else ''}")

# ============================================================
# 7. DIRECTIONAL BIAS
# ============================================================
print("\n" + "=" * 70)
print("Directional Analysis:")

for threshold in [3, 4]:
    mask = panel["low_vol_count"] >= threshold
    if mask.sum() < 10:
        continue
    
    ret_cols = [c for c in panel.columns if c.endswith("_fwd_ret")]
    sub = panel.loc[mask, ret_cols].stack().dropna()
    up = (sub > 0).sum()
    down = (sub < 0).sum()
    total = len(sub)
    avg_ret = sub.mean() * 100
    print(f"  {threshold}+ sync: {total} obs, Up={up} ({up/total*100:.1f}%), Down={down} ({down/total*100:.1f}%), avg_ret={avg_ret:.4f}%")

# ============================================================
# 8. DETAILED: Per-asset behavior during sync
# ============================================================
print("\n" + "=" * 70)
print("Per-Asset Behavior During 3+ Sync:")

sync_mask = panel["low_vol_count"] >= 3
for col in low_vol_cols:
    short = col.replace("_is_low", "")
    fwd_abs = f"{short}_fwd_abs"
    fwd_ret = f"{short}_fwd_ret"
    
    if fwd_abs in panel.columns:
        during = panel.loc[sync_mask, fwd_abs].mean() * 100
        outside = panel.loc[~sync_mask, fwd_abs].mean() * 100
        print(f"  {short}: during sync={during:.4f}%, outside={outside:.4f}%, diff={(during/outside-1)*100:.1f}%")

# ============================================================
# 9. SAVE SUMMARY
# ============================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

# Best threshold result
best_threshold = 3
sync_m = panel["low_vol_count"] >= best_threshold
rel_m = sync_m & (panel["low_vol_count"].shift(-1) < best_threshold)
fwd_cols = [c for c in panel.columns if c.endswith("_fwd_abs")]
if rel_m.sum() > 0:
    base = panel.loc[~sync_m, fwd_cols].mean().mean()
    rel = panel.loc[rel_m, fwd_cols].mean().mean()

print(f"  Symbols: {list(data.keys())}")
print(f"  Total days: {len(panel)}")
print(f"  3+ sync days: {sync_m.sum()}")
print(f"  Release events: {rel_m.sum()}")
print(f"  Baseline move: {base*100:.4f}%")
print(f"  Release move: {rel*100:.4f}%")
print(f"  Enhancement: {(rel/base-1)*100:.1f}%")
