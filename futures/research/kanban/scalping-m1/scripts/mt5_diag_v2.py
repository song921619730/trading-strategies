#!/usr/bin/env python3
"""Try to fetch M5 data from MT5 with different approaches"""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import sys, time

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=path):
    print(f"Init failed: {mt5.last_error()}")
    sys.exit(1)

print(f"Account: {mt5.account_info().login}")

sym = "XAUUSD"
print(f"\n{sym} current: bid={mt5.symbol_info_tick(sym).bid} ask={mt5.symbol_info_tick(sym).ask}")

# Option 1: copy_rates_from_pos with different positions
print("\n--- copy_rates_from_pos (0 to 3 bars) ---")
for bars in [1, 3, 5, 10]:
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, bars)
    if r is not None and len(r) > 0:
        print(f"  {bars}: got {len(r)} bars, last={r[-1][0]} close={r[-1][4]}")
    else:
        print(f"  {bars}: None/empty")

# Option 2: copy_rates_from with specific timestamps
print("\n--- copy_rates_from (last 7 days) ---")
for days_back in [1, 3, 7]:
    from_dt = datetime.now(timezone.utc) - timedelta(days=days_back)
    r = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, from_dt, 5000)
    if r is not None and len(r) > 0:
        times = [x[0] for x in r]
        print(f"  {days_back}d: {len(r)} bars, [{min(times)} -> {max(times)}]")
    else:
        print(f"  {days_back}d: None/empty")

# Option 3: Try M1 first (sometimes that "warms up" the terminal)
print("\n--- Warm-up with M1 ---")
r1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 5)
if r1 is not None and len(r1) > 0:
    print(f"  M1: got {len(r1)} bars, last={r1[-1][0]} close={r1[-1][4]}")
    time.sleep(1)
    # Now try M5 again
    r2 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 5)
    if r2 is not None and len(r2) > 0:
        print(f"  After warmup M5: got {len(r2)} bars, last={r2[-1][0]} close={r2[-1][4]}")
    else:
        print(f"  After warmup M5: still None/empty")
else:
    print(f"  M1: None/empty")

# Option 4: Try copy_rates_range
print("\n--- copy_rates_range ---")
start_dt = datetime.now(timezone.utc) - timedelta(hours=48)
end_dt = datetime.now(timezone.utc)
print(f"  range: {start_dt} -> {end_dt}")
r3 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, start_dt, end_dt)
if r3 is not None and len(r3) > 0:
    times = [x[0] for x in r3]
    print(f"  got {len(r3)} bars: [{min(times)} -> {max(times)}]")
else:
    print(f"  None/empty (err={mt5.last_error()})")

mt5.shutdown()
