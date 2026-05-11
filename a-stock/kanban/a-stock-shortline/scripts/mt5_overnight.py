import MetaTrader5 as mt5
import datetime

try:
    mt5.initialize()
    
    # Check for JP225 type symbols
    all_s = mt5.symbols_get()
    jp = [s.name for s in all_s if ('JP225' in s.name or 'NIKKEI' in s.name.upper() or 'NI225' in s.name.upper())]
    if jp:
        print(f"JP symbols found: {jp[:10]}")
    else:
        print("JP225: NO SYMBOL FOUND (checking all symbols)")
        # List first 30 symbols for debugging
        for s in all_s[:30]:
            print(f"  SYM: {s.name}")
    
    # Try symbols with m suffix
    symbols = ["US30m", "US500m", "USTECm", "HK50m"]
    
    for s in symbols:
        tick = mt5.symbol_info_tick(s)
        if tick:
            dt = datetime.datetime.fromtimestamp(tick.time)
            print(f"{s}: bid={tick.bid}, ask={tick.ask}, time={dt.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"{s}: NO TICK")
    
    # Daily bars - last 5 days
    print("\n=== DAILY BARS (last 5) ===")
    for s in symbols:
        rates = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_D1, 0, 5)
        if rates is not None and len(rates) > 0:
            for r in rates:
                dt = datetime.datetime.fromtimestamp(r[0])
                print(f"{s}_D1: date={dt.strftime('%Y%m%d')}, open={r[1]:.2f}, high={r[2]:.2f}, low={r[3]:.2f}, close={r[4]:.2f}, vol={r[5]}")
        else:
            print(f"{s}_D1: NO DATA")
    
    # Also try without m suffix
    for s in ["US30", "US500", "USTEC", "HK50"]:
        tick = mt5.symbol_info_tick(s)
        if tick:
            dt = datetime.datetime.fromtimestamp(tick.time)
            print(f"{s}: bid={tick.bid}, ask={tick.ask}, time={dt.strftime('%Y-%m-%d %H:%M:%S')}")

finally:
    mt5.shutdown()
