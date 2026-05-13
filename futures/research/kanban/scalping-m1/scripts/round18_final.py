#!/usr/bin/env python3
"""Round 18 - Final verification tests"""
import sys
sys.path.insert(0, '.')
from data_loader import load_data, compute_indicators
from grid_engine import run_grid
import pandas as pd
import numpy as np

# Test bf_046 with correct hold (115)
print("bf_046: XAU US 15-16 RSI<20 CB>=2 (with hold=115)")
result = run_grid({
    "timeframe": "M5",
    "symbols": ["XAUUSD"],
    "entry_condition": "session == 'us' and hour >= 15 and hour < 16 and rsi14 < 20 and consecutive_bear >= 2",
    "direction": "long",
    "hold_periods": [60, 80, 100, 110, 115, 120, 130],
})
if result and "XAUUSD" in result:
    for r in result["XAUUSD"]:
        wr = r['win_rate'] * 100
        ar = r['avg_return'] * 100
        print(f"  hold={r['hold_period']:3d}  WR={wr:.1f}%  n={r['n']:4d}  avg={ar:.3f}%  Sharpe={r['sharpe_ratio']:.2f}")

print()

# Test bf_048: XAU M1 9-11 RSI<18 CB>=3
print("bf_048: XAU M1 9-11 RSI<18 CB>=3")
result = run_grid({
    "timeframe": "M1",
    "symbols": ["XAUUSD"],
    "entry_condition": "session == 'europe' and hour >= 9 and hour < 11 and rsi14 < 18 and consecutive_bear >= 3",
    "direction": "long",
    "hold_periods": [10, 12, 14, 16, 18, 20, 23],
})
if result and "XAUUSD" in result:
    for r in result["XAUUSD"]:
        wr = r['win_rate'] * 100
        ar = r['avg_return'] * 100
        print(f"  hold={r['hold_period']:2d}  WR={wr:.1f}%  n={r['n']:4d}  avg={ar:.3f}%  Sharpe={r['sharpe_ratio']:.2f}")

print()

# Test bf_041: XAU M1 8-11 RSI<18 CB>=3
print("bf_041: XAU M1 8-11 RSI<18 CB>=3")
result = run_grid({
    "timeframe": "M1",
    "symbols": ["XAUUSD"],
    "entry_condition": "session == 'europe' and hour >= 8 and hour < 11 and rsi14 < 18 and consecutive_bear >= 3",
    "direction": "long",
    "hold_periods": [10, 13, 16, 20, 23, 25, 30],
})
if result and "XAUUSD" in result:
    for r in result["XAUUSD"]:
        wr = r['win_rate'] * 100
        ar = r['avg_return'] * 100
        print(f"  hold={r['hold_period']:2d}  WR={wr:.1f}%  n={r['n']:4d}  avg={ar:.3f}%  Sharpe={r['sharpe_ratio']:.2f}")

print()

# NEW TEST: XAU US 15-18 RSI<20 CB>=2 (bf_018 base) + JP resonance with hold=100
print("NEW - XAU US 15-18 RSI<20 CB>=2 + JP US 15-18 RSI<20 CB>=2 within 3 bars")
print("(combining bf_018 and bf_023 conditions)")
xau_m5 = compute_indicators(load_data("M5", symbols=["XAUUSD"])["XAUUSD"])
jp_m5 = compute_indicators(load_data("M5", symbols=["JP225"])["JP225"])

common_idx = xau_m5.index.intersection(jp_m5.index)
xau_aln = xau_m5.loc[common_idx]
jp_aln = jp_m5.loc[common_idx]

# XAU: US 15-18 RSI<20 CB>=2 (bf_018)
xau_cond = ((xau_aln['session'] == 'us') & (xau_aln['hour'] >= 15) & (xau_aln['hour'] < 18) & (xau_aln['rsi14'] < 20) & (xau_aln['consecutive_bear'] >= 2))
xau_entries = xau_aln[xau_cond]
print(f"XAU bf_018: {len(xau_entries)} signals")

# JP: US 15-18 RSI<20 CB>=2
jp_cond = ((jp_aln['session'] == 'us') & (jp_aln['hour'] >= 15) & (jp_aln['hour'] < 18) & (jp_aln['rsi14'] < 20) & (jp_aln['consecutive_bear'] >= 2))
jp_entries = jp_aln[jp_cond]
print(f"JP similar: {len(jp_entries)} signals")

# Same bar
same = xau_entries.index.intersection(jp_entries.index)
print(f"Same bar resonance: {len(same)}")

if len(same) >= 10:
    for hold in [60, 80, 100, 110, 120, 130]:
        hits = 0
        total_pnl = 0
        count = 0
        for idx in same:
            entry_price = xau_aln.loc[idx, 'close']
            pos = xau_aln.index.get_loc(idx)
            if pos + hold < len(xau_aln):
                exit_price = xau_aln.iloc[pos + hold]['close']
                count += 1
                pnl = (exit_price - entry_price) / entry_price * 100
                total_pnl += pnl
                if pnl > 0:
                    hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:3d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")

print()

# NEW TEST: XAU M5 欧盘8-11 RSI<18 CB>=4 (not in best_findings, see if there's something new)
print("NEW - XAU M5 EU 8-11 RSI<18 CB>=4")
result = run_grid({
    "timeframe": "M5",
    "symbols": ["XAUUSD"],
    "entry_condition": "session == 'europe' and hour >= 8 and hour < 11 and rsi14 < 18 and consecutive_bear >= 4",
    "direction": "long",
    "hold_periods": [30, 35, 40, 42, 44, 48],
})
if result and "XAUUSD" in result:
    for r in result["XAUUSD"]:
        wr = r['win_rate'] * 100
        ar = r['avg_return'] * 100
        print(f"  hold={r['hold_period']:2d}  WR={wr:.1f}%  n={r['n']:4d}  avg={ar:.3f}%  Sharpe={r['sharpe_ratio']:.2f}")

print()

# NEW TEST: XAU M5 EU 9-11 RSI<18 CB>=4 (more restrictive than bf_035)
print("NEW - XAU M5 EU 9-11 RSI<18 CB>=4")
result = run_grid({
    "timeframe": "M5",
    "symbols": ["XAUUSD"],
    "entry_condition": "session == 'europe' and hour >= 9 and hour < 11 and rsi14 < 18 and consecutive_bear >= 4",
    "direction": "long",
    "hold_periods": [30, 35, 40, 42, 44, 48],
})
if result and "XAUUSD" in result:
    for r in result["XAUUSD"]:
        wr = r['win_rate'] * 100
        ar = r['avg_return'] * 100
        print(f"  hold={r['hold_period']:2d}  WR={wr:.1f}%  n={r['n']:4d}  avg={ar:.3f}%  Sharpe={r['sharpe_ratio']:.2f}")

print()

# NEW TEST: XAU M5 US 15-16 RSI<22 CB>=2 (more signals than bf_046)
print("NEW - XAU M5 US 15-16 RSI<22 CB>=2")
result = run_grid({
    "timeframe": "M5",
    "symbols": ["XAUUSD"],
    "entry_condition": "session == 'us' and hour >= 15 and hour < 16 and rsi14 < 22 and consecutive_bear >= 2",
    "direction": "long",
    "hold_periods": [60, 80, 100, 110, 115, 120, 130],
})
if result and "XAUUSD" in result:
    for r in result["XAUUSD"]:
        wr = r['win_rate'] * 100
        ar = r['avg_return'] * 100
        print(f"  hold={r['hold_period']:3d}  WR={wr:.1f}%  n={r['n']:4d}  avg={ar:.3f}%  Sharpe={r['sharpe_ratio']:.2f}")
