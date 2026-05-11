#!/usr/bin/env python3
"""M30 Data Summary — Load, compute indicators, print structured table."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from data_loader import load_data, compute_indicators, list_available_symbols

# ── 1. Check & Load ─────────────────────────────────────────────────
print("=" * 78)
print("  Loading M30 data ...")
print("=" * 78)

# First list to confirm
syms = list_available_symbols(timeframe="M30")
print(f"  Symbols found: {len(syms)} — {', '.join(syms)}\n")

# Load raw data
raw = load_data(timeframe="M30")
print(f"  Loaded {len(raw)} symbols\n")

# ── 2. Compute indicators ───────────────────────────────────────────
print("=" * 78)
print("  Computing indicators ...")
print("=" * 78)

enriched = {}
for sym, df in raw.items():
    try:
        enriched[sym] = compute_indicators(df)
        print(f"  ✓ {sym:>10s}  {len(df):>8,} rows  →  indicators added")
    except Exception as e:
        print(f"  ✗ {sym:>10s}  FAILED: {e}")
        enriched[sym] = df  # passthrough

print()

# ── 3. Compute per-symbol stats ─────────────────────────────────────
print("=" * 78)
print("  M30 STRUCTURED SUMMARY")
print("=" * 78)

header = f"  {'Symbol':<10s} {'Rows':>9s} {'Start Date':<19s} {'End Date':<19s} {'Bull%':>7s} {'ATR/closeμ':>10s} {'ATR/closeM':>10s} {'RSIμ':>7s}"
sep = "  " + "-" * 91

print(header)
print(sep)

total_rows = 0
total_bull_candles = 0
total_candles = 0
all_atr_ratios = []
all_rsi = []

rows_per_sym = []

for sym in sorted(enriched.keys()):
    df = enriched[sym]

    # Row count & date range
    n = len(df)
    total_rows += n
    start_dt = df.index[0].strftime("%Y-%m-%d %H:%M")
    end_dt = df.index[-1].strftime("%Y-%m-%d %H:%M")

    # Bullish % (using non-NaN open/close)
    valid = df[["open", "close"]].dropna()
    bull_count = (valid["close"] > valid["open"]).sum()
    total_candles += len(valid)
    total_bull_candles += bull_count
    bull_pct = 100.0 * bull_count / len(valid) if len(valid) > 0 else np.nan

    # ATR / close — use rows where both are non-NaN
    atr_close = df[["atr14", "close"]].dropna()
    if len(atr_close) > 0:
        atr_ratio = (atr_close["atr14"] / atr_close["close"]).dropna()
        atr_mean = float(atr_ratio.mean()) * 100  # as %
        atr_median = float(atr_ratio.median()) * 100
        all_atr_ratios.extend(atr_ratio.tolist())
    else:
        atr_mean = np.nan
        atr_median = np.nan

    # RSI mean
    rsi_vals = df["rsi14"].dropna()
    if len(rsi_vals) > 0:
        rsi_mean = float(rsi_vals.mean())
        all_rsi.extend(rsi_vals.tolist())
    else:
        rsi_mean = np.nan

    print(f"  {sym:<10s} {n:>9,} {start_dt:<19s} {end_dt:<19s} {bull_pct:>6.1f}% {atr_mean:>9.4f}% {atr_median:>9.4f}% {rsi_mean:>7.2f}")

    rows_per_sym.append((sym, n, bull_pct, atr_mean, rsi_mean))

print(sep)

# ── 4. Aggregate statistics ─────────────────────────────────────────
overall_bull_pct = 100.0 * total_bull_candles / total_candles if total_candles > 0 else np.nan
overall_atr_mean = 100.0 * np.mean(all_atr_ratios) if all_atr_ratios else np.nan
overall_atr_median = 100.0 * np.median(all_atr_ratios) if all_atr_ratios else np.nan
overall_rsi_mean = np.mean(all_rsi) if all_rsi else np.nan

print(f"  {'TOTAL / AVG':<10s} {total_rows:>9,} {'':19s} {'':19s} {overall_bull_pct:>6.1f}% {overall_atr_mean:>9.4f}% {overall_atr_median:>9.4f}% {overall_rsi_mean:>7.2f}")
print(f"  {'(14 symbols)':>10s}")
print("=" * 78)

# ── 5. Additional diagnostics ───────────────────────────────────────
print()
print("─" * 78)
print("  ADDITIONAL DIAGNOSTICS")
print("─" * 78)
print(f"  Total records (all symbols):       {total_rows:>12,}")
print(f"  Total non-NaN candles analysed:    {total_candles:>12,}")
print(f"  Bullish candles:                   {total_bull_candles:>12,}")
print(f"  Overall bull %:                    {overall_bull_pct:>11.2f}%")
print(f"  Overall ATR/close μ (mean):        {overall_atr_mean:>11.4f}%")
print(f"  Overall ATR/close median:          {overall_atr_median:>11.4f}%")
print(f"  Overall RSI μ (mean):              {overall_rsi_mean:>11.4f}")
print()
print(f"  Per-symbol row counts: {[n for _, n, _, _, _ in rows_per_sym]}")
print(f"  Min rows: {min(n for _, n, _, _, _ in rows_per_sym)}  Max rows: {max(n for _, n, _, _, _ in rows_per_sym)}")
print()

# ── 6. Volatility ranking (highest ATR close ratio first) ───────────
print("─" * 78)
print("  VOLATILITY RANKING (by mean ATR/close %)")
print("─" * 78)
ranked = sorted(rows_per_sym, key=lambda x: x[3], reverse=True)
for i, (sym, n, bull_pct, atr_mean, rsi_mean) in enumerate(ranked, 1):
    print(f"  {i:>2d}. {sym:<10s}  ATR/close μ={atr_mean:.4f}%  RSI μ={rsi_mean:.2f}  Bull={bull_pct:.1f}%  Rows={n:,}")

print()
print("=" * 78)
print("  M30 data summary complete — ready for Analyst.")
print("=" * 78)
