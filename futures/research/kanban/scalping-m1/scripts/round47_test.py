#!/usr/bin/env python3
"""
Round 47 — M1/M5 Scalping 季度复审 + 跨周期验证(第3月) + 仓位配置

聚焦:
  1. XAUUSD M1 US CB>=3+RSI<10 季度复审(第9月)+EU极值成熟标签确认
  2. XAUUSD M5 US RSI<6+CB>=1 跨周期验证(第3月)+n积累目标n≥35
  3. XAGUSD M5 EU RSI<8+CB>=1 跨周期验证(第3月)+仓位配置验证
  4. US500 M5 EU CB>=5+RSI<14 月度跟踪(第7月)+CB>=6版本对比监控
  5. XAUUSD M1 ASIA 第5月跟踪+大hold测试(hold=30/55)
  6. US30 M1 EU CB>=4 vs CB>=5 对比+hold=10/20验证CB>=5稳定性
  7. XAUUSD M5 美盘H15/H19精确定时第3月跟踪+n积累
  8. XAGUSD M5 仓位配置模拟: RSI<6(大仓位) vs RSI<8 EU(常规) vs RSI<8 ALL(轻仓)
  9. US30 M5从扫描范围移除确认
  10. JP225 M5权重下调+仅保留US session监控
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grid_engine import run_grid
from data_loader import load_data, compute_indicators, list_available_symbols
import pandas as pd
import numpy as np
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

TARGET_M5 = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]
TARGET_M1 = ["XAUUSD", "XAGUSD", "US30"]

print("=" * 120)
print(f"ROUND 47 — M1/M5 Scalping 季度复审 + 跨周期验证(第3月) — {NOW}")
print(f"Target: M1/M5 on XAUUSD XAGUSD JP225 US500 US30")
print("=" * 120)

# =====================================================
# HELPER: print results in a clean table
# =====================================================
def print_strategy_table(name_map, results_dict):
    """Print results for a named strategy dictionary."""
    print(f"\n| {'Strategy':<30} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Prev/Ref':<15} |")
    print(f"|{':':->30}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->15}|")
    for name, (symbols_list, cfg_entry, cfg_dir, hold_periods, prev_ref) in name_map.items():
        if name not in results_dict:
            continue
        sym_res = results_dict[name]
        for sym, sym_results in sym_res.items():
            best = max(sym_results, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
            if best and best["n"] >= 3:
                wr = f"{best['win_rate']*100:.1f}%"
                ar = f"{best['avg_return']*100:.3f}%"
                print(f"| {name:<30} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {prev_ref:<15} |")


# =====================================================
# PART 1: XAUUSD M1 季度复审(第9月)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 1: XAUUSD M1 季度复审(第9月) — US/EU/ASIA/双极值")
print("─" * 120)

m1_tracking = [
    # US 第9月
    {"name": "XAU_M1_US_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_US_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU 极值 第9月
    {"name": "XAU_M1_EU_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU 宽松版本 CB>=2
    {"name": "XAU_M1_EU_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # ASIA 第5月跟踪
    {"name": "XAU_M1_ASIA_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
    {"name": "XAU_M1_ASIA_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
    # 双极值联合
    {"name": "XAU_M1_DUAL_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "(session=='europe' or session=='us') and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
]

all_m1_results = {}
for cfg in m1_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_m1_results[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 M1 第9月跟踪 — 最佳Hold Period:\n")
print(f"| {'Strategy':<30} | {'Symbol':<8} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Chg':<15} |")
print(f"|{':':->30}|{':':->8}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->15}|")
prev_refs_m1 = {
    "XAU_M1_US_CB3_RSI10": "85.4% r46",
    "XAU_M1_US_CB2_RSI10": "81.0% r46",
    "XAU_M1_EU_CB3_RSI10": "97.2% r46",
    "XAU_M1_EU_CB2_RSI10": "—",
    "XAU_M1_ASIA_CB3_RSI10": "75.0% r46",
    "XAU_M1_ASIA_CB2_RSI10": "73.8% r46",
    "XAU_M1_DUAL_CB3_RSI10": "85.7% r46",
}
for name, results in sorted(all_m1_results.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
        if best and best["n"] >= 3:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            prev = prev_refs_m1.get(name, "")
            print(f"| {name:<30} | {sym:<8} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {prev:<15} |")

# =====================================================
# PART 2: XAUUSD M5 US RSI<6+CB>=1 第3月跨周期验证
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 2: XAUUSD M5 US RSI<6/8 第3月跨周期验证")
print("─" * 120)

xau_m5_tracking = [
    {"name": "XAU_M5_US_RSI6_CB1", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<6 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_US_RSI6_CB2", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<6 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_US_RSI8_CB1", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<8 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_US_RSI8_CB2", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # 宽松版 CB>=3
    {"name": "XAU_M5_US_RSI6_CB3", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<6 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
]

all_xau_m5 = {}
for cfg in xau_m5_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_xau_m5[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 XAU M5 US RSI<6/8 第3月跨周期验证:\n")
print(f"| {'Strategy':<30} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Prev':<15} |")
print(f"|{':':->30}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->15}|")
prev_refs_xau_m5 = {
    "XAU_M5_US_RSI6_CB1": "89.3% n=28",
    "XAU_M5_US_RSI6_CB2": "87.0% n=23",
    "XAU_M5_US_RSI8_CB1": "72.1% n=61",
    "XAU_M5_US_RSI8_CB2": "70.0% n=50",
    "XAU_M5_US_RSI6_CB3": "—",
}
for name, results in sorted(all_xau_m5.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
        if best and best["n"] >= 3:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            prev = prev_refs_xau_m5.get(name, "")
            print(f"| {name:<30} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {prev:<15} |")

# =====================================================
# PART 3: XAGUSD M5 EU RSI<8 第3月跨周期验证
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 3: XAGUSD M5 EU RSI<8 第3月跨周期验证 + 仓位配置")
print("─" * 120)

xag_m5_tracking = [
    {"name": "XAG_M5_EU_RSI8_CB1", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_EU_RSI8_CB2", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_EU_RSI8_CB3", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_EU_RSI8_CB4", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_EU_RSI8_CB5", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # 仓位配置对比: RSI<6 ALL
    {"name": "XAG_M5_RSI6_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<6 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI6_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<6 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # RSI<8 ALL
    {"name": "XAG_M5_RSI8_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<8 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI8_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI8_CB3_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<8 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
]

all_xag_m5 = {}
for cfg in xag_m5_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_xag_m5[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 XAG M5 EU RSI<8 第3月跨周期验证:\n")
print(f"| {'Strategy':<30} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Prev':<15} |")
print(f"|{':':->30}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->15}|")
prev_refs_xag = {
    "XAG_M5_EU_RSI8_CB1": "90.3% n=31",
    "XAG_M5_EU_RSI8_CB2": "89.3% n=28",
    "XAG_M5_EU_RSI8_CB3": "88.0% n=25",
    "XAG_M5_EU_RSI8_CB4": "90.9% n=22",
    "XAG_M5_EU_RSI8_CB5": "94.7% n=19",
    "XAG_M5_RSI6_CB1_ALL": "86.0% n=93",
    "XAG_M5_RSI6_CB2_ALL": "85.9% n=78",
    "XAG_M5_RSI8_CB1_ALL": "75.6% n=164",
    "XAG_M5_RSI8_CB2_ALL": "75.2% n=141",
    "XAG_M5_RSI8_CB3_ALL": "72.0% n=118",
}
for name, results in sorted(all_xag_m5.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
        if best and best["n"] >= 3:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            prev = prev_refs_xag.get(name, "")
            print(f"| {name:<30} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {prev:<15} |")

# =====================================================
# PART 4: US500 M5 EU CB>=5+RSI<14 第7月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 4: US500 M5 EU 第7月跟踪 + CB>=6版本对比")
print("─" * 120)

us500_tracking = [
    {"name": "US500_EU_CB4_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    {"name": "US500_EU_CB5_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    {"name": "US500_EU_CB6_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=6",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    {"name": "US500_EU_CB5_RSI12", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    {"name": "US500_EU_CB5_RSI10", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
]

all_us500 = {}
for cfg in us500_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_us500[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 US500 M5 EU 第7月跟踪:\n")
print(f"| {'Strategy':<25} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Prev':<15} |")
print(f"|{':':->25}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->15}|")
prev_refs_us500 = {
    "US500_EU_CB4_RSI14": "78.1% n=73",
    "US500_EU_CB5_RSI14": "84.6% n=52",
    "US500_EU_CB6_RSI14": "85.7% n=35",
    "US500_EU_CB5_RSI12": "—",
    "US500_EU_CB5_RSI10": "—",
}
for name, results in sorted(all_us500.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
        if best and best["n"] >= 3:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            prev = prev_refs_us500.get(name, "")
            print(f"| {name:<25} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {prev:<15} |")

# =====================================================
# PART 5: US30 M1 EU 积累验证
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 5: US30 M1 EU CB对比+hold验证")
print("─" * 120)

us30_tracking = [
    {"name": "US30_M1_EU_CB3_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "US30_M1_EU_CB4_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "US30_M1_EU_CB5_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # US30 M1 US session
    {"name": "US30_M1_US_CB4_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
]

all_us30 = {}
for cfg in us30_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_us30[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 US30 M1 结果:\n")
print(f"| {'Strategy':<25} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Status':<12} |")
print(f"|{':':->25}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->12}|")
prev_refs_us30 = {
    "US30_M1_EU_CB3_RSI14": "65.1% r46",
    "US30_M1_EU_CB4_RSI14": "70.4% r46 ✅",
    "US30_M1_EU_CB5_RSI14": "73.2% r46 ✅",
    "US30_M1_US_CB4_RSI14": "52.1% r46",
}
for name, results in sorted(all_us30.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
        if best and best["n"] >= 3:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            status = "✅ CP3/3" if best["win_rate"] >= 0.70 and best["n"] >= 30 else "⏳ accumulating"
            print(f"| {name:<25} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {status:<12} |")

# =====================================================
# PART 6: XAUUSD M5 美盘H15/H19精确定时第3月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 6: XAUUSD M5 美盘H15/H19精确定时第3月跟踪")
print("─" * 120)

xau_hour_tracking = [
    # H15 (US开盘)
    {"name": "XAU_M5_H15_CB1_RSI10", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==15 and rsi14<10 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_H15_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==15 and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # H19 (美盘盘中)
    {"name": "XAU_M5_H19_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==19 and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_H19_CB5_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==19 and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_H19_CB3_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==19 and rsi14<12 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
]

all_xau_hour = {}
for cfg in xau_hour_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_xau_hour[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 XAU M5 美盘H精确定时第3月:\n")
print(f"| {'Strategy':<30} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Prev':<15} |")
print(f"|{':':->30}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->15}|")
prev_refs_xau_hour = {
    "XAU_M5_H15_CB1_RSI10": "91.7% n=12",
    "XAU_M5_H15_CB2_RSI10": "90.9% n=11",
    "XAU_M5_H19_CB4_RSI12": "90.9% n=11",
    "XAU_M5_H19_CB5_RSI12": "100% n=8",
    "XAU_M5_H19_CB3_RSI12": "80.0% n=15",
}
for name, results in sorted(all_xau_hour.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 3 else 0)
        if best and best["n"] >= 2:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            prev = prev_refs_xau_hour.get(name, "")
            print(f"| {name:<30} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {prev:<15} |")

# =====================================================
# PART 7: XAGUSD M5 仓位配置模拟
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 7: XAGUSD M5 仓位配置模拟 — 月信号频率")
print("─" * 120)

# Load data for frequency analysis
try:
    xag_data = load_data(timeframe="M5", symbols=["XAGUSD"])
    if xag_data and "XAGUSD" in xag_data:
        df = compute_indicators(xag_data["XAGUSD"])
        
        # Count signals for each condition
        configs = {
            "RSI<6": "rsi14<6",
            "RSI<8": "rsi14<8",
            "RSI<10": "rsi14<10",
        }
        
        print("\n📊 XAGUSD M5 信号频率对比:\n")
        print(f"| {'条件':<15} | {'信号总数':<10} | {'信号率':<10} | {'月均':<10} | {'每信号间距':<12} |")
        print(f"|{':':->15}|{':':->10}|{':':->10}|{':':->10}|{':':->12}|")
        
        for label, cond in configs.items():
            mask = df.eval(cond)
            n_signals = mask.sum()
            total_candles = len(df)
            freq_pct = n_signals / total_candles * 100 if total_candles > 0 else 0
            
            # Approximate monthly: ~7200 M5 candles/month (6/day * 5 days * 52 weeks / 12 months ≈ 7200)
            months = total_candles / 7200
            per_month = n_signals / months if months > 0 else 0
            
            print(f"| {label:<15} | {n_signals:<10} | {freq_pct:<9.2f}% | {per_month:<9.1f} | 1/{total_candles//max(n_signals,1):>4} candles |")
        
        # Session breakdown for RSI<8
        print("\n📊 XAGUSD M5 RSI<8 Session频率:\n")
        for sess in ["asia", "europe", "us"]:
            mask = df.eval(f"session=='{sess}' and rsi14<8")
            n = mask.sum()
            total_sess = (df["session"] == sess).sum()
            pct = n / total_sess * 100 if total_sess > 0 else 0
            per_month = n / months if months > 0 else 0
            print(f"  {sess:<10}: {n:>5} signals ({pct:.2f}% of session, ~{per_month:.1f}/月)")
except Exception as e:
    print(f"  ⚠ XAGUSD 频率分析失败: {e}")

# =====================================================
# PART 8: JP225 M5 US session 权重下调监控
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 8: JP225 M5 US session 监控（权重下调）")
print("─" * 120)

jp225_tracking = [
    {"name": "JP225_M5_US_CB3_RSI10", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 45]},
    {"name": "JP225_M5_US_CB5_RSI12", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 45]},
    {"name": "JP225_M5_US_CB4_RSI10", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 45]},
    {"name": "JP225_M5_US_CB5_RSI14", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<14 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 45]},
]

all_jp225 = {}
for cfg in jp225_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_jp225[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 JP225 M5 US session 监控:\n")
print(f"| {'Strategy':<25} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Verdict':<12} |")
print(f"|{':':->25}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->12}|")
for name, results in sorted(all_jp225.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 5:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            verdict = "✅推荐" if best["win_rate"] >= 0.70 and best["sharpe_ratio"] >= 15 else ("⚠️边界" if best["win_rate"] >= 0.65 else "❌不推荐")
            print(f"| {name:<25} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {verdict:<12} |")

# =====================================================
# PART 9: US30 M5 移除确认扫描
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 9: US30 M5 移除确认 — 快速验证")
print("─" * 120)

us30_m5_tracking = [
    {"name": "US30_M5_EU_CB5_RSI10", "symbols": ["US30"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
    {"name": "US30_M5_US_CB5_RSI12", "symbols": ["US30"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
    {"name": "US30_M5_EU_CB5_RSI12", "symbols": ["US30"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
]

all_us30_m5 = {}
for cfg in us30_m5_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_us30_m5[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 US30 M5 快速验证 — 是否全线<65%:\n")
print(f"| {'Strategy':<25} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Status':<12} |")
print(f"|{':':->25}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->12}|")
us30_m5_best_wr = 0
for name, results in sorted(all_us30_m5.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
        if best and best["n"] >= 3:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            us30_m5_best_wr = max(us30_m5_best_wr, best["win_rate"])
            status = "✅<65% 确认移除" if best["win_rate"] < 0.65 else "⚠️≥65% 需重新评估"
            print(f"| {name:<25} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {status:<12} |")

print(f"\n  US30 M5 最高WR: {us30_m5_best_wr*100:.1f}%")
if us30_m5_best_wr < 0.65:
    print("  ✅ 确认: US30 M5 全线WR<65% — 从M5扫描范围移除")
else:
    print("  ⚠️ 发现WR≥65%策略,需重新评估移除决定")

# =====================================================
# SUMMARY
# =====================================================
print("\n" + "=" * 120)
print(f"📋 ROUND 47 SUMMARY — 季度复审 + 跨周期验证(第3月)")
print("=" * 120)

# Collect all top findings
all_findings = []

for name, results in sorted(all_m1_results.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append((name, sym, best))

for name, results in sorted(all_xau_m5.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append((name, sym, best))

for name, results in sorted(all_xag_m5.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append((name, sym, best))

for name, results in sorted(all_us500.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append((name, sym, best))

for name, results in sorted(all_us30.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 20 and best["win_rate"] >= 0.65:
            all_findings.append((name, sym, best))

for name, results in sorted(all_xau_hour.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
        if best and best["n"] >= 5 and best["win_rate"] >= 0.70:
            all_findings.append((name, sym, best))

# Sort by WR descending
all_findings.sort(key=lambda x: -x[2]["win_rate"])

print(f"\nTop Findings (WR≥70% n≥10, or WR≥70% n≥5 for timed): {len(all_findings)}\n")
print(f"| {'Rank':<5} | {'Name':<30} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<8} |")
print(f"|{'':->5}|{'':->30}|{'':->7}|{'':->6}|{'':->5}|{'':->10}|{'':->8}|")
for i, (name, sym, best) in enumerate(all_findings, 1):
    wr = f"{best['win_rate']*100:.1f}%"
    ar = f"{best['avg_return']*100:.3f}%"
    print(f"| {i:<5} | {name:<30} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<8.2f} |")

print(f"\n{'='*120}")
print(f"✅ ROUND 47 COMPLETE — {NOW}")
print(f"{'='*120}")
