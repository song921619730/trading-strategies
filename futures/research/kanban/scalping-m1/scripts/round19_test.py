#!/usr/bin/env python3
"""
Round 19 — 超短线研究循环
Testing priority=1 hypotheses:
1. round19_001: XAUUSD M5 欧盘9-11 RSI<16+CB>=4 窗口微扩展至9:30-11:00
2. round19_002: XAUUSD M5 US 15-16 RSI<18+CB>=2 窗口微调(14:45-15:45 / 15:00-15:45)
3. round19_003: JP225 M5 US 15-16 RSI<16+CB>=2 vs bf_045 对比
4. round19_004: XAUUSD M5 欧盘10-11 RSI深度扫描
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
    
    # Consecutive bear (close < open)
    bear = (df['close'] < df['open']).astype(int)
    df['consecutive_bear'] = bear.groupby((bear == 0).cumsum()).cumsum()
    
    # Consecutive bull (close > open)
    bull = (df['close'] > df['open']).astype(int)
    df['consecutive_bull'] = bull.groupby((bull == 0).cumsum()).cumsum()
    
    return df

def test_condition(df, condition_mask, label, hold_range=None):
    """Test a condition on data and report results across hold periods."""
    entries = df[condition_mask].copy()
    print(f"\n--- {label} ---")
    print(f"Entry signals: {len(entries)}")
    
    if len(entries) < 5:
        print(f"  ⚠️  Too few signals ({len(entries)}), skipping detailed analysis")
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
    
    # Find best hold by combined score (WR * 0.7 + n * 0.3 normalized)
    if results:
        best_hold = max(results, key=lambda h: results[h]['wr'] * 0.7 + min(results[h]['n'] / 200, 1) * 30)
        best = results[best_hold]
        print(f"  Best hold={best_hold}: WR={best['wr']:.1f}% n={best['n']} avg={best['avg_ret']:.3f}%")
        
        # Show top 3 results
        sorted_results = sorted(results.items(), key=lambda x: x[1]['wr'], reverse=True)[:5]
        for hold, r in sorted_results:
            print(f"    hold={hold:3d}: WR={r['wr']:.1f}% n={r['n']} avg={r['avg_ret']:.3f}%")
    
    return entries

# ═══════════════════════════════════════════════════════════════
# DATA SUMMARY
# ═══════════════════════════════════════════════════════════════
print("=" * 70)
print("ROUND 19 — Scalping M1/M5 Research")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 70)

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
# H1: XAUUSD M5 欧盘9-11 RSI<16+CB>=4 窗口微扩展至9:30-11:00
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H1: XAUUSD M5 欧盘9-11 RSI<16+CB>=4 窗口微扩展至9:30-11:00")
print("=" * 70)

xau_m5_raw = load_data("M5", symbols=["XAUUSD"])
xau_m5 = add_session_and_cb(xau_m5_raw["XAUUSD"])
xau_m5 = compute_indicators(xau_m5)

# Baseline: 9-11 RSI<16+CB>=4 (current known: n=38 WR=89.5%)
mask_baseline = (
    (xau_m5['session'] == 'europe') &
    (xau_m5.index.hour >= 9) &
    (xau_m5.index.hour < 11) &
    (xau_m5['rsi14'] < 16) &
    (xau_m5['consecutive_bear'] >= 4)
)
test_condition(xau_m5, mask_baseline, "Baseline: 9-11 RSI<16+CB>=4", 
               hold_range=[38, 40, 41, 42, 44, 46, 48])

# Test 1: 9:30-11:00 RSI<16+CB>=4
mask_930_11 = (
    (xau_m5['session'] == 'europe') &
    ((xau_m5.index.hour == 9) & (xau_m5.index.minute >= 30) |
     (xau_m5.index.hour == 10)) &  # hour 10 only (10:00-10:59)
    (xau_m5['rsi14'] < 16) &
    (xau_m5['consecutive_bear'] >= 4)
)
test_condition(xau_m5, mask_930_11, "9:30-11:00 RSI<16+CB>=4",
               hold_range=[38, 40, 41, 42, 44, 46, 48])

# Test 2: 9:30-10:30 RSI<16+CB>=4 (narrower, more signals at start of session)
mask_930_1030 = (
    (xau_m5['session'] == 'europe') &
    ((xau_m5.index.hour == 9) & (xau_m5.index.minute >= 30) |
     (xau_m5.index.hour == 10) & (xau_m5.index.minute <= 30)) &
    (xau_m5['rsi14'] < 16) &
    (xau_m5['consecutive_bear'] >= 4)
)
test_condition(xau_m5, mask_930_1030, "9:30-10:30 RSI<16+CB>=4",
               hold_range=[38, 40, 41, 42, 44, 46, 48])

# Test 3: 9-10:30 RSI<16+CB>=4 (keep 9-10, extend to 10:30)
mask_9_1030 = (
    (xau_m5['session'] == 'europe') &
    (xau_m5.index.hour >= 9) &
    (xau_m5.index.hour < 10) |
    (xau_m5.index.hour == 10) & (xau_m5.index.minute <= 30) &
    (xau_m5['rsi14'] < 16) &
    (xau_m5['consecutive_bear'] >= 4)
)
# Fix the mask for 9-10:30
mask_9_1030_fixed = (
    (xau_m5['session'] == 'europe') &
    (
        ((xau_m5.index.hour >= 9) & (xau_m5.index.hour < 10)) |
        ((xau_m5.index.hour == 10) & (xau_m5.index.minute <= 30))
    ) &
    (xau_m5['rsi14'] < 16) &
    (xau_m5['consecutive_bear'] >= 4)
)
test_condition(xau_m5, mask_9_1030_fixed, "9-10:30 RSI<16+CB>=4",
               hold_range=[38, 40, 41, 42, 44, 46, 48])

# Cross-check with RSI<18 (wider net)
mask_930_11_rsi18 = (
    (xau_m5['session'] == 'europe') &
    ((xau_m5.index.hour == 9) & (xau_m5.index.minute >= 30) |
     (xau_m5.index.hour == 10)) &
    (xau_m5['rsi14'] < 18) &
    (xau_m5['consecutive_bear'] >= 4)
)
test_condition(xau_m5, mask_930_11_rsi18, "9:30-11:00 RSI<18+CB>=4 (wider RSI)",
               hold_range=[38, 40, 41, 42, 44, 46, 48])

# ═══════════════════════════════════════════════════════════════
# H2: XAUUSD M5 US 15-16 RSI<18+CB>=2 窗口微调
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H2: XAUUSD M5 US 15-16 RSI<18+CB>=2 窗口微调")
print("=" * 70)

# Baseline: 15-16 RSI<18+CB>=2 (current known: n=41 WR=90.2%)
mask_15_16_rsi18 = (
    (xau_m5['session'] == 'us') &
    (xau_m5.index.hour >= 15) &
    (xau_m5.index.hour < 16) &
    (xau_m5['rsi14'] < 18) &
    (xau_m5['consecutive_bear'] >= 2)
)
test_condition(xau_m5, mask_15_16_rsi18, "Baseline: 15-16 RSI<18+CB>=2",
               hold_range=[100, 105, 110, 115, 120, 125, 130])

# Test: 14:45-15:45 RSI<18+CB>=2 (shift 15min earlier)
mask_1445_1545 = (
    (xau_m5['session'] == 'us') &
    ((xau_m5.index.hour == 14) & (xau_m5.index.minute >= 45) |
     (xau_m5.index.hour == 15) & (xau_m5.index.minute <= 45)) &
    (xau_m5['rsi14'] < 18) &
    (xau_m5['consecutive_bear'] >= 2)
)
test_condition(xau_m5, mask_1445_1545, "14:45-15:45 RSI<18+CB>=2",
               hold_range=[100, 105, 110, 115, 120, 125, 130])

# Test: 15:00-15:45 RSI<18+CB>=2 (right-justified)
mask_15_1545 = (
    (xau_m5['session'] == 'us') &
    (xau_m5.index.hour == 15) &
    (xau_m5.index.minute <= 45) &
    (xau_m5['rsi14'] < 18) &
    (xau_m5['consecutive_bear'] >= 2)
)
test_condition(xau_m5, mask_15_1545, "15:00-15:45 RSI<18+CB>=2",
               hold_range=[100, 105, 110, 115, 120, 125, 130])

# Test: 14:45-16:00 RSI<18+CB>=2 (wider window)
mask_1445_16 = (
    (xau_m5['session'] == 'us') &
    ((xau_m5.index.hour == 14) & (xau_m5.index.minute >= 45) |
     (xau_m5.index.hour == 15)) &
    (xau_m5['rsi14'] < 18) &
    (xau_m5['consecutive_bear'] >= 2)
)
test_condition(xau_m5, mask_1445_16, "14:45-16:00 RSI<18+CB>=2",
               hold_range=[100, 105, 110, 115, 120, 125, 130])

# Cross-check: 15-16 RSI<20+CB>=2 (bf_046) with wider hold scan
mask_15_16_rsi20 = (
    (xau_m5['session'] == 'us') &
    (xau_m5.index.hour >= 15) &
    (xau_m5.index.hour < 16) &
    (xau_m5['rsi14'] < 20) &
    (xau_m5['consecutive_bear'] >= 2)
)
test_condition(xau_m5, mask_15_16_rsi20, "bf_046 ref: 15-16 RSI<20+CB>=2",
               hold_range=[100, 105, 110, 115, 120, 125, 130])

# ═══════════════════════════════════════════════════════════════
# H3: JP225 M5 US 15-16 RSI<16+CB>=2 vs bf_045
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H3: JP225 M5 US 15-16 RSI<16+CB>=2 vs bf_045 (15-18 RSI<12+CB>=2)")
print("=" * 70)

jp_m5_raw = load_data("M5", symbols=["JP225"])
jp_m5 = add_session_and_cb(jp_m5_raw["JP225"])
jp_m5 = compute_indicators(jp_m5_raw["JP225"])  # preserves CB columns

jp_m5['session'] = 'asia'
jp_m5.loc[(jp_m5.index.hour >= 8) & (jp_m5.index.hour < 13), 'session'] = 'europe'
jp_m5.loc[(jp_m5.index.hour >= 13) & (jp_m5.index.hour < 22), 'session'] = 'us'
bear = (jp_m5['close'] < jp_m5['open']).astype(int)
jp_m5['consecutive_bear'] = bear.groupby((bear == 0).cumsum()).cumsum()

# Baseline: bf_045 — 15-18 RSI<12+CB>=2
mask_jp_bf045 = (
    (jp_m5['session'] == 'us') &
    (jp_m5.index.hour >= 15) &
    (jp_m5.index.hour < 18) &
    (jp_m5['rsi14'] < 12) &
    (jp_m5['consecutive_bear'] >= 2)
)
test_condition(jp_m5, mask_jp_bf045, "bf_045: 15-18 RSI<12+CB>=2",
               hold_range=[55, 60, 65, 70, 75, 80, 85, 90])

# New: 15-16 RSI<16+CB>=2 (current state says n=51 WR=78.4%)
mask_jp_15_16_rsi16 = (
    (jp_m5['session'] == 'us') &
    (jp_m5.index.hour >= 15) &
    (jp_m5.index.hour < 16) &
    (jp_m5['rsi14'] < 16) &
    (jp_m5['consecutive_bear'] >= 2)
)
test_condition(jp_m5, mask_jp_15_16_rsi16, "15-16 RSI<16+CB>=2",
               hold_range=[55, 60, 65, 70, 75, 80, 85, 90])

# Comparison: 15-16 RSI<14+CB>=2 (tighter RSI)
mask_jp_15_16_rsi14 = (
    (jp_m5['session'] == 'us') &
    (jp_m5.index.hour >= 15) &
    (jp_m5.index.hour < 16) &
    (jp_m5['rsi14'] < 14) &
    (jp_m5['consecutive_bear'] >= 2)
)
test_condition(jp_m5, mask_jp_15_16_rsi14, "15-16 RSI<14+CB>=2",
               hold_range=[55, 60, 65, 70, 75, 80, 85, 90])

# Comparison: 15-16 RSI<12+CB>=2 (tightest)
mask_jp_15_16_rsi12 = (
    (jp_m5['session'] == 'us') &
    (jp_m5.index.hour >= 15) &
    (jp_m5.index.hour < 16) &
    (jp_m5['rsi14'] < 12) &
    (jp_m5['consecutive_bear'] >= 2)
)
test_condition(jp_m5, mask_jp_15_16_rsi12, "15-16 RSI<12+CB>=2",
               hold_range=[55, 60, 65, 70, 75, 80, 85, 90])

# ═══════════════════════════════════════════════════════════════
# H4: XAUUSD M5 欧盘10-11 RSI深度扫描
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H4: XAUUSD M5 欧盘10-11 RSI深度扫描")
print("=" * 70)

# RSI<16+CB>=3
mask_10_11_rsi16_cb3 = (
    (xau_m5['session'] == 'europe') &
    (xau_m5.index.hour == 10) &
    (xau_m5['rsi14'] < 16) &
    (xau_m5['consecutive_bear'] >= 3)
)
test_condition(xau_m5, mask_10_11_rsi16_cb3, "10-11 RSI<16+CB>=3",
               hold_range=[38, 40, 42, 44, 46, 48, 50])

# RSI<15+CB>=2
mask_10_11_rsi15_cb2 = (
    (xau_m5['session'] == 'europe') &
    (xau_m5.index.hour == 10) &
    (xau_m5['rsi14'] < 15) &
    (xau_m5['consecutive_bear'] >= 2)
)
test_condition(xau_m5, mask_10_11_rsi15_cb2, "10-11 RSI<15+CB>=2",
               hold_range=[38, 40, 42, 44, 46, 48, 50])

# RSI<14+CB>=2
mask_10_11_rsi14_cb2 = (
    (xau_m5['session'] == 'europe') &
    (xau_m5.index.hour == 10) &
    (xau_m5['rsi14'] < 14) &
    (xau_m5['consecutive_bear'] >= 2)
)
test_condition(xau_m5, mask_10_11_rsi14_cb2, "10-11 RSI<14+CB>=2",
               hold_range=[38, 40, 42, 44, 46, 48, 50])

# RSI<17+CB>=4 (alternative combo)
mask_10_11_rsi17_cb4 = (
    (xau_m5['session'] == 'europe') &
    (xau_m5.index.hour == 10) &
    (xau_m5['rsi14'] < 17) &
    (xau_m5['consecutive_bear'] >= 4)
)
test_condition(xau_m5, mask_10_11_rsi17_cb4, "10-11 RSI<17+CB>=4",
               hold_range=[38, 40, 42, 44, 46, 48, 50])

# ═══════════════════════════════════════════════════════════════
# BONUS: XAGUSD M5 模式探索 — 欧盘超卖+连阴
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("BONUS: XAGUSD M5 欧盘超卖做多初探")
print("=" * 70)

xag_m5_raw = load_data("M5", symbols=["XAGUSD"])
if xag_m5_raw:
    xag_m5 = add_session_and_cb(xag_m5_raw["XAGUSD"])
    xag_m5 = compute_indicators(xag_m5_raw["XAGUSD"])
    xag_m5['session'] = 'asia'
    xag_m5.loc[(xag_m5.index.hour >= 8) & (xag_m5.index.hour < 13), 'session'] = 'europe'
    xag_m5.loc[(xag_m5.index.hour >= 13) & (xag_m5.index.hour < 22), 'session'] = 'us'
    bear = (xag_m5['close'] < xag_m5['open']).astype(int)
    xag_m5['consecutive_bear'] = bear.groupby((bear == 0).cumsum()).cumsum()
    
    # Test XAGUSD with XAU-derived patterns
    for label, mask_fn in [
        ("9-11 RSI<22+CB>=3", 
         lambda: (xag_m5['session']=='europe') & (xag_m5.index.hour>=9) & (xag_m5.index.hour<11) & (xag_m5['rsi14']<22) & (xag_m5['consecutive_bear']>=3)),
        ("15-16 RSI<20+CB>=2",
         lambda: (xag_m5['session']=='us') & (xag_m5.index.hour>=15) & (xag_m5.index.hour<16) & (xag_m5['rsi14']<20) & (xag_m5['consecutive_bear']>=2)),
        ("US 15-18 RSI<20+CB>=2",
         lambda: (xag_m5['session']=='us') & (xag_m5.index.hour>=15) & (xag_m5.index.hour<18) & (xag_m5['rsi14']<20) & (xag_m5['consecutive_bear']>=2)),
    ]:
        mask = mask_fn()
        test_condition(xag_m5, mask, f"XAGUSD M5 {label}",
                       hold_range=[30, 40, 45, 50, 60, 75, 90, 105, 115, 120])
else:
    print("  ⚠️  XAGUSD M5 data not available")

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ROUND 19 SUMMARY")
print("=" * 70)
print("\nTesting complete. See report for detailed findings.")
