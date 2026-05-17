#!/usr/bin/env python3
"""
fetch_m1m5_data_v2.py — Fetch M1/M5 data from MT5 using pagination (copy_rates_from_pos).

MT5's copy_rates_range fails for M1/M5 over large date ranges, so we use
copy_rates_from_pos stepping backwards in 1000-bar chunks.

Usage (Windows Python):
    /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \\
        F:/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/scripts/fetch_m1m5_data_v2.py
"""
import os, sys, json, logging, time
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 module not found. Must run with Windows Python.")
    sys.exit(1)

SCALP_SYMBOLS = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]
TIMEFRAMES = ["M1", "M5"]

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
DATA_DIR = BASE_DIR / "data"
METADATA_PATH = DATA_DIR / "metadata_m1m5.json"

CHUNK_SIZE = 5000  # bars per fetch call

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fetch_m1m5_v2")

COLUMNS_KEEP = ["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]

def timeframe_map(mt5):
    return {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
    }

def fetch_all_bars(mt5, symbol, tf_enum, start_date):
    """
    Fetch all bars for symbol/timeframe from start_date to present,
    using copy_rates_from_pos stepping backwards.
    """
    all_bars = []
    offset = 0
    max_bars = 1000000  # safety cap

    while offset < max_bars:
        rates = mt5.copy_rates_from_pos(symbol, tf_enum, offset, CHUNK_SIZE)
        if rates is None or len(rates) == 0:
            break
        
        df_chunk = pd.DataFrame(rates)
        if df_chunk.empty:
            break

        df_chunk["time"] = pd.to_datetime(df_chunk["time"], unit="s", utc=True)
        
        # Filter to only keep bars >= start_date
        before = len(df_chunk)
        df_chunk = df_chunk[df_chunk["time"] >= pd.Timestamp(start_date)]
        after = len(df_chunk)
        
        if after > 0:
            all_bars.append(df_chunk)
        
        # Check if we've gone past start_date
        if after < before or (len(rates) < CHUNK_SIZE):
            # We've either hit the start or reached the beginning of data
            break
        
        # Move offset forward (copy_rates_from_pos goes backwards in time as offset increases)
        offset += len(rates)
        
        # Be polite
        time.sleep(0.1)

    if not all_bars:
        return None

    df = pd.concat(all_bars, ignore_index=True)
    df.drop_duplicates(subset=["time"], inplace=True)
    df.sort_values("time", inplace=True)
    
    # Keep only needed columns
    existing = [c for c in COLUMNS_KEEP if c in df.columns]
    df = df[["time"] + existing].copy()
    df.set_index("time", inplace=True)
    
    return df

def save_dataframe(df, path, symbol, timeframe):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=True)
        log.info("Saved %s %s -> %s (%d rows, %s -> %s)",
                 symbol, timeframe, path, len(df),
                 df.index[0].strftime("%Y-%m-%d %H:%M"),
                 df.index[-1].strftime("%Y-%m-%d %H:%M"))
        return True
    except Exception as e:
        log.error("Failed to save %s %s: %s", symbol, timeframe, e)
        return False

def build_metadata(results):
    meta = {}
    meta["_generated"] = datetime.now(timezone.utc).isoformat()
    meta["symbols"] = {}
    for symbol, tf_data in results.items():
        meta["symbols"][symbol] = {}
        for tf_key, info in tf_data.items():
            if info["df"] is not None and not info["df"].empty:
                meta["symbols"][symbol][tf_key] = {
                    "file": str(info["path"]),
                    "rows": len(info["df"]),
                    "first_time": str(info["df"].index[0]),
                    "last_time": str(info["df"].index[-1]),
                    "columns": list(info["df"].columns),
                }
            else:
                meta["symbols"][symbol][tf_key] = None
    return meta

def main():
    log.info("=" * 60)
    log.info("MT5 M1/M5 Data Fetcher v2 — Pagination Mode")
    log.info("Symbols: %s", SCALP_SYMBOLS)
    log.info("=" * 60)

    if not mt5.initialize():
        log.error("MT5 initialize() failed: %s", mt5.last_error())
        sys.exit(1)

    term = mt5.terminal_info()
    log.info("Connected: %s | Build %d | Connected: %s", term.name, term.build, term.connected)
    tfs = timeframe_map(mt5)

    # Ensure directories exist
    for tf in TIMEFRAMES:
        (DATA_DIR / tf).mkdir(parents=True, exist_ok=True)

    results = {}
    for idx, symbol in enumerate(SCALP_SYMBOLS, start=1):
        log.info("[%d/%d] %s ...", idx, len(SCALP_SYMBOLS), symbol)
        results[symbol] = {}

        sym_info = mt5.symbol_info(symbol)
        if sym_info is None:
            log.warning("Symbol %s not found, skipping", symbol)
            for tf_key in TIMEFRAMES:
                results[symbol][tf_key] = {"df": None, "path": None}
            continue
        if not sym_info.visible:
            mt5.symbol_select(symbol, True)

        for tf_key in TIMEFRAMES:
            log.info("  Fetching %s %s ...", symbol, tf_key)
            out_path = DATA_DIR / tf_key / f"{symbol}.parquet"
            df = fetch_all_bars(mt5, symbol, tfs[tf_key], datetime(2021, 1, 1, tzinfo=timezone.utc))
            results[symbol][tf_key] = {"df": df, "path": out_path}
            if df is not None and not df.empty:
                save_dataframe(df, out_path, symbol, tf_key)
            else:
                log.warning("  No data for %s %s", symbol, tf_key)

    mt5.shutdown()
    log.info("Disconnected from MT5.")

    # Metadata
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    metadata = build_metadata(results)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    log.info("Metadata saved -> %s", METADATA_PATH)

    # Summary
    print()
    print("=" * 72)
    print("  FETCH SUMMARY — M1/M5")
    print("=" * 72)
    print(f"  {'Symbol':<12} {'TF':<6} {'Rows':>12} {'First':<22} {'Last':<22}")
    print("  " + "-" * 74)
    for sym in SCALP_SYMBOLS:
        for tf_key in TIMEFRAMES:
            info = results.get(sym, {}).get(tf_key, {})
            df = info.get("df")
            if df is not None and not df.empty:
                first = df.index[0].strftime("%Y-%m-%d %H:%M")
                last = df.index[-1].strftime("%Y-%m-%d %H:%M")
                rows = len(df)
                print(f"  {sym:<12} {tf_key:<6} {rows:>12} {first:<22} {last:<22}")
            else:
                print(f"  {sym:<12} {tf_key:<6} {'—':>12} {'—':<22} {'—':<22}")
    print("=" * 72)

if __name__ == "__main__":
    main()
