#!/usr/bin/env python3
"""Fetch M1 data from MT5 for all symbols and update parquet files."""
import json, os, sys, time
from datetime import datetime, timezone
import pandas as pd
import MetaTrader5 as mt5

SYMBOLS = {
    "AUDUSD": "AUDUSDm",
    "EURUSD": "EURUSDm",
    "GBPUSD": "GBPUSDm",
    "HK50": "HK50m",
    "JP225": "JP225m",
    "UKOIL": "UKOILm",
    "US30": "US30m",
    "US500": "US500m",
    "USDCHF": "USDCHFm",
    "USDJPY": "USDJPYm",
    "USOIL": "USOILm",
    "USTEC": "USTECm",
    "XAGUSD": "XAGUSDm",
    "XAUUSD": "XAUUSDm",
}

TARGET_DIR = r"F:\AIcoding_space\Hermes\strategies\futures\research\kanban\scalping-m1\data\M1"
os.makedirs(TARGET_DIR, exist_ok=True)

BARS_COUNT = 200000  # enough for ~5 months of M1

def main():
    print(f"MT5 M1 Data Fetcher")
    print(f"Start: {datetime.now(timezone.utc).isoformat()}")
    print(f"=" * 60)

    path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
    login = int(os.getenv("MT5_LOGIN", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")

    if not mt5.initialize(path=path, login=login, password=password, server=server):
        print(f"MT5 init failed: {mt5.last_error()}")
        return

    account = mt5.account_info()
    if account:
        print(f"Account: {account.login} Balance: {account.balance:.2f}")
    else:
        print("No account info (may still work)")

    success = 0
    for sym, mt5_sym in SYMBOLS.items():
        parquet_path = os.path.join(TARGET_DIR, f"{sym}.parquet")
        
        # Load existing data
        existing_df = None
        if os.path.exists(parquet_path):
            try:
                existing_df = pd.read_parquet(parquet_path)
                if not isinstance(existing_df.index, pd.DatetimeIndex):
                    existing_df = None
            except:
                existing_df = None
        
        print(f"\n[{sym}] ({mt5_sym}) Downloading M1...", end=" ", flush=True)
        try:
            bars = mt5.copy_rates_from_pos(mt5_sym, mt5.TIMEFRAME_M1, 0, BARS_COUNT)
            if bars is None or len(bars) < 100:
                print(f"insufficient data ({len(bars) if bars else 0})")
                continue
            
            # Convert to DataFrame
            df = pd.DataFrame(bars)
            df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
            df = df.set_index('time')
            df = df.rename(columns={
                'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
                'tick_volume': 'tick_volume', 'spread': 'spread', 'real_volume': 'real_volume'
            })
            # Keep only needed columns
            cols = [c for c in ['open','high','low','close','tick_volume','spread','real_volume'] if c in df.columns]
            df = df[cols]
            df = df.sort_index()

            # Merge with existing data
            if existing_df is not None and len(existing_df) > 0:
                combined = pd.concat([existing_df, df])
                combined = combined[~combined.index.duplicated(keep='last')]
                combined = combined.sort_index()
            else:
                combined = df

            # Trim to last 200k bars to keep size manageable
            if len(combined) > 200000:
                combined = combined.iloc[-200000:]
            
            combined.to_parquet(parquet_path)
            print(f"OK: {len(bars)} new bars, total {len(combined)} rows")
            print(f"   Range: {combined.index[0]} -> {combined.index[-1]}")
            success += 1
            time.sleep(0.5)  # rate limiting
        
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
