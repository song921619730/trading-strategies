#!/usr/bin/env python3
"""
Round 36 Hypothesis Tests — Futures Intraday Pattern Mining
Tests the most promising extension from Round 35:
降低ATR阈值扩大亚盘外汇做多样本验证
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
        "name": "round36_a02",
        "description": "GBPUSD/EURUSD H1 Asia+RSI<40+ATR>0.20% LONG — 降低ATR阈值扩大样本验证",
        "config": {
            "timeframe": "H1",
            "symbols": ["GBPUSD", "EURUSD"],
            "entry_condition": "session == 'asia' and rsi14 < 40 and atr14 / close > 0.0020",
            "direction": "long",
            "hold_periods": [1, 2, 3, 5, 7, 10, 12, 15, 20],
            "exit_at_close": True,
        },
    },
    {
        "name": "round36_a01",
        "description": "EURUSD/GBPUSD/USDCHF H1 Hour=8(London open)+RSI>50 SHORT 跨品种扩展",
        "config": {
            "timeframe": "H1",
            "symbols": ["EURUSD", "GBPUSD", "USDCHF"],
            "entry_condition": "hour == 8 and rsi14 > 50",
            "direction": "short",
            "hold_periods": [1, 2, 3, 5, 7, 10],
            "exit_at_close": True,
        },
    },
    {
        "name": "round36_a03",
        "description": "EURUSD H1 Hour=8 SHORT + RSI>50 + ATR>0.15% 增强版尝试突破61.25%",
        "config": {
            "timeframe": "H1",
            "symbols": ["EURUSD"],
            "entry_condition": "hour == 8 and rsi14 > 50 and atr14 / close > 0.0015",
            "direction": "short",
            "hold_periods": [1, 2, 3, 5, 7, 10],
            "exit_at_close": True,
        },
    },
    {
        "name": "round36_a04",
        "description": "JP225 M30 Asia+RSI<30+ATR>0.25% LONG 添加ATR过滤尝试突破60%",
        "config": {
            "timeframe": "M30",
            "symbols": ["JP225"],
            "entry_condition": "session == 'asia' and rsi14 < 30 and atr14 / close > 0.0025",
            "direction": "long",
            "hold_periods": [10, 14, 16, 20, 24, 30],
            "exit_at_close": True,
        },
    },
]


def fmt_pct(v):
    if v is None:
        return "   N/A   "
    return f"{v:>+7.2%}"


def fmt_float(v, width=8, decimals=4):
    if v is None:
        return f"{'N/A':>{width}}"
    return f"{v:>{width}.{decimals}f}"


def print_results_table(results, test_name):
    """Pretty-print results for a single test's symbols + hold periods."""
    meta = results.get("_meta", {})
    print(f"\n{'='*70}")
    print(f"📊 {test_name}")
    print(f"{'='*70}")

    for sym in sorted(results.keys()):
        if sym == "_meta":
            continue
        sym_data = results[sym]
        print(f"\n  🔹 {sym} — {meta.get('config', {}).get('entry_condition', '')}")
        print(f"  {'Hold':>6} {'Signals':>8} {'Win Rate':>10} {'Avg Ret':>10} {'Sharpe':>8} {'Max DD':>8}")
        print(f"  {'-'*54}")
        for hp in sorted(sym_data.keys(), key=int):
            d = sym_data[hp]
            label = ""
            wr = d.get("win_rate", 0) or 0
            n = d.get("signal_count", 0) or 0
            if wr >= 0.60 and n >= 30:
                label = " 🔴 STRONG"
            elif wr >= 0.55 and n >= 30:
                label = " 🔸 PROMISING"
            elif wr < 0.45 and n >= 30:
                label = " 🔄 REVERSAL"
            elif n < 30:
                label = " ⚠️ 小样本"
            print(f"  {hp:>6} {n:>8} {fmt_pct(wr)} {fmt_pct(d.get('avg_return'))} {fmt_float(d.get('sharpe_ratio'), width=8, decimals=2)} {fmt_pct(d.get('max_drawdown'))}{label}")

    print()


def main():
    print("🚀 Round 36 — Hypothesis Tests")
    print("=" * 70)

    for test in TESTS:
        name = test["name"]
        desc = test["description"]
        config = test["config"]

        print(f"\n▶ Running: {name}")
        print(f"  {desc}")
        print(f"  Config: {pformat(config, indent=4)}")

        try:
            results = run_grid(config)
            print_results_table(results, f"{name}: {desc}")

            # Find best per symbol
            for sym in sorted(results.keys()):
                if sym == "_meta":
                    continue
                sym_data = results[sym]
                best_hp = None
                best_wr = 0.0
                best_n = 0
                for hp, d in sym_data.items():
                    wr = d.get("win_rate", 0) or 0
                    n = d.get("signal_count", 0) or 0
                    if wr > best_wr and n >= 10:
                        best_wr = wr
                        best_hp = hp
                        best_n = n
                if best_hp is not None:
                    bd = sym_data[best_hp]
                    print(f"  🏆 {sym} BEST: hold={best_hp} WR={best_wr:.2%} n={best_n} Sharpe={fmt_float(bd.get('sharpe_ratio'))}")

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            traceback.print_exc()

    print("\n✅ Round 36 tests complete.")


if __name__ == "__main__":
    main()
