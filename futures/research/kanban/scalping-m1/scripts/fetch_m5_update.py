#!/usr/bin/env python3
"""Fetch fresh M5 data from MT5 for all scalping symbols"""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
import sys, time, os

SYMBOLS = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]
TARGET_DIR = r"F:\AIcoding_space\Hermes\strategies\futures\research\kanban\scalping-m1\data\M5"
os.makedirs(TARGET_DIR, exist_ok=True)

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=path):
    print(f"Init failed: {mt5.last_error()}")
    sys.exit(1)

print(f"Account: {mt5.account_info().login}")
print(f"Server: {mt5.account_info().server}")

# Warm-up
print("\n--- Warm-up ---")
for sym in SYMBOLS:
    info = mt5.symbol_info(sym)
    if info and not info.select:
        mt5.symbol_select(sym, True)
    print(f"  {sym}: select={info.select if info else 'N/A'}")

time.sleep(1)

# Fetch M5
print("\n--- Fetching M5 ---")
success = 0
for sym in SYMBOLS:
    parquet_path = os.path.join(TARGET_DIR, f"{sym}.parquet")
    
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
    
    print(f"  [{sym}] copy_rates_from_pos (M5, pos=0)...", end=" ", flush=True)
    try:
        bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 200000)
        if bars is None or len(bars) == 0:
            print(f"0 bars, trying from_date=30days...", end=" ")
            fd = datetime.now(timezone.utc) - timedelta(days=30)
            bars = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, fd, 200000)
        
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
        
        if existing is not None and len(existing) > 0:
            combined = pd.concat([existing, df])
            combined = combined[~combined.index.duplicated(keep='last')]
            combined = combined.sort_index()
            new_rows = len(combined) - len(existing)
        else:
            combined = df
            new_rows = len(df)
        
        if len(combined) > 200000:
            combined = combined.iloc[-200000:]
        
        combined.to_parquet(parquet_path)
        print(f"+{new_rows} new, total {len(combined)} [{combined.index[0]} -> {combined.index[-1]}]")
        success += 1
    except Exception as e:
        print(f"ERROR: {e}")
    
    time.sleep(0.3)

mt5.shutdown()
print(f"\nDone. Updated {success}/{len(SYMBOLS)} symbols.")
