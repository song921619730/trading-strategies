#!/usr/bin/env python3
"""Researcher: load M30 data, compute indicators, print structured summary for Analyst."""

import sys
from pathlib import Path

import pandas as pd
from data_loader import list_available_symbols, load_data, compute_indicators

# ------------------------------------------------------------------
# 1. Check M30 data availability
# ------------------------------------------------------------------
print("=" * 78)
print("  M30 DATA LOAD — Checking available symbols")
print("=" * 78)

m30_syms = list_available_symbols(timeframe="M30")
print(f"  M30 symbols found: {len(m30_syms)}")
print(f"  Symbols: {m30_syms}")
print()

# ------------------------------------------------------------------
# 2. Load raw M30 data
# ------------------------------------------------------------------
print("Loading M30 data ...")
m30_raw = load_data(timeframe="M30")
print(f"  → {len(m30_raw)} symbols loaded\n")

# ------------------------------------------------------------------
# 3. Compute indicators on all symbols
# ------------------------------------------------------------------
print("Computing indicators (ATR14, RSI14, MA20/50/200, BB, session, etc.) ...")
m30_data = {}
for sym, df in m30_raw.items():
    try:
        m30_data[sym] = compute_indicators(df)
        print(f"  ✓ {sym}: {len(df)} rows → {len(m30_data[sym].columns)} columns")
    except Exception as e:
        print(f"  ✗ {sym}: compute_indicators FAILED — {e}")
        m30_data[sym] = df  # passthrough raw
print()

# ------------------------------------------------------------------
# 4. Print structured summary table
# ------------------------------------------------------------------
def print_m30_summary(data: dict):
    """Print a formatted M30 data summary table for the Analyst."""
    print("=" * 88)
    print("  RESEARCHER DATA SUMMARY — M30 (30-Minute)")
    print("=" * 88)
    print(f"  {'Symbol':<12} {'Rows':>10} {'From':<22} {'To':<22} {'Sessions':>8}  {'Indicators'}")
    print(f"  {'-' * 80}")
    
    total_rows = 0
    for sym in sorted(data.keys()):
        df = data[sym]
        rows = len(df)
        total_rows += rows
        start = df.index[0].strftime('%Y-%m-%d %H:%M')
        end = df.index[-1].strftime('%Y-%m-%d %H:%M')
        
        # Count unique trading sessions present
        if 'session' in df.columns:
            sessions = df['session'].nunique()
            session_str = str(sessions)
        else:
            session_str = '?'
        
        # List extra indicator columns (beyond OHLCV)
        base_cols = {'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume'}
        indicator_cols = [c for c in df.columns if c not in base_cols]
        indicator_str = ', '.join(indicator_cols[:8])  # show first 8
        if len(indicator_cols) > 8:
            indicator_str += f' … +{len(indicator_cols)-8} more'
        
        print(f"  {sym:<12} {rows:>10,}  {start:<22} {end:<22} {session_str:>8}  {indicator_str}")
    
    print(f"  {'-' * 80}")
    print(f"  {'TOTAL':<12} {total_rows:>10,}  ({len(data)} symbols, M30)")
    print(f"  {'-' * 80}")
    
    # Extra stats
    print(f"\n  Data range (earliest → latest across all symbols):")
    earliest = min(df.index[0] for df in data.values())
    latest = max(df.index[-1] for df in data.values())
    print(f"    Global start: {earliest.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"    Global end:   {latest.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"    Total M30 bars: {total_rows:,}")
    print(f"    Avg rows/symbol: {total_rows // len(data):,}")
    
    print(f"\n  Session coverage:")
    all_sessions = set()
    for df in data.values():
        if 'session' in df.columns:
            all_sessions.update(df['session'].unique())
    if all_sessions:
        print(f"    Sessions present: {sorted(all_sessions)}")
    
    print(f"  Indicator columns available (on enriched DataFrames):")
    all_indicator_cols = set()
    for df in data.values():
        all_indicator_cols.update(c for c in df.columns if c not in base_cols)
    if all_indicator_cols:
        print(f"    {sorted(all_indicator_cols)}")
    else:
        print(f"    (indicators not computed)")
    
    print("=" * 88)
    print()

print_m30_summary(m30_data)

# ------------------------------------------------------------------
# 5. Report readiness for Analyst
# ------------------------------------------------------------------
print(f"Ready for Analyst. M30: {len(m30_data)} symbols loaded and enriched.")
print("All DataFrames available in memory.")

# Quick validation
print()
print("=" * 78)
print("  VALIDATION CHECKS")
print("=" * 78)
all_ok = True
for sym, df in m30_data.items():
    issues = []
    if df.index.name != 'time':
        issues.append(f"index name is '{df.index.name}', expected 'time'")
    if not isinstance(df.index, pd.DatetimeIndex):
        issues.append("index is not DatetimeIndex")
    if 'session' not in df.columns:
        issues.append("missing 'session' column")
    if 'rsi14' not in df.columns:
        issues.append("missing 'rsi14' column")
    if 'atr14' not in df.columns:
        issues.append("missing 'atr14' column")
    
    if issues:
        all_ok = False
        print(f"  ✗ {sym}: {', '.join(issues)}")
    else:
        print(f"  ✓ {sym}: {len(df)} rows, {len(df.columns)} cols, session ✓, indicators ✓")

if all_ok:
    print(f"\n  All {len(m30_data)} symbols passed validation ✓")
else:
    print(f"\n  Some validation issues found — see above")
print("=" * 78)
