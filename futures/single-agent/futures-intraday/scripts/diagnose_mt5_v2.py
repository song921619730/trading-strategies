#!/usr/bin/env python3
"""诊断 MT5 品种名 — 确定正确的 symbol 命名"""
import json, os, sys
import MetaTrader5 as mt5

path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
login = int(os.getenv("MT5_LOGIN", "0"))

mt5.initialize(path=path, login=login)

# Test: with vs without 'm' suffix
tests = [
    ("EURUSD", "EURUSDm"),
    ("GBPUSD", "GBPUSDm"),
    ("USDJPY", "USDJPYm"),
    ("AUDUSD", "USDCHFm"),
    ("XAUUSD", "XAUUSDm"),
    ("US30", "US30m"),
    ("US500", "US500m"),
    ("USTEC", "USTECm"),
    ("JP225", "JP225m"),
    ("HK50", "HK50m"),
    ("USOIL", "USOILm"),
    ("UKOIL", "UKOILm"),
]

print(f"{'symbol':15s} {'without m':15s} {'with m':15s}")
print("-" * 45)

for without_m, with_m in tests:
    r1 = mt5.copy_rates_from_pos(without_m, mt5.TIMEFRAME_H1, 0, 3)
    r2 = mt5.copy_rates_from_pos(with_m, mt5.TIMEFRAME_H1, 0, 3)
    n1 = len(r1) if r1 is not None else 0
    n2 = len(r2) if r2 is not None else 0
    ok1 = "✅" if n1 > 0 else "❌"
    ok2 = "✅" if n2 > 0 else "❌"
    print(f"{without_m:15s} {ok1:15s} {ok2:15s}")

# Also check how to access struct fields
print("\n=== Struct field access test ===")
rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 3)
if rates is not None and len(rates) > 0:
    r = rates[0]
    print(f"type: {type(r)}")
    print(f"dtype: {r.dtype}")
    print(f"fields: {r.dtype.names}")
    # Try accessing by name
    print(f"r['time'] = {r['time']}")
    print(f"r['open'] = {r['open']}")
    print(f"r['close'] = {r['close']}")
    # Try accessing by attribute
    print(f"r.time via tolist: {r.tolist()}")

# Check $ symbol prefix
print("\n=== Dollar prefix check ===")
for sym in ["$EURUSD", "$USDJPY", "$US30", "$US500"]:
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 3)
    n = len(r) if r is not None else 0
    print(f"  {sym:15s} → {'✅' if n>0 else '❌'} ({n} bars)")

mt5.shutdown()
