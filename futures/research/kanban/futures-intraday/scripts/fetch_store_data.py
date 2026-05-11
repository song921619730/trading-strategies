#!/usr/bin/env python3
"""
fetch_store_data.py

Fetches 5 years (2021-01-01 to present) of H1 and M30 historical data
from MetaTrader5 for 14 symbols and stores them as parquet files.

Usage (Windows Python - MT5 must be running):
    /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \\
        F:/AIcoding_space/Hermes/.../fetch_store_data.py
"""

import os
import sys
import json
import logging
import datetime
from pathlib import Path

import pandas as pd

# MetaTrader5 import (only works on Windows Python)
try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 module not found. This script must be run with Windows Python.")
    print("Usage:")
    print("  /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe fetch_store_data.py")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYMBOLS = [
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCHF", "USOIL", "UKOIL", "USTEC",
    "US30", "US500", "JP225", "HK50",
]

TIMEFRAMES = {
    "H1": None,  # will map after import
    "M30": None,
}

# Data directory: two levels up from scripts/, then data/
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent  # futures-intraday/
DATA_DIR = BASE_DIR / "data"

H1_DIR = DATA_DIR / "H1"
M30_DIR = DATA_DIR / "M30"
METADATA_PATH = DATA_DIR / "metadata.json"

START_DATE = datetime.datetime(2021, 1, 1, tzinfo=datetime.timezone.utc)
END_DATE = datetime.datetime.now(datetime.timezone.utc)

COLUMNS_KEEP = ["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fetch_store_data")


# ---------------------------------------------------------------------------
# MT5 wrappers — import after confirming we are on Windows Python
# ---------------------------------------------------------------------------

def _import_mt5():
    """Import MetaTrader5 module. Must be running under Windows Python."""
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        log.error(
            "MetaTrader5 library not found. Make sure you are running this "
            "script with Windows Python where MetaTrader5 is installed."
        )
        sys.exit(1)


def connect_mt5(mt5):
    """Establish connection to the MT5 terminal."""
    if not mt5.initialize():
        err = mt5.last_error()
        log.error(f"MT5 initialize() failed: {err}")
        sys.exit(1)

    # Check terminal is connected
    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        log.error("MT5 terminal_info() returned None — is the terminal running?")
        mt5.shutdown()
        sys.exit(1)

    log.info(
        "Connected to MT5 — terminal: %s, build: %d, connected: %s",
        terminal_info.name,
        terminal_info.build,
        terminal_info.connected,
    )
    return terminal_info


def timeframe_map(mt5):
    """Return a dict mapping friendly names to MT5 timeframe constants."""
    return {
        "H1": mt5.TIMEFRAME_H1,
        "M30": mt5.TIMEFRAME_M30,
    }


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_rates(mt5, symbol, tf_enum, start, end):
    """
    Fetch OHLCV data from MT5 for *symbol* on timeframe *tf_enum*.
    Returns a pandas DataFrame with columns:
        time, open, high, low, close, tick_volume, spread, real_volume
    or None on failure.
    """
    rates = mt5.copy_rates_range(symbol, tf_enum, start, end)
    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        log.warning("No data for %s: %s", symbol, err)
        return None

    df = pd.DataFrame(rates)

    # Convert time from seconds to datetime
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

    # Keep only needed columns
    missing = [c for c in COLUMNS_KEEP if c not in df.columns]
    if missing:
        log.warning("Symbol %s missing columns: %s", symbol, missing)

    existing = [c for c in COLUMNS_KEEP if c in df.columns]
    df = df[["time"] + existing].copy()
    df.set_index("time", inplace=True)

    return df


def save_dataframe(df, path, symbol, timeframe):
    """Save DataFrame as parquet, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=True)
        log.info("Saved %s %s -> %s (%d rows)", symbol, timeframe, path, len(df))
        return True
    except Exception as e:
        log.error("Failed to save %s %s: %s", symbol, timeframe, e)
        return False


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def build_metadata(results):
    """Build metadata dict from fetch results."""
    meta = {}
    meta["_generated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    meta["_start_requested"] = START_DATE.isoformat()
    meta["_end_requested"] = END_DATE.isoformat()
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 60)
    log.info("MT5 Historical Data Fetcher")
    log.info("Range: %s  ->  %s", START_DATE.date(), END_DATE.date())
    log.info("Symbols: %d", len(SYMBOLS))
    log.info("=" * 60)

    # --- 1. Connect to MT5 ---
    mt5 = _import_mt5()
    connect_mt5(mt5)
    tfs = timeframe_map(mt5)

    # --- 2. Ensure output directories exist ---
    H1_DIR.mkdir(parents=True, exist_ok=True)
    M30_DIR.mkdir(parents=True, exist_ok=True)

    # --- 3. Fetch data for each symbol ---
    results = {}  # symbol -> {tf: {"df": DataFrame, "path": Path}}

    for idx, symbol in enumerate(SYMBOLS, start=1):
        log.info("[%d/%d] Processing %s ...", idx, len(SYMBOLS), symbol)
        results[symbol] = {}

        # Check symbol availability
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            log.warning("Symbol %s not found in MT5, skipping", symbol)
            for tf_key in ["H1", "M30"]:
                results[symbol][tf_key] = {"df": None, "path": None}
            continue

        # Optionally select symbol in MarketWatch (doesn't hurt)
        if not symbol_info.visible:
            mt5.symbol_select(symbol, True)

        for tf_key in ["H1", "M30"]:
            tf_enum = tfs[tf_key]
            out_dir = H1_DIR if tf_key == "H1" else M30_DIR
            out_path = out_dir / f"{symbol}.parquet"

            log.info("  Fetching %s %s ...", symbol, tf_key)
            df = fetch_rates(mt5, symbol, tf_enum, START_DATE, END_DATE)
            results[symbol][tf_key] = {"df": df, "path": out_path}

            if df is not None and not df.empty:
                save_dataframe(df, out_path, symbol, tf_key)
            else:
                log.warning("  No data for %s %s — skipping file", symbol, tf_key)

    # --- 4. Disconnect ---
    mt5.shutdown()
    log.info("Disconnected from MT5.")

    # --- 5. Write metadata ---
    log.info("Writing metadata ...")
    metadata = build_metadata(results)
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    log.info("Metadata saved -> %s", METADATA_PATH)

    # --- 6. Summary ---
    print()
    print("=" * 72)
    print("  FETCH SUMMARY")
    print("=" * 72)
    print(f"  {'Symbol':<12} {'Timeframe':<10} {'Rows':>10} {'First':<22} {'Last':<22}")
    print("  " + "-" * 76)
    total_h1 = 0
    total_m30 = 0
    ok_h1 = 0
    ok_m30 = 0
    for sym in SYMBOLS:
        for tf_key in ["H1", "M30"]:
            info = results.get(sym, {}).get(tf_key, {})
            df = info.get("df")
            if df is not None and not df.empty:
                first = str(df.index[0].strftime("%Y-%m-%d %H:%M"))
                last = str(df.index[-1].strftime("%Y-%m-%d %H:%M"))
                rows = len(df)
                print(f"  {sym:<12} {tf_key:<10} {rows:>10} {first:<22} {last:<22}")
                if tf_key == "H1":
                    total_h1 += rows
                    ok_h1 += 1
                else:
                    total_m30 += rows
                    ok_m30 += 1
            else:
                print(f"  {sym:<12} {tf_key:<10} {'—':>10} {'—':<22} {'—':<22}")
    print("  " + "-" * 76)
    print(f"  {'TOTAL':<12} {'H1':<10} {total_h1:>10}  {'OK symbols:':<10} {ok_h1:<2}/{len(SYMBOLS)}")
    print(f"  {'TOTAL':<12} {'M30':<10} {total_m30:>10}  {'OK symbols:':<10} {ok_m30:<2}/{len(SYMBOLS)}")
    print("=" * 72)

    log.info("All done! Data stored in: %s", DATA_DIR)


if __name__ == "__main__":
    main()
