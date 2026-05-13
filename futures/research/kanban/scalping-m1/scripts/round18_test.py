#!/usr/bin/env python3
"""
Round 18 — 超短线研究循环
Testing priority=1 hypotheses:
1. round17_001: XAUUSD M5 欧盘9:45-11 RSI<22+CB>=4 跨数据周期稳定性验证
2. round17_002: XAUUSD M5 US 15-16 + JP225 多品种共振扩大样本
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators
from grid_engine import run_grid
import pandas as pd
import numpy as np

# Step 1: Load data summary
print("="*70)
print("DATA SUMMARY")
print("="*70)
for tf in ["M1", "M5"]:
    data = load_data(tf, symbols=["XAUUSD","EURUSD","USDJPY","US30","JP225"])
    for sym, df in data.items():
        df2 = compute_indicators(df)
        rsi_val = df2['rsi14'].iloc[-1]
        atr_val = df2['atr14_pct'].iloc[-1]
        print(f"{sym:10s} {tf} {len(df2):>8} rows  RSI={rsi_val:.1f}  ATR%={atr_val:.2f}%")

print()

# ============ Hypothesis 1: round17_001 ============
# XAUUSD M5 欧盘9:45-11 RSI<22+CB>=4 跨数据周期稳定性验证
print("="*70)
print("H1: XAUUSD M5 欧盘9:45-11 RSI<22+CB>=4 跨数据周期稳定性验证")
print("="*70)

# Load full XAUUSD M5 data
xau_m5_raw = load_data("M5", symbols=["XAUUSD"])
xau_m5 = compute_indicators(xau_m5_raw["XAUUSD"])

# Define the condition
xau_m5['session'] = 'asia'
xau_m5.loc[(xau_m5.index.hour >= 8) & (xau_m5.index.hour < 13), 'session'] = 'europe'
xau_m5.loc[(xau_m5.index.hour >= 13) & (xau_m5.index.hour < 22), 'session'] = 'us'

xau_m5['consecutive_bear'] = xau_m5['close'].rolling(20).apply(
    lambda x: np.sum(np.diff(x) < 0) if len(x) > 1 else 0, raw=True
)
xau_m5['consecutive_bull'] = xau_m5['close'].rolling(20).apply(
    lambda x: np.sum(np.diff(x) > 0) if len(x) > 1 else 0, raw=True
)

# Split data into 3 periods (P1: first third, P2: middle third, P3: last third)
n = len(xau_m5)
p1 = xau_m5.iloc[:n//3].copy()
p2 = xau_m5.iloc[n//3:2*n//3].copy()
p3 = xau_m5.iloc[2*n//3:].copy()

print(f"Total data: {n} rows")
print(f"P1: {len(p1)} rows ({p1.index[0]} to {p1.index[-1]})")
print(f"P2: {len(p2)} rows ({p2.index[0]} to {p2.index[-1]})")
print(f"P3: {len(p3)} rows ({p3.index[0]} to {p3.index[-1]})")
print()

# Test each period
config_base = {
    "timeframe": "M5",
    "symbols": ["XAUUSD"],
    "entry_condition": "session == 'europe' and hour >= 9 and hour < 11 and minute >= 45 and rsi14 < 22 and consecutive_bear >= 4",
    "direction": "long",
    "hold_periods": [44],  # best hold from bf_050
}

# We need to test each period separately
# Let's build the test manually
def test_period(data, label):
    """Test the condition on a specific data period"""
    mask = (
        (data['session'] == 'europe') &
        (data.index.hour >= 9) &
        (data.index.hour < 11) &
        (data.index.minute >= 45) &
        (data['rsi14'] < 22) &
        (data['consecutive_bear'] >= 4)
    )
    entries = data[mask].copy()
    print(f"{label}: {len(entries)} entry signals")
    
    if len(entries) < 10:
        return None
    
    for hold in [38, 40, 42, 44, 46, 48]:
        hits = 0
        total_pnl = 0
        for idx, row in entries.iterrows():
            entry_price = row['close']
            # Find exit price
            pos = data.index.get_loc(idx)
            if pos + hold < len(data):
                exit_price = data.iloc[pos + hold]['close']
            else:
                continue
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            if pnl > 0:
                hits += 1
        wr = hits / len(entries) * 100 if len(entries) > 0 else 0
        avg_ret = total_pnl / len(entries) if len(entries) > 0 else 0
        print(f"  hold={hold:2d}  WR={wr:.1f}%  n={len(entries)}  avg={avg_ret:.3f}%")
    
    return entries

print("--- P1 (Early) ---")
r1 = test_period(p1, "P1")
print()
print("--- P2 (Middle) ---")
r2 = test_period(p2, "P2")
print()
print("--- P3 (Recent) ---")
r3 = test_period(p3, "P3")
print()

# Also test the full period for baseline comparison
print("--- Full Period ---")
r_full = test_period(xau_m5, "FULL")
print()

print("="*70)
print("H2: XAUUSD M5 US 15-16 + JP225 多品种共振扩大样本")
print("="*70)

# Now test hypothesis 2: multi-asset resonance with broader JP225 condition
# JP225 RSI<16+CB>=2 (n=121 signals) as JP filter, check XAU signal quality

jp_m5_raw = load_data("M5", symbols=["JP225"])
jp_m5 = compute_indicators(jp_m5_raw["JP225"])

jp_m5['session'] = 'asia'
jp_m5.loc[(jp_m5.index.hour >= 8) & (jp_m5.index.hour < 13), 'session'] = 'europe'
jp_m5.loc[(jp_m5.index.hour >= 13) & (jp_m5.index.hour < 22), 'session'] = 'us'

jp_m5['consecutive_bear'] = jp_m5['close'].rolling(20).apply(
    lambda x: np.sum(np.diff(x) < 0) if len(x) > 1 else 0, raw=True
)
jp_m5['consecutive_bull'] = jp_m5['close'].rolling(20).apply(
    lambda x: np.sum(np.diff(x) > 0) if len(x) > 1 else 0, raw=True
)

# Get aligned data - use the same index
common_idx = xau_m5.index.intersection(jp_m5.index)
xau_aligned = xau_m5.loc[common_idx]
jp_aligned = jp_m5.loc[common_idx]

print(f"Aligned data: {len(common_idx)} rows")
print()

# JP condition 1: RSI<16+CB>=2 (broader, n=121)
jp_cond1 = (
    (jp_aligned['session'] == 'us') &
    (jp_aligned.index.hour >= 15) &
    (jp_aligned.index.hour < 18) &
    (jp_aligned['rsi14'] < 16) &
    (jp_aligned['consecutive_bear'] >= 2)
)
jp_sig1 = jp_aligned[jp_cond1].copy()
print(f"JP225 RSI<16+CB>=2 (us 15-18): {len(jp_sig1)} signals")

# XAU condition: US 15-16 RSI<20+CB>=2 (bf_046)
xau_cond = (
    (xau_aligned['session'] == 'us') &
    (xau_aligned.index.hour >= 15) &
    (xau_aligned.index.hour < 16) &
    (xau_aligned['rsi14'] < 20) &
    (xau_aligned['consecutive_bear'] >= 2)
)
xau_sig = xau_aligned[xau_cond].copy()
print(f"XAUUSD RSI<20+CB>=2 (us 15-16): {len(xau_sig)} signals")

# Test: XAU entry on same bar as JP signal
same_bar_mask = jp_cond1 & xau_cond
same_bar = xau_aligned[same_bar_mask].copy()
print(f"\nSame bar resonance: {len(same_bar)} signals")

if len(same_bar) >= 5:
    for hold in [80, 90, 100, 110, 115, 120, 130]:
        hits = 0
        total_pnl = 0
        for idx, row in same_bar.iterrows():
            entry_price = row['close']
            pos = xau_aligned.index.get_loc(idx)
            if pos + hold < len(xau_aligned):
                exit_price = xau_aligned.iloc[pos + hold]['close']
            else:
                continue
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            if pnl > 0:
                hits += 1
        wr = hits / len(same_bar) * 100
        avg_ret = total_pnl / len(same_bar)
        print(f"  hold={hold:3d}  WR={wr:.1f}%  n={len(same_bar)}  avg={avg_ret:.3f}%")

# Test: JP signals within 5 bars before XAU entry (wider resonance window)
print("\n--- JP信号后5根K线内XAU共振 ---")
# For each JP signal, check if XAU signal appears within 5 bars
confirmed_signals = 0
confirmed_data = []
for jp_idx, jp_row in jp_sig1.iterrows():
    jp_pos = jp_aligned.index.get_loc(jp_idx)
    # Check bars [jp_pos, jp_pos+5] for XAU condition
    for offset in range(0, 6):  # same bar to 5 bars later
        check_pos = jp_pos + offset
        if check_pos >= len(xau_aligned):
            break
        check_idx = xau_aligned.index[check_pos]
        check_row = xau_aligned.loc[check_idx]
        # Check XAU condition on this bar
        xau_cond_local = (
            (check_row['session'] == 'us') &
            (check_idx.hour >= 15) &
            (check_idx.hour < 16) &
            (check_row['rsi14'] < 20) &
            (check_row['consecutive_bear'] >= 2)
        )
        if xau_cond_local:
            confirmed_signals += 1
            confirmed_data.append(check_row)
            break  # Only count once per JP signal

print(f"JP->XAU confirmed signals: {confirmed_signals}")

if confirmed_signals >= 10:
    confirmed_df = pd.DataFrame(confirmed_data)
    for hold in [80, 90, 100, 110, 115, 120, 130]:
        hits = 0
        total_pnl = 0
        count = 0
        for row_dict in confirmed_data:
            idx = row_dict.name
            entry_price = row_dict['close']
            pos = xau_aligned.index.get_loc(idx)
            if pos + hold < len(xau_aligned):
                exit_price = xau_aligned.iloc[pos + hold]['close']
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

# Also test: XAU baseline vs XAU with JP filter
print("\n--- XAU standalone vs XAU+JP filter comparison ---")
# XAU standalone
xau_usa_15_16 = (
    (xau_m5['session'] == 'us') &
    (xau_m5.index.hour >= 15) &
    (xau_m5.index.hour < 16) &
    (xau_m5['rsi14'] < 20) &
    (xau_m5['consecutive_bear'] >= 2)
)
xau_entries = xau_m5[xau_usa_15_16].copy()
print(f"XAU standalone entries: {len(xau_entries)}")

# Now cross-reference: only take XAU entries where JP225 also has a bearish signal (CB>=2) in US session
# within the last 3 bars
xau_with_jp_filter = []
for idx, row in xau_entries.iterrows():
    pos = xau_m5.index.get_loc(idx)
    # Check JP225 in last 3 bars
    jp_check = False
    for offset in range(0, 4):  # current bar to 3 bars back
        check_pos = pos - offset
        if check_pos < 0:
            break
        check_idx = xau_m5.index[check_pos]
        if check_idx in jp_aligned.index:
            jp_row = jp_aligned.loc[check_idx]
            jp_cond = (
                (jp_row['session'] == 'us') &
                (jp_row.index.hour >= 15) &
                (jp_row.index.hour < 18) &
                (jp_row['rsi14'] < 20) &  # looser RSI
                (jp_row['consecutive_bear'] >= 2)
            )
            if jp_cond:
                jp_check = True
                break
    if jp_check:
        xau_with_jp_filter.append(row)

print(f"XAU with JP filter (CB>=2 within 3 bars): {len(xau_with_jp_filter)}")

if len(xau_with_jp_filter) >= 10:
    for hold in [80, 90, 100, 110, 115, 120, 130]:
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

print()
print("="*70)
print("Done Round 18 Tests")
print("="*70)
