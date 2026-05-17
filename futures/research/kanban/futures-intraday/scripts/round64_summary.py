#!/usr/bin/env python3
"""Round 64 — Analyst & Writer: Generate Summary from Researcher Results"""
import json
from collections import defaultdict
from pathlib import Path

RESULTS_PATH = Path(__file__).resolve().parent.parent / "logs" / "round64_researcher_results.json"
STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "research_state.json"
REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "reports" / "round_064.md"

with open(RESULTS_PATH) as f:
    data = json.load(f)

# Extract all findings
findings = []
for test_id, test_results in data.items():
    if not isinstance(test_results, dict):
        continue
    for sym, sym_res in test_results.items():
        if not isinstance(sym_res, dict):
            continue
        for hp, stats in sym_res.items():
            if not isinstance(stats, dict):
                continue
            n = stats.get("signal_count", 0)
            wr = stats.get("win_rate")
            avg_ret = stats.get("avg_return")
            sharpe = stats.get("sharpe_ratio")
            dd = stats.get("max_drawdown")
            if wr is not None and n >= 30 and wr >= 0.60:
                findings.append({
                    "test_id": test_id,
                    "symbol": sym,
                    "hold_period": int(hp) if isinstance(hp, str) else hp,
                    "signal_count": n,
                    "win_rate": wr,
                    "avg_return": avg_ret,
                    "sharpe_ratio": sharpe,
                    "max_drawdown": dd,
                })

findings.sort(key=lambda x: (x["win_rate"], x["signal_count"]), reverse=True)

# Group by test
by_test = defaultdict(list)
for f in findings:
    by_test[f["test_id"]].append(f)

# Injectable candidates (n>=150, WR>=65%)
injectable = [f for f in findings if f["signal_count"] >= 150 and f["win_rate"] >= 0.65]
# Strong (WR>=70%, n>=50)
strong = [f for f in findings if f["win_rate"] >= 0.70 and f["signal_count"] >= 50]
# Standard (n>=30, WR>=60%)
standard = [f for f in findings if f["signal_count"] >= 30 and f["win_rate"] >= 0.60]

print(f"Total test groups: {len(by_test)}")
print(f"Total findings (WR>=60%, n>=30): {len(findings)}")
print(f"Injectable (n>=150, WR>=65%): {len(injectable)}")
print(f"Strong (WR>=70%, n>=50): {len(strong)}")
print(f"Standard (WR>=60%, n>=30): {len(standard)}")

# Print injectable
if injectable:
    print("\n## INJECTABLE SIGNALS")
    for f in injectable[:10]:
        print(f"  {f['test_id']} {f['symbol']} hp={f['hold_period']} WR={f['win_rate']:.2%} n={f['signal_count']} avg_ret={f['avg_return']:.4f} sharpe={f['sharpe_ratio']:.2f}")

# Print strong
if strong:
    print("\n## STRONG SIGNALS (WR>=70%, n>=50)")
    for f in strong[:20]:
        print(f"  {f['test_id']} {f['symbol']} hp={f['hold_period']} WR={f['win_rate']:.2%} n={f['signal_count']} avg_ret={f['avg_return']:.4f} sharpe={f['sharpe_ratio']:.2f}")

# Print best per test
print("\n## BEST PER TEST")
for test_id in sorted(by_test.keys()):
    best = max(by_test[test_id], key=lambda x: x['win_rate'] * min(x['signal_count']/150, 1))
    print(f"  {test_id}: {best['symbol']} hp={best['hold_period']} WR={best['win_rate']:.2%} n={best['signal_count']} sr={best['sharpe_ratio']:.2f}")

# Print findings summary by symbol
print("\n## FINDS BY SYMBOL")
sym_count = defaultdict(int)
for f in findings:
    sym_count[f['symbol']] += 1
for sym, cnt in sorted(sym_count.items()):
    print(f"  {sym}: {cnt} findings")
