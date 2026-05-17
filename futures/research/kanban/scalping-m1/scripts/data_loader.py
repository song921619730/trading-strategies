#!/usr/bin/env python3
"""data_loader.py — Scalping M1/M5 Data Loader

Reads parquet files from ../data/{M1,M5}/{symbol}.parquet.
Provides functions for listing symbols and loading data.
指标计算请使用 batch_precompute.compute_all_fast() 获得全量 509 列。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger("data_loader")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

TIMEFRAME_DIRS = {
    "M1": DATA_DIR / "M1",
    "M5": DATA_DIR / "M5",
    "M30": DATA_DIR / "M30",
    "H1": DATA_DIR / "H1",
    "H4": DATA_DIR / "H4",
    "D1": DATA_DIR / "D1",
    "W1": DATA_DIR / "W1",
    "MN1": DATA_DIR / "MN1",
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
