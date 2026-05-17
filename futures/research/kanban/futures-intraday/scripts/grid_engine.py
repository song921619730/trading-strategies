#!/usr/bin/env python3
"""
grid_engine.py — Futures Intraday Hypothesis Testing Engine

Evaluates an entry-condition expression over OHLCV candle data (H1 or M30),
measures forward returns over multiple holding periods, and returns aggregate
statistics per symbol.

Usage (programmatic)::

    from grid_engine import run_grid

    config = {
        "timeframe": "H1",
        "symbols": ["XAUUSDm", "EURUSDm"],
        "entry_condition": "rsi14 < 30 and open > ma20",
        "direction": "long",
        "hold_periods": [1, 3, 5, 10],
        "exit_at_close": True,
    }
    results = run_grid(config)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from data_loader import compute_indicators, load_data

log = logging.getLogger("grid_engine")

# Approximate number of candles per year (used for Sharpe annualisation).
# Futures trade ~23 h/day, ~5.5 days/week → ~6 000 H1 bars / year.
_PERIODS_PER_YEAR: Dict[str, int] = {
    "H1": 6_000,
    "M30": 12_000,
    "M5": 72_000,    # 5 min bars: ~23h/day × 12 bars/h × 365 ≈ 100,740; use 72,000 as conservative
    "M1": 360_000,   # 1 min bars: ~23h/day × 60 bars/h × 365 ≈ 503,700; use 360,000 as conservative
}

# ---------------------------------------------------------------------------
# Core statistics helpers
# ---------------------------------------------------------------------------


def _compute_stats(
    returns: np.ndarray,
    hold_period: int,
    periods_per_year: int,
) -> Dict[str, Any]:
    """Aggregate statistics from an array of per-trade returns.

    Parameters
    ----------
    returns : np.ndarray
        1-D array of realised forward returns (as decimals, e.g. 0.01 = 1%).
    hold_period : int
        Number of candles each return spans (used to annualise Sharpe).
    periods_per_year : int
        Number of candles per year for the current timeframe.

    Returns
    -------
    dict
        Keys: signal_count, avg_return, win_rate, sharpe_ratio, max_drawdown.
    """
    n = len(returns)
    if n == 0:
        return {
            "signal_count": 0,
            "avg_return": None,
            "win_rate": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
        }

    avg_ret = float(returns.mean())
    win_rate = float((returns > 0).mean())
    std_ret = float(returns.std())

    # --- Annualised Sharpe ratio (assuming zero risk-free rate) ---
    # If returns are over *hp* candles, we scale by sqrt(periods_per_year / hp)
    # to approximate a yearly Sharpe.
    if std_ret > 0 and hold_period > 0:
        sharpe = avg_ret / std_ret * np.sqrt(periods_per_year / hold_period)
    else:
        sharpe = 0.0

    # --- Max drawdown (from equity curve of sequential trades) ---
    equity = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    max_dd = float(drawdown.max())

    return {
        "signal_count": n,
        "avg_return": avg_ret,
        "win_rate": win_rate,
        "sharpe_ratio": float(sharpe),
        "max_drawdown": max_dd,
    }


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------


def run_grid(config: dict) -> Dict[str, Any]:
    """Execute a hypothesis test defined by *config*.

    Config keys
    -----------
    timeframe : str
        ``'H1'`` or ``'M30'``.
    symbols : list of str, optional
        Symbols to test.  ``None`` or empty = all available symbols.
    entry_condition : str
        A pandas- / Python- expression evaluated per row.
        Example: ``'rsi14 < 30 and open > ma20'``
        Column names from ``compute_indicators()`` are available.
    direction : str
        ``'long'`` or ``'short'``.
    hold_periods : list of int
        Number of candles to hold (e.g. ``[1, 3, 5, 10]``).
    exit_at_close : bool
        If ``True`` (default), exit at the close of the last holding candle.
        If ``False``, exit at the open of the last holding candle.

    Returns
    -------
    dict
        Nested structure::

            {
                "XAUUSDm": {
                    1:  {"signal_count": …, "avg_return": …, …},
                    3:  {"signal_count": …, "avg_return": …, …},
                    …
                },
                "EURUSDm": { … },
                "_meta": {
                    "config": { … },       # the input config
                    "total_symbols": 2,
                    "symbols_with_signals": 2,
                }
            }

        Each per-(symbol, hold_period) entry contains:
            signal_count, avg_return, win_rate, sharpe_ratio, max_drawdown.
    """
    # --- Normalise config ---
    timeframe = config["timeframe"]
    direction = config.get("direction", "long").lower()
    entry_condition = config["entry_condition"]
    hold_periods = config.get("hold_periods", [1, 3, 5, 10])
    exit_at_close = config.get("exit_at_close", True)
    symbols = config.get("symbols") or None  # None = load all

    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got '{direction}'")

    if timeframe not in _PERIODS_PER_YEAR:
        raise ValueError(f"Unsupported timeframe '{timeframe}'")

    periods_per_year = _PERIODS_PER_YEAR[timeframe]

    # --- 1. Load & prepare data ---
    log.info("Loading %s data …", timeframe)
    raw_data = load_data(timeframe=timeframe, symbols=symbols)

    if not raw_data:
        log.warning("No data loaded. Returning empty results.")
        return {"_meta": {"config": config, "total_symbols": 0, "symbols_with_signals": 0}}

    log.info("Computing indicators for %d symbol(s) …", len(raw_data))
    data: Dict[str, pd.DataFrame] = {}
    for sym, df in raw_data.items():
        try:
            data[sym] = compute_indicators(df)
        except Exception as exc:
            log.error("compute_indicators failed for %s: %s", sym, exc)
            continue

    if not data:
        log.warning("No symbols survived indicator computation.")
        return {"_meta": {"config": config, "total_symbols": 0, "symbols_with_signals": 0}}

    # --- 2. Direction sign ---
    dir_sign = 1.0 if direction == "long" else -1.0

    # --- 3. Iterate symbols & holding periods ---
    results: Dict[str, Any] = {}
    symbols_with_signals = 0

    for sym, df in data.items():
        n_rows = len(df)
        if n_rows == 0:
            continue

        log.debug("Processing %s …", sym)
        close_arr = df["close"].values
        open_arr = df["open"].values

        # Evaluate entry condition → boolean mask
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
            log.debug("  No signals for %s", sym)
            results[sym] = {hp: _compute_stats(np.array([]), hp, periods_per_year)
                            for hp in hold_periods}
            continue

        symbols_with_signals += 1

        # Pre-allocate a dict of lists for each hold period
        period_returns: Dict[int, List[float]] = {hp: [] for hp in hold_periods}

        # Walk through each signal and record forward returns
        for i in signal_indices:
            entry_price = close_arr[i]

            for hp in hold_periods:
                exit_idx = i + hp
                if exit_idx >= n_rows:
                    # Not enough data for this hold period
                    continue

                if exit_at_close:
                    exit_price = close_arr[exit_idx]
                else:
                    exit_price = open_arr[exit_idx]

                # Direction-adjusted return
                ret = (exit_price - entry_price) / entry_price * dir_sign
                period_returns[hp].append(ret)

        # Compute stats per hold period
        sym_results: Dict[int, Dict[str, Any]] = {}
        for hp in hold_periods:
            ret_arr = np.array(period_returns[hp], dtype=np.float64)
            sym_results[hp] = _compute_stats(ret_arr, hp, periods_per_year)

        results[sym] = sym_results

    # --- 4. Attach metadata ---
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
        "Grid engine finished — %d symbols, %d with signals, %d total signals",
        len(data),
        symbols_with_signals,
        n_total,
    )

    return results


# ---------------------------------------------------------------------------
# CLI entry point (convenience for manual testing)
# ---------------------------------------------------------------------------
def _demo() -> None:
    """Run a quick demo with a built-in config (requires data on disk)."""
    config = {
        "timeframe": "H1",
        "symbols": None,  # all available
        "entry_condition": "rsi14 < 30 and open > ma20",
        "direction": "long",
        "hold_periods": [1, 3, 5, 10],
        "exit_at_close": True,
    }
    results = run_grid(config)

    # Pretty-print a summary
    meta = results.pop("_meta", {})
    print(f"\n{'='*70}")
    print(f"  Grid Engine Demo Results")
    print(f"  Config: {meta.get('config', {}).get('entry_condition', 'N/A')}")
    print(f"  Symbols: {meta.get('total_symbols', 0)} total, "
          f"{meta.get('symbols_with_signals', 0)} with signals")
    print(f"{'='*70}")

    for sym, sym_res in sorted(results.items()):
        if not sym_res:
            continue
        print(f"\n  {sym}:")
        for hp in sorted(sym_res.keys(), key=int):
            s = sym_res[hp]
            cnt = s.get("signal_count", 0)
            if cnt == 0:
                print(f"    Hold {hp:>2}:  no signals")
                continue
            avg = s.get("avg_return", 0) or 0
            wr = s.get("win_rate", 0) or 0
            sh = s.get("sharpe_ratio", 0) or 0
            dd = s.get("max_drawdown", 0) or 0
            print(f"    Hold {hp:>2}:  n={cnt:>4}  avg_ret={avg:>+7.4f}  "
                  f"win_rate={wr:>6.2%}  sharpe={sh:>6.2f}  max_dd={dd:>7.4f}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s")
    _demo()
