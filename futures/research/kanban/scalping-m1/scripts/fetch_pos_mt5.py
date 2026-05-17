#!/usr/bin/env python3
"""Use copy_rates_from_pos to get latest M5+M1 bars and merge"""
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
print(f"Current time: {datetime.now(timezone.utc)}")
print(f"Max bars: {mt5.terminal_info().maxbars}")

for sym in SYMBOLS:
    mt5.symbol_select(sym, True)
time.sleep(1)

for timeframe_name, mt5_tf, target_subdir in [
    ("M5", mt5.TIMEFRAME_M5, "M5"),
    ("M1", mt5.TIMEFRAME_M1, "M1"),
]:
    TARGET_DIR = f"{BASE_DIR}\\data\\{target_subdir}"
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    print(f"\n--- {timeframe_name} ---")
    
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
        
        # Use copy_rates_from_pos with the max possible amount
        # First determine how many bars to fetch
        max_bars = mt5.terminal_info().maxbars  # typically 100000
        
        # Try pos=0 (latest bars) with a number within maxbars
        bars = mt5.copy_rates_from_pos(sym, mt5_tf, 0, max_bars)
        
        if bars is None or len(bars) == 0:
            print(f"  [{sym}] copy_rates_from_pos failed")
            # Try alternative: copy_rates_range for last 2 days
            from_dt = datetime.now(timezone.utc) - timedelta(days=2)
            bars = mt5.copy_rates_range(sym, mt5_tf, from_dt, datetime.now(timezone.utc))
            if bars is None or len(bars) == 0:
                print(f"  [{sym}] copy_rates_range also failed")
                continue
        
        df = pd.DataFrame(bars)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df = df.set_index('time')
        cols = [c for c in ['open','high','low','close','tick_volume','spread','real_volume'] if c in df.columns]
        df = df[cols]
        df = df.sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        
        print(f"  [{sym}] MT5: {len(df)} rows [{df.index[0]} -> {df.index[-1]}]")
        
        if existing is not None and len(existing) > 0:
            old_end = existing.index[-1]
            new_bars = df[df.index > old_end]
            if len(new_bars) > 0:
                combined = pd.concat([existing, new_bars])
                combined = combined[~combined.index.duplicated(keep='last')]
                combined = combined.sort_index()
                if len(combined) > 250000:
                    combined = combined.iloc[-250000:]
                combined.to_parquet(parquet_path)
                print(f"  ✅ [{sym}] +{len(new_bars)} new rows! Now: {len(combined)} [{combined.index[0]} -> {combined.index[-1]}]")
            else:
                print(f"  ℹ️  [{sym}] No new data (existing latest: {old_end}, MT5 latest: {df.index[-1]})")
        else:
            # New file - keep last 100k
            if len(df) > 100000:
                df = df.iloc[-100000:]
            df.to_parquet(parquet_path)
            print(f"  ✅ [{sym}] New file: {len(df)} rows [{df.index[0]} -> {df.index[-1]}]")
        
        time.sleep(0.2)

mt5.shutdown()
print(f"\n✅ Done at {datetime.now(timezone.utc)}")
