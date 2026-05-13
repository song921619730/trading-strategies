#!/usr/bin/env python3
"""data_loader.py — Scalping M1/M5 Data Loader & Indicator Calculator

Reads parquet files from ../data/{M1,M5}/{symbol}.parquet.
Provides functions for listing symbols, loading data, computing technical indicators.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

log = logging.getLogger("data_loader")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

TIMEFRAME_DIRS = {
    "M1": DATA_DIR / "M1",
    "M5": DATA_DIR / "M5",
}

PERIODS_PER_YEAR: Dict[str, int] = {
    "M1": 360_000,   # 1 min × 60 × 23 × 5.5 × 52
    "M5": 72_000,    # 5 min × 12 × 23 × 5.5 × 52
}


def list_available_symbols(timeframe: str = "M5") -> List[str]:
    """列出指定时间框架下可用的品种"""
    d = TIMEFRAME_DIRS.get(timeframe)
    if not d or not d.exists():
        return []
    return sorted([p.stem for p in d.glob("*.parquet")])


def load_data(timeframe: str = "M5", symbols: Optional[List[str]] = None,
              start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    """加载 OHLCV 数据

    Parameters
    ----------
    timeframe : str
        "M1" or "M5"
    symbols : list or None
        None = 全部可用品种
    start, end : str or None
        日期过滤 "YYYY-MM-DD"

    Returns
    -------
    dict[symbol → DataFrame with columns: open,high,low,close,tick_volume,spread,real_volume]
    """
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
            log.warning("Missing data file: %s", fp)
            continue
        try:
            df = pd.read_parquet(fp)
        except Exception as e:
            log.error("Failed to read %s: %s", fp, e)
            continue

        if df.empty:
            continue

        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
                df = df.set_index("time")
            else:
                log.warning("No datetime index or 'time' column in %s", fp)
                continue

        df = df.sort_index()
        if start:
            df = df[df.index >= start]
        if end:
            df = df[df.index <= end]

        # Standard column names
        required = ["open", "high", "low", "close"]
        if not all(c in df.columns for c in required):
            log.warning("Missing required columns in %s, has: %s", fp, list(df.columns))
            continue

        result[sym] = df
        log.info("Loaded %s %s: %d rows [%s → %s]",
                 sym, timeframe, len(df),
                 df.index[0].strftime("%Y-%m-%d"),
                 df.index[-1].strftime("%Y-%m-%d"))

    return result


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """在 DataFrame 上计算技术指标（原地修改）

    新增列：
      - rsi14           : 14-period RSI
      - atr14           : 14-period ATR (absolute value)
      - atr14_pct       : ATR/close * 100
      - ma20, ma50      : 简单移动平均线
      - consecutive_bear: 连续阴线计数
      - session         : 交易时段 (asia/europe/us)
    """
    df = df.copy()

    # ── RSI(14) ──
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi14"] = 100.0 - (100.0 / (1.0 + rs))

    # ── ATR(14) ──
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14, min_periods=14).mean()
    df["atr14_pct"] = df["atr14"] / df["close"] * 100

    # ── MA ──
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()

    # ── Consecutive bear candles ──
    bear = (df["close"] < df["open"]).astype(int)
    df["consecutive_bear"] = bear.groupby((bear == 0).cumsum()).cumsum()

    # ── Consecutive bull candles ──
    bull = (df["close"] > df["open"]).astype(int)
    df["consecutive_bull"] = bull.groupby((bull == 0).cumsum()).cumsum()

    # ── Time columns ──
    df["hour"] = df.index.hour
    df["minute"] = df.index.minute

    # ── Session ──
    def _session(h: int) -> str:
        if 0 <= h < 8:
            return "asia"
        elif 8 <= h < 13:
            return "europe"
        else:
            return "us"

    df["session"] = df.index.hour.map(_session)

    return df
