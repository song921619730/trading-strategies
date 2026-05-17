#!/usr/bin/env python3
"""Check M30 data consistency"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')
from data_loader import load_data, compute_indicators
import pandas as pd
import numpy as np

# Check raw M30 data
m30 = load_data('M30', symbols=['XAGUSD'])
xag = m30['XAGUSD']
print(f'XAGUSD M30 raw: rows={len(xag)}, dates={xag.index[0]} to {xag.index[-1]}')

# Compute indicators
xag2 = compute_indicators(xag)
print(f'After compute_indicators: rows={len(xag2)}, has rsi14={"rsi14" in xag2.columns}')

# Compute consecutive_bull ourselves 
bull = (xag2['close'] > xag2['open']).astype(int)
cb = bull.groupby((bull == 0).cumsum()).cumsum()
cond = (cb >= 4) & (xag2['rsi14'] > 80)
print(f'Signals (our calc): {cond.sum()}')

# Now check what the add_session in round32 would produce  
def add_session(df):
    df = df.copy()
    bull2 = (df['close'] > df['open']).astype(int)
    df['consecutive_bull'] = bull2.groupby((bull2 == 0).cumsum()).cumsum()
    return df

xag3 = add_session(xag2)
cond2 = (xag3['consecutive_bull'] >= 4) & (xag3['rsi14'] > 80)
print(f'Signals (add_session): {cond2.sum()}')

# Check all signal dates
entries = xag3[cond2]
print(f'Signal dates:')
for dt in entries.index:
    print(f'  {dt}')
print(f'Total: {len(entries)}')
