#!/usr/bin/env python3
"""Round 3: Deep dive 4+5 — fix."""
import numpy as np
import pandas as pd
from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
from grid_engine import _compute_stats

# ─── Deep Dive 4: US30 atr>0.4 volume对比 — 看收益分布 ───
print("=" * 70)
print("DEEP DIVE 4: US30 M5 atr>0.4 volume对比 — 收益分布")
print("=" * 70)

data_us30 = load_data("M5", symbols=["US30"])
for sym, df in data_us30.items():
    df2 = compute_indicators(df)
    df2['vol_ma20'] = df2['tick_volume'].rolling(20).mean()
    df2['volume_high'] = df2['tick_volume'] > df2['vol_ma20']
    df2['volume_low'] = df2['tick_volume'] <= df2['vol_ma20']
    
    cond_base = "session == 'us' and atr14_pct > 0.4"
    mask_base = df2.eval(cond_base)
    mask_high = mask_base & df2['volume_high']
    mask_low = mask_base & df2['volume_low']
    
    print(f"Base (atr>0.4):        {mask_base.sum()} signals")
    print(f"  + volume_high:       {mask_high.sum()} signals")
    print(f"  + volume_low:        {mask_low.sum()} signals")
    
    for label, m in [("base", mask_base), ("vol_high", mask_high), ("vol_low", mask_low)]:
        ep = df2.loc[m, "close"].values
        ei = df2.index[m]
        returns = []
        for i in range(len(ei)):
            pos = df2.index.get_loc(ei[i])
            exit_pos = pos + 120
            if exit_pos >= len(df2):
                continue
            exit_price = df2.iloc[exit_pos]["close"]
            ret = (exit_price - ep[i]) / ep[i]
            returns.append(ret)
        returns_arr = np.array(returns, dtype=float)
        wr = float((returns_arr > 0).mean()) * 100
        avg = float(returns_arr.mean()) * 100
        std = float(returns_arr.std()) * 100
        print(f"  {label:<12s} hold=120: WR={wr:.1f}% n={len(returns_arr)} avg={avg:.3f}% "
              f"std={std:.3f}%")
        pos_ret = returns_arr[returns_arr > 0]
        neg_ret = returns_arr[returns_arr <= 0]
        if len(pos_ret) > 0 and len(neg_ret) > 0:
            print(f"             pos_median={np.median(pos_ret)*100:.4f}% neg_median={np.median(neg_ret)*100:.4f}%")


# ─── Deep Dive 5: XAUUSD M1 美盘RSI<20 hold精细 ───
print("\n" + "=" * 70)
print("DEEP DIVE 5: XAUUSD M1 美盘 RSI<20 — hold谱")
print("=" * 70)

data_m1 = load_data("M1", symbols=["XAUUSD"])
for sym, df in data_m1.items():
    df2 = compute_indicators(df)
    
    cond = "session == 'us' and rsi14 < 20"
    mask = df2.eval(cond)
    entry_prices = df2.loc[mask, "close"].values
    entry_indices = df2.index[mask]
    print(f"信号总数: {len(entry_prices)}")
    
    hold_periods = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30]
    periods_per_year = PERIODS_PER_YEAR["M1"]
    
    print(f"\n{'Hold':<6} {'胜率':<7} {'n':<6} {'平均收益':<12} {'Sharpe':<10}")
    print("-" * 45)
    for hold in hold_periods:
        returns = []
        for i in range(len(entry_indices)):
            pos = df2.index.get_loc(entry_indices[i])
            exit_pos = pos + hold
            if exit_pos >= len(df2):
                continue
            exit_price = df2.iloc[exit_pos]["close"]
            ret = (exit_price - entry_prices[i]) / entry_prices[i]
            returns.append(ret)
        returns_arr = np.array(returns, dtype=float)
        stats = _compute_stats(returns_arr, hold, periods_per_year)
        marker = " ★" if stats["win_rate"] >= 0.60 and stats["n"] >= 50 else ""
        print(f"Hold={hold:<3} {stats['win_rate']*100:.1f}% {stats['n']:<6} {stats['avg_return']*100:.4f}%  {stats['sharpe_ratio']:<10.2f}{marker}")


# ─── Deep Dive 6: XAUUSD M5 US中段 RSI<20 vs RSI<25 — 不同hold对比总结 ───
print("\n" + "=" * 70)
print("DEEP DIVE 6: XAUUSD M5 US中段 RSI<20 hold=75详细收益分布")
print("=" * 70)

data5 = load_data("M5", symbols=["XAUUSD"])
for sym, df in data5.items():
    df2 = compute_indicators(df)
    
    cond = "hour >= 16 and hour < 19 and rsi14 < 20"
    mask = df2.eval(cond)
    ep = df2.loc[mask, "close"].values
    ei = df2.index[mask]
    
    for hold in [75, 90]:
        returns = []
        for i in range(len(ei)):
            pos = df2.index.get_loc(ei[i])
            exit_pos = pos + hold
            if exit_pos >= len(df2):
                continue
            exit_price = df2.iloc[exit_pos]["close"]
            ret = (exit_price - ep[i]) / ep[i]
            returns.append(ret)
        returns_arr = np.array(returns, dtype=float)
        wr = float((returns_arr > 0).mean()) * 100
        avg = float(returns_arr.mean()) * 100
        std = float(returns_arr.std()) * 100
        pos_ret = returns_arr[returns_arr > 0]
        neg_ret = returns_arr[returns_arr <= 0]
        print(f"Hold={hold}: WR={wr:.1f}% n={len(returns_arr)} avg={avg:.4f}% std={std:.4f}%")
        if len(pos_ret) > 0 and len(neg_ret) > 0:
            print(f"  pos_median={np.median(pos_ret)*100:.4f}% neg_median={np.median(neg_ret)*100:.4f}% "
                  f"pos_count={len(pos_ret)} neg_count={len(neg_ret)}")

print("\nDone.")
