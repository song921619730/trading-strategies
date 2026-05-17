#!/usr/bin/env python3
"""Fetch M1 from MT5 - use copy_rates_from_pos with proper fallback."""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
import sys, time, os

SYMBOLS = [
    "AUDUSD", "EURUSD", "GBPUSD", "HK50", "JP225",
    "UKOIL", "US30", "US500", "USDCHF", "USDJPY",
    "USOIL", "USTEC", "XAGUSD", "XAUUSD",
]
TARGET_DIR = r"F:\AIcoding_space\Hermes\strategies\futures\research\kanban\scalping-m1\data\M1"
os.makedirs(TARGET_DIR, exist_ok=True)

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=path):
    print(f"Init failed: {mt5.last_error()}")
    sys.exit(1)

print(f"Account: {mt5.account_info().login}")
print(f"Server: {mt5.account_info().server}")

# First do a "warm-up" fetch for each symbol using copy_rates_from with recent date
# This seems to be needed for the terminal to start serving data
print("\n--- Warm-up: checking symbols ---")
for sym in SYMBOLS:
    info = mt5.symbol_info(sym)
    if info and not info.select:
        mt5.symbol_select(sym, True)
    print(f"  {sym}: select={info.select if info else 'N/A'}")

time.sleep(1)

# Now fetch data using copy_rates_from_pos
print("\n--- Fetching M1 data ---")
success = 0
for sym in SYMBOLS:
    parquet_path = os.path.join(TARGET_DIR, f"{sym}.parquet")
    
    # Load existing
    existing = None
    if os.path.exists(parquet_path):
        try:
            existing = pd.read_parquet(parquet_path)
            if isinstance(existing.index, pd.DatetimeIndex):
                if existing.index.tz is None:
                    existing.index = existing.index.tz_localize('UTC')
                print(f"  [{sym}] Existing: {len(existing)} rows [{existing.index[0]} -> {existing.index[-1]}]")
        except:
            existing = None
    
    print(f"  [{sym}] copy_rates_from_pos (M1, pos=0)...", end=" ", flush=True)
    try:
        bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 200000)
        if bars is None or len(bars) == 0:
            print(f"0 bars, trying from_date=14days...", end=" ")
            fd = datetime.now(timezone.utc) - timedelta(days=14)
            bars = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, fd, 200000)
        
        if bars is None or len(bars) == 0:
            print(f"FAILED")
            continue
        
        df = pd.DataFrame(bars)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df = df.set_index('time')
        cols = [c for c in ['open','high','low','close','tick_volume','spread','real_volume'] if c in df.columns]
        df = df[cols]
        df = df.sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        
        # Merge
        if existing is not None and len(existing) > 0:
            combined = pd.concat([existing, df])
            combined = combined[~combined.index.duplicated(keep='last')]
            combined = combined.sort_index()
            new_rows = len(combined) - len(existing)
        else:
            combined = df
            new_rows = len(df)
        
        if len(combined) > 250000:
            combined = combined.iloc[-250000:]
        
        combined.to_parquet(parquet_path)
        print(f"+{new_rows} new, total {len(combined)} [{combined.index[0]} -> {combined.index[-1]}]")
        success += 1
    
    except Exception as e:
        print(f"ERROR: {e}")
    
    time.sleep(0.3)

mt5.shutdown()
print(f"\nDone. Updated {success}/{len(SYMBOLS)} symbols.")
