#!/usr/bin/env python3
"""Round 3: Priority-1 tests for Scalping M1/M5 research."""
import sys, logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s|%(message)s")

import numpy as np
import pandas as pd
from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
from grid_engine import run_grid, print_results_table, _compute_stats

# ─── Test 1: US30 M5 atr>0.4 + volume filter  (round2_008) ───

print("=" * 70)
print("TEST 1 (round2_008): US30 M5 atr>0.4 + volume filter")
print("=" * 70)

data = load_data("M5", symbols=["US30", "JP225"])
results_all = {}

for sym, df in data.items():
    df2 = compute_indicators(df)
    
    # Calculate rolling avg volume (20 periods)
    df2['vol_ma20'] = df2['tick_volume'].rolling(20).mean()
    df2['volume_high'] = df2['tick_volume'] > df2['vol_ma20']
    df2['volume_low'] = df2['tick_volume'] <= df2['vol_ma20']
    
    # Test conditions
    conditions = {
        "base (atr>0.4 only)": "session == 'us' and atr14_pct > 0.4",
        "atr>0.4 + volume_high": "session == 'us' and atr14_pct > 0.4 and volume_high",
        "atr>0.4 + volume_low": "session == 'us' and atr14_pct > 0.4 and volume_low",
    }
    
    hold_periods = [5, 10, 15, 20, 30, 60, 90, 120, 240]
    periods_per_year = PERIODS_PER_YEAR["M5"]
    
    for label, condition in conditions.items():
        mask = df2.eval(condition)
        entry_prices = df2.loc[mask, "close"].values
        entry_indices = df2.index[mask]
        
        if len(entry_prices) < 5:
            print(f"{sym:10s} | {label:<30s} | n={len(entry_prices)} — 样本不足")
            continue
        
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
            
            key = f"{sym}|{label}|Hold={hold}"
            results_all[key] = {
                "sym": sym, "label": label, "hold": hold,
                "wr": stats["win_rate"], "n": stats["n"],
                "avg_ret": stats["avg_return"], "sharpe": stats["sharpe_ratio"],
                "mdd": stats["max_drawdown"],
            }

# Print results sorted by WR desc
print(f"\n{'品种':<10} {'条件':<35} {'Hold':<5} {'胜率':<7} {'n':<6} {'平均收益':<10} {'Sharpe':<8}")
print("-" * 85)
for k in sorted(results_all, key=lambda k: -results_all[k]["wr"]):
    r = results_all[k]
    if r["n"] >= 10:
        print(f"{r['sym']:<10} {r['label']:<35} {r['hold']:<5} {r['wr']*100:.1f}% {r['n']:<6} {r['avg_ret']*100:.4f}% {r['sharpe']:<8.2f}")


# ─── Test 2: XAUUSD M5 US中段(16-18)超卖做多 — hold精细扫描 (round2_009) ───

print("\n" + "=" * 70)
print("TEST 2 (round2_009): XAUUSD M5 US中段(16-18)超卖做多 — hold精细扫描")
print("=" * 70)

data2 = load_data("M5", symbols=["XAUUSD"])
for sym, df in data2.items():
    df2 = compute_indicators(df)
    
    # Base condition: US mid-session + RSI<25
    conditions = {
        "US中段(16-18) RSI<25 (base)": "hour >= 16 and hour < 19 and rsi14 < 25",
        "US中段 RSI<25 + 连阴>=2": "hour >= 16 and hour < 19 and rsi14 < 25 and consecutive_bear >= 2",
        "US中段 RSI<25 + 连阴>=3": "hour >= 16 and hour < 19 and rsi14 < 25 and consecutive_bear >= 3",
        "US中段 RSI<20 (更严格)": "hour >= 16 and hour < 19 and rsi14 < 20",
        "US中段 RSI<30 (更宽松)": "hour >= 16 and hour < 19 and rsi14 < 30",
        "US中段(15-18) RSI<25 (提前1h)": "hour >= 15 and hour < 19 and rsi14 < 25",
        "US中段(16-20) RSI<25 (延长1h)": "hour >= 16 and hour < 20 and rsi14 < 25",
    }
    
    hold_periods = [10, 15, 20, 30, 45, 60, 75, 90, 105, 120]
    periods_per_year = PERIODS_PER_YEAR["M5"]
    
    all_results = []
    
    for label, condition in conditions.items():
        mask = df2.eval(condition)
        entry_prices = df2.loc[mask, "close"].values
        entry_indices = df2.index[mask]
        
        if len(entry_prices) < 5:
            print(f"  {label:<45s} n={len(entry_prices)} — 样本不足")
            continue
        
        best_wr = 0
        best_hold = 0
        best_avg = 0
        best_sharpe = 0
        best_n = 0
        
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
            
            if stats["win_rate"] > best_wr and stats["n"] >= 20:
                best_wr = stats["win_rate"]
                best_hold = hold
                best_avg = stats["avg_return"]
                best_sharpe = stats["sharpe_ratio"]
                best_n = stats["n"]
        
        if best_n >= 20:
            all_results.append((label, best_hold, best_wr, best_n, best_avg, best_sharpe))
    
    # Sort by WR descending
    all_results.sort(key=lambda x: -x[2])
    
    print(f"\n{'条件':<45s} {'最佳Hold':<9} {'胜率':<7} {'n':<6} {'平均收益':<10} {'Sharpe':<8}")
    print("-" * 90)
    for label, hold, wr, n, avg, sharpe in all_results:
        marker = ""
        if wr >= 0.70 and n >= 50:
            marker = " ★★★"
        elif wr >= 0.65 and n >= 50:
            marker = " ★★"
        elif wr >= 0.60 and n >= 50:
            marker = " ★"
        print(f"{label:<45s} Hold={hold:<4} {wr*100:.1f}% {n:<6} {avg*100:.4f}% {sharpe:<8.2f}{marker}")

    # Also print full hold spectrum for the base condition
    print("\n--- US中段(16-18) RSI<25 全hold谱 ---")
    print(f"{'Hold':<6} {'胜率':<7} {'n':<6} {'平均收益':<10} {'Sharpe':<8} {'MaxDD':<8}")
    mask = df2.eval("hour >= 16 and hour < 19 and rsi14 < 25")
    entry_prices = df2.loc[mask, "close"].values
    entry_indices = df2.index[mask]
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
        print(f"Hold={hold:<3} {stats['win_rate']*100:.1f}% {stats['n']:<6} {stats['avg_return']*100:.4f}% {stats['sharpe_ratio']:<8.2f} {stats['max_drawdown']:<8.2f}")


# ─── Test 3: Additional exploration — XAUUSD M5 US mid-session SHORT ═══
# Check asymmetry: oversold long vs overbought short in US mid-session

print("\n" + "=" * 70)
print("TEST 3 (bonus): XAUUSD M5 US中段 超买做空 非对称性检查")
print("=" * 70)

for sym, df in data2.items():
    df2 = compute_indicators(df)
    
    cond_short = "hour >= 16 and hour < 19 and rsi14 > 70"
    mask = df2.eval(cond_short)
    entry_prices = df2.loc[mask, "close"].values
    entry_indices = df2.index[mask]
    print(f"US中段超买(RSI>70)信号数: {len(entry_prices)}")
    
    if len(entry_prices) >= 10:
        for hold in [5, 10, 15, 20, 30, 60, 90]:
            returns = []
            for i in range(len(entry_indices)):
                pos = df2.index.get_loc(entry_indices[i])
                exit_pos = pos + hold
                if exit_pos >= len(df2):
                    continue
                exit_price = df2.iloc[exit_pos]["close"]
                ret = (entry_prices[i] - exit_price) / entry_prices[i]  # short
                returns.append(ret)
            returns_arr = np.array(returns, dtype=float)
            stats = _compute_stats(returns_arr, hold, PERIODS_PER_YEAR["M5"])
            print(f"  Hold={hold:<3} WR={stats['win_rate']*100:.1f}% n={stats['n']:<6} avg={stats['avg_return']*100:.4f}% Sharpe={stats['sharpe_ratio']:.2f}")


# ─── Test 4: XAUUSD M1 RSI<20 session细分 (round2_010) ───
print("\n" + "=" * 70)
print("TEST 4 (round2_010): XAUUSD M1 RSI<20 超卖 — session细分")
print("=" * 70)

data_m1 = load_data("M1", symbols=["XAUUSD"])
for sym, df in data_m1.items():
    df2 = compute_indicators(df)
    
    conditions = {
        "全时段 RSI<20 (base)": "rsi14 < 20",
        "亚盘 RSI<20": "session == 'asia' and rsi14 < 20",
        "欧盘 RSI<20": "session == 'europe' and rsi14 < 20",
        "美盘 RSI<20": "session == 'us' and rsi14 < 20",
    }
    
    hold_periods = [1, 2, 3, 5, 10, 15, 20, 30, 60]
    periods_per_year = PERIODS_PER_YEAR["M1"]
    
    print(f"\n{'条件':<35s} {'最佳Hold':<9} {'胜率':<7} {'n':<6} {'平均收益':<10} {'Sharpe':<8}")
    print("-" * 80)
    
    for label, condition in conditions.items():
        mask = df2.eval(condition)
        entry_prices = df2.loc[mask, "close"].values
        entry_indices = df2.index[mask]
        
        if len(entry_prices) < 10:
            print(f"{label:<35s} n={len(entry_prices)} — 样本不足")
            continue
        
        best_wr = 0
        best_hold = 0
        best_avg = 0
        best_sharpe = 0
        best_n = 0
        
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
            
            if stats["win_rate"] > best_wr and stats["n"] >= 20:
                best_wr = stats["win_rate"]
                best_hold = hold
                best_avg = stats["avg_return"]
                best_sharpe = stats["sharpe_ratio"]
                best_n = stats["n"]
        
        marker = ""
        if best_wr >= 0.62 and best_n >= 100:
            marker = " ★★"
        elif best_wr >= 0.60 and best_n >= 100:
            marker = " ★"
        print(f"{label:<35s} Hold={best_hold:<4} {best_wr*100:.1f}% {best_n:<6} {best_avg*100:.4f}% {best_sharpe:<8.2f}{marker}")


# ─── Test 5: JP225 M5 美盘高波动做多 + volume (from round2_008扩展) ───
print("\n" + "=" * 70)
print("TEST 5 (bonus): JP225 M5 美盘高波做多 + atr阈值分档(扩展round2_008)")
print("=" * 70)

data3 = load_data("M5", symbols=["JP225"])
for sym, df in data3.items():
    df2 = compute_indicators(df)
    df2['vol_ma20'] = df2['tick_volume'].rolling(20).mean()
    df2['volume_high'] = df2['tick_volume'] > df2['vol_ma20']
    
    conds = {
        "atr>0.3 (base)": "session == 'us' and atr14_pct > 0.3 and rsi14 > 50",
        "atr>0.3 + vol_high": "session == 'us' and atr14_pct > 0.3 and rsi14 > 50 and volume_high",
        "atr>0.4 (base)": "session == 'us' and atr14_pct > 0.4 and rsi14 > 50",
        "atr>0.4 + vol_high": "session == 'us' and atr14_pct > 0.4 and rsi14 > 50 and volume_high",
    }
    
    hold_periods = [30, 60, 90, 120, 240]
    periods_per_year = PERIODS_PER_YEAR["M5"]
    
    print(f"\n{'条件':<45s} {'最佳Hold':<9} {'胜率':<7} {'n':<6} {'平均收益':<10} {'Sharpe':<8}")
    print("-" * 90)
    
    for label, condition in conds.items():
        mask = df2.eval(condition)
        entry_prices = df2.loc[mask, "close"].values
        entry_indices = df2.index[mask]
        
        if len(entry_prices) < 5:
            print(f"{label:<45s} n={len(entry_prices)} — 样本不足")
            continue
        
        best_wr, best_hold, best_avg, best_sharpe, best_n = 0, 0, 0, 0, 0
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
            if stats["win_rate"] > best_wr and stats["n"] >= 10:
                best_wr = stats["win_rate"]
                best_hold = hold
                best_avg = stats["avg_return"]
                best_sharpe = stats["sharpe_ratio"]
                best_n = stats["n"]
        
        marker = ""
        if best_wr >= 0.65 and best_n >= 50:
            marker = " ★★"
        elif best_wr >= 0.60 and best_n >= 50:
            marker = " ★"
        print(f"{label:<45s} Hold={best_hold:<4} {best_wr*100:.1f}% {best_n:<6} {best_avg*100:.4f}% {best_sharpe:<8.2f}{marker}")


print("\n" + "=" * 70)
print("所有测试完成")
print("=" * 70)
