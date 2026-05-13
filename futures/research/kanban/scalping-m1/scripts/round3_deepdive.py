#!/usr/bin/env python3
"""Round 3: Deep dive on promising findings."""
import numpy as np
import pandas as pd
from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
from grid_engine import _compute_stats

# ─── Deep Dive 1: XAUUSD M1 欧盘 RSI<20 — hold精细扫描 ───
print("=" * 70)
print("DEEP DIVE 1: XAUUSD M1 欧盘 RSI<20 — hold精细扫描")
print("=" * 70)

data = load_data("M1", symbols=["XAUUSD"])
for sym, df in data.items():
    df2 = compute_indicators(df)
    
    # Check condition
    cond = "session == 'europe' and rsi14 < 20"
    mask = df2.eval(cond)
    entry_prices = df2.loc[mask, "close"].values
    entry_indices = df2.index[mask]
    print(f"信号总数: {len(entry_prices)}")
    print(f"约每 {len(df2)/len(entry_prices):.0f} 根K线1次信号")
    
    # Fine scan holds 1-60
    hold_periods = list(range(1, 61))
    periods_per_year = PERIODS_PER_YEAR["M1"]
    
    results = []
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
        results.append((hold, stats["win_rate"], stats["n"], stats["avg_return"], stats["sharpe_ratio"]))
    
    # Show best 10 by WR
    results.sort(key=lambda x: -x[1])
    print(f"\n{'Hold':<6} {'胜率':<7} {'n':<6} {'平均收益':<12} {'Sharpe':<10}")
    print("-" * 45)
    for hold, wr, n, avg, sharpe in results[:15]:
        if n >= 20:
            marker = ""
            if wr >= 0.65 and n >= 100:
                marker = " ★★"
            elif wr >= 0.62:
                marker = " ★"
            print(f"Hold={hold:<3} {wr*100:.1f}% {n:<6} {avg*100:.4f}% {sharpe:<10.2f}{marker}")
    
    # Also check if adding consecutive_bear helps
    print("\n--- 加入连续阴线过滤 ---")
    conds = {
        "base (RSI<20)": "session == 'europe' and rsi14 < 20",
        "+ consecutive_bear>=2": "session == 'europe' and rsi14 < 20 and consecutive_bear >= 2",
        "+ consecutive_bear>=3": "session == 'europe' and rsi14 < 20 and consecutive_bear >= 3",
    }
    for label, c in conds.items():
        m = df2.eval(c)
        print(f"{label:<40s} n={m.sum()}")


# ─── Deep Dive 2: XAUUSD M5 US中段 RSI<20 — 更精细hold扫描 ───
print("\n" + "=" * 70)
print("DEEP DIVE 2: XAUUSD M5 US中段 RSI<20 — 精确hold扫描")
print("=" * 70)

data5 = load_data("M5", symbols=["XAUUSD"])
for sym, df in data5.items():
    df2 = compute_indicators(df)
    
    cond = "hour >= 16 and hour < 19 and rsi14 < 20"
    mask = df2.eval(cond)
    entry_prices = df2.loc[mask, "close"].values
    entry_indices = df2.index[mask]
    print(f"信号总数: {len(entry_prices)}")
    
    hold_periods = list(range(30, 131, 5))  # 30 to 130 step 5
    periods_per_year = PERIODS_PER_YEAR["M5"]
    
    results = []
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
        results.append((hold, stats["win_rate"], stats["n"], stats["avg_return"], stats["sharpe_ratio"]))
    
    results.sort(key=lambda x: -x[1])
    print(f"\n{'Hold':<6} {'胜率':<7} {'n':<6} {'平均收益':<12} {'Sharpe':<10}")
    print("-" * 45)
    for hold, wr, n, avg, sharpe in results[:10]:
        if n >= 20:
            print(f"Hold={hold:<3} {wr*100:.1f}% {n:<6} {avg*100:.4f}% {sharpe:<10.2f}")


# ─── Deep Dive 3: XAUUSD M1 欧盘 RSI<25 (更宽松) ───
print("\n" + "=" * 70)
print("DEEP DIVE 3: XAUUSD M1 欧盘 RSI<25 — 宽松版本vs严格版本")
print("=" * 70)

for sym, df in data.items():
    df2 = compute_indicators(df)
    
    conds = {
        "RSI<20 (严格)": "session == 'europe' and rsi14 < 20",
        "RSI<25 (中等)": "session == 'europe' and rsi14 < 25",
        "RSI<30 (宽松)": "session == 'europe' and rsi14 < 30",
    }
    
    hold_periods = [5, 10, 15, 20, 30, 45, 60]
    periods_per_year = PERIODS_PER_YEAR["M1"]
    
    print(f"\n{'条件':<35s} {'最佳Hold':<9} {'胜率':<7} {'n':<6} {'平均收益':<12} {'Sharpe':<10}")
    print("-" * 80)
    
    for label, cond in conds.items():
        m = df2.eval(cond)
        ep = df2.loc[m, "close"].values
        ei = df2.index[m]
        
        best_wr, best_hold, best_avg, best_sharpe, best_n = 0, 0, 0, 0, 0
        for hold in hold_periods:
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
            stats = _compute_stats(returns_arr, hold, periods_per_year)
            if stats["win_rate"] > best_wr and stats["n"] >= 20:
                best_wr = stats["win_rate"]
                best_hold = hold
                best_avg = stats["avg_return"]
                best_sharpe = stats["sharpe_ratio"]
                best_n = stats["n"]
        
        print(f"{label:<35s} Hold={best_hold:<4} {best_wr*100:.1f}% {best_n:<6} {best_avg*100:.4f}%  {best_sharpe:<10.2f}")


# ─── Deep Dive 4: US30 atr>0.4 volume对比 — 看收益分布 ───
print("\n" + "=" * 70)
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
    
    # Check hold=120 returns
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
        print(f"  {label:<12s} hold=120: WR={np.mean(returns>0)*100:.1f}% n={len(returns)} avg={np.mean(returns)*100:.3f}% "
              f"std={np.std(returns)*100:.3f}% min={np.min(returns)*100:.3f}% max={np.max(returns)*100:.3f}%")
        # Skewness
        skew = pd.Series(returns).skew()
        print(f"             skewness={skew:.2f}  pos_median={np.median(returns[returns>0]):.4f} neg_median={np.median(returns[returns<=0]):.4f}")


# ─── Deep Dive 5: XAUUSD M1 美盘RSI<20 hold精细 ───
print("\n" + "=" * 70)
print("DEEP DIVE 5: XAUUSD M1 美盘 RSI<20 — hold谱")
print("=" * 70)

for sym, df in data.items():
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

print("\n" + "=" * 70)
print("所有深度分析完成")
print("=" * 70)
