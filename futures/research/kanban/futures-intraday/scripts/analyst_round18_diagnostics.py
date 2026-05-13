#!/usr/bin/env python3
"""Deep-dive diagnostics: ATR filter impact on XAUUSD signals"""
import sys, logging
import numpy as np
import pandas as pd
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '.')
from data_loader import load_data, compute_indicators

df_raw = load_data(timeframe='M30', symbols=['XAUUSD'])
df = compute_indicators(df_raw['XAUUSD'])

close_arr = df['close'].values
n_rows = len(df)

mask_us_rsi = df.eval("session == 'us' and rsi14 < 40").values.astype(bool)
mask_filtered = df.eval("atr14 / close > 0.002").values.astype(bool)
mask_full = mask_us_rsi & mask_filtered
mask_removed = mask_us_rsi & (~mask_filtered)

signal_indices_all = np.where(mask_us_rsi)[0]
signal_indices_filtered = np.where(mask_full)[0]
signal_indices_removed = np.where(mask_removed)[0]

print(f'Total rows: {len(df)}')
print(f'All signals (US+RSI<40): {len(signal_indices_all)}')
print(f'After ATR>0.2% filter: {len(signal_indices_filtered)}')
print(f'Removed by filter: {len(signal_indices_removed)}')
print(f'Filter retention rate: {len(signal_indices_filtered)/len(signal_indices_all)*100:.2f}%')

# Check performance at hold=15
print(f'\n{"="*70}')
print(f'  PERFORMANCE COMPARISON AT HOLD=15')
print(f'{"="*70}')
print(f'{"Group":<20} {"Count":>8} {"WinRate":>10} {"AvgRet":>12} {"Sharpe":>10}')
print(f'{"-"*60}')

for hp in [10, 15]:
    print(f'\n--- Hold={hp} ---')
    for label, idx_set in [('All (no filter)', signal_indices_all), 
                            ('ATR>0.2% kept', signal_indices_filtered),
                            ('ATR removed (low vol)', signal_indices_removed)]:
        rets = []
        for i in idx_set:
            exit_idx = i + hp
            if exit_idx < n_rows:
                rets.append((close_arr[exit_idx] - close_arr[i]) / close_arr[i])
        if rets:
            rets = np.array(rets)
            n = len(rets)
            wr = np.mean(rets > 0)
            avg = np.mean(rets)
            std = np.std(rets)
            sharpe = avg / std * np.sqrt(12000 / hp) if std > 0 else 0
            print(f'{label:<20} {n:>8} {wr:>9.2%} {avg:>+11.6f} {sharpe:>9.2f}')

# ATR threshold exploration
print(f'\n{"="*70}')
print(f'  ATR THRESHOLD EXPLORATION (Hold=15)')
print(f'{"="*70}')
print(f'{"Threshold":<15} {"Count":>8} {"WinRate":>10} {"AvgRet":>12} {"Sharpe":>10}')
print(f'{"-"*60}')

for threshold in [0.001, 0.0015, 0.002, 0.0025, 0.003, 0.0035, 0.004, 0.005]:
    mask_t = df.eval(f'atr14 / close > {threshold}').values.astype(bool)
    mask_combined = mask_us_rsi & mask_t
    idx = np.where(mask_combined)[0]
    rets = []
    for i in idx:
        exit_idx = i + 15
        if exit_idx < n_rows:
            rets.append((close_arr[exit_idx] - close_arr[i]) / close_arr[i])
    if rets:
        rets = np.array(rets)
        n = len(rets)
        wr = np.mean(rets > 0)
        avg = np.mean(rets)
        std = np.std(rets)
        sharpe = avg / std * np.sqrt(12000 / 15) if std > 0 else 0
        print(f'{threshold:<15.4f} {n:>8} {wr:>9.2%} {avg:>+11.6f} {sharpe:>9.2f}')
    else:
        print(f'{threshold:<15.4f} {"0":>8} {"N/A":>10} {"N/A":>12} {"N/A":>10}')

# What about reversing the filter? Low volatility only?
print(f'\n{"="*70}')
print(f'  REVERSE HYPOTHESIS: Low volatility only (ATR <= 0.2%)')
print(f'{"="*70}')
mask_lowvol = mask_us_rsi & (~mask_filtered)
idx_lowvol = np.where(mask_lowvol)[0]
rets = []
for i in idx_lowvol:
    exit_idx = i + 15
    if exit_idx < n_rows:
        rets.append((close_arr[exit_idx] - close_arr[i]) / close_arr[i])
if rets:
    rets = np.array(rets)
    print(f'Low vol only: n={len(rets)}, wr={np.mean(rets>0):.2%}, avg={np.mean(rets):.6f}')
    # Also check hold=10
    rets10 = []
    for i in idx_lowvol:
        exit_idx = i + 10
        if exit_idx < n_rows:
            rets10.append((close_arr[exit_idx] - close_arr[i]) / close_arr[i])
    if rets10:
        rets10 = np.array(rets10)
        print(f'Low vol only (hold=10): n={len(rets10)}, wr={np.mean(rets10>0):.2%}, avg={np.mean(rets10):.6f}')
