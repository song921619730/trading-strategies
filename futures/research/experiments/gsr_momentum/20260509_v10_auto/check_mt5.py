#!/usr/bin/env python3
"""检查MT5连接状态和数据可用性"""
import sys
sys.path.insert(0, 'C:/Users/gj/AppData/Local/Programs/Python/Python312')

import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5初始化失败")
    sys.exit(1)

symbols = [
    'XAUUSDm', 'XAGUSDm', 'EURUSDm', 'GBPUSDm', 'USDJPYm', 'AUDUSDm', 'USDCHFm',
    'USOILm', 'UKOILm', 'USTECm', 'US30m', 'US500m', 'JP225m', 'HK50m'
]

for sym in symbols:
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 5000)
    if rates is not None and len(rates) > 0:
        import pandas as pd
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        print(f"{sym}: {len(df)} bars, from {df['time'].min().date()} to {df['time'].max().date()}")
    else:
        print(f"{sym}: 无数据")

mt5.shutdown()
