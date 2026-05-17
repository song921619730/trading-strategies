#!/usr/bin/env python3
"""Debug: Verify XAGUSD M30 results"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')
from data_loader import load_data, compute_indicators
import pandas as pd
import numpy as np

m30 = load_data('M30', symbols=['XAGUSD'])
xag = compute_indicators(m30['XAGUSD'])

bull = (xag['close'] > xag['open']).astype(int)
xag['consecutive_bull'] = bull.groupby((bull == 0).cumsum()).cumsum()

cond = (xag['consecutive_bull'] >= 4) & (xag['rsi14'] > 80)
entries = xag[cond]
print(f'Total signals: {len(entries)}')
print(f'Date range: {entries.index[0]} to {entries.index[-1]}')
print(f'Sample:')
for idx, row in entries.head(5).iterrows():
    print(f'  {idx}: CB={row["consecutive_bull"]:.0f} RSI={row["rsi14"]:.1f} Close={row["close"]:.2f}')

for hold in [30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]:
    hits, total, count = 0, 0.0, 0
    for idx, row in entries.iterrows():
        pos = xag.index.get_loc(idx)
        if pos + hold < len(xag):
            pnl = (xag.iloc[pos + hold]['close'] - row['close']) / row['close'] * 100
            total += pnl
            count += 1
            if pnl > 0: hits += 1
    wr = hits/count*100 if count else 0
    avg = total/count if count else 0
    print(f'hold={hold:3d} n={count:3d} WR={wr:.1f}% avg={avg:.3f}%')
