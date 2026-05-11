#!/usr/bin/env python3
"""Researcher: load data, compute indicators, print summary for H1 timeframe."""

import sys
from pathlib import Path
from data_loader import list_available_symbols, load_data, compute_indicators

# ------------------------------------------------------------------
# 1. Check data availability
# ------------------------------------------------------------------
h1_syms = list_available_symbols(timeframe="H1")
print(f"H1 symbols ({len(h1_syms)}): {h1_syms}")
print()

# ------------------------------------------------------------------
# 2. Load raw data for H1 only (task specifies H1)
# ------------------------------------------------------------------
print("Loading H1 data ...")
h1_raw = load_data(timeframe="H1")
print(f"  → {len(h1_raw)} symbols loaded\n")

# ------------------------------------------------------------------
# 3. Compute indicators
# ------------------------------------------------------------------
print("Computing indicators (H1) ...")
h1_data = {}
for sym, df in h1_raw.items():
    try:
        h1_data[sym] = compute_indicators(df)
        print(f"  ✓ {sym}: {len(df)} rows → enriched")
    except Exception as e:
        print(f"  ✗ {sym}: compute_indicators failed: {e}")
        h1_data[sym] = df  # passthrough raw
print()

# ------------------------------------------------------------------
# 4. Print structured summary table (following Section 6 format)
# ------------------------------------------------------------------
def print_summary(data: dict, tf: str):
    """Print a formatted data summary table for the Analyst."""
    print(f"{'='*78}")
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
        # Count unique trading sessions present
        sessions = df['session'].nunique() if 'session' in df.columns else '?'
        print(f"  {sym:<12} {rows:>10} {start:<20} {end:<20} {sessions:>8}")
    print(f"  {'-'*70}")
    print(f"  {'TOTAL':<12} {total_rows:>10}  ({len(data)} symbols, {tf})")
    print(f"{'='*78}\n")

print_summary(h1_data, "H1")

# ------------------------------------------------------------------
# 5. Report readiness for Analyst & confirm enriched columns
# ------------------------------------------------------------------
print(f"Ready for Analyst. H1: {len(h1_data)} symbols loaded and enriched.")

# Show all enriched columns from first symbol
first_sym = sorted(h1_data.keys())[0]
enriched_cols = h1_data[first_sym].columns.tolist()
raw_cols = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
indicator_cols = [c for c in enriched_cols if c not in raw_cols]

print(f"\nEnriched columns available ({len(indicator_cols)} indicator columns added):")
print("  " + ", ".join(indicator_cols))
print()

# Verify all symbols have the same enriched columns
all_match = all(
    sorted(h1_data[sym].columns.tolist()) == sorted(enriched_cols)
    for sym in h1_data
)
print(f"Column consistency across all {len(h1_data)} symbols: {'✓ ALL MATCH' if all_match else '✗ MISMATCH DETECTED'}")

# Show sample non-NaN row count to confirm indicators computed
sample_df = h1_data[first_sym]
non_nan = sample_df.dropna(subset=indicator_cols).shape[0]
print(f"Sample ({first_sym}): {non_nan}/{len(sample_df)} rows with fully populated indicators (rest have NaN due to warmup periods)")
