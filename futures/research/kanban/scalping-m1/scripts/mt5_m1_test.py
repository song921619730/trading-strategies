#!/usr/bin/env python3
"""Test M1 data fetch with various parameters."""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
mt5.initialize(path=path)

print("M1 Data Fetch Tests")
print("=" * 60)

# Test 1: copy_rates_from with recent date
test_sym = "XAUUSD"
print(f"\n1. {test_sym} M1 copy_rates_from:")
for days_back in [1, 2, 3, 7, 14, 30]:
    fd = datetime.now(timezone.utc) - timedelta(days=days_back)
    bars = mt5.copy_rates_from(test_sym, mt5.TIMEFRAME_M1, fd, 10000)
    count = len(bars) if bars is not None else 0
    if count > 0:
        t0 = datetime.fromtimestamp(bars[0]['time'], tz=timezone.utc)
        t1 = datetime.fromtimestamp(bars[-1]['time'], tz=timezone.utc)
        print(f"   {days_back:3d} days ago ({fd.date()}): {count:5d} bars [{t0} -> {t1}]")
    else:
        print(f"   {days_back:3d} days ago ({fd.date()}): 0 bars")

# Test 2: copy_rates_from_pos
print(f"\n2. {test_sym} M1 copy_rates_from_pos:")
for pos in [0, 1, 100, 1000]:
    bars = mt5.copy_rates_from_pos(test_sym, mt5.TIMEFRAME_M1, pos, 100)
    count = len(bars) if bars is not None else 0
    print(f"   pos={pos}: {count} bars")

# Test 3: Other symbols M1
print(f"\n3. Other symbols M1 (from 3 days ago):")
fd = datetime.now(timezone.utc) - timedelta(days=3)
for sym in ["EURUSD", "GBPUSD", "US30", "US500", "XAGUSD", "JP225"]:
    bars = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, fd, 10000)
    count = len(bars) if bars is not None else 0
    if count > 0:
        t0 = datetime.fromtimestamp(bars[0]['time'], tz=timezone.utc)
        t1 = datetime.fromtimestamp(bars[-1]['time'], tz=timezone.utc)
        print(f"   {sym}: {count} bars [{t0} -> {t1}]")
    else:
        print(f"   {sym}: 0 bars")

mt5.shutdown()
print("\nDone.")
