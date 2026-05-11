#!/usr/bin/env python3
"""
researcher_m30_summary.py — T1 Researcher Profile
Loads M30 (and H1) futures data, computes indicators, prints structured summary table.
"""

import sys
import os

# Ensure scripts directory is on path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from data_loader import list_available_symbols, load_data, compute_indicators


def print_summary(data: dict, tf: str):
    """Print structured data summary table."""
    print(f"\n{'='*78}")
    print(f"  RESEARCHER DATA SUMMARY — {tf}")
    print(f"{'='*78}")
    print(f"  {'Symbol':<12} {'Rows':>10} {'From':<20} {'To':<20} {'Sessions':>8}")
    print(f"  {'-'*70}")
    total_rows = 0
    for sym in sorted(data.keys()):
        df = data[sym]
        rows = len(df)
        total_rows += rows
        start = df.index[0].strftime('%Y-%m-%d %H:%M')
        end = df.index[-1].strftime('%Y-%m-%d %H:%M')
        sessions = df['session'].nunique() if 'session' in df.columns else '?'
        print(f"  {sym:<12} {rows:>10} {start:<20} {end:<20} {sessions:>8}")
    print(f"  {'-'*70}")
    print(f"  {'TOTAL':<12} {total_rows:>10}  ({len(data)} symbols, {tf})")
    print(f"{'='*78}\n")


def main():
    print("=" * 78)
    print("  RESEARCHER PROFILE (T1) — Data Preparation for Analyst")
    print("=" * 78)

    # Step 1: Check data availability
    print("\n[1] Checking data availability ...")
    h1_syms = list_available_symbols(timeframe="H1")
    m30_syms = list_available_symbols(timeframe="M30")
    print(f"  H1 symbols:  {len(h1_syms)} — {h1_syms}")
    print(f"  M30 symbols: {len(m30_syms)} — {m30_syms}")

    # Confirm data exists (14 symbols expected)
    if len(m30_syms) < 14:
        print(f"  WARNING: Expected 14 M30 symbols, found {len(m30_syms)}")
    if len(h1_syms) < 14:
        print(f"  WARNING: Expected 14 H1 symbols, found {len(h1_syms)}")

    # Step 2: Load M30 data
    print("\n[2] Loading M30 data ...")
    m30_raw = load_data(timeframe="M30")
    print(f"  → {len(m30_raw)} symbols loaded")

    # Step 3: Load H1 data (also kept ready for Analyst)
    print("\n[3] Loading H1 data ...")
    h1_raw = load_data(timeframe="H1")
    print(f"  → {len(h1_raw)} symbols loaded")

    # Step 4: Compute indicators (M30)
    print("\n[4] Computing indicators (M30) ...")
    m30_data = {sym: compute_indicators(df) for sym, df in m30_raw.items()}
    print(f"  → Indicators computed for {len(m30_data)} symbols")

    # Step 5: Compute indicators (H1)
    print("\n[5] Computing indicators (H1) ...")
    h1_data = {sym: compute_indicators(df) for sym, df in h1_raw.items()}
    print(f"  → Indicators computed for {len(h1_data)} symbols")

    # Step 6: Print structured summary tables
    print("\n[6] Data Summary Tables")
    print_summary(m30_data, "M30")
    print_summary(h1_data, "H1")

    # Step 7: Extra statistics — bull ratio, avg ATR, session distribution
    print("[7] Extra Statistics")
    print("=" * 78)
    print(f"  {'Symbol':<12} {'Bull Ratio':>12} {'Avg ATR14':>12} {'Avg MA20':>12}")
    print(f"  {'-'*60}")
    for sym in sorted(m30_data.keys()):
        df = m30_data[sym]
        bull_ratio = (df['close'] > df['open']).mean()
        avg_atr = df['atr14'].mean()
        avg_ma20 = df['ma20'].mean()
        print(f"  {sym:<12} {bull_ratio:>11.2%} {avg_atr:>12.5f} {avg_ma20:>12.2f}")
    print(f"  {'-'*60}")

    # Session distribution
    print(f"\n  {'='*78}")
    print(f"  {'Trading Session Distribution (M30)':^78}")
    print(f"  {'='*78}")
    print(f"  {'Symbol':<12} {'Asia':>8} {'Europe':>8} {'US':>8} {'Total':>8}")
    print(f"  {'-'*48}")
    for sym in sorted(m30_data.keys()):
        df = m30_data[sym]
        session_counts = df['session'].value_counts()
        asia = session_counts.get('asia', 0)
        europe = session_counts.get('europe', 0)
        us = session_counts.get('us', 0)
        total = asia + europe + us
        print(f"  {sym:<12} {asia:>8} {europe:>8} {us:>8} {total:>8}")
    print(f"  {'-'*48}")
    total_asia = sum(df['session'].value_counts().get('asia', 0) for df in m30_data.values())
    total_europe = sum(df['session'].value_counts().get('europe', 0) for df in m30_data.values())
    total_us = sum(df['session'].value_counts().get('us', 0) for df in m30_data.values())
    grand_total = total_asia + total_europe + total_us
    print(f"  {'TOTAL':<12} {total_asia:>8} {total_europe:>8} {total_us:>8} {grand_total:>8}")

    # RSI extremes
    print(f"\n  {'='*78}")
    print(f"  {'RSI14 Extremes (M30) — Last 50 Bars':^78}")
    print(f"  {'='*78}")
    for sym in sorted(m30_data.keys()):
        df = m30_data[sym]
        recent = df.tail(50)
        rsi_min = recent['rsi14'].min()
        rsi_max = recent['rsi14'].max()
        rsi_last = recent['rsi14'].iloc[-1]
        print(f"  {sym:<12}  last_rsi={rsi_last:>6.2f}  min_rsi_50={rsi_min:>6.2f}  max_rsi_50={rsi_max:>6.2f}")

    print()
    print("=" * 78)
    print("  Data preparation complete. Ready for Analyst.")
    print("=" * 78)


if __name__ == "__main__":
    main()
