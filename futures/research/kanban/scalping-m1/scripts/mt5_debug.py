#!/usr/bin/env python3
"""Debug: step by step MT5 M1 fetch."""
import MetaTrader5 as mt5
from datetime import datetime, timezone
import sys

path = "C:/Program Files/MetaTrader 5/terminal64.exe"

print(f"1. mt5.__version__ = {mt5.__version__}")
print(f"2. Calling mt5.initialize(path='{path}')...")
result = mt5.initialize(path=path)
print(f"   Result: {result}")

if not result:
    print(f"   Error: {mt5.last_error()}")
    sys.exit(1)

print(f"3. Terminal info:")
ti = mt5.terminal_info()
print(f"   connected={ti.connected}, trade_allowed={ti.trade_allowed}")

print(f"4. Account info:")
ai = mt5.account_info()
print(f"   login={ai.login}, server={ai.server}")

print(f"5. Symbol info for XAUUSD:")
info = mt5.symbol_info("XAUUSD")
print(f"   select={info.select}, visible={info.visible}")
print(f"   time={info.time}, digits={info.digits}")
print(f"   spread={info.spread}, spread_float={info.spread_float}")

print(f"6. copy_rates_from_pos(M1, pos=0, count=10)...")
bars = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M1, 0, 10)
if bars is not None:
    print(f"   Got {len(bars)} bars")
    if len(bars) > 0:
        t0 = datetime.fromtimestamp(bars[0]['time'], tz=timezone.utc)
        t1 = datetime.fromtimestamp(bars[-1]['time'], tz=timezone.utc)
        print(f"   First: {t0}, Last: {t1}")
else:
    err = mt5.last_error()
    print(f"   Error: {err}")

print(f"7. copy_rates_from(date=7days ago, count=10)...")
fd = datetime(2026, 5, 7, tzinfo=timezone.utc)
bars2 = mt5.copy_rates_from("XAUUSD", mt5.TIMEFRAME_M1, fd, 10)
if bars2 is not None:
    print(f"   Got {len(bars2)} bars")
    if len(bars2) > 0:
        t0 = datetime.fromtimestamp(bars2[0]['time'], tz=timezone.utc)
        t1 = datetime.fromtimestamp(bars2[-1]['time'], tz=timezone.utc)
        print(f"   First: {t0}, Last: {t1}")
else:
    err = mt5.last_error()
    print(f"   Error: {err}")

mt5.shutdown()
print("8. Done.")
