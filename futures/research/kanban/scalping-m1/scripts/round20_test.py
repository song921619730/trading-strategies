#!/usr/bin/env python3
"""
Round 20 — 超短线研究循环 (Scalping Edition)
Testing priority=1 hypotheses:
1. round20_001: XAGUSD M5 US 15-16 RSI<20+CB>=2 (bf_053) 跨数据周期稳定性验证
2. round20_002: XAGUSD M5 US 15-16 RSI阈值精化 (RSI<18/16/14 + CB>=2/3)
3. round20_003: XAGUSD + XAUUSD 15-16 多品种共振 (low priority extension)
4. round20_005: XAUUSD M5 US 14:45-15:45 RSI<20+CB>=2 宽窗口版
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np

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
    
    # Split data into 3 periods
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
print("ROUND 20 — XAGUSD 跨周期稳定性验证 + XAU 窗口微调")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=20, testing round20_001/002/005")
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
# H1: XAGUSD M5 US 15-16 RSI<20+CB>=2 (bf_053) 跨周期稳定性
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H1: XAGUSD M5 US 15-16 RSI<20+CB>=2 (bf_053) 跨周期稳定性验证")
print("=" * 70)

xag_m5_raw = load_data("M5", symbols=["XAGUSD"])
if xag_m5_raw:
    xag_m5 = compute_indicators(xag_m5_raw["XAGUSD"])
    xag_m5 = add_session_and_cb(xag_m5)
    
    mask_bf053 = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 15) &
        (xag_m5.index.hour < 16) &
        (xag_m5['rsi14'] < 20) &
        (xag_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(xag_m5, mask_bf053, "bf_053: XAGUSD US 15-16 RSI<20+CB>=2",
                               hold_range=[100, 105, 110, 115, 120, 125, 130])
else:
    print("  ⚠️  XAGUSD M5 data not available")

# ═══════════════════════════════════════════════════════════════
# H2: XAGUSD M5 US 15-16 RSI阈值精化
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H2: XAGUSD M5 US 15-16 RSI阈值精化 (RSI<18/16/14 + CB>=2/3)")
print("=" * 70)

if xag_m5_raw:
    for rsi_threshold in [18, 16, 14]:
        for cb_min in [2, 3]:
            mask = (
                (xag_m5['session'] == 'us') &
                (xag_m5.index.hour >= 15) &
                (xag_m5.index.hour < 16) &
                (xag_m5['rsi14'] < rsi_threshold) &
                (xag_m5['consecutive_bear'] >= cb_min)
            )
            label = f"XAGUSD US 15-16 RSI<{rsi_threshold}+CB>={cb_min}"
            test_condition(xag_m5, mask, label,
                          hold_range=[100, 105, 110, 115, 120, 125, 130])

# ═══════════════════════════════════════════════════════════════
# H3: XAUUSD M5 US 14:45-15:45 RSI<20+CB>=2 宽窗口版
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H3: XAUUSD M5 US 14:45-15:45 RSI<20+CB>=2 (round20_005)")
print("=" * 70)

xau_m5_raw = load_data("M5", symbols=["XAUUSD"])
if xau_m5_raw:
    xau_m5 = compute_indicators(xau_m5_raw["XAUUSD"])
    xau_m5 = add_session_and_cb(xau_m5)
    
    # bf_046 reference: 15-16 RSI<20+CB>=2
    mask_046 = (
        (xau_m5['session'] == 'us') &
        (xau_m5.index.hour >= 15) &
        (xau_m5.index.hour < 16) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(xau_m5, mask_046, "bf_046 ref: XAU 15-16 RSI<20+CB>=2",
                               hold_range=[100, 105, 110, 115, 120, 125, 130])
    
    # 14:45-15:45 RSI<20+CB>=2
    mask_1445_1545 = (
        (xau_m5['session'] == 'us') &
        (((xau_m5.index.hour == 14) & (xau_m5.index.minute >= 45)) |
         (xau_m5.index.hour == 15)) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(xau_m5, mask_1445_1545, "14:45-15:45 RSI<20+CB>=2",
                               hold_range=[100, 105, 110, 115, 120, 125, 130])
    
    # RSI<22+CB>=2 (best WR/n balance from round18)
    mask_rsi22 = (
        (xau_m5['session'] == 'us') &
        (xau_m5.index.hour >= 15) &
        (xau_m5.index.hour < 16) &
        (xau_m5['rsi14'] < 22) &
        (xau_m5['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(xau_m5, mask_rsi22, "15-16 RSI<22+CB>=2 (放宽版bf_046)",
                               hold_range=[100, 105, 110, 115, 120, 125, 130])

# ═══════════════════════════════════════════════════════════════
# H4: XAGUSD M1 US 15-16 RSI<20+CB>=2 M1迁移 (round20_004)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H4: XAGUSD M1 US 15-16 RSI<20+CB>=2 M1迁移 (round20_004)")
print("=" * 70)

xag_m1_raw = load_data("M1", symbols=["XAGUSD"])
if xag_m1_raw:
    xag_m1 = compute_indicators(xag_m1_raw["XAGUSD"])
    xag_m1 = add_session_and_cb(xag_m1)
    
    mask_m1 = (
        (xag_m1['session'] == 'us') &
        (xag_m1.index.hour >= 15) &
        (xag_m1.index.hour < 16) &
        (xag_m1['rsi14'] < 20) &
        (xag_m1['consecutive_bear'] >= 2)
    )
    test_condition(xag_m1, mask_m1, "XAGUSD M1 US 15-16 RSI<20+CB>=2",
                  hold_range=[30, 45, 60, 75, 90, 105, 120, 180, 240])
else:
    print("  ⚠️  XAGUSD M1 data not available")

# ═══════════════════════════════════════════════════════════════
# BONUS: XAGUSD + XAUUSD 共振
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("BONUS: XAGUSD + XAUUSD US 15-16 共振")
print("=" * 70)

if xag_m5_raw and xau_m5_raw:
    # Create signal series
    xag_signal = (
        (xag_m5['session'] == 'us') &
        (xag_m5.index.hour >= 15) &
        (xag_m5.index.hour < 16) &
        (xag_m5['rsi14'] < 20) &
        (xag_m5['consecutive_bear'] >= 2)
    )
    xau_signal = (
        (xau_m5['session'] == 'us') &
        (xau_m5.index.hour >= 15) &
        (xau_m5.index.hour < 16) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 2)
    )
    
    # Both triggered on same M5 candle
    both_signal = xag_signal & xau_signal
    test_condition(xau_m5, both_signal, "XAG+XAU 同bar共振 → XAU做多",
                  hold_range=[100, 105, 110, 115, 120, 125, 130])
    
    test_condition(xag_m5, both_signal, "XAG+XAU 同bar共振 → XAG做多",
                  hold_range=[100, 105, 110, 115, 120, 125, 130])

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ROUND 20 SUMMARY")
print("=" * 70)
print("\nTesting complete. See report for detailed findings.")
