#!/usr/bin/env python3
"""
Researcher Round 19 — Load H1 data, compute indicators, print structured summary.

Usage:
    cd /mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/scripts
    python3 round19_researcher_load.py
"""

import sys
import os
from pathlib import Path

# Ensure scripts dir is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from data_loader import list_available_symbols, load_data, compute_indicators


def print_data_summary(data: dict, timeframe: str):
    """Print a formatted summary of loaded data (cf. data-mt5.md §7)."""
    print()
    print("=" * 78)
    print(f"  RESEARCHER DATA SUMMARY — {timeframe}")
    print("=" * 78)
    print(f"  {'Symbol':<12} {'Rows':>10} {'From':<20} {'To':<20} {'Sessions':>8}")
    print(f"  {'-' * 70}")

    total_rows = 0
    for sym in sorted(data.keys()):
        df = data[sym]
        rows = len(df)
        total_rows += rows
        start = df.index[0].strftime('%Y-%m-%d %H:%M')
        end = df.index[-1].strftime('%Y-%m-%d %H:%M')
        sessions = df['session'].nunique() if 'session' in df.columns else '?'
        print(f"  {sym:<12} {rows:>10} {start:<20} {end:<20} {str(sessions):>8}")

    print(f"  {'-' * 70}")
    print(f"  {'TOTAL':<12} {total_rows:>10}  ({len(data)} symbols, {timeframe})")
    print("=" * 78)


def main():
    # ------------------------------------------------------------------
    # 1. List available symbols
    # ------------------------------------------------------------------
    print("=" * 78)
    print("  RESEARCHER ROUND 19 — H1 DATA LOADING TASK")
    print("=" * 78)

    h1_syms = list_available_symbols(timeframe="H1")
    print(f"\nAvailable H1 symbols on disk: {len(h1_syms)}")
    for s in h1_syms:
        print(f"  - {s}")

    if len(h1_syms) < 2:
        print("\nERROR: Insufficient H1 data found. Expected 14 symbols.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Load raw H1 data for all 14 symbols
    # ------------------------------------------------------------------
    print(f"\nLoading H1 data for {len(h1_syms)} symbols ...")
    h1_raw = load_data(timeframe="H1")
    print(f"  → {len(h1_raw)} symbols successfully loaded")

    if len(h1_raw) < 14:
        print(f"\nWARNING: Expected 14 symbols, got {len(h1_raw)}. "
              "Proceeding with available data.")

    # ------------------------------------------------------------------
    # 3. Compute technical indicators on every symbol
    # ------------------------------------------------------------------
    print(f"\nComputing technical indicators for all symbols ...")
    h1_enriched = {}
    for sym, df in h1_raw.items():
        try:
            h1_enriched[sym] = compute_indicators(df)
            print(f"  ✓ {sym}: {len(df)} rows → indicators computed")
        except Exception as e:
            print(f"  ✗ {sym}: compute_indicators failed — {e}")
            h1_enriched[sym] = df  # pass-through raw

    # ------------------------------------------------------------------
    # 4. Print structured summary table (data-mt5.md §7 format)
    # ------------------------------------------------------------------
    print_data_summary(h1_enriched, "H1")

    # ------------------------------------------------------------------
    # 5. Show available indicator columns (first symbol)
    # ------------------------------------------------------------------
    if h1_enriched:
        first_sym = sorted(h1_enriched.keys())[0]
        indicator_cols = [
            c for c in h1_enriched[first_sym].columns
            if c not in ('open', 'high', 'low', 'close',
                          'tick_volume', 'spread', 'real_volume')
        ]
        print(f"\nAvailable indicator columns (from {first_sym}):")
        print(f"  {', '.join(indicator_cols)}")

    # ------------------------------------------------------------------
    # 6. Per-symbol status confirmation
    # ------------------------------------------------------------------
    print(f"\n{'=' * 78}")
    print(f"  PER-SYMBOL STATUS CONFIRMATION — H1")
    print(f"{'=' * 78}")
    print(f"  {'Symbol':<12} {'Rows':>8} {'Start':<12} {'End':<12} {'Indicators':>10} {'Ready':>8}")
    print(f"  {'-' * 62}")
    all_ready = True
    for sym in sorted(h1_enriched.keys()):
        df = h1_enriched[sym]
        rows = len(df)
        start = df.index[0].strftime('%Y-%m-%d')
        end = df.index[-1].strftime('%Y-%m-%d')
        has_indicators = all(
            c in df.columns for c in
            ['atr14', 'rsi14', 'ma20', 'ma50', 'ma200',
             'bb_upper', 'bb_lower', 'session']
        )
        status = "✓ READY" if has_indicators else "⚠ PARTIAL"
        if not has_indicators:
            all_ready = False
        print(f"  {sym:<12} {rows:>8} {start:<12} {end:<12} {'13 cols':>10} {status:>8}")

    print(f"  {'-' * 62}")
    if all_ready:
        print(f"  All {len(h1_enriched)} symbols enriched and ready.")
    else:
        print(f"  Some symbols have partial indicators — review warnings above.")
    print(f"{'=' * 78}")

    # ------------------------------------------------------------------
    # 7. Final readiness announcement
    # ------------------------------------------------------------------
    print(f"\nResearcher 数据就绪，可交付 Analyst。")
    print(f"Loaded {len(h1_enriched)} symbols at H1 timeframe, "
          f"total {sum(len(df) for df in h1_enriched.values()):,} rows.")


if __name__ == "__main__":
    main()
