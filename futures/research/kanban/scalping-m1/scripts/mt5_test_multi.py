#!/usr/bin/env python3
"""Fetch M1 from MT5 - one symbol at time approach, testing each."""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import pandas as pd
import sys, time

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=path):
    print(f"Init failed: {mt5.last_error()}")
    sys.exit(1)

print(f"Account: {mt5.account_info().login}")

# Test each symbol one by one
for sym in ["XAUUSD", "EURUSD", "GBPUSD"]:
    print(f"\n--- {sym} ---")
    info = mt5.symbol_info(sym)
    print(f"  info: select={info.select if info else 'None'}")
    
    if info and not info.select:
        mt5.symbol_select(sym, True)
        time.sleep(0.5)
    
    # Try different approaches
    print(f"  Approach 1: copy_rates_from with from_date=7 days ago...")
    fd = datetime.now(timezone.utc) - timedelta(days=7)
    bars = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, fd, 5000)
    if bars is not None and len(bars) > 0:
        t0 = datetime.fromtimestamp(bars[0]['time'], tz=timezone.utc)
        t1 = datetime.fromtimestamp(bars[-1]['time'], tz=timezone.utc)
        print(f"    ✅ {len(bars)} bars [{t0} -> {t1}]")
    else:
        print(f"    ❌ 0 bars")
        
        print(f"  Approach 2: copy_rates_from_pos...")
        bars2 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 5000)
        if bars2 is not None and len(bars2) > 0:
            t0 = datetime.fromtimestamp(bars2[0]['time'], tz=timezone.utc)
            t1 = datetime.fromtimestamp(bars2[-1]['time'], tz=timezone.utc)
            print(f"    ✅ {len(bars2)} bars [{t0} -> {t1}]")
        else:
            print(f"    ❌ 0 bars")
    
    time.sleep(0.5)

mt5.shutdown()
print("\nDone.")
