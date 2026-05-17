#!/usr/bin/env python3
"""Diagnose MT5 connectivity and try to fetch data"""
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import sys

path = "C:/Program Files/MetaTrader 5/terminal64.exe"
if not mt5.initialize(path=path):
    print(f"Init failed: {mt5.last_error()}")
    sys.exit(1)

print(f"Account: {mt5.account_info().login}")
print(f"Server: {mt5.account_info().server}")
print(f"Trade mode: {mt5.account_info().trade_mode}")
print(f"Balance: {mt5.account_info().balance}")
print(f"Terminal info: {mt5.terminal_info()}")

# Check version
print(f"\nMT5 Version: {mt5.__version__}")

# Try symbol info
sym = "XAUUSD"
info = mt5.symbol_info(sym)
if info:
    print(f"\n{sym} info:")
    print(f"  trade_mode: {info.trade_mode}")
    print(f"  time: {info.time}")
    print(f"  bid: {info.bid}")
    print(f"  ask: {info.ask}")
    print(f"  spread: {info.spread}")
    print(f"  session_begins: {info.session_begins}")
    print(f"  session_ends: {info.session_ends}")
else:
    print(f"\n{sym} info: None")

# Try getting last tick
tick = mt5.symbol_info_tick(sym)
if tick:
    print(f"\n{sym} last tick: time={tick.time} bid={tick.bid} ask={tick.ask}")

# Try copy_rates_from_pos with specific bars
print(f"\nTrying copy_rates_from_pos with 5 bars...")
rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 5)
if rates is not None:
    print(f"  Got {len(rates)} bars")
    for r in rates:
        print(f"  time={r[0]} open={r[1]} high={r[2]} low={r[3]} close={r[4]}")
else:
    err = mt5.last_error()
    print(f"  Failed: {err}")

# Try copy_rates_from with specific date
print(f"\nTrying copy_rates_from with last 3 days...")
from_dt = datetime.now(timezone.utc) - timedelta(days=3)
print(f"  from: {from_dt}")
rates2 = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, from_dt, 100)
if rates2 is not None:
    print(f"  Got {len(rates2)} bars")
    if len(rates2) > 0:
        print(f"  Last bar: time={rates2[-1][0]} close={rates2[-1][4]}")
else:
    err = mt5.last_error()
    print(f"  Failed: {err}")

# Check what timeframes are available
print(f"\nChecking M1...")
rates_m1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 5)
if rates_m1 is not None:
    print(f"  Got {len(rates_m1)} M1 bars")
else:
    err = mt5.last_error()
    print(f"  Failed: {err}")

mt5.shutdown()
