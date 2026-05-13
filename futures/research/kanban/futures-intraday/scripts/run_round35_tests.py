#!/usr/bin/env python3
"""
Round 35 Hypothesis Tests — Futures Intraday Pattern Mining
Runs 4 tests and prints structured results with PROMISING / STRONG flags.
"""

import sys
import logging
import traceback
from pprint import pformat

logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s | %(message)s")

from grid_engine import run_grid

# ---------------------------------------------------------------------------
# Test definitions
# ---------------------------------------------------------------------------

TESTS = [
    {
        "name": "round35_a01a",
        "description": "JP225 M30 Asia+RSI<30 LONG (cross-timeframe validation)",
        "config": {
            "timeframe": "M30",
            "symbols": ["JP225"],
            "entry_condition": "session == 'asia' and rsi14 < 30",
            "direction": "long",
            "hold_periods": [2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 30],
            "exit_at_close": True,
        },
    },
    {
        "name": "round35_a01b",
        "description": "HK50/AUDUSD H1 Asia+RSI<30 LONG (cross-symbol Asia expansion)",
        "config": {
            "timeframe": "H1",
            "symbols": ["HK50", "AUDUSD"],
            "entry_condition": "session == 'asia' and rsi14 < 30",
            "direction": "long",
            "hold_periods": [1, 2, 3, 5, 7, 10, 12, 15, 20],
            "exit_at_close": True,
        },
    },
    {
        "name": "round35_a03",
        "description": "EURUSD H1 Hour=8(London open) SHORT + RSI>50 filter",
        "config": {
            "timeframe": "H1",
            "symbols": ["EURUSD"],
            "entry_condition": "hour == 8 and rsi14 > 50",
            "direction": "short",
            "hold_periods": [1, 2, 3, 5, 7, 10],
            "exit_at_close": True,
        },
    },
    {
        "name": "round35_a04",
        "description": "GBPUSD/EURUSD H1 Asia+RSI<40+ATR>0.25% LONG (expand small sample signal)",
        "config": {
            "timeframe": "H1",
            "symbols": ["GBPUSD", "EURUSD"],
            "entry_condition": "session == 'asia' and rsi14 < 40 and atr14 / close > 0.0025",
            "direction": "long",
            "hold_periods": [1, 2, 3, 5, 7, 10, 15, 20],
            "exit_at_close": True,
        },
    },
]


def fmt_pct(v):
    """Format a decimal as percentage string."""
    if v is None:
        return "   N/A   "
    return f"{v:>+7.2%}"


def fmt_float(v, width=8, decimals=4):
    if v is None:
        return " " * width
    return f"{v:>{width}.{decimals}f}"


def flag_status(n, win_rate):
    """Return a flag string based on win_rate and signal count."""
    if win_rate is None or n == 0:
        return ""
    if win_rate > 0.60:
        return " <<< STRONG"
    if win_rate > 0.55 and n >= 30:
        return " <<< PROMISING"
    return ""


def print_results(test_name, description, results):
    """Pretty-print structured results for one test."""
    meta = results.pop("_meta", {})
    print(f"\n{'=' * 80}")
    print(f"  TEST: {test_name}")
    print(f"  {description}")
    print(f"  Config: {meta.get('config', {}).get('entry_condition', 'N/A')}")
    print(f"  Symbols: {meta.get('total_symbols', 0)} total, "
          f"{meta.get('symbols_with_signals', 0)} with signals")
    print(f"{'=' * 80}")

    if not results:
        print("  (no results)")
        return

    # Sort symbols for consistent output
    for sym in sorted(results.keys()):
        sym_res = results[sym]
        if not sym_res:
            print(f"\n  {sym}:  (no data)")
            continue

        print(f"\n  {sym}:")
        # Header
        print(f"    {'Hold':>5} | {'Signals':>7} | {'Win Rate':>9} | "
              f"{'Avg Return':>10} | {'Sharpe':>7} | {'Max DD':>8} | Flag")
        print(f"    {'-'*5} | {'-'*7} | {'-'*9} | {'-'*10} | {'-'*7} | {'-'*8} | {'-'*15}")

        for hp in sorted(sym_res.keys(), key=int):
            s = sym_res[hp]
            cnt = s.get("signal_count", 0)
            wr = s.get("win_rate", None)
            avg = s.get("avg_return", None)
            sharpe = s.get("sharpe_ratio", None)
            max_dd = s.get("max_drawdown", None)

            flag = flag_status(cnt, wr)

            if cnt == 0:
                print(f"    {hp:>5} | {cnt:>7} |  no signals  |")
            else:
                print(f"    {hp:>5} | {cnt:>7} | {wr:>8.2%} | "
                      f"{avg:>+9.4f} | {sharpe:>7.2f} | {max_dd:>7.2%} |{flag}")

    # Put meta back
    results["_meta"] = meta


def main():
    print("=" * 80)
    print("  ROUND 35 — FUTURES INTRADAY HYPOTHESIS TESTS")
    print(f"  Running {len(TESTS)} tests …")
    print("=" * 80)

    for i, test in enumerate(TESTS, 1):
        name = test["name"]
        desc = test["description"]
        config = test["config"]

        print(f"\n{'─' * 80}")
        print(f"  [{i}/{len(TESTS)}] {name}: {desc}")
        print(f"{'─' * 80}")

        try:
            results = run_grid(config)
            print_results(name, desc, results)
        except Exception as e:
            print(f"\n  ERROR running {name}: {e}")
            traceback.print_exc()

        # Flush output
        sys.stdout.flush()

    print(f"\n{'=' * 80}")
    print("  ROUND 35 — ALL TESTS COMPLETE")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
