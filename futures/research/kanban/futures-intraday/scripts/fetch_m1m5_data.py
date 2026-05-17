#!/usr/bin/env python3
"""
fetch_m1m5_data.py — Fetch M1 and M5 historical data from MT5 for scalping symbols.

Usage (Windows Python):
    /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \\
        /mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/scripts/fetch_m1m5_data.py
"""
import os, sys, json, logging
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 module not found. Must run with Windows Python.")
    sys.exit(1)

# Symbols for scalping research
SCALP_SYMBOLS = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]

TIMEFRAMES = {
    "M1": None,
    "M5": None,
}

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
M1_DIR = DATA_DIR / "M1"
M5_DIR = DATA_DIR / "M5"
METADATA_PATH = DATA_DIR / "metadata_m1m5.json"

START_DATE = datetime(2021, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime.now(timezone.utc)

COLUMNS_KEEP = ["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fetch_m1m5")

def timeframe_map(mt5):
    return {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
    }

def fetch_rates(mt5, symbol, tf_enum, start, end):
    rates = mt5.copy_rates_range(symbol, tf_enum, start, end)
    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        log.warning("No data for %s: %s", symbol, err)
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    existing = [c for c in COLUMNS_KEEP if c in df.columns]
    df = df[["time"] + existing].copy()
    df.set_index("time", inplace=True)
    return df

def save_dataframe(df, path, symbol, timeframe):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=True)
        log.info("Saved %s %s -> %s (%d rows)", symbol, timeframe, path, len(df))
        return True
    except Exception as e:
        log.error("Failed to save %s %s: %s", symbol, timeframe, e)
        return False

def build_metadata(results):
    meta = {}
    meta["_generated"] = datetime.now(timezone.utc).isoformat()
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

def main():
    log.info("=" * 60)
    log.info("MT5 M1/M5 Data Fetcher for Scalping Research")
    log.info("Range: %s -> %s", START_DATE.date(), END_DATE.date())
    log.info("Symbols: %d", len(SCALP_SYMBOLS))
    log.info("=" * 60)

    if not mt5.initialize():
        log.error("MT5 initialize() failed: %s", mt5.last_error())
        sys.exit(1)

    term = mt5.terminal_info()
    log.info("Connected: %s | %s | Build %d", term.name, term.connected, term.build)
    tfs = timeframe_map(mt5)

    M1_DIR.mkdir(parents=True, exist_ok=True)
    M5_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    for idx, symbol in enumerate(SCALP_SYMBOLS, start=1):
        log.info("[%d/%d] Processing %s ...", idx, len(SCALP_SYMBOLS), symbol)
        results[symbol] = {}

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            log.warning("Symbol %s not found in MT5, skipping", symbol)
            for tf_key in ["M1", "M5"]:
                results[symbol][tf_key] = {"df": None, "path": None}
            continue

        if not symbol_info.visible:
            mt5.symbol_select(symbol, True)

        for tf_key in ["M1", "M5"]:
            tf_enum = tfs[tf_key]
            out_dir = M1_DIR if tf_key == "M1" else M5_DIR
            out_path = out_dir / f"{symbol}.parquet"

            log.info("  Fetching %s %s ...", symbol, tf_key)
            df = fetch_rates(mt5, symbol, tf_enum, START_DATE, END_DATE)
            results[symbol][tf_key] = {"df": df, "path": out_path}

            if df is not None and not df.empty:
                save_dataframe(df, out_path, symbol, tf_key)
            else:
                log.warning("  No data for %s %s", symbol, tf_key)

    mt5.shutdown()
    log.info("Disconnected from MT5.")

    # Write metadata
    metadata = build_metadata(results)
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    log.info("Metadata saved -> %s", METADATA_PATH)

    # Summary
    print()
    print("=" * 72)
    print("  FETCH SUMMARY — M1/M5")
    print("=" * 72)
    print(f"  {'Symbol':<12} {'Timeframe':<10} {'Rows':>12} {'First':<22} {'Last':<22}")
    print("  " + "-" * 78)
    for sym in SCALP_SYMBOLS:
        for tf_key in ["M1", "M5"]:
            info = results.get(sym, {}).get(tf_key, {})
            df = info.get("df")
            if df is not None and not df.empty:
                first = str(df.index[0].strftime("%Y-%m-%d %H:%M"))
                last = str(df.index[-1].strftime("%Y-%m-%d %H:%M"))
                rows = len(df)
                print(f"  {sym:<12} {tf_key:<10} {rows:>12} {first:<22} {last:<22}")
            else:
                print(f"  {sym:<12} {tf_key:<10} {'—':>12} {'—':<22} {'—':<22}")
    print("=" * 72)
    log.info("All done!")

if __name__ == "__main__":
    main()
