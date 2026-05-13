#!/usr/bin/env python3
"""
analyst_round19_rsi_scan.py — Round 19 H1 RSI Threshold Gradient Scan

Since RSI<35 (67.48%) marginally improved over RSI<40 (67.36%) but lost signals,
scan a range of RSI thresholds to find the optimal balance.

Entry condition template: "session == 'us' and atr14 / close > 0.0025 and rsi14 < {THRESHOLD}"
Direction: long
Timeframe: H1
Symbols: [EURUSD]
Hold periods: [7] (focus on the baseline optimal)
RSI thresholds: [33, 35, 37, 38, 39, 40]
"""

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from grid_engine import run_grid

rsi_thresholds = [33, 35, 37, 38, 39, 40]
hold_periods = [7]  # Focus on the baseline optimal
base_condition = "session == 'us' and atr14 / close > 0.0025 and rsi14 < {}"

print("=" * 70)
print("  ROUND 19 — RSI THRESHOLD GRADIENT SCAN")
print("=" * 70)
print(f"\n  Direction: long")
print(f"  Symbol: EURUSD")
print(f"  Hold periods: {hold_periods}")
print(f"  RSI thresholds: {rsi_thresholds}")
print()

all_threshold_results = {}

for rsi_val in rsi_thresholds:
    condition = base_condition.format(rsi_val)
    config = {
        "timeframe": "H1",
        "symbols": ["EURUSD"],
        "entry_condition": condition,
        "direction": "long",
        "hold_periods": hold_periods,
        "exit_at_close": True,
    }

    print(f"  Testing RSI<{rsi_val}...", end=" ")
    results = run_grid(config)
    meta = results.pop("_meta", {})

    sym_res = results.get("EURUSD", {})
    hp_res = sym_res.get(7, {})
    cnt = hp_res.get("signal_count", 0) or 0
    wr = hp_res.get("win_rate", 0) or 0
    avg = hp_res.get("avg_return", 0) or 0
    sh = hp_res.get("sharpe_ratio", 0) or 0
    dd = hp_res.get("max_drawdown", 0) or 0

    if cnt < 30:
        verdict = "INCONCLUSIVE"
    elif wr > 0.60:
        verdict = "STRONG"
    elif wr > 0.55:
        verdict = "PROMISING"
    elif wr < 0.50:
        verdict = "REVERSAL"
    else:
        verdict = "WEAK"

    print(f"n={cnt}, wr={wr:.2%}, sharpe={sh:.2f}, verdict={verdict}")

    all_threshold_results[rsi_val] = {
        "signal_count": cnt,
        "win_rate": round(wr, 6),
        "avg_return": round(avg, 6),
        "sharpe_ratio": round(sh, 6),
        "max_drawdown": round(dd, 6),
        "verdict": verdict,
    }

# Print summary table
print(f"\n{'='*70}")
print(f"  RSI THRESHOLD COMPARISON (hold=7)")
print(f"{'='*70}")
print(f"  {'RSI<':<8} {'n':>5} {'WinRate':>8} {'AvgRet':>10} {'Sharpe':>7} {'MaxDD':>8} {'Verdict':>12}")
print(f"  {'-'*60}")
for rsi_val in sorted(all_threshold_results.keys()):
    r = all_threshold_results[rsi_val]
    cnt = r["signal_count"]
    wr = r["win_rate"]
    avg = r["avg_return"]
    sh = r["sharpe_ratio"]
    dd = r["max_drawdown"]
    v = r["verdict"]
    print(f"  RSI<{rsi_val:<4} {cnt:>5} {wr:>7.2%} {avg:>+9.5f} {sh:>6.2f} {dd:>7.4f} {v:>12}")

# Determine optimal threshold by win rate * sqrt(n) composite score
print(f"\n{'='*70}")
print(f"  OPTIMAL THRESHOLD ANALYSIS")
print(f"{'='*70}")

best_threshold = None
best_composite = 0

for rsi_val, r in sorted(all_threshold_results.items()):
    if r["signal_count"] >= 30:
        # Composite: win_rate * sqrt(signal_count) — balances quality and quantity
        composite = r["win_rate"] * (r["signal_count"] ** 0.5)
        print(f"  RSI<{rsi_val}: wr={r['win_rate']:.2%} n={r['signal_count']} composite={composite:.4f}")
        if composite > best_composite:
            best_composite = composite
            best_threshold = rsi_val

if best_threshold:
    br = all_threshold_results[best_threshold]
    print(f"\n  ★ Optimal threshold: RSI<{best_threshold}")
    print(f"    Win rate: {br['win_rate']:.2%}")
    print(f"    Signal count: {br['signal_count']}")
    print(f"    Sharpe: {br['sharpe_ratio']:.2f}")

output = {
    "threshold_scan": all_threshold_results,
    "best_threshold": best_threshold,
    "best_composite_score": round(best_composite, 4),
}

print(f"\n---STRUCTURED_OUTPUT---")
print(json.dumps(output, indent=2, ensure_ascii=False))
print("---END_STRUCTURED_OUTPUT---")
