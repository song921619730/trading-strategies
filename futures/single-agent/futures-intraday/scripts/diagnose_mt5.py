#!/usr/bin/env python3
"""诊断 MT5 数据连接 — 查看可用品种和能否获取数据"""
import json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE))

import MetaTrader5 as mt5

path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
login = int(os.getenv("MT5_LOGIN", "0"))
password = os.getenv("MT5_PASSWORD", "")
server = os.getenv("MT5_SERVER", "")

print(f"MT5 path: {path}")
print(f"Login: {login}")

if not mt5.initialize(path=path, login=login, password=password, server=server):
    print(f"❌ MT5 init failed: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

print(f"✅ MT5 initialized")
term = mt5.terminal_info()
acct = mt5.account_info()
if term:
    print(f"   Terminal: {term.name} trade_allowed={term.trade_allowed}")
if acct:
    print(f"   Account: {acct.login} balance={acct.balance} equity={acct.equity} trade_expert={acct.trade_expert}")

# Check what symbols are available - look for forex and indices
print("\n=== 检查常用品种 ===")
test_symbols = [
    "EURUSD", "EURUSDm", "EURUSD.m", 
    "GBPUSD", "GBPUSDm",
    "USDJPY", "USDJPYm",
    "AUDUSD", "AUDUSDm",
    "US30", "US30m", "US30Cash",
    "US500", "US500m", "SP500",
    "USTEC", "USTECm", "NAS100",
    "JP225", "JP225m", "JPN225",
    "XAUUSD", "XAUUSDm", "GOLD",
    "XAGUSD", "XAGUSDm", "SILVER",
    "USOIL", "USOILm", "WTI",
    "UKOIL", "UKOILm", "BRENT",
    "HK50", "HK50m", "HK50Cash",
    "DXY", "USDX",
]

for sym in test_symbols:
    info = mt5.symbol_info(sym)
    if info:
        # Try to get data
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 5)
        count = len(rates) if rates is not None else 0
        print(f"  ✅ {sym:15s} selectable={info.select} visible={info.visible} rates={count}")
        if rates and count > 0:
            r = rates[0]
            print(f"     Fields: {type(r)} - keys available: {dir(r)[-15:]}")
            print(f"     Sample: time={r.time} open={r.open} close={r.close}")
    else:
        err = mt5.last_error()
        print(f"  ❌ {sym:15s} not found (err={err})")

print("\n=== Market Watch symbols ===")
try:
    symbols = mt5.symbols_get()
    if symbols:
        # Show first 30
        forex = [s.name for s in symbols if "EUR" in s.name or "GBP" in s.name or "JPY" in s.name or "USD" in s.name]
        indices = [s.name for s in symbols if any(x in s.name for x in ["US30","US500","USTEC","JP225","HK50","NAS","SPX"])]
        metals = [s.name for s in symbols if any(x in s.name for x in ["XAU","XAG","GOLD","SILVER"])]
        oils = [s.name for s in symbols if "OIL" in s.name]
        
        print(f"  Forex symbols found: {forex[:10]}")
        print(f"  Index symbols found: {indices[:10]}")
        print(f"  Metal symbols found: {metals[:10]}")
        print(f"  Oil symbols found: {oils[:10]}")
        print(f"  Total symbols: {len(symbols)}")
    else:
        print("  No symbols found in market watch")
except Exception as e:
    print(f"  Error listing symbols: {e}")

mt5.shutdown()
