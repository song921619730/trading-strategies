#!/usr/bin/env python3
"""
Round 23 — 超短线研究循环
Testing priority=1 hypotheses:
1. round23_001: XAG+XAU 欧盘RSI<18+CB>=2 共振→XAG 数据积累(n>30验证)
2. round23_002: XAUUSD M1 欧盘9-11 RSI<16+CB>=3 vs 美盘M1 初探
3. round23_003: XAUUSD 欧盘M5 vs 美盘M5 组合策略(同时持有多单)回测
4. round23_004: XAGUSD M5 独有模式(非共振)更深阈值调优
5. round23_005: JP225 欧盘时段超卖模式初探
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
    print(f"  {'条件':<50} {'信号数':<8} {'Hold':<6} {'胜率':<8} {'平均收益':<12}")
    print(f"  {'-'*50} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")
    for row in data:
        print(f"  {row[0]:<50} {row[1]:<8} {row[2]:<6} {row[3]:<8} {row[4]:<12}")

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 70)
print("ROUND 23 — Scalping M1/M5 深入挖掘 + 新领域探索")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=23, testing round23_001~005")
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
# H1: XAG+XAU 欧盘RSI<18+CB>=2 共振→XAG 数据积累(n>30验证)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H1: XAG+XAU 欧盘共振数据积累 — RSI<18+CB>=2 阈值调优")
print("=" * 70)
print("目标: 欧盘共振RSI<18+CB>=2→XAG WR=100% n=22 — 积累至n>30 + 跨周期验证")

xag_m5_raw = load_data("M5", symbols=["XAGUSD"])
xau_m5_raw = load_data("M5", symbols=["XAUUSD"])

if xag_m5_raw and xau_m5_raw:
    xag_m5 = compute_indicators(xag_m5_raw["XAGUSD"])
    xag_m5 = add_session_and_cb(xag_m5)
    xau_m5 = compute_indicators(xau_m5_raw["XAUUSD"])
    xau_m5 = add_session_and_cb(xau_m5)
    
    # ── 欧盘9-11 RSI<18+CB>=2 共振 (round22: XAG WR=100% n=22) ──
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
    print(f"\nXAG+XAU 欧盘9-11 RSI<18+CB>=2 共振: {both_eu_rsi18_cb2.sum()} signals")
    if both_eu_rsi18_cb2.sum() >= 5:
        test_condition_with_periods(xag_m5, both_eu_rsi18_cb2,
                                    "欧盘RSI<18+CB>=2共振→XAG",
                                    hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition_with_periods(xau_m5, both_eu_rsi18_cb2,
                                    "欧盘RSI<18+CB>=2共振→XAU",
                                    hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # ── 欧盘9-11 RSI<18+CB>=1 共振 (更宽松) ──
    xag_eu_rsi18_cb1 = (
        (xag_m5['session'] == 'europe') &
        (xag_m5.index.hour >= 9) &
        (xag_m5.index.hour < 11) &
        (xag_m5['rsi14'] < 18) &
        (xag_m5['consecutive_bear'] >= 1)
    )
    xau_eu_rsi18_cb1 = (
        (xau_m5['session'] == 'europe') &
        (xau_m5.index.hour >= 9) &
        (xau_m5.index.hour < 11) &
        (xau_m5['rsi14'] < 18) &
        (xau_m5['consecutive_bear'] >= 1)
    )
    both_eu_rsi18_cb1 = xag_eu_rsi18_cb1 & xau_eu_rsi18_cb1
    print(f"\nXAG+XAU 欧盘9-11 RSI<18+CB>=1 共振: {both_eu_rsi18_cb1.sum()} signals")
    if both_eu_rsi18_cb1.sum() >= 5:
        test_condition(xag_m5, both_eu_rsi18_cb1, "欧盘RSI<18+CB>=1共振→XAG",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition(xau_m5, both_eu_rsi18_cb1, "欧盘RSI<18+CB>=1共振→XAU",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # ── 欧盘9-11 RSI<16+CB>=2 共振 (更紧RSI) ──
    xag_eu_rsi16_cb2 = (
        (xag_m5['session'] == 'europe') &
        (xag_m5.index.hour >= 9) &
        (xag_m5.index.hour < 11) &
        (xag_m5['rsi14'] < 16) &
        (xag_m5['consecutive_bear'] >= 2)
    )
    xau_eu_rsi16_cb2 = (
        (xau_m5['session'] == 'europe') &
        (xau_m5.index.hour >= 9) &
        (xau_m5.index.hour < 11) &
        (xau_m5['rsi14'] < 16) &
        (xau_m5['consecutive_bear'] >= 2)
    )
    both_eu_rsi16_cb2 = xag_eu_rsi16_cb2 & xau_eu_rsi16_cb2
    print(f"\nXAG+XAU 欧盘9-11 RSI<16+CB>=2 共振: {both_eu_rsi16_cb2.sum()} signals")
    if both_eu_rsi16_cb2.sum() >= 5:
        test_condition(xag_m5, both_eu_rsi16_cb2, "欧盘RSI<16+CB>=2共振→XAG",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition(xau_m5, both_eu_rsi16_cb2, "欧盘RSI<16+CB>=2共振→XAU",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # ── 欧盘8-11 RSI<20+CB>=1 共振 (最大信号量) ──
    xag_eu_wide_cb1 = (
        (xag_m5['session'] == 'europe') &
        (xag_m5.index.hour >= 8) &
        (xag_m5.index.hour < 11) &
        (xag_m5['rsi14'] < 20) &
        (xag_m5['consecutive_bear'] >= 1)
    )
    xau_eu_wide_cb1 = (
        (xau_m5['session'] == 'europe') &
        (xau_m5.index.hour >= 8) &
        (xau_m5.index.hour < 11) &
        (xau_m5['rsi14'] < 20) &
        (xau_m5['consecutive_bear'] >= 1)
    )
    both_eu_wide_cb1 = xag_eu_wide_cb1 & xau_eu_wide_cb1
    print(f"\nXAG+XAU 欧盘8-11 RSI<20+CB>=1 共振: {both_eu_wide_cb1.sum()} signals")
    if both_eu_wide_cb1.sum() >= 5:
        test_condition(xag_m5, both_eu_wide_cb1, "欧盘8-11宽窗共振→XAG",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
        test_condition(xau_m5, both_eu_wide_cb1, "欧盘8-11宽窗共振→XAU",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
else:
    print("  ⚠️  XAGUSD or XAUUSD M5 data not available")

# ═══════════════════════════════════════════════════════════════
# H2: XAUUSD M1 欧盘9-11 RSI<16+CB>=3 vs 美盘M1 初探
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H2: XAUUSD M1 欧盘 vs 美盘 对比验证")
print("=" * 70)
print("目标: M1欧盘最佳模式(WR=87%) vs 美盘M1超卖模式初探")

xau_m1_raw = load_data("M1", symbols=["XAUUSD"])
if xau_m1_raw:
    xau_m1 = compute_indicators(xau_m1_raw["XAUUSD"])
    xau_m1 = add_session_and_cb(xau_m1)
    
    # ── 欧盘9-11 RSI<16+CB>=3 (已知最佳, WR=87%) ──
    mask_m1_eu_9_11 = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 9) &
        (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 16) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xau_m1, mask_m1_eu_9_11,
                                "M1 欧盘9-11 RSI<16+CB>=3",
                                hold_range=[12, 14, 16, 18, 20, 23, 25, 28, 30])
    
    # ── 美盘 15-16 M1初探: RSI<16+CB>=3 ──
    mask_m1_us_15_16 = (
        (xau_m1['session'] == 'us') &
        (xau_m1.index.hour >= 15) &
        (xau_m1.index.hour < 16) &
        (xau_m1['rsi14'] < 16) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xau_m1, mask_m1_us_15_16,
                                "M1 美盘15-16 RSI<16+CB>=3",
                                hold_range=[12, 14, 16, 18, 20, 23, 25, 28, 30])
    
    # ── 美盘 15-16 M1: RSI<20+CB>=2 (更宽松) ──
    mask_m1_us_15_16_loose = (
        (xau_m1['session'] == 'us') &
        (xau_m1.index.hour >= 15) &
        (xau_m1.index.hour < 16) &
        (xau_m1['rsi14'] < 20) &
        (xau_m1['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(xau_m1, mask_m1_us_15_16_loose,
                                "M1 美盘15-16 RSI<20+CB>=2",
                                hold_range=[12, 14, 16, 18, 20, 23, 25, 28, 30])
    
    # ── 美盘 14-17 M1: RSI<16+CB>=3 (宽窗口) ──
    mask_m1_us_14_17 = (
        (xau_m1['session'] == 'us') &
        (xau_m1.index.hour >= 14) &
        (xau_m1.index.hour < 17) &
        (xau_m1['rsi14'] < 16) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xau_m1, mask_m1_us_14_17,
                                "M1 美盘14-17 RSI<16+CB>=3",
                                hold_range=[12, 14, 16, 18, 20, 23, 25, 28, 30])
else:
    print("  ⚠️  XAUUSD M1 data not available")

# ═══════════════════════════════════════════════════════════════
# H3: XAUUSD 欧盘M5 vs 美盘M5 组合策略(同时持有多单)回测
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H3: XAUUSD M5 欧盘 vs 美盘 组合策略(同时持有多单)回测")
print("=" * 70)
print("目标: 模拟同时持有欧盘+美盘多单, 分析组合收益特征")

if xau_m5_raw:
    xau_m5_h3 = compute_indicators(xau_m5_raw["XAUUSD"])
    xau_m5_h3 = add_session_and_cb(xau_m5_h3)
    
    # 欧盘条件: 9-11 RSI<18+CB>=4, hold=42 (已知最佳欧盘)
    mask_eu = (
        (xau_m5_h3['session'] == 'europe') &
        (xau_m5_h3.index.hour >= 9) &
        (xau_m5_h3.index.hour < 11) &
        (xau_m5_h3['rsi14'] < 18) &
        (xau_m5_h3['consecutive_bear'] >= 4)
    )
    
    # 美盘条件: 15-16 RSI<20+CB>=2, hold=115 (已知最佳美盘 bf_046)
    mask_us = (
        (xau_m5_h3['session'] == 'us') &
        (xau_m5_h3.index.hour >= 15) &
        (xau_m5_h3.index.hour < 16) &
        (xau_m5_h3['rsi14'] < 20) &
        (xau_m5_h3['consecutive_bear'] >= 2)
    )
    
    entries_eu = xau_m5_h3[mask_eu].copy()
    entries_us = xau_m5_h3[mask_us].copy()
    
    print(f"\n欧盘信号: {len(entries_eu)}  美盘信号: {len(entries_us)}")
    
    # 计算各信号在各自hold下的收益
    eu_hold = 42
    us_hold = 115
    
    def compute_returns(df, entries, hold):
        rets = []
        for idx, row in entries.iterrows():
            entry_price = row['close']
            pos = df.index.get_loc(idx)
            if pos + hold < len(df):
                exit_price = df.iloc[pos + hold]['close']
                ret = (exit_price - entry_price) / entry_price * 100
                rets.append(ret)
        return np.array(rets)
    
    eu_rets = compute_returns(xau_m5_h3, entries_eu, eu_hold)
    us_rets = compute_returns(xau_m5_h3, entries_us, us_hold)
    
    print(f"\n--- 独立策略表现 ---")
    print(f"  欧盘 (hold={eu_hold}): n={len(eu_rets)} "
          f"WR={np.mean(eu_rets>0)*100:.1f}% avg={np.mean(eu_rets):.3f}%")
    print(f"  美盘 (hold={us_hold}): n={len(us_rets)} "
          f"WR={np.mean(us_rets>0)*100:.1f}% avg={np.mean(us_rets):.3f}%")
    
    # ── 组合策略: 信号重叠日期分析 ──
    # 检查两个策略的信号是否在同一天出现
    eu_dates = set(entries_eu.index.date)
    us_dates = set(entries_us.index.date)
    overlap_dates = eu_dates & us_dates
    
    print(f"\n--- 组合分析 ---")
    print(f"  欧盘独立日期: {len(eu_dates)}  美盘独立日期: {len(us_dates)}")
    print(f"  重叠日期: {len(overlap_dates)}")
    
    # 如果同时持有多单: 组合收益 = 欧盘收益(hold=42) + 美盘收益(hold=115)
    # 但前提是信号在同一天
    combo_rets = []
    for d in overlap_dates:
        eu_rows = entries_eu[entries_eu.index.date == d]
        us_rows = entries_us[entries_us.index.date == d]
        if len(eu_rows) > 0 and len(us_rows) > 0:
            eu_ret = compute_returns(xau_m5_h3, eu_rows, eu_hold)
            us_ret = compute_returns(xau_m5_h3, us_rows, us_hold)
            if len(eu_ret) > 0 and len(us_ret) > 0:
                # 平均每个策略一个信号时的组合收益
                combo_rets.append(eu_ret[0] + us_ret[0])
    
    if len(combo_rets) >= 5:
        combo_arr = np.array(combo_rets)
        print(f"\n  组合策略(同日双信号)表现:")
        print(f"    样本数: {len(combo_arr)}")
        print(f"    组合WR: {np.mean(combo_arr>0)*100:.1f}%")
        print(f"    组合avg: {np.mean(combo_arr):.3f}%")
        print(f"    组合std: {np.std(combo_arr):.3f}%")
        
        # 分解
        eu_only = []
        for d in eu_dates - us_dates:
            rows = entries_eu[entries_eu.index.date == d]
            rets = compute_returns(xau_m5_h3, rows, eu_hold)
            eu_only.extend(rets)
        if len(eu_only) > 0:
            print(f"  欧盘独立日: n={len(eu_only)} WR={np.mean(np.array(eu_only)>0)*100:.1f}%")
        
        us_only = []
        for d in us_dates - eu_dates:
            rows = entries_us[entries_us.index.date == d]
            rets = compute_returns(xau_m5_h3, rows, us_hold)
            us_only.extend(rets)
        if len(us_only) > 0:
            print(f"  美盘独立日: n={len(us_only)} WR={np.mean(np.array(us_only)>0)*100:.1f}%")
    else:
        print(f"  组合样本不足{len(combo_rets)} < 5")
    
    # ── 简单累加: 假设分别独立开单(无重叠限制) ──
    all_rets = np.concatenate([eu_rets, us_rets])
    print(f"\n  累加策略(欧盘+美盘独立开单):")
    print(f"    总信号数: {len(all_rets)}")
    print(f"    整体WR: {np.mean(all_rets>0)*100:.1f}%")
    print(f"    整体avg: {np.mean(all_rets):.3f}%")

# ═══════════════════════════════════════════════════════════════
# H4: XAGUSD M5 独有模式(非共振)更深阈值调优
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H4: XAGUSD M5 独有模式(非共振)更深阈值调优")
print("=" * 70)
print("目标: 挖掘XAGUSD独立(非共振)超卖模式 — RSI<16+CB>=4等深度阈值")

if xag_m5_raw:
    xag_m5_h4 = compute_indicators(xag_m5_raw["XAGUSD"])
    xag_m5_h4 = add_session_and_cb(xag_m5_h4)
    
    # ── 美盘 15-16 各种阈值对比 ──
    xag_configs = [
        ("US 15-16 RSI<18+CB>=3 (当前最佳)", 
         (xag_m5_h4['session']=='us') & (xag_m5_h4.index.hour>=15) & (xag_m5_h4.index.hour<16) &
         (xag_m5_h4['rsi14']<18) & (xag_m5_h4['consecutive_bear']>=3)),
        ("US 15-16 RSI<16+CB>=4 (更紧)", 
         (xag_m5_h4['session']=='us') & (xag_m5_h4.index.hour>=15) & (xag_m5_h4.index.hour<16) &
         (xag_m5_h4['rsi14']<16) & (xag_m5_h4['consecutive_bear']>=4)),
        ("US 15-16 RSI<14+CB>=3 (极端超卖)", 
         (xag_m5_h4['session']=='us') & (xag_m5_h4.index.hour>=15) & (xag_m5_h4.index.hour<16) &
         (xag_m5_h4['rsi14']<14) & (xag_m5_h4['consecutive_bear']>=3)),
        ("US 15-16 RSI<20+CB>=4 (高CB)", 
         (xag_m5_h4['session']=='us') & (xag_m5_h4.index.hour>=15) & (xag_m5_h4.index.hour<16) &
         (xag_m5_h4['rsi14']<20) & (xag_m5_h4['consecutive_bear']>=4)),
        ("US 15-16 RSI<16+CB>=5 (最严格)", 
         (xag_m5_h4['session']=='us') & (xag_m5_h4.index.hour>=15) & (xag_m5_h4.index.hour<16) &
         (xag_m5_h4['rsi14']<16) & (xag_m5_h4['consecutive_bear']>=5)),
    ]
    
    print(f"\n--- XAGUSD M5 美盘15-16 阈值网格 ---")
    xag_comp_data = []
    for label, mask in xag_configs:
        entries = xag_m5_h4[mask]
        print(f"  {label}: {len(entries)} signals", end="")
        if len(entries) < 3:
            print(" ⚠️ 太少")
            continue
        # Quick test at hold=105 (已知最佳)
        hits = 0
        total_pnl = 0.0
        count = 0
        for idx, row in entries.iterrows():
            entry_price = row['close']
            pos = xag_m5_h4.index.get_loc(idx)
            for hold in [95, 100, 105, 110, 115, 120]:
                if pos + hold < len(xag_m5_h4):
                    exit_price = xag_m5_h4.iloc[pos + hold]['close']
                    pnl = (exit_price - entry_price) / entry_price * 100
                    total_pnl += pnl
                    count += 1
                    if pnl > 0:
                        hits += 1
                    break  # only test one hold per entry
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            xag_comp_data.append((label, str(count), "105", f"{wr:.1f}%", f"{avg_ret:.3f}%"))
            print(f"  WR={wr:.1f}% avg={avg_ret:.3f}%")
    
    if xag_comp_data:
        print_compact_comparison("XAGUSD 美盘阈值对比 (hold=105)", xag_comp_data)
    
    # ── 欧盘独有模式(非共振) ──
    print(f"\n--- XAGUSD M5 欧盘9-11 独有阈值 ---")
    xag_eu_configs = [
        ("EU 9-11 RSI<18+CB>=3", 
         (xag_m5_h4['session']=='europe') & (xag_m5_h4.index.hour>=9) & (xag_m5_h4.index.hour<11) &
         (xag_m5_h4['rsi14']<18) & (xag_m5_h4['consecutive_bear']>=3)),
        ("EU 9-11 RSI<16+CB>=4", 
         (xag_m5_h4['session']=='europe') & (xag_m5_h4.index.hour>=9) & (xag_m5_h4.index.hour<11) &
         (xag_m5_h4['rsi14']<16) & (xag_m5_h4['consecutive_bear']>=4)),
        ("EU 9-11 RSI<14+CB>=3", 
         (xag_m5_h4['session']=='europe') & (xag_m5_h4.index.hour>=9) & (xag_m5_h4.index.hour<11) &
         (xag_m5_h4['rsi14']<14) & (xag_m5_h4['consecutive_bear']>=3)),
    ]
    
    for label, mask in xag_eu_configs:
        entries = xag_m5_h4[mask]
        print(f"  {label}: {len(entries)} signals", end="")
        if len(entries) < 5:
            print(" ⚠️ 太少")
            continue
        test_condition(xag_m5_h4, mask, f"{label}",
                      hold_range=[95, 100, 105, 110, 115, 120, 125, 130])

# ═══════════════════════════════════════════════════════════════
# H5: JP225 欧盘时段超卖模式初探
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H5: JP225 欧盘时段超卖模式初探")
print("=" * 70)
print("目标: 探索JP225在欧盘时段的超卖反转模式(目前仅美盘有85.4%模式)")

jp_m5_raw = load_data("M5", symbols=["JP225"])
if jp_m5_raw:
    jp_m5 = compute_indicators(jp_m5_raw["JP225"])
    jp_m5 = add_session_and_cb(jp_m5)
    
    # ── 欧盘 8-11 超卖模式 ──
    jp_eu_configs = [
        ("EU 8-11 RSI<14+CB>=2 (同美盘条件)", 
         (jp_m5['session']=='europe') & (jp_m5.index.hour>=8) & (jp_m5.index.hour<11) &
         (jp_m5['rsi14']<14) & (jp_m5['consecutive_bear']>=2)),
        ("EU 8-11 RSI<16+CB>=2 (宽松)    ",
         (jp_m5['session']=='europe') & (jp_m5.index.hour>=8) & (jp_m5.index.hour<11) &
         (jp_m5['rsi14']<16) & (jp_m5['consecutive_bear']>=2)),
        ("EU 8-11 RSI<14+CB>=1 (最低CB)  ",
         (jp_m5['session']=='europe') & (jp_m5.index.hour>=8) & (jp_m5.index.hour<11) &
         (jp_m5['rsi14']<14) & (jp_m5['consecutive_bear']>=1)),
        ("EU 9-11 RSI<14+CB>=2 (窄窗口)  ",
         (jp_m5['session']=='europe') & (jp_m5.index.hour>=9) & (jp_m5.index.hour<11) &
         (jp_m5['rsi14']<14) & (jp_m5['consecutive_bear']>=2)),
    ]
    
    print(f"\n--- JP225 M5 欧盘超卖模式 ---")
    jp_comp_data = []
    for label, mask in jp_eu_configs:
        entries = jp_m5[mask]
        print(f"  {label}: {len(entries)} signals", end="")
        if len(entries) < 5:
            print(" ⚠️ 太少")
            continue
        # Quick test at hold=55 (美盘最佳)
        hits = 0
        total_pnl = 0.0
        count = 0
        for idx, row in entries.iterrows():
            entry_price = row['close']
            pos = jp_m5.index.get_loc(idx)
            for hold in [45, 50, 55, 60, 65, 70]:
                if pos + hold < len(jp_m5):
                    exit_price = jp_m5.iloc[pos + hold]['close']
                    pnl = (exit_price - entry_price) / entry_price * 100
                    total_pnl += pnl
                    count += 1
                    if pnl > 0:
                        hits += 1
                    break
        if count > 0:
            wr = hits / count * 100
            avg_ret = total_pnl / count
            jp_comp_data.append((label, str(count), "55", f"{wr:.1f}%", f"{avg_ret:.3f}%"))
            print(f"  WR={wr:.1f}% avg={avg_ret:.3f}%")
    
    if jp_comp_data:
        print_compact_comparison("JP225 欧盘超卖模式对比 (hold=55)", jp_comp_data)
    
    # ── 最佳欧盘模式跨周期验证 ──
    best_eu_mask = (
        (jp_m5['session']=='europe') & (jp_m5.index.hour>=8) & (jp_m5.index.hour<11) &
        (jp_m5['rsi14']<14) & (jp_m5['consecutive_bear']>=2)
    )
    if best_eu_mask.sum() >= 10:
        test_condition_with_periods(jp_m5, best_eu_mask,
                                    "JP225 欧盘8-11 RSI<14+CB>=2 (最佳候选)",
                                    hold_range=[45, 50, 55, 60, 65, 70, 75, 80])
    
    # ── 美盘 vs 欧盘 对比总结 ──
    print(f"\n--- JP225 美盘 vs 欧盘 最终对比 ---")
    mask_us_jp = (
        (jp_m5['session']=='us') & (jp_m5.index.hour>=15) & (jp_m5.index.hour<16) &
        (jp_m5['rsi14']<14) & (jp_m5['consecutive_bear']>=2)
    )
    entries_us_jp = jp_m5[mask_us_jp]
    entries_eu_jp = jp_m5[best_eu_mask]
    print(f"  美盘: {len(entries_us_jp)} signals | 欧盘: {len(entries_eu_jp)} signals")

print("\n" + "=" * 70)
print("ROUND 23 — 完成")
print(f"Time: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 70)
