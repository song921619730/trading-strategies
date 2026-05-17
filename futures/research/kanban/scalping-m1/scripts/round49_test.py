#!/usr/bin/env python3
"""
Round 49 — M1/M5 Scalping 月度跟踪(第11/9/7月) + 跨周期验证(第5月) + 新策略独立跟踪(第1-2月)

聚焦:
  1. XAUUSD M1 US/EU 第11月跟踪 + EU_CB2第3月跟踪 + EU_RSI8新策略独立跟踪(第1月)
  2. XAUUSD M5 US RSI<6+CB>=1 继续监控n增长(第5次检查)
  3. XAGUSD M5 EU RSI<8+CB>=1 第5月验证 + RSI<5新策略独立跟踪(第2月)
  4. US500 M5 EU CB>=5+RSI<14 第9月跟踪
  5. XAUUSD M1 ASIA 第7月跟踪 + CB4版持续跟踪
  6. US30 M1 EU CB4+RSI<12新策略第2月验证
  7. XAUUSD M5 H15/H19精确定时第5月跟踪
  8. XAGUSD M5 RSI<5 CB1 ALL新策略第2月验证
  9. JP225 M5 最低权重监控
  10. 新探索: EU CB3+RSI<8 n积累 + US30 M1 RSI<12深入 + 数据更新验证 + XAU M5 US RSI<5
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

print("=" * 120)
print(f"ROUND 49 — M1/M5 Scalping 月度跟踪(第11/9/7月) + 跨周期验证(第5月) — {NOW}")
print(f"Target: M1/M5 on XAUUSD XAGUSD JP225 US500 US30")
print("=" * 120)

# =====================================================
# HELPER
# =====================================================
def print_best_table(name_results_map, prev_refs=None, min_n=3):
    """Print best hold-period result per strategy."""
    print(f"| {'Strategy':<30} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Ref':<15} |")
    print(f"|{':':->30}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->15}|")
    for name in sorted(name_results_map.keys()):
        results = name_results_map[name]
        for sym, sym_res in results.items():
            best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= min_n else 0)
            if best and best["n"] >= min_n:
                wr = f"{best['win_rate']*100:.1f}%"
                ar = f"{best['avg_return']*100:.3f}%"
                prev = prev_refs.get(name, "") if prev_refs else ""
                print(f"| {name:<30} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {prev:<15} |")

def collect_best(name_results_map, min_n=10, min_wr=0.70):
    """Collect top findings across all tested strategies."""
    findings = []
    for name, results in name_results_map.items():
        for sym, sym_res in results.items():
            best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= min_n else 0)
            if best and best["n"] >= min_n and best["win_rate"] >= min_wr:
                findings.append((name, sym, best))
    return sorted(findings, key=lambda x: -x[2]["win_rate"])


# =====================================================
# PART 1: XAUUSD M1 第11月跟踪 — US/EU/双极值 + EU_CB2第3月 + EU_RSI8第1月
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 1: XAUUSD M1 第11月跟踪 — US/EU/双极值 + EU_CB2(第3月) + EU_RSI8(第1月)")
print("─" * 120)

m1_tracking = [
    # US 第11月
    {"name": "XAU_M1_US_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_US_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU 第11月
    {"name": "XAU_M1_EU_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU_CB2 宽松版 — 第3月独立跟踪
    {"name": "XAU_M1_EU_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # 双极值联合
    {"name": "XAU_M1_DUAL_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "(session=='europe' or session=='us') and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU_RSI8 — 第1月独立跟踪
    {"name": "XAU_M1_EU_CB3_RSI8", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_EU_CB2_RSI8", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU CB2+RSI5 极端积累追踪
    {"name": "XAU_M1_EU_CB2_RSI5", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<5 and consecutive_bear>=2",
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

prev_refs_m1 = {
    "XAU_M1_US_CB3_RSI10": "85.4% r48",
    "XAU_M1_US_CB2_RSI10": "81.0% r48",
    "XAU_M1_EU_CB3_RSI10": "97.2% r48",
    "XAU_M1_EU_CB2_RSI10": "93.2% r48",
    "XAU_M1_DUAL_CB3_RSI10": "85.7% r48",
    "XAU_M1_EU_CB3_RSI8": "100.0% r48",
    "XAU_M1_EU_CB2_RSI8": "93.1% r48",
    "XAU_M1_EU_CB2_RSI5": "100.0% n=15",
}
print("\n📊 M1 第11月跟踪 (best hold):")
print_best_table(all_m1_results, prev_refs_m1)


# =====================================================
# PART 2: XAUUSD M5 US RSI<6 第5次监控(含n增长检查)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 2: XAUUSD M5 US RSI<6 第5次监控 — 标记数据冻结风险")
print("─" * 120)

xau_m5_tracking = [
    {"name": "XAU_M5_US_RSI6_CB1", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<6 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_US_RSI6_CB2", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<6 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_US_RSI6_CB3", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<6 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_US_RSI8_CB1", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<8 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # RSI<5 积累追踪
    {"name": "XAU_M5_US_RSI5_CB1", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<5 and consecutive_bear>=1",
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

prev_refs_xau_m5 = {
    "XAU_M5_US_RSI6_CB1": "89.3% n=28",
    "XAU_M5_US_RSI6_CB2": "87.0% n=23",
    "XAU_M5_US_RSI6_CB3": "84.2% n=19",
    "XAU_M5_US_RSI8_CB1": "72.1% n=61",
    "XAU_M5_US_RSI5_CB1": "90.5% n=21",
}
print("\n📊 XAU M5 US RSI<6 第5次监控:")
print_best_table(all_xau_m5, prev_refs_xau_m5)

# Check n-growth for RSI6 CB1 — 第5次检查
if "XAU_M5_US_RSI6_CB1" in all_xau_m5:
    for sym, res_list in all_xau_m5["XAU_M5_US_RSI6_CB1"].items():
        best = max(res_list, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
        if best:
            n_val = best['n']
            print(f"\n  ⚡ XAU_M5_US_RSI6_CB1 n={n_val} (ref: 28 in R48) — {'✅ 有增长!' if n_val > 28 else '❌ 连续5月无增长 — 建议标记为数据冻结'}")


# =====================================================
# PART 3: XAGUSD M5 EU RSI<8 第5月验证 + RSI<5 ALL第2月
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 3: XAGUSD M5 EU RSI<8 第5月验证 + RSI<5 ALL第2月跟踪")
print("─" * 120)

xag_m5_tracking = [
    # EU session — 第5月验证
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
    # ALL sessions — RSI<5 第2月验证(候选纳入推荐)
    {"name": "XAG_M5_RSI5_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<5 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI5_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<5 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # RSI<6 ALL 对比基线
    {"name": "XAG_M5_RSI6_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<6 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI6_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<6 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # RSI<8 ALL 仓位配置
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

prev_refs_xag = {
    "XAG_M5_EU_RSI8_CB1": "90.3% n=31",
    "XAG_M5_EU_RSI8_CB2": "89.3% n=28",
    "XAG_M5_EU_RSI8_CB3": "88.0% n=25",
    "XAG_M5_EU_RSI8_CB4": "90.9% n=22",
    "XAG_M5_RSI5_CB1_ALL": "88.7% n=71",
    "XAG_M5_RSI5_CB2_ALL": "—",
    "XAG_M5_RSI6_CB1_ALL": "86.0% n=93",
    "XAG_M5_RSI6_CB2_ALL": "85.9% n=78",
    "XAG_M5_RSI8_CB1_ALL": "75.6% n=164",
    "XAG_M5_RSI8_CB2_ALL": "75.2% n=141",
    "XAG_M5_RSI8_CB3_ALL": "72.0% n=118",
}
print("\n📊 XAG M5 第5月验证 + RSI<5第2月:")
print_best_table(all_xag_m5, prev_refs_xag)

# Check n-growth for XAG_M5_EU_RSI8_CB1 (key strategy)
if "XAG_M5_EU_RSI8_CB1" in all_xag_m5:
    for sym, res_list in all_xag_m5["XAG_M5_EU_RSI8_CB1"].items():
        best = max(res_list, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
        if best:
            print(f"\n  ⚡ XAG_M5_EU_RSI8_CB1 n={best['n']} (ref: 31 in R48) — {'✅ 有增长!' if best['n'] > 31 else '⚠️ 无增长'}")


# =====================================================
# PART 4: US500 M5 EU 第9月跟踪 + RSI<12/10版本深化
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 4: US500 M5 EU 第9月跟踪 + RSI<12验证 + RSI<10探索")
print("─" * 120)

us500_tracking = [
    # 标准版本
    {"name": "US500_EU_CB4_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    {"name": "US500_EU_CB5_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    {"name": "US500_EU_CB6_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=6",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    # RSI<12 优化版本
    {"name": "US500_EU_CB5_RSI12", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    # RSI<10 严格版本
    {"name": "US500_EU_CB5_RSI10", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    # CB6+RSI12 极严格
    {"name": "US500_EU_CB6_RSI12", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=6",
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

prev_refs_us500 = {
    "US500_EU_CB4_RSI14": "78.1% n=73",
    "US500_EU_CB5_RSI14": "84.6% n=52",
    "US500_EU_CB6_RSI14": "85.7% n=35",
    "US500_EU_CB5_RSI12": "83.3% n=36",
    "US500_EU_CB5_RSI10": "79.2% n=24",
    "US500_EU_CB6_RSI12": "—",
}
print("\n📊 US500 M5 EU 第9月跟踪:")
print_best_table(all_us500, prev_refs_us500)


# =====================================================
# PART 5: XAUUSD M1 ASIA 第7月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 5: XAUUSD M1 ASIA 第7月跟踪")
print("─" * 120)

asia_tracking = [
    {"name": "XAU_M1_ASIA_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
    {"name": "XAU_M1_ASIA_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
    {"name": "XAU_M1_ASIA_CB4_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
]

all_asia = {}
for cfg in asia_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_asia[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

prev_refs_asia = {
    "XAU_M1_ASIA_CB3_RSI10": "75.0% n=68",
    "XAU_M1_ASIA_CB2_RSI10": "73.8% n=80",
    "XAU_M1_ASIA_CB4_RSI10": "72.2% n=54",
}
print("\n📊 XAU M1 ASIA 第7月跟踪:")
print_best_table(all_asia, prev_refs_asia)


# =====================================================
# PART 6: US30 M1 EU CB4+RSI<12 第2月验证 + 深入分析
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 6: US30 M1 EU CB4+RSI<12 第2月验证 + 深入分析")
print("─" * 120)

us30_tracking = [
    # 基线
    {"name": "US30_M1_EU_CB3_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "US30_M1_EU_CB4_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "US30_M1_EU_CB5_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # RSI<12 第2月验证
    {"name": "US30_M1_EU_CB4_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # RSI<12 + CB5 深入
    {"name": "US30_M1_EU_CB5_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # RSI<10深入
    {"name": "US30_M1_EU_CB4_RSI10", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=4",
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

prev_refs_us30 = {
    "US30_M1_EU_CB3_RSI14": "65.1% r48",
    "US30_M1_EU_CB4_RSI14": "70.4% r48 ✅",
    "US30_M1_EU_CB5_RSI14": "73.2% r48 ⚠️hold=5",
    "US30_M1_EU_CB4_RSI12": "77.8% r48 ✅",
    "US30_M1_EU_CB5_RSI12": "—",
    "US30_M1_EU_CB4_RSI10": "—",
}
print("\n📊 US30 M1 EU CP复审 + RSI<12第2月验证:")
print(f"| {'Strategy':<30} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<7} | {'Status':<15} | {'Ref':<15} |")
print(f"|{':':->30}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->7}|{':':->15}|{':':->15}|")
for name in sorted(all_us30.keys()):
    results = all_us30[name]
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
        if best and best["n"] >= 3:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            prev = prev_refs_us30.get(name, "")
            wr_val = best["win_rate"]
            n_val = best["n"]
            sharpe_val = best["sharpe_ratio"]
            if wr_val >= 0.70 and n_val >= 30:
                if best["hold_period"] < 10:
                    status = "⚠️ hold<10"
                else:
                    status = "✅ CP通过"
            elif wr_val >= 0.65:
                status = "⏳ 边界"
            else:
                status = "❌ 不合格"
            print(f"| {name:<30} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<7.2f} | {status:<15} | {prev:<15} |")


# =====================================================
# PART 7: XAUUSD M5 H15/H19精确定时第5月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 7: XAUUSD M5 美盘H15/H19精确定时第5月跟踪")
print("─" * 120)

xau_hour_tracking = [
    # H15 (US开盘)
    {"name": "XAU_M5_H15_CB1_RSI10", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==15 and rsi14<10 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_H15_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==15 and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M5_H15_CB1_RSI8", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==15 and rsi14<8 and consecutive_bear>=1",
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
    # H16探索
    {"name": "XAU_M5_H16_CB1_RSI10", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "hour==16 and rsi14<10 and consecutive_bear>=1",
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

prev_refs_xau_hour = {
    "XAU_M5_H15_CB1_RSI10": "91.7% n=12",
    "XAU_M5_H15_CB2_RSI10": "90.9% n=11",
    "XAU_M5_H15_CB1_RSI8": "100% n=7",
    "XAU_M5_H19_CB4_RSI12": "90.9% n=11",
    "XAU_M5_H19_CB5_RSI12": "100% n=8",
    "XAU_M5_H19_CB3_RSI12": "80.0% n=15",
    "XAU_M5_H16_CB1_RSI10": "70% n=10",
}
print("\n📊 XAU M5 美盘H精确定时第5月:")
print_best_table(all_xau_hour, prev_refs_xau_hour, min_n=2)


# =====================================================
# PART 8: XAGUSD M5 RSI<5 CB1 ALL 第2月验证 — 信号频率检测
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 8: XAGUSD M5 仓位配置 — 信号频率更新 + RSI<5第2月验证")
print("─" * 120)

try:
    xag_data = load_data(timeframe="M5", symbols=["XAGUSD"])
    if xag_data and "XAGUSD" in xag_data:
        df = compute_indicators(xag_data["XAGUSD"])

        configs = {
            "RSI<5 CB1 ALL": "rsi14<5 and consecutive_bear>=1",
            "RSI<6 CB1 ALL": "rsi14<6 and consecutive_bear>=1",
            "RSI<6 CB2 ALL": "rsi14<6 and consecutive_bear>=2",
            "RSI<8 CB1 ALL": "rsi14<8 and consecutive_bear>=1",
            "RSI<8 CB2 ALL": "rsi14<8 and consecutive_bear>=2",
            "RSI<8 CB3 ALL": "rsi14<8 and consecutive_bear>=3",
            "RSI<8 EU CB1": "session=='europe' and rsi14<8 and consecutive_bear>=1",
            "RSI<8 EU CB2": "session=='europe' and rsi14<8 and consecutive_bear>=2",
        }

        total_candles = len(df)
        months = total_candles / 7200  # ~7200 M5 candles/month

        print("\n📊 XAGUSD M5 信号频率表 (仓位配置):\n")
        print(f"| {'策略':<20} | {'信号总数':<8} | {'月均信号':<10} | {'信号率%':<8} | {'仓位建议':<12} |")
        print(f"|{':':->20}|{':':->8}|{':':->10}|{':':->8}|{':':->12}|")

        for label, cond in configs.items():
            mask = df.eval(cond)
            n_signals = int(mask.sum())
            per_month = n_signals / months if months > 0 else 0
            freq_pct = n_signals / total_candles * 100 if total_candles > 0 else 0

            if per_month >= 10:
                pos = "🟢 大仓位"
            elif per_month >= 5:
                pos = "🟡 中仓位"
            elif per_month >= 2:
                pos = "🟠 小仓位"
            else:
                pos = "🔴 极轻仓"

            print(f"| {label:<20} | {n_signals:<8} | {per_month:<9.1f}/月 | {freq_pct:<7.3f}% | {pos:<12} |")

except Exception as e:
    print(f"  ⚠ XAGUSD 仓位配置验证失败: {e}")


# =====================================================
# PART 9: JP225 M5 最低权重监控
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 9: JP225 M5 最低权重监控")
print("─" * 120)

jp225_tracking = [
    {"name": "JP225_M5_US_CB3_RSI10", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 45]},
    {"name": "JP225_M5_US_CB4_RSI10", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 45]},
    {"name": "JP225_M5_US_CB5_RSI12", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=5",
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

print("\n📊 JP225 M5 US session 监控:")
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
# PART 10: 新探索方向
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 10: 新探索 — EU CB3+RSI<8积累 + US30深入 + 数据更新验证")
print("─" * 120)

# 10a: XAU M1 EU CB3+RSI<8 积累追踪 (100% WR, n currently 25, target n>=30)
# 10b: US30 M1 deeper RSI levels
# 10c: Check data freshness for M5 XAUUSD
# 10d: Other cross-session explorations

m1_explore = [
    # EU CB3+RSI<8 accumulation - already in Part 1 but list explicitly
    {"name": "XAU_M1_EU_CB3_RSI7", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<7 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU CB2 with deeper RSI
    {"name": "XAU_M1_EU_CB2_RSI7", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<7 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU CB2+RSI5 accumulation (from R48: 100% n=15)
    {"name": "XAU_M1_EU_CB2_RSI5", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<5 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
]

all_m1_explore = {}
for cfg in m1_explore:
    try:
        # Check if not already tested in Part 1
        name = cfg["name"]
        if name not in all_m1_results:
            res = run_grid(cfg)
            if res:
                all_m1_explore[name] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 新探索: M1 EU 极深入分析:")
print_best_table(all_m1_explore, {"XAU_M1_EU_CB3_RSI7": "—", "XAU_M1_EU_CB2_RSI7": "91.3% n=23", "XAU_M1_EU_CB2_RSI5": "100% n=15"}, min_n=3)

# 10c: Data date range verification (check if M5 data has new rows since R48)
print("\n📊 数据更新验证 (M5 XAUUSD):")
try:
    m5_data = load_data(timeframe="M5", symbols=["XAUUSD"])
    if m5_data and "XAUUSD" in m5_data:
        df = m5_data["XAUUSD"]
        first_date = df.index[0].strftime("%Y-%m-%d")
        last_date = df.index[-1].strftime("%Y-%m-%d %H:%M")
        total_rows = len(df)
        print(f"  XAUUSD M5: {total_rows} rows, {first_date} → {last_date}")
        # Check if data includes today
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if df.index[-1].strftime("%Y-%m-%d") == today:
            print(f"  ✅ 数据包含今天({today})，已更新")
        elif df.index[-1].strftime("%Y-%m-%d") >= "2026-05-13":
            print(f"  ⚠️ 数据截至 {last_date}，可能未包含最新数据")
        else:
            print(f"  ❌ 数据较旧: {last_date}")
except Exception as e:
    print(f"  ⚠ 数据验证失败: {e}")


# =====================================================
# SUMMARY
# =====================================================
print("\n" + "=" * 120)
print(f"📋 ROUND 49 SUMMARY — 月度跟踪(第11/9/7月) + 跨周期验证(第5月) + 新探索")
print("=" * 120)

# Collect all findings
all_findings = []
all_maps = [
    ("M1跟踪", collect_best(all_m1_results, min_n=10, min_wr=0.70)),
    ("XAU M5", collect_best(all_xau_m5, min_n=10, min_wr=0.70)),
    ("XAG M5", collect_best(all_xag_m5, min_n=10, min_wr=0.70)),
    ("US500", collect_best(all_us500, min_n=10, min_wr=0.70)),
    ("ASIA", collect_best(all_asia, min_n=10, min_wr=0.70)),
    ("US30", collect_best(all_us30, min_n=10, min_wr=0.70)),
    ("XAU H精确定时", [(n, s, b) for n, results in all_xau_hour.items() for s, res_list in results.items()
                         for b in [max(res_list, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)]
                         if b and b["n"] >= 5 and b["win_rate"] >= 0.70]),
    ("JP225", [(n, s, b) for n, results in all_jp225.items() for s, res_list in results.items()
                for b in [max(res_list, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)]
                if b and b["n"] >= 10 and b["win_rate"] >= 0.70]),
    ("新探索", collect_best(all_m1_explore, min_n=5, min_wr=0.70)),
]

print(f"\n{'='*120}")
print("🏆 TOP FINDINGS (WR≥70% n≥10)" if False else "🏆 ALL FINDINGS SUMMARY")
print(f"{'='*120}")
print(f"| {'Rank':<5} | {'Category':<12} | {'Strategy':<30} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<8} |")
print(f"|{'':->5}|{'':->12}|{'':->30}|{'':->7}|{'':->6}|{'':->5}|{'':->10}|{'':->8}|")

rank = 0
for category, findings in all_maps:
    for name, sym, best in sorted(findings, key=lambda x: -x[2]["win_rate"]):
        rank += 1
        wr = f"{best['win_rate']*100:.1f}%"
        ar = f"{best['avg_return']*100:.3f}%"
        print(f"| {rank:<5} | {category:<12} | {name:<30} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<8.2f} |")

if rank == 0:
    print("| (no findings meeting criteria)")

print(f"\n{'='*120}")
print(f"✅ ROUND 49 COMPLETE — {NOW}")
print(f"{'='*120}")
