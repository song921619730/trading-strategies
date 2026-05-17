#!/usr/bin/env python3
"""
Round 46 — M1/M5 Scalping 月度跟踪 + 跨周期验证 + 最终评估

聚焦:
  1. XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第8月)+EU极值继续监控
  2. XAUUSD M5 US RSI<6+CB>=1 跨周期验证(第2月)+n积累
  3. XAGUSD M5 EU RSI<8+CB>=1 跨周期验证(第2月)+最佳CB阈值确认
  4. US500 M5 EU CB>=5+RSI<14 月度跟踪续跑(第6月)+正式纳入确认
  5. XAUUSD M1 ASIA CB>=3+RSI<10 跨周期验证(第4月)+CB>=2版本对比
  6. US30 M1 EU 持续积累+CP3/3季度复审
  7. XAUUSD M5 美盘H15/H19精确定时策略跨周期验证(第2月)
  8. XAGUSD M5 RSI<8 vs RSI<6 性能对比+仓位配置建议
  9. 关闭做空分支—不再执行做空扫描
  10. JP225/US30 M5级别最终评估—考虑移除出M5扫描范围
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
print(f"ROUND 46 — M1/M5 Scalping Focused Scan — {NOW}")
print(f"Target: M1/M5 on XAUUSD XAGUSD JP225 US500 US30")
print("=" * 120)

# =====================================================
# PART 1: XAUUSD M1 第8月跟踪 + EU极值 + 双极值联合
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 1: XAUUSD M1 MONTHLY TRACKING (第8月 US+EU) + ASIA (第4月)")
print("─" * 120)

m1_tracking = [
    # US CB>=3+RSI<10 第8月跟踪
    {"name": "XAU_M1_US_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_US_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU 极值 (续跑, 第8月)
    {"name": "XAU_M1_EU_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # ASIA 第4月跟踪
    {"name": "XAU_M1_ASIA_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "XAU_M1_ASIA_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
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

print("\n📊 M1 Strategies — Best Hold Period per Strategy:\n")
print(f"| {'Strategy':<30} | {'Symbol':<8} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} | {'Chg':<8} |")
print(f"|{':':->30}|{':':->8}|{':':->7}|{':':->6}|{':':->5}|{':':->8}|{':':->7}|{':':->8}|")
for name, results in sorted(all_m1_results.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 5:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            # Compare with round45
            prev_ref = ""
            if "US_CB3" in name: prev_ref = "85.4% r45"
            elif "EU_CB3" in name: prev_ref = "97.2% r45"
            elif "ASIA_CB3" in name: prev_ref = "75.0% r45"
            elif "ASIA_CB2" in name: prev_ref = "73.8% r45"
            elif "DUAL_CB3" in name: prev_ref = "85.7% r45"
            print(f"| {name:<30} | {sym:<8} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<8} | {best['sharpe_ratio']:<7.2f} | {prev_ref:<8} |")

# =====================================================
# PART 2: XAUUSD M5 US RSI<6+CB>=1 跨周期验证(第2月)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 2: XAUUSD M5 US RSI<6 CROSS-VALIDATION (第2月)")
print("─" * 120)

xau_rsi6_cfg = [
    {"name": "XAU_M5_US_RSI6_CB1", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<6 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
    {"name": "XAU_M5_US_RSI6_CB2", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<6 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
    # Also test RSI<8 version for comparison
    {"name": "XAU_M5_US_RSI8_CB1", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<8 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
    {"name": "XAU_M5_US_RSI8_CB2", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
]

xau_rsi6_results = {}
for cfg in xau_rsi6_cfg:
    try:
        res = run_grid(cfg)
        if res:
            xau_rsi6_results[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 XAU M5 US RSI<6/8 Cross-Validation:\n")
print(f"| {'Strategy':<30} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} | {'Prev':<10} |")
print(f"|{':':->30}|{':':->7}|{':':->6}|{':':->5}|{':':->8}|{':':->7}|{':':->10}|")
prev_data = {"XAU_M5_US_RSI6_CB1": "89.3% n=28", "XAU_M5_US_RSI6_CB2": "87.0% n=23"}
for name in sorted(xau_rsi6_results.keys()):
    results = xau_rsi6_results[name]
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 8 else 0)
        if best:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            prev = prev_data.get(name, "N/A")
            print(f"| {name:<30} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<8} | {best['sharpe_ratio']:<7.2f} | {prev:<10} |")

# =====================================================
# PART 3: XAGUSD M5 EU RSI<8+CB>=1 跨周期验证(第2月)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 3: XAGUSD M5 EU RSI<8 CROSS-VALIDATION (第2月) + CB优化")
print("─" * 120)

# Frequency analysis first
xag_data = load_data("M5", ["XAGUSD"])
if xag_data:
    xag_df = compute_indicators(xag_data["XAGUSD"])
    total_candles = len(xag_df)
    
    # RSI<6 vs RSI<8 frequency
    print("\n  RSI<6 vs RSI<8 Frequency Comparison:\n")
    rsi6_total = (xag_df["rsi14"] < 6).sum()
    rsi8_total = (xag_df["rsi14"] < 8).sum()
    rsi10_total = (xag_df["rsi14"] < 10).sum()
    print(f"  RSI<6:  {rsi6_total} signals ({rsi6_total/total_candles*100:.2f}%, ~{total_candles//max(rsi6_total,1)} candles/signal)")
    print(f"  RSI<8:  {rsi8_total} signals ({rsi8_total/total_candles*100:.2f}%, ~{total_candles//max(rsi8_total,1)} candles/signal)")
    print(f"  RSI<10: {rsi10_total} signals ({rsi10_total/total_candles*100:.2f}%, ~{total_candles//max(rsi10_total,1)} candles/signal)")
    print(f"  RSI<8/RSI<6 ratio: {rsi8_total/max(rsi6_total,1):.1f}x")
    print(f"  RSI<10/RSI<6 ratio: {rsi10_total/max(rsi6_total,1):.1f}x")
    
    # Monthly breakdown
    print("\n  Monthly signal count for XAGUSD M5:\n")
    for rsi_thresh, label in [(6, "RSI<6"), (8, "RSI<8"), (10, "RSI<10")]:
        monthly = xag_df[xag_df["rsi14"] < rsi_thresh].resample("ME").size()
        print(f"  {label}: avg={monthly.mean():.1f}/月, std={monthly.std():.1f}/月")
    
    # CB thresholds for RSI<8
    print("\n  XAGUSD M5 RSI<8 + CB threshold scan:\n")
    print(f"| {'CB>=':<6} | {'ALL':<8} | {'Asia':<8} | {'Europe':<8} | {'US':<8} |")
    print(f"|{':':->6}|{':':->8}|{':':->8}|{':':->8}|{':':->8}|")
    for cb in [1, 2, 3, 4, 5]:
        all_sig = ((xag_df["rsi14"] < 8) & (xag_df["consecutive_bear"] >= cb)).sum()
        asia_sig = ((xag_df["rsi14"] < 8) & (xag_df["consecutive_bear"] >= cb) & (xag_df["session"] == "asia")).sum()
        eu_sig = ((xag_df["rsi14"] < 8) & (xag_df["consecutive_bear"] >= cb) & (xag_df["session"] == "europe")).sum()
        us_sig = ((xag_df["rsi14"] < 8) & (xag_df["consecutive_bear"] >= cb) & (xag_df["session"] == "us")).sum()
        print(f"| CB>={cb:<1}   | {all_sig:<8} | {asia_sig:<8} | {eu_sig:<8} | {us_sig:<8} |")

# Grid test for XAG RSI<8
xag_rsi8_cfgs = []
for sess in ["europe", "asia", "us"]:
    for cb in [1, 2, 3, 4, 5]:
        xag_rsi8_cfgs.append({
            "name": f"XAG_M5_RSI8_CB>={cb}_{sess}",
            "symbols": ["XAGUSD"], "timeframe": "M5",
            "entry_condition": f"session=='{sess}' and rsi14<8 and consecutive_bear>={cb}",
            "direction": "long", "hold_periods": [5, 10, 15, 30, 55],
        })

xag_rsi8_results = []
for cfg in xag_rsi8_cfgs:
    try:
        res = run_grid(cfg)
        if res and "XAGUSD" in res:
            for r in res["XAGUSD"]:
                if r["n"] >= 10:
                    xag_rsi8_results.append({
                        "name": cfg["name"], "session": sess, "cb": cb,
                        "hold": r["hold_period"], "wr": r["win_rate"],
                        "n": r["n"], "avg_r": r["avg_return"], "sharpe": r["sharpe_ratio"],
                    })
    except Exception as e:
        pass

xag_rsi8_results.sort(key=lambda x: -x["wr"])
print(f"\nTop 20 XAG M5 RSI<8 Grid (n≥10):\n")
print(f"| {'Rank':<5} | {'Name':<30} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{':':->5}|{':':->30}|{':':->7}|{':':->6}|{':':->5}|{':':->8}|{':':->7}|")
for i, r in enumerate(xag_rsi8_results[:20], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | {r['name']:<30} | {wr:<7} | {r['n']:<6} | {r['hold']:<5} | {ar:<8} | {r['sharpe']:<7.2f} |")

# =====================================================
# PART 4: US500 M5 EU CB>=5+RSI<14 第6月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 4: US500 M5 EU CB>=5+RSI<14 MONTHLY TRACKING (第6月)")
print("─" * 120)

us500_tracking = [
    {"name": "US500_EU_CB5_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 25, 40]},
    {"name": "US500_EU_CB4_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 25, 40]},
    {"name": "US500_EU_CB6_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=6",
     "direction": "long", "hold_periods": [5, 10, 15, 25, 40]},
]

us500_results = {}
for cfg in us500_tracking:
    try:
        res = run_grid(cfg)
        if res:
            us500_results[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 US500 M5 EU Tracking Results:\n")
print(f"| {'Strategy':<25} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} | {'Prev':<10} |")
print(f"|{':':->25}|{':':->7}|{':':->6}|{':':->5}|{':':->8}|{':':->7}|{':':->10}|")
prev_us500 = {"US500_EU_CB5_RSI14": "84.6% n=52", "US500_EU_CB4_RSI14": "78.1% n=73"}
for name in sorted(us500_results.keys()):
    results = us500_results[name]
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            prev = prev_us500.get(name, "N/A")
            print(f"| {name:<25} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<8} | {best['sharpe_ratio']:<7.2f} | {prev:<10} |")

# =====================================================
# PART 5: US30 M1 EU 持续积累 + CP3/3季度复审
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 5: US30 M1 EU ACCUMULATION + CP3/3 QUARTERLY REVIEW")
print("─" * 120)

us30_m1_cfgs = [
    {"name": "US30_M1_EU_CB4_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "US30_M1_EU_CB3_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "US30_M1_US_CB4_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "US30_M1_EU_CB5_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
]

us30_m1_results = {}
for cfg in us30_m1_cfgs:
    try:
        res = run_grid(cfg)
        if res:
            us30_m1_results[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 US30 M1 Results:\n")
print(f"| {'Strategy':<28} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} | {'Status':<10} |")
print(f"|{':':->28}|{':':->7}|{':':->6}|{':':->5}|{':':->8}|{':':->7}|{':':->10}|")
for name in sorted(us30_m1_results.keys()):
    results = us30_m1_results[name]
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            cp3_pass = "✅ CP3/3" if (best['win_rate'] >= 0.70 and best['n'] >= 10) else "⏳ accumulating"
            print(f"| {name:<28} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<8} | {best['sharpe_ratio']:<7.2f} | {cp3_pass:<10} |")

# =====================================================
# PART 6: XAUUSD M5 美盘H15/H19精确定时 第2月跨周期验证
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 6: XAUUSD M5 US HOUR TIMED STRATEGY CROSS-VALIDATION (第2月)")
print("─" * 120)

# Focus specifically on H15 and H19 which were best in round45
us_timed_cfgs = [
    # H15 variants
    {"name": "XAU_M5_H15_CB1_RSI10", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==15 and rsi14<10 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_H15_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==15 and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_H15_CB1_RSI8", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==15 and rsi14<8 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # H19 variants
    {"name": "XAU_M5_H19_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==19 and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_H19_CB5_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==19 and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_H19_CB3_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==19 and rsi14<12 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # H16, H20 for broader scan
    {"name": "XAU_M5_H16_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==16 and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_H20_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==20 and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
]

us_timed_results = {}
for cfg in us_timed_cfgs:
    try:
        res = run_grid(cfg)
        if res:
            us_timed_results[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 XAU M5 US Hour Timed Cross-Validation:\n")
print(f"| {'Strategy':<28} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} | {'Prev':<10} |")
print(f"|{':':->28}|{':':->7}|{':':->6}|{':':->5}|{':':->8}|{':':->7}|{':':->10}|")
prev_timed = {"XAU_M5_H15_CB1_RSI10": "91.7% n=12", "XAU_M5_H19_CB4_RSI12": "90.9% n=11",
              "XAU_M5_H19_CB5_RSI12": "100% n=8"}
for name in sorted(us_timed_results.keys()):
    results = us_timed_results[name]
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 8 else 0)
        if best and best["n"] >= 5:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            prev = prev_timed.get(name, "N/A")
            print(f"| {name:<28} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<8} | {best['sharpe_ratio']:<7.2f} | {prev:<10} |")

# =====================================================
# PART 7: XAGUSD M5 RSI<8 vs RSI<6 性能对比+仓位配置建议
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 7: XAGUSD M5 RSI<8 vs RSI<6 PERFORMANCE COMPARISON")
print("─" * 120)

xag_compare_cfgs = [
    # RSI<6 variants (all sessions)
    {"name": "XAG_M5_RSI6_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<6 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
    {"name": "XAG_M5_RSI6_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<6 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
    # RSI<8 variants (all sessions)
    {"name": "XAG_M5_RSI8_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<8 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
    {"name": "XAG_M5_RSI8_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
    {"name": "XAG_M5_RSI8_CB3_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<8 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
    # RSI<10 variants (all sessions)
    {"name": "XAG_M5_RSI10_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<10 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
    {"name": "XAG_M5_RSI10_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
]

xag_compare_results = {}
for cfg in xag_compare_cfgs:
    try:
        res = run_grid(cfg)
        if res:
            xag_compare_results[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 XAGUSD M5 RSI<6 vs RSI<8 vs RSI<10 Performance:\n")
print(f"| {'Strategy':<28} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} | {'$/month':<8} |")
print(f"|{':':->28}|{':':->7}|{':':->6}|{':':->5}|{':':->8}|{':':->7}|{':':->8}|")
# Estimate signals/month from total data
xag_total_months = total_candles / (12 * 24 * 30) if 'total_candles' in dir() else 17  # ~17 months of M5 data
for name in sorted(xag_compare_results.keys()):
    results = xag_compare_results[name]
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            # Estimate signals/month
            est_months = total_candles / (12 * 24 * 30)
            sigs_per_month = best['n'] / est_months if est_months > 0 else 0
            print(f"| {name:<28} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<8} | {best['sharpe_ratio']:<7.2f} | {sigs_per_month:<8.1f} |")

# =====================================================
# PART 8: JP225/US30 M5最终评估
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 8: JP225/US30 M5 FINAL EVALUATION — 考虑移除出M5扫描范围")
print("─" * 120)

# JP225 M5 scan
jp_m5_cfgs = []
for sess in ["asia", "europe", "us"]:
    for cb in [2, 3, 4, 5]:
        for rsi in [10, 12, 14, 18, 20]:
            jp_m5_cfgs.append({
                "name": f"JP225_M5_{sess}_CB>={cb}_RSI<{rsi}",
                "symbols": ["JP225"], "timeframe": "M5",
                "entry_condition": f"session=='{sess}' and rsi14<{rsi} and consecutive_bear>={cb}",
                "direction": "long", "hold_periods": [5, 10, 20, 45],
            })

# US30 M5 scan
us30_m5_cfgs = []
for sess in ["europe", "us"]:
    for cb in [2, 3, 4, 5]:
        for rsi in [10, 12, 14, 18]:
            us30_m5_cfgs.append({
                "name": f"US30_M5_{sess}_CB>={cb}_RSI<{rsi}",
                "symbols": ["US30"], "timeframe": "M5",
                "entry_condition": f"session=='{sess}' and rsi14<{rsi} and consecutive_bear>={cb}",
                "direction": "long", "hold_periods": [5, 10, 20, 30, 55],
            })

# Run JP225
jp_m5_raw = []
for cfg in jp_m5_cfgs:
    try:
        res = run_grid(cfg)
        if res and "JP225" in res:
            for r in res["JP225"]:
                if r["n"] >= 10:
                    jp_m5_raw.append({"name": cfg["name"], "wr": r["win_rate"],
                                       "n": r["n"], "hold": r["hold_period"],
                                       "avg_r": r["avg_return"], "sharpe": r["sharpe_ratio"]})
    except Exception as e:
        pass

jp_m5_raw.sort(key=lambda x: -x["wr"])
print(f"\n📊 JP225 M5 — Best results (n≥10):\n")
print(f"| {'Rank':<5} | {'Name':<32} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{':':->5}|{':':->32}|{':':->7}|{':':->6}|{':':->5}|{':':->8}|{':':->7}|")
for i, r in enumerate(jp_m5_raw[:15], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | {r['name']:<32} | {wr:<7} | {r['n']:<6} | {r['hold']:<5} | {ar:<8} | {r['sharpe']:<7.2f} |")

# Assess removal
jp_best_wr = max([r["wr"] for r in jp_m5_raw], default=0)
jp_best_n = max([r["n"] for r in jp_m5_raw if r["wr"] == jp_best_wr], default=0) if jp_m5_raw else 0
print(f"\n  JP225 M5 Best WR: {jp_best_wr*100:.1f}% (n={jp_best_n})")
if jp_best_wr < 0.65:
    print("  ✅ 确认: JP225 M5 全线WR<65% — 建议从M5扫描范围移除")
else:
    print(f"  ⚠️ JP225 M5 发现WR≥65%策略, 需进一步评估")

# Run US30 M5
us30_m5_raw = []
for cfg in us30_m5_cfgs:
    try:
        res = run_grid(cfg)
        if res and "US30" in res:
            for r in res["US30"]:
                if r["n"] >= 10:
                    us30_m5_raw.append({"name": cfg["name"], "wr": r["win_rate"],
                                        "n": r["n"], "hold": r["hold_period"],
                                        "avg_r": r["avg_return"], "sharpe": r["sharpe_ratio"]})
    except Exception as e:
        pass

us30_m5_raw.sort(key=lambda x: -x["wr"])
print(f"\n📊 US30 M5 — Best results (n≥10):\n")
print(f"| {'Rank':<5} | {'Name':<32} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{':':->5}|{':':->32}|{':':->7}|{':':->6}|{':':->5}|{':':->8}|{':':->7}|")
for i, r in enumerate(us30_m5_raw[:15], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | {r['name']:<32} | {wr:<7} | {r['n']:<6} | {r['hold']:<5} | {ar:<8} | {r['sharpe']:<7.2f} |")

us30_m5_best_wr = max([r["wr"] for r in us30_m5_raw], default=0)
print(f"\n  US30 M5 Best WR: {us30_m5_best_wr*100:.1f}%")
if us30_m5_best_wr < 0.65:
    print("  ✅ 确认: US30 M5 全线WR<65% — 建议从M5扫描范围移除")
else:
    print(f"  ⚠️ US30 M5 发现WR≥65%策略, 需进一步评估")

# =====================================================
# PART 9: 做空确认 — 保持关闭
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 9: SHORT STRATEGY — 已关闭, 不再扫描")
print("─" * 120)
print("  做空分支已于Round 45正式关闭。所有M1/M5做空策略WR<65%。")
print("  本轮跳过做空扫描。")

# =====================================================
# SUMMARY
# =====================================================
print("\n" + "=" * 120)
print("📋 ROUND 46 SUMMARY — Key Findings")
print("=" * 120)

# Collect top findings
all_findings = []

# From M1 tracking
for name, results in all_m1_results.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"])
        if best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append({
                "symbol": sym, "name": name, "hold": best["hold_period"],
                "wr": best["win_rate"], "n": best["n"], "avg_r": best["avg_return"],
            })

# From RSI6 cross-val
for name, results in xau_rsi6_results.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 8 else 0)
        if best and best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append({
                "symbol": sym, "name": name, "hold": best["hold_period"],
                "wr": best["win_rate"], "n": best["n"], "avg_r": best["avg_return"],
            })

# From US500 tracking
for name, results in us500_results.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append({
                "symbol": sym, "name": name, "hold": best["hold_period"],
                "wr": best["win_rate"], "n": best["n"], "avg_r": best["avg_return"],
            })

# From XAG compare
for name, results in xag_compare_results.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append({
                "symbol": sym, "name": name, "hold": best["hold_period"],
                "wr": best["win_rate"], "n": best["n"], "avg_r": best["avg_return"],
            })

# From XAG RSI8 grid
for r in xag_rsi8_results:
    if r["wr"] >= 0.75 and r["n"] >= 15:
        all_findings.append(r)

# From US timed
for name, results in us_timed_results.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 8 else 0)
        if best and best["n"] >= 8 and best["win_rate"] >= 0.70:
            all_findings.append({
                "symbol": sym, "name": name, "hold": best["hold_period"],
                "wr": best["win_rate"], "n": best["n"], "avg_r": best["avg_return"],
            })

# From US30 M1
for name, results in us30_m1_results.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append({
                "symbol": sym, "name": name, "hold": best["hold_period"],
                "wr": best["win_rate"], "n": best["n"], "avg_r": best["avg_return"],
            })

all_findings.sort(key=lambda x: -x["wr"])
print(f"\nTop Confirmable Findings (WR≥75% n≥20, or WR≥70% n≥10): {len(all_findings)}\n")
print(f"| {'Rank':<5} | {'Symbol/Name':<35} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} |")
print(f"|{':':->5}|{':':->35}|{':':->7}|{':':->6}|{':':->5}|{':':->8}|")
for i, r in enumerate(all_findings[:25], 1):
    sym = r.get("name", r.get("symbol", "?"))
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%" if "avg_r" in r else "-"
    n = r.get("n", 0)
    h = r.get("hold", 0)
    print(f"| {i:<5} | {sym:<35} | {wr:<7} | {n:<6} | {h:<5} | {ar:<8} |")

print("\n" + "=" * 120)
print(f"✅ ROUND 46 COMPLETE — {NOW}")
print("=" * 120)
