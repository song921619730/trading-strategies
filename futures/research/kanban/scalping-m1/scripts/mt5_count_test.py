#!/usr/bin/env python3
"""Test if count parameter matters."""
import MetaTrader5 as mt5
from datetime import datetime, timezone
import sys

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=path):
    print(f"FAIL: {mt5.last_error()}")
    sys.exit(1)

print(f"Account: {mt5.account_info().login}")

for count in [10, 100, 1000, 10000, 50000, 100000, 150000]:
    bars = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M1, 0, count)
    if bars is not None:
        print(f"  count={count}: got {len(bars)} bars")
        if len(bars) > 0:
            t0 = datetime.fromtimestamp(bars[0]['time'], tz=timezone.utc)
            t1 = datetime.fromtimestamp(bars[-1]['time'], tz=timezone.utc)
            print(f"    Range: {t0} -> {t1}")
    else:
        err = mt5.last_error()
        print(f"  count={count}: FAILED ({err})")

mt5.shutdown()
