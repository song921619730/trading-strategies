#!/usr/bin/env python3
"""Round 18 - H2 extra tests: XAU+JP filter comparison"""
import sys
sys.path.insert(0, '.')
from data_loader import load_data, compute_indicators
import pandas as pd
import numpy as np

xau_m5_raw = load_data("M5", symbols=["XAUUSD"])
xau_m5 = compute_indicators(xau_m5_raw["XAUUSD"])

jp_m5_raw = load_data("M5", symbols=["JP225"])
jp_m5 = compute_indicators(jp_m5_raw["JP225"])

for df in [xau_m5, jp_m5]:
    df['session'] = 'asia'
    df.loc[(df.index.hour >= 8) & (df.index.hour < 13), 'session'] = 'europe'
    df.loc[(df.index.hour >= 13) & (df.index.hour < 22), 'session'] = 'us'
    df['consecutive_bear'] = df['close'].rolling(20).apply(lambda x: np.sum(np.diff(x) < 0) if len(x) > 1 else 0, raw=True)

common_idx = xau_m5.index.intersection(jp_m5.index)
xau_aligned = xau_m5.loc[common_idx]
jp_aligned = jp_m5.loc[common_idx]

print("XAU standalone entries (US 15-16 RSI<20 CB>=2 - bf_046):")
xau_cond = ((xau_m5['session'] == 'us') & (xau_m5.index.hour >= 15) & (xau_m5.index.hour < 16) & (xau_m5['rsi14'] < 20) & (xau_m5['consecutive_bear'] >= 2))
xau_entries = xau_m5[xau_cond].copy()
print(f"  {len(xau_entries)} signals")

# XAU + JP filter
xau_with_jp_filter = []
for idx, row in xau_entries.iterrows():
    if idx not in jp_aligned.index:
        continue
    pos = jp_aligned.index.get_loc(idx)
    jp_check = False
    for offset in range(0, 4):
        check_pos = pos - offset
        if check_pos < 0:
            break
        check_idx = jp_aligned.index[check_pos]
        jp_row = jp_aligned.loc[check_idx]
        jp_cond = ((jp_row['session'] == 'us') & (check_idx.hour >= 15) & (check_idx.hour < 18) & (jp_row['rsi14'] < 20) & (jp_row['consecutive_bear'] >= 2))
        if jp_cond:
            jp_check = True
            break
    if jp_check:
        xau_with_jp_filter.append(row)

print(f"\nXAU + JP filter (JP CB>=2 within 3 bars): {len(xau_with_jp_filter)}")
if len(xau_with_jp_filter) >= 10:
    for hold in [80, 90, 100, 110, 115, 120]:
        hits = 0
        total_pnl = 0
        count = 0
        for row_dict in xau_with_jp_filter:
            idx = row_dict.name
            entry_price = row_dict['close']
            pos = xau_m5.index.get_loc(idx)
            if pos + hold < len(xau_m5):
                exit_price = xau_m5.iloc[pos + hold]['close']
            else:
                continue
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            count += 1
            if pnl > 0:
                hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:3d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")

# Also test: XAU JP same-bar resonance across whole US session (15-18)
print("\n--- XAU+JP same-bar (US 15-18 both conditions) ---")
xau_cond_loose = ((xau_m5['session'] == 'us') & (xau_m5.index.hour >= 15) & (xau_m5.index.hour < 18) & (xau_m5['rsi14'] < 20) & (xau_m5['consecutive_bear'] >= 2))
jp_cond_bear = ((jp_m5['session'] == 'us') & (jp_m5.index.hour >= 15) & (jp_m5.index.hour < 18) & (jp_m5['rsi14'] < 16) & (jp_m5['consecutive_bear'] >= 2))

xau_loose_entries = xau_m5[xau_cond_loose].copy()
jp_entries = jp_m5[jp_cond_bear].copy()
common_same = xau_loose_entries.index.intersection(jp_entries.index)
print(f"XAU loose (US 15-18 RSI<20 CB>=2): {len(xau_loose_entries)}")
print(f"JP (US 15-18 RSI<16 CB>=2): {len(jp_entries)}")
print(f"Same bar resonance: {len(common_same)}")

if len(common_same) >= 5:
    for hold in [40, 60, 80, 100, 110, 120]:
        hits = 0
        total_pnl = 0
        count = 0
        for idx in common_same:
            entry_price = xau_m5.loc[idx, 'close']
            pos = xau_m5.index.get_loc(idx)
            if pos + hold < len(xau_m5):
                exit_price = xau_m5.iloc[pos + hold]['close']
            else:
                continue
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            count += 1
            if pnl > 0:
                hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:3d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")

# XAU US 15-18 standalone baseline
print(f"\n--- XAU US 15-18 RSI<20 CB>=2 standalone baseline ---")
if len(xau_loose_entries) >= 50:
    for hold in [40, 60, 80, 100, 110, 120]:
        hits = 0
        total_pnl = 0
        count = 0
        for idx, row in xau_loose_entries.iterrows():
            entry_price = row['close']
            pos = xau_m5.index.get_loc(idx)
            if pos + hold < len(xau_m5):
                exit_price = xau_m5.iloc[pos + hold]['close']
            else:
                continue
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            count += 1
            if pnl > 0:
                hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:3d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")
