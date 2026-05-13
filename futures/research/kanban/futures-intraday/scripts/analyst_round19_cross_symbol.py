#!/usr/bin/env python3
"""
analyst_round19_cross_symbol.py — Round 19 H1 Cross-Symbol Validation

After the main hypothesis (EURUSD RSI<35 hold=7: 67.48%), validate
whether the same pattern works on other major symbols.

Entry condition: "session == 'us' and atr14 / close > 0.0025 and rsi14 < 35"
Direction: long
Timeframe: H1
Symbols: [XAUUSD, US500, GBPUSD, US30, XAGUSD, USTEC]
Hold periods: [3, 5, 7, 10, 12, 15]
"""

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from grid_engine import run_grid

config = {
    "timeframe": "H1",
    "symbols": ["XAUUSD", "US500", "GBPUSD", "US30", "XAGUSD", "USTEC"],
    "entry_condition": "session == 'us' and atr14 / close > 0.0025 and rsi14 < 35",
    "direction": "long",
    "hold_periods": [3, 5, 7, 10, 12, 15],
    "exit_at_close": True,
}

print("=" * 70)
print("  ROUND 19 — CROSS-SYMBOL VALIDATION")
print("=" * 70)
print(f"\n  Entry: {config['entry_condition']}")
print(f"  Direction: {config['direction']}")
print(f"  Symbols: {', '.join(config['symbols'])}")
print(f"  Hold periods: {config['hold_periods']}")
print()

print("Running grid engine...")
results = run_grid(config)

meta = results.pop("_meta", {})
print(f"\n  Symbols with signals: {meta.get('symbols_with_signals', 0)} / {meta.get('total_symbols', 0)}")
print()

# Print header
print(f"  {'Symbol':<12} {'Hold':>4} {'n':>5} {'WinRate':>8} {'AvgRet':>10} {'Sharpe':>7} {'MaxDD':>8} {'Verdict':>12}")
print(f"  {'-'*70}")

cross_results = {}
best_overall = {"wr": 0}

for sym in sorted(results.keys()):
    sym_res = results[sym]
    for hp in sorted(sym_res.keys(), key=int):
        s = sym_res[hp]
        cnt = s.get("signal_count", 0)
        wr = s.get("win_rate", 0) or 0
        avg = s.get("avg_return", 0) or 0
        sh = s.get("sharpe_ratio", 0) or 0
        dd = s.get("max_drawdown", 0) or 0

        # Determine verdict
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

        print(f"  {sym:<12} {hp:>4} {cnt:>5} {wr:>7.2%} {avg:>+9.5f} {sh:>6.2f} {dd:>7.4f} {verdict:>12}")

        if sym not in cross_results:
            cross_results[sym] = {}
        cross_results[sym][hp] = {
            "signal_count": cnt,
            "win_rate": round(wr, 6),
            "avg_return": round(avg, 6),
            "sharpe_ratio": round(sh, 6),
            "max_drawdown": round(dd, 6),
            "verdict": verdict,
        }

        # Track best per symbol at hold=7
        if hp == 7 and wr > best_overall.get("wr", 0) and cnt >= 30:
            best_overall = {
                "symbol": sym,
                "hold": hp,
                "win_rate": wr,
                "avg_return": avg,
                "sharpe": sh,
                "count": cnt,
            }

# Summary table at hold=7
print(f"\n{'='*70}")
print(f"  CROSS-SYMBOL SUMMARY at hold=7")
print(f"{'='*70}")
print(f"  {'Symbol':<12} {'n':>5} {'WinRate':>8} {'AvgRet':>10} {'Sharpe':>7} {'Verdict':>12}")
print(f"  {'-'*56}")
for sym in sorted(cross_results.keys()):
    r = cross_results[sym].get(7, {})
    cnt = r.get("signal_count", 0)
    wr = r.get("win_rate", 0) or 0
    avg = r.get("avg_return", 0) or 0
    sh = r.get("sharpe_ratio", 0) or 0
    v = r.get("verdict", "N/A")
    print(f"  {sym:<12} {cnt:>5} {wr:>7.2%} {avg:>+9.5f} {sh:>6.2f} {v:>12}")

# Print structured output
output = {
    "config": config,
    "cross_results": cross_results,
    "best_overall": best_overall,
}

print(f"\n---STRUCTURED_OUTPUT---")
print(json.dumps(output, indent=2, ensure_ascii=False))
print("---END_STRUCTURED_OUTPUT---")
