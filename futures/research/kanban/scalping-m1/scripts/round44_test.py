#!/usr/bin/env python3
"""
Round 44 — M1/M5 Scalping 月度跟踪续跑 + RSI<6 跨周期验证 + 美盘深度扫描

聚焦:
  1. XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第6月)+EU极值持续监控
  2. XAGUSD M5 RSI<6新发现跨周期验证+频率统计
  3. XAGUSD M5 EU CB>=2+RSI<8 n积累监测
  4. US500 M5 EU CB>=5+RSI<14 月度跟踪续跑(第4月)+正式纳入
  5. XAUUSD M1 ASIA CB>=3+RSI<10 跨周期验证(第2月)
  6. US30 M1 EU 持续积累
  7. M5全品种窄扫描: RSI<6/8/10 + 时段过滤 + 小时过滤
  8. XAUUSD M5 美盘时段深度扫描(hour=15-21, CB+RSI精细网格)
  9. 做空策略放弃确认
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
print(f"ROUND 44 — M1/M5 Scalping Focused Scan — {NOW}")
print(f"Target: M1/M5 on XAUUSD XAGUSD JP225 US500 US30")
print("=" * 120)

# =====================================================
# PART 1: 核心策略月度跟踪 (续跑)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 1: M5 CORE STRATEGIES MONTHLY TRACKING (续跑)")
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
    # JP225 M5
    {"name": "JP225_M5_CB4_RSI20", "symbols": ["JP225"], "timeframe": "M5",
     "entry_condition": "rsi14<20 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 20, 45, 135]},
    # US30 M5
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

# =====================================================
# PART 2: XAUUSD M1 月度跟踪 (第6月) + ASIA第2月
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 2: XAUUSD M1 MONTHLY TRACKING (第6月) + EU/ASIA")
print("─" * 120)

m1_tracking = [
    # US CB>=3+RSI<10 第6月跟踪
    {"name": "XAU_M1_US_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_US_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU 极值
    {"name": "XAU_M1_EU_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # ASIA 第2月跟踪
    {"name": "XAU_M1_ASIA_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "XAU_M1_ASIA_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "XAU_M1_ASIA_CB2_RSI12", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<12 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 20]},
    # 双极值联合
    {"name": "XAU_M1_DUAL_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "(session=='europe' or session=='us') and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # US30 M1 EU
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

# =====================================================
# PART 3: XAGUSD M5 RSI<6 跨周期验证 + 频率统计
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 3: XAGUSD M5 RSI<6 CROSS-VALIDATION + FREQUENCY ANALYSIS")
print("─" * 120)

# Load XAGUSD M5 data for frequency analysis
xag_data = load_data("M5", ["XAGUSD"])
if xag_data:
    xag_df = compute_indicators(xag_data["XAGUSD"])
    total_candles = len(xag_df)
    # Count RSI<6 signals
    rsi6_signals = (xag_df["rsi14"] < 6).sum()
    # Count by CB threshold
    for cb in [1, 2, 3, 4, 5]:
        sigs = ((xag_df["rsi14"] < 6) & (xag_df["consecutive_bear"] >= cb)).sum()
        print(f"  XAGUSD M5 RSI<6 + CB>={cb}: {sigs} signals in {total_candles} candles ({sigs/total_candles*100:.2f}% frequency, ~1 per {total_candles//max(sigs,1)} candles)")
    
    # Monthly breakdown
    print("\n  Monthly signal count for XAGUSD M5 RSI<6 + CB>=1:")
    monthly = xag_df[xag_df["rsi14"] < 6].resample("ME").size()
    for dt, cnt in monthly.items():
        print(f"    {dt.strftime('%Y-%m')}: {cnt} signals")
    print(f"    Average: {monthly.mean():.1f} signals/month")
    print(f"    Std: {monthly.std():.1f} signals/month")

    # Session breakdown for RSI<6
    print("\n  Session breakdown for XAGUSD M5 RSI<6:")
    for sess in ["asia", "europe", "us"]:
        cnt = ((xag_df["rsi14"] < 6) & (xag_df["session"] == sess)).sum()
        print(f"    {sess}: {cnt} signals ({cnt/total_candles*100:.2f}%)")

# Grid scan: RSI<6 + CB + session filters
print("\n  Grid: RSI<6 + CB thresholds + Session filters:\n")
rsi6_grid = []
for sess in ["asia", "europe", "us", None]:
    for cb in [1, 2, 3, 4, 5]:
        cond = f"consecutive_bear>={cb} and rsi14<6"
        if sess:
            cond += f" and session=='{sess}'"
        name = f"XAG_M5_RSI6_CB>={cb}" + (f"_{sess}" if sess else "_ALL")
        cfg = {
            "name": name, "symbols": ["XAGUSD"], "timeframe": "M5",
            "entry_condition": cond, "direction": "long",
            "hold_periods": [5, 10, 20, 35, 55],
        }
        try:
            res = run_grid(cfg)
            if res and "XAGUSD" in res:
                for r in res["XAGUSD"]:
                    if r["n"] >= 10:
                        rsi6_grid.append({
                            "session": sess or "ALL", "cb": cb,
                            "hold": r["hold_period"], "wr": r["win_rate"],
                            "n": r["n"], "avg_r": r["avg_return"], "sharpe": r["sharpe_ratio"],
                        })
        except Exception as e:
            pass

rsi6_grid.sort(key=lambda x: -x["wr"])
print(f"| {'Rank':<5} | {'Session':<8} | {'CB>=':<5} | {'Hold':<5} | {'WR':<7} | {'n':<6} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{'':->5}|{'':->8}|{'':->5}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|{'':->7}|")
for i, r in enumerate(rsi6_grid[:20], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | {r['session']:<8} | CB>={r['cb']:<1}   | {r['hold']:<5} | {wr:<7} | {r['n']:<6} | {ar:<8} | {r['sharpe']:<7.2f} |")

# =====================================================
# PART 4: M5 全品种窄扫描 — RSI<6/8/10 + 时段过滤
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 4: M5 NARROW SCAN — RSI low + Session + Hour filters")
print("─" * 120)

narrow_results = []
for sym in TARGET_M5:
    for sess in ["asia", "europe", "us"]:
        for rsi in [6, 8, 10]:
            for cb in [1, 2, 3, 4, 5]:
                cond = f"session=='{sess}' and rsi14<{rsi} and consecutive_bear>={cb}"
                cfg = {
                    "name": f"{sym}_M5_{sess}_RSI<{rsi}_CB>={cb}",
                    "symbols": [sym], "timeframe": "M5",
                    "entry_condition": cond, "direction": "long",
                    "hold_periods": [5, 10, 15, 30, 55],
                }
                try:
                    res = run_grid(cfg)
                    if res and sym in res:
                        for r in res[sym]:
                            if r["n"] >= 10:
                                narrow_results.append({
                                    "symbol": sym, "session": sess, "rsi": rsi, "cb": cb,
                                    "hold": r["hold_period"], "wr": r["win_rate"],
                                    "n": r["n"], "avg_r": r["avg_return"], "sharpe": r["sharpe_ratio"],
                                })
                except Exception as e:
                    pass

narrow_results.sort(key=lambda x: -x["wr"])
print(f"\nTop 30 M5 Narrow Scan (n≥10):\n")
print(f"| {'Rank':<5} | {'Symbol':<8} | {'Session':<8} | {'RSI<':<5} | {'CB>=':<5} | {'Hold':<5} | {'WR':<7} | {'n':<6} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{'':->5}|{'':->8}|{'':->8}|{'':->5}|{'':->5}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|{'':->7}|")
for i, r in enumerate(narrow_results[:30], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | {r['symbol']:<8} | {r['session']:<8} | RSI<{r['rsi']:<2}  | CB>={r['cb']:<1}   | {r['hold']:<5} | {wr:<7} | {r['n']:<6} | {ar:<8} | {r['sharpe']:<7.2f} |")

# =====================================================
# PART 5: XAUUSD M5 美盘深度扫描 hour=15-21
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 5: XAUUSD M5 US SESSION DEEP SCAN (hour=15-21)")
print("─" * 120)

us_hour_results = []
for hr_start in range(15, 22):
    for cb in [1, 2, 3, 4, 5]:
        for rsi in [6, 8, 10, 12, 14, 16, 18, 20]:
            cond = f"hour=={hr_start} and rsi14<{rsi} and consecutive_bear>={cb}"
            cfg = {
                "name": f"XAU_M5_H{hr_start}_CB>={cb}_RSI<{rsi}",
                "symbols": ["XAUUSD"], "timeframe": "M5",
                "entry_condition": cond, "direction": "long",
                "hold_periods": [5, 10, 15, 30, 55],
            }
            try:
                res = run_grid(cfg)
                if res and "XAUUSD" in res:
                    for r in res["XAUUSD"]:
                        if r["n"] >= 10:
                            us_hour_results.append({
                                "hour": hr_start, "cb": cb, "rsi": rsi,
                                "hold": r["hold_period"], "wr": r["win_rate"],
                                "n": r["n"], "avg_r": r["avg_return"], "sharpe": r["sharpe_ratio"],
                            })
            except Exception as e:
                pass

us_hour_results.sort(key=lambda x: -x["wr"])
print(f"\nTop 20 XAUUSD M5 US Hour Scan (n≥10):\n")
print(f"| {'Rank':<5} | {'Hour':<5} | {'CB>=':<5} | {'RSI<':<5} | {'Hold':<5} | {'WR':<7} | {'n':<6} | {'avg%':<8} | {'Sharpe':<7} |")
print(f"|{'':->5}|{'':->5}|{'':->5}|{'':->5}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|{'':->7}|")
for i, r in enumerate(us_hour_results[:20], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | H{r['hour']:<2}   | CB>={r['cb']:<1}   | RSI<{r['rsi']:<2}  | {r['hold']:<5} | {wr:<7} | {r['n']:<6} | {ar:<8} | {r['sharpe']:<7.2f} |")

# =====================================================
# PART 6: XAUUSD M1/M5 做空确认扫描 (放弃确认)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 6: SHORT CONFIRMATION SCAN (确认放弃做空)")
print("─" * 120)

short_results = []
for sym in TARGET_M5:
    for tf in ["M1", "M5"]:
        for cb in [2, 3, 4]:
            for rsi in [75, 80, 85]:
                cond = f"consecutive_bull>={cb} and rsi14>{rsi}"
                cfg = {
                    "name": f"{sym}_{tf}_SHORT_CBull>={cb}_RSI>{rsi}",
                    "symbols": [sym], "timeframe": tf,
                    "entry_condition": cond, "direction": "short",
                    "hold_periods": [3, 5, 10, 20, 35],
                }
                try:
                    res = run_grid(cfg)
                    if res and sym in res:
                        for r in res[sym]:
                            if r["n"] >= 10:
                                short_results.append({
                                    "symbol": sym, "tf": tf, "cbull": cb, "rsi": rsi,
                                    "hold": r["hold_period"], "wr": r["win_rate"],
                                    "n": r["n"], "avg_r": r["avg_return"],
                                })
                except Exception as e:
                    pass

short_results.sort(key=lambda x: -x["wr"])
print(f"\nTop 15 SHORT (n≥10) — 验证是否仍有>65%:\n")
print(f"| {'Rank':<5} | {'Symbol':<8} | {'TF':<4} | {'CBull>=':<7} | {'RSI>':<5} | {'Hold':<5} | {'WR':<7} | {'n':<6} | {'avg%':<8} |")
print(f"|{'':->5}|{'':->8}|{'':->4}|{'':->7}|{'':->5}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|")
for i, r in enumerate(short_results[:15], 1):
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%"
    print(f"| {i:<5} | {r['symbol']:<8} | {r['tf']:<4} | CBull>={r['cbull']:<1}  | RSI>{r['rsi']:<2}  | {r['hold']:<5} | {wr:<7} | {r['n']:<6} | {ar:<8} |")

# Check if any short strategy has WR >= 65%
best_short_wr = max([r["wr"] for r in short_results], default=0)
print(f"\n  Best SHORT WR across all: {best_short_wr*100:.1f}%")
if best_short_wr < 0.65:
    print("  ✅ 确认: 无做空策略WR≥65%, 放弃做空方向合理。")
else:
    print("  ⚠️ 发现WR≥65%做空策略, 需进一步评估！")

# =====================================================
# SUMMARY
# =====================================================
print("\n" + "=" * 120)
print("📋 ROUND 44 SUMMARY — Key Findings")
print("=" * 120)

# Collect all findings with WR>=70%
all_findings = []

# From tracking
for name, results in all_m5_results.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"])
        if best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append({
                "symbol": sym, "name": name, "hold": best["hold_period"],
                "wr": best["win_rate"], "n": best["n"], "avg_r": best["avg_return"],
            })

for name, results in all_m1_results.items():
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"])
        if best["n"] >= 10 and best["win_rate"] >= 0.70:
            all_findings.append({
                "symbol": sym, "name": name, "hold": best["hold_period"],
                "wr": best["win_rate"], "n": best["n"], "avg_r": best["avg_return"],
            })

# From narrow scan
for r in narrow_results:
    if r["wr"] >= 0.75 and r["n"] >= 20:
        all_findings.append(r)

# From XAG RSI6 scan
for r in rsi6_grid:
    if r["wr"] >= 0.75 and r["n"] >= 20:
        all_findings.append(r)

# From US hour scan  
for r in us_hour_results:
    if r["wr"] >= 0.75 and r["n"] >= 20:
        all_findings.append(r)

all_findings.sort(key=lambda x: -x["wr"])
print(f"\nTop Confirmable Findings (WR≥75% n≥20, or WR≥70% n≥10 from tracking): {len(all_findings)}\n")
print(f"| {'Rank':<5} | {'Symbol/Name':<35} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<8} |")
print(f"|{'':->5}|{'':->35}|{'':->7}|{'':->6}|{'':->5}|{'':->8}|")
for i, r in enumerate(all_findings[:20], 1):
    sym = r.get("name", r.get("symbol", "?"))
    wr = f"{r['wr']*100:.1f}%"
    ar = f"{r['avg_r']*100:.3f}%" if "avg_r" in r else "-"
    n = r.get("n", 0)
    h = r.get("hold", 0)
    print(f"| {i:<5} | {sym:<35} | {wr:<7} | {n:<6} | {h:<5} | {ar:<8} |")

print("\n" + "=" * 120)
print(f"✅ ROUND 44 COMPLETE — {NOW}")
print("=" * 120)
