#!/usr/bin/env python3
"""
Analyst task: test hypothesis round20_a01
XAUUSD M30 美盘+RSI<40+ATR>0.35%做多 hold扫描 寻找最优持有期
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s")

from grid_engine import run_grid

# NOTE: Using "XAUUSD" (without "m") because the actual parquet file is XAUUSD.parquet
config = {
    "timeframe": "M30",
    "symbols": ["XAUUSD"],
    "entry_condition": "(session == 'us') and (rsi14 < 40) and (atr14 / close > 0.0035)",
    "direction": "long",
    "hold_periods": [3, 5, 7, 10, 12, 15, 20],
    "exit_at_close": True,
}

results = run_grid(config)
meta = results.pop("_meta", {})
print(f"Entry condition: {meta.get('config', {}).get('entry_condition', '?')}")
print(f"Direction: {meta.get('config', {}).get('direction', '?')}")
print(f"Symbols with signals: {meta.get('symbols_with_signals', 0)} / {meta.get('total_symbols', 0)}")
print()

for sym, sym_res in sorted(results.items()):
    for hp in sorted(sym_res.keys(), key=int):
        s = sym_res[hp]
        cnt = s.get("signal_count", 0)
        if cnt == 0:
            continue
        wr = s.get("win_rate", 0) or 0
        avg = s.get("avg_return", 0) or 0
        sharpe = s.get("sharpe_ratio", 0) or 0
        dd = s.get("max_drawdown", 0) or 0
        print(f"  {sym:<12} hold={hp:>2}  n={cnt:>4}  wr={wr:>6.2%}  avg={avg:>+8.5f}  sharpe={sharpe:>6.2f}  dd={dd:>7.4f}")

# Print machine-readable results for parsing
print("\n---MACHINE_RESULTS---")
import json
# Prepare clean results
clean = {}
for sym, sym_res in sorted(results.items()):
    clean[sym] = {}
    for hp in sorted(sym_res.keys(), key=int):
        s = sym_res[hp]
        clean[sym][str(hp)] = {
            "signal_count": s.get("signal_count", 0),
            "win_rate": s.get("win_rate", 0) or 0,
            "avg_return": s.get("avg_return", 0) or 0,
            "sharpe_ratio": s.get("sharpe_ratio", 0) or 0,
            "max_drawdown": s.get("max_drawdown", 0) or 0,
        }
clean["_meta"] = meta
print(json.dumps(clean, indent=2))
