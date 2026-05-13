#!/usr/bin/env python3
"""Load H1 futures data, compute indicators, output structured summary."""

import sys
import os

# Ensure scripts directory is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from data_loader import load_data, compute_indicators, list_available_symbols

def main():
    # Step 1: List H1 symbols
    symbols = list_available_symbols("H1")
    print("=" * 80)
    print(f"H1 SYMBOLS FOUND: {len(symbols)}")
    print(f"Symbols: {symbols}")
    print("=" * 80)

    # Step 2: Load data for all H1 symbols
    dfs = load_data("H1", symbols)
    print(f"\nLoaded {len(dfs)}/{len(symbols)} symbols successfully.\n")

    # Step 3: Compute indicators for each symbol's DataFrame
    dfs_enriched = {}
    for sym, df in dfs.items():
        print(f"  Computing indicators for {sym}... ({len(df)} rows)")
        dfs_enriched[sym] = compute_indicators(df)

    # Step 4: Print structured summary
    print("\n")
    print("=" * 80)
    print("STRUCTURED DATA SUMMARY — H1 TIMEFRAME")
    print("=" * 80)

    total_all = 0
    total_signal_rows = 0

    for sym in sorted(dfs_enriched.keys()):
        df = dfs_enriched[sym]
        n_rows = len(df)
        total_all += n_rows

        # Date range
        dt_min = df.index.min().strftime("%Y-%m-%d %H:%M")
        dt_max = df.index.max().strftime("%Y-%m-%d %H:%M")

        # Columns
        cols = list(df.columns)
        indicator_cols = [c for c in cols if c not in [
            'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume'
        ]]

        # Session distribution
        session_counts = df['session'].value_counts().to_dict() if 'session' in df.columns else {}

        # Count rows with non-NaN indicators (signal rows = rows with at least atr14 and rsi14)
        signal_rows = df.dropna(subset=['atr14', 'rsi14']).shape[0]
        total_signal_rows += signal_rows

        print(f"\n{'─' * 70}")
        print(f"  {sym}")
        print(f"{'─' * 70}")
        print(f"  Rows:              {n_rows:>8,}")
        print(f"  Date Range:        {dt_min}  →  {dt_max}")
        print(f"  Signal Rows:       {signal_rows:>8,}  (rows with valid atr14 & rsi14)")
        print(f"  Indicator Columns: {', '.join(sorted(indicator_cols))}")
        print(f"  Session Dist:      {session_counts}")

        # Quick stats on key indicators
        if 'rsi14' in df.columns:
            rsi_mean = df['rsi14'].mean()
            rsi_std = df['rsi14'].std()
            print(f"  RSI14 (mean±std):  {rsi_mean:.2f} ± {rsi_std:.2f}")
        if 'atr14' in df.columns:
            atr_mean = df['atr14'].mean()
            atr_median = df['atr14'].median()
            print(f"  ATR14 (mean±med):  {atr_mean:.4f}  |  {atr_median:.4f}")
        if 'ma20' in df.columns and 'close' in df.columns:
            # Price vs MA20 ratio
            ratio = (df['close'] / df['ma20']).mean()
            print(f"  Close/MA20 ratio:  {ratio:.4f}")

    # Totals
    print(f"\n{'=' * 80}")
    print(f"  OVERALL TOTALS")
    print(f"{'=' * 80}")
    print(f"  Total symbols:      {len(dfs_enriched)}")
    print(f"  Total rows:         {total_all:>8,}")
    print(f"  Total signal rows:  {total_signal_rows:>8,}")
    print(f"  All available cols: {list(dfs_enriched[list(dfs_enriched.keys())[0]].columns) if dfs_enriched else 'N/A'}")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
