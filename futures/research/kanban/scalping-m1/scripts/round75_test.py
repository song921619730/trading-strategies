#!/usr/bin/env python3
"""
Round 75 — M1/M5 Scalping 第37/35/33/28月跟踪 + H1/M30探索
(数据截至: 2026-05-14 06:29 UTC)

聚焦:
  1. XAUUSD M1 EU/US 第37月常规跟踪 + EU_CB2第29月 + EU_RSI8第27月 + CB3+RSI7第26月 + CB2+RSI7第26月
  2. XAUUSD M5 US RSI<6 冻结归档跳过(季度检查8月)
  3. XAGUSD M5 RSI<5 ALL第28月跟踪 + RSI<4第23月跟踪 + RSI4深度hold=70第23月跟踪
  4. US500 M5 EU 第35月常规跟踪(关注是否继续恶化)
  5. XAUUSD M1 ASIA 第33月跟踪(重点验证R74 re-run发现的WR下降)
  6. US30 M1 EU 第28月跟踪
  7. XAUUSD M5 H15/H19冻结归档跳过
  8. XAGUSD M5 信号频率更新
  9. JP225 M5最低权重监控
  10. H1/M30新探索 + XAU M5边界跟踪

⚠️ 命名约定: "RSI<X" = rsi14 < X (RSI14低于阈值X, 非RSI周期X)
"""
import sys, os, json, logging, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grid_engine import run_grid
from data_loader import load_data, compute_indicators, list_available_symbols
import pandas as pd
import numpy as np
from datetime import datetime

logging.basicConfig(level=logging.WARNING, format='%(asctime)s [%(levelname)s] %(message)s')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

print("=" * 120)
print(f"ROUND 75 — M1/M5 Scalping 第37/35/33/28月跟踪 + H1/M30探索 — {NOW}")
print(f"Target: M1/M5/H1/M30 on XAUUSD XAGUSD JP225 US500 US30")
print("=" * 120)

# =====================================================
# CACHED indicator computation
# =====================================================
_cache = {}
def get_data(symbol, timeframe):
    key = (symbol, timeframe)
    if key not in _cache:
        t0 = time.time()
        data = load_data(timeframe=timeframe, symbols=[symbol])
        if symbol in data:
            _cache[key] = compute_indicators(data[symbol])
            print(f"  ✅ Computed {symbol} {timeframe}: {len(_cache[key])} rows ({time.time()-t0:.1f}s)")
        else:
            print(f"  ⚠ No data for {symbol} {timeframe}")
            _cache[key] = None
    return _cache[key]

def run_grid_cached(cfg, min_n=3):
    timeframe = cfg["timeframe"]
    symbols = cfg["symbols"]
    entry_condition = cfg.get("entry_condition", "")
    direction = cfg.get("direction", "long")
    hold_periods = cfg.get("hold_periods", [1, 3, 5, 10])
    periods_per_year = {"M1": 360000, "M5": 72000, "M15": 24000, "M30": 12000, "H1": 6000}.get(timeframe, 72000)

    results = {}
    for sym in symbols:
        df = get_data(sym, timeframe)
        if df is None or df.empty:
            continue
        try:
            mask = df.eval(entry_condition)
        except Exception as e:
            print(f"    ⚠ Condition FAILED [{cfg['name']}]: {e}")
            return {sym: []}

        entry_prices = df.loc[mask, "close"].values
        entry_indices = df.index[mask]
        n_signals = len(entry_prices)
        if n_signals < min_n:
            print(f"    ℹ️  {cfg['name']} {sym}: only {n_signals} signals (need {min_n})")
            return {sym: []}

        sym_results = []
        for hold in hold_periods:
            returns = []
            for i in range(n_signals):
                entry_idx = entry_indices[i]
                entry_price = entry_prices[i]
                raw_pos = df.index.get_loc(entry_idx)
                pos = raw_pos.start if isinstance(raw_pos, slice) else int(raw_pos)
                exit_pos = pos + hold
                if exit_pos >= len(df):
                    continue
                exit_price = df.iloc[exit_pos]["close"]
                if direction == "long":
                    ret = (exit_price - entry_price) / entry_price
                else:
                    ret = (entry_price - exit_price) / entry_price
                returns.append(ret)

            returns_arr = np.array(returns, dtype=float)
            n2 = len(returns_arr)
            if n2 < min_n:
                continue
            win_rate = float((returns_arr > 0).mean())
            avg_return = float(returns_arr.mean())
            std = float(returns_arr.std()) if returns_arr.std() > 0 else 1e-10
            sharpe = (avg_return / std) * np.sqrt(periods_per_year / hold) if avg_return != 0 else 0
            cum = np.cumprod(1 + returns_arr)
            peak = np.maximum.accumulate(cum)
            dd = (peak - cum) / peak
            max_dd = float(dd.max()) if len(dd) > 0 else 0.0
            sym_results.append({
                "hold_period": hold, "n": n2, "win_rate": win_rate,
                "avg_return": avg_return, "sharpe_ratio": sharpe, "max_drawdown": max_dd
            })
        if sym_results:
            results[sym] = sym_results
            best = max(sym_results, key=lambda r: r["win_rate"])
            print(f"  📊 {cfg['name']}: best hold={best['hold_period']} WR={best['win_rate']*100:.1f}% n={best['n']} Sharpe={best['sharpe_ratio']:.2f} (signals={n_signals})")
    return results

def print_table(name_results_map, min_n=3, title="Results", prev_refs=None):
    rows = []
    for name, results in name_results_map.items():
        for sym, sym_res in results.items():
            best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= min_n else 0)
            if best and best["n"] >= min_n:
                rows.append((name, sym, best))
    if not rows:
        print(f"  (no results meeting criteria)")
        return
    rows.sort(key=lambda x: -x[2]["win_rate"])
    header = f"| {'Strategy':<38} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<9} | {'Ref':<20} |"
    sep = "-" * len(header)
    print(f"\n{title}:")
    print(header)
    print(sep)
    for name, sym, best in rows:
        wr = f"{best['win_rate']*100:.1f}%"
        ar = f"{best['avg_return']*100:.3f}%"
        prev = prev_refs.get(name, "") if prev_refs else ""
        print(f"| {name:<38} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<9.2f} | {prev:<20} |")
    return rows

# Standard hold lists
M1_HOLDS = [5, 10, 15, 20, 25, 30, 40, 50, 55, 60, 70, 80]
M5_HOLDS = [5, 10, 15, 20, 25, 30, 40, 50, 55, 60, 70, 80, 100, 120]

# ════════════════════════════════════════════════════════════
# PART 1: XAUUSD M1 — 第37月常规跟踪(US/EU)
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 1: XAUUSD M1 — 第37月常规跟踪(US/EU) + 扩展")
print(f"{'─'*120}")

xau_m1_cfgs = [
    # US session
    {"name": "XAU_M1_US_CB3_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3", "hold_periods": M1_HOLDS},
    {"name": "XAU_M1_US_CB2_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=2", "hold_periods": M1_HOLDS},
    # EU session
    {"name": "XAU_M1_EU_CB3_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3", "hold_periods": M1_HOLDS},
    {"name": "XAU_M1_EU_CB2_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=2", "hold_periods": M1_HOLDS},
    # Dual (EU+US)
    {"name": "XAU_M1_DUAL_CB3_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "(session=='europe' or session=='us') and rsi14<10 and consecutive_bear>=3", "hold_periods": M1_HOLDS},
    # EU RSI8 (rsi14<8)
    {"name": "XAU_M1_EU_CB3_RSI8", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=3", "hold_periods": M1_HOLDS},
    {"name": "XAU_M1_EU_CB2_RSI8", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=2", "hold_periods": M1_HOLDS},
    # EU RSI7 (rsi14<7)
    {"name": "XAU_M1_EU_CB3_RSI7", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<7 and consecutive_bear>=3", "hold_periods": M1_HOLDS},
    {"name": "XAU_M1_EU_CB2_RSI7", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<7 and consecutive_bear>=2", "hold_periods": M1_HOLDS},
    # EU RSI5 (rsi14<5)
    {"name": "XAU_M1_EU_CB2_RSI5", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<5 and consecutive_bear>=2", "hold_periods": M1_HOLDS},
    # US CB4 RSI12 (rsi14<12)
    {"name": "XAU_M1_US_CB4_RSI12", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4", "hold_periods": M1_HOLDS},
]

ALL_M1_RESULTS = {}
for cfg in xau_m1_cfgs:
    print(f"  🔍 {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_M1_RESULTS[cfg['name']] = res

# ════════════════════════════════════════════════════════════
# PART 2: XAUUSD M5 US RSI<6 — ❄️ 跳过
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 2: XAUUSD M5 US RSI<6 — ❄️ 跳过(季度检查2026-08)")

# ════════════════════════════════════════════════════════════
# PART 3: XAGUSD M5 — RSI<5/RSI<4/RSI<6/RSI<8
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 3: XAGUSD M5 RSI<5 ALL第28月 + RSI<4第23月跟踪")
print(f"{'─'*120}")

xag_m5_cfgs = [
    # RSI<4 (rsi14<4) — 第23月
    {"name": "XAG_M5_RSI4_CB1_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<4 and consecutive_bear>=1", "hold_periods": M5_HOLDS},
    {"name": "XAG_M5_RSI4_CB2_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<4 and consecutive_bear>=2", "hold_periods": M5_HOLDS},
    # RSI<5 (rsi14<5) — 第28月
    {"name": "XAG_M5_RSI5_CB1_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<5 and consecutive_bear>=1", "hold_periods": M5_HOLDS},
    {"name": "XAG_M5_RSI5_CB2_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<5 and consecutive_bear>=2", "hold_periods": M5_HOLDS},
    # RSI<6 (rsi14<6) — 参考
    {"name": "XAG_M5_RSI6_CB1_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<6 and consecutive_bear>=1", "hold_periods": M5_HOLDS},
    {"name": "XAG_M5_RSI6_CB2_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<6 and consecutive_bear>=2", "hold_periods": M5_HOLDS},
    {"name": "XAG_M5_RSI6_CB3_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<6 and consecutive_bear>=3", "hold_periods": M5_HOLDS},
    # RSI<8 (rsi14<8) — 参考
    {"name": "XAG_M5_RSI8_CB1_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<8 and consecutive_bear>=1", "hold_periods": M5_HOLDS},
    {"name": "XAG_M5_RSI8_CB2_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<8 and consecutive_bear>=2", "hold_periods": M5_HOLDS},
    {"name": "XAG_M5_RSI8_CB3_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<8 and consecutive_bear>=3", "hold_periods": M5_HOLDS},
]

ALL_XAG_RESULTS = {}
for cfg in xag_m5_cfgs:
    print(f"  🔍 {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_XAG_RESULTS[cfg['name']] = res

# ════════════════════════════════════════════════════════════
# PART 4: US500 M5 EU 第35月常规跟踪
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 4: US500 M5 EU 第35月常规跟踪")
print(f"{'─'*120}")

us500_m5_cfgs = [
    {"name": "US500_EU_CB4_RSI14", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4", "hold_periods": M5_HOLDS},
    {"name": "US500_EU_CB5_RSI14", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=5", "hold_periods": M5_HOLDS},
    {"name": "US500_EU_CB6_RSI14", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=6", "hold_periods": M5_HOLDS},
    {"name": "US500_EU_CB5_RSI12", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5", "hold_periods": M5_HOLDS},
    {"name": "US500_EU_CB5_RSI10", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=5", "hold_periods": M5_HOLDS},
    {"name": "US500_EU_CB6_RSI12", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=6", "hold_periods": M5_HOLDS},
]
ALL_US500_RESULTS = {}
for cfg in us500_m5_cfgs:
    print(f"  🔍 {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_US500_RESULTS[cfg['name']] = res

# ════════════════════════════════════════════════════════════
# PART 5: XAUUSD M1 ASIA 第33月跟踪 ⚠️重点验证
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 5: XAUUSD M1 ASIA 第33月跟踪 ⚠️重点验证(R74 re-run WR下降)")
print(f"{'─'*120}")

asia_m1_cfgs = [
    {"name": "XAU_M1_ASIA_CB3_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=3",
     "hold_periods": [1, 3, 5, 10, 15, 20, 25, 30]},
    {"name": "XAU_M1_ASIA_CB2_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=2",
     "hold_periods": [1, 3, 5, 10, 15, 20, 25, 30]},
    {"name": "XAU_M1_ASIA_CB4_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=4",
     "hold_periods": [1, 3, 5, 10, 15, 20, 25, 30]},
]
ALL_ASIA_RESULTS = {}
for cfg in asia_m1_cfgs:
    print(f"  🔍 {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_ASIA_RESULTS[cfg['name']] = res

# ════════════════════════════════════════════════════════════
# PART 6: US30 M1 EU 第28月跟踪
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 6: US30 M1 EU 第28月跟踪")
print(f"{'─'*120}")

us30_m1_cfgs = [
    {"name": "US30_EU_CB4_RSI14", "timeframe": "M1", "symbols": ["US30"],
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4", "hold_periods": M1_HOLDS},
    {"name": "US30_EU_CB5_RSI14", "timeframe": "M1", "symbols": ["US30"],
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=5", "hold_periods": M1_HOLDS},
    {"name": "US30_EU_CB4_RSI12", "timeframe": "M1", "symbols": ["US30"],
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=4", "hold_periods": M1_HOLDS},
    {"name": "US30_EU_CB5_RSI12", "timeframe": "M1", "symbols": ["US30"],
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5", "hold_periods": M1_HOLDS},
    {"name": "US30_EU_CB4_RSI10", "timeframe": "M1", "symbols": ["US30"],
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=4", "hold_periods": M1_HOLDS},
    {"name": "US30_EU_CB6_RSI12", "timeframe": "M1", "symbols": ["US30"],
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=6", "hold_periods": M1_HOLDS},
]
ALL_US30_RESULTS = {}
for cfg in us30_m1_cfgs:
    print(f"  🔍 {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_US30_RESULTS[cfg['name']] = res

# ════════════════════════════════════════════════════════════
# PART 7: XAUUSD M5 H15/H19 — ❄️ 跳过
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 7: XAUUSD M5 H15/H19 — ❄️ 跳过(季度检查8月)")

# ════════════════════════════════════════════════════════════
# PART 8: XAGUSD M5 信号频率检测
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 8: XAGUSD M5 信号频率检测")
print(f"{'─'*120}")

xag_m5 = get_data("XAGUSD", "M5")
if xag_m5 is not None:
    total_bars = len(xag_m5)
    years = total_bars / 72000  # M5 bars per year ~72000
    rsi_conds = {
        "RSI14<4 CB1": "rsi14<4 and consecutive_bear>=1",
        "RSI14<4 CB2": "rsi14<4 and consecutive_bear>=2",
        "RSI14<5 CB1": "rsi14<5 and consecutive_bear>=1",
        "RSI14<5 CB2": "rsi14<5 and consecutive_bear>=2",
        "RSI14<6 CB1": "rsi14<6 and consecutive_bear>=1",
        "RSI14<6 CB2": "rsi14<6 and consecutive_bear>=2",
    }
    print(f"  📅 数据: {total_bars} bars ≈ {years:.1f}年")
    for label, cond in rsi_conds.items():
        try:
            n = int(xag_m5.eval(cond).sum())
            freq_yr = n / years if years > 0 else 0
            freq_mo = freq_yr / 12
            print(f"  📈 {label:<20}: {n}信号 = {freq_yr:.1f}次/年 ({freq_mo:.1f}次/月)")
        except Exception as e:
            print(f"  ⚠ {label}: {e}")

# ════════════════════════════════════════════════════════════
# PART 9: JP225 M5最低权重监控
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 9: JP225 M5最低权重监控")
print(f"{'─'*120}")

jp225_m5_cfgs = [
    {"name": "JP225_M5_US_CB3_RSI10", "timeframe": "M5", "symbols": ["JP225"],
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3", "hold_periods": M5_HOLDS},
    {"name": "JP225_M5_US_CB4_RSI10", "timeframe": "M5", "symbols": ["JP225"],
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=4", "hold_periods": M5_HOLDS},
    {"name": "JP225_M5_US_CB5_RSI12", "timeframe": "M5", "symbols": ["JP225"],
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=5", "hold_periods": M5_HOLDS},
    {"name": "JP225_M5_EU_CB3_RSI10", "timeframe": "M5", "symbols": ["JP225"],
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3", "hold_periods": M5_HOLDS},
]
ALL_JP225_RESULTS = {}
for cfg in jp225_m5_cfgs:
    print(f"  🔍 {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_JP225_RESULTS[cfg['name']] = res

# ════════════════════════════════════════════════════════════
# PART 10: 新探索
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 10: 新探索")
print(f"{'─'*120}")

# 10a: XAG M5 RSI4深度hold=70
print("\n🔍 10a: XAG M5 RSI<4 CB1 DEEP hold=70 第23月确认")
xag_deep_cfgs = [
    {"name": "XAG_M5_RSI4_CB1_DEEP", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<4 and consecutive_bear>=1", "hold_periods": [55, 60, 70, 80, 100]},
    {"name": "XAG_M5_RSI4_CB2_DEEP", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<4 and consecutive_bear>=2", "hold_periods": [55, 60, 70, 80, 100]},
]
XAG_DEEP_RESULTS = {}
for cfg in xag_deep_cfgs:
    print(f"  🔍 {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        XAG_DEEP_RESULTS[cfg['name']] = res

# 10b: XAU M5边界跟踪
print("\n🔍 10b: XAU M5 边界跟踪(US_CB3_RSI15)")
xau_m5_boundary_cfgs = [
    {"name": "XAU_M5_US_CB3_RSI15", "timeframe": "M5", "symbols": ["XAUUSD"],
     "entry_condition": "session=='us' and rsi14<15 and consecutive_bear>=3", "hold_periods": M5_HOLDS},
    {"name": "XAU_M5_US_CB4_RSI12", "timeframe": "M5", "symbols": ["XAUUSD"],
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4", "hold_periods": M5_HOLDS},
]
XAU_M5_BOUNDARY_RESULTS = {}
for cfg in xau_m5_boundary_cfgs:
    print(f"  🔍 {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        XAU_M5_BOUNDARY_RESULTS[cfg['name']] = res

# 10c: Data source check
print("\n🔍 10c: 数据源状态检查")
for tf in ["M5", "M1"]:
    data = load_data(timeframe=tf, symbols=["XAUUSD", "XAGUSD", "US500", "US30", "JP225"])
    available = [s for s in data.keys()]
    print(f"  {tf}可用: {len(available)}")
    for sym in ["XAUUSD", "XAGUSD", "US500", "US30", "JP225"]:
        if sym in data:
            df = data[sym]
            print(f"    {sym}: {df.index[0]} → {df.index[-1]} ({len(df)}行)")

# ════════════════════════════════════════════════════════════
# COMPILE ALL RESULTS & SUMMARY
# ════════════════════════════════════════════════════════════
ALL_RESULTS = {}
for d in [ALL_M1_RESULTS, ALL_XAG_RESULTS, ALL_US500_RESULTS, ALL_ASIA_RESULTS,
          ALL_US30_RESULTS, ALL_JP225_RESULTS, XAG_DEEP_RESULTS, XAU_M5_BOUNDARY_RESULTS]:
    ALL_RESULTS.update(d)

# Reference values from R74
PREV_REFS = {
    "XAU_M1_EU_CB3_RSI10": "85.7% n=63 R74✅",
    "XAU_M1_EU_CB2_RSI10": "82.2% n=73 R74✅",
    "XAU_M1_EU_CB3_RSI8": "89.2% n=37 R74✅",
    "XAU_M1_EU_CB2_RSI8": "87.2% n=39 R74",
    "XAU_M1_EU_CB3_RSI7": "89.7% n=29 R74✅",
    "XAU_M1_EU_CB2_RSI7": "90.0% n=30 ✅R74新",
    "XAU_M1_EU_CB2_RSI5": "100% n=19 R74",
    "XAU_M1_US_CB3_RSI10": "81.2% n=48 R74✅",
    "XAU_M1_US_CB2_RSI10": "79.4% n=63 R74",
    "XAU_M1_DUAL_CB3_RSI10": "81.1% n=111 R74✅",
    "XAU_M1_US_CB4_RSI12": "70.6% n=68 R74⚠️",
    "XAG_M5_RSI4_CB1_ALL": "94.4% n=54 ✅R74(22月)",
    "XAG_M5_RSI4_CB2_ALL": "94.1% n=51 R74",
    "XAG_M5_RSI5_CB1_ALL": "89.3% n=75 ✅R74(27月)",
    "XAG_M5_RSI5_CB2_ALL": "88.4% n=69 R74",
    "XAG_M5_RSI6_CB1_ALL": "86.4% n=103 R74",
    "XAG_M5_RSI6_CB2_ALL": "85.6% n=90 R74",
    "XAG_M5_RSI6_CB3_ALL": "85.5% n=76 R74",
    "XAG_M5_RSI8_CB1_ALL": "75.3% n=186 R74",
    "XAG_M5_RSI8_CB2_ALL": "75.3% n=162 R74",
    "XAG_M5_RSI8_CB3_ALL": "74.8% n=139 R74",
    "XAG_M5_RSI4_CB1_DEEP": "98.1% n=54 ✅R74",
    "XAG_M5_RSI4_CB2_DEEP": "98.0% n=51 R74",
    "US500_EU_CB4_RSI14": "63.0% n=127 ❌R74",
    "US500_EU_CB5_RSI14": "66.7% n=99 ❌R74",
    "US500_EU_CB5_RSI10": "77.5% n=40 ⏳R74",
    "US500_EU_CB5_RSI12": "70.0% n=60 R74",
    "US500_EU_CB6_RSI14": "67.1% n=70 R74",
    "US500_EU_CB6_RSI12": "69.6% n=46 R74",
    "US30_EU_CB4_RSI14": "55.9% n=143 ❌R74",
    "US30_EU_CB5_RSI14": "63.5% n=104 R74",
    "US30_EU_CB4_RSI12": "61.9% n=84 ❌R74",
    "US30_EU_CB5_RSI12": "70.0% n=60 ⏳R74",
    "US30_EU_CB4_RSI10": "62.7% n=51 ❌R74",
    "US30_EU_CB6_RSI12": "69.8% n=43 ⚠️R74",
    "JP225_M5_US_CB3_RSI10": "65.2% n=112 R74",
    "JP225_M5_US_CB4_RSI10": "66.7% n=87 R74",
    "JP225_M5_US_CB5_RSI12": "64.0% n=89 R74",
    "JP225_M5_EU_CB3_RSI10": "66.2% n=77 R74",
    "XAU_M1_ASIA_CB3_RSI10": "78.2%(73.5%) n=78 R74⚠️",
    "XAU_M1_ASIA_CB2_RSI10": "76.9%(72.9%) n=91 R74⚠️",
    "XAU_M1_ASIA_CB4_RSI10": "79.1%(73.6%) n=67 R74⚠️",
    "XAU_M5_US_CB3_RSI15": "65.7% n=213 R74边界",
    "XAU_M5_US_CB4_RSI12": "63.0% n=100 R74边界",
}

print(f"\n{'='*120}")
print(f"📋 ROUND 75 关键发现汇总 — {NOW}")
print(f"{'='*120}")

# Top Findings (WR>=75% n>=15)
print("\n🏆 Top Findings (WR>=75% n>=15):")
print_table(ALL_RESULTS, min_n=15, title="")

# Detailed (WR>=70% n>=25)
print("\n📊 所有策略详细结果(WR>=70% n>=25):")
print_table(ALL_RESULTS, min_n=25, title="")

# Asia verification
print("\n🔍 XAU M1 ASIA 第33月跟踪 ⚠️重点验证:")
print_table(ALL_ASIA_RESULTS, min_n=3, title="")

# XAG Deep
print("\n🔍 XAG M5 DEEP hold=70:")
print_table(XAG_DEEP_RESULTS, min_n=3, title="")

# ════════════════════════════════════════════════════════════
# RUN H1/M30 SCRIPTS
# ════════════════════════════════════════════════════════════
print(f"\n{'─'*120}")
print("📊 PART 11: H1/M30 扫描(现有脚本)")
print(f"{'─'*120}")

for script in ["round75_h1m30.py", "round75_m30_scan.py", "round75_scan_v2.py"]:
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script)
    if os.path.exists(script_path):
        print(f"\n  🔄 运行 {script} (timeout=240s)...")
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True, text=True, timeout=240,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            out = result.stdout
            print(out[-1500:] if len(out) > 1500 else out)
            if result.stderr:
                print(f"  ⚠ stderr: {result.stderr[-300:]}")
        except subprocess.TimeoutExpired:
            print(f"  ⏰ {script} 超时(240s)")
        except Exception as e:
            print(f"  ⚠ {script} 失败: {e}")
    else:
        print(f"  ⚠ 不存在: {script_path}")

print(f"\n{'='*120}")
print(f"✅ ROUND 75 完成. {NOW}")
print(f"{'='*120}")
