#!/usr/bin/env python3
"""
Round 74 — M1/M5 Scalping 第36/34/32/27月跟踪 + 第28/26/25/24/22月验证

聚焦:
  1. XAUUSD M1 EU/US 第36月常规跟踪 + EU_CB2第28月 + EU_RSI8第26月 + CB3+RSI7第25月 + US_CB4_RSI12第24月跟踪
  2. XAUUSD M5 US RSI<6 冻结归档跳过(下次季度检查8月)
  3. XAGUSD M5 RSI<5 ALL第27月跟踪(质量监控) + RSI<4第22月跟踪(确认验证) + RSI4深度hold=70第22月跟踪
  4. US500 M5 EU 第34月常规跟踪(关注WR下降是否继续恶化) + 寻找新EU替代策略
  5. XAUUSD M1 ASIA 第32月跟踪(WR维持75%+确认)
  6. US30 M1 EU 第27月跟踪(重新评估-CB5+RSI12第26月继续观察) + 寻找替代策略
  7. XAUUSD M5 H15/H19冻结归档跳过
  8. XAGUSD M5 RSI<5 ALL第27月跟踪 + RSI<4第22月跟踪(深度hold=70) + 信号频率更新
  9. JP225 M5最低权重监控(维持边界)
  10. 新探索: ①XAG M5 RSI4深度hold=70第22月确认 ②US30 CB5+RSI12持续观察(第26月)
      ③XAU M5 US_CB3_RSI15边界跟踪 ④AUDUSD M30停止跟踪(WR跌破75%)
      ⑤XAU M1 ASIA WR维持75%+ ⑥新数据自动下载(MT5 API)
"""
import sys, os, json, logging, time
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
print(f"ROUND 74 — M1/M5 Scalping 第36/34/32/27月跟踪 + 第28/26/25/24/22月验证 — {NOW}")
print(f"Target: M1/M5/H1/M30 on XAUUSD XAGUSD JP225 US500 US30 ...")
print("=" * 120)

# =====================================================
# CACHED indicator computation (优化版)
# =====================================================
_cache = {}
def get_data(symbol, timeframe):
    key = (symbol, timeframe)
    if key not in _cache:
        data = load_data(timeframe=timeframe, symbols=[symbol])
        if symbol in data:
            _cache[key] = compute_indicators(data[symbol])
            print(f"  ✅ Computed indicators for {symbol} {timeframe}: {len(_cache[key])} rows")
        else:
            print(f"  ⚠ No data for {symbol} {timeframe}")
            _cache[key] = None
    return _cache[key]

def run_grid_cached(cfg):
    """取代 run_grid，使用缓存的 DataFrame 以节省重复计算"""
    timeframe = cfg["timeframe"]
    symbols = cfg["symbols"]
    entry_condition = cfg.get("entry_condition", "")
    direction = cfg.get("direction", "long")
    hold_periods = cfg.get("hold_periods", [1, 3, 5, 10])
    exit_at_close = cfg.get("exit_at_close", True)
    periods_per_year = {"M1": 360000, "M5": 72000, "M15": 24000, "M30": 12000, "H1": 6000}.get(timeframe, 72000)

    results = {}
    for sym in symbols:
        df = get_data(sym, timeframe)
        if df is None or df.empty:
            continue

        try:
            mask = df.eval(entry_condition)
        except Exception as e:
            print(f"  ⚠ Condition eval failed for {cfg['name']}: {e}")
            continue

        entry_prices = df.loc[mask, "close"].values
        entry_indices = df.index[mask]
        n_signals = len(entry_prices)

        if n_signals < 3:
            continue

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
            if n2 < 3:
                continue
            win_rate = float((returns_arr > 0).mean())
            avg_return = float(returns_arr.mean())
            std = float(returns_arr.std()) if returns_arr.std() > 0 else 1e-10
            sharpe = (avg_return / std) * np.sqrt(periods_per_year / hold)
            cum = np.cumprod(1 + returns_arr)
            peak = np.maximum.accumulate(cum)
            dd = (peak - cum) / peak
            max_dd = float(dd.max())
            sym_results.append({
                "n": n2, "win_rate": win_rate, "avg_return": avg_return,
                "sharpe_ratio": sharpe, "max_drawdown": max_dd, "hold_period": hold,
            })

        if sym_results:
            results[sym] = sym_results
            best = max(sym_results, key=lambda r: r["win_rate"])
            print(f"  📊 {cfg['name']}: best hold={best['hold_period']} WR={best['win_rate']*100:.1f}% n={best['n']} Sharpe={best['sharpe_ratio']:.2f}")

    return results

# =====================================================
# HELPER
# =====================================================
def print_best_table(name_results_map, prev_refs=None, min_n=3):
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

def print_us30_table(name_results_map, prev_refs=None):
    """Print US30 results with status column."""
    header = f"| {'Strategy':<35} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<9} | {'Status':<18} | {'Ref':<18} |"
    sep = f"|{':':->35}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->9}|{':':->18}|{':':->18}|"
    print(header)
    print(sep)
    for name in sorted(name_results_map.keys()):
        results = name_results_map[name]
        for sym, sym_res in results.items():
            best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 5 else 0)
            if best and best["n"] >= 3:
                wr = f"{best['win_rate']*100:.1f}%"
                ar = f"{best['avg_return']*100:.3f}%"
                prev = prev_refs.get(name, "") if prev_refs else ""
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

def collect_best(name_results_map, min_n=10, min_wr=0.70):
    findings = []
    for name, results in name_results_map.items():
        for sym, sym_res in results.items():
            best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= min_n else 0)
            if best and best["n"] >= min_n and best["win_rate"] >= min_wr:
                findings.append((name, sym, best))
    return sorted(findings, key=lambda x: -x[2]["win_rate"])


t0 = time.time()

# =====================================================
# PART 1: XAUUSD M1 — 第36月常规跟踪(US/EU) + EU_CB2第28月 + EU_RSI8第26月 + CB3+RSI7第25月 + US_CB4_RSI12第24月
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 1: XAUUSD M1 — 第36月常规跟踪(US/EU) + EU_CB2(第28月) + EU_RSI8(第26月) + CB3+RSI7(第25月) + US_CB4_RSI12(第24月)")
print("─" * 120)
print("  预计算 M1 XAUUSD 指标...")
sys.stdout.flush()

m1_tracking = [
    # US 第36月常规跟踪
    {"name": "XAU_M1_US_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_US_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU 第36月常规跟踪
    {"name": "XAU_M1_EU_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU_CB2 宽松版 — 第28月独立跟踪
    {"name": "XAU_M1_EU_CB2_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # 双极值联合 — 第36月跟踪
    {"name": "XAU_M1_DUAL_CB3_RSI10", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "(session=='europe' or session=='us') and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU_RSI8 — 第26月独立跟踪
    {"name": "XAU_M1_EU_CB3_RSI8", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAU_M1_EU_CB2_RSI8", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # EU CB3+RSI7 — 第25月独立跟踪
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
    # US CB4+RSI12 第24月跟踪(恢复候选状态)
    {"name": "XAU_M1_US_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
]

all_m1_results = {}
for cfg in m1_tracking:
    try:
        res = run_grid_cached(cfg)
        if res:
            all_m1_results[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

prev_refs_m1 = {
    "XAU_M1_US_CB3_RSI10": "81.2% n=48 R73✅",
    "XAU_M1_US_CB2_RSI10": "79.5% R73",
    "XAU_M1_EU_CB3_RSI10": "85.7% n=63 R73✅",
    "XAU_M1_EU_CB2_RSI10": "82.2% n=73 R73✅",
    "XAU_M1_DUAL_CB3_RSI10": "81.1% n=111 R73✅",
    "XAU_M1_EU_CB3_RSI8": "89.2% n=37 R73",
    "XAU_M1_EU_CB2_RSI8": "87.2% n=39 R73",
    "XAU_M1_EU_CB3_RSI7": "89.7% n=29 R73",
    "XAU_M1_EU_CB2_RSI7": "87.0% n=23 R73",
    "XAU_M1_EU_CB2_RSI5": "100.0% n=19 R73",
    "XAU_M1_US_CB4_RSI12": "70.6% n=68 ⚠️R73恢复候选",
}
print("\n📊 M1 第36月跟踪(US/EU) + 扩展追踪:")
print_best_table(all_m1_results, prev_refs_m1)
sys.stdout.flush()


# =====================================================
# PART 2: XAUUSD M5 US RSI<6 — 跳过(冻结归档)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 2: XAUUSD M5 US RSI<6 — ❄️ 跳过(冻结归档, 下次季度检查2026-08)")
print("─" * 120)
print("  ⏭️  连续12月+n无增长(28),正式归档为季度检查.")
sys.stdout.flush()


# =====================================================
# PART 3: XAGUSD M5 RSI<5 ALL第27月跟踪 + RSI<4第22月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 3: XAGUSD M5 RSI<5 ALL第27月跟踪(质量监控) + RSI<4第22月跟踪(确认验证)")
print("─" * 120)
print("  预计算 M5 XAGUSD 指标...")
sys.stdout.flush()

xag_m5_tracking = [
    # ALL sessions — RSI<5 第27月跟踪
    {"name": "XAG_M5_RSI5_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<5 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI5_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<5 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # RSI<6 对比基线
    {"name": "XAG_M5_RSI6_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<6 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI6_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<6 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI6_CB3_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<6 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # RSI<8 仓位参考
    {"name": "XAG_M5_RSI8_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<8 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI8_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<8 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI8_CB3_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<8 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    # RSI<4 第22月跟踪(确认验证)
    {"name": "XAG_M5_RSI4_CB1_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<4 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
    {"name": "XAG_M5_RSI4_CB2_ALL", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<4 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 30, 55]},
]

all_xag_m5 = {}
for cfg in xag_m5_tracking:
    try:
        res = run_grid_cached(cfg)
        if res:
            all_xag_m5[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

prev_refs_xag = {
    "XAG_M5_RSI5_CB1_ALL": "89.3% n=75 ✅R73(第26月)",
    "XAG_M5_RSI5_CB2_ALL": "88.4% n=69 R73",
    "XAG_M5_RSI6_CB1_ALL": "86.4% n=103 R73",
    "XAG_M5_RSI6_CB2_ALL": "85.7% n=87 R73",
    "XAG_M5_RSI6_CB3_ALL": "85.5% n=76 R73",
    "XAG_M5_RSI8_CB1_ALL": "75.2% n=175 R73",
    "XAG_M5_RSI8_CB2_ALL": "74.5% n=152 R73",
    "XAG_M5_RSI8_CB3_ALL": "70.9% n=130 R73",
    "XAG_M5_RSI4_CB1_ALL": "94.4% n=54 ✅R73(第21月)",
    "XAG_M5_RSI4_CB2_ALL": "94.1% n=51 R73",
}
print("\n📊 XAG M5 RSI<5 ALL第27月跟踪(质量监控) + RSI4第22月跟踪:")
print_best_table(all_xag_m5, prev_refs_xag)
sys.stdout.flush()


# =====================================================
# PART 4: US500 M5 EU 第34月常规跟踪 + 新替代策略探索
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 4: US500 M5 EU 第34月常规跟踪(关注WR下降是否继续恶化) + 新替代策略探索")
print("─" * 120)
print("  预计算 M5 US500 指标...")
sys.stdout.flush()

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
    {"name": "US500_EU_CB6_RSI12", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=6",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    # 新替代探索 — US session US500
    {"name": "US500_US_CB4_RSI12", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
    {"name": "US500_US_CB5_RSI12", "symbols": ["US500"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30]},
]

all_us500 = {}
for cfg in us500_tracking:
    try:
        res = run_grid_cached(cfg)
        if res:
            all_us500[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

prev_refs_us500 = {
    "US500_EU_CB4_RSI14": "63.0% n=127 R73 ❌",
    "US500_EU_CB5_RSI14": "66.7% n=99 R73 ❌",
    "US500_EU_CB6_RSI14": "67.1% n=70 R73",
    "US500_EU_CB5_RSI12": "70.0% n=60 R73",
    "US500_EU_CB5_RSI10": "77.5% n=40 R73 ⏳",
    "US500_EU_CB6_RSI12": "69.6% n=46 R73",
}
print("\n📊 US500 M5 EU 第34月常规跟踪 + US session 探索:")
print_best_table(all_us500, prev_refs_us500)
sys.stdout.flush()


# =====================================================
# PART 5: XAUUSD M1 ASIA 第32月跟踪
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 5: XAUUSD M1 ASIA 第32月跟踪")
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
        res = run_grid_cached(cfg)
        if res:
            all_asia[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

prev_refs_asia = {
    "XAU_M1_ASIA_CB3_RSI10": "78.2% n=78 R73 ✅",
    "XAU_M1_ASIA_CB2_RSI10": "76.9% n=91 R73 ✅",
    "XAU_M1_ASIA_CB4_RSI10": "79.1% n=67 R73 ✅",
}
print("\n📊 XAU M1 ASIA 第32月跟踪:")
print_best_table(all_asia, prev_refs_asia)
sys.stdout.flush()


# =====================================================
# PART 6: US30 M1 EU 第27月跟踪 + 替代策略探索
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 6: US30 M1 EU 第27月跟踪(重新评估) + 替代策略探索")
print("─" * 120)
print("  预计算 M1 US30 指标...")
sys.stdout.flush()

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
    # RSI<12 第27月跟踪(已撤销正式推荐)
    {"name": "US30_M1_EU_CB4_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # RSI<12 + CB5 第26月继续观察
    {"name": "US30_M1_EU_CB5_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # RSI<10深入跟踪
    {"name": "US30_M1_EU_CB4_RSI10", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # CB6+RSI12 第24月跟踪
    {"name": "US30_M1_EU_CB6_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=6",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    # US session 替代探索
    {"name": "US30_M1_US_CB4_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
    {"name": "US30_M1_US_CB5_RSI12", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30]},
]

all_us30 = {}
for cfg in us30_tracking:
    try:
        res = run_grid_cached(cfg)
        if res:
            all_us30[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

prev_refs_us30 = {
    "US30_M1_EU_CB3_RSI14": "61.9% R73",
    "US30_M1_EU_CB4_RSI14": "58.9% R73",
    "US30_M1_EU_CB5_RSI14": "63.5% R73",
    "US30_M1_EU_CB4_RSI12": "61.9% ❌(撤销推荐)R73",
    "US30_M1_EU_CB5_RSI12": "70.0% ⏳观察中 R73",
    "US30_M1_EU_CB4_RSI10": "62.7% R73",
    "US30_M1_EU_CB6_RSI12": "69.8% ⚠️边界 R73",
}
print("\n📊 US30 M1 EU 第27月跟踪 + US session 替代探索:")
print_us30_table(all_us30, prev_refs_us30)
sys.stdout.flush()


# =====================================================
# PART 7: XAUUSD M5 H15/H19冻结归档跳过
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 7: XAUUSD M5 H15/H19 — ❄️ 跳过(冻结归档, 下次季度检查8月)")
print("─" * 120)
print("  ⏭️  连续12月n无增长,正式归档. 下次季度检查: 2026年8月.")
sys.stdout.flush()


# =====================================================
# PART 8: XAGUSD M5 — 信号频率检测(第27月/第22月更新)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 8: XAGUSD M5 — 信号频率检测(第27月/第22月更新)")
print("─" * 120)

try:
    df_xag = get_data("XAGUSD", "M5")
    if df_xag is not None:
        for name, cond, desc in [
            ("XAG_M5_RSI4_CB1_ALL", "rsi14<4 and consecutive_bear>=1", "RSI<4 CB1 ALL"),
            ("XAG_M5_RSI4_CB2_ALL", "rsi14<4 and consecutive_bear>=2", "RSI<4 CB2 ALL"),
            ("XAG_M5_RSI5_CB1_ALL", "rsi14<5 and consecutive_bear>=1", "RSI<5 CB1 ALL"),
            ("XAG_M5_RSI5_CB2_ALL", "rsi14<5 and consecutive_bear>=2", "RSI<5 CB2 ALL"),
            ("XAG_M5_RSI6_CB1_ALL", "rsi14<6 and consecutive_bear>=1", "RSI<6 CB1 ALL"),
            ("XAG_M5_RSI6_CB2_ALL", "rsi14<6 and consecutive_bear>=2", "RSI<6 CB2 ALL"),
        ]:
            mask = df_xag.eval(cond)
            total = int(mask.sum())
            years = (df_xag.index[-1] - df_xag.index[0]).days / 365.25
            freq = total / max(years, 0.5)
            print(f"  📈 {desc}: {total}信号 = {freq:.1f}次/年 ({total/max(years*12,0.5):.1f}次/月)")

        last_date = df_xag.index[-1]
        print(f"\n  📅 数据截至: {last_date.strftime('%Y-%m-%d %H:%M')} UTC")
except Exception as e:
    print(f"  ⚠ 信号频率分析失败: {e}")
sys.stdout.flush()


# =====================================================
# PART 9: JP225 M5最低权重监控(维持边界)
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 9: JP225 M5最低权重监控(维持边界)")
print("─" * 120)
print("  预计算 M5 JP225 指标...")
sys.stdout.flush()

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
        res = run_grid_cached(cfg)
        if res:
            all_jp225[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")

prev_refs_jp225 = {
    "JP225_M5_US_CB3_RSI10": "65.2% n=112 R73",
    "JP225_M5_US_CB4_RSI10": "66.7% n=87 R73",
    "JP225_M5_US_CB5_RSI12": "64.0% n=89 R73",
    "JP225_M5_EU_CB3_RSI10": "66.2% n=77 R73",
}
print("\n📊 JP225 M5 最低权重监控(维持边界):")
print_best_table(all_jp225, prev_refs_jp225)
sys.stdout.flush()


# =====================================================
# PART 10: 新探索
# =====================================================
print("\n" + "─" * 120)
print("📊 PART 10: 新探索 — ①XAG M5 RSI4深度hold=70第22月确认 ②US30 CB5+RSI12持续观察(第26月) ③XAU M5 US_CB3_RSI15边界跟踪 ④AUDUSD M30停止跟踪(WR跌破75%) ⑤XAU M1 ASIA WR维持75%+ ⑥数据源检查")
print("─" * 120)

# --- 10a: XAG M5 RSI<4 第22月确认(深度hold=70跟踪) ---
print("\n🔍 10a: XAG M5 RSI<4 CB1 ALL 第22月确认 — 深度hold=70跟踪")
xag_rsi4_deep = [
    {"name": "XAG_M5_RSI4_CB1_DEEP", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<4 and consecutive_bear>=1",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 40, 55, 70, 90]},
    {"name": "XAG_M5_RSI4_CB2_DEEP", "symbols": ["XAGUSD"], "timeframe": "M5",
     "entry_condition": "rsi14<4 and consecutive_bear>=2",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 40, 55, 70, 90]},
]
all_xag_rsi4_deep = {}
for cfg in xag_rsi4_deep:
    try:
        res = run_grid_cached(cfg)
        if res:
            all_xag_rsi4_deep[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")
print("\n📊 XAG M5 RSI<4 深度hold=70 第22月确认:")
print_best_table(all_xag_rsi4_deep)

# --- 10b: US30 CB5+RSI12 第26月持续观察 ---
print("\n🔍 10b: US30 CB5+RSI12 第26月持续观察(包含更长hold)")
us30_hold_stable = [
    {"name": "US30_EU_CB5_RSI12_STABLE", "symbols": ["US30"], "timeframe": "M1",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 25, 30, 40, 55]},
]
all_us30_stable = {}
for cfg in us30_hold_stable:
    try:
        res = run_grid_cached(cfg)
        if res:
            all_us30_stable[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")
print("\n📊 US30 CB5+RSI12 hold稳定性(第26月观察):")
print_best_table(all_us30_stable)

# --- 10c: XAU M5 宽松阈值边界跟踪 ---
print("\n🔍 10c: XAU M5 边界跟踪(US_CB3_RSI15 n=215+ 信号池)")
xau_m5_boundary = [
    {"name": "XAU_M5_EU_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
    {"name": "XAU_M5_US_CB3_RSI15", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<15 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
    {"name": "XAU_M5_US_CB4_RSI12", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
    # 新增探索: 做空 XAU M5 极限测试(最近行情是否有做空可能)
    {"name": "XAU_M5_US_CB6_RSI14_SHORT", "symbols": ["XAUUSD"], "timeframe": "M5",
     "entry_condition": "session=='us' and rsi14>86 and consecutive_bull>=6",
     "direction": "short", "hold_periods": [5, 10, 15, 20, 30]},
]
all_xau_m5 = {}
for cfg in xau_m5_boundary:
    try:
        res = run_grid_cached(cfg)
        if res:
            all_xau_m5[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")
print("\n📊 XAU M5 边界跟踪 + 做空测试:")
print_best_table(all_xau_m5)

# --- 10d: AUDUSD M30 — 停止跟踪(WR跌破75%) ---
print("\n🔍 10d: AUDUSD M30 — 停止跟踪(WR跌破75% - 第17轮连续记录中止)")
print("  ⏭️  AUDUSD M30 CB4+RSI15 WR=70.9% R73,连续17轮75%+记录中止,正式停止跟踪。")
print("     保留基线参考以备未来重新评估。")

# --- 10e: XAU M1 ASIA 深度hold验证 ---
print("\n🔍 10e: XAU M1 ASIA WR维持75%+跟踪确认(深度hold验证)")
asia_deep = [
    {"name": "XAU_M1_ASIA_CB3_RSI10_DEEP", "symbols": ["XAUUSD"], "timeframe": "M1",
     "entry_condition": "session=='asia' and rsi14<10 and consecutive_bear>=3",
     "direction": "long", "hold_periods": [5, 10, 15, 20, 30, 55]},
]
all_asia_deep = {}
for cfg in asia_deep:
    try:
        res = run_grid_cached(cfg)
        if res:
            all_asia_deep[cfg["name"]] = res
    except Exception as e:
        print(f"  ⚠ {cfg['name']}: {e}")
print("\n📊 XAU M1 ASIA 深度hold检测:")
print_best_table(all_asia_deep)

# --- 10f: 数据源状态检查 ---
print("\n🔍 10f: 数据源状态检查")
try:
    for tf in ["M5", "M1", "H1", "M30"]:
        syms = list_available_symbols(tf)
        print(f"  {tf}可用品种: {len(syms)}")
    for tf, sym in [("M5", "XAUUSD"), ("M1", "XAUUSD"), ("H1", "XAUUSD"), ("M30", "XAUUSD")]:
        data = load_data(timeframe=tf, symbols=[sym])
        if sym in data:
            df = data[sym]
            print(f"  {sym} {tf}: {df.index[0].strftime('%Y-%m-%d %H:%M')} → {df.index[-1].strftime('%Y-%m-%d %H:%M')} ({len(df)}行)")
except Exception as e:
    print(f"  ⚠ 数据源检查失败: {e}")
sys.stdout.flush()


# =====================================================
# SUMMARY — 顶级发现汇总
# =====================================================
print("\n" + "=" * 120)
print("📋 ROUND 74 关键发现汇总 — " + NOW)
print("=" * 120)

all_results = {}
for name, results in list(all_m1_results.items()) + list(all_xag_m5.items()) + list(all_us500.items()) + list(all_asia.items()) + list(all_us30.items()) + list(all_jp225.items()) + list(all_xag_rsi4_deep.items()) + list(all_us30_stable.items()) + list(all_xau_m5.items()) + list(all_asia_deep.items()):
    if name not in all_results:
        all_results[name] = results

findings = collect_best(all_results, min_n=15, min_wr=0.75)
if findings:
    print("\n🏆 Top Findings (WR>=75% n>=15):")
    print(f"| {'Strategy':<35} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<9} |")
    print(f"|{':':->35}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->9}|")
    for name, sym, best in findings:
        wr = f"{best['win_rate']*100:.1f}%"
        ar = f"{best['avg_return']*100:.3f}%"
        print(f"| {name:<35} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<9.2f} |")
else:
    print("\n⚠️ 无符合条件(WR>=75% n>=15)的发现")

# Output all results with WR>=70% n>=25
print("\n\n📊 所有策略详细结果(WR>=70% n>=25):")
print(f"| {'Strategy':<35} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<9} |")
print(f"|{':':->35}|{':':->7}|{':':->6}|{':':->5}|{':':->10}|{':':->9}|")
for name in sorted(all_results.keys()):
    results = all_results[name]
    for sym, sym_res in results.items():
        best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= 25 else 0)
        if best and best["n"] >= 25 and best["win_rate"] >= 0.70:
            wr = f"{best['win_rate']*100:.1f}%"
            ar = f"{best['avg_return']*100:.3f}%"
            print(f"| {name:<35} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<9.2f} |")

# Boundary strategies (65%<=WR<75% n>=20)
boundary = collect_best(all_results, min_n=20, min_wr=0.65)
boundary = [(n, s, b) for n, s, b in boundary if b["win_rate"] < 0.75]
if boundary:
    print("\n⚠️ 边界策略(65%<=WR<75% n>=20):")
    for name, sym, best in sorted(boundary, key=lambda x: -x[2]["win_rate"]):
        wr = f"{best['win_rate']*100:.1f}%"
        hp = best["hold_period"]
        nv = best["n"]
        sp = best["sharpe_ratio"]
        print(f"  • {name}: WR={wr} n={nv} hold={hp} Sharpe={sp:.1f}")

elapsed = time.time() - t0
print(f"\n⏱  R74 耗时: {elapsed:.0f}s")
print(f"✅ ROUND 74 完成. {NOW}")
