#!/usr/bin/env python3
"""
analyst_round19_run.py — Round 19 H1 Hypothesis Test

Hypothesis: round17_a01
  EURUSD H1 美盘+高ATR+RSI<35做多 hold=7 尝试推至68%+

Entry condition: "session == 'us' and atr14 / close > 0.0025 and rsi14 < 35"
Direction: long
Timeframe: H1
Symbols: ["EURUSD"] (primary target)
Hold periods: [3, 5, 7, 10, 12, 15]
"""

import json
import sys
from pathlib import Path
from pprint import pprint

# Make sure scripts dir is on path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from grid_engine import run_grid

# ------------------------------------------------------------------
# Step 1: Config
# ------------------------------------------------------------------
config = {
    "timeframe": "H1",
    "symbols": ["EURUSD"],
    "entry_condition": "session == 'us' and atr14 / close > 0.0025 and rsi14 < 35",
    "direction": "long",
    "hold_periods": [3, 5, 7, 10, 12, 15],
    "exit_at_close": True,
}

print("=" * 70)
print("  ROUND 19 — H1 HYPOTHESIS TEST")
print("=" * 70)
print(f"\n  Hypothesis: round17_a01")
print(f"  EURUSD H1 美盘+高ATR+RSI<35做多 hold=7 尝试推至68%+")
print(f"\n  Entry condition: {config['entry_condition']}")
print(f"  Direction: {config['direction']}")
print(f"  Symbol: {config['symbols'][0]}")
print(f"  Hold periods: {config['hold_periods']}")
print(f"  Baseline (RSI<40): hold=7 → 67.36%, n=193, Sharpe=8.24")
print()

# ------------------------------------------------------------------
# Step 2: Run grid
# ------------------------------------------------------------------
print("Running grid engine...")
results = run_grid(config)

# ------------------------------------------------------------------
# Step 3: Parse results
# ------------------------------------------------------------------
meta = results.pop("_meta", {})
print(f"\n  Symbols with signals: {meta.get('symbols_with_signals', 0)} / {meta.get('total_symbols', 0)}")
print()

# Print header
print(f"  {'Symbol':<12} {'Hold':>4} {'n':>5} {'WinRate':>8} {'AvgRet':>10} {'Sharpe':>7} {'MaxDD':>8}")
print(f"  {'-'*56}")

best_wr = 0.0
best_params = None
all_results = {}

for sym in sorted(results.keys()):
    sym_res = results[sym]
    for hp in sorted(sym_res.keys(), key=int):
        s = sym_res[hp]
        cnt = s.get("signal_count", 0)
        if cnt == 0:
            continue
        wr = s.get("win_rate", 0) or 0
        avg = s.get("avg_return", 0) or 0
        sh = s.get("sharpe_ratio", 0) or 0
        dd = s.get("max_drawdown", 0) or 0
        print(f"  {sym:<12} {hp:>4} {cnt:>5} {wr:>7.2%} {avg:>+9.5f} {sh:>6.2f} {dd:>7.4f}")

        if wr > best_wr and cnt >= 30:
            best_wr = wr
            best_params = {
                "symbol": sym,
                "hold": hp,
                "win_rate": wr,
                "avg_return": avg,
                "sharpe": sh,
                "count": cnt,
                "max_drawdown": dd,
            }

        if sym not in all_results:
            all_results[sym] = {}
        all_results[sym][hp] = {
            "signal_count": cnt,
            "win_rate": round(wr, 6),
            "avg_return": round(avg, 6),
            "sharpe_ratio": round(sh, 6),
            "max_drawdown": round(dd, 6),
        }

print(f"\n  Best result: wr={best_wr:.2%} at hold={best_params['hold']}, n={best_params['count']}, Sharpe={best_params['sharpe']:.2f}" if best_params else "  No valid results.")

# ------------------------------------------------------------------
# Step 4: Interpretation
# ------------------------------------------------------------------
verdict = "inconclusive"
summary = ""

if best_params:
    wr = best_params["win_rate"]
    cnt = best_params["count"]

    if cnt < 30:
        verdict = "inconclusive"
        summary = f"样本不足: 仅{cnt}个信号(n<30), 无法得出可靠结论"
    elif wr > 0.60:
        verdict = "strong"
        summary = f"Strong signal: EURUSD hold={best_params['hold']} wr={wr:.2%} (n={cnt}, Sharpe={best_params['sharpe']:.2f})"
        print(f"\n  ★★★ STRONG SIGNAL! win_rate={wr:.2%} > 60% threshold")
    elif wr > 0.55:
        verdict = "promising"
        summary = f"Promising: EURUSD hold={best_params['hold']} wr={wr:.2%} (n={cnt})"
        print(f"\n  ★ PROMISING! win_rate={wr:.2%} > 55% threshold")
    elif wr < 0.50:
        verdict = "reversal_possible"
        summary = f"Win rate {wr:.2%} < 50%, reverse direction may work"
        print(f"\n  ⚠ Win rate {wr:.2%} < 50%. Reverse direction may work.")
    else:
        verdict = "weak"
        summary = f"Weak signal: EURUSD wr={wr:.2%} (n={cnt})"

# Compare with baseline (RSI<40: 67.36%, n=193, Sharpe=8.24 at hold=7)
baseline_wr = 0.6736
baseline_n = 193
baseline_sharpe = 8.24
baseline_hold = 7

print(f"\n{'='*70}")
print(f"  BASELINE COMPARISON (RSI<40 vs RSI<35)")
print(f"{'='*70}")

# Find RSI<35 result at hold=7
rsi35_result_hold7 = all_results.get("EURUSD", {}).get(7, {})
rsi35_wr_hold7 = rsi35_result_hold7.get("win_rate", 0) or 0
rsi35_n_hold7 = rsi35_result_hold7.get("signal_count", 0) or 0
rsi35_sharpe_hold7 = rsi35_result_hold7.get("sharpe_ratio", 0) or 0

print(f"\n  {'Metric':<20} {'RSI<40 (baseline)':>20} {'RSI<35 (test)':>20} {'Delta':>10}")
print(f"  {'-'*70}")
print(f"  {'Win Rate':<20} {baseline_wr:>19.2%} {rsi35_wr_hold7:>19.2%} {rsi35_wr_hold7 - baseline_wr:>+9.2%}")
print(f"  {'Signal Count':<20} {baseline_n:>20} {rsi35_n_hold7:>20} {rsi35_n_hold7 - baseline_n:>+9}")
print(f"  {'Sharpe':<20} {baseline_sharpe:>19.2f} {rsi35_sharpe_hold7:>19.2f} {rsi35_sharpe_hold7 - baseline_sharpe:>+9.2f}")

# Check if we hit the target of 68%+
target = 0.68
if rsi35_wr_hold7 >= target:
    print(f"\n  ✅ 目标达成! RSI<35 hold=7 {rsi35_wr_hold7:.2%} >= {target:.0%}!")
elif rsi35_wr_hold7 > baseline_wr:
    print(f"\n  ⬆ RSI<35 hold=7 {rsi35_wr_hold7:.2%} > baseline {baseline_wr:.2%} — 胜率提升!")
else:
    print(f"\n  ⬇ RSI<35 hold=7 {rsi35_wr_hold7:.2%} < baseline {baseline_wr:.2%} — 胜率下降")

# ------------------------------------------------------------------
# Step 5: Output summary for parent agent
# ------------------------------------------------------------------
print(f"\n{'='*70}")
print(f"  ROUND 19 SUMMARY")
print(f"{'='*70}")
print(f"\n  Verdict: {verdict.upper()}")
print(f"  Summary: {summary}")

# Generate JSON-like structured output for parsing
output = {
    "config": config,
    "verdict": verdict,
    "summary": summary,
    "best_params": best_params,
    "all_results": all_results,
    "baseline": {
        "win_rate": baseline_wr,
        "signal_count": baseline_n,
        "sharpe_ratio": baseline_sharpe,
        "hold": baseline_hold,
    },
    "hold7_comparison": {
        "rsi35_win_rate": rsi35_wr_hold7,
        "rsi35_signal_count": rsi35_n_hold7,
        "rsi35_sharpe": rsi35_sharpe_hold7,
        "delta_win_rate": rsi35_wr_hold7 - baseline_wr,
        "delta_signal_count": rsi35_n_hold7 - baseline_n,
        "delta_sharpe": rsi35_sharpe_hold7 - baseline_sharpe,
    },
}

print(f"\n---STRUCTURED_OUTPUT---")
print(json.dumps(output, indent=2, ensure_ascii=False))
print("---END_STRUCTURED_OUTPUT---")
