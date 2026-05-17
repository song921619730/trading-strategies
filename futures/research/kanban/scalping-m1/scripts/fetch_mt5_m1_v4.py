#!/usr/bin/env python3
"""Fetch M1 data from MT5 for all symbols - with proper init and timezone handling."""
import os, sys, time
from datetime import datetime, timezone, timedelta
import pandas as pd
import MetaTrader5 as mt5

SYMBOLS = [
    "AUDUSD", "EURUSD", "GBPUSD", "HK50", "JP225",
    "UKOIL", "US30", "US500", "USDCHF", "USDJPY",
    "USOIL", "USTEC", "XAGUSD", "XAUUSD",
]

TARGET_DIR = r"F:\AIcoding_space\Hermes\strategies\futures\research\kanban\scalping-m1\data\M1"
os.makedirs(TARGET_DIR, exist_ok=True)

def load_existing(path):
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
        if not isinstance(df.index, pd.DatetimeIndex):
            return None
        # Make timezone-aware if naive
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        return df
    except Exception as e:
        print(f"    Error loading existing: {e}")
        return None

def main():
    print(f"MT5 M1 Data Fetcher v4")
    print(f"Start: {datetime.now(timezone.utc).isoformat()}")
    print(f"=" * 60)

    path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
    if not mt5.initialize(path=path):
        print(f"MT5 init failed: {mt5.last_error()}")
        return

    acc = mt5.account_info()
    if acc:
        print(f"Account: {acc.login} Server: {acc.server}")
    else:
        print("No account info")

    success = 0
    for sym in SYMBOLS:
        parquet_path = os.path.join(TARGET_DIR, f"{sym}.parquet")
        
        # Load existing
        existing_df = load_existing(parquet_path)
        if existing_df is not None:
            print(f"  [{sym}] Existing: {len(existing_df)} rows, {existing_df.index[0]} -> {existing_df.index[-1]}")
        else:
            print(f"  [{sym}] No existing data")

        print(f"  [{sym}] Fetching M1...", end=" ", flush=True)
        try:
            # Ensure symbol is selected
            info = mt5.symbol_info(sym)
            if info and not info.select:
                mt5.symbol_select(sym, True)
                time.sleep(0.2)

            # Use copy_rates_from for maximum coverage
            from_date = datetime.now(timezone.utc) - timedelta(days=45)
            bars = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, from_date, 150000)
            
            if bars is None or len(bars) < 100:
                # Fallback to copy_rates_from_pos
                print(f"from_date failed, trying pos=0...", end=" ")
                bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 150000)
            
            if bars is None or len(bars) < 100:
                print(f"FAILED ({len(bars) if bars else 0})")
                continue

            # Convert to DataFrame
            df = pd.DataFrame(bars)
            df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
            df = df.set_index('time')
            
            col_map = {
                'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
                'tick_volume': 'tick_volume', 'spread': 'spread', 'real_volume': 'real_volume'
            }
            df = df.rename(columns=col_map)
            cols = [c for c in ['open','high','low','close','tick_volume','spread','real_volume'] if c in df.columns]
            df = df[cols]
            df = df.sort_index()
            
            # Ensure timezone-aware
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC')

            # Merge with existing
            if existing_df is not None and len(existing_df) > 0:
                combined = pd.concat([existing_df, df])
                combined = combined[~combined.index.duplicated(keep='last')]
                combined = combined.sort_index()
                new_count = len(combined) - len(existing_df)
                print(f"OK: +{new_count} new bars, total {len(combined)}")
            else:
                combined = df
                print(f"OK: {len(bars)} bars, new file")

            # Trim
            if len(combined) > 250000:
                combined = combined.iloc[-250000:]

            print(f"     Range: {combined.index[0]} -> {combined.index[-1]}")
            combined.to_parquet(parquet_path)
            success += 1
            time.sleep(0.3)

        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

    mt5.shutdown()
    print(f"\n{'='*60}")
    print(f"Done. Updated {success}/{len(SYMBOLS)} symbols.")
    print(f"Target: {TARGET_DIR}")

if __name__ == "__main__":
    main()
