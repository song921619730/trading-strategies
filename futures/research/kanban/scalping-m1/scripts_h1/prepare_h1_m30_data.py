#!/usr/bin/env python3
"""Resample M1 data to H1 and M30, save as parquet.

Usage:
    cd /path/to/scalping-m1
    python3 scripts_h1/prepare_h1_m30_data.py
"""
import os, sys, logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("prepare")

BASE = Path(__file__).resolve().parent.parent
M1_DIR = BASE / "data" / "M1"
H1_DIR = BASE / "data" / "H1"
M30_DIR = BASE / "data" / "M30"

H1_DIR.mkdir(parents=True, exist_ok=True)
M30_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = [
    "AUDUSD", "EURUSD", "GBPUSD", "HK50", "JP225",
    "UKOIL", "US30", "US500", "USDCHF", "USDJPY",
    "USOIL", "USTEC", "XAGUSD", "XAUUSD",
]

def resample_m1_to_target(m1_df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample M1 OHLCV to higher timeframe (H1='1h', M30='30min')."""
    ohlc = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "tick_volume": "sum",
        "spread": "mean",
        "real_volume": "sum",
    }
    resampled = m1_df.resample(rule, closed="left", label="left").agg(ohlc)
    resampled = resampled.dropna(subset=["open", "high", "low", "close"])
    return resampled

def process():
    for sym in SYMBOLS:
        m1_fp = M1_DIR / f"{sym}.parquet"
        if not m1_fp.exists():
            log.warning("M1 data missing for %s, skipping", sym)
            continue

        m1_df = pd.read_parquet(m1_fp)
        if not isinstance(m1_df.index, pd.DatetimeIndex):
            if "time" in m1_df.columns:
                m1_df["time"] = pd.to_datetime(m1_df["time"])
                m1_df = m1_df.set_index("time")
            else:
                log.warning("No datetime index for %s", sym)
                continue

        m1_df = m1_df.sort_index()

        # H1 (1 hour)
        h1_df = resample_m1_to_target(m1_df, "1h")
        h1_fp = H1_DIR / f"{sym}.parquet"
        h1_df.to_parquet(h1_fp)
        log.info("%s H1: %d rows [%s → %s]", sym, len(h1_df),
                 h1_df.index[0].strftime("%Y-%m-%d %H:%M"),
                 h1_df.index[-1].strftime("%Y-%m-%d %H:%M"))

        # M30 (30 minutes)
        m30_df = resample_m1_to_target(m1_df, "30min")
        m30_fp = M30_DIR / f"{sym}.parquet"
        m30_df.to_parquet(m30_fp)
        log.info("%s M30: %d rows [%s → %s]", sym, len(m30_df),
                 m30_df.index[0].strftime("%Y-%m-%d %H:%M"),
                 m30_df.index[-1].strftime("%Y-%m-%d %H:%M"))

    print("\n✅ All H1/M30 data prepared.")

if __name__ == "__main__":
    process()
