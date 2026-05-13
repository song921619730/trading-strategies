#!/usr/bin/env python3
"""
Round 21 — H1 Data Summary Generator
Loads H1 data for target symbols, computes indicators, outputs structured Markdown tables.
"""

import sys
import os

# Ensure we're in the scripts dir so data_loader can resolve ../data/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# Add scripts dir to path
sys.path.insert(0, SCRIPT_DIR)

from data_loader import load_data, compute_indicators
import pandas as pd
pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 200)
pd.set_option('display.max_colwidth', 12)

# ── Symbols we want (actual filenames, no 'm' suffix) ──
SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'XAUUSD', 'XAGUSD', 'US30', 'US500']

# ── 1. Load raw data ──
print("=" * 80)
print("ROUND 21 — H1 DATA SUMMARY")
print("=" * 80)
print()
print(f"Symbols requested: {SYMBOLS}")
print()

raw = load_data(timeframe='H1', symbols=SYMBOLS)
print(f"Successfully loaded {len(raw)} symbols from H1 parquet files.\n")

# ── 2. Compute indicators for each symbol ──
indicator_dfs = {}
for sym in SYMBOLS:
    if sym not in raw:
        print(f"⚠  {sym}: NOT FOUND on disk, skipping.")
        continue
    df = compute_indicators(raw[sym])
    indicator_dfs[sym] = df
    print(f"✓ {sym}: computed indicators → {len(df)} rows")

print()

# ── 3. Per-symbol summary ──
def print_table(header, rows):
    """Print a simple markdown table."""
    col_widths = []
    for ci, h in enumerate(header):
        max_w = len(str(h))
        for r in rows:
            max_w = max(max_w, len(str(r[ci])))
        col_widths.append(max_w + 2)  # padding
    # header sep
    hdr_line = "|"
    sep_line = "|"
    for ci, h in enumerate(header):
        w = col_widths[ci]
        hdr_line += f" {str(h).ljust(w-1)}|"
        sep_line += f" {'-'*(w-1)}|"
    print(hdr_line)
    print(sep_line)
    for r in rows:
        line = "|"
        for ci, val in enumerate(r):
            w = col_widths[ci]
            line += f" {str(val).ljust(w-1)}|"
        print(line)
    print()

# 3a. Overview table
print("## 3a. Dataset Overview\n")
header = ['Symbol', 'Rows', 'Start Date', 'End Date', 'Indicator Columns']
rows = []
for sym in SYMBOLS:
    if sym not in indicator_dfs:
        continue
    df = indicator_dfs[sym]
    ind_cols = [c for c in df.columns if c not in ('open','high','low','close','tick_volume','spread','real_volume')]
    rows.append([
        sym,
        str(len(df)),
        str(df.index.min().strftime('%Y-%m-%d')),
        str(df.index.max().strftime('%Y-%m-%d')),
        ', '.join(ind_cols)
    ])
print_table(header, rows)

# 3b. RSI14 descriptive statistics
print("## 3b. RSI14 Descriptive Statistics\n")
header = ['Symbol', 'Count', 'Min', '25%', '50%', '75%', 'Max', 'Mean']
rows = []
for sym in SYMBOLS:
    if sym not in indicator_dfs:
        continue
    df = indicator_dfs[sym]
    rsi = df['rsi14'].dropna()
    desc = rsi.describe(percentiles=[0.25, 0.5, 0.75])
    rows.append([
        sym,
        f"{len(rsi):.0f}",
        f"{desc['min']:.2f}",
        f"{desc['25%']:.2f}",
        f"{desc['50%']:.2f}",
        f"{desc['75%']:.2f}",
        f"{desc['max']:.2f}",
        f"{desc['mean']:.2f}",
    ])
print_table(header, rows)

# 3c. Session distribution
print("## 3c. Session Distribution (asia / europe / us)\n")
header = ['Symbol', 'Total Rows', 'asia', 'europe', 'us']
rows = []
for sym in SYMBOLS:
    if sym not in indicator_dfs:
        continue
    df = indicator_dfs[sym]
    counts = df['session'].value_counts()
    rows.append([
        sym,
        str(len(df)),
        str(counts.get('asia', 0)),
        str(counts.get('europe', 0)),
        str(counts.get('us', 0)),
    ])
print_table(header, rows)

# 3d. Last 5 rows sample (for indicator verification)
print("## 3d. Last 5 Rows — Data Sample (Indicator Verification)\n")
for sym in SYMBOLS:
    if sym not in indicator_dfs:
        continue
    df = indicator_dfs[sym]
    print(f"### {sym}\n")
    tail = df.tail(5)
    # Select relevant columns for display
    display_cols = ['open','high','low','close','atr14','rsi14','ma20','ma50','session','hour','dayofweek','consecutive_bull_count','consecutive_bear_count']
    show_cols = [c for c in display_cols if c in df.columns]
    print(tail[show_cols].to_string())
    print()

# ── 4. Summary of all indicator columns available per symbol ──
print("## 4. Indicator Column Availability\n")
header = ['Symbol'] + ['atr14','rsi14','ma20','ma50','ma200','bb_upper','bb_lower','pct_chg','gap_pct','session','hour','dayofweek','consecutive_bull_count','consecutive_bear_count']
rows = []
for sym in SYMBOLS:
    if sym not in indicator_dfs:
        continue
    df = indicator_dfs[sym]
    row = [sym]
    for col in header[1:]:
        row.append('✓' if col in df.columns else '')
    rows.append(row)
print_table(header, rows)

# ── 5. Additional: ATR14 descriptive stats ──
print("## 5. ATR14 Descriptive Statistics (bonus — useful for strategy context)\n")
header = ['Symbol', 'Count', 'Min', '25%', '50%', '75%', 'Max', 'Mean']
rows = []
for sym in SYMBOLS:
    if sym not in indicator_dfs:
        continue
    df = indicator_dfs[sym]
    atr = df['atr14'].dropna()
    desc = atr.describe(percentiles=[0.25, 0.5, 0.75])
    rows.append([
        sym,
        f"{len(atr):.0f}",
        f"{desc['min']:.4f}",
        f"{desc['25%']:.4f}",
        f"{desc['50%']:.4f}",
        f"{desc['75%']:.4f}",
        f"{desc['max']:.4f}",
        f"{desc['mean']:.4f}",
    ])
print_table(header, rows)

print("=" * 80)
print("SUMMARY COMPLETE — Ready for Analyst Profile hypothesis testing")
print("=" * 80)
