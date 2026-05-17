#!/usr/bin/env python3
"""Analyze Round 60 M1/M5 results and find best patterns."""
import json
import sys
from pathlib import Path

with open("logs/round60_m1m5_results.json") as f:
    data = json.load(f)

MIN_SIGNALS = 20

def fmt_pct(v):
    if v is None:
        return "N/A"
    return f"{v:.2%}"

print("=" * 90)
print("  ROUND 60 — M1/M5 SCALPING RESULTS ANALYSIS")
print("=" * 90)

findings = []

for test_id, sym_results in data.items():
    for sym, holds in sym_results.items():
        best_entry = None
        for hp_str, metrics in holds.items():
            hp = int(hp_str)
            n = metrics.get('signal_count', 0)
            wr = metrics.get('win_rate', None)
            sharpe = metrics.get('sharpe_ratio', None)
            avg_ret = metrics.get('avg_return', None)
            max_dd = metrics.get('max_drawdown', None)

            if wr is None or n < MIN_SIGNALS:
                continue

            if best_entry is None or (wr > best_entry['wr'] and n >= MIN_SIGNALS):
                best_entry = {
                    'hp': hp,
                    'n': n,
                    'wr': wr,
                    'sharpe': sharpe,
                    'avg_ret': avg_ret,
                    'max_dd': max_dd,
                }

        if best_entry and best_entry['wr'] >= 0.60:
            findings.append({
                'test_id': test_id,
                'sym': sym,
                **best_entry
            })
            print(f"\n  🏆 {test_id} | {sym}")
            print(f"     Hold={best_entry['hp']:>2}  n={best_entry['n']:>4}  "
                  f"WR={best_entry['wr']:.2%}  Sharpe={best_entry['sharpe']:.2f}  "
                  f"AvgRet={best_entry['avg_ret']:+.5f}  MaxDD={best_entry['max_dd']:.4f}")

# Sort by WR
findings.sort(key=lambda x: x['wr'], reverse=True)

print(f"\n{'='*90}")
print(f"  TOP FINDINGS (WR >= 60%, n >= {MIN_SIGNALS})")
print(f"  Total: {len(findings)}")
print(f"{'='*90}")

# Print detailed table
print(f"\n{'Rank':<5} {'Test':<30} {'Sym':<8} {'HP':<5} {'n':<6} {'WR':<8} {'Sharpe':<8} {'AvgRet':<10} {'MaxDD':<8}")
print(f"{'-'*5} {'-'*30} {'-'*8} {'-'*5} {'-'*6} {'-'*8} {'-'*8} {'-'*10} {'-'*8}")
for i, f in enumerate(findings, 1):
    print(f"{i:<5} {f['test_id']:<30} {f['sym']:<8} {f['hp']:<5} {f['n']:<6} "
          f"{f['wr']:.2%}     {f['sharpe']:<7.2f} {f['avg_ret']:<+9.5f} {f['max_dd']:<7.4f}")

# Save findings
out = []
for f in findings:
    out.append({
        'test_id': f['test_id'],
        'sym': f['sym'],
        'hold': f['hp'],
        'signal_count': f['n'],
        'win_rate': f['wr'],
        'sharpe_ratio': f['sharpe'],
        'avg_return': f['avg_ret'],
        'max_drawdown': f['max_dd'],
    })

with open("logs/round60_findings.json", "w") as f:
    json.dump(out, f, indent=2)

print(f"\nDetailed findings saved to logs/round60_findings.json")
print(f"Top 3 signals:")
for i, f in enumerate(findings[:3], 1):
    print(f"  {i}. {f['test_id']} | {f['sym']} | HP={f['hp']} | WR={f['wr']:.2%} | n={f['n']} | Sharpe={f['sharpe']:.2f}")
