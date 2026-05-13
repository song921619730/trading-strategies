#!/usr/bin/env python3
"""
Round 18 — 重新测试 (使用正确的 consecutive_bear 计算)
使用 data_loader 的 compute_indicators 确保 CB 计算一致
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators
import pandas as pd
import numpy as np

# ============ Load M5 data properly ============
print("Loading M5 data...")
m5_raw = load_data("M5", symbols=["XAUUSD", "JP225"])

xau_m5 = compute_indicators(m5_raw["XAUUSD"])
jp_m5 = compute_indicators(m5_raw["JP225"])

print(f"XAUUSD M5: {len(xau_m5)} rows [{xau_m5.index[0]} → {xau_m5.index[-1]}]")
print(f"JP225 M5: {len(jp_m5)} rows [{jp_m5.index[0]} → {jp_m5.index[-1]}]")

# Verify consecutive_bear computation
print(f"\nXAU CB sample (last 10):")
print(xau_m5[['close', 'open', 'consecutive_bear']].tail(10).to_string())

# ============ H1: XAUUSDM5 9:45-11 RSI<22+CB>=4 跨周期验证 ============
print("\n" + "="*70)
print("H1: XAUUSD M5 9:45-11 RSI<22+CB>=4 跨周期稳定性验证 (correct CB)")
print("="*70)

n = len(xau_m5)
p1 = xau_m5.iloc[:n//3]
p2 = xau_m5.iloc[n//3:2*n//3]
p3 = xau_m5.iloc[2*n//3:]

def test_bf050(data, label):
    mask = (
        (data['session'] == 'europe') &
        (data['hour'] >= 9) & (data['hour'] < 11) & (data['minute'] >= 45) &
        (data['rsi14'] < 22) &
        (data['consecutive_bear'] >= 4)
    )
    entries = data[mask].copy()
    print(f"{label}: {len(entries)} signals")
    if len(entries) < 5:
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
                count += 1
                pnl = (exit_price - entry_price) / entry_price * 100
                total_pnl += pnl
                if pnl > 0:
                    hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:2d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")

test_bf050(p1, "P1")
print()
test_bf050(p2, "P2")
print()
test_bf050(p3, "P3")
print()
test_bf050(xau_m5, "FULL")
print()

# ============ H2: XAU+JP共振 — 使用正确CB ============
print("="*70)
print("H2: XAU+JP225 多品种共振 (正确的CB计算)")
print("="*70)

common_idx = xau_m5.index.intersection(jp_m5.index)
xau_aln = xau_m5.loc[common_idx]
jp_aln = jp_m5.loc[common_idx]

# XAU US 15-16 RSI<20 CB>=2 (bf_046)
xau_cond = (
    (xau_aln['session'] == 'us') &
    (xau_aln['hour'] >= 15) & (xau_aln['hour'] < 16) &
    (xau_aln['rsi14'] < 20) &
    (xau_aln['consecutive_bear'] >= 2)
)
xau_entries = xau_aln[xau_cond]
print(f"XAU standalone (bf_046): {len(xau_entries)} signals")

# JP US 15-18 RSI<16 CB>=2 (bf_045)
jp_cond = (
    (jp_aln['session'] == 'us') &
    (jp_aln['hour'] >= 15) & (jp_aln['hour'] < 18) &
    (jp_aln['rsi14'] < 16) &
    (jp_aln['consecutive_bear'] >= 2)
)
jp_entries = jp_aln[jp_cond]
print(f"JP extreme (bf_045): {len(jp_entries)} signals")

# Same bar resonance
same_bar = xau_entries.index.intersection(jp_entries.index)
print(f"\nSame bar resonance (XAU bf_046 + JP bf_045): {len(same_bar)}")

if len(same_bar) >= 5:
    for hold in [60, 80, 100, 110, 115, 120]:
        hits = 0
        total_pnl = 0
        count = 0
        for idx in same_bar:
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

# Also test broader JP condition for more samples
print("\n--- XAU bf_046 + JP broader condition ---")
jp_broader = (
    (jp_aln['session'] == 'us') &
    (jp_aln['hour'] >= 15) & (jp_aln['hour'] < 18) &
    (jp_aln['rsi14'] < 20) &
    (jp_aln['consecutive_bear'] >= 2)
)
jp_broader_entries = jp_aln[jp_broader]
print(f"JP broader (RSI<20 CB>=2): {len(jp_broader_entries)} signals")

same_bar2 = xau_entries.index.intersection(jp_broader_entries.index)
print(f"Same bar resonance: {len(same_bar2)}")

if len(same_bar2) >= 10:
    for hold in [60, 80, 100, 110, 115, 120]:
        hits = 0
        total_pnl = 0
        count = 0
        for idx in same_bar2:
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

# Test XAU+JP filter (XAU entries filtered by recent JP condition)
print("\n--- XAU+JP filter: XAU signal + JP signal within last 3 bars ---")
xau_filtered = []
for idx, row in xau_entries.iterrows():
    pos = jp_aln.index.get_loc(idx)
    jp_found = False
    for offset in range(0, 4):
        check_pos = pos - offset
        if check_pos < 0:
            break
        check_idx = jp_aln.index[check_pos]
        jp_r = jp_aln.loc[check_idx]
        if (jp_r['session'] == 'us' and jp_r['hour'] >= 15 and jp_r['hour'] < 18 and 
            jp_r['rsi14'] < 20 and jp_r['consecutive_bear'] >= 2):
            jp_found = True
            break
    if jp_found:
        xau_filtered.append(row)

print(f"XAU bf_046 + JP filter (RSI<20 CB>=2 within 3 bars): {len(xau_filtered)}")

if len(xau_filtered) >= 15:
    for hold in [60, 80, 100, 110, 115, 120]:
        hits = 0
        total_pnl = 0
        count = 0
        for row_dict in xau_filtered:
            idx = row_dict.name
            entry_price = row_dict['close']
            pos = xau_m5.index.get_loc(idx)
            if pos + hold < len(xau_m5):
                exit_price = xau_m5.iloc[pos + hold]['close']
                count += 1
                pnl = (exit_price - entry_price) / entry_price * 100
                total_pnl += pnl
                if pnl > 0:
                    hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            print(f"  hold={hold:3d}  WR={wr:.1f}%  n={count}  avg={avg_ret:.3f}%")

# ============ Also test bf_050 baseline using run_grid from grid_engine ============
print("\n" + "="*70)
print("BASELINE: Using grid_engine.run_grid for bf_050 condition")
print("="*70)

from grid_engine import run_grid
import warnings
warnings.filterwarnings('ignore')

# Also test bf_046, bf_047 baselines
configs = [
    {
        "name": "bf_050: XAU 9:45-11 RSI<22 CB>=4",
        "entry": "session == 'europe' and hour >= 9 and hour < 11 and minute >= 45 and rsi14 < 22 and consecutive_bear >= 4",
    },
    {
        "name": "bf_046: XAU US 15-16 RSI<20 CB>=2",
        "entry": "session == 'us' and hour >= 15 and hour < 16 and rsi14 < 20 and consecutive_bear >= 2",
    },
    {
        "name": "bf_047: XAU EU 10-11 RSI<22 CB>=3",
        "entry": "session == 'europe' and hour >= 10 and hour < 11 and rsi14 < 22 and consecutive_bear >= 3",
    },
    {
        "name": "bf_034: XAU EU 9-11 RSI<22 CB>=3",
        "entry": "session == 'europe' and hour >= 9 and hour < 11 and rsi14 < 22 and consecutive_bear >= 3",
    },
]

for cfg in configs:
    print(f"\n--- {cfg['name']} ---")
    try:
        result = run_grid({
            "timeframe": "M5",
            "symbols": ["XAUUSD"],
            "entry_condition": cfg["entry"],
            "direction": "long",
            "hold_periods": [38, 40, 42, 44, 46, 48, 50],
        })
        if result and "XAUUSD" in result:
            for r in result["XAUUSD"]:
                wr = r['win_rate'] * 100
                ar = r['avg_return'] * 100
                print(f"  hold={r['hold_period']:2d}  WR={wr:.1f}%  n={r['n']:4d}  avg={ar:.3f}%  Sharpe={r['sharpe_ratio']:.2f}")
    except Exception as e:
        print(f"  Error: {e}")
