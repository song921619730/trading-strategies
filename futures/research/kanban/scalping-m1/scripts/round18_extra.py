#!/usr/bin/env python3
"""Round 18 - Additional tests for new hypotheses"""
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
    df['consecutive_bull'] = df['close'].rolling(20).apply(lambda x: np.sum(np.diff(x) > 0) if len(x) > 1 else 0, raw=True)

common_idx = xau_m5.index.intersection(jp_m5.index)
xau_aln = xau_m5.loc[common_idx]
jp_aln = jp_m5.loc[common_idx]

# ============================================================
# Test 1: XAU US 15-18 + JP US 15-18 (broadest JP condition to boost n)
# Use JP: US 15-18 RSI<20 (no CB requirement) as a volume/volatility filter
# ============================================================
print("="*70)
print("TEST 1: XAU US 15-18 RSI<20 CB>=2 + JP US 15-18 RSI<20 (any)")
print("="*70)

xau_cond = ((xau_aln['session'] == 'us') & (xau_aln.index.hour >= 15) & (xau_aln.index.hour < 18) & (xau_aln['rsi14'] < 20) & (xau_aln['consecutive_bear'] >= 2))
jp_cond = ((jp_aln['session'] == 'us') & (jp_aln.index.hour >= 15) & (jp_aln.index.hour < 18) & (jp_aln['rsi14'] < 20))

# Same bar: XAU + JP
resonance = xau_cond & jp_cond
resonance_idx = xau_aln.index[resonance]
print(f"XAU standalone signals: {sum(xau_cond)}")
print(f"JP (RSI<20) signals: {sum(jp_cond)}")
print(f"Same bar resonance: {len(resonance_idx)}")

if len(resonance_idx) >= 30:
    for hold in [40, 60, 80, 100, 110, 120, 130]:
        hits = 0
        total_pnl = 0
        count = 0
        for idx in resonance_idx:
            entry_price = xau_aln.loc[idx, 'close']
            pos = xau_aln.index.get_loc(idx)
            if pos + hold < len(xau_aln):
                exit_price = xau_aln.iloc[pos + hold]['close']
            else:
                continue
            count += 1
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            if pnl > 0:
                hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:3d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")

# ============================================================
# Test 2: XAU US 15-16 + JP US 15-18 with loosest JP condition
# Try JP: RSI<22 (no CB) to get more resonance
# ============================================================
print("\n" + "="*70)
print("TEST 2: XAU US 15-16 RSI<20 CB>=2 + JP US 15-18 RSI<22 (any)")
print("="*70)

xau_cond2 = ((xau_m5['session'] == 'us') & (xau_m5.index.hour >= 15) & (xau_m5.index.hour < 16) & (xau_m5['rsi14'] < 20) & (xau_m5['consecutive_bear'] >= 2))
jp_cond2 = ((jp_m5['session'] == 'us') & (jp_m5.index.hour >= 15) & (jp_m5.index.hour < 18) & (jp_m5['rsi14'] < 22))
xau2_entries = xau_m5[xau_cond2]
jp2_entries = jp_m5[jp_cond2]
common2 = xau2_entries.index.intersection(jp2_entries.index)
print(f"XAU signals: {len(xau2_entries)}")
print(f"JP RSI<22 signals: {len(jp2_entries)}")
print(f"Resonance: {len(common2)}")

if len(common2) >= 30:
    for hold in [80, 90, 100, 110, 115, 120, 130]:
        hits = 0
        total_pnl = 0
        count = 0
        for idx in common2:
            entry_price = xau_m5.loc[idx, 'close']
            pos = xau_m5.index.get_loc(idx)
            if pos + hold < len(xau_m5):
                exit_price = xau_m5.iloc[pos + hold]['close']
            else:
                continue
            count += 1
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            if pnl > 0:
                hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:3d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")

# ============================================================
# Test 3: XAU M1 欧盘8-11 RSI<18+CB>=3 (bf_041) 跨数据周期稳定性验证
# ============================================================
print("\n" + "="*70)
print("TEST 3: XAUUSD M1 欧盘8-11 RSI<18+CB>=3 (bf_041) 跨周期稳定性")
print("="*70)

xau_m1_raw = load_data("M1", symbols=["XAUUSD"])
xau_m1 = compute_indicators(xau_m1_raw["XAUUSD"])
xau_m1['session'] = 'asia'
xau_m1.loc[(xau_m1.index.hour >= 8) & (xau_m1.index.hour < 13), 'session'] = 'europe'
xau_m1.loc[(xau_m1.index.hour >= 13) & (xau_m1.index.hour < 22), 'session'] = 'us'
xau_m1['consecutive_bear'] = xau_m1['close'].rolling(20).apply(lambda x: np.sum(np.diff(x) < 0) if len(x) > 1 else 0, raw=True)

n = len(xau_m1)
p1 = xau_m1.iloc[:n//3].copy()
p2 = xau_m1.iloc[n//3:2*n//3].copy()
p3 = xau_m1.iloc[2*n//3:].copy()

print(f"Total: {n} rows | P1: {len(p1)} | P2: {len(p2)} | P3: {len(p3)}")

def test_m1_period(data, label, best_hold):
    mask = ((data['session'] == 'europe') & (data.index.hour >= 8) & (data.index.hour < 11) & (data['rsi14'] < 18) & (data['consecutive_bear'] >= 3))
    entries = data[mask].copy()
    print(f"{label}: {len(entries)} signals")
    if len(entries) < 10:
        return
    for hold in [10, 13, 16, 20, 23, 25, 30]:
        hits = 0
        total_pnl = 0
        count = 0
        for idx, row in entries.iterrows():
            entry_price = row['close']
            pos = data.index.get_loc(idx)
            if pos + hold < len(data):
                exit_price = data.iloc[pos + hold]['close']
            else:
                continue
            count += 1
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            if pnl > 0:
                hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:2d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")

test_m1_period(p1, "P1", 23)
print()
test_m1_period(p2, "P2", 23)
print()
test_m1_period(p3, "P3", 23)
print()
test_m1_period(xau_m1, "FULL", 23)

# ============================================================
# Test 4: XAU M1 欧盘9-11 RSI<18+CB>=4 (bf_042) 跨周期稳定性
# ============================================================
print("\n" + "="*70)
print("TEST 4: XAUUSD M1 欧盘9-11 RSI<18+CB>=4 (bf_042) 跨周期稳定性")
print("="*70)

def test_m1_cb4(data, label):
    mask = ((data['session'] == 'europe') & (data.index.hour >= 9) & (data.index.hour < 11) & (data['rsi14'] < 18) & (data['consecutive_bear'] >= 4))
    entries = data[mask].copy()
    print(f"{label}: {len(entries)} signals")
    if len(entries) < 10:
        return
    for hold in [10, 12, 13, 15, 16, 18, 20]:
        hits = 0
        total_pnl = 0
        count = 0
        for idx, row in entries.iterrows():
            entry_price = row['close']
            pos = data.index.get_loc(idx)
            if pos + hold < len(data):
                exit_price = data.iloc[pos + hold]['close']
            else:
                continue
            count += 1
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            if pnl > 0:
                hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:2d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")

test_m1_cb4(p1, "P1")
print()
test_m1_cb4(p2, "P2")
print()
test_m1_cb4(p3, "P3")
print()
test_m1_cb4(xau_m1, "FULL")

# ============================================================
# Test 5: New - XAU M5 欧盘10-11 RSI<22+CB>=3 (bf_047) 跨周期稳定性
# ============================================================
print("\n" + "="*70)
print("TEST 5: XAUUSD M5 欧盘10-11 RSI<22+CB>=3 (bf_047) 跨周期稳定性")
print("="*70)

n_m5 = len(xau_m5)
p1_m5 = xau_m5.iloc[:n_m5//3].copy()
p2_m5 = xau_m5.iloc[n_m5//3:2*n_m5//3].copy()
p3_m5 = xau_m5.iloc[2*n_m5//3:].copy()

def test_m5_bf047(data, label):
    mask = ((data['session'] == 'europe') & (data.index.hour >= 10) & (data.index.hour < 11) & (data['rsi14'] < 22) & (data['consecutive_bear'] >= 3))
    entries = data[mask].copy()
    print(f"{label}: {len(entries)} signals")
    if len(entries) < 10:
        return
    for hold in [38, 40, 42, 44, 46, 48, 50]:
        hits = 0
        total_pnl = 0
        count = 0
        for idx, row in entries.iterrows():
            entry_price = row['close']
            pos = data.index.get_loc(idx)
            if pos + hold < len(data):
                exit_price = data.iloc[pos + hold]['close']
            else:
                continue
            count += 1
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            if pnl > 0:
                hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:2d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")

test_m5_bf047(p1_m5, "P1")
print()
test_m5_bf047(p2_m5, "P2")
print()
test_m5_bf047(p3_m5, "P3")
print()
test_m5_bf047(xau_m5, "FULL")
