#!/usr/bin/env python3
"""Fetch M1 data from MT5 for all symbols and update parquet files.
Use copy_rates_from with from_date instead of copy_rates_from_pos."""
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

FETCH_DAYS = 180  # fetch ~6 months of M1 data

def main():
    print(f"MT5 M1 Data Fetcher v2")
    print(f"Start: {datetime.now(timezone.utc).isoformat()}")
    print(f"=" * 60)

    path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")

    if not mt5.initialize(path=path):
        print(f"MT5 init failed: {mt5.last_error()}")
        return

    acc = mt5.account_info()
    if acc:
        print(f"Account: {acc.login} Server: {acc.server} Balance: {acc.balance:.2f}")
    else:
        print("No account info")

    from_date = datetime.now(timezone.utc) - timedelta(days=FETCH_DAYS)
    print(f"Fetching M1 data from {from_date}")

    success = 0
    for sym in SYMBOLS:
        parquet_path = os.path.join(TARGET_DIR, f"{sym}.parquet")

        # Load existing data
        existing_df = None
        if os.path.exists(parquet_path):
            try:
                existing_df = pd.read_parquet(parquet_path)
                if isinstance(existing_df.index, pd.DatetimeIndex):
                    print(f"  [{sym}] Existing: {len(existing_df)} rows, {existing_df.index[0]} -> {existing_df.index[-1]}")
                else:
                    existing_df = None
            except Exception as e:
                print(f"  [{sym}] Error reading existing: {e}")

        print(f"  [{sym}] Downloading M1...", end=" ", flush=True)
        try:
            bars = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, from_date, 200000)
            if bars is None or len(bars) < 100:
                print(f"insufficient data ({len(bars) if bars else 0})")
                continue

            # Convert to DataFrame
            df = pd.DataFrame(bars)
            df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
            df = df.set_index('time')
            
            # Rename and select columns
            col_map = {
                'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
                'tick_volume': 'tick_volume', 'spread': 'spread', 'real_volume': 'real_volume'
            }
            df = df.rename(columns=col_map)
            cols = [c for c in ['open','high','low','close','tick_volume','spread','real_volume'] if c in df.columns]
            df = df[cols]
            df = df.sort_index()

            # Merge
            if existing_df is not None and len(existing_df) > 0:
                combined = pd.concat([existing_df, df])
                combined = combined[~combined.index.duplicated(keep='last')]
                combined = combined.sort_index()
            else:
                combined = df

            # Trim
            if len(combined) > 300000:
                combined = combined.iloc[-300000:]

            combined.to_parquet(parquet_path)
            print(f"OK: {len(bars)} new bars")
            print(f"     Total: {len(combined)} rows [{combined.index[0]} -> {combined.index[-1]}]")
            success += 1
            time.sleep(0.3)  # rate limiting

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
