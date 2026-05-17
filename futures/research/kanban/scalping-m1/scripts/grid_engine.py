#!/usr/bin/env python3
"""grid_engine.py — Scalping M1/M5 Hypothesis Testing Engine

Evaluates an entry-condition expression over OHLCV candle data (M1 or M5),
measures forward returns over multiple holding periods, and returns aggregate
statistics per symbol.

Usage:
    from grid_engine import run_grid

    config = {
        "timeframe": "M5",
        "symbols": ["EURUSD", "XAUUSD"],
        "entry_condition": "session == 'asia' and rsi14 < 25",
        "direction": "long",
        "hold_periods": [1, 3, 5, 10, 20, 30],
        "exit_at_close": True,
    }
    results = run_grid(config)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# 注: 指标计算请直接使用 batch_precompute.compute_all_fast()
# 此引擎仅做条件回测，不计算指标
from data_loader import load_data

# 尝试加载 batch_precompute（全量 509 列）
try:
    _GS = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts")
    if _GS not in sys.path:
        sys.path.insert(0, _GS)
    from batch_precompute import compute_all_fast as _calc_indicators
except Exception:
    _calc_indicators = None

log = logging.getLogger("grid_engine")


def _compute_stats(returns: np.ndarray, hold_period: int, periods_per_year: int) -> Dict[str, Any]:
    """Aggregate statistics from an array of per-trade returns."""
    n = len(returns)
    if n < 5:
        return {"n": n, "win_rate": 0.0, "avg_return": 0.0, "sharpe_ratio": 0.0, "max_drawdown": 0.0}

    win_rate = float((returns > 0).mean())
    avg_return = float(returns.mean())
    std = float(returns.std()) if returns.std() > 0 else 1e-10

    # Annualised Sharpe
    sharpe = (avg_return / std) * np.sqrt(periods_per_year / hold_period)

    # Max drawdown of cumulative returns
    cum = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cum)
    dd = (peak - cum) / peak
    max_dd = float(dd.max())

    return {
        "n": n,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
    }


def _evaluate_condition(df: pd.DataFrame, condition: str) -> pd.Series:
    """Evaluate a condition string against DataFrame columns, return bool Series."""
    try:
        return df.eval(condition)
    except Exception as e:
        log.error("Condition eval failed: %s — %s", condition, e)
        return pd.Series(False, index=df.index)


def run_grid(config: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Run hypothesis grid test over all symbols.

    Returns: dict[symbol → list[result_per_hold_period]]
    """
    timeframe = config["timeframe"]
    symbols = config["symbols"]
    entry_condition = config.get("entry_condition", "")
    direction = config.get("direction", "long")
    hold_periods = config.get("hold_periods", [1, 3, 5, 10])
    exit_at_close = config.get("exit_at_close", True)

    periods_per_year = {"M1": 360000, "M5": 72000}.get(timeframe, 72000)

    if not entry_condition:
        log.error("entry_condition is empty")
        return {}

    log.info("Loading %s data for %s …", timeframe, symbols)
    data = load_data(timeframe=timeframe, symbols=symbols)

    results: Dict[str, List[Dict]] = {}
    for sym, raw_df in data.items():
        df = _calc_indicators(raw_df, timeframe) if _calc_indicators else raw_df
        mask = _evaluate_condition(df, entry_condition)
        entry_prices = df.loc[mask, "close"].values
        entry_indices = df.index[mask]

        if len(entry_prices) < 5:
            log.info("%s: only %d signals for '%s' — skipping", sym, len(entry_prices), entry_condition)
            continue

        sym_results = []
        for hold in hold_periods:
            returns = []
            for i in range(len(entry_indices)):
                entry_idx = entry_indices[i]
                entry_price = entry_prices[i]
                raw_pos = df.index.get_loc(entry_idx)
                pos = raw_pos.start if isinstance(raw_pos, slice) else int(raw_pos)

                if exit_at_close:
                    exit_pos = pos + hold
                else:
                    # Exit at next open (simulates opening next candle)
                    exit_pos = pos + hold

                if exit_pos >= len(df):
                    continue

                exit_price = df.iloc[exit_pos]["close"]

                if direction == "long":
                    ret = (exit_price - entry_price) / entry_price
                else:
                    ret = (entry_price - exit_price) / entry_price

                returns.append(ret)

            returns_arr = np.array(returns, dtype=float)
            stats = _compute_stats(returns_arr, hold, periods_per_year)
            stats["hold_period"] = hold
            sym_results.append(stats)

        if sym_results:
            results[sym] = sym_results
            best = max(sym_results, key=lambda r: r["win_rate"])
            log.info("%s: best hold=%d WR=%.1f%% n=%d Sharpe=%.2f",
                     sym, best["hold_period"], best["win_rate"] * 100, best["n"], best["sharpe_ratio"])

    return results


def print_results_table(results: Dict[str, List[Dict]], title: str = "Results"):
    """Pretty-print results in a markdown table."""
    print(f"\n## {title}\n")
    print(f"| {'品种':<10} | {'Hold':<6} | {'胜率':<7} | {'n':<6} | {'平均收益':<10} | {'Sharpe':<8} | {'MaxDD':<8} |")
    print(f"|{'':->10}|{'':->6}|{'':->7}|{'':->6}|{'':->10}|{'':->8}|{'':->8}|")
    for sym, sym_res in sorted(results.items()):
        for r in sorted(sym_res, key=lambda x: -x["win_rate"]):
            wr = f"{r['win_rate']*100:.1f}%"
            ar = f"{r['avg_return']*100:.3f}%"
            print(f"| {sym:<10} | Hold={r['hold_period']:<3} | {wr:<7} | {r['n']:<6} | {ar:<10} | {r['sharpe_ratio']:<8.2f} | {r['max_drawdown']:<8.2f} |")
