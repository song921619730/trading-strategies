#!/usr/bin/env python3
"""Check all symbols available in the latest pre_analyze data"""
import json, os

TRIUMVIRATE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_path = os.path.join(TRIUMVIRATE_DIR, "data", "pre_analyze_latest.json")

with open(data_path, 'r') as f:
    d = json.load(f)

symbols = d.get('symbols', {})
positions = d.get('open_positions', [])
print("=" * 60)
print("CURRENT ACCOUNT POSITIONS (ALL MAGICS)")
print("=" * 60)
for p in positions:
    print(f"  {p['symbol']} {p['type']} {p['volume']} @ {p['open_price']} PnL: {p['profit']}")
    print(f"    SL: {p['sl']}, TP: {p['tp']}, Current: {p['current_price']}")

print()
print("=" * 60)
print("SYMBOL AVAILABILITY (14 symbols)")
print("=" * 60)
for sym in sorted(symbols.keys()):
    data = symbols[sym]
    held = data.get('already_held', False)
    ind = data.get('indicators', {})
    atr = ind.get('atr_14', 'N/A')
    price = data.get('trade_params', {}).get('current_price', 'N/A')
    corr_buy = data.get('correlation', {}).get('BUY', {})
    corr_sell = data.get('correlation', {}).get('SELL', {})
    can_buy = corr_buy.get('can_open', False)
    can_sell = corr_sell.get('can_open', False)
    print(f"  {sym}:")
    print(f"    held={held}, price={price}, atr={atr}")
    print(f"    correlation: can_buy={can_buy}, can_sell={can_sell}")

# Determine which magics hold what
print()
print("=" * 60)
print("TRIUMVIRATE (234004) OPEN POSITIONS (from trade logs)")
print("=" * 60)
# From pnl_report we know: USOIL BUY, USDJPY BUY
triumvirate_symbols = ["USOIL", "USDJPY"]
for p in positions:
    if p['symbol'] in triumvirate_symbols:
        print(f"  {p['symbol']}: {p['type']} vol={p['volume']}, open={p['open_price']}, sl={p['sl']}, tp={p['tp']}, pnl={p['profit']}")
    else:
        print(f"  {p['symbol']}: (non-Triumvirate magic) {p['type']} vol={p['volume']}, pnl={p['profit']}")
