#!/usr/bin/env python3
"""
data_loader.py — Futures Intraday Data Loader & Indicator Calculator

Reads parquet files from ../data/H1/{symbol}.parquet and ../data/M30/{symbol}.parquet.
Provides functions for listing symbols, loading data, computing technical indicators,
and resampling to daily timeframe.

DataFrame schema (from fetch_store_data.py):
    Index: DatetimeIndex named 'time' (UTC)
    Columns: open, high, low, close, tick_volume, spread, real_volume
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

log = logging.getLogger("data_loader")

# --- Path resolution ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent  # futures-intraday/
DATA_DIR = PROJECT_DIR / "data"

H1_DIR = DATA_DIR / "H1"
M30_DIR = DATA_DIR / "M30"

TIMEFRAME_DIRS = {
    "H1": H1_DIR,
    "M30": M30_DIR,
}

# ---------------------------------------------------------------------------
# 1.  Symbol discovery
# ---------------------------------------------------------------------------


def list_available_symbols(timeframe: Optional[str] = None) -> List[str]:
    """Return sorted list of symbol names that have data on disk.

    Parameters
    ----------
    timeframe : str, optional
        If 'H1' or 'M30', only scan that subdirectory.
        If None, scan both and return union.

    Returns
    -------
    List[str]
        Alphabetically sorted symbol names (without .parquet extension).
    """
    if timeframe is not None:
        tf_dirs = [TIMEFRAME_DIRS[timeframe]]
    else:
        tf_dirs = [H1_DIR, M30_DIR]

    symbols: set[str] = set()
    for d in tf_dirs:
        if not d.is_dir():
            log.warning("Data directory not found: %s", d)
            continue
        for fpath in d.glob("*.parquet"):
            symbols.add(fpath.stem)

    return sorted(symbols)


# ---------------------------------------------------------------------------
# 2.  Data loading
# ---------------------------------------------------------------------------


def load_data(
    timeframe: str = "H1",
    symbols: Optional[List[str]] = None,
) -> Dict[str, pd.DataFrame]:
    """Load parquet files for the given timeframe and symbol list.

    Parameters
    ----------
    timeframe : str
        One of ``'H1'`` or ``'M30'``.
    symbols : list of str, optional
        Symbols to load.  If ``None``, all available symbols are loaded.

    Returns
    -------
    dict[str, pd.DataFrame]
        Mapping of ``{symbol: DataFrame}``.  The DataFrame has a
        ``DatetimeIndex`` named ``'time'`` and columns ``open, high, low,
        close, tick_volume, spread, real_volume``.

    Raises
    ------
    ValueError
        If *timeframe* is invalid.
    """
    if timeframe not in TIMEFRAME_DIRS:
        raise ValueError(f"Unknown timeframe '{timeframe}'.  Choose from {list(TIMEFRAME_DIRS)}")

    data_dir = TIMEFRAME_DIRS[timeframe]
    if not data_dir.is_dir():
        log.warning("Data directory does not exist: %s", data_dir)
        return {}

    if symbols is None:
        symbols = list_available_symbols(timeframe=timeframe)

    result: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        fpath = data_dir / f"{sym}.parquet"
        if not fpath.is_file():
            log.warning("File not found, skipping: %s", fpath)
            continue
        try:
            df = pd.read_parquet(fpath)
            # Ensure the index is a DatetimeIndex named 'time'
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            df.index.name = "time"
            df.sort_index(inplace=True)
            result[sym] = df
            log.debug("Loaded %s (%s) — %d rows", sym, timeframe, len(df))
        except Exception as exc:
            log.error("Failed to load %s: %s", fpath, exc)

    if not result:
        log.warning("No data loaded for timeframe=%s, symbols=%s", timeframe, symbols)

    return result


# ---------------------------------------------------------------------------
# 3.  Indicator computation
# ---------------------------------------------------------------------------


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (exponential smoothing with alpha = 1/period)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (simple moving average of TR)."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period).mean()


def _bollinger_bands(
    series: pd.Series, period: int = 20, n_std: float = 2.0
) -> tuple[pd.Series, pd.Series]:
    """Return (upper_band, lower_band) for a simple moving-average envelope."""
    ma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std(ddof=0)
    return ma + n_std * std, ma - n_std * std


def _session_label(hour: int) -> str:
    """Classify a UTC hour into a trading session.

    Approximate boundaries (UTC):
        Asia   00:00 – 07:59
        Europe 08:00 – 15:59
        US     16:00 – 23:59
    """
    if hour < 8:
        return "asia"
    if hour < 16:
        return "europe"
    return "us"


def _consecutive_counts(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (consecutive_bull, consecutive_bear) Series.

    A candle is *bull* when ``close > open``, *bear* when ``close < open``.
    Doji candles (close == open) reset both counters to zero.
    """
    bull = (df["close"] > df["open"]).astype(int)
    bear = (df["close"] < df["open"]).astype(int)

    # Group consecutive identical values
    bull_groups = (bull != bull.shift()).cumsum()
    bear_groups = (bear != bear.shift()).cumsum()

    bull_cnt = bull.groupby(bull_groups).cumsum()
    bear_cnt = bear.groupby(bear_groups).cumsum()

    return bull_cnt, bear_cnt


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical-indicator columns to an OHLCV DataFrame.

    Input DataFrame must have columns
    ``open, high, low, close`` and a ``DatetimeIndex`` named ``'time'``.

    Added columns
    -------------
    atr14                 : Average True Range (14-period)
    rsi14                 : Relative Strength Index (14-period, Wilder's)
    ma20, ma50, ma200     : Simple moving averages of close
    bb_upper, bb_lower    : Bollinger Bands (20,2)
    pct_chg               : Close-to-close percentage change
    gap_pct               : (open - prev_close) / prev_close
    session               : Trading session label ('asia' / 'europe' / 'us')
    dayofweek             : Day of week (0=Monday … 6=Sunday)
    hour                  : Hour of day (0–23, UTC)
    consecutive_bull_count: Number of consecutive bullish candles
    consecutive_bear_count: Number of consecutive bearish candles

    Returns
    -------
    pd.DataFrame
        Same as input with indicator columns appended.  Rows at the beginning
        of the series may contain NaN where rolling windows are incomplete.
    """
    df = df.copy()

    # --- Price-derived indicators ---
    df["atr14"] = _atr(df, period=14)
    df["rsi14"] = _rsi(df["close"], period=14)

    df["ma20"] = df["close"].rolling(window=20).mean()
    df["ma50"] = df["close"].rolling(window=50).mean()
    df["ma200"] = df["close"].rolling(window=200).mean()

    df["bb_upper"], df["bb_lower"] = _bollinger_bands(df["close"], period=20, n_std=2.0)

    df["pct_chg"] = df["close"].pct_change() * 100.0  # percentage
    df["gap_pct"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1) * 100.0

    # --- Temporal / session features ---
    df["hour"] = df.index.hour
    df["dayofweek"] = df.index.dayofweek
    df["session"] = df["hour"].apply(_session_label)

    # --- Consecutive candles ---
    bull_cnt, bear_cnt = _consecutive_counts(df)
    df["consecutive_bull_count"] = bull_cnt
    df["consecutive_bear_count"] = bear_cnt

    return df


# ---------------------------------------------------------------------------
# 4.  Daily resampling (D1 context)
# ---------------------------------------------------------------------------


def resample_to_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Resample intraday OHLCV data to daily bars.

    Aggregation:
        open          : first open of the day
        high          : max high of the day
        low           : min low of the day
        close         : last close of the day
        tick_volume   : sum
        spread        : mean (volume-weighted would be better but simple average
                         is sufficient for context)
        real_volume   : sum

    Parameters
    ----------
    df : pd.DataFrame
        Intraday DataFrame with ``DatetimeIndex``.

    Returns
    -------
    pd.DataFrame
        Daily OHLCV DataFrame with ``DatetimeIndex`` (date only).
    """
    if df.empty:
        return pd.DataFrame()

    agg_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "tick_volume": "sum",
        "spread": "mean",
        "real_volume": "sum",
    }

    # Only aggregate columns that exist
    agg_dict = {k: v for k, v in agg_dict.items() if k in df.columns}

    daily = df.resample("D").agg(agg_dict)
    daily.index.name = "time"

    return daily


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s")
    print("Available symbols:", list_available_symbols())
    print("Available symbols (H1):", list_available_symbols(timeframe="H1"))
    print("Available symbols (M30):", list_available_symbols(timeframe="M30"))
