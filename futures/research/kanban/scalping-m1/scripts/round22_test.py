#!/usr/bin/env python3
"""
Round 22 — 超短线研究循环
Testing priority=1 hypotheses:
1. round22_001: XAG+XAU 共振CB>=1 数据积累(n>30验证)
2. round22_002: XAUUSD 欧盘9-11 RSI<18+CB>=4 vs bf_046 US 15-16 对比验证
3. round22_003: JP225 RSI<14+CB>=2 跨周期深入验证
4. round22_004: XAUUSD M1 欧盘RSI<16+CB>=3 跨周期稳定性再验证
5. round22_005: XAG+XAU 欧盘共振n>30积累验证 + 阈值调优
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def add_session_and_cb(df):
    """Add session and correct consecutive_bear/bull columns."""
    df = df.copy()
    df['session'] = 'asia'
    df.loc[(df.index.hour >= 8) & (df.index.hour < 13), 'session'] = 'europe'
    df.loc[(df.index.hour >= 13) & (df.index.hour < 22), 'session'] = 'us'
    
    bear = (df['close'] < df['open']).astype(int)
    df['consecutive_bear'] = bear.groupby((bear == 0).cumsum()).cumsum()
    bull = (df['close'] > df['open']).astype(int)
    df['consecutive_bull'] = bull.groupby((bull == 0).cumsum()).cumsum()
    return df

def test_condition(df, condition_mask, label, hold_range=None):
    """Test a condition on data and report results across hold periods."""
    entries = df[condition_mask].copy()
    print(f"\n--- {label} ---")
    print(f"Entry signals: {len(entries)}")
    
    if len(entries) < 5:
        print(f"  ⚠️  Too few signals ({len(entries)}), skipping")
        return entries
    
    if hold_range is None:
        hold_range = list(range(30, 131, 5))
    
    results = {}
    for hold in hold_range:
        hits = 0
        total_pnl = 0.0
        count = 0
        for idx, row in entries.iterrows():
            entry_price = row['close']
            pos = df.index.get_loc(idx)
            if pos + hold < len(df):
                exit_price = df.iloc[pos + hold]['close']
            else:
                continue
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            count += 1
            if pnl > 0:
                hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            results[hold] = {'n': count, 'wr': wr, 'avg_ret': avg_ret}
    
    if results:
        best_hold = max(results, key=lambda h: results[h]['wr'] * 0.7 + min(results[h]['n'] / 200, 1) * 30)
        best = results[best_hold]
        print(f"  Best hold={best_hold}: WR={best['wr']:.1f}% n={best['n']} avg={best['avg_ret']:.3f}%")
        sorted_results = sorted(results.items(), key=lambda x: x[1]['wr'], reverse=True)[:5]
        for hold, r in sorted_results:
            print(f"    hold={hold:3d}: WR={r['wr']:.1f}% n={r['n']} avg={r['avg_ret']:.3f}%")
    
    return entries

def test_condition_with_periods(df, condition_mask, label, hold_range=None):
    """Test with P1/P2/P3 period breakdown for stability check."""
    entries_all = df[condition_mask].copy()
    print(f"\n--- {label} (跨周期稳定性验证) ---")
    print(f"Total signals: {len(entries_all)}")
    
    if len(entries_all) < 10:
        print(f"  ⚠️  Too few signals ({len(entries_all)}), skipping period breakdown")
        return test_condition(df, condition_mask, label, hold_range)
    
    if hold_range is None:
        hold_range = list(range(30, 131, 5))
    
    # Split data into 3 periods chronologically
    dates = df.index.sort_values()
    n_idx = len(dates)
    split1 = dates[int(n_idx * 0.33)]
    split2 = dates[int(n_idx * 0.67)]
    
    periods = {
        'P1 (最早)': df[df.index < split1],
        'P2 (中段)': df[(df.index >= split1) & (df.index < split2)],
        'P3 (最近)': df[df.index >= split2],
    }
    
    all_results = {}
    for period_name, period_df in periods.items():
        period_mask = condition_mask.reindex(period_df.index, fill_value=False)
        entries = period_df[period_mask].copy()
        
        results = {}
        for hold in hold_range:
            hits = 0
            total_pnl = 0.0
            count = 0
            for idx, row in entries.iterrows():
                entry_price = row['close']
                pos = period_df.index.get_loc(idx)
                if pos + hold < len(period_df):
                    exit_price = period_df.iloc[pos + hold]['close']
                else:
                    continue
                pnl = (exit_price - entry_price) / entry_price * 100
                total_pnl += pnl
                count += 1
                if pnl > 0:
                    hits += 1
            if count > 0:
                wr = hits / count * 100
                avg_ret = total_pnl / count
                results[hold] = {'n': count, 'wr': wr, 'avg_ret': avg_ret}
        
        if results:
            best_hold = max(results, key=lambda h: results[h]['wr'] * 0.7 + min(results[h]['n'] / 200, 1) * 30)
            best = results[best_hold]
            all_results[period_name] = (best_hold, best)
            print(f"  {period_name}: n={best['n']} hold={best_hold} WR={best['wr']:.1f}% avg={best['avg_ret']:.3f}%")
    
    # Full period
    entries = entries_all
    results_full = {}
    for hold in hold_range:
        hits = 0
        total_pnl = 0.0
        count = 0
        for idx, row in entries.iterrows():
            entry_price = row['close']
            pos = df.index.get_loc(idx)
            if pos + hold < len(df):
                exit_price = df.iloc[pos + hold]['close']
            else:
                continue
            pnl = (exit_price - entry_price) / entry_price * 100
            total_pnl += pnl
            count += 1
            if pnl > 0:
                hits += 1
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            results_full[hold] = {'n': count, 'wr': wr, 'avg_ret': avg_ret}
    
    if results_full:
        best_hold = max(results_full, key=lambda h: results_full[h]['wr'] * 0.7 + min(results_full[h]['n'] / 200, 1) * 30)
        best = results_full[best_hold]
        print(f"  全周期:    n={best['n']} hold={best_hold} WR={best['wr']:.1f}% avg={best['avg_ret']:.3f}%")
    
    return entries_all

def print_compact_comparison(title, data):
    """Print a compact comparison table."""
    print(f"\n  ** {title} **")
    print(f"  {'条件':<45} {'信号数':<8} {'Hold':<6} {'胜率':<8} {'平均收益':<12}")
    print(f"  {'-'*45} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")
    for row in data:
        print(f"  {row[0]:<45} {row[1]:<8} {row[2]:<6} {row[3]:<8} {row[4]:<12}")

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 70)
print("ROUND 22 — Scalping M1/M5 数据积累 + 跨周期再验证")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=22, testing round22_001~005")
print("=" * 70)

# ── Load data ──
for tf in ["M5", "M1"]:
    print(f"\n--- {tf} Data Summary ---")
    data = load_data(tf, symbols=["XAUUSD", "XAGUSD", "JP225", "US500", "US30"])
    for sym, df in data.items():
        df2 = compute_indicators(df)
        rsi_val = df2['rsi14'].iloc[-1]
        atr_val = df2['atr14_pct'].iloc[-1]
        close_val = df2['close'].iloc[-1]
        print(f"  {sym:8s} {tf}: {len(df2):>8} rows  [{df2.index[0].date()} → {df2.index[-1].date()}]  "
              f"Close={close_val:.1f}  RSI={rsi_val:.1f}  ATR%={atr_val:.3f}%")

# ═══════════════════════════════════════════════════════════════
# H1: XAG+XAU 共振CB>=1 数据积累(n>30验证)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H1: XAG+XAU 共振CB>=1 — 数据积累(n>30验证)")
print("=" * 70)
print("目标: 验证CB>=1共振模式信号数能否超过30，且WR>85%")

xag_m5_raw = load_data("M5", symbols=["XAGUSD"])
xau_m5_raw = load_data("M5", symbols=["XAUUSD"])

if xag_m5_raw and xau_m5_raw:
    xag_m5 = compute_indicators(xag_m5_raw["XAGUSD"])
    xag_m5 = add_session_and_cb(xag_m5)
    xau_m5 = compute_indicators(xau_m5_raw["XAUUSD"])
    xau_m5 = add_session_and_cb(xau_m5)
    
    # ── CB>=1 共振 (已从round21获知WR=95.5% n=22) ──
    xag_cb1 = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 15) &
        (xag_m5.index.hour < 16) &
        (xag_m5['rsi14'] < 20) &
        (xag_m5['consecutive_bear'] >= 1)
    )
    xau_cb1 = (
        (xau_m5['session'] == 'us') &
        (xau_m5.index.hour >= 15) &
        (xau_m5.index.hour < 16) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 1)
    )
    both_cb1 = xag_cb1 & xau_cb1
    print(f"\nXAG+XAU 美盘15-16 同bar共振 (CB>=1): {both_cb1.sum()} signals")
    if both_cb1.sum() >= 5:
        test_condition(xau_m5, both_cb1, "共振CB>=1→XAU做多 (hold=95重点验证)",
                      hold_range=[85, 90, 95, 100, 105, 110, 115, 120])
        test_condition(xag_m5, both_cb1, "共振CB>=1→XAG做多 (hold=95重点验证)",
                      hold_range=[85, 90, 95, 100, 105, 110, 115, 120])
    
    # ── 扩展窗口: 14-17 (更宽美盘窗口) ──
    xag_wide = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 14) &
        (xag_m5.index.hour < 17) &
        (xag_m5['rsi14'] < 20) &
        (xag_m5['consecutive_bear'] >= 1)
    )
    xau_wide = (
        (xau_m5['session'] == 'us') &
        (xau_m5.index.hour >= 14) &
        (xau_m5.index.hour < 17) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 1)
    )
    both_wide = xag_wide & xau_wide
    print(f"\nXAG+XAU 美盘14-17 宽窗口共振 (CB>=1): {both_wide.sum()} signals")
    if both_wide.sum() >= 5:
        test_condition(xau_m5, both_wide, "共振宽窗口→XAU做多",
                      hold_range=[85, 90, 95, 100, 105, 110, 115, 120])
        test_condition(xag_m5, both_wide, "共振宽窗口→XAG做多",
                      hold_range=[85, 90, 95, 100, 105, 110, 115, 120])
    
    # ── RSI<18+CB>=1 共振 (round21: 100% n=10, 需要积累) ──
    xag_rsi18_cb1 = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 15) &
        (xag_m5.index.hour < 16) &
        (xag_m5['rsi14'] < 18) &
        (xag_m5['consecutive_bear'] >= 1)
    )
    xau_rsi18_cb1 = (
        (xau_m5['session'] == 'us') &
        (xau_m5.index.hour >= 15) &
        (xau_m5.index.hour < 16) &
        (xau_m5['rsi14'] < 18) &
        (xau_m5['consecutive_bear'] >= 1)
    )
    both_rsi18_cb1 = xag_rsi18_cb1 & xau_rsi18_cb1
    print(f"\nXAG+XAU 美盘15-16 RSI<18+CB>=1 共振: {both_rsi18_cb1.sum()} signals")
    if both_rsi18_cb1.sum() >= 5:
        test_condition_with_periods(xau_m5, both_rsi18_cb1, "RSI<18+CB>=1 共振→XAU",
                                    hold_range=[85, 90, 95, 100, 105, 110, 115, 120])
        test_condition_with_periods(xag_m5, both_rsi18_cb1, "RSI<18+CB>=1 共振→XAG",
                                    hold_range=[85, 90, 95, 100, 105, 110, 115, 120])
else:
    print("  ⚠️  XAGUSD or XAUUSD M5 data not available")

# ═══════════════════════════════════════════════════════════════
# H2: XAUUSD 欧盘9-11 RSI<18+CB>=4 vs bf_046 US 15-16 对比验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H2: XAUUSD 欧盘9-11 RSI<18+CB>=4 vs bf_046 US 15-16 对比验证")
print("=" * 70)
print("目标: 比较XAUUSD两个最佳模式在不同时段的稳定性及优劣")

if xau_m5_raw:
    xau_m5_2 = compute_indicators(xau_m5_raw["XAUUSD"])
    xau_m5_2 = add_session_and_cb(xau_m5_2)
    
    # ── 欧盘9-11 RSI<18+CB>=4 (round21最佳欧盘模式) ──
    mask_eu_9_11 = (
        (xau_m5_2['session'] == 'europe') &
        (xau_m5_2.index.hour >= 9) &
        (xau_m5_2.index.hour < 11) &
        (xau_m5_2['rsi14'] < 18) &
        (xau_m5_2['consecutive_bear'] >= 4)
    )
    print(f"\n--- XAUUSD 欧盘9-11 RSI<18+CB>=4 ---")
    entries_eu = xau_m5_2[mask_eu_9_11]
    print(f"Signals: {len(entries_eu)}")
    if len(entries_eu) >= 10:
        test_condition_with_periods(xau_m5_2, mask_eu_9_11, "欧盘9-11 RSI<18+CB>=4",
                                    hold_range=[38, 40, 42, 44, 46, 48, 50, 52])
    
    # ── bf_046: US 15-16 RSI<20+CB>=2 (美盘经典模式) ──
    mask_us_15_16 = (
        (xau_m5_2['session'] == 'us') &
        (xau_m5_2.index.hour >= 15) &
        (xau_m5_2.index.hour < 16) &
        (xau_m5_2['rsi14'] < 20) &
        (xau_m5_2['consecutive_bear'] >= 2)
    )
    print(f"\n--- XAUUSD 美盘15-16 RSI<20+CB>=2 (bf_046) ---")
    entries_us = xau_m5_2[mask_us_15_16]
    print(f"Signals: {len(entries_us)}")
    if len(entries_us) >= 10:
        test_condition_with_periods(xau_m5_2, mask_us_15_16, "美盘15-16 RSI<20+CB>=2 (bf_046)",
                                    hold_range=[105, 110, 115, 120, 125, 130, 135, 140])
    
    # ── 对比总览 ──
    print(f"\n{'='*60}")
    print("H2 对比总结:")
    print(f"{'='*60}")
    
    # Quick comparison at recommended holds
    comparison_data = []
    for label, mask, holds in [
        ("欧盘9-11 RSI<18+CB>=4", mask_eu_9_11, [42, 44, 46, 48]),
        ("美盘15-16 RSI<20+CB>=2 (bf_046)", mask_us_15_16, [115, 120, 125]),
    ]:
        entries = xau_m5_2[mask]
        for hold in holds:
            hits = 0
            total_pnl = 0.0
            count = 0
            for idx, row in entries.iterrows():
                entry_price = row['close']
                pos = xau_m5_2.index.get_loc(idx)
                if pos + hold < len(xau_m5_2):
                    exit_price = xau_m5_2.iloc[pos + hold]['close']
                else:
                    continue
                pnl = (exit_price - entry_price) / entry_price * 100
                total_pnl += pnl
                count += 1
                if pnl > 0:
                    hits += 1
            if count > 0:
                wr = hits / count * 100
                avg_ret = total_pnl / count
                comparison_data.append((label, str(count), str(hold), f"{wr:.1f}%", f"{avg_ret:.3f}%"))
    
    print_compact_comparison("XAUUSD 欧盘 vs 美盘 模式对比", comparison_data)

# ═══════════════════════════════════════════════════════════════
# H3: JP225 RSI<14+CB>=2 跨周期深入验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H3: JP225 RSI<14+CB>=2 跨周期深入验证")
print("=" * 70)
print("目标: 验证Round21最佳的JP225模式(RSI<14+CB>=2)跨周期稳定性")

jp_m5_raw = load_data("M5", symbols=["JP225"])
if jp_m5_raw:
    jp_m5 = compute_indicators(jp_m5_raw["JP225"])
    jp_m5 = add_session_and_cb(jp_m5)
    
    # RSI<14+CB>=2 (round21最佳)
    mask_jp_rsi14_cb2 = (
        (jp_m5['session'] == 'us') &
        (jp_m5.index.hour >= 15) &
        (jp_m5.index.hour < 16) &
        (jp_m5['rsi14'] < 14) &
        (jp_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(jp_m5, mask_jp_rsi14_cb2, "JP225 US 15-16 RSI<14+CB>=2",
                                hold_range=[50, 55, 60, 65, 70, 75, 80, 85])
    
    # ── 扩展窗口: 15-18 RSI<14+CB>=2 (更多信号) ──
    mask_jp_wide = (
        (jp_m5['session'] == 'us') &
        (jp_m5.index.hour >= 15) &
        (jp_m5.index.hour < 18) &
        (jp_m5['rsi14'] < 14) &
        (jp_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(jp_m5, mask_jp_wide, "JP225 US 15-18 RSI<14+CB>=2 (扩展窗口)",
                                hold_range=[50, 55, 60, 65, 70, 75, 80, 85])
    
    # ── 交替: RSI<14+CB>=3 (更严格CB) ──
    mask_jp_rsi14_cb3 = (
        (jp_m5['session'] == 'us') &
        (jp_m5.index.hour >= 15) &
        (jp_m5.index.hour < 16) &
        (jp_m5['rsi14'] < 14) &
        (jp_m5['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(jp_m5, mask_jp_rsi14_cb3, "JP225 US 15-16 RSI<14+CB>=3",
                                hold_range=[50, 55, 60, 65, 70, 75, 80, 85])
else:
    print("  ⚠️  JP225 M5 data not available")

# ═══════════════════════════════════════════════════════════════
# H4: XAUUSD M1 欧盘RSI<16+CB>=3 跨周期稳定性再验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H4: XAUUSD M1 欧盘RSI<16+CB>=3 跨周期稳定性再验证")
print("=" * 70)
print("目标: M1最佳模式(RSI<16+CB>=3)跨周期是否持续稳定")

xau_m1_raw = load_data("M1", symbols=["XAUUSD"])
if xau_m1_raw:
    xau_m1 = compute_indicators(xau_m1_raw["XAUUSD"])
    xau_m1 = add_session_and_cb(xau_m1)
    
    # RSI<16+CB>=3 (round21最佳M1模式)
    mask_m1_rsi16_cb3 = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 8) &
        (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 16) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xau_m1, mask_m1_rsi16_cb3,
                                "M1 欧盘8-11 RSI<16+CB>=3",
                                hold_range=[12, 14, 16, 18, 20, 23, 25, 28, 30])
    
    # ── 9-11窄窗口 RSI<16+CB>=3 ──
    mask_m1_9_11_rsi16_cb3 = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 9) &
        (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 16) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xau_m1, mask_m1_9_11_rsi16_cb3,
                                "M1 欧盘9-11 RSI<16+CB>=3",
                                hold_range=[12, 14, 16, 18, 20, 23, 25, 28, 30])
    
    # ── 8-11 RSI<16+CB>=2 (更多信号, 但可能胜率稍低) ──
    mask_m1_rsi16_cb2 = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 8) &
        (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 16) &
        (xau_m1['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(xau_m1, mask_m1_rsi16_cb2,
                                "M1 欧盘8-11 RSI<16+CB>=2",
                                hold_range=[12, 14, 16, 18, 20, 23, 25, 28, 30])
    
    # ── 8-11 RSI<15+CB>=3 (更紧RSI) ──
    mask_m1_rsi15_cb3 = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 8) &
        (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 15) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xau_m1, mask_m1_rsi15_cb3,
                                "M1 欧盘8-11 RSI<15+CB>=3",
                                hold_range=[12, 14, 16, 18, 20, 23, 25, 28, 30])
else:
    print("  ⚠️  XAUUSD M1 data not available")

# ═══════════════════════════════════════════════════════════════
# H5: XAG+XAU 欧盘共振n>30积累验证 + 阈值调优
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H5: XAG+XAU 欧盘共振n>30积累验证 + 阈值调优")
print("=" * 70)
print("目标: 欧盘共振(round21发现XAG~93.1%)数据积累+阈值优化")

if xag_m5_raw and xau_m5_raw:
    # ── 欧盘9-11 RSI<20+CB>=2 (已知: XAG WR=93.1% n=29) ──
    xag_eu_cb2 = (
        (xag_m5['session'] == 'europe') &
        (xag_m5.index.hour >= 9) &
        (xag_m5.index.hour < 11) &
        (xag_m5['rsi14'] < 20) &
        (xag_m5['consecutive_bear'] >= 2)
    )
    xau_eu_cb2 = (
        (xau_m5['session'] == 'europe') &
        (xau_m5.index.hour >= 9) &
        (xau_m5.index.hour < 11) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 2)
    )
    both_eu_cb2 = xag_eu_cb2 & xau_eu_cb2
    print(f"\nXAG+XAU 欧盘9-11 共振 (RSI<20+CB>=2): {both_eu_cb2.sum()} signals")
    if both_eu_cb2.sum() >= 5:
        test_condition(xau_m5, both_eu_cb2, "欧盘共振→XAU做多 (CB>=2)",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition(xag_m5, both_eu_cb2, "欧盘共振→XAG做多 (CB>=2)",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # ── 欧盘 CB>=1 共振 (更多信号) ──
    xag_eu_cb1 = (
        (xag_m5['session'] == 'europe') &
        (xag_m5.index.hour >= 9) &
        (xag_m5.index.hour < 11) &
        (xag_m5['rsi14'] < 20) &
        (xag_m5['consecutive_bear'] >= 1)
    )
    xau_eu_cb1 = (
        (xau_m5['session'] == 'europe') &
        (xau_m5.index.hour >= 9) &
        (xau_m5.index.hour < 11) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 1)
    )
    both_eu_cb1 = xag_eu_cb1 & xau_eu_cb1
    print(f"\nXAG+XAU 欧盘9-11 共振 (RSI<20+CB>=1): {both_eu_cb1.sum()} signals")
    if both_eu_cb1.sum() >= 5:
        test_condition(xau_m5, both_eu_cb1, "欧盘共振→XAU (CB>=1)",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition(xag_m5, both_eu_cb1, "欧盘共振→XAG (CB>=1)",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # ── 欧盘 RSI<18+CB>=2 (更严格RSI) ──
    xag_eu_rsi18_cb2 = (
        (xag_m5['session'] == 'europe') &
        (xag_m5.index.hour >= 9) &
        (xag_m5.index.hour < 11) &
        (xag_m5['rsi14'] < 18) &
        (xag_m5['consecutive_bear'] >= 2)
    )
    xau_eu_rsi18_cb2 = (
        (xau_m5['session'] == 'europe') &
        (xau_m5.index.hour >= 9) &
        (xau_m5.index.hour < 11) &
        (xau_m5['rsi14'] < 18) &
        (xau_m5['consecutive_bear'] >= 2)
    )
    both_eu_rsi18_cb2 = xag_eu_rsi18_cb2 & xau_eu_rsi18_cb2
    print(f"\nXAG+XAU 欧盘9-11 共振 (RSI<18+CB>=2): {both_eu_rsi18_cb2.sum()} signals")
    if both_eu_rsi18_cb2.sum() >= 5:
        test_condition(xau_m5, both_eu_rsi18_cb2, "欧盘RSI<18共振→XAU",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition(xag_m5, both_eu_rsi18_cb2, "欧盘RSI<18共振→XAG",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])

print("\n" + "=" * 70)
print("ROUND 22 — 完成")
print(f"Time: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 70)
