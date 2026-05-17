#!/usr/bin/env python3
"""Verify the XAGUSD M30 short vs long discrepancy"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')
from data_loader import load_data, compute_indicators
import pandas as pd
import numpy as np

m30 = load_data('M30', symbols=['XAGUSD'])
xag = compute_indicators(m30['XAGUSD'])
bull = (xag['close'] > xag['open']).astype(int)
xag['consecutive_bull'] = bull.groupby((bull == 0).cumsum()).cumsum()

# Strategy: CBull>=4 + RSI>80
cond = (xag['consecutive_bull'] >= 4) & (xag['rsi14'] > 80)
entries = xag[cond]
print(f'Total signals: {len(entries)}')

for hold in [30, 55, 60, 70]:
    hits_long, total_long = 0, 0.0
    count = 0
    for idx, row in entries.iterrows():
        pos = xag.index.get_loc(idx)
        if pos + hold < len(xag):
            pnl_long = (xag.iloc[pos + hold]['close'] - row['close']) / row['close'] * 100
            total_long += pnl_long
            count += 1
            if pnl_long > 0: hits_long += 1
    
    wr_long = hits_long / count * 100 if count else 0
    wr_short = 100 - wr_long
    avg_long = total_long / count if count else 0
    avg_short = -avg_long
    
    print(f'hold={hold}: n={count}')
    print(f'  LONG:  WR={wr_long:.1f}% avg={avg_long:.3f}%')
    print(f'  SHORT: WR={wr_short:.1f}% avg={avg_short:.3f}%')
