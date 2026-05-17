#!/usr/bin/env python3
"""Debug fetch_one_m1.py issues."""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import sys

sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
path = "C:/Program Files/MetaTrader 5/terminal64.exe"

print(f"1. Initialize...", flush=True)
if not mt5.initialize(path=path):
    print(f"   FAIL: {mt5.last_error()}")
    sys.exit(1)
print(f"   OK", flush=True)

print(f"2. Account: {mt5.account_info().login}", flush=True)

print(f"3. symbol_info({sym})...", flush=True)
info = mt5.symbol_info(sym)
if info:
    print(f"   select={info.select}, visible={info.visible}", flush=True)
    print(f"   spread={info.spread}", flush=True)
else:
    print(f"   NOT FOUND", flush=True)

print(f"4. copy_rates_from_pos({sym}, M1, 0, 200000)...", flush=True)
bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 200000)
if bars is not None:
    print(f"   Got {len(bars)} bars", flush=True)
    if len(bars) > 0:
        t0 = datetime.fromtimestamp(bars[0]['time'], tz=timezone.utc)
        t1 = datetime.fromtimestamp(bars[-1]['time'], tz=timezone.utc)
        print(f"   Range: {t0} -> {t1}", flush=True)
else:
    err = mt5.last_error()
    print(f"   FAILED: {err}", flush=True)

print(f"5. copy_rates_from({sym}, M1, from_date=7d ago, 200000)...", flush=True)
fd = datetime.now(timezone.utc) - timedelta(days=7)
bars2 = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, fd, 200000)
if bars2 is not None:
    print(f"   Got {len(bars2)} bars", flush=True)
    if len(bars2) > 0:
        t0 = datetime.fromtimestamp(bars2[0]['time'], tz=timezone.utc)
        t1 = datetime.fromtimestamp(bars2[-1]['time'], tz=timezone.utc)
        print(f"   Range: {t0} -> {t1}", flush=True)
else:
    err = mt5.last_error()
    print(f"   FAILED: {err}", flush=True)

mt5.shutdown()
print("6. Done.", flush=True)
