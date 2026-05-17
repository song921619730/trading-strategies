#!/usr/bin/env python3
"""Batch fetch M1 from MT5 - uses count=90000 (safe limit)."""
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
MAX_BARS = 90000  # Safe limit < maxbars=100000

os.makedirs(TARGET_DIR, exist_ok=True)
path = "C:/Program Files/MetaTrader 5/terminal64.exe"

if not mt5.initialize(path=path):
    print(f"INIT_FAIL|{mt5.last_error()}")
    sys.exit(1)

print(f"ACCOUNT|{mt5.account_info().login}|{mt5.account_info().server}")
print(f"MAX_BARS|{MAX_BARS}")
print()

success = 0
for sym in SYMBOLS:
    parquet_path = os.path.join(TARGET_DIR, f"{sym}.parquet")
    
    # Load existing
    existing = None
    existing_len = 0
    if os.path.exists(parquet_path):
        try:
            existing = pd.read_parquet(parquet_path)
            if isinstance(existing.index, pd.DatetimeIndex):
                if existing.index.tz is None:
                    existing.index = existing.index.tz_localize('UTC')
                existing_len = len(existing)
        except:
            existing = None
    
    # Fetch M1
    bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, MAX_BARS)
    if bars is None or len(bars) == 0:
        # Fallback
        fd = datetime.now(timezone.utc) - timedelta(days=60)
        bars = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, fd, MAX_BARS)
    
    if bars is None or len(bars) == 0:
        print(f"NO_DATA|{sym}")
        time.sleep(0.5)
        continue
    
    # Convert
    df = pd.DataFrame(bars)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df = df.set_index('time')
    cols = [c for c in ['open','high','low','close','tick_volume','spread','real_volume'] if c in df.columns]
    df = df[cols]
    df = df.sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    
    # Check freshness
    last_new = df.index[-1]
    new_count = len(df)
    
    # Merge
    if existing is not None and existing_len > 0:
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep='last')]
        combined = combined.sort_index()
        if len(combined) > 300000:
            combined = combined.iloc[-300000:]
        added = len(combined) - existing_len
    else:
        combined = df
        added = new_count
    
    combined.to_parquet(parquet_path)
    print(f"OK|{sym}|fetched_{new_count}|existing_{existing_len}|+{added}|total_{len(combined)}|last_{last_new}")
    success += 1
    time.sleep(0.3)

mt5.shutdown()
print(f"\nDONE|{success}/{len(SYMBOLS)}")
