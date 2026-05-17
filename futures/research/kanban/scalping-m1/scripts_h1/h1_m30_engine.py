#!/usr/bin/env python3
"""H1/M30 Research Engine — Futures Intraday European/Asian Session Pattern Discovery

Extends data_loader and grid_engine for H1/M30 timeframes.
Focuses on European (08:00-13:00 UTC) and Asian (00:00-08:00 UTC) session patterns.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

log = logging.getLogger("h1_m30_engine")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

TIMEFRAME_DIRS = {
    "H1": DATA_DIR / "H1",
    "M30": DATA_DIR / "M30",
}

PERIODS_PER_YEAR: Dict[str, int] = {
    "H1": 5000,    # ~1 hour × 23 × 5.5 × 52
    "M30": 10000,  # ~30 min × 23 × 5.5 × 52
}

SYMBOLS_ALL = [
    "AUDUSD", "EURUSD", "GBPUSD", "HK50", "JP225",
    "UKOIL", "US30", "US500", "USDCHF", "USDJPY",
    "USOIL", "USTEC", "XAGUSD", "XAUUSD",
]

def list_available_symbols(timeframe: str) -> List[str]:
    d = TIMEFRAME_DIRS.get(timeframe)
    if not d or not d.exists():
        return []
    return sorted([p.stem for p in d.glob("*.parquet")])

def load_data(timeframe: str = "H1", symbols: Optional[List[str]] = None,
              start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    d = TIMEFRAME_DIRS.get(timeframe)
    if not d or not d.exists():
        log.warning("Data directory not found: %s", d)
        return {}

    if symbols is None:
        symbols = list_available_symbols(timeframe)

    result = {}
    for sym in symbols:
        fp = d / f"{sym}.parquet"
        if not fp.exists():
            log.warning("Missing data: %s", fp)
            continue
        try:
            df = pd.read_parquet(fp)
        except Exception as e:
            log.error("Failed to read %s: %s", fp, e)
            continue

        if df.empty:
            continue
        if not isinstance(df.index, pd.DatetimeIndex):
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
                df = df.set_index("time")
            else:
                continue

        df = df.sort_index()
        if start:
            df = df[df.index >= start]
        if end:
            df = df[df.index <= end]

        required = ["open", "high", "low", "close"]
        if not all(c in df.columns for c in required):
            continue

        result[sym] = df
    return result

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical indicators for H1/M30 data."""
    df = df.copy()

    # RSI(14)
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi14"] = 100.0 - (100.0 / (1.0 + rs))

    # ATR(14)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14, min_periods=14).mean()
    df["atr14_pct"] = df["atr14"] / df["close"] * 100

    # MAs
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()

    # Consecutive bear/bull
    bear = (df["close"] < df["open"]).astype(int)
    df["consecutive_bear"] = bear.groupby((bear == 0).cumsum()).cumsum()
    bull = (df["close"] > df["open"]).astype(int)
    df["consecutive_bull"] = bull.groupby((bull == 0).cumsum()).cumsum()

    # Time columns
    df["hour"] = df.index.hour
    df["minute"] = df.index.minute
    df["dayofweek"] = df.index.dayofweek

    # Session: Asia 0-8, Europe 8-13, US 13-22
    def _session(h: int) -> str:
        if 0 <= h < 8:
            return "asia"
        elif 8 <= h < 13:
            return "europe"
        else:
            return "us"
    df["session"] = df.index.hour.map(_session)

    # Price relative to MA
    df["above_ma20"] = (df["close"] > df["ma20"]).astype(int)
    df["above_ma50"] = (df["close"] > df["ma50"]).astype(int)

    # Candle body
    df["body"] = abs(df["close"] - df["open"])
    df["body_pct"] = df["body"] / df["open"] * 100
    df["is_bear"] = (df["close"] < df["open"]).astype(int)

    return df


def run_test(df: pd.DataFrame, condition_mask: pd.Series, label: str,
             direction: str = "long", hold_range: Optional[List[int]] = None,
             periods_per_year: int = 5000) -> Dict[str, Any]:
    """
    Test a boolean condition mask on DataFrame.
    Returns dict with results per hold period.
    """
    if hold_range is None:
        # H1: hold up to 24 bars (1 day), M30: up to 48 bars
        pass  # set per call

    entries = df[condition_mask].copy()
    n_signals = len(entries)

    results = {}
    for hold in hold_range:
        returns = []
        for idx in entries.index:
            entry_price = df.loc[idx, "close"]
            pos = df.index.get_loc(idx)
            exit_pos = pos + hold
            if exit_pos >= len(df):
                continue
            exit_price = df.iloc[exit_pos]["close"]

            if direction == "long":
                ret = (exit_price - entry_price) / entry_price
            else:
                ret = (entry_price - exit_price) / entry_price
            returns.append(ret)

        if len(returns) < 5:
            continue

        ret_arr = np.array(returns, dtype=float)
        n = len(ret_arr)
        wr = float((ret_arr > 0).mean())
        avg_ret = float(ret_arr.mean())
        std = float(ret_arr.std()) if ret_arr.std() > 0 else 1e-10
        sharpe = (avg_ret / std) * np.sqrt(periods_per_year / hold) if hold > 0 else 0.0

        # Max drawdown
        cum = np.cumprod(1 + ret_arr)
        peak = np.maximum.accumulate(cum)
        dd = (peak - cum) / peak
        max_dd = float(dd.max()) if len(dd) > 0 else 0.0

        results[hold] = {
            "n": n, "win_rate": wr, "avg_return": avg_ret,
            "sharpe": sharpe, "max_dd": max_dd,
        }

    return results


def print_results(results: Dict[int, Dict], label: str, n_signals: int, symbol: str):
    """Pretty print test results."""
    print(f"\n{'='*60}")
    print(f"📊 {symbol} | {label}")
    print(f"   Total signals: {n_signals}")
    print(f"{'='*60}")
    if not results:
        print("   No valid results (insufficient data)")
        return

    print(f" {'Hold':<6} {'WinRate':<9} {'n':<6} {'AvgRet%':<10} {'Sharpe':<9} {'MaxDD':<9}")
    print(f" {'-'*5} {'-'*8} {'-'*5} {'-'*9} {'-'*8} {'-'*8}")

    best_wr = max(results.items(), key=lambda x: x[1]["win_rate"])
    best_sharpe = max(results.items(), key=lambda x: x[1]["sharpe"])

    for hold in sorted(results.keys()):
        r = results[hold]
        wr_mark = " ★" if hold == best_wr[0] and r["win_rate"] >= 0.60 else ""
        sh_mark = " ◆" if hold == best_sharpe[0] and r["sharpe"] >= 3.0 else ""
        print(f" {hold:<6} {r['win_rate']*100:>6.1f}%{wr_mark:<2} {r['n']:<6} {r['avg_return']*100:>7.3f}%{'':<2} {r['sharpe']:<9.2f} {r['max_dd']:<9.2f}")

    print(f"\n   🏆 Best WR: hold={best_wr[0]} WR={best_wr[1]['win_rate']*100:.1f}% n={best_wr[1]['n']} Sharpe={best_wr[1]['sharpe']:.2f}")
    print(f"   🏆 Best Sharpe: hold={best_sharpe[0]} WR={best_sharpe[1]['win_rate']*100:.1f}% n={best_sharpe[1]['n']} Sharpe={best_sharpe[1]['sharpe']:.2f}")


def evaluate_pattern(df: pd.DataFrame, sym: str, entry_condition: str, label: str,
                     direction: str = "long",
                     hold_range: Optional[List[int]] = None,
                     tf: str = "H1") -> Dict:
    """Evaluate a pattern via string expression."""
    if hold_range is None:
        if tf == "H1":
            hold_range = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24]
        else:  # M30
            hold_range = [1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 30, 48]

    pppy = PERIODS_PER_YEAR.get(tf, 5000)

    try:
        mask = df.eval(entry_condition)
    except Exception as e:
        log.error("Condition eval failed: %s — %s", entry_condition, e)
        return {}

    n_signals = mask.sum()
    if n_signals < 5:
        return {}

    results = run_test(df, mask, label, direction, hold_range, pppy)
    print_results(results, label, n_signals, sym)

    # Return best result
    if results:
        best = max(results.items(), key=lambda x: x[1]["win_rate"])
        return {
            "symbol": sym,
            "label": label,
            "direction": direction,
            "n_signals": n_signals,
            "best_hold": best[0],
            "best_wr": best[1]["win_rate"],
            "best_n": best[1]["n"],
            "best_avg_ret": best[1]["avg_return"],
            "best_sharpe": best[1]["sharpe"],
            "all_results": results,
        }
    return {}
