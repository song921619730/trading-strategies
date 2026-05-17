#!/usr/bin/env python3
"""Diagnose MT5 connectivity and available symbols."""
import MetaTrader5 as mt5
from datetime import datetime, timezone

path = "C:/Program Files/MetaTrader 5/terminal64.exe"

print("=" * 60)
print("MT5 Diagnostics")
print("=" * 60)

# Initialize without login
print("\n1. Initialize without login...")
if not mt5.initialize(path=path):
    print(f"   FAILED: {mt5.last_error()}")
else:
    print("   OK")

# Check account
print("\n2. Account info:")
acc = mt5.account_info()
if acc:
    print(f"   Login: {acc.login}, Server: {acc.server}")
    print(f"   Balance: {acc.balance}, Equity: {acc.equity}")
else:
    print(f"   No account: {mt5.last_error()}")

# List available symbols
print("\n3. Symbols:")
symbols = mt5.symbols_get()
if symbols:
    print(f"   Total symbols: {len(symbols)}")
    # Show forex and indices
    for s in symbols[:10]:
        print(f"   - {s.name}")
    # Check for specific symbols
    for test_sym in ['XAUUSD', 'XAUUSDm', 'EURUSD', 'EURUSDm', 'US30', 'US30m', 'BTCUSD']:
        info = mt5.symbol_info(test_sym)
        if info:
            print(f"   ✅ {test_sym}: selectable={info.select}")
        else:
            print(f"   ❌ {test_sym}: not found")
else:
    print(f"   No symbols: {mt5.last_error()}")

# Try from_date
print("\n4. Try copy_rates_from (last 7 days)...")
from_date = datetime(2026, 5, 7, tzinfo=timezone.utc)
for test_sym in ['XAUUSD', 'XAUUSDm', 'EURUSD', 'EURUSDm']:
    bars = mt5.copy_rates_from(test_sym, mt5.TIMEFRAME_H1, from_date, 100)
    if bars is not None and len(bars) > 0:
        print(f"   ✅ {test_sym} H1: {len(bars)} bars from {datetime.fromtimestamp(bars[0]['time'], tz=timezone.utc)}")
    else:
        bars2 = mt5.copy_rates_from(test_sym, mt5.TIMEFRAME_M1, from_date, 100)
        if bars2 is not None and len(bars2) > 0:
            print(f"   ✅ {test_sym} M1: {len(bars2)} bars from {datetime.fromtimestamp(bars2[0]['time'], tz=timezone.utc)}")
        else:
            print(f"   ❌ {test_sym}: no data")

# Try copy_rates_from_pos
print("\n5. Try copy_rates_from_pos...")
for test_sym in ['XAUUSD', 'XAUUSDm']:
    bars = mt5.copy_rates_from_pos(test_sym, mt5.TIMEFRAME_H1, 0, 10)
    if bars is not None and len(bars) > 0:
        print(f"   ✅ {test_sym} H1 pos=0: {len(bars)} bars")
    else:
        print(f"   ❌ {test_sym}: error={mt5.last_error()}")

mt5.shutdown()
print("\nDone.")
