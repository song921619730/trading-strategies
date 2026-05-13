#!/usr/bin/env python3
"""
candlestick_engine.py — Candlestick Pattern Hypothesis Testing Engine

Extends the grid_engine concept by adding candlestick feature columns
before evaluating entry conditions.

Usage:
    from candlestick_engine import run_candlestick_grid

    results = run_candlestick_grid({
        "timeframe": "H1",
        "symbols": ["XAUUSD", "EURUSD"],
        "entry_condition": "`inside_bar` and rsi14 < 40",
        "direction": "long",
        "hold_periods": [1, 3, 5, 7, 10, 15, 20],
    })
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Reuse grid_engine's stat helpers
import sys, os
GRID_DIR = os.path.join(os.path.dirname(__file__), "../../futures-intraday/scripts")
if GRID_DIR not in sys.path:
    sys.path.insert(0, GRID_DIR)

from grid_engine import _compute_stats, _PERIODS_PER_YEAR
from data_loader import load_data, compute_indicators, list_available_symbols
from candlestick_features import add_candlestick_features

log = logging.getLogger("candlestick_engine")


def run_candlestick_grid(config: dict) -> Dict[str, Any]:
    """Execute a candlestick hypothesis test.

    Config keys:
        timeframe (str): 'H1' or 'M30'
        symbols (list, optional): Symbols to test. None = all available.
        entry_condition (str): Pandas eval expression.
            Candlestick columns (inside_bar, doji, etc.) are available.
            IMPORTANT: Backtick-quote candlestick column names!
            E.g. "`inside_bar` and rsi14 < 40"
        direction (str): 'long' or 'short'
        hold_periods (list of int): Hold periods in candle units.
        exit_at_close (bool): Exit at close (True) or open (False).

    Returns:
        dict: Same format as grid_engine.run_grid().
    """
    timeframe = config["timeframe"]
    direction = config.get("direction", "long").lower()
    entry_condition = config["entry_condition"]
    hold_periods = config.get("hold_periods", [1, 3, 5, 10])
    exit_at_close = config.get("exit_at_close", True)
    symbols = config.get("symbols") or None

    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got '{direction}'")
    if timeframe not in _PERIODS_PER_YEAR:
        raise ValueError(f"Unsupported timeframe '{timeframe}'")

    periods_per_year = _PERIODS_PER_YEAR[timeframe]

    # ── 1. Load & prepare data with candlestick features ──
    log.info("Loading %s data …", timeframe)
    raw_data = load_data(timeframe=timeframe, symbols=symbols)
    if not raw_data:
        log.warning("No data loaded.")
        return {"_meta": {"config": config, "total_symbols": 0, "symbols_with_signals": 0}}

    log.info("Computing indicators + candlestick features for %d symbol(s) …", len(raw_data))
    data: Dict[str, pd.DataFrame] = {}
    for sym, df in raw_data.items():
        try:
            df = compute_indicators(df)
            df = add_candlestick_features(df)
            data[sym] = df
        except Exception as exc:
            log.error("Feature computation failed for %s: %s", sym, exc)
            continue

    if not data:
        log.warning("No symbols survived feature computation.")
        return {"_meta": {"config": config, "total_symbols": 0, "symbols_with_signals": 0}}

    # ── 2. Direction sign ──
    dir_sign = 1.0 if direction == "long" else -1.0

    # ── 3. Iterate symbols & holding periods ──
    results: Dict[str, Any] = {}
    symbols_with_signals = 0

    for sym, df in data.items():
        n_rows = len(df)
        if n_rows == 0:
            continue

        close_arr = df["close"].values
        open_arr = df["open"].values

        # Evaluate entry condition
        try:
            condition_mask = df.eval(entry_condition)
        except Exception as exc:
            log.error("eval('%s') failed for %s: %s", entry_condition, sym, exc)
            results[sym] = {hp: _compute_stats(np.array([]), hp, periods_per_year)
                            for hp in hold_periods}
            continue

        mask_arr = condition_mask.values.astype(bool)
        signal_indices = np.where(mask_arr)[0]

        if len(signal_indices) == 0:
            results[sym] = {hp: _compute_stats(np.array([]), hp, periods_per_year)
                            for hp in hold_periods}
            continue

        symbols_with_signals += 1

        period_returns: Dict[int, List[float]] = {hp: [] for hp in hold_periods}

        for i in signal_indices:
            entry_price = close_arr[i]
            for hp in hold_periods:
                exit_idx = i + hp
                if exit_idx >= n_rows:
                    continue
                exit_price = close_arr[exit_idx] if exit_at_close else open_arr[exit_idx]
                ret = (exit_price - entry_price) / entry_price * dir_sign
                period_returns[hp].append(ret)

        sym_results: Dict[int, Dict[str, Any]] = {}
        for hp in hold_periods:
            ret_arr = np.array(period_returns[hp], dtype=np.float64)
            sym_results[hp] = _compute_stats(ret_arr, hp, periods_per_year)

        results[sym] = sym_results

    # ── 4. Metadata ──
    results["_meta"] = {
        "config": config,
        "total_symbols": len(data),
        "symbols_with_signals": symbols_with_signals,
    }

    n_total = sum(
        v.get("signal_count", 0)
        for sym_res in results.values()
        if isinstance(sym_res, dict) and sym_res
        for v in (list(sym_res.values()) if sym_res else [])
        if isinstance(v, dict)
    )
    log.info(
        "Candlestick engine finished — %d symbols, %d with signals, %d total signals",
        len(data), symbols_with_signals, n_total,
    )

    return results
