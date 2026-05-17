#!/usr/bin/env python3
"""Fetch RECENT M5+M1 data from MT5 (last 3 days) and merge with existing"""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
import sys, time, os

SYMBOLS = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]
BASE_DIR = "F:\\AIcoding_space\\Hermes\\strategies\\futures\\research\\kanban\\scalping-m1"

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=path):
    print(f"Init failed: {mt5.last_error()}")
    sys.exit(1)

print(f"Account: {mt5.account_info().login}")
now_utc = datetime.now(timezone.utc)
print(f"Current time: {now_utc}")

for sym in SYMBOLS:
    mt5.symbol_select(sym, True)

time.sleep(1)

total_new_m5 = 0
total_new_m1 = 0

for timeframe_name, mt5_tf, target_subdir, days_back in [
    ("M5", mt5.TIMEFRAME_M5, "M5", 3),
    ("M1", mt5.TIMEFRAME_M1, "M1", 3),
]:
    TARGET_DIR = f"{BASE_DIR}\\data\\{target_subdir}"
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    print(f"\n--- Fetching {timeframe_name} (last {days_back} days) ---")
    
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
            except:
                existing = None
        
        # Get recent bars
        from_dt = now_utc - timedelta(days=days_back)
        bars = mt5.copy_rates_from(sym, mt5_tf, from_dt, 10000)
        
        if bars is None or len(bars) == 0:
            print(f"  [{sym}] No data from MT5")
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
            old_end = existing.index[-1]
            new_bars_from_mt5 = df[df.index > old_end]
            new_count = len(new_bars_from_mt5)
            
            if new_count > 0:
                combined = pd.concat([existing, new_bars_from_mt5])
                combined = combined[~combined.index.duplicated(keep='last')]
                combined = combined.sort_index()
                if len(combined) > 250000:
                    combined = combined.iloc[-250000:]
                combined.to_parquet(parquet_path)
                print(f"  [{sym}] +{new_count} new bars! [{existing.index[-1]} -> {new_bars_from_mt5.index[-1]}] total={len(combined)}")
            else:
                print(f"  [{sym}] No new bars (existing ends at {old_end}, MT5 gives up to {df.index[-1]})")
        else:
            df.to_parquet(parquet_path)
            print(f"  [{sym}] New file: {len(df)} rows [{df.index[0]} -> {df.index[-1]}]")
        
        success += 1
        time.sleep(0.2)

mt5.shutdown()
print(f"\n✅ Recent data fetch complete!")
print(f"Time: {datetime.now(timezone.utc)}")
