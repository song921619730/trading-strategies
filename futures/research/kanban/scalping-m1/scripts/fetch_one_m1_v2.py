#!/usr/bin/env python3
"""Fetch M1 data - one symbol. Use count <= maxbars (100000)."""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
import sys, time, os

sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
TARGET_DIR = r"F:\AIcoding_space\Hermes\strategies\futures\research\kanban\scalping-m1\data\M1"
os.makedirs(TARGET_DIR, exist_ok=True)
parquet_path = os.path.join(TARGET_DIR, f"{sym}.parquet")
MAX_BARS = 100000  # MT5 maxbars limit

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=path):
    print(f"FAIL|{sym}|init_error:{mt5.last_error()}")
    sys.exit(1)

# Fetch using copy_rates_from_pos with MAX_BARS
bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, MAX_BARS)

if bars is None or len(bars) == 0:
    # Fallback: try copy_rates_from with recent date
    fd = datetime.now(timezone.utc) - timedelta(days=30)
    bars = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, fd, MAX_BARS)

if bars is None or len(bars) == 0:
    print(f"NO_DATA|{sym}")
    mt5.shutdown()
    sys.exit(1)

# Convert to DataFrame
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
            if len(combined) > 300000:
                combined = combined.iloc[-300000:]
            new_rows = len(combined) - len(existing)
        else:
            combined = df
            new_rows = len(df)
    except Exception as e:
        print(f"WARN|merge_error:{e}", flush=True)
        combined = df
        new_rows = len(df)
else:
    combined = df
    new_rows = len(df)

combined.to_parquet(parquet_path)
t0 = combined.index[0].strftime('%Y-%m-%d %H:%M')
t1 = combined.index[-1].strftime('%Y-%m-%d %H:%M')
print(f"OK|{sym}|+{new_rows}|total_{len(combined)}|{t0}|{t1}")
mt5.shutdown()
