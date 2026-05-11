#!/usr/bin/env python3
"""
M30 Data Summary & Indicator Validation Script
Loads M30 data for all 14 symbols, computes indicators, and prints structured summary.
"""
import sys
import json
from pathlib import Path

import pandas as pd

# Ensure scripts dir is on path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from data_loader import load_data, compute_indicators, list_available_symbols

# ── 1. List available symbols ──────────────────────────────────────────────
m30_syms = list_available_symbols(timeframe="M30")
print(f"[INFO] Found {len(m30_syms)} M30 symbols: {m30_syms}")
print()

if len(m30_syms) < 2:
    print("[ERROR] M30 data count < 2 — data likely missing or corrupt.")
    sys.exit(1)

# ⚠ Expected 14 symbols for full coverage
EXPECTED = {
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCHF", "USOIL", "UKOIL", "USTEC",
    "US30", "US500", "JP225", "HK50",
}
missing = EXPECTED - set(m30_syms)
if missing:
    print(f"[WARN] Missing expected symbols: {missing}")
else:
    print("[OK] All 14 expected symbols are present.")
print()

# ── 2. Load all M30 data ──────────────────────────────────────────────────
print("=" * 100)
print("LOADING M30 DATA FOR ALL SYMBOLS...")
print("=" * 100)
data = load_data(timeframe="M30")
print(f"[INFO] Loaded {len(data)} symbols.\n")

# ── 3. Compute indicators ──────────────────────────────────────────────────
print("=" * 100)
print("COMPUTING TECHNICAL INDICATORS...")
print("=" * 100)

enriched = {}
for sym in sorted(data.keys()):
    df = data[sym]
    try:
        df_enr = compute_indicators(df)
        enriched[sym] = df_enr
        print(f"  ✓ {sym:10s} | {len(df_enr):>6d} rows → indicators computed")
    except Exception as e:
        print(f"  ✗ {sym:10s} | ERROR: {e}")

print()

# ── 4. Structured Summary Table ────────────────────────────────────────────
print("=" * 120)
print("STRUCTURED DATA SUMMARY")
print("=" * 120)

header = f"{'Symbol':<10s} {'Rows':>8s} {'Date Start':>22s} {'Date End':>22s} {'Sessions':>20s} {'Last RSI14':>10s} {'Last BearCnt':>12s}"
sep = "-" * 110
print(header)
print(sep)

all_sessions_counts = {}
total_rows = 0

for sym in sorted(enriched.keys()):
    df = enriched[sym]
    rows = len(df)
    total_rows += rows
    dt_start = str(df.index.min())
    dt_end = str(df.index.max())

    # Session distribution
    if "session" in df.columns:
        sess_counts = df["session"].value_counts()
        # Format as e.g. "asia:1234 europe:567 us:890"
        sess_str = " ".join([f"{k}:{v}" for k, v in sess_counts.items()])
        all_sessions_counts[sym] = dict(sess_counts)
    else:
        sess_str = "⚠ MISSING"

    # Last valid RSI14
    if "rsi14" in df.columns:
        last_rsi = df["rsi14"].dropna().iloc[-1] if df["rsi14"].notna().any() else float("nan")
        rsi_str = f"{last_rsi:>8.2f}" if not pd.isna(last_rsi) else "     N/A"
    else:
        rsi_str = "  ⚠ MISSING"

    # Last valid consecutive_bear_count
    if "consecutive_bear_count" in df.columns:
        last_bear = df["consecutive_bear_count"].dropna().iloc[-1] if df["consecutive_bear_count"].notna().any() else 0
        bear_str = f"{int(last_bear):>6d}" if not pd.isna(last_bear) else "  N/A"
    else:
        bear_str = "  ⚠ MISSING"

    print(f"{sym:<10s} {rows:>8,d} {dt_start:>22s} {dt_end:>22s} {sess_str:>20s} {rsi_str:>10s} {bear_str:>12s}")

print(sep)
print(f"{'TOTAL':<10s} {total_rows:>8,d} {'':22s} {'':22s} {'':20s} {'':10s} {'':12s}")
print()

# ── 5. Enriched Columns Verification ───────────────────────────────────────
print("=" * 120)
print("ENRICHED COLUMNS VERIFICATION")
print("=" * 120)

expected_columns = [
    "atr14", "rsi14", "ma20", "ma50", "ma200",
    "bb_upper", "bb_lower", "pct_chg", "gap_pct",
    "hour", "dayofweek", "session",
    "consecutive_bull_count", "consecutive_bear_count",
]

first_sym = list(enriched.keys())[0]
first_df = enriched[first_sym]
all_cols = list(first_df.columns)
found_cols = set(all_cols)
missing_cols = [c for c in expected_columns if c not in found_cols]
extra_cols = [c for c in all_cols if c not in expected_columns and c not in ("open","high","low","close","tick_volume","spread","real_volume")]

if missing_cols:
    print(f"⚠ MISSING COLUMNS (in {first_sym}): {missing_cols}")
else:
    print(f"✓ ALL {len(expected_columns)} expected indicator columns present.")

if extra_cols:
    print(f"ℹ Extra non-OHLCV columns: {extra_cols}")

print(f"ℹ Total columns in enriched DataFrame: {len(all_cols)}")
print(f"ℹ Columns: {all_cols}")
print()

# ── 6. Focus Check: session column ────────────────────────────────────────
print("=" * 120)
print("FOCUS CHECKS: session, consecutive_bear_count, rsi14")
print("=" * 120)

all_ok = True

# 6a. session column
print("\n--- session column ---")
for sym in sorted(enriched.keys()):
    df = enriched[sym]
    if "session" not in df.columns:
        print(f"  ✗ {sym}: session column MISSING")
        all_ok = False
        continue
    sess_vals = df["session"].unique()
    has_asia = "asia" in sess_vals
    has_europe = "europe" in sess_vals
    has_us = "us" in sess_vals
    null_sess = df["session"].isna().sum()
    status = "✓" if (has_asia and has_europe and has_us) else "⚠"
    print(f"  {status} {sym:10s} | values={sorted(sess_vals)} | nulls={null_sess}")

# 6b. consecutive_bear_count column
print("\n--- consecutive_bear_count column ---")
bear_values_seen = set()
for sym in sorted(enriched.keys()):
    df = enriched[sym]
    if "consecutive_bear_count" not in df.columns:
        print(f"  ✗ {sym}: consecutive_bear_count MISSING")
        all_ok = False
        continue
    col = df["consecutive_bear_count"]
    max_val = col.max()
    null_cnt = col.isna().sum()
    unique_vals = sorted(col.dropna().unique())
    bear_values_seen.update(unique_vals)
    print(f"  ✓ {sym:10s} | max={int(max_val):>3d} | nulls={null_cnt:>6d} | unique={unique_vals[:10]}{'...' if len(unique_vals)>10 else ''}")

# 6c. rsi14 column
print("\n--- rsi14 column ---")
rsi_min = float("inf")
rsi_max = float("-inf")
for sym in sorted(enriched.keys()):
    df = enriched[sym]
    if "rsi14" not in df.columns:
        print(f"  ✗ {sym}: rsi14 MISSING")
        all_ok = False
        continue
    col = df["rsi14"].dropna()
    if len(col) == 0:
        print(f"  ⚠ {sym}: rsi14 all NaN")
        continue
    cmin, cmax = col.min(), col.max()
    rsi_min = min(rsi_min, cmin)
    rsi_max = max(rsi_max, cmax)
    last5 = col.tail(5).round(2).tolist()
    print(f"  ✓ {sym:10s} | min={cmin:>6.2f} max={cmax:>6.2f} | last_5={last5}")

print(f"\nℹ RSI14 global range across all symbols: [{rsi_min:.2f}, {rsi_max:.2f}]")
print(f"ℹ Consecutive bear count unique values seen: {sorted(bear_values_seen)[:20]}...")

# ── 7. Final Report ────────────────────────────────────────────────────────
print()
print("=" * 120)
print("FINAL VERDICT")
print("=" * 120)
if all_ok and len(enriched) == 14:
    print("✓ ALL CHECKS PASSED — M30 data is ready for auto_001 hypothesis testing.")
else:
    print(f"⚠ PARTIAL ISSUES — {len(enriched)}/14 symbols enriched. See above.")
print(f"ℹ Total enriched rows across all symbols: {total_rows:,}")
print()

# Export brief JSON for downstream
summary_json = {
    "status": "ok" if all_ok and len(enriched) == 14 else "partial",
    "symbols_loaded": len(data),
    "symbols_enriched": len(enriched),
    "total_rows": total_rows,
    "expected_columns_present": len(missing_cols) == 0,
    "columns": all_cols,
    "session_ok": all("session" in enriched[s] for s in enriched),
    "bear_count_ok": all("consecutive_bear_count" in enriched[s] for s in enriched),
    "rsi14_ok": all("rsi14" in enriched[s] for s in enriched),
    "global_rsi_range": [round(rsi_min, 2), round(rsi_max, 2)],
}
json_path = Path(__file__).resolve().parent.parent / "reports" / "m30_data_summary.json"
json_path.write_text(json.dumps(summary_json, indent=2))
print(f"[INFO] Summary JSON exported to: {json_path}")
print("[DONE]")
