#!/usr/bin/env python3
"""Fetch M1 data - process one symbol per invocation for reliability."""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
import sys, time, os

sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"

# Map of possible symbol names on server
sym_variants = [sym, sym + "m", sym.replace("USD", "USDm")]

TARGET_DIR = r"F:\AIcoding_space\Hermes\strategies\futures\research\kanban\scalping-m1\data\M1"
os.makedirs(TARGET_DIR, exist_ok=True)
parquet_path = os.path.join(TARGET_DIR, f"{sym}.parquet")

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=path):
    print(f"INIT_FAIL|{mt5.last_error()}")
    sys.exit(1)

# Find working symbol name
working_sym = None
for variant in sym_variants:
    info = mt5.symbol_info(variant)
    if info and info.select:
        working_sym = variant
        break

if not working_sym:
    # Try without pre-check - just try the original name
    working_sym = sym

# Fetch data
bars = mt5.copy_rates_from_pos(working_sym, mt5.TIMEFRAME_M1, 0, 200000)
if bars is None or len(bars) == 0:
    # Fallback
    fd = datetime.now(timezone.utc) - timedelta(days=7)
    bars = mt5.copy_rates_from(working_sym, mt5.TIMEFRAME_M1, fd, 200000)

if bars is None or len(bars) == 0:
    print(f"NO_DATA|{sym}")
    mt5.shutdown()
    sys.exit(1)

df = pd.DataFrame(bars)
df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
df = df.set_index('time')
cols = [c for c in ['open','high','low','close','tick_volume','spread','real_volume'] if c in df.columns]
df = df[cols]
df = df.sort_index()
if df.index.tz is None:
    df.index = df.index.tz_localize('UTC')

# Merge with existing
if os.path.exists(parquet_path):
    try:
        existing = pd.read_parquet(parquet_path)
        if isinstance(existing.index, pd.DatetimeIndex):
            if existing.index.tz is None:
                existing.index = existing.index.tz_localize('UTC')
            combined = pd.concat([existing, df])
            combined = combined[~combined.index.duplicated(keep='last')]
            combined = combined.sort_index()
            if len(combined) > 250000:
                combined = combined.iloc[-250000:]
            new_rows = len(combined) - len(existing)
        else:
            combined = df
            new_rows = len(df)
    except:
        combined = df
        new_rows = len(df)
else:
    combined = df
    new_rows = len(df)

combined.to_parquet(parquet_path)
print(f"OK|{sym}|{working_sym}|+{new_rows}|total_{len(combined)}|{combined.index[0]}|{combined.index[-1]}")
mt5.shutdown()
