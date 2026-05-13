#!/usr/bin/env python3
"""
round28_a01 — XAUUSD H1 美盘+RSI<40+ATR>0.35%做多 精密持有期扫描
"""
import sys, os, json
sys.path.insert(0, 'scripts')

from grid_engine import run_grid

# =====================================================
# 步骤1: XAUUSD精密持有期扫描
# =====================================================
config = {
    "timeframe": "H1",
    "symbols": ["XAUUSD"],
    "entry_condition": "session == 'us' and rsi14 < 40 and atr14 / close > 0.0035",
    "direction": "long",
    "hold_periods": [3, 5, 6, 7, 8, 9, 10, 12, 15, 20],
    "exit_at_close": True,
}
results = run_grid(config)

print("=" * 70)
print("  XAUUSD H1 精密持有期扫描")
print(f"  条件: session == 'us' and rsi14 < 40 and atr14 / close > 0.0035")
print("=" * 70)

xau = results.get("XAUUSD", {})
for hp in sorted(xau.keys(), key=int):
    s = xau[hp]
    cnt = s.get("signal_count", 0)
    if cnt == 0:
        print(f"  Hold {hp:>2}:  no signals")
        continue
    wr = s.get("win_rate", 0) or 0
    avg = s.get("avg_return", 0) or 0
    sh = s.get("sharpe_ratio", 0) or 0
    dd = s.get("max_drawdown", 0) or 0
    flag = " *** NEW BEST!" if wr > 0.6298 else ""
    if wr > 0.6298:
        flag += " (exceeds 62.98% baseline!)"
    print(f"  Hold {hp:>2}:  n={cnt:>4}  avg_ret={avg:>+7.4f}  wr={wr:>6.2%}  sharpe={sh:>6.2f}  max_dd={dd:>7.4f}{flag}")

print()
print("=== BASELINE ===")
print("  Round23/27 hold=7: wr=62.98%, n=705, Sharpe=3.25")
print()

# Find best
best_hp = None
best_wr = 0
best_sharpe = 0
for hp in sorted(xau.keys(), key=int):
    s = xau[hp]
    wr = s.get("win_rate", 0) or 0
    if wr > best_wr:
        best_wr = wr
        best_hp = hp
        best_sharpe = s.get("sharpe_ratio", 0) or 0

print(f"  >>> 最优持有期: hold={best_hp}, wr={best_wr:.4%}, Sharpe={best_sharpe:.2f}")
print()

# =====================================================
# 步骤3: 跨品种验证 hold=7
# =====================================================
print("=" * 70)
print("  跨品种验证 (hold=7)")
print("=" * 70)

symbols_to_test = ["XAGUSD", "US30", "US500", "USTEC", "JP225", "EURUSD", "GBPUSD", "AUDUSD", "HK50"]

config2 = {
    "timeframe": "H1",
    "symbols": symbols_to_test,
    "entry_condition": "session == 'us' and rsi14 < 40 and atr14 / close > 0.0035",
    "direction": "long",
    "hold_periods": [7],
    "exit_at_close": True,
}
results2 = run_grid(config2)

print(f"{'Symbol':>10} | {'n':>5} | {'WR':>7} | {'AvgRet':>8} | {'Sharpe':>7} | {'MaxDD':>8}")
print("-" * 60)
for sym in symbols_to_test:
    s = results2.get(sym, {}).get(7, {})
    cnt = s.get("signal_count", 0)
    wr = s.get("win_rate", 0) or 0
    avg = s.get("avg_return", 0) or 0
    sh = s.get("sharpe_ratio", 0) or 0
    dd = s.get("max_drawdown", 0) or 0
    flag = ""
    if wr >= 0.60:
        flag = " *** STRONG"
    elif wr >= 0.55:
        flag = " * moderate"
    print(f"{sym:>10} | {cnt:>5} | {wr:>6.2%} | {avg:>+7.4f} | {sh:>6.2f} | {dd:>7.4f}{flag}")
print("-" * 60)

# Save results
os.makedirs("reports", exist_ok=True)
output = {
    "round": 28,
    "hypothesis": "round27_a01",
    "xau_results": {str(k): v for k, v in xau.items()},
    "cross_validation": {sym: results2.get(sym, {}).get(7, {}) for sym in symbols_to_test},
    "baseline": {"hold": 7, "win_rate": 0.6298, "n": 705, "sharpe": 3.25},
    "best_hold": best_hp,
    "best_wr": best_wr,
    "improved": best_wr > 0.6298,
}

with open("reports/round28_a01_results.json", "w") as f:
    json.dump(output, f, indent=2, default=str)

print()
print("Results saved to reports/round28_a01_results.json")
