#!/usr/bin/env python3
"""
Round 10 — Analyst: Test round9_a01 hypothesis on M30 timeframe.
Tests A through E as specified in the task.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

# Ensure we can import grid_engine
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from grid_engine import run_grid

logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s | %(message)s")

HOLD_PERIODS = [3, 5, 8, 10, 12, 15, 20]
US_INDICES = ["US500", "USTEC", "US30"]
FX_COMMODITIES = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]

ALL_TESTS = []

# ── Test A: Pure US session baseline (M30) ──
ALL_TESTS.append({
    "name": "A_baseline_us_session_long",
    "config": {
        "timeframe": "M30",
        "symbols": US_INDICES,
        "entry_condition": "session == 'us'",
        "direction": "long",
        "hold_periods": HOLD_PERIODS,
        "exit_at_close": True,
    },
})

# ── Test B: US session + RSI<50 ──
ALL_TESTS.append({
    "name": "B_us_rsi50_long",
    "config": {
        "timeframe": "M30",
        "symbols": US_INDICES,
        "entry_condition": "session == 'us' and rsi14 < 50",
        "direction": "long",
        "hold_periods": HOLD_PERIODS,
        "exit_at_close": True,
    },
})

# ── Test C: US session + RSI<45 ──
ALL_TESTS.append({
    "name": "C_us_rsi45_long",
    "config": {
        "timeframe": "M30",
        "symbols": US_INDICES,
        "entry_condition": "session == 'us' and rsi14 < 45",
        "direction": "long",
        "hold_periods": HOLD_PERIODS,
        "exit_at_close": True,
    },
})

# ── Test D: US session + RSI>50 short ──
ALL_TESTS.append({
    "name": "D_us_rsi50_short",
    "config": {
        "timeframe": "M30",
        "symbols": US_INDICES,
        "entry_condition": "session == 'us' and rsi14 > 50",
        "direction": "short",
        "hold_periods": HOLD_PERIODS,
        "exit_at_close": True,
    },
})

# ── Test E: Cross-asset — US session + RSI<50 on FX ──
ALL_TESTS.append({
    "name": "E_us_rsi50_fx_long",
    "config": {
        "timeframe": "M30",
        "symbols": FX_COMMODITIES,
        "entry_condition": "session == 'us' and rsi14 < 50",
        "direction": "long",
        "hold_periods": [5, 10, 15, 20],
        "exit_at_close": True,
    },
})


def print_results(test_name: str, results: dict):
    meta = results.pop("_meta", {})
    print(f"\n{'='*80}")
    print(f"  TEST: {test_name}")
    print(f"  Condition: {meta.get('config', {}).get('entry_condition', 'N/A')}")
    print(f"  Direction: {meta.get('config', {}).get('direction', 'N/A')}")
    print(f"  Symbols with signals: {meta.get('symbols_with_signals', 0)} / {meta.get('total_symbols', 0)}")
    print(f"{'='*80}")

    if not results:
        print("  (no results)")
        return

    for sym in sorted(results.keys()):
        sym_res = results[sym]
        if not sym_res:
            continue
        print(f"\n  {sym}:")
        print(f"  {'Hold':>5}  {'n':>6}  {'WinRate':>8}  {'AvgRet':>10}  {'Sharpe':>8}  {'MaxDD':>10}  {'Label':>12}")
        print(f"  {'-'*5}  {'-'*6}  {'-'*8}  {'-'*10}  {'-'*8}  {'-'*10}  {'-'*12}")
        for hp in sorted(sym_res.keys(), key=int):
            s = sym_res[hp]
            cnt = s.get("signal_count", 0)
            if cnt == 0:
                print(f"  {hp:>5}  {'0':>6}  {'N/A':>8}  {'N/A':>10}  {'N/A':>8}  {'N/A':>10}  {'NO SIGNAL':>12}")
                continue
            wr = s.get("win_rate", 0) or 0
            avg = s.get("avg_return", 0) or 0
            sh = s.get("sharpe_ratio", 0) or 0
            dd = s.get("max_drawdown", 0) or 0

            # Label
            if cnt < 30:
                label = "INCONCLUSIVE"
            elif wr >= 0.60:
                label = "STRONG"
            elif wr >= 0.55:
                label = "PROMISING"
            elif wr >= 0.50:
                label = "WEAK"
            else:
                label = "BELOW 50%"
            print(f"  {hp:>5}  {cnt:>6}  {wr:>8.2%}  {avg:>+10.6f}  {sh:>8.2f}  {dd:>10.4f}  {label:>12}")


def main():
    all_results = {}

    for test in ALL_TESTS:
        name = test["name"]
        config = test["config"]
        print(f"\n>>> Running {name}...")
        try:
            results = run_grid(config)
            all_results[name] = results
            print_results(name, results)
        except Exception as e:
            print(f"  ERROR running {name}: {e}")
            import traceback
            traceback.print_exc()
            all_results[name] = {"_meta": {"error": str(e), "config": config}}

    # ── Summary extraction ──
    print(f"\n\n{'='*80}")
    print("  SUMMARY OF FINDINGS")
    print(f"{'='*80}")

    summary_data = {}

    for test_name, results in all_results.items():
        meta = results.pop("_meta", {})
        entry_cond = meta.get("config", {}).get("entry_condition", "N/A")
        direction = meta.get("config", {}).get("direction", "N/A")

        test_summary = {
            "name": test_name,
            "entry_condition": entry_cond,
            "direction": direction,
            "symbols": {}
        }

        for sym in sorted(results.keys()):
            sym_res = results[sym]
            if not sym_res:
                continue

            best_hp = None
            best_wr = 0
            best_data = None

            for hp in sorted(sym_res.keys(), key=int):
                s = sym_res[hp]
                cnt = s.get("signal_count", 0)
                if cnt < 30:
                    continue
                wr = s.get("win_rate", 0) or 0
                if wr > best_wr:
                    best_wr = wr
                    best_hp = hp
                    best_data = s

            if best_data:
                test_summary["symbols"][sym] = {
                    "best_hold": best_hp,
                    "win_rate": round(best_wr, 4),
                    "signal_count": best_data["signal_count"],
                    "avg_return": best_data["avg_return"],
                    "sharpe_ratio": best_data["sharpe_ratio"],
                    "max_drawdown": best_data["max_drawdown"],
                }

        summary_data[test_name] = test_summary

        print(f"\n--- {test_name} ---")
        for sym, data in test_summary["symbols"].items():
            wr = data["win_rate"]
            label = "STRONG" if wr >= 0.60 else ("PROMISING" if wr >= 0.55 else ("WEAK" if wr >= 0.50 else "BELOW 50%"))
            print(f"  {sym:<8}: hold={data['best_hold']:>2}  wr={wr:.2%}  n={data['signal_count']:>5}  avg={data['avg_return']:>+.6f}  sharpe={data['sharpe_ratio']:.2f}  -> {label}")

    return all_results, summary_data


if __name__ == "__main__":
    results_data, summary = main()

    # Save raw results for inspection
    out_path = SCRIPT_DIR / "round10_raw_results.json"
    serializable = {}
    for test_name, results in results_data.items():
        serializable[test_name] = {}
        for sym, sym_res in results.items():
            if sym == "_meta":
                serializable[test_name]["_meta"] = sym_res
                continue
            serializable[test_name][sym] = {
                str(hp): stats for hp, stats in sym_res.items()
            }
    with open(out_path, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\nRaw results saved to {out_path}")
