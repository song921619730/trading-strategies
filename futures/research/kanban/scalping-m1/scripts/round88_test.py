#!/usr/bin/env python3
"""Round 88 — M1/M5 Scalping 第50/48/42/41/36/8月跟踪
(数据边界: M5→2026-05-14 11:50 UTC, M1→2026-05-14 11:51 UTC)
⚠️ 数据无更新 — 与R87完全一致（MT5 Linux不可用）

聚焦:
  1. XAUUSD M1 EU/US 第50月常规跟踪 + EU_CB2第42月 + EU_CB4_RSI12第8月跟踪(关注回升是否持续)
  2. XAGUSD M5 RSI<5 ALL第41月 + RSI<4第36月 + RSI3第8月跟踪
  3. US500 M5 EU 第48月常规跟踪
  4. XAUUSD M1 ASIA 已归档 — 跳过
  5. US30 M1 EU 第41月改善持续跟踪
  6. JP225 M5 US session监控
  7. XAGUSD M5 RSI3/4/5/6信号频率更新
"""
import sys, os, json, logging, time
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
logging.basicConfig(level=logging.WARNING, format='%(asctime)s [%(levelname)s] %(message)s')

# =====================================================
# Self-contained indicator computation
# =====================================================
def compute_indicators(df):
    df = df.copy()
    if 'session' not in df.columns:
        hours = df.index.hour if hasattr(df.index, 'hour') else pd.Series(df.index).dt.hour
        df['hour'] = hours
        df['session'] = 'asia'
        df.loc[(df['hour'] >= 8) & (df['hour'] < 13), 'session'] = 'europe'
        df.loc[(df['hour'] >= 13) & (df['hour'] < 22), 'session'] = 'us'
    if 'rsi14' not in df.columns:
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_g = gain.rolling(14, min_periods=14).mean()
        avg_l = loss.rolling(14, min_periods=14).mean()
        rs = avg_g / avg_l.replace(0, np.nan)
        df['rsi14'] = 100.0 - (100.0 / (1.0 + rs))
    if 'consecutive_bear' not in df.columns and 'consecutive_bull' not in df.columns:
        bear = (df['close'] < df['open']).astype(int)
        def count_consecutive(series):
            result = series.copy() * 0
            count = 0
            for i in range(len(series)):
                if series.iloc[i] == 1:
                    count += 1
                else:
                    count = 0
                result.iloc[i] = count
            return result
        df['consecutive_bear'] = count_consecutive(bear)
        bull = (df['close'] > df['open']).astype(int)
        df['consecutive_bull'] = count_consecutive(bull)
    if 'atr14_pct' not in df.columns and 'atr14' not in df.columns:
        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()
        df['atr14'] = atr14
        df['atr14_pct'] = atr14 / close.replace(0, np.nan) * 100
    return df

from data_loader import load_data

NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("=" * 120)
print(f"ROUND 88 — M1/M5 Scalping 第50/48/42/41/36/8月跟踪 — {NOW}")
print(f"Target: XAUUSD XAGUSD JP225 US500 US30")
print(f"Data:   M5->2026-05-14 11:50 UTC, M1->2026-05-14 11:51 UTC")
print(f"⚠️ 数据无更新 — 所有结果与R87完全一致")
print(f"依据:   state/research_state.json next_actions round88")
print("=" * 120)

_cache = {}
def get_data(symbol, timeframe):
    key = (symbol, timeframe)
    if key not in _cache:
        t0 = time.time()
        data = load_data(timeframe=timeframe, symbols=[symbol])
        if symbol in data:
            _cache[key] = compute_indicators(data[symbol])
            print(f"  [OK] Loaded {symbol} {timeframe}: {len(_cache[key])} rows ({time.time()-t0:.1f}s)")
        else:
            print(f"  [!!] No data for {symbol} {timeframe}")
            _cache[key] = None
    return _cache[key]

def run_grid_cached(cfg, min_n=3, hold_periods_override=None):
    timeframe = cfg["timeframe"]
    symbols = cfg["symbols"]
    entry_condition = cfg.get("entry_condition", "")
    direction = cfg.get("direction", "long")
    hold_periods = hold_periods_override or cfg.get("hold_periods", [1, 3, 5, 10])
    periods_per_year = {"M1": 360000, "M5": 72000, "M15": 24000, "M30": 12000, "H1": 6000}.get(timeframe, 72000)
    results = {}
    for sym in symbols:
        df = get_data(sym, timeframe)
        if df is None or df.empty:
            continue
        try:
            mask = df.eval(entry_condition)
        except Exception as e:
            print(f"    [!!] Condition FAILED [{cfg['name']}]: {e}")
            return {sym: []}
        entry_prices = df.loc[mask, "close"].values
        entry_indices = df.index[mask]
        n_signals = len(entry_prices)
        if n_signals < min_n:
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
            print(f"  [DATA] {cfg['name']}: best hold={best['hold_period']} WR={best['win_rate']*100:.1f}% n={best['n']} Sharpe={best['sharpe_ratio']:.2f} (signals={n_signals})")
    return results

M1_HOLDS = [5, 10, 15, 20, 25, 30, 40, 50, 55, 60, 70, 80]
M5_HOLDS = [5, 10, 15, 20, 25, 30, 40, 50, 55, 60, 70, 80, 100, 120]

ALL_RESULTS = {}

# ============================================================
# PART 1: XAUUSD M1 — 第50月常规跟踪(EU/US) + EU_CB2第42月 + EU_CB4_RSI12第8月
# ============================================================
print(f"\n{'='*120}")
print("PART 1: XAUUSD M1 — 第50月常规跟踪(EU/US) + EU_CB2第42月 + CB4_RSI12第8月")
print(f"{'='*120}")

xau_m1_cfgs = [
    # 第50月核心跟踪
    {"name": "XAU_M1_EU_CB3_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3", "hold_periods": M1_HOLDS},
    {"name": "XAU_M1_US_CB3_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3", "hold_periods": M1_HOLDS},
    {"name": "XAU_M1_DUAL_CB3_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "(session=='europe' or session=='us') and rsi14<10 and consecutive_bear>=3", "hold_periods": M1_HOLDS},
    # 第42月 EU_CB2
    {"name": "XAU_M1_EU_CB2_RSI10", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=2", "hold_periods": M1_HOLDS},
    # 参考策略
    {"name": "XAU_M1_EU_CB3_RSI8", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=3", "hold_periods": M1_HOLDS},
    {"name": "XAU_M1_EU_CB2_RSI8", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<8 and consecutive_bear>=2", "hold_periods": M1_HOLDS},
    # 第8月确认 EU_CB4_RSI12 (关注回升是否持续)
    {"name": "XAU_M1_EU_CB4_RSI12", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=4", "hold_periods": M1_HOLDS},
    {"name": "XAU_M1_EU_CB3_RSI12", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=3", "hold_periods": M1_HOLDS},
    {"name": "XAU_M1_EU_CB2_RSI12", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=2", "hold_periods": M1_HOLDS},
    # US_CB4_RSI12 参考
    {"name": "XAU_M1_US_CB4_RSI12", "timeframe": "M1", "symbols": ["XAUUSD"],
     "entry_condition": "session=='us' and rsi14<12 and consecutive_bear>=4", "hold_periods": M1_HOLDS},
]

for cfg in xau_m1_cfgs:
    print(f"  [RUN] {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_RESULTS[cfg['name']] = res

# ============================================================
# PART 2: XAUUSD M5 US RSI<6 — [跳过] 冻结归档 (季度检查2026-08)
# ============================================================
print(f"\n{'='*120}")
print("PART 2: XAUUSD M5 US RSI<6 — [跳过] 冻结归档 (季度检查2026-08)")
print(f"{'='*120}")

# ============================================================
# PART 3: XAGUSD M5 — RSI<5第41月 + RSI<4第36月 + RSI3第8月
# ============================================================
print(f"\n{'='*120}")
print("PART 3: XAGUSD M5 RSI<5 ALL第41月 + RSI<4第36月 + RSI3第8月")
print(f"{'='*120}")

xag_m5_cfgs = [
    # RSI<5 第41月
    {"name": "XAG_M5_RSI5_CB1_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<5 and consecutive_bear>=1", "hold_periods": M5_HOLDS},
    {"name": "XAG_M5_RSI5_CB2_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<5 and consecutive_bear>=2", "hold_periods": M5_HOLDS},
    # RSI<4 第36月
    {"name": "XAG_M5_RSI4_CB1_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<4 and consecutive_bear>=1", "hold_periods": M5_HOLDS},
    {"name": "XAG_M5_RSI4_CB2_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<4 and consecutive_bear>=2", "hold_periods": M5_HOLDS},
    # RSI<3 第8月
    {"name": "XAG_M5_RSI3_CB1_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<3 and consecutive_bear>=1", "hold_periods": M5_HOLDS},
    {"name": "XAG_M5_RSI3_CB2_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<3 and consecutive_bear>=2", "hold_periods": M5_HOLDS},
    # RSI<6 参考
    {"name": "XAG_M5_RSI6_CB1_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<6 and consecutive_bear>=1", "hold_periods": M5_HOLDS},
    {"name": "XAG_M5_RSI6_CB2_ALL", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<6 and consecutive_bear>=2", "hold_periods": M5_HOLDS},
]

for cfg in xag_m5_cfgs:
    print(f"  [RUN] {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_RESULTS[cfg['name']] = res

# ============================================================
# PART 4: US500 M5 EU 第48月常规跟踪
# ============================================================
print(f"\n{'='*120}")
print("PART 4: US500 M5 EU 第48月常规跟踪")
print(f"{'='*120}")

us500_m5_cfgs = [
    {"name": "US500_EU_CB4_RSI14", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=4", "hold_periods": M5_HOLDS},
    {"name": "US500_EU_CB5_RSI14", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=5", "hold_periods": M5_HOLDS},
    {"name": "US500_EU_CB6_RSI14", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<14 and consecutive_bear>=6", "hold_periods": M5_HOLDS},
    {"name": "US500_EU_CB5_RSI12", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=5", "hold_periods": M5_HOLDS},
    {"name": "US500_EU_CB6_RSI12", "timeframe": "M5", "symbols": ["US500"],
     "entry_condition": "session=='europe' and rsi14<12 and consecutive_bear>=6", "hold_periods": M5_HOLDS},
]

for cfg in us500_m5_cfgs:
    print(f"  [RUN] {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_RESULTS[cfg['name']] = res

# ============================================================
# PART 5: XAUUSD M1 ASIA 已归档 — 跳过
# ============================================================
print(f"\n{'='*120}")
print("PART 5: XAUUSD M1 ASIA — [跳过] 已正式归档 (R87确认WR=67.7%)")
print(f"{'='*120}")

# ============================================================
# PART 6: US30 M1 EU 第41月改善持续跟踪
# ============================================================
print(f"\n{'='*120}")
print("PART 6: US30 M1 EU 第41月改善持续跟踪 (CB6+RSI12, CB4+RSI10)")
print(f"{'='*120}")

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
    print(f"  [RUN] {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_US30_RESULTS[cfg['name']] = res
        ALL_RESULTS[cfg['name']] = res

# ============================================================
# PART 7: XAUUSD M5 H15/H19 — [跳过] 冻结归档
# ============================================================
print(f"\n{'='*120}")
print("PART 7: XAUUSD M5 H15/H19 — [跳过] 冻结归档")
print(f"{'='*120}")

# ============================================================
# PART 8: XAGUSD M5 RSI3/4/5/6 信号频率更新 + DEEP hold=70
# ============================================================
print(f"\n{'='*120}")
print("PART 8: XAGUSD M5 RSI3/4/5/6 信号频率更新 + DEEP hold=70")
print(f"{'='*120}")

# Deep hold=70 跟踪
xag_deep_hold = [70]
xag_deep_cfgs = [
    {"name": "XAG_M5_RSI3_DEEP", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<3 and consecutive_bear>=1", "hold_periods": xag_deep_hold},
    {"name": "XAG_M5_RSI4_DEEP", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<4 and consecutive_bear>=1", "hold_periods": xag_deep_hold},
    {"name": "XAG_M5_RSI5_DEEP", "timeframe": "M5", "symbols": ["XAGUSD"],
     "entry_condition": "rsi14<5 and consecutive_bear>=1", "hold_periods": xag_deep_hold},
]

# Signal frequency: count signals per RSI threshold
print("  [ANALYSIS] Signal frequency per RSI threshold:")
xag_df = get_data("XAGUSD", "M5")
if xag_df is not None:
    for rsi_thresh in [3, 4, 5, 6, 8, 10]:
        for cb_min in [1, 2, 3]:
            cond = f"rsi14<{rsi_thresh} and consecutive_bear>={cb_min}"
            n_signals = xag_df.eval(cond).sum()
            if n_signals > 0:
                print(f"    RSI<{rsi_thresh} CB>={cb_min}: {n_signals:>5} signals ({n_signals/len(xag_df)*100:.2f}%)")

XAG_DEEP_RESULTS = {}
for cfg in xag_deep_cfgs:
    print(f"  [RUN] {cfg['name']}...")
    res = run_grid_cached(cfg, min_n=5)
    if res:
        XAG_DEEP_RESULTS[cfg['name']] = res
        ALL_RESULTS[cfg['name']] = res

# ============================================================
# PART 9: JP225 M5 最低权重监控 (US session)
# ============================================================
print(f"\n{'='*120}")
print("PART 9: JP225 M5 US session最低权重监控")
print(f"{'='*120}")

jp225_m5_cfgs = [
    {"name": "JP225_US_CB3_RSI10", "timeframe": "M5", "symbols": ["JP225"],
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=3", "hold_periods": M5_HOLDS},
    {"name": "JP225_US_CB4_RSI10", "timeframe": "M5", "symbols": ["JP225"],
     "entry_condition": "session=='us' and rsi14<10 and consecutive_bear>=4", "hold_periods": M5_HOLDS},
    {"name": "JP225_EU_CB3_RSI10", "timeframe": "M5", "symbols": ["JP225"],
     "entry_condition": "session=='europe' and rsi14<10 and consecutive_bear>=3", "hold_periods": M5_HOLDS},
]

for cfg in jp225_m5_cfgs:
    print(f"  [RUN] {cfg['name']}...")
    res = run_grid_cached(cfg)
    if res:
        ALL_RESULTS[cfg['name']] = res

# ============================================================
# RESULTS PRINTING
# ============================================================
def print_table(name_results_map, min_n=5, title="Results"):
    rows = []
    for name, results in name_results_map.items():
        for sym, sym_res in results.items():
            best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= min_n else 0)
            if best and best["n"] >= min_n:
                rows.append((name, sym, best))
    if not rows:
        print(f"  (no results meeting criteria)")
        return []
    rows.sort(key=lambda x: -x[2]["win_rate"])
    header = f"| {'Strategy':<38} | {'WR':<7} | {'n':<6} | {'Hold':<5} | {'avg%':<10} | {'Sharpe':<9} |"
    sep = "-" * len(header)
    print(f"\n{title}:" if title else "")
    print(header)
    print(sep)
    for name, sym, best in rows:
        wr = f"{best['win_rate']*100:.1f}%"
        ar = f"{best['avg_return']*100:.3f}%"
        print(f"| {name:<38} | {wr:<7} | {best['n']:<6} | {best['hold_period']:<5} | {ar:<10} | {best['sharpe_ratio']:<9.2f} |")
    return rows

def print_compact(name_results_map, min_n=5, title="Compact Results"):
    """Print only best per strategy"""
    rows = []
    for name, results in name_results_map.items():
        for sym, sym_res in results.items():
            best = max(sym_res, key=lambda r: r["win_rate"] if r["n"] >= min_n else 0)
            if best and best["n"] >= min_n:
                rows.append((name, sym, best))
    if not rows:
        return
    rows.sort(key=lambda x: -x[2]["win_rate"])
    for name, sym, best in rows:
        wr = f"{best['win_rate']*100:.1f}%"
        ar = f"{best['avg_return']*100:.3f}%"
        print(f"  {name:<38} | WR={wr:<6} n={best['n']:<5} hold={best['hold_period']:<3} avg={ar:<8} Sharpe={best['sharpe_ratio']:<7.2f}")

print(f"\n{'='*120}")
print(f"ROUND 88 关键发现汇总 — {NOW}")
print(f"{'='*120}")

print("\n[T] Top Findings (WR>=75% n>=15):")
all_rows = print_table(ALL_RESULTS, min_n=15)

print("\n[T] 所有策略详细结果(WR>=70% n>=25):")
print_table(ALL_RESULTS, min_n=25)

print("\n[T] XAU M1 ASIA — [已归档] 跳过")

print("\n[T] XAG M5 DEEP hold=70:")
print_table(XAG_DEEP_RESULTS, min_n=3)

print("\n[T] US30 第41月改善持续跟踪:")
us30_rows = print_table(ALL_US30_RESULTS, min_n=20)
if us30_rows:
    best_wr = max(r[2]["win_rate"] for r in us30_rows)
    best_name = max(us30_rows, key=lambda r: r[2]["win_rate"])[0]
    print(f"  [EVAL] 最佳WR={best_wr*100:.1f}% ({best_name})", end="")
    if best_wr >= 0.85:
        print(" [STAR] 改善持续! 重点关注")
    elif best_wr >= 0.75:
        print(" [OK] 改善维持")
    else:
        print(" [WARN] 改善未持续")

# ============================================================
# Summary table for all strategies (compact)
# ============================================================
print(f"\n{'='*120}")
print("ROUND 88 完整策略排名 (WR降序, n>=10)")
print(f"{'='*120}")
print_compact(ALL_RESULTS, min_n=10)

print(f"\n{'='*120}")
print(f"[DONE] ROUND 88 核心分析完成. {NOW}")
print(f"[DATA] M5->2026-05-14 11:50 UTC, M1->2026-05-14 11:51 UTC")
print(f"[NOTE] ⚠️ 数据无更新 — 所有结果与R87完全一致 (MT5 Linux不可用)")
print(f"{'='*120}")
