#!/usr/bin/env python3
"""
Researcher: M30 data loading, indicator computation, structured summary.
Round 14 — M30 timeframe, all 14 symbols.
"""
import sys
from pathlib import Path

# Ensure scripts/ is on the path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from data_loader import list_available_symbols, load_data, compute_indicators

# ---------------------------------------------------------------------------
# 1. List & verify M30 symbols
# ---------------------------------------------------------------------------
print("=" * 72)
print("  RESEARCHER — M30 Data Loading (Round 14)")
print("=" * 72)

m30_syms = list_available_symbols(timeframe="M30")
print(f"\n  M30 symbols found: {len(m30_syms)}")
print(f"  Symbols: {', '.join(m30_syms)}")

if len(m30_syms) < 14:
    print(f"  WARNING: Expected 14 symbols, found {len(m30_syms)}")
    # Continue anyway with what we have

# ---------------------------------------------------------------------------
# 2. Load raw M30 data for all symbols
# ---------------------------------------------------------------------------
print("\n  Loading M30 data for all symbols ...")
m30_raw = load_data(timeframe="M30")
print(f"  → {len(m30_raw)} symbols loaded")

# ---------------------------------------------------------------------------
# 3. Compute technical indicators for each symbol
# ---------------------------------------------------------------------------
print("\n  Computing indicators (atr14, rsi14, ma20/50/200, bb, pct_chg, "
      "gap_pct, session, dayofweek, hour, consecutive counts) ...")

m30_enriched = {}
compute_errors = []
for sym in sorted(m30_raw.keys()):
    try:
        m30_enriched[sym] = compute_indicators(m30_raw[sym])
        print(f"    ✓ {sym}: {len(m30_enriched[sym]):>6} rows enriched")
    except Exception as e:
        print(f"    ✗ {sym}: compute_indicators FAILED — {e}")
        compute_errors.append(sym)
        m30_enriched[sym] = m30_raw[sym]  # passthrough raw

print(f"\n  Compute complete. {len(m30_enriched) - len(compute_errors)}/{len(m30_enriched)} OK"
      + (f", {len(compute_errors)} failed" if compute_errors else ""))

# ---------------------------------------------------------------------------
# 4. Print structured data summary table (per Section 7 of data-mt5.md)
# ---------------------------------------------------------------------------
def print_summary(data: dict, tf: str):
    """Print a formatted data summary table for the Analyst."""
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
        # Count unique trading sessions present
        sessions = df['session'].nunique() if 'session' in df.columns else '?'
        print(f"  {sym:<12} {rows:>10} {start:<20} {end:<20} {str(sessions):>8}")
    print(f"  {'-'*70}")
    print(f"  {'TOTAL':<12} {total_rows:>10}  ({len(data)} symbols, {tf})")
    print(f"{'='*78}\n")

print_summary(m30_enriched, "M30")

# ---------------------------------------------------------------------------
# 5. Report data readiness
# ---------------------------------------------------------------------------
print(f"  {'='*60}")
print(f"    DATA READY FOR ANALYST")
print(f"    {'• M30:':<20} {len(m30_enriched)} symbols, {sum(len(df) for df in m30_enriched.values())} total rows")
print(f"    {'• Timeframe:':<20} M30 (30-minute)")
print(f"    {'• Indicators:':<20} atr14, rsi14, ma20, ma50, ma200, bb_upper,")
print(f"    {'':20} bb_lower, pct_chg, gap_pct, session, dayofweek, hour,")
print(f"    {'':20} consecutive_bull_count, consecutive_bear_count")
print(f"    {'• Status:':<20} {'READY' if not compute_errors else 'PARTIAL (see errors above)'}")
print(f"  {'='*60}")
