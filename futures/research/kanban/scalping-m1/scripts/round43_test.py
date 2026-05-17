#!/usr/bin/env python3
"""
Round 43 — M1/M5 Scalping 聚焦: 月度跟踪续跑 + ASIA新方向 + 形态跨周期验证

聚焦品种 (5 target): XAUUSD, XAGUSD, JP225, US500, US30
时间框架: M1 / M5

目标(next_actions from round42):
  1. XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第5月)+ASIA新阈值CB>=2+RSI<10月跟踪启动
  2. XAGUSD M5 EU 新阈值CB>=2+RSI<8 n积累; CB>=2+RSI<10确认
  4. US500 M5 EU CB>=5+RSI<14月度跟踪续跑(第3月)
  8. JP225 M1/M5 做多策略探索 (M1/M5级别)
  10. M1/M5形态+RSI联合策略跨周期验证

使用 grid_engine.py 进行系统化扫描
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grid_engine import run_grid, print_results_table
from data_loader import load_data, compute_indicators, list_available_symbols
import pandas as pd
import numpy as np
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

TARGET_SYMBOLS_M5 = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]
TARGET_SYMBOLS_M1 = ["XAUUSD", "XAGUSD", "US30"]  # M1 only for these

print("=" * 120)
print(f"ROUND 43 — M1/M5 Scalping Focused Scan — {NOW}")
print(f"Target: M1/M5 on XAUUSD XAGUSD JP225 US500 US30")
print("=" * 120)

# ═══════════════════════════════════════════════════════════════
# 1. M5 — 核心策略月度跟踪 (续跑 round42 的 best_known)
# ═══════════════════════════════════════════════════════════════

print("\n" + "─" * 120)
print("📊 PART 1: M5 CORE STRATEGIES MONTHLY TRACKING")
print("─" * 120)

m5_tracking = [
    # XAUUSD 双枪策略
    {"name": "XAU_EU_doublegun", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and hour>=9 and hour<12 and rsi14<18 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 20, 42, 55]},
    {"name": "XAU_US_doublegun", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and hour>=15 and hour<17 and rsi14<20 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 20, 55, 115]},
    # XAGUSD EU
    {"name": "XAG_EU_CB3_RSI10", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 20, 35]},
    {"name": "XAG_EU_CB2_RSI8", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 20, 35]},
    {"name": "XAG_EU_CB2_RSI10", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 20, 35]},
    # US500 EU
    {"name": "US500_EU_CB5_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 25]},
    {"name": "US500_EU_CB4_RSI14", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 25]},
    # JP225 M5 long
    {"name": "JP225_M5_CB4_RSI20", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "rsi14<20 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 20, 45, 135]},
    {"name": "JP225_M5_CB3_RSI20", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "rsi14<20 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 20, 45, 135]},
    # US30 M5 — 探索新策略
    {"name": "US30_M5_CB4_RSI14", "symbols": ["US30"], "timeframe": "M5",
     "entry_condition": "rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 20, 30, 55]},
]

all_m5_results = {}
for cfg in m5_tracking:
    try:
        res = run_grid(cfg)
        if res:
            all_m5_results[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

# Print summary table for M5 core strategies
print("\n📊 M5 Core Strategies — Best Hold Period per Strategy:\n")
print(f"| {'Strategy':<30} | {'Symbol':<8} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{'':->30}|{'':->8}|{'':->7}|{'':->6}|{'':->5}|{'':->8}|{'':->7}|")
for name, results in sorted(all_m5_results.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 5:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            print(f"| {name:<30} | {sym:<8} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<8} | {best['sharpe_ratio']:<7.2f} |")

# ═══════════════════════════════════════════════════════════════
# 2. XAUUSD M1 月度跟踪与ASIA探索
# ═══════════════════════════════════════════════════════════════

print("\n" + "─" * 120)
print("📊 PART 2: XAUUSD M1 EXTREME TRACKING + ASIA EXPLORATION")
print("─" * 120)

m1_tracking = [
    # XAUUSD M1 US extreme
    {"name": "XAU_M1_US_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_US_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # XAUUSD M1 EU extreme
    {"name": "XAU_M1_EU_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # XAUUSD M1 ASIA (新方向)
    {"name": "XAU_M1_ASIA_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "XAU_M1_ASIA_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # XAUUSD M1 ASIA 宽松
    {"name": "XAU_M1_ASIA_CB2_RSI12", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<12 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 20]},
    # 双极值联合
    {"name": "XAU_M1_DUAL_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "(session=='europe' or session=='us') and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # US30 M1 (已知)
    {"name": "US30_M1_EU_CB4_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "US30_M1_EU_CB3_RSI14", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
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
print(f"| {'Strategy':<28} | {'Symbol':<8} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{'':->28}|{'':->8}|{'':->7}|{'':->6}|{'':->5}|{'':->8}|{'':->7}|")
for name, results in sorted(all_m1_results.items()):
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 10 else 0)
        if best and best["n"] >= 5:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            print(f"| {name:<28} | {sym:<8} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<8} | {best['sharpe_ratio']:<7.2f} |")

# ═══════════════════════════════════════════════════════════════
# 3. M1/M5 新参数空间探索 — 连阴+RSI网格扫描
# ═══════════════════════════════════════════════════════════════

print("\n" + "─" * 120)
print("📊 PART 3: GRID SCAN — Consecutive Bear + RSI Combinations (M5)")
print("─" * 120)

# Test RSI thresholds
rsi_thresholds = [6, 8, 10, 12, 14, 16, 18, 20]
cb_thresholds = [1, 2, 3, 4, 5]
hold_range = [5, 10, 20, 35, 55]

grid_results = []
for sym in TARGET_SYMBOLS_M5:
    for cb in cb_thresholds:
        for rsi in rsi_thresholds:
            cfg = {
                "name": f"{sym}_M5_CB>={cb}_RSI<{rsi}",
                "symbols": [sym],
                "timeframe": "M5",
                "entry_condition": f"consecutive_bear>={cb} and rsi14<{rsi}",
                "direction": "long",
                "hold_periods": hold_range,
            }
            try:
                res = run_grid(cfg)
                if res and sym in res:
                    for r in res[sym]:
                        if r["n"] >= 10:
                            grid_results.append({
                                "symbol": sym,
                                "cb": cb,
                                "rsi": rsi,
                                "hold": r["hold_period"],
                                "wr": r["win_rate"],
                                "n": r["n"],
                                "avg_r": r["avg_return"],
                                "sharpe": r["sharpe_ratio"],
                            })
            except Exception as e:
                pass

# Sort and show top 30
grid_results.sort(key=lambda x: -x["wr"])
print(f"\nTop 30 M5 Consecutive Bear + RSI Combinations (n≥10):\n")
print(f"| {'Rank':<5} | {'Symbol':<8} | {'CB>=':<5} | {'RSI<':<5} | {'Hold':<5} | {'WR':<7} | {'n':<6} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{'':->5}|{'':->8}|{'':->5}|{'':->5}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|{'':->7}|")
for i, r in enumerate(grid_results[:30], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | {r['symbol']:<8} | CB>={r['cb']:<1}   | RSI<{r['rsi']:<2}  | {r['hold']:<5} | {wr:<7} | {r['n']:<6} | {ar:<8} | {r['sharpe']:<7.2f} |")

# ═══════════════════════════════════════════════════════════════
# 4. 做空探索 — M5 连阳+RSI高
# ═══════════════════════════════════════════════════════════════

print("\n" + "─" * 120)
print("📊 PART 4: SHORT EXPLORATION — Consecutive Bull + High RSI (M5)")
print("─" * 120)

# Test SHORT: consecutive_bull + RSI high
rsi_high_thresholds = [75, 80, 85]
cbull_thresholds = [2, 3, 4]

short_results = []
for sym in TARGET_SYMBOLS_M5:
    for cb in cbull_thresholds:
        for rsi in rsi_high_thresholds:
            cfg = {
                "name": f"{sym}_M5_SHORT_CBull>={cb}_RSI>{rsi}",
                "symbols": [sym],
                "timeframe": "M5",
                "entry_condition": f"consecutive_bull>={cb} and rsi14>{rsi}",
                "direction": "short",
                "hold_periods": [5, 10, 20, 35, 55],
            }
            try:
                res = run_grid(cfg)
                if res and sym in res:
                    for r in res[sym]:
                        if r["n"] >= 10:
                            short_results.append({
                                "symbol": sym,
                                "cbull": cb,
                                "rsi": rsi,
                                "hold": r["hold_period"],
                                "wr": r["win_rate"],
                                "n": r["n"],
                                "avg_r": r["avg_return"],
                                "sharpe": r["sharpe_ratio"],
                            })
            except Exception as e:
                pass

short_results.sort(key=lambda x: -x["wr"])
print(f"\nTop 15 M5 SHORT Combinations (n≥10):\n")
print(f"| {'Rank':<5} | {'Symbol':<8} | {'CBull>=':<7} | {'RSI>':<5} | {'Hold':<5} | {'WR':<7} | {'n':<6} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{'':->5}|{'':->8}|{'':->7}|{'':->5}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|{'':->7}|")
for i, r in enumerate(short_results[:15], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | {r['symbol']:<8} | CBull>={r['cbull']:<1}  | RSI>{r['rsi']:<2}  | {r['hold']:<5} | {wr:<7} | {r['n']:<6} | {ar:<8} | {r['sharpe']:<7.2f} |")

# ═══════════════════════════════════════════════════════════════
# 5. 时段细分探索 — ASIA/EU/US 对XAUUSD M1/M5
# ═══════════════════════════════════════════════════════════════

print("\n" + "─" * 120)
print("📊 PART 5: SESSION BREAKDOWN — XAUUSD M1/M5 by Session")
print("─" * 120)

session_grid = []
for tf in ["M1", "M5"]:
    for session in ["asia", "europe", "us"]:
        for cb in [2, 3, 4]:
            for rsi in [10, 14, 18]:
                cfg = {
                    "name": f"XAU_{tf}_{session}_CB>={cb}_RSI<{rsi}",
                    "symbols": ["XAUUSD"],
                    "timeframe": tf,
                    "entry_condition": f"session=='{session}' and consecutive_bear>={cb} and rsi14<{rsi}",
                    "direction": "long",
                    "hold_periods": [5, 10, 15, 30, 55],
                }
                try:
                    res = run_grid(cfg)
                    if res and "XAUUSD" in res:
                        for r in res["XAUUSD"]:
                            if r["n"] >= 10:
                                session_grid.append({
                                    "tf": tf, "session": session, "cb": cb, "rsi": rsi,
                                    "hold": r["hold_period"], "wr": r["win_rate"],
                                    "n": r["n"], "avg_r": r["avg_return"], "sharpe": r["sharpe_ratio"],
                                })
                except Exception as e:
                    pass

session_grid.sort(key=lambda x: -x["wr"])
print(f"\nTop 20 XAUUSD Session Breakdown (n≥10):\n")
print(f"| {'Rank':<5} | {'TF':<4} | {'Session':<8} | {'CB>=':<5} | {'RSI<':<5} | {'Hold':<5} | {'WR':<7} | {'n':<6} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{'':->5}|{'':->4}|{'':->8}|{'':->5}|{'':->5}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|{'':->7}|")
for i, r in enumerate(session_grid[:20], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | {r['tf']:<4} | {r['session']:<8} | CB>={r['cb']:<1}   | RSI<{r['rsi']:<2}  | {r['hold']:<5} | {wr:<7} | {r['n']:<6} | {ar:<8} | {r['sharpe']:<7.2f} |")

# ═══════════════════════════════════════════════════════════════
# 6. XAUUSD 做空探索 — M1/M5
# ═══════════════════════════════════════════════════════════════

print("\n" + "─" * 120)
print("📊 PART 6: XAUUSD SHORT — M1/M5 Session Exploration")
print("─" * 120)

xau_short_results = []
for tf in ["M1", "M5"]:
    for session in ["asia", "europe", "us"]:
        for cb in [2, 3, 4]:
            for rsi in [75, 80, 85]:
                cfg = {
                    "name": f"XAU_{tf}_{session}_SHORT_CBull>={cb}_RSI>{rsi}",
                    "symbols": ["XAUUSD"],
                    "timeframe": tf,
                    "entry_condition": f"session=='{session}' and consecutive_bull>={cb} and rsi14>{rsi}",
                    "direction": "short",
                    "hold_periods": [3, 5, 10, 20, 35],
                }
                try:
                    res = run_grid(cfg)
                    if res and "XAUUSD" in res:
                        for r in res["XAUUSD"]:
                            if r["n"] >= 8:
                                xau_short_results.append({
                                    "tf": tf, "session": session, "cbull": cb, "rsi": rsi,
                                    "hold": r["hold_period"], "wr": r["win_rate"],
                                    "n": r["n"], "avg_r": r["avg_return"],
                                })
                except Exception as e:
                    pass

xau_short_results.sort(key=lambda x: -x["wr"])
print(f"\nTop 10 XAUUSD SHORT (n≥8):\n")
print(f"| {'Rank':<5} | {'TF':<4} | {'Session':<8} | {'CBull>=':<7} | {'RSI>':<5} | {'Hold':<5} | {'WR':<7} | {'n':<6} | {'avg%':<8} |")
print(f"|{'':->5}|{'':->4}|{'':->8}|{'':->7}|{'':->5}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|")
for i, r in enumerate(xau_short_results[:10], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | {r['tf']:<4} | {r['session']:<8} | CBull>={r['cbull']:<1}  | RSI>{r['rsi']:<2}  | {r['hold']:<5} | {wr:<7} | {r['n']:<6} | {ar:<8} |")

# ═══════════════════════════════════════════════════════════════
# SUMMARY & NEXT ACTIONS
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 120)
print("📋 ROUND 43 SUMMARY — Key Findings")
print("=" * 120)

# Collect best findings
all_findings = []

# From grid scan (WR >= 75%, n >= 20)
for r in grid_results:
    if r["wr"] >= 0.75 and r["n"] >= 20:
        all_findings.append(r)

# From short scan
for r in short_results:
    if r["wr"] >= 0.70 and r["n"] >= 15:
        all_findings.append(r)

# From session breakdown
for r in session_grid:
    if r["wr"] >= 0.75 and r["n"] >= 20:
        all_findings.append(r)

# From m1/m5 tracking
for name, results in all_m5_results.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"])
        if best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append({
                "symbol": sym, "name": name, "hold": best["hold_period"],
                "wr": best["win_rate"], "n": best["n"], "avg_r": best["avg_return"],
            })

all_findings.sort(key=lambda x: -x["wr"])
print(f"\nTop Confirmable Findings (WR≥75% or n≥15 WR≥70%): {len(all_findings)}\n")

print("\n" + "=" * 120)
print(f"✅ ROUND 43 COMPLETE — {NOW}")
print("=" * 120)
