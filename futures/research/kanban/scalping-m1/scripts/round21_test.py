#!/usr/bin/env python3
"""
Round 21 — 超短线研究循环
Testing priority=1 hypotheses:
1. round21_001: XAGUSD M5 RSI<18+CB>=3 跨周期稳定性深入验证
2. round21_002: XAG+XAU 共振信号扩展 (CB>=1 及阈值调优)
3. round21_003: XAUUSD M1 欧盘 bf_041 深度验证 + 跨周期稳定性
4. round21_004: JP225 M5 US 15-16 RSI<14+CB>=2 vs RSI<16+CB>=2 对比
5. round21_005: XAUUSD M5 欧盘8-11 RSI<16+CB>=4 跨周期稳定性(H4迁移)
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
    n = len(dates)
    split1 = dates[int(n * 0.33)]
    split2 = dates[int(n * 0.67)]
    
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

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 70)
print("ROUND 21 — Scalping M1/M5 交叉验证 + 共振信号扩展")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=21, testing round21_001~005")
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
# H1: XAGUSD M5 RSI<18+CB>=3 跨周期稳定性深入验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H1: XAGUSD M5 RSI<18+CB>=3 跨周期稳定性深入验证")
print("=" * 70)

xag_m5_raw = load_data("M5", symbols=["XAGUSD"])
if xag_m5_raw:
    xag_m5 = compute_indicators(xag_m5_raw["XAGUSD"])
    xag_m5 = add_session_and_cb(xag_m5)
    
    # RSI<18+CB>=3 (round20 best)
    mask_rsi18_cb3 = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 15) &
        (xag_m5.index.hour < 16) &
        (xag_m5['rsi14'] < 18) &
        (xag_m5['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xag_m5, mask_rsi18_cb3, "XAGUSD US 15-16 RSI<18+CB>=3",
                                hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # Compare: RSI<18+CB>=2 (more signals)
    mask_rsi18_cb2 = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 15) &
        (xag_m5.index.hour < 16) &
        (xag_m5['rsi14'] < 18) &
        (xag_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(xag_m5, mask_rsi18_cb2, "XAGUSD US 15-16 RSI<18+CB>=2",
                                hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # Compare: RSI<16+CB>=3 (tighter RSI)
    mask_rsi16_cb3 = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 15) &
        (xag_m5.index.hour < 16) &
        (xag_m5['rsi14'] < 16) &
        (xag_m5['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xag_m5, mask_rsi16_cb3, "XAGUSD US 15-16 RSI<16+CB>=3",
                                hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
else:
    print("  ⚠️  XAGUSD M5 data not available")

# ═══════════════════════════════════════════════════════════════
# H2: XAG+XAU 共振信号扩展
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H2: XAG+XAU 共振信号扩展 (CB阈值降低 + 窗口扩展)")
print("=" * 70)

xau_m5_raw = load_data("M5", symbols=["XAUUSD"])
if xag_m5_raw and xau_m5_raw:
    xau_m5 = compute_indicators(xau_m5_raw["XAUUSD"])
    xau_m5 = add_session_and_cb(xau_m5)
    
    # Define signal conditions
    xag_signal_cb2 = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 15) &
        (xag_m5.index.hour < 16) &
        (xag_m5['rsi14'] < 20) &
        (xag_m5['consecutive_bear'] >= 2)
    )
    xau_signal_cb2 = (
        (xau_m5['session'] == 'us') &
        (xau_m5.index.hour >= 15) &
        (xau_m5.index.hour < 16) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 2)
    )
    
    # Test 1: CB>=2 resonance (original, n=16)
    both_cb2 = xag_signal_cb2 & xau_signal_cb2
    print(f"\nXAG+XAU 同bar共振 (CB>=2): {both_cb2.sum()} signals")
    if both_cb2.sum() >= 5:
        test_condition(xau_m5, both_cb2, "共振→XAU做多 (CB>=2)",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition(xag_m5, both_cb2, "共振→XAG做多 (CB>=2)",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # Test 2: CB>=1 resonance (less restrictive, more signals)
    xag_signal_cb1 = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 15) &
        (xag_m5.index.hour < 16) &
        (xag_m5['rsi14'] < 20) &
        (xag_m5['consecutive_bear'] >= 1)
    )
    xau_signal_cb1 = (
        (xau_m5['session'] == 'us') &
        (xau_m5.index.hour >= 15) &
        (xau_m5.index.hour < 16) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 1)
    )
    both_cb1 = xag_signal_cb1 & xau_signal_cb1
    print(f"\nXAG+XAU 同bar共振 (CB>=1): {both_cb1.sum()} signals")
    if both_cb1.sum() >= 5:
        test_condition(xau_m5, both_cb1, "共振→XAU做多 (CB>=1)",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition(xag_m5, both_cb1, "共振→XAG做多 (CB>=1)",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # Test 3: RSI<18 resonance with CB>=1 (even tighter RSI)
    xag_signal_rsi18_cb1 = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 15) &
        (xag_m5.index.hour < 16) &
        (xag_m5['rsi14'] < 18) &
        (xag_m5['consecutive_bear'] >= 1)
    )
    xau_signal_rsi18_cb1 = (
        (xau_m5['session'] == 'us') &
        (xau_m5.index.hour >= 15) &
        (xau_m5.index.hour < 16) &
        (xau_m5['rsi14'] < 18) &
        (xau_m5['consecutive_bear'] >= 1)
    )
    both_rsi18_cb1 = xag_signal_rsi18_cb1 & xau_signal_rsi18_cb1
    print(f"\nXAG+XAU 同bar共振 (RSI<18+CB>=1): {both_rsi18_cb1.sum()} signals")
    if both_rsi18_cb1.sum() >= 5:
        test_condition(xau_m5, both_rsi18_cb1, "共振→XAU做多 (RSI<18+CB>=1)",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition(xag_m5, both_rsi18_cb1, "共振→XAG做多 (RSI<18+CB>=1)",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # Test 4: XAU+XAG 欧盘共振 (9-11)
    xag_eu = (
        (xag_m5['session'] == 'europe') &
        (xag_m5.index.hour >= 9) &
        (xag_m5.index.hour < 11) &
        (xag_m5['rsi14'] < 20) &
        (xag_m5['consecutive_bear'] >= 2)
    )
    xau_eu = (
        (xau_m5['session'] == 'europe') &
        (xau_m5.index.hour >= 9) &
        (xau_m5.index.hour < 11) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 2)
    )
    both_eu = xag_eu & xau_eu
    print(f"\nXAG+XAU 欧盘9-11 共振 (RSI<20+CB>=2): {both_eu.sum()} signals")
    if both_eu.sum() >= 5:
        test_condition(xau_m5, both_eu, "欧盘共振→XAU做多",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition(xag_m5, both_eu, "欧盘共振→XAG做多",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])

# ═══════════════════════════════════════════════════════════════
# H3: XAUUSD M1 欧盘 bf_041 深度验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H3: XAUUSD M1 欧盘 bf_041 (8-11 RSI<18+CB>=3) 深度验证")
print("=" * 70)

xau_m1_raw = load_data("M1", symbols=["XAUUSD"])
if xau_m1_raw:
    xau_m1 = compute_indicators(xau_m1_raw["XAUUSD"])
    xau_m1 = add_session_and_cb(xau_m1)
    
    # bf_041: 8-11 RSI<18+CB>=3
    mask_bf041 = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 8) &
        (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 18) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    # M1 hold periods are shorter (in minutes)
    test_condition_with_periods(xau_m1, mask_bf041, "bf_041: XAU M1 欧盘8-11 RSI<18+CB>=3",
                                hold_range=[10, 12, 14, 16, 18, 20, 23, 25, 28, 30])
    
    # Variant: 9-11 RSI<18+CB>=3 (bf_048 — tighter window)
    mask_bf048 = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 9) &
        (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 18) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xau_m1, mask_bf048, "bf_048: XAU M1 欧盘9-11 RSI<18+CB>=3",
                                hold_range=[10, 12, 14, 16, 18, 20, 23, 25, 28, 30])
    
    # Variant: 8-11 RSI<16+CB>=3 (tighter RSI)
    mask_rsi16_cb3 = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 8) &
        (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 16) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xau_m1, mask_rsi16_cb3, "XAU M1 欧盘8-11 RSI<16+CB>=3",
                                hold_range=[10, 12, 14, 16, 18, 20, 23, 25, 28, 30])
    
    # Variant: 8-11 RSI<18+CB>=4 (higher CB demand)
    mask_rsi18_cb4 = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 8) &
        (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 18) &
        (xau_m1['consecutive_bear'] >= 4)
    )
    test_condition_with_periods(xau_m1, mask_rsi18_cb4, "XAU M1 欧盘8-11 RSI<18+CB>=4",
                                hold_range=[10, 12, 14, 16, 18, 20, 23, 25, 28, 30])
else:
    print("  ⚠️  XAUUSD M1 data not available")

# ═══════════════════════════════════════════════════════════════
# H4: JP225 M5 US 15-16 RSI阈值对比 + 跨周期
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H4: JP225 M5 US 15-16 RSI阈值对比 + 跨周期稳定性")
print("=" * 70)

jp_m5_raw = load_data("M5", symbols=["JP225"])
if jp_m5_raw:
    jp_m5 = compute_indicators(jp_m5_raw["JP225"])
    jp_m5 = add_session_and_cb(jp_m5)
    
    # RSI<16+CB>=2 (from round19: WR~78.4% n=51)
    mask_jp_rsi16_cb2 = (
        (jp_m5['session'] == 'us') &
        (jp_m5.index.hour >= 15) &
        (jp_m5.index.hour < 16) &
        (jp_m5['rsi14'] < 16) &
        (jp_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(jp_m5, mask_jp_rsi16_cb2, "JP225 US 15-16 RSI<16+CB>=2",
                                hold_range=[55, 60, 65, 70, 75, 80, 85, 90])
    
    # RSI<14+CB>=2 (tighter)
    mask_jp_rsi14_cb2 = (
        (jp_m5['session'] == 'us') &
        (jp_m5.index.hour >= 15) &
        (jp_m5.index.hour < 16) &
        (jp_m5['rsi14'] < 14) &
        (jp_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(jp_m5, mask_jp_rsi14_cb2, "JP225 US 15-16 RSI<14+CB>=2",
                                hold_range=[55, 60, 65, 70, 75, 80, 85, 90])
    
    # RSI<18+CB>=2 (more signals)
    mask_jp_rsi18_cb2 = (
        (jp_m5['session'] == 'us') &
        (jp_m5.index.hour >= 15) &
        (jp_m5.index.hour < 16) &
        (jp_m5['rsi14'] < 18) &
        (jp_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(jp_m5, mask_jp_rsi18_cb2, "JP225 US 15-16 RSI<18+CB>=2",
                                hold_range=[55, 60, 65, 70, 75, 80, 85, 90])
    
    # bf_045: 15-18 RSI<12+CB>=2 (wider window)
    mask_jp_bf045 = (
        (jp_m5['session'] == 'us') &
        (jp_m5.index.hour >= 15) &
        (jp_m5.index.hour < 18) &
        (jp_m5['rsi14'] < 12) &
        (jp_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(jp_m5, mask_jp_bf045, "bf_045: JP225 US 15-18 RSI<12+CB>=2",
                                hold_range=[55, 60, 65, 70, 75, 80, 85, 90])
else:
    print("  ⚠️  JP225 M5 data not available")

# ═══════════════════════════════════════════════════════════════
# H5: XAUUSD M5 欧盘8-11 RSI<16+CB>=4 跨周期验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H5: XAUUSD M5 欧盘8-11 RSI<16+CB>=4 跨周期稳定性")
print("=" * 70)

if xau_m5_raw:
    # 8-11 RSI<16+CB>=4
    mask_eu_rsi16_cb4 = (
        (xau_m5['session'] == 'europe') &
        (xau_m5.index.hour >= 8) &
        (xau_m5.index.hour < 11) &
        (xau_m5['rsi14'] < 16) &
        (xau_m5['consecutive_bear'] >= 4)
    )
    test_condition_with_periods(xau_m5, mask_eu_rsi16_cb4, "XAU M5 欧盘8-11 RSI<16+CB>=4",
                                hold_range=[35, 38, 40, 42, 44, 46, 48, 50])
    
    # 9-11 RSI<16+CB>=4 (known high WR from round19)
    mask_9_11_rsi16_cb4 = (
        (xau_m5['session'] == 'europe') &
        (xau_m5.index.hour >= 9) &
        (xau_m5.index.hour < 11) &
        (xau_m5['rsi14'] < 16) &
        (xau_m5['consecutive_bear'] >= 4)
    )
    test_condition_with_periods(xau_m5, mask_9_11_rsi16_cb4, "XAU M5 欧盘9-11 RSI<16+CB>=4",
                                hold_range=[35, 38, 40, 42, 44, 46, 48, 50])
    
    # 9-11 RSI<18+CB>=4 (wider RSI net)
    mask_9_11_rsi18_cb4 = (
        (xau_m5['session'] == 'europe') &
        (xau_m5.index.hour >= 9) &
        (xau_m5.index.hour < 11) &
        (xau_m5['rsi14'] < 18) &
        (xau_m5['consecutive_bear'] >= 4)
    )
    test_condition_with_periods(xau_m5, mask_9_11_rsi18_cb4, "XAU M5 欧盘9-11 RSI<18+CB>=4",
                                hold_range=[35, 38, 40, 42, 44, 46, 48, 50])

# ═══════════════════════════════════════════════════════════════
# BONUS: US500 M5 US 15-16 超卖初探
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("BONUS: US500 M5 US 15-16 超卖做多初探")
print("=" * 70)

us500_m5_raw = load_data("M5", symbols=["US500"])
if us500_m5_raw:
    us500_m5 = compute_indicators(us500_m5_raw["US500"])
    us500_m5 = add_session_and_cb(us500_m5)
    
    mask_us500 = (
        (us500_m5['session'] == 'us') &
        (us500_m5.index.hour >= 15) &
        (us500_m5.index.hour < 16) &
        (us500_m5['rsi14'] < 20) &
        (us500_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(us500_m5, mask_us500, "US500 US 15-16 RSI<20+CB>=2",
                                hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # US30 M5 US 15-16 
    us30_m5_raw = load_data("M5", symbols=["US30"])
    if us30_m5_raw:
        us30_m5 = compute_indicators(us30_m5_raw["US30"])
        us30_m5 = add_session_and_cb(us30_m5)
        mask_us30 = (
            (us30_m5['session'] == 'us') &
            (us30_m5.index.hour >= 15) &
            (us30_m5.index.hour < 16) &
            (us30_m5['rsi14'] < 20) &
            (us30_m5['consecutive_bear'] >= 2)
        )
        test_condition_with_periods(us30_m5, mask_us30, "US30 US 15-16 RSI<20+CB>=2",
                                    hold_range=[95, 100, 105, 110, 115, 120, 125, 130])

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ROUND 21 SUMMARY")
print("=" * 70)
print("\nTesting complete. See report for detailed findings.")
