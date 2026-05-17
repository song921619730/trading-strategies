#!/usr/bin/env python3
"""Fetch fresh M5+M1 data from MT5 - uses copy_rates_from which works reliably"""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
import sys, time, os

SYMBOLS = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=path):
    print(f"Init failed: {mt5.last_error()}")
    sys.exit(1)

print(f"Account: {mt5.account_info().login}")

# Warm-up
for sym in SYMBOLS:
    mt5.symbol_select(sym, True)

time.sleep(1)

for timeframe_name, mt5_tf, target_subdir in [
    ("M5", mt5.TIMEFRAME_M5, "M5"),
    ("M1", mt5.TIMEFRAME_M1, "M1"),
]:
    TARGET_DIR = f"F:\\AIcoding_space\\Hermes\\strategies\\futures\\research\\kanban\\scalping-m1\\data\\{target_subdir}"
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"Fetching {timeframe_name}...")
    print(f"{'='*60}")
    
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
        
        # Fetch from MT5 - use copy_rates_from with a generous window
        print(f"  [{sym}] copy_rates_from (last 60 days)...", end=" ", flush=True)
        try:
            # Go back 60 days to get a full range
            from_dt = datetime.now(timezone.utc) - timedelta(days=60)
            bars = mt5.copy_rates_from(sym, mt5_tf, from_dt, 50000)
            
            if bars is None or len(bars) == 0:
                print(f"FAILED (empty)")
                continue
            
            df = pd.DataFrame(bars)
            df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
            df = df.set_index('time')
            cols = [c for c in ['open','high','low','close','tick_volume','spread','real_volume'] if c in df.columns]
            df = df[cols]
            df = df.sort_index()
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC')
            
            print(f"got {len(df)} rows [{df.index[0]} -> {df.index[-1]}]")
            
            # Merge with existing
            if existing is not None and len(existing) > 0:
                combined = pd.concat([existing, df])
                combined = combined[~combined.index.duplicated(keep='last')]
                combined = combined.sort_index()
                new_rows = len(combined) - len(existing)
            else:
                combined = df
                new_rows = len(df)
            
            # Keep last 200k bars max
            if len(combined) > 200000:
                combined = combined.iloc[-200000:]
            
            combined.to_parquet(parquet_path)
            print(f"    → Saved: +{new_rows} new, total {len(combined)} [{combined.index[0]} -> {combined.index[-1]}]")
            success += 1
            
        except Exception as e:
            print(f"ERROR: {e}")
        
        time.sleep(0.2)
    
    print(f"  {timeframe_name}: Updated {success}/{len(SYMBOLS)} symbols")

mt5.shutdown()
print(f"\n✅ Data fetch complete!")
