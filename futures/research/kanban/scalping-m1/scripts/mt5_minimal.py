#!/usr/bin/env python3
"""Minimal M1 fetch - one symbol at a time, with proper initialization."""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
import os, sys, time

sym = "XAUUSD"
target = r"F:\AIcoding_space\Hermes\strategies\futures\research\kanban\scalping-m1\data\M1"
os.makedirs(target, exist_ok=True)
parquet_path = os.path.join(target, f"{sym}.parquet")

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
print(f"Initializing MT5...")
if not mt5.initialize(path=path):
    print(f"Init failed: {mt5.last_error()}")
    sys.exit(1)

print(f"Terminal info: {mt5.terminal_info()}")
print(f"Account info: {mt5.account_info()}")

# Try to get symbol info
info = mt5.symbol_info(sym)
print(f"Symbol info for {sym}:")
if info:
    print(f"  select={info.select}, visible={info.visible}, session_deals={info.session_deals}")
    # Try to select if not selected
    if not info.select:
        print(f"  Selecting symbol...")
        mt5.symbol_select(sym, True)
        time.sleep(1)
        info2 = mt5.symbol_info(sym)
        print(f"  After select: select={info2.select}")

# Now try copy_rates_from_pos
print(f"\nTrying copy_rates_from_pos({sym}, M1, 0, 1000)...")
bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 1000)
if bars is not None:
    print(f"  Got {len(bars)} bars")
    if len(bars) > 0:
        t0 = datetime.fromtimestamp(bars[0]['time'], tz=timezone.utc)
        t1 = datetime.fromtimestamp(bars[-1]['time'], tz=timezone.utc)
        print(f"  Range: {t0} -> {t1}")
        
        # Convert to parquet
        df = pd.DataFrame(bars)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df = df.set_index('time')
        df = df[['open','high','low','close','tick_volume','spread','real_volume']]
        df = df.sort_index()
        
        # Load existing
        if os.path.exists(parquet_path):
            existing = pd.read_parquet(parquet_path)
            if isinstance(existing.index, pd.DatetimeIndex):
                print(f"  Existing: {len(existing)} rows [{existing.index[0]} -> {existing.index[-1]}]")
                combined = pd.concat([existing, df])
                combined = combined[~combined.index.duplicated(keep='last')]
                combined = combined.sort_index()
                if len(combined) > 250000:
                    combined = combined.iloc[-250000:]
            else:
                combined = df
        else:
            combined = df
        
        combined.to_parquet(parquet_path)
        print(f"  Saved: {len(combined)} rows [{combined.index[0]} -> {combined.index[-1]}]")
else:
    err = mt5.last_error()
    print(f"  Failed: {err}")

mt5.shutdown()
print("\nDone.")
