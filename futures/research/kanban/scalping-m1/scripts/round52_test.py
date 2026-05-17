#!/usr/bin/env python3
"""
Round 52 — M1/M5 Scalping 第14/12/10月跟踪 + 第5/4/3月验证 + 新探索 + H1/M30 候选监控

聚焦:
  1. XAUUSD M1 US/EU 第14月常规跟踪 + EU_CB2第6月 + EU_RSI8第4月 + CB3+RSI7第3月
  2. XAUUSD M5 US RSI<6 冻结归档跳过(季度检查)
  3. XAGUSD M5 RSI<5 ALL第5月跟踪(质量监控) + EU归档跳过
  4. US500 M5 EU 第12月常规跟踪(年度审查) + CB6+RSI12跟踪
  5. XAUUSD M1 ASIA 第10月跟踪
  6. US30 M1 EU CB4+RSI12第5月跟踪 + CB5+RSI12第4月验证(正式推荐维持) + CB6+RSI12第2月跟踪(hold验证)
  7. XAUUSD M5 H15/H19冻结归档跳过
  8. XAGUSD M5 RSI<5 ALL第5月跟踪(仓位信号频率)
  9. JP225 M5最低权重监控(维持边界)
  10. 新探索: XAU M1 US CB4+RSI12第2月验证 + US30 CB6+RSI12 hold稳定性分析 + XAU M5宽松阈值 + AUDUSD M30候选监控
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
print(f"ROUND 52 — M1/M5 Scalping 第14/12/10月跟踪 + 第5/4/3月验证 + 新探索 — {NOW}")
print(f"Target: M1/M5/H1/M30 on XAUUSD XAGUSD JP225 US500 US30 AUDUSD ...")
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
# PART 1: XAUUSD M1 — 第14月常规跟踪 + EU_CB2第6月 + EU_RSI8第4月 + CB3+RSI7第3月
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 1: XAUUSD M1 — 第14月常规跟踪(US/EU) + EU_CB2(第6月) + EU_RSI8(第4月) + CB3+RSI7(第3月)")
print("─" * 120)

m1_tracking = [
    # US 第14月常规跟踪
    {"name": "XAU_M1_US_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_US_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU 第14月常规跟踪
    {"name": "XAU_M1_EU_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU_CB2 宽松版 — 第6月独立跟踪
    {"name": "XAU_M1_EU_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # 双极值联合
    {"name": "XAU_M1_DUAL_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "(session=='europe' or session=='us') and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU_RSI8 — 第4月独立跟踪
    {"name": "XAU_M1_EU_CB3_RSI8", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_EU_CB2_RSI8", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU CB3+RSI7 — 第3月独立跟踪
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
    # 🆕 M1 US CB4+RSI12 第2月验证(新发现候选)
    {"name": "XAU_M1_US_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4",
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
    "XAU_M1_US_CB3_RSI10": "85.4% n=48 R51",
    "XAU_M1_US_CB2_RSI10": "81.0% R51",
    "XAU_M1_EU_CB3_RSI10": "97.2% n=36 R51",
    "XAU_M1_EU_CB2_RSI10": "93.2% n=44 R51",
    "XAU_M1_DUAL_CB3_RSI10": "85.7% n=84 R51",
    "XAU_M1_EU_CB3_RSI8": "100.0% n=25 R51",
    "XAU_M1_EU_CB2_RSI8": "93.1% n=29 R51",
    "XAU_M1_EU_CB3_RSI7": "100.0% n=19 R51",
    "XAU_M1_EU_CB2_RSI7": "91.3% n=23 R51",
    "XAU_M1_EU_CB2_RSI5": "100.0% n=15 R51",
    "XAU_M1_US_CB4_RSI12": "76.4% n=72 🆕R51",
}
print("\n📊 M1 第14月跟踪(US/EU年度) + 扩展追踪:")
print_best_table(all_m1_results, prev_refs_m1)


# =====================================================
# PART 2: XAUUSD M5 US RSI<6 — 跳过(冻结归档, 下次季度检查8月)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 2: XAUUSD M5 US RSI<6 — ❄️ 跳过(冻结归档, 下次季度检查2026-08)")
print("─" * 120)
print("  ⏭️  连续7月n无增长(28),正式归档为季度检查.")
print("  ⏭️  下次检查: 2026年8月(第3季度).")


# =====================================================
# PART 3: XAGUSD M5 RSI<5 ALL第5月跟踪 + EU归档跳过
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 3: XAGUSD M5 RSI<5 ALL第5月跟踪(质量监控) + EU归档跳过")
print("─" * 120)

xag_m5_tracking = [
    # ALL sessions — RSI<5 第5月跟踪(正式纳入推荐后质量监控)
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
    # 🆕 RSI<4 极端测试(新探索)
    {"name": "XAG_M5_RSI4_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<4 and consecutive_bear>=1",
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
    "XAG_M5_RSI5_CB1_ALL": "88.7% n=71 ✅R51",
    "XAG_M5_RSI5_CB2_ALL": "88.3% n=60 R51",
    "XAG_M5_RSI6_CB1_ALL": "86.0% n=93",
    "XAG_M5_RSI6_CB2_ALL": "85.9% n=78",
    "XAG_M5_RSI6_CB3_ALL": "84.4% n=64",
    "XAG_M5_RSI8_CB1_ALL": "75.6% n=164",
    "XAG_M5_RSI8_CB2_ALL": "75.2% n=141",
    "XAG_M5_RSI8_CB3_ALL": "72.0% n=118",
    "XAG_M5_RSI4_CB1_ALL": "— 🆕",
}
print("\n📊 XAG M5 RSI<5 ALL第5月跟踪(质量监控):")
print_best_table(all_xag_m5, prev_refs_xag)


# =====================================================
# PART 4: US500 M5 EU 第12月常规跟踪(年度审查) + CB6+RSI12跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 4: US500 M5 EU 第12月常规跟踪(年度审查) + CB6+RSI12跟踪")
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
    "US500_EU_CB5_RSI14": "84.6% n=52 ✅第12月",
    "US500_EU_CB6_RSI14": "85.7% n=35",
    "US500_EU_CB5_RSI12": "83.3% n=36",
    "US500_EU_CB5_RSI10": "79.2% n=24",
    "US500_EU_CB6_RSI12": "84.6% n=26",
}
print("\n📊 US500 M5 EU 第12月常规跟踪(年度审查):")
print_best_table(all_us500, prev_refs_us500)


# =====================================================
# PART 5: XAUUSD M1 ASIA 第10月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 5: XAUUSD M1 ASIA 第10月跟踪")
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
print("\n📊 XAU M1 ASIA 第10月跟踪:")
print_best_table(all_asia, prev_refs_asia)


# =====================================================
# PART 6: US30 M1 EU CB4+RSI12第5月跟踪 + CB5+RSI12第4月验证 + CB6+RSI12第2月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 6: US30 M1 EU CB4+RSI12第5月跟踪 + CB5+RSI12第4月验证(正式推荐维持) + CB6+RSI12第2月跟踪(hold验证)")
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
    # RSI<12 第5月跟踪(正式推荐)
    {"name": "US30_M1_EU_CB4_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # RSI<12 + CB5 第4月验证(正式推荐维持)
    {"name": "US30_M1_EU_CB5_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # RSI<10深入跟踪
    {"name": "US30_M1_EU_CB4_RSI10", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # CB6+RSI12 第2月跟踪(hold验证)
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
    "US30_M1_EU_CB4_RSI14": "70.4%",
    "US30_M1_EU_CB5_RSI14": "73.2% ⚠️hold=5",
    "US30_M1_EU_CB4_RSI12": "77.8% ✅推荐第4月",
    "US30_M1_EU_CB5_RSI12": "80.0% ✅正式纳入",
    "US30_M1_EU_CB4_RSI10": "77.8%",
    "US30_M1_EU_CB6_RSI12": "88.5% 🆕 hold=15",
}
print("\n📊 US30 M1 EU 跟踪(第5月/第4月/第2月):")
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
print("  ⏭️  连续7月n无增长,正式归档. 下次季度检查: 2026年8月.")


# =====================================================
# PART 8: XAGUSD M5 RSI<5 ALL第5月跟踪 — 信号频率检测
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 8: XAGUSD M5 RSI<5 ALL第5月跟踪 — 仓位配置更新(信号频率)")
print("─" * 120)

try:
    xag_data = load_data(timeframe="M5", symbols=["XAGUSD"])
    if xag_data and "XAGUSD" in xag_data:
        df = compute_indicators(xag_data["XAGUSD"])
        for name, cond, desc in [
            ("XAG_M5_RSI4_CB1_ALL", "rsi14<4 and consecutive_bear>=1", "RSI<4 CB1 ALL"),
            ("XAG_M5_RSI5_CB1_ALL", "rsi14<5 and consecutive_bear>=1", "RSI<5 CB1 ALL"),
            ("XAG_M5_RSI5_CB2_ALL", "rsi14<5 and consecutive_bear>=2", "RSI<5 CB2 ALL"),
            ("XAG_M5_RSI6_CB1_ALL", "rsi14<6 and consecutive_bear>=1", "RSI<6 CB1 ALL"),
            ("XAG_M5_RSI6_CB2_ALL", "rsi14<6 and consecutive_bear>=2", "RSI<6 CB2 ALL"),
        ]:
            mask = df.eval(cond)
            total = int(mask.sum())
            years = (df.index[-1] - df.index[0]).days / 365.25
            freq = total / max(years, 0.5)
            print(f"  📈 {desc}: {total}信号 = {freq:.1f}次/年 ({total/max(years*12,0.5):.1f}次/月)")

        last_date = df.index[-1]
        print(f"\n  📅 数据截至: {last_date.strftime('%Y-%m-%d %H:%M')} UTC")
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
    "JP225_M5_EU_CB3_RSI10": "55.6% n=54",
}
print("\n📊 JP225 M5 最低权重监控(维持边界):")
print_best_table(all_jp225, prev_refs_jp225)


# =====================================================
# PART 10: 新探索
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 10: 新探索 — ①XAU M1 US CB4+RSI12第2月验证 ②US30 CB6+RSI12 hold稳定性 ③XAU M5宽松阈值 ④AUDUSD M30候选")
print("─" * 120)

# --- 10a: XAU M1 US CB4+RSI12 第2月验证(深度不同hold) ---
print("\n🔍 10a: XAU M1 US CB4+RSI12 第2月验证 — 不同hold深度")
xau_us_cb4_deep = [
    {"name": "XAU_M1_US_CB4_RSI12_DEEP", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 40, 55, 70]},
]
all_xau_cb4_deep = {}
for cfg in xau_us_cb4_deep:
    try:
        res = run_grid(cfg)
        if res:
            all_xau_cb4_deep[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")
print("\n📊 XAU M1 US CB4+RSI12 深度hold测试:")
print_best_table(all_xau_cb4_deep)

# --- 10b: US30 CB6+RSI12 第2月hold稳定性验证(包含更长hold) ---
print("\n🔍 10b: US30 CB6+RSI12 第2月hold稳定性验证")
us30_cb6_stable = [
    {"name": "US30_EU_CB6_RSI12_STABLE", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=6",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30, 40]},
]
all_us30_cb6_stable = {}
for cfg in us30_cb6_stable:
    try:
        res = run_grid(cfg)
        if res:
            all_us30_cb6_stable[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")
print("\n📊 US30 CB6+RSI12 hold稳定性:")
print_best_table(all_us30_cb6_stable)

# --- 10c: XAU M5 宽松阈值探索(寻找未冻结新信号) ---
print("\n🔍 10c: XAU M5 宽松阈值探索(寻找新信号源)")
xau_m5_explore = [
    # M5 美盘中位阈值
    {"name": "XAU_M5_US_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [10, 15, 30, 55]},
    # M5 EU 中等阈值
    {"name": "XAU_M5_EU_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [10, 15, 30, 55]},
    # M5 ASIA 宽松
    {"name": "XAU_M5_ASIA_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='asia' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [10, 15, 30, 55]},
    # M5 US RSI<15 + CB>=3 更宽松
    {"name": "XAU_M5_US_CB3_RSI15", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<15 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [10, 15, 30, 55]},
    # M5 EU RSI<15 + CB>=4
    {"name": "XAU_M5_EU_CB4_RSI15", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<15 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [10, 15, 30, 55]},
]
all_xau_m5_explore = {}
for cfg in xau_m5_explore:
    try:
        res = run_grid(cfg)
        if res:
            all_xau_m5_explore[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")
print("\n📊 XAU M5 宽松阈值探索:")
print_best_table(all_xau_m5_explore, min_n=5)

# --- 10d: AUDUSD M30 候选监控 ---
print("\n🔍 10d: AUDUSD M30 候选监控(CP3/3候选纳入)")
aud_m30_tracking = [
    {"name": "AUD_M30_CB3_RSI18", "symbols": ["AUDUSD"], "timeframe": "M30",
     "entry_condition": "session=='europe' and rsi14<18 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 40, 60]},
    {"name": "AUD_M30_CB4_RSI18", "symbols": ["AUDUSD"], "timeframe": "M30",
     "entry_condition": "session=='europe' and rsi14<18 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 40, 60]},
    {"name": "AUD_M30_CB3_RSI15", "symbols": ["AUDUSD"], "timeframe": "M30",
     "entry_condition": "session=='europe' and rsi14<15 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 40, 60]},
    {"name": "AUD_M30_CB2_RSI18", "symbols": ["AUDUSD"], "timeframe": "M30",
     "entry_condition": "session=='europe' and rsi14<18 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 40, 60]},
]
all_aud_m30 = {}
for cfg in aud_m30_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_aud_m30[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")
print("\n📊 AUDUSD M30 候选监控:")
print_best_table(all_aud_m30, min_n=5)

# --- 10e: 数据源状态检查 ---
print("\n🔍 10e: 数据源状态检查")
try:
    m5_symbols = list_available_symbols("M5")
    m1_symbols = list_available_symbols("M1")
    h1_symbols = list_available_symbols("H1")
    m30_symbols = list_available_symbols("M30")
    print(f"  M5可用品种: {len(m5_symbols)}")
    print(f"  M1可用品种: {len(m1_symbols)}")
    print(f"  H1可用品种: {len(h1_symbols)}")
    print(f"  M30可用品种: {len(m30_symbols)}")
    
    # 核心品种数据时间
    for sym, tf in [("XAUUSD","M5"), ("XAGUSD","M5"), ("XAUUSD","M1"), ("XAUUSD","H1"), ("XAUUSD","M30")]:
        d = load_data(timeframe=tf, symbols=[sym])
        if d and sym in d:
            df = d[sym]
            print(f"  {sym} {tf}: {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d %H:%M')} ({len(df)}行)")
except Exception as e:
    print(f"  ⚠ 数据检查失败: {e}")


# =====================================================
# SUMMARY: 关键发现汇总
# =====================================================
print("\n" + "=" * 120)
print(f"📋 ROUND 52 关键发现汇总 — {NOW}")
print("=" * 120)

# 汇总所有策略
all_strategies = {}
for d in [all_m1_results, all_xag_m5, all_us500, all_asia, all_us30, all_jp225,
          all_xau_cb4_deep, all_us30_cb6_stable, all_xau_m5_explore, all_aud_m30]:
    all_strategies.update(d)

print("\n🏆 Top Findings (WR>=75% n>=15):")
print(f"| {'Strategy':<35} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<9} |")
print(f"|{':':->35}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->9}|")
all_findings = []
for name, results in all_strategies.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 15 and best["win_rate"] >= 0.75:
            all_findings.append((name, sym, best))
all_findings.sort(key=lambda x: -x[2]["win_rate"])
for name, sym, best in all_findings:
    wr = f"{best['win_rate']*100:.1f}%"
    ar = f"{best['avg_return']*100:.3f}%"
    print(f"| {name:<35} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<9.2f} |")

# 边界策略
print("\n⚠️ 边界策略(65%<=WR<75% n>=20):")
for name, results in all_strategies.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 20 and 0.65 <= best["win_rate"] < 0.75:
            print(f"  • {name}: WR={best['win_rate']*100:.1f}% n={best['n']} hold={best['hold_period']} Sharpe={best['sharpe_ratio']:.1f}")

print(f"\n✅ ROUND 52 完成. {NOW}")
print("=" * 120)
