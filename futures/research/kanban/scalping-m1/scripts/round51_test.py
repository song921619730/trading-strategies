#!/usr/bin/env python3
"""
Round 51 — M1/M5 Scalping 第13/11/9月跟踪 + 第4/3/2月验证 + 新探索 + CB6+RSI12跟踪

聚焦:
  1. XAUUSD M1 US/EU 第13月常规跟踪 + EU_CB2第5月 + EU_RSI8第3月 + CB3+RSI7第2月
  2. XAUUSD M5 US RSI<6 冻结归档跳过(季度检查)
  3. XAGUSD M5 RSI<5 ALL第4月跟踪(质量监控) + EU归档跳过
  4. US500 M5 EU 第11月常规跟踪 + CB6+RSI12跟踪
  5. XAUUSD M1 ASIA 第9月跟踪
  6. US30 M1 EU CB4+RSI12第4月跟踪 + CB5+RSI12第3月验证(推荐纳入) + CB6+RSI12新发现第1月跟踪
  7. XAUUSD M5 H15/H19冻结归档跳过
  8. XAGUSD M5 RSI<5 ALL第4月跟踪(信号频率)
  9. JP225 M5最低权重监控(维持边界)
  10. 新探索: US30 CB6+RSI12第2月验证 + H1/M30策略监控
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
print(f"ROUND 51 — M1/M5 Scalping 第13/11/9月跟踪 + 第4/3/2月验证 — {NOW}")
print(f"Target: M1/M5 on XAUUSD XAGUSD JP225 US500 US30")
print("=" * 120)

# =====================================================
# HELPER
# =====================================================
def print_best_table(name_results_map, prev_refs=None, min_n=3, extended=False):
    """Print best hold-period result per strategy."""
    header = f"| {'Strategy':<35} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<9} | {'Ref':<20} |"
    sep = f"|{':':->35}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->9}|{':':->20}|"
    print(header)
    print(sep)
    for name in sorted(name_results_map.keys()):
        results = name_results_map[name]
        for sym, sym_res in results.items():
            best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= min_n else 0)
            if best and best["n"] >= min_n:
                wr = f"{best['win_rate']*100:.1f}%"
                ar = f"{best['avg_return']*100:.3f}%"
                prev = prev_refs.get(name, "") if prev_refs else ""
                print(f"| {name:<35} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<9.2f} | {prev:<20} |")

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
# PART 1: XAUUSD M1 — 第13月常规跟踪 + EU_CB2第5月 + EU_RSI8第3月 + CB3+RSI7第2月
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 1: XAUUSD M1 — 第13月常规跟踪(US/EU) + EU_CB2(第5月) + EU_RSI8(第3月) + CB3+RSI7(第2月)")
print("─" * 120)

m1_tracking = [
    # US 第13月常规跟踪
    {"name": "XAU_M1_US_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_US_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU 第13月常规跟踪
    {"name": "XAU_M1_EU_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU_CB2 宽松版 — 第5月独立跟踪
    {"name": "XAU_M1_EU_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # 双极值联合
    {"name": "XAU_M1_DUAL_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "(session=='europe' or session=='us') and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU_RSI8 — 第3月独立跟踪
    {"name": "XAU_M1_EU_CB3_RSI8", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_EU_CB2_RSI8", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU CB3+RSI7 — 第2月独立跟踪(原R49 R50: 100% n=19)
    {"name": "XAU_M1_EU_CB3_RSI7", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<7 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU CB2+RSI7 探索
    {"name": "XAU_M1_EU_CB2_RSI7", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<7 and consecutive_bear>=2",
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
    "XAU_M1_US_CB3_RSI10": "85.4% n=48 R50",
    "XAU_M1_US_CB2_RSI10": "81.0% R50",
    "XAU_M1_EU_CB3_RSI10": "97.2% n=36 R50",
    "XAU_M1_EU_CB2_RSI10": "93.2% n=44 R50",
    "XAU_M1_DUAL_CB3_RSI10": "85.7% n=84 R50",
    "XAU_M1_EU_CB3_RSI8": "100.0% n=25 R50",
    "XAU_M1_EU_CB2_RSI8": "93.1% n=29 R50",
    "XAU_M1_EU_CB3_RSI7": "100.0% n=19 R50",
    "XAU_M1_EU_CB2_RSI7": "91.3% n=23 R50",
    "XAU_M1_EU_CB2_RSI5": "100.0% n=15 R50",
}
print("\n📊 M1 第13月跟踪(US/EU年度审查通过后常规跟踪):")
print_best_table(all_m1_results, prev_refs_m1)


# =====================================================
# PART 2: XAUUSD M5 US RSI<6 — 跳过(冻结归档, 下次季度检查8月)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 2: XAUUSD M5 US RSI<6 — ❄️ 跳过(冻结归档, 下次季度检查2026-08)")
print("─" * 120)
print("  ⏭️  连续6月n无增长(28→28→28→28→28→28),正式归档为季度检查.")
print("  ⏭️  下次检查: 2026年8月(第3季度).")


# =====================================================
# PART 3: XAGUSD M5 RSI<5 ALL第4月跟踪 + EU归档跳过
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 3: XAGUSD M5 RSI<5 ALL第4月跟踪(质量监控) + EU归档跳过")
print("─" * 120)

xag_m5_tracking = [
    # ALL sessions — RSI<5 第4月跟踪(正式纳入推荐后质量监控)
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
    {"name": "XAG_M5_RSI6_CB3_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<6 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # RSI<8 ALL 仓位参考
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
    "XAG_M5_RSI5_CB1_ALL": "88.7% n=71 ✅R50",
    "XAG_M5_RSI5_CB2_ALL": "88.3% n=60 R50",
    "XAG_M5_RSI6_CB1_ALL": "86.0% n=93",
    "XAG_M5_RSI6_CB2_ALL": "85.9% n=78",
    "XAG_M5_RSI6_CB3_ALL": "—",
    "XAG_M5_RSI8_CB1_ALL": "75.6% n=164",
    "XAG_M5_RSI8_CB2_ALL": "75.2% n=141",
    "XAG_M5_RSI8_CB3_ALL": "72.0% n=118",
}
print("\n📊 XAG M5 RSI<5 ALL第4月跟踪(质量监控):")
print_best_table(all_xag_m5, prev_refs_xag)


# =====================================================
# PART 4: US500 M5 EU 第11月常规跟踪 + CB6+RSI12跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 4: US500 M5 EU 第11月常规跟踪 + CB6+RSI12跟踪")
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
    # CB6+RSI12 极严格(高Sharpe)
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
    "US500_EU_CB5_RSI14": "84.6% n=52 ✅第11月",
    "US500_EU_CB6_RSI14": "85.7% n=35",
    "US500_EU_CB5_RSI12": "83.3% n=36",
    "US500_EU_CB5_RSI10": "79.2% n=24",
    "US500_EU_CB6_RSI12": "84.6% n=26",
}
print("\n📊 US500 M5 EU 第11月常规跟踪:")
print_best_table(all_us500, prev_refs_us500)


# =====================================================
# PART 5: XAUUSD M1 ASIA 第9月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 5: XAUUSD M1 ASIA 第9月跟踪")
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
print("\n📊 XAU M1 ASIA 第9月跟踪:")
print_best_table(all_asia, prev_refs_asia)


# =====================================================
# PART 6: US30 M1 EU CB4+RSI12第4月跟踪 + CB5+RSI12第3月验证 + CB6+RSI12新发现第1月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 6: US30 M1 EU CB4+RSI12第4月跟踪 + CB5+RSI12第3月验证(推荐纳入) + CB6+RSI12新发现第1月跟踪")
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
    # RSI<12 第4月跟踪(已纳入推荐)
    {"name": "US30_M1_EU_CB4_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # RSI<12 + CB5 第3月验证(推荐候选 → 正式纳入)
    {"name": "US30_M1_EU_CB5_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # RSI<10深入跟踪
    {"name": "US30_M1_EU_CB4_RSI10", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # 🆕 CB6+RSI12 — 新发现第1月跟踪(R50: 88.5% n=26 hold=15 Sharpe=145.33)
    {"name": "US30_M1_EU_CB6_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=6",
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
    "US30_M1_EU_CB3_RSI14": "65.1%",
    "US30_M1_EU_CB4_RSI14": "70.4% ✅",
    "US30_M1_EU_CB5_RSI14": "73.2% ⚠️hold=5",
    "US30_M1_EU_CB4_RSI12": "77.8% ✅推荐",
    "US30_M1_EU_CB5_RSI12": "80.0% 🆕候选",
    "US30_M1_EU_CB4_RSI10": "77.8%",
    "US30_M1_EU_CB6_RSI12": "88.5% n=26 🆕🎯",
}
print("\n📊 US30 M1 EU 跟踪(第4月/第3月/第1月):")
print(f"| {'Strategy':<35} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<9} | {'Status':<18} | {'Ref':<18} |")
print(f"|{':':->35}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->9}|{':':->18}|{':':->18}|")
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
            hp = best["hold_period"]
            if wr_val >= 0.75 and n_val >= 30 and hp >= 10:
                status = "✅ 正式推荐"
            elif wr_val >= 0.75 and n_val >= 25 and hp >= 10:
                status = "✅ 推荐候选"
            elif wr_val >= 0.70 and n_val >= 20:
                status = "⏳ 观察中"
            elif wr_val >= 0.65:
                status = "⚠️ 边界"
            else:
                status = "❌ 不合格"
            print(f"| {name:<35} | {wr:<7} | {best['n']:<6} | {hp:<5} | {ar:<10} | {best['sharpe_ratio']:<9.2f} | {status:<18} | {prev:<18} |")


# =====================================================
# PART 7: XAUUSD M5 H15/H19冻结归档跳过
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 7: XAUUSD M5 H15/H19 — ❄️ 跳过(冻结归档, 下次季度检查8月)")
print("─" * 120)
print("  ⏭️  连续6月n无增长,正式归档. 下次季度检查: 2026年8月.")


# =====================================================
# PART 8: XAGUSD M5 RSI<5 ALL第4月跟踪 — 信号频率检测
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 8: XAGUSD M5 RSI<5 ALL第4月跟踪 — 仓位配置更新(信号频率)")
print("─" * 120)

try:
    xag_data = load_data(timeframe="M5", symbols=["XAGUSD"])
    if xag_data and "XAGUSD" in xag_data:
        df = compute_indicators(xag_data["XAGUSD"])
        for name, cond, desc in [
            ("XAG_M5_RSI5_CB1_ALL", "rsi14<5 and consecutive_bear>=1", "RSI<5 CB1 ALL"),
            ("XAG_M5_RSI5_CB2_ALL", "rsi14<5 and consecutive_bear>=2", "RSI<5 CB2 ALL"),
            ("XAG_M5_RSI6_CB1_ALL", "rsi14<6 and consecutive_bear>=1", "RSI<6 CB1 ALL"),
            ("XAG_M5_RSI6_CB2_ALL", "rsi14<6 and consecutive_bear>=2", "RSI<6 CB2 ALL"),
        ]:
            mask = df.eval(cond)
            total = mask.sum()
            years = (df.index[-1] - df.index[0]).days / 365.25
            freq = total / max(years, 0.5)
            print(f"  📈 {desc}: {total}信号 = {freq:.1f}次/年 ({total/max(years*12,0.5):.1f}次/月)")

        # 数据新鲜度检查
        last_date = df.index[-1]
        days_since = (pd.Timestamp.utcnow() - last_date).days
        print(f"\n  📅 数据截至: {last_date.strftime('%Y-%m-%d %H:%M')} UTC ({days_since}天前)")
        if days_since > 7:
            print("  ⚠️ 数据超过7天,可能不是最新!")
        else:
            print("  ✅ 数据较新")
except Exception as e:
    print(f"  ⚠ 信号频率分析失败: {e}")


# =====================================================
# PART 9: JP225 M5最低权重监控(维持边界)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 9: JP225 M5最低权重监控(维持边界)")
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
    # EU session check
    {"name": "JP225_M5_EU_CB3_RSI10", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3",
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

prev_refs_jp225 = {
    "JP225_M5_US_CB3_RSI10": "68.5% n=111",
    "JP225_M5_US_CB4_RSI10": "66.3% n=86",
    "JP225_M5_US_CB5_RSI12": "67.4% n=89",
    "JP225_M5_EU_CB3_RSI10": "—",
}
print("📊 JP225 M5 最低权重监控(维持边界):")
print_best_table(all_jp225, prev_refs_jp225)


# =====================================================
# PART 10: 新探索 — US30 CB6+RSI12第2月验证 + H1/M30策略监控
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 10: 新探索 — ①US30 CB6+RSI12第2月验证 ②XAU数据源检查 ③H1/M30策略状态")
print("─" * 120)

# --- 10a: US30 CB6+RSI12 定向第2月验证(不同hold深度) ---
print("\n🔍 10a: US30 CB6+RSI12 第2月验证 — 不同hold深度对比")
us30_cb6_deep = [
    {"name": "US30_CB6_RSI12_DEEP", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=6",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30, 40, 55]},
    # 美盘版本对比
    {"name": "US30_US_CB6_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=6",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # 做空探索(谨慎)
    {"name": "US30_EU_CB6_RSI12_SHORT", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14>88 and consecutive_bull>=6",
     "direction": "short", "hold_periods": [5, 10, 15, 20, 30]},
]
all_cb6_deep = {}
for cfg in us30_cb6_deep:
    try:
        res = run_grid(cfg)
        if res:
            all_cb6_deep[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 US30 CB6+RSI12 第2月验证(深度hold测试):")
print_best_table(all_cb6_deep)

# --- 10b: XAU M5数据源扩展检查 ---
print("\n🔍 10b: XAU M5数据源扩展检查")
try:
    from data_loader import list_available_symbols
    m5_symbols = list_available_symbols("M5")
    m1_symbols = list_available_symbols("M1")
    print(f"  M5可用品种({len(m5_symbols)}): {', '.join(m5_symbols[:10])}{'...' if len(m5_symbols)>10 else ''}")
    print(f"  M1可用品种({len(m1_symbols)}): {', '.join(m1_symbols[:10])}{'...' if len(m1_symbols)>10 else ''}")
    
    # 检查XAU M5最新数据时间
    xau_m5 = load_data(timeframe="M5", symbols=["XAUUSD"])
    if xau_m5 and "XAUUSD" in xau_m5:
        df = xau_m5["XAUUSD"]
        print(f"  XAUUSD M5: {len(df)}行, {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d %H:%M')}")
except Exception as e:
    print(f"  ⚠ 数据检查失败: {e}")

# --- 10c: H1/M30策略状态检查 ---
print("\n🔍 10c: H1/M30策略状态检查")
try:
    h1_symbols = list_available_symbols("H1")
    m30_symbols = list_available_symbols("M30")
    print(f"  H1可用品种: {len(h1_symbols)}")
    print(f"  M30可用品种: {len(m30_symbols)}")
    
    if "XAUUSD" in h1_symbols:
        xau_h1 = load_data(timeframe="H1", symbols=["XAUUSD"])
        if xau_h1 and "XAUUSD" in xau_h1:
            df = xau_h1["XAUUSD"]
            print(f"  XAUUSD H1: {len(df)}行, {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d %H:%M')}")
except Exception as e:
    print(f"  ⚠ H1/M30检查失败: {e}")

# --- 10d: XAU USD小幅扩展阈值测试(探索新信号源) ---
print("\n🔍 10d: XAU USD M1/M5阈值拓展探索(寻找未冻结的新信号)")
xau_explore = [
    # M1 美盘中位阈值
    {"name": "XAU_M1_US_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [10, 15, 30, 55]},
    # M5 欧盘放宽CB
    {"name": "XAU_M5_EU_CB5_RSI10", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [10, 15, 30, 55]},
    # M5 美盘中位
    {"name": "XAU_M5_US_CB4_RSI10", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [10, 15, 30, 55]},
    # M5 ASIA 试试
    {"name": "XAU_M5_ASIA_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [10, 15, 30, 55]},
]

all_xau_explore = {}
for cfg in xau_explore:
    try:
        res = run_grid(cfg)
        if res:
            all_xau_explore[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

print("\n📊 XAU USD 阈值拓展探索:")
print_best_table(all_xau_explore, min_n=5)


# =====================================================
# SUMMARY: 关键发现汇总
# =====================================================
print("\n" + "=" * 120)
print(f"📋 ROUND 51 关键发现汇总 — {NOW}")
print("=" * 120)

def detect_change(current_val, ref_str):
    """Parse ref string for n and WR comparison."""
    try:
        parts = ref_str.split()
        for p in parts:
            if p.startswith("n="):
                ref_n = int(p.split("=")[1].split(",")[0].split(")")[0])
                return current_val - ref_n, ref_n
    except:
        pass
    return None, None

# 汇总所有策略中最好的发现
print("\n🏆 Top Findings (WR>=75% n>=15):")
all_findings = []

for name, results in {**all_m1_results, **all_xag_m5, **all_us500, **all_asia, **all_us30, **all_jp225, **all_cb6_deep, **all_xau_explore}.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 15 and best["win_rate"] >= 0.75:
            all_findings.append((name, sym, best))

all_findings.sort(key=lambda x: -x[2]["win_rate"])

print(f"| {'Strategy':<35} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<9} | {'Signal/month':<14} |")
print(f"|{':':->35}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->9}|{':':->14}|")
for name, sym, best in all_findings:
    wr = f"{best['win_rate']*100:.1f}%"
    ar = f"{best['avg_return']*100:.3f}%"
    print(f"| {name:<35} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<9.2f} | {'—':<14} |")

# Print bottom performers (for monitoring)
print("\n⚠️ 边界策略(65%<=WR<75% n>=20):")
for name, results in {**all_m1_results, **all_xag_m5, **all_us500, **all_asia, **all_us30, **all_jp225}.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 20 and 0.65 <= best["win_rate"] < 0.75:
            print(f"  • {name}: WR={best['win_rate']*100:.1f}% n={best['n']} hold={best['hold_period']} Sharpe={best['sharpe_ratio']:.1f}")

print(f"\n✅ ROUND 51 完成. {NOW}")
print("=" * 120)
