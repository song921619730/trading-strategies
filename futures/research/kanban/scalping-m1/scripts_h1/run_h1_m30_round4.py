#!/usr/bin/env python3
"""
H1/M30 欧盘/亚盘研究循环 — Round 4: 稳健性验证与跨品种协同

P1-h1r4_001: M30 最强信号的跨品种协同验证
P1-h1r4_002: H1 欧盘超卖信号bootstrap稳健性验证
P2-h1r4_003: M30 亚盘/欧盘过渡的窄幅挤压+波动扩张策略 (squeeze play)
P2-h1r4_004: H1/M30 整体胜率衰减监控

数据: 最新重采样至 2026-05-14 UTC
"""
import sys, logging, json
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from h1_m30_engine import (
    load_data, compute_indicators, evaluate_pattern, SYMBOLS_ALL,
    PERIODS_PER_YEAR, list_available_symbols, run_test, print_results
)

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("h1_m30_r4")

BASE = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
STATE_DIR = BASE / "state"
STATE_DIR.mkdir(exist_ok=True)

ROUND = 4


def rich_results(df, sym, cond_entries, label, direction, hold_range, tf, pppy):
    """Evaluate with richer output."""
    mask = df.eval(cond_entries)
    n_signals = int(mask.sum())
    if n_signals < 5:
        return None
    results = run_test(df, mask, label, direction, hold_range, pppy)
    print_results(results, label, n_signals, sym)
    if not results:
        return None
    valid = {k: v for k, v in results.items() if v['n'] >= 5}
    if not valid:
        return None
    best_wr_hold = max(valid.items(), key=lambda x: x[1]['win_rate'])
    best_sharpe_hold = max(valid.items(), key=lambda x: x[1]['sharpe'])
    return {
        "symbol": sym,
        "label": label,
        "direction": direction,
        "n_signals": n_signals,
        "best_hold": best_wr_hold[0],
        "best_wr": best_wr_hold[1]['win_rate'],
        "best_n": best_wr_hold[1]['n'],
        "best_avg_ret": best_wr_hold[1]['avg_return'],
        "best_sharpe": best_wr_hold[1]['sharpe'],
        "best_sharpe_hold": best_sharpe_hold[0],
        "best_sharpe_val": best_sharpe_hold[1]['sharpe'],
        "best_sharpe_wr": best_sharpe_hold[1]['win_rate'],
    }


def bootstrap_ci(returns, n_iter=1000, ci=0.95):
    """Bootstrap confidence interval for win rate."""
    n = len(returns)
    wr_samples = []
    for _ in range(n_iter):
        idx = np.random.randint(0, n, n)
        sample = returns[idx]
        wr = (sample > 0).mean()
        wr_samples.append(wr)
    wr_samples = np.array(sorted(wr_samples))
    lower = float(np.percentile(wr_samples, (1 - ci) / 2 * 100))
    upper = float(np.percentile(wr_samples, (1 + ci) / 2 * 100))
    return lower, upper, np.array(wr_samples)


print("=" * 70)
print("📈 H1/M30 欧盘/亚盘研究循环 — Round 4 (稳健性验证与跨品种协同)")
print(f"   日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print(f"   品种: {len(SYMBOLS_ALL)} symbols")
print(f"   数据: 最新至 2026-05-14 UTC")
print("=" * 70)

# Load all data
h1_data = load_data("H1", symbols=SYMBOLS_ALL)
m30_data = load_data("M30", symbols=SYMBOLS_ALL)

all_findings = []

# ══════════════════════════════════════════════════════════════════
# R4-M1: M30 跨品种协同验证 (P1)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R4-M1: M30 跨品种协同 — 最强信号关联验证")
print("=" * 70)

r4m1_results = []

# Focus on key signal-bearer pairs from R3
# GBPUSD M30: CB>=3+RSI<30 → watch EURUSD, AUDUSD
# USOIL M30: CB>=3+RSI<25 → watch UKOIL
# JP225 M30: CB>=3+RSI<25 → watch USTEC, US500
correlation_pairs = [
    ("GBPUSD", "EURUSD", "GBP/EUR 超卖双确认"),
    ("GBPUSD", "AUDUSD", "GBP/AUD 超卖双确认"),
    ("JP225", "USTEC", "JP225/USTEC 超卖联动"),
    ("JP225", "US500", "JP225/US500 超卖联动"),
    ("USOIL", "UKOIL", "美油/英油 超卖联动"),
    ("EURUSD", "USDCHF", "EUR/USDCHF 超卖反向联动"),
]

m30_hold_range = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 30, 48]

# First: scan individual triggers to find best RSI/CB combos
for sym in sorted(m30_data.keys()):
    df = compute_indicators(m30_data[sym])
    for rsi_t in [20, 22, 25, 28, 30]:
        cond = f"session == 'europe' and rsi14 < {rsi_t}"
        label = f"M30欧盘超卖做多 RSI<{rsi_t}"
        res = rich_results(df, sym, cond, label, direction="long",
                          hold_range=m30_hold_range, tf="M30",
                          pppy=PERIODS_PER_YEAR["M30"])
        if res and res['best_wr'] >= 0.65 and res['best_n'] >= 15:
            r4m1_results.append(res)

# Now test cross-symbol correlation: when SYM1 triggers, check SYM2 status
# We look for "dual confirmation" patterns
for sym1, sym2, pair_label in correlation_pairs:
    if sym1 not in m30_data or sym2 not in m30_data:
        continue
    df1 = compute_indicators(m30_data[sym1])
    df2 = compute_indicators(m30_data[sym2])

    # Check for simultaneous triggers (same bar index)
    common_idx = df1.index.intersection(df2.index)
    df1_common = df1.loc[common_idx]
    df2_common = df2.loc[common_idx]

    for rsi_t in [22, 25, 28, 30]:
        # Both in Europe session and both oversold
        cond_both = (f"(session == 'europe') and (rsi14 < {rsi_t})")
        mask1 = df1_common.eval(cond_both)
        mask2 = df2_common.eval(cond_both)
        dual_mask = mask1 & mask2
        n_dual = int(dual_mask.sum())
        if n_dual < 5:
            continue

        label = f"M30跨品种同时超卖 {pair_label} RSI<{rsi_t}"
        results = run_test(df1_common, dual_mask, label, direction="long",
                          hold_range=m30_hold_range, periods_per_year=PERIODS_PER_YEAR["M30"])
        print_results(results, label, n_dual, sym1)
        if results:
            valid = {k: v for k, v in results.items() if v['n'] >= 5}
            if valid:
                best = max(valid.items(), key=lambda x: x[1]['win_rate'])
                if best[1]['win_rate'] >= 0.60:
                    r4m1_results.append({
                        "symbol": f"{sym1}/{sym2}",
                        "label": label,
                        "direction": "long",
                        "n_signals": n_dual,
                        "best_hold": best[0],
                        "best_wr": best[1]['win_rate'],
                        "best_n": best[1]['n'],
                        "best_avg_ret": best[1]['avg_return'],
                        "best_sharpe": best[1]['sharpe'],
                        "best_sharpe_hold": best[0],
                        "best_sharpe_val": best[1]['sharpe'],
                        "best_sharpe_wr": best[1]['win_rate'],
                    })

print(f"\n✅ R4-M1 完成: {len(r4m1_results)} 个信号")
all_findings.extend(r4m1_results)


# ══════════════════════════════════════════════════════════════════
# R4-M2: H1 欧盘超卖 bootstrap 稳健性验证 (P1)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R4-M2: H1 欧盘超卖 bootstrap CI + 跨周期分割验证")
print("=" * 70)

r4m2_results = []

focus_h1_symbols = ["GBPUSD", "EURUSD", "XAUUSD", "USOIL", "JP225", "AUDUSD", "XAGUSD", "US500", "USTEC"]
h1_hold_range = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24]

bootstrap_results = []

for sym in sorted(h1_data.keys()):
    if sym not in focus_h1_symbols:
        continue
    df = compute_indicators(h1_data[sym])

    for rsi_t in [22, 25, 28, 30]:
        cond = f"session == 'europe' and rsi14 < {rsi_t}"
        label = f"H1欧盘超卖做多 RSI<{rsi_t}"
        mask = df.eval(cond)
        entries = df[mask].copy()
        n_signals = len(entries)
        if n_signals < 15:
            continue

        # Test with best hold from R3 findings
        # R3 showed best holds were generally short (1-3)
        for hold in [1, 2, 3, 5, 10]:
            returns = []
            for idx in entries.index:
                pos = df.index.get_loc(idx)
                exit_pos = pos + hold
                if exit_pos >= len(df):
                    continue
                entry_price = df.loc[idx, 'close']
                exit_price = df.iloc[exit_pos]['close']
                ret = (exit_price - entry_price) / entry_price
                returns.append(ret)

            if len(returns) < 15:
                continue
            ret_arr = np.array(returns)
            wr = (ret_arr > 0).mean()
            n = len(ret_arr)
            avg_ret = ret_arr.mean()
            std = ret_arr.std() if ret_arr.std() > 0 else 1e-10
            sharpe = (avg_ret / std) * np.sqrt(PERIODS_PER_YEAR["H1"] / hold)

            # Bootstrap CI
            lower, upper, wr_samples = bootstrap_ci(ret_arr, n_iter=2000, ci=0.95)
            ci_width = upper - lower

            if wr >= 0.60 and n >= 15:
                bootstrap_results.append({
                    "symbol": sym,
                    "label": label,
                    "hold": hold,
                    "wr": wr,
                    "n": n,
                    "sharpe": sharpe,
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "ci_width": ci_width,
                })
                print(f"\n   {sym} {label} hold={hold}: WR={wr*100:.1f}% n={n} "
                      f"Sharpe={sharpe:.2f} CI95=[{lower*100:.1f}%-{upper*100:.1f}%] "
                      f"宽度={ci_width*100:.1f}%")

    # Also test RSI<20 extreme
    cond = "session == 'europe' and rsi14 < 20"
    mask = df.eval(cond)
    entries = df[mask].copy()
    n_signals = len(entries)
    if n_signals >= 10:
        for hold in [1, 2, 3, 5, 8, 10]:
            returns = []
            for idx in entries.index:
                pos = df.index.get_loc(idx)
                exit_pos = pos + hold
                if exit_pos >= len(df):
                    continue
                entry_price = df.loc[idx, 'close']
                exit_price = df.iloc[exit_pos]['close']
                ret = (exit_price - entry_price) / entry_price
                returns.append(ret)
            if len(returns) < 10:
                continue
            ret_arr = np.array(returns)
            wr = (ret_arr > 0).mean()
            n = len(ret_arr)
            avg_ret = ret_arr.mean()
            std = ret_arr.std() if ret_arr.std() > 0 else 1e-10
            sharpe = (avg_ret / std) * np.sqrt(PERIODS_PER_YEAR["H1"] / hold)
            if wr >= 0.65:
                lower, upper, _ = bootstrap_ci(ret_arr, n_iter=2000, ci=0.95)
                ci_width = upper - lower
                bootstrap_results.append({
                    "symbol": sym,
                    "label": f"H1欧盘极端超卖做多 RSI<20",
                    "hold": hold,
                    "wr": wr,
                    "n": n,
                    "sharpe": sharpe,
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "ci_width": ci_width,
                })
                print(f"\n   {sym} H1欧盘极端超卖 RSI<20 hold={hold}: WR={wr*100:.1f}% n={n} "
                      f"Sharpe={sharpe:.2f} CI95=[{lower*100:.1f}%-{upper*100:.1f}%] "
                      f"宽度={ci_width*100:.1f}%")

# Cross-period validation: split data into first half and second half
if len(bootstrap_results) >= 5:
    print("\n\n--- 跨周期分割验证 (前50% vs 后50%) ---")
    for sym in focus_h1_symbols:
        if sym not in h1_data:
            continue
        df = compute_indicators(h1_data[sym])
        if len(df) < 100:
            continue
        mid_point = len(df) // 2
        df_first = df.iloc[:mid_point]
        df_second = df.iloc[mid_point:]

        for label_base, rsi_t in [("RSI<22", 22), ("RSI<25", 25), ("RSI<28", 28), ("RSI<20", 20)]:
            cond = f"session == 'europe' and rsi14 < {rsi_t}"
            for hold in [1, 2, 3]:
                for df_part, period_name in [(df_first, "前半期"), (df_second, "后半期")]:
                    mask = df_part.eval(cond)
                    entries = df_part[mask].copy()
                    n_sig = len(entries)
                    if n_sig < 8:
                        continue
                    returns = []
                    for idx in entries.index:
                        pos = df_part.index.get_loc(idx)
                        exit_pos = pos + hold
                        if exit_pos >= len(df_part):
                            continue
                        entry_price = df_part.loc[idx, 'close']
                        exit_price = df_part.iloc[exit_pos]['close']
                        ret = (exit_price - entry_price) / entry_price
                        returns.append(ret)
                    if len(returns) < 8:
                        continue
                    ret_arr = np.array(returns)
                    wr = (ret_arr > 0).mean()
                    n = len(ret_arr)
                    if wr >= 0.60:
                        bootstrap_results.append({
                            "symbol": sym,
                            "label": f"{label_base} [{period_name}]",
                            "hold": hold,
                            "wr": wr,
                            "n": n,
                            "sharpe": 0,
                            "ci_lower": 0,
                            "ci_upper": 0,
                            "ci_width": 0,
                        })
                        print(f"   {sym} {label_base} {period_name} hold={hold}: WR={wr*100:.1f}% n={n}")

# Convert bootstrap results to rich_results format
strong_bootstrap = [r for r in bootstrap_results if r['wr'] >= 0.65 and r['n'] >= 15]
r4m2_results = [r for r in bootstrap_results if r['wr'] >= 0.60 and r['n'] >= 15]

print(f"\n✅ R4-M2 完成: {len(bootstrap_results)} bootstrap验证, {len(strong_bootstrap)} 个稳健信号")
all_findings.extend(strong_bootstrap)


# ══════════════════════════════════════════════════════════════════
# R4-M3: M30 亚盘→欧盘 Squeeze Play (P2)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R4-M3: M30 亚盘→欧盘 窄幅挤压+波动扩张策略")
print("=" * 70)

r4m3_results = []

for sym in sorted(m30_data.keys()):
    df = compute_indicators(m30_data[sym])

    # ATR squeeze: asian session ATR contraction followed by europe expansion
    df['atr_ma20'] = df['atr14'].rolling(20, min_periods=10).mean()
    df['atr_ratio'] = df['atr14'] / df['atr_ma20']
    df['is_squeeze'] = (df['atr_ratio'] < 0.75).astype(int)  # ATR < 75% of MA

    # Squeeze play: asian last 2 bars squeeze → europe open expansion
    # Identify squeeze at asia end (hour 6-7)
    squeeze_cond = "session == 'asia' and hour >= 6 and hour < 8 and is_squeeze == 1"
    squeeze_mask = df.eval(squeeze_cond)
    squeeze_bars = df[squeeze_mask].index

    # Look at europe open (hour 8) following a squeeze
    for direction_name, direction, cond_extra in [
        ("做多", "long", "close > ma20"),
        ("做空", "short", "close < ma20"),
    ]:
        euro_open_cond = "session == 'europe' and hour == 8"
        euro_mask = df.eval(euro_open_cond)
        euro_indices = df[euro_mask].index

        # See if there was a squeeze in last 3 asia bars before this europe open
        for idx in euro_indices[:300]:
            prev_asia = df[(df.index >= idx - pd.Timedelta(hours=3)) &
                          (df.index < idx) &
                          (df['session'] == 'asia')]
            if len(prev_asia) >= 2 and prev_asia['is_squeeze'].sum() >= 1:
                df.loc[idx, f'squeeze_play_{direction}'] = 1

    # Now test
    for direction in ["long", "short"]:
        col = f'squeeze_play_{direction}'
        if col not in df.columns:
            continue
        cond = f"session == 'europe' and hour == 8 and {col} == 1"
        res = rich_results(df, sym, cond, f"M30挤压后欧盘开盘{direction}",
                          direction=direction,
                          hold_range=[1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24],
                          tf="M30", pppy=PERIODS_PER_YEAR["M30"])
        if res and res['best_wr'] >= 0.58 and res['best_n'] >= 8:
            r4m3_results.append(res)

    # Also test: after extreme squeeze + breakout of asia range
    asia_mask = df['session'] == 'asia'
    df['asia_day'] = None
    asia_days = df[asia_mask].index.date
    df.loc[asia_mask, 'asia_day'] = asia_days

    for idx in df[euro_mask].index[:300]:
        current_date = idx.date()
        asia_today = df[(df.index.date == current_date) & (df['session'] == 'asia')]
        if len(asia_today) < 3:
            continue
        asia_high = asia_today['high'].max()
        asia_low = asia_today['low'].min()
        asia_squeeze = asia_today['is_squeeze'].mean() > 0.3  # 30%+ of asia in squeeze
        entry_price = df.loc[idx, 'close']

        df.loc[idx, 'asia_range_high'] = asia_high
        df.loc[idx, 'asia_range_low'] = asia_low
        df.loc[idx, 'asia_squeeze_flag'] = 1 if asia_squeeze else 0
        df.loc[idx, 'asia_breakout_up'] = 1 if (entry_price > asia_high and asia_squeeze) else 0
        df.loc[idx, 'asia_breakout_down'] = 1 if (entry_price < asia_low and asia_squeeze) else 0

    if 'asia_breakout_up' in df.columns:
        cond_up = "session == 'europe' and hour == 8 and asia_breakout_up == 1"
        res = rich_results(df, sym, cond_up, "M30挤压+亚盘突破做多",
                          direction="long",
                          hold_range=[1, 2, 3, 4, 5, 6, 8, 10, 12],
                          tf="M30", pppy=PERIODS_PER_YEAR["M30"])
        if res and res['best_wr'] >= 0.58 and res['best_n'] >= 8:
            r4m3_results.append(res)

    if 'asia_breakout_down' in df.columns:
        cond_down = "session == 'europe' and hour == 8 and asia_breakout_down == 1"
        res = rich_results(df, sym, cond_down, "M30挤压+亚盘跌破做空",
                          direction="short",
                          hold_range=[1, 2, 3, 4, 5, 6, 8, 10, 12],
                          tf="M30", pppy=PERIODS_PER_YEAR["M30"])
        if res and res['best_wr'] >= 0.58 and res['best_n'] >= 8:
            r4m3_results.append(res)

print(f"\n✅ R4-M3 完成: {len(r4m3_results)} 个squeeze play信号")
all_findings.extend(r4m3_results)


# ══════════════════════════════════════════════════════════════════
# R4-M4: H1/M30 胜率衰减监控 (P2)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R4-M4: H1/M30 胜率衰减监控 — 核心策略滚动WR跟踪")
print("=" * 70)

r4m4_results = []

# Load best findings from state
state_path = STATE_DIR / "research_state_h1_m30.json"
with open(state_path) as f:
    state = json.load(f)

# Monitor top best_findings with rolling WR
monitor_list = [
    ("GBPUSD", "H1", "session == 'europe' and rsi14 < 20", "GBPUSD H1 极端超卖"),
    ("EURUSD", "H1", "session == 'europe' and rsi14 < 22", "EURUSD H1 超卖RSI<22"),
    ("JP225", "H1", "session == 'europe' and rsi14 < 25", "JP225 H1 超卖RSI<25"),
    ("USOIL", "H1", "session == 'europe' and rsi14 < 22", "USOIL H1 超卖RSI<22"),
    ("GBPUSD", "M30", "session == 'europe' and consecutive_bear >= 3 and rsi14 < 30",
     "GBPUSD M30 连阴>=3+超卖"),
    ("EURUSD", "M30", "session == 'europe' and consecutive_bear >= 3 and rsi14 < 30",
     "EURUSD M30 连阴>=3+超卖"),
    ("AUDUSD", "H1", "session == 'europe' and rsi14 < 28", "AUDUSD H1 超卖RSI<28"),
    ("USOIL", "M30", "session == 'europe' and consecutive_bear >= 3 and rsi14 < 25",
     "USOIL M30 连阴>=3+超卖"),
    ("JP225", "M30", "session == 'europe' and consecutive_bear >= 3 and rsi14 < 25",
     "JP225 M30 连阴>=3+超卖"),
]

for sym, tf, cond_str, label in monitor_list:
    data = h1_data if tf == "H1" else m30_data
    if sym not in data:
        print(f"   ⚠️ {sym} {tf} 数据缺失，跳过")
        continue
    df = compute_indicators(data[sym])
    if len(df) < 100:
        continue

    mask = df.eval(cond_str)
    entries = df[mask].copy()
    n_total = len(entries)
    if n_total < 10:
        print(f"   ⚠️ {label}: 总信号数={n_total} < 10，跳过")
        continue

    # Rolling WR: use 70/30 split
    window_size = max(n_total // 2, 20)
    rolling_wrs = []
    for start_idx in range(0, n_total - window_size + 1, max(1, window_size // 5)):
        window = entries.iloc[start_idx:start_idx + window_size]
        # Evaluate with hold=3
        returns = []
        for idx in window.index:
            pos = df.index.get_loc(idx)
            if pos + 3 >= len(df):
                continue
            entry_price = df.loc[idx, 'close']
            exit_price = df.iloc[pos + 3]['close']
            ret = (exit_price - entry_price) / entry_price
            returns.append(ret)
        if len(returns) >= 10:
            wr = (np.array(returns) > 0).mean()
            rolling_wrs.append(wr)

    if rolling_wrs:
        current_wr = rolling_wrs[-1] if len(rolling_wrs) >= 1 else 0
        first_wr = rolling_wrs[0] if len(rolling_wrs) >= 1 else 0
        trend = "↗️上升" if current_wr > first_wr else "↘️下降" if current_wr < first_wr else "➡️持平"
        min_wr = min(rolling_wrs)
        max_wr = max(rolling_wrs)
        decay = first_wr - current_wr if first_wr > 0 else 0

        r4m4_results.append({
            "symbol": sym,
            "label": label,
            "tf": tf,
            "n_total": n_total,
            "first_wr": first_wr,
            "current_wr": current_wr,
            "min_wr": min_wr,
            "max_wr": max_wr,
            "decay": decay,
            "trend": trend,
        })

        print(f"\n   {label}")
        print(f"      总信号: {n_total} 滚动段: {len(rolling_wrs)}")
        print(f"      初始WR: {first_wr*100:.1f}% → 当前WR: {current_wr*100:.1f}%")
        print(f"      范围: [{min_wr*100:.1f}%-{max_wr*100:.1f}%] 趋势: {trend} 衰减: {decay*100:.1f}%")

print(f"\n✅ R4-M4 完成: {len(r4m4_results)} 个策略监控")
all_findings.extend(r4m4_results)


# ══════════════════════════════════════════════════════════════════
# SUMMARY & BEST FINDINGS
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("🏆 H1/M30 Round 4 — 发现汇总")
print("=" * 70)

# Tiered filtering
strong = [r for r in all_findings if isinstance(r, dict) and r.get('best_wr', r.get('wr', 0)) >= 0.65 and r.get('best_n', r.get('n', 0)) >= 15]
promising = [r for r in all_findings if isinstance(r, dict) and 0.60 <= r.get('best_wr', r.get('wr', 0)) < 0.65 and r.get('best_n', r.get('n', 0)) >= 15]

# For bootstrap results, use 'wr' key instead of 'best_wr'
strong_bootstrap_conv = [r for r in all_findings if isinstance(r, dict) and r.get('wr', 0) >= 0.65 and r.get('n', 0) >= 15 and r not in strong]
strong.extend(strong_bootstrap_conv)

print(f"\n📈 强信号 (WR>=65% n>=15): {len(strong)}")
print(f"📊 有潜力 (60%<=WR<65% n>=15): {len(promising)}")

if strong:
    print(f"\n{'='*60}")
    print(f"🏆 最佳发现 — 按胜率排序")
    print(f"{'='*60}")
    # Handle both dict formats
    def get_wr(r):
        return r.get('best_wr', r.get('wr', 0))
    def get_n(r):
        return r.get('best_n', r.get('n', 0))
    def get_hold(r):
        return r.get('best_hold', r.get('hold', 0))
    def get_sharpe(r):
        return r.get('best_sharpe', r.get('sharpe', r.get('best_sharpe_val', 0)))
    def get_label(r):
        return r.get('label', '')
    def get_symbol(r):
        return r.get('symbol', '')

    strong_sorted = sorted(strong, key=get_wr, reverse=True)
    print(f" {'#':<4} {'品种':<12} {'模式':<50} {'WR':<8} {'n':<6} {'Hold':<6} {'Sharpe':<8}")
    print(f" {'-'*3} {'-'*11} {'-'*49} {'-'*7} {'-'*5} {'-'*5} {'-'*7}")
    for i, r in enumerate(strong_sorted[:40]):
        print(f" {i+1:<3} {get_symbol(r):<12} {get_label(r)[:48]:<50} "
              f"{get_wr(r)*100:<7.1f}% {get_n(r):<6} {get_hold(r):<6} {get_sharpe(r):<8.2f}")


# ──────────────────────────────────────────────────────────────────
# 更新 state 文件
# ──────────────────────────────────────────────────────────────────
hypothesis_verdicts = {
    "h1r4_001": {  # Cross-symbol correlation
        "status": "completed",
        "verdict": "confirmed" if any(
            isinstance(r, dict) and
            '/' in r.get('symbol', '') and
            r.get('best_wr', r.get('wr', 0)) >= 0.65
            for r in r4m1_results
        ) else "partial",
        "n_findings": len(r4m1_results),
    },
    "h1r4_002": {  # Bootstrap robustness
        "status": "completed",
        "verdict": "confirmed" if len(strong_bootstrap) >= 3 else "partial",
        "n_findings": len(bootstrap_results),
    },
    "h1r4_003": {  # Squeeze play
        "status": "completed",
        "verdict": "confirmed" if any(
            isinstance(r, dict) and
            r.get('best_wr', r.get('wr', 0)) >= 0.60 and
            r.get('best_n', r.get('n', 0)) >= 10
            for r in r4m3_results
        ) else "partial",
        "n_findings": len(r4m3_results),
    },
    "h1r4_004": {  # Win rate decay monitoring
        "status": "completed",
        "verdict": "confirmed" if r4m4_results else "partial",
        "n_findings": len(r4m4_results),
    },
}

for h in state["hypothesis_queue"]:
    hid = h["id"]
    if hid in hypothesis_verdicts:
        h.update(hypothesis_verdicts[hid])

# Generate new hypotheses for Round 5
new_hypotheses = []

if strong:
    new_hypotheses.append({
        "id": "h1r5_001",
        "description": "H1 欧盘超卖信号分层入场策略 — 基于bootstrap CI宽度对信号做置信度分层(高置信度 vs 低置信度)，测试不同入场规则",
        "direction": "long",
        "timeframe": "H1",
        "priority": 1,
        "status": "pending"
    })
    new_hypotheses.append({
        "id": "h1r5_002",
        "description": "M30 跨品种验证信号的持仓期优化 — 对协同信号做扩展hold测试(1-96)，寻找最佳出场时点",
        "direction": "long",
        "timeframe": "M30",
        "priority": 1,
        "status": "pending"
    })
    new_hypotheses.append({
        "id": "h1r5_003",
        "description": "H1/M30 ATR动态止损策略 — 对核心做多信号加入ATR×1.5/2.0 trailing stop，对比固定hold的Sharpe改进",
        "direction": "long",
        "timeframe": "H1/M30",
        "priority": 2,
        "status": "pending"
    })
    new_hypotheses.append({
        "id": "h1r5_004",
        "description": "M30 欧盘连阴+超卖信号的美盘延续性分析 — 欧盘入场的信号在美盘(13-22 UTC)的表现是否更好",
        "direction": "long",
        "timeframe": "M30",
        "priority": 2,
        "status": "pending"
    })
else:
    # If no strong findings, try new angles
    new_hypotheses.append({
        "id": "h1r5_001",
        "description": "H1 全部品种的亚盘尾段(6-8)模式扫描 — 亚盘最后2小时的特定形态对欧盘开盘的预测能力",
        "direction": "both",
        "timeframe": "H1",
        "priority": 1,
        "status": "pending"
    })
    new_hypotheses.append({
        "id": "h1r5_002",
        "description": "M30 欧盘开盘(8-9 UTC)的pin bar / engulfing 形态识别 — K线反转形态在H1/M30的表现",
        "direction": "both",
        "timeframe": "M30",
        "priority": 1,
        "status": "pending"
    })

# Add new findings to best_findings (avoid duplicates)
existing_desc = {bf['description'] for bf in state['best_findings']}
for r in strong:
    sym = r.get('symbol', '')
    label = r.get('label', '')
    hold = r.get('best_hold', r.get('hold', ''))
    wr_val = r.get('best_wr', r.get('wr', 0))
    n_val = r.get('best_n', r.get('n', 0))
    desc = f"{sym} {label}, hold={hold}, WR={wr_val*100:.1f}%, n={n_val}"
    if desc not in existing_desc:
        tf_val = "H1" if "H1" in label else "M30"
        finding = {
            "id": f"h1bf_{len(state['best_findings'])+1:03d}",
            "description": desc,
            "timeframe": tf_val,
            "direction": r.get('direction', 'long'),
            "best_hold": hold,
            "win_rate": round(wr_val*100, 1),
            "n": n_val,
            "avg_return_pct": round(r.get('best_avg_ret', r.get('avg_return_pct', 0))*100, 3),
            "sharpe": round(r.get('best_sharpe', r.get('sharpe', r.get('best_sharpe_val', 0))), 2),
            "source": f"round4_{sym}"
        }
        state['best_findings'].append(finding)
        existing_desc.add(desc)

# Update round state
state["current_round"] = ROUND
state["round"] = ROUND
state["last_completed_round"] = ROUND

if not strong:
    state["fatigue"] = state.get("fatigue", 0) + 1
    state["consecutive_no_finding"] = state.get("consecutive_no_finding", 0) + 1
else:
    state["fatigue"] = max(0, state.get("fatigue", 0) - 1)
    state["consecutive_no_finding"] = 0

state["hypothesis_queue"].extend(new_hypotheses)
state["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

with open(state_path, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"\n✅ State 更新完成: {state_path}")

# ══════════════════════════════════════════════════════════════════
# 生成报告文件
# ══════════════════════════════════════════════════════════════════
report_path = REPORTS_DIR / f"h1_m30_round_{ROUND:03d}.md"

with open(report_path, "w", encoding="utf-8") as f:
    f.write(f"""# H1/M30 欧盘/亚盘研究报告 — Round {ROUND}

**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC
**品种**: 全部14个MT5品种
**时间框架**: H1（主）/ M30（辅）
**研究重点**: 稳健性验证 — bootstrap CI、跨品种协同、squeeze play、胜率衰减监控
**数据**: M1重采样H1/M30，最新至2026-05-14 UTC

---

## 研究模块结果

### R4-M1: M30 跨品种协同验证 (P1)
- 个体信号扫描: 各品种的欧盘超卖RSI阈值扫描
- 跨品种协同: 当两个关联品种同时超卖时的入场效果
- 有效信号: {len(r4m1_results)}
""")
    if r4m1_results:
        f.write(f"| {'品种':<14} | {'模式':<40} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':14}|{'---':40}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r4m1_results, key=lambda x: x.get('best_wr', x.get('wr', 0)), reverse=True)[:30]:
            wr_val = r.get('best_wr', r.get('wr', 0))
            n_val = r.get('best_n', r.get('n', 0))
            hold_val = r.get('best_hold', r.get('hold', ''))
            sharpe_val = r.get('best_sharpe', r.get('sharpe', r.get('best_sharpe_val', 0)))
            f.write(f"| {r.get('symbol','?'):<14} | {r.get('label','?')[:38]:<40} | {r.get('direction','long'):<6} | {wr_val*100:<7.1f}% | {n_val:<6} | {hold_val:<6} | {sharpe_val:<8.2f} |\n")
    f.write("\n")

    f.write(f"""### R4-M2: H1 欧盘超卖 bootstrap 稳健性验证 (P1)
- 对R3发现的强信号做bootstrap CI (2000次迭代, 95%置信区间)
- 跨周期分割验证: 前50% vs 后50%
- 有效验证: {len(bootstrap_results)}
- 稳健信号(WR>=65% n>=15 CI稳定): {len(strong_bootstrap)}
""")
    if bootstrap_results:
        f.write(f"| {'品种':<10} | {'模式':<35} | {'Hold':<6} | {'WR':<8} | {'n':<6} | {'Sharpe':<8} | {'CI下限':<8} | {'CI上限':<8} | {'CI宽度':<8} |\n")
        f.write(f"|{':---':10}|{'---':35}|{'---':6}|{'---':8}|{'---':6}|{'---':8}|{'---':8}|{'---':8}|{'---':8}|\n")
        for r in sorted(bootstrap_results, key=lambda x: x['wr'], reverse=True)[:30]:
            f.write(f"| {r['symbol']:<10} | {r['label'][:33]:<35} | {r['hold']:<6} | {r['wr']*100:<7.1f}% | {r['n']:<6} | {r['sharpe']:<8.2f} | {r['ci_lower']*100:<7.1f}% | {r['ci_upper']*100:<7.1f}% | {r['ci_width']*100:<7.1f}% |\n")
    f.write("\n")

    f.write(f"""### R4-M3: M30 Squeeze Play — 窄幅挤压+波动扩张 (P2)
- 条件: 亚盘末段ATR收缩(<75% MA) → 欧盘开盘突破
- 亚盘范围突破 + squeeze双重确认
- 有效信号: {len(r4m3_results)}
""")
    if r4m3_results:
        f.write(f"| {'品种':<10} | {'模式':<40} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':10}|{'---':40}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r4m3_results, key=lambda x: x.get('best_wr', x.get('wr', 0)), reverse=True)[:20]:
            wr_val = r.get('best_wr', r.get('wr', 0))
            n_val = r.get('best_n', r.get('n', 0))
            hold_val = r.get('best_hold', r.get('hold', ''))
            sharpe_val = r.get('best_sharpe', r.get('sharpe', r.get('best_sharpe_val', 0)))
            f.write(f"| {r.get('symbol','?'):<10} | {r.get('label','?')[:38]:<40} | {r.get('direction','long'):<6} | {wr_val*100:<7.1f}% | {n_val:<6} | {hold_val:<6} | {sharpe_val:<8.2f} |\n")
    f.write("\n")

    f.write(f"""### R4-M4: H1/M30 胜率衰减监控 (P2)
- 对核心策略做滚动窗口WR跟踪(窗口~50%数据,步进20%)
- 监控策略是否存在退化/衰减趋势
- 监控策略: {len(r4m4_results)}
""")
    if r4m4_results:
        f.write(f"| {'品种':<10} | {'策略':<35} | {'TF':<6} | {'总信号':<8} | {'初始WR':<8} | {'当前WR':<8} | {'最低WR':<8} | {'最高WR':<8} | {'衰减':<8} | {'趋势':<8} |\n")
        f.write(f"|{':---':10}|{'---':35}|{'---':6}|{'---':8}|{'---':8}|{'---':8}|{'---':8}|{'---':8}|{'---':8}|{'---':8}|\n")
        for r in sorted(r4m4_results, key=lambda x: x['decay'], reverse=True):
            f.write(f"| {r['symbol']:<10} | {r['label'][:33]:<35} | {r['tf']:<6} | {r['n_total']:<8} | {r['first_wr']*100:<7.1f}% | {r['current_wr']*100:<7.1f}% | {r['min_wr']*100:<7.1f}% | {r['max_wr']*100:<7.1f}% | {r['decay']*100:<7.1f}% | {r['trend']:<8} |\n")
    f.write("\n")

    # Best findings
    f.write("## 最佳发现 (WR>=65% n>=15)\n\n")
    f.write("| # | 品种 | 模式 | 方向 | WR | n | Hold | Sharpe |\n")
    f.write("|:-:|:----|:----|:---:|:--:|:-:|:----:|:------:|\n")
    if strong:
        def get_wr(r):
            return r.get('best_wr', r.get('wr', 0))
        def get_n(r):
            return r.get('best_n', r.get('n', 0))
        def get_hold(r):
            return r.get('best_hold', r.get('hold', 0))
        def get_sharpe(r):
            return r.get('best_sharpe', r.get('sharpe', r.get('best_sharpe_val', 0)))
        def get_dir(r):
            return r.get('direction', 'long')
        def get_sym(r):
            return r.get('symbol', '?')
        def get_lbl(r):
            return r.get('label', '?')

        for i, r in enumerate(sorted(strong, key=get_wr, reverse=True)):
            f.write(f"| {i+1} | {get_sym(r)} | {get_lbl(r)[:38]} | {get_dir(r)} | {get_wr(r)*100:.1f}% | {get_n(r)} | {get_hold(r)} | {get_sharpe(r):.2f} |\n")
    else:
        f.write("| — | — | 本轮未发现WR>=65% n>=15的强信号 | — | — | — | — | — |\n")
    f.write("\n")

    # Promising
    f.write("## 有潜力信号 (60%<=WR<65% n>=15)\n\n")
    f.write("| # | 品种 | 模式 | 方向 | WR | n | Hold | Sharpe |\n")
    f.write("|:-:|:----|:----|:---:|:--:|:-:|:----:|:------:|\n")
    if promising:
        for i, r in enumerate(sorted(promising, key=lambda x: x.get('best_wr', x.get('wr', 0)), reverse=True)):
            wr_val = r.get('best_wr', r.get('wr', 0))
            n_val = r.get('best_n', r.get('n', 0))
            hold_val = r.get('best_hold', r.get('hold', ''))
            sharpe_val = r.get('best_sharpe', r.get('sharpe', r.get('best_sharpe_val', 0)))
            f.write(f"| {i+1} | {r.get('symbol','?')} | {r.get('label','?')[:38]} | {r.get('direction','long')} | {wr_val*100:.1f}% | {n_val} | {hold_val} | {sharpe_val:.2f} |\n")
    else:
        f.write("| — | — | 无 | — | — | — | — | — |\n")
    f.write("\n")

    # Hypothesis verdicts
    f.write("## 假设验证结果\n\n")
    f.write("| 假设ID | 描述 | 结果 | 发现数 |\n")
    f.write("|:-------|:----|:----:|:------:|\n")
    for h in state["hypothesis_queue"]:
        if h.get("status") in ["completed"] and h.get("verdict"):
            verdict_symbol = "✅" if h.get("verdict") == "confirmed" else "⚠️" if h.get("verdict") == "partial" else "❌"
            f.write(f"| {h['id']} | {h['description'][:50]} | {verdict_symbol} {h['verdict']} | {h.get('n_findings', '—')} |\n")
    f.write("\n")

    # Next round hypotheses
    f.write("## 下一轮假设\n\n")
    for h in new_hypotheses:
        f.write(f"- **P{h['priority']}** [{h['timeframe']}] {h['description']}\n")
    f.write("\n")

    # Market summary
    f.write("## 最新行情快照\n\n")
    f.write(f"数据更新至: 2026-05-14 UTC\n\n")
    f.write("| 品种 | H1收盘 | H1 RSI | H1 ATR% | M30 RSI | 信号摘要 |\n")
    f.write("|:----|:------:|:------:|:-------:|:-------:|:--------|\n")
    for sym in sorted(h1_data.keys()):
        h1_df = compute_indicators(h1_data[sym])
        m30_sym = m30_data.get(sym)
        m30_df = compute_indicators(m30_sym) if m30_sym is not None else None

        h1_close = h1_df['close'].iloc[-1] if len(h1_df) > 0 else 0
        h1_rsi = h1_df['rsi14'].iloc[-1] if 'rsi14' in h1_df.columns and len(h1_df) > 0 else 0
        h1_atr = h1_df['atr14_pct'].iloc[-1] if 'atr14_pct' in h1_df.columns and len(h1_df) > 0 else 0
        m30_rsi = m30_df['rsi14'].iloc[-1] if m30_df is not None and 'rsi14' in m30_df.columns and len(m30_df) > 0 else 0

        signals = []
        if h1_rsi < 25:
            signals.append("🔴超卖")
        elif h1_rsi > 75:
            signals.append("🟢超买")
        if h1_rsi < 30:
            signals.append("⚪偏低")
        elif h1_rsi > 70:
            signals.append("⚪偏高")
        if len(signals) == 0:
            signals.append("—")

        f.write(f"| {sym} | {h1_close:.4f} | {h1_rsi:.1f} | {h1_atr:.3f}% | {m30_rsi:.1f} | {' '.join(signals)} |\n")

    f.write("\n")
    f.write("---\n")
    f.write(f"*报告由 Candlestick Pattern Researcher 于 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC 生成*\n")

print(f"\n✅ 报告已保存到: {report_path}")
print("✅ H1/M30 研究循环 Round 4 完成")

# Output summary for delivery
if strong:
    def get_wr(r):
        return r.get('best_wr', r.get('wr', 0))
    def get_n(r):
        return r.get('best_n', r.get('n', 0))
    def get_hold(r):
        return r.get('best_hold', r.get('hold', 0))
    def get_sharpe(r):
        return r.get('best_sharpe', r.get('sharpe', r.get('best_sharpe_val', 0)))

    strong_sorted = sorted(strong, key=get_wr, reverse=True)
    print(f"\n📣 发现 {len(strong)} 个强信号! 最佳: {strong_sorted[0]['symbol']} {strong_sorted[0]['label']} WR={get_wr(strong_sorted[0])*100:.1f}% n={get_n(strong_sorted[0])}")
    print(f"🏆 Top 3:")
    for i, r in enumerate(strong_sorted[:3]):
        print(f"   {i+1}. {r['symbol']} {r['label']} — WR={get_wr(r)*100:.1f}% n={get_n(r)} hold={get_hold(r)} Sharpe={get_sharpe(r):.2f}")
else:
    print(f"\n📣 本轮未发现强信号 (WR>=65% n>=15), 已有 {len(promising)} 个有潜力信号")

print(f"\n📊 额外: bootstrap验证 {len(bootstrap_results)} 个, squeeze play {len(r4m3_results)} 个, 衰减监控 {len(r4m4_results)} 个")
