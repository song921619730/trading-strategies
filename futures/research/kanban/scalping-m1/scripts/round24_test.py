#!/usr/bin/env python3
"""
Round 24 — 超短线研究循环
Testing priority=1 hypotheses (from round23 next_actions):
1. round24_001: XAGUSD 欧盘RSI<14+CB>=3 (新发现WR=86.5% n=37) 跨周期稳定性验证
2. round24_002: XAGUSD 美盘RSI<14+CB>=3 (新荐87.5%) vs 旧RSI<18+CB>=3 (80.6%) 跨周期对比
3. round24_003: XAUUSD 双枪策略(欧盘+美盘组合)实时模拟盘跟踪
4. round24_004: JPY / EURUSD / GBPUSD 等非贵金属品种超卖模式初探
5. round24_005: XAGUSD 美盘RSI<16+CB>=5 (90.9% n=11) 数据积累
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

def get_stats(df, mask, hold):
    """Quick stats for a condition at a specific hold period."""
    entries = df[mask]
    hits, total, count = 0, 0.0, 0
    for idx, row in entries.iterrows():
        pos = df.index.get_loc(idx)
        if pos + hold < len(df):
            pnl = (df.iloc[pos + hold]['close'] - row['close']) / row['close'] * 100
            total += pnl
            count += 1
            if pnl > 0: hits += 1
    return count, hits/count*100 if count else 0, total/count if count else 0

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
print("ROUND 24 — Scalping M1/M5 深入验证 + 新领域探索")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=24, testing round24_001~005")
print("=" * 70)

# ── Load data ──
for tf in ["M5", "M1"]:
    print(f"\n--- {tf} Data Summary ---")
    data = load_data(tf, symbols=["XAUUSD", "XAGUSD", "JP225", "US500", "US30", "EURUSD", "GBPUSD"])
    for sym, df in data.items():
        df2 = compute_indicators(df)
        rsi_val = df2['rsi14'].iloc[-1]
        atr_val = df2['atr14_pct'].iloc[-1]
        close_val = df2['close'].iloc[-1]
        print(f"  {sym:8s} {tf}: {len(df2):>8} rows  [{df2.index[0].date()} → {df2.index[-1].date()}]  "
              f"Close={close_val:.1f}  RSI={rsi_val:.1f}  ATR%={atr_val:.3f}%")

# ═══════════════════════════════════════════════════════════════
# H1: XAGUSD 欧盘RSI<14+CB>=3 跨周期稳定性验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H1: XAGUSD M5 欧盘RSI<14+CB>=3 跨周期稳定性验证")
print("=" * 70)
print("目标: round23发现XAG欧盘独有模式RSI<14+CB>=3 WR=86.5% n=37 — 跨周期P1/P2/P3稳定性验证")

xag_m5_raw = load_data("M5", symbols=["XAGUSD"])
if xag_m5_raw:
    xag_m5 = compute_indicators(xag_m5_raw["XAGUSD"])
    xag_m5 = add_session_and_cb(xag_m5)
    
    # 欧盘9-11 RSI<14+CB>=3 (round23新发现)
    eu_mask_rsi14_cb3 = (
        (xag_m5['session'] == 'europe') &
        (xag_m5.index.hour >= 9) &
        (xag_m5.index.hour < 11) &
        (xag_m5['rsi14'] < 14) &
        (xag_m5['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xag_m5, eu_mask_rsi14_cb3,
                                "XAG 欧盘9-11 RSI<14+CB>=3 (新发现86.5%)",
                                hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # 也测试CB>=2的宽松版
    eu_mask_rsi14_cb2 = (
        (xag_m5['session'] == 'europe') &
        (xag_m5.index.hour >= 9) &
        (xag_m5.index.hour < 11) &
        (xag_m5['rsi14'] < 14) &
        (xag_m5['consecutive_bear'] >= 2)
    )
    if eu_mask_rsi14_cb2.sum() >= 10:
        test_condition_with_periods(xag_m5, eu_mask_rsi14_cb2,
                                    "XAG 欧盘9-11 RSI<14+CB>=2 (宽松版对比)",
                                    hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    else:
        test_condition(xag_m5, eu_mask_rsi14_cb2,
                       "XAG 欧盘9-11 RSI<14+CB>=2 (宽松版对比)",
                       hold_range=[95, 100, 105, 110, 115, 120, 125, 130])

# ═══════════════════════════════════════════════════════════════
# H2: XAGUSD 美盘RSI<14+CB>=3 vs 旧RSI<18+CB>=3 跨周期对比
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H2: XAGUSD M5 美盘RSI<14+CB>=3 vs 旧RSI<18+CB>=3 跨周期对比")
print("=" * 70)
print("目标: 新荐87.5% vs 旧80.6% 跨周期稳定性对比 — 验证新阈值是否真优于旧阈值")

if xag_m5_raw:
    xag_m5_h2 = compute_indicators(xag_m5_raw["XAGUSD"])
    xag_m5_h2 = add_session_and_cb(xag_m5_h2)
    
    # 旧: RSI<18+CB>=3 (当前基准, WR=80.6% n=31)
    us_mask_old = (
        (xag_m5_h2['session'] == 'us') &
        (xag_m5_h2.index.hour >= 15) &
        (xag_m5_h2.index.hour < 16) &
        (xag_m5_h2['rsi14'] < 18) &
        (xag_m5_h2['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xag_m5_h2, us_mask_old,
                                "XAG 美盘15-16 RSI<18+CB>=3 (旧基准80.6%)",
                                hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # 新: RSI<14+CB>=3 (新荐, WR=87.5% n=16)
    us_mask_new = (
        (xag_m5_h2['session'] == 'us') &
        (xag_m5_h2.index.hour >= 15) &
        (xag_m5_h2.index.hour < 16) &
        (xag_m5_h2['rsi14'] < 14) &
        (xag_m5_h2['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xag_m5_h2, us_mask_new,
                                "XAG 美盘15-16 RSI<14+CB>=3 (新荐87.5%)",
                                hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # 过渡方案: RSI<16+CB>=4 (86.7% n=15)
    us_mask_mid = (
        (xag_m5_h2['session'] == 'us') &
        (xag_m5_h2.index.hour >= 15) &
        (xag_m5_h2.index.hour < 16) &
        (xag_m5_h2['rsi14'] < 16) &
        (xag_m5_h2['consecutive_bear'] >= 4)
    )
    test_condition_with_periods(xag_m5_h2, us_mask_mid,
                                "XAG 美盘15-16 RSI<16+CB>=4 (过渡86.7%)",
                                hold_range=[95, 100, 105, 110, 115, 120, 125, 130])
    
    # 对比表格
    print(f"\n--- 对比总结 (hold=105) ---")
    comp = []
    for name, mask in [("旧: RSI<18+CB>=3", us_mask_old),
                       ("新: RSI<14+CB>=3", us_mask_new),
                       ("过渡: RSI<16+CB>=4", us_mask_mid)]:
        n, wr, avg = get_stats(xag_m5_h2, mask, 105)
        comp.append((name, str(n), "105", f"{wr:.1f}%", f"{avg:.3f}%"))
    print_compact_comparison("XAGUSD 美盘三方案对比", comp)

# ═══════════════════════════════════════════════════════════════
# H3: XAUUSD 双枪策略(欧盘+美盘组合) — 更新数据+日期重叠再验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H3: XAUUSD 双枪策略(欧盘+美盘组合) — 更新数据+日期重叠再验证")
print("=" * 70)
print("目标: round23发现几乎完全互补(仅2天重叠) — 更新数据后重新验证重叠度+组合胜率")

xau_m5_raw = load_data("M5", symbols=["XAUUSD"])
if xau_m5_raw:
    xau_m5_h3 = compute_indicators(xau_m5_raw["XAUUSD"])
    xau_m5_h3 = add_session_and_cb(xau_m5_h3)
    
    # 欧盘: 9-11 RSI<18+CB>=4, hold=42
    mask_eu = (
        (xau_m5_h3['session'] == 'europe') &
        (xau_m5_h3.index.hour >= 9) &
        (xau_m5_h3.index.hour < 11) &
        (xau_m5_h3['rsi14'] < 18) &
        (xau_m5_h3['consecutive_bear'] >= 4)
    )
    
    # 美盘: 15-16 RSI<20+CB>=2, hold=115 (bf_046)
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
    
    # 日期重叠分析
    eu_dates = set(entries_eu.index.date)
    us_dates = set(entries_us.index.date)
    overlap_dates = eu_dates & us_dates
    
    print(f"\n--- 日期重叠分析 ---")
    print(f"  欧盘独立日期: {len(eu_dates)}")
    print(f"  美盘独立日期: {len(us_dates)}")
    print(f"  重叠日期: {len(overlap_dates)}")
    if len(overlap_dates) <= 5 and len(overlap_dates) > 0:
        print(f"  重叠日期列表: {sorted(overlap_dates)}")
    
    # 累加策略
    all_rets = np.concatenate([eu_rets, us_rets])
    print(f"\n--- 累加策略(欧盘+美盘独立开单) ---")
    print(f"  总信号数: {len(all_rets)}")
    print(f"  整体WR: {np.mean(all_rets>0)*100:.1f}%")
    print(f"  整体avg: {np.mean(all_rets):.3f}%")
    print(f"  整体std: {np.std(all_rets):.3f}%")
    print(f"  最大单笔: {np.max(all_rets):.3f}%")
    print(f"  最小单笔: {np.min(all_rets):.3f}%")
    
    # 时间分布
    eu_hours = entries_eu.index.hour.to_numpy()
    us_hours = entries_us.index.hour.to_numpy()
    print(f"\n--- 信号时间分布 ---")
    print(f"  欧盘: h{eu_hours.min()}-{eu_hours.max()}, 平均入场={eu_hours.mean():.1f}h")
    print(f"  美盘: h{us_hours.min()}-{us_hours.max()}, 平均入场={us_hours.mean():.1f}h")
    
    # 周分布
    eu_dow = entries_eu.index.dayofweek.to_numpy()
    us_dow = entries_us.index.dayofweek.to_numpy()
    print(f"\n--- 信号周分布 (0=周一) ---")
    eu_dow_dist = {i: int((eu_dow==i).sum()) for i in range(5)}
    us_dow_dist = {i: int((us_dow==i).sum()) for i in range(5)}
    print(f"  欧盘: {eu_dow_dist}")
    print(f"  美盘: {us_dow_dist}")
    
    # 近6个月细分
    cutoff_6m = pd.Timestamp.now() - pd.DateOffset(months=6)
    entries_eu_recent = entries_eu[entries_eu.index >= cutoff_6m]
    entries_us_recent = entries_us[entries_us.index >= cutoff_6m]
    print(f"\n--- 近6个月信号 ---")
    print(f"  欧盘: {len(entries_eu_recent)} signals")
    print(f"  美盘: {len(entries_us_recent)} signals")
    if len(entries_eu_recent) >= 5:
        eu_recent_rets = compute_returns(xau_m5_h3, entries_eu_recent, eu_hold)
        print(f"  欧盘近6月: n={len(eu_recent_rets)} WR={np.mean(eu_recent_rets>0)*100:.1f}% avg={np.mean(eu_recent_rets):.3f}%")
    if len(entries_us_recent) >= 5:
        us_recent_rets = compute_returns(xau_m5_h3, entries_us_recent, us_hold)
        print(f"  美盘近6月: n={len(us_recent_rets)} WR={np.mean(us_recent_rets>0)*100:.1f}% avg={np.mean(us_recent_rets):.3f}%")
    if len(entries_eu_recent) >= 5 and len(entries_us_recent) >= 5:
        all_recent = np.concatenate([eu_recent_rets, us_recent_rets])
        print(f"  组合近6月: n={len(all_recent)} WR={np.mean(all_recent>0)*100:.1f}% avg={np.mean(all_recent):.3f}%")

# ═══════════════════════════════════════════════════════════════
# H4: JPY / EURUSD / GBPUSD 等非贵金属品种超卖模式初探
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H4: 非贵金属品种超卖模式初探 — JPY/EURUSD/GBPUSD/US500/US30")
print("=" * 70)
print("目标: 将已验证的XAU/XAG超卖模式扩展到其他品种，探索可复制性")

# 加载多品种M5数据
m5_extra_raw = load_data("M5", symbols=["JP225", "EURUSD", "GBPUSD", "US500", "US30"])

for sym in ["JP225", "EURUSD", "GBPUSD", "US500", "US30"]:
    if sym not in m5_extra_raw:
        print(f"\n  ⚠️  {sym} M5 data not available")
        continue
    
    df_sym = compute_indicators(m5_extra_raw[sym])
    df_sym = add_session_and_cb(df_sym)
    
    print(f"\n--- {sym} M5 超卖模式探索 ---")
    print(f"  最新价: {df_sym['close'].iloc[-1]:.1f}  RSI(14): {df_sym['rsi14'].iloc[-1]:.1f}")
    
    # 策略A: 美盘15-16 RSI<14+CB>=2 (XAG新阈值移植)
    us_mask_a = (
        (df_sym['session'] == 'us') &
        (df_sym.index.hour >= 15) &
        (df_sym.index.hour < 16) &
        (df_sym['rsi14'] < 14) &
        (df_sym['consecutive_bear'] >= 2)
    )
    test_condition(df_sym, us_mask_a, f"{sym} US 15-16 RSI<14+CB>=2 (XAG移植)",
                  hold_range=[45, 50, 55, 60, 65, 70, 85, 100, 115])
    
    # 策略B: 美盘15-16 RSI<16+CB>=2 (较宽松)
    us_mask_b = (
        (df_sym['session'] == 'us') &
        (df_sym.index.hour >= 15) &
        (df_sym.index.hour < 16) &
        (df_sym['rsi14'] < 16) &
        (df_sym['consecutive_bear'] >= 2)
    )
    test_condition(df_sym, us_mask_b, f"{sym} US 15-16 RSI<16+CB>=2",
                  hold_range=[45, 50, 55, 60, 65, 70, 85, 100, 115])
    
    # 策略C: 美盘15-16 RSI<20+CB>=2 (XAU bf_046移植)
    us_mask_c = (
        (df_sym['session'] == 'us') &
        (df_sym.index.hour >= 15) &
        (df_sym.index.hour < 16) &
        (df_sym['rsi14'] < 20) &
        (df_sym['consecutive_bear'] >= 2)
    )
    test_condition(df_sym, us_mask_c, f"{sym} US 15-16 RSI<20+CB>=2 (XAU移植)",
                  hold_range=[45, 50, 55, 60, 65, 70, 85, 100, 115])
    
    # 策略D: 欧盘9-11 RSI<14+CB>=3 (XAG欧盘移植)
    eu_mask_d = (
        (df_sym['session'] == 'europe') &
        (df_sym.index.hour >= 9) &
        (df_sym.index.hour < 11) &
        (df_sym['rsi14'] < 14) &
        (df_sym['consecutive_bear'] >= 3)
    )
    test_condition(df_sym, eu_mask_d, f"{sym} EU 9-11 RSI<14+CB>=3 (XAG欧盘移植)",
                  hold_range=[45, 50, 55, 60, 65, 70, 85, 100, 115])

# ═══════════════════════════════════════════════════════════════
# H5: XAGUSD 美盘RSI<16+CB>=5 (最严格阈值) 数据积累 + 深度验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("H5: XAGUSD 美盘RSI<16+CB>=5 (最严格阈值) 数据积累 + 深度验证")
print("=" * 70)
print("目标: round23发现RSI<16+CB>=5 WR=90.9% n=11 — 数据积累+跨周期验证+hold精细调优")

if xag_m5_raw:
    xag_m5_h5 = compute_indicators(xag_m5_raw["XAGUSD"])
    xag_m5_h5 = add_session_and_cb(xag_m5_h5)
    
    # RSI<16+CB>=5 (最严格, WR=90.9% n=11)
    us_mask_strict1 = (
        (xag_m5_h5['session'] == 'us') &
        (xag_m5_h5.index.hour >= 15) &
        (xag_m5_h5.index.hour < 16) &
        (xag_m5_h5['rsi14'] < 16) &
        (xag_m5_h5['consecutive_bear'] >= 5)
    )
    test_condition_with_periods(xag_m5_h5, us_mask_strict1,
                                "XAG 美盘15-16 RSI<16+CB>=5 (最严格CB>=5)",
                                hold_range=[85, 90, 95, 100, 105, 110, 115, 120, 125, 130])
    
    # RSI<14+CB>=4 (另一种极端组合)
    us_mask_strict2 = (
        (xag_m5_h5['session'] == 'us') &
        (xag_m5_h5.index.hour >= 15) &
        (xag_m5_h5.index.hour < 16) &
        (xag_m5_h5['rsi14'] < 14) &
        (xag_m5_h5['consecutive_bear'] >= 4)
    )
    test_condition(xag_m5_h5, us_mask_strict2,
                   "XAG 美盘15-16 RSI<14+CB>=4 (极端RSI+高CB)",
                   hold_range=[85, 90, 95, 100, 105, 110, 115, 120, 125, 130])
    
    # RSI<15+CB>=5 (中间RSI + 高CB)
    us_mask_strict3 = (
        (xag_m5_h5['session'] == 'us') &
        (xag_m5_h5.index.hour >= 15) &
        (xag_m5_h5.index.hour < 16) &
        (xag_m5_h5['rsi14'] < 15) &
        (xag_m5_h5['consecutive_bear'] >= 5)
    )
    test_condition(xag_m5_h5, us_mask_strict3,
                   "XAG 美盘15-16 RSI<15+CB>=5 (中间RSI)",
                   hold_range=[85, 90, 95, 100, 105, 110, 115, 120, 125, 130])
    
    # 所有美盘XAG模式全览对比
    print(f"\n--- XAGUSD 美盘15-16 全部候选对比 (hold=105) ---")
    us_mask_old_h5 = (
        (xag_m5_h5['session'] == 'us') & (xag_m5_h5.index.hour >= 15) & (xag_m5_h5.index.hour < 16) &
        (xag_m5_h5['rsi14'] < 18) & (xag_m5_h5['consecutive_bear'] >= 3)
    )
    us_mask_new_h5 = (
        (xag_m5_h5['session'] == 'us') & (xag_m5_h5.index.hour >= 15) & (xag_m5_h5.index.hour < 16) &
        (xag_m5_h5['rsi14'] < 14) & (xag_m5_h5['consecutive_bear'] >= 3)
    )
    us_mask_mid_h5 = (
        (xag_m5_h5['session'] == 'us') & (xag_m5_h5.index.hour >= 15) & (xag_m5_h5.index.hour < 16) &
        (xag_m5_h5['rsi14'] < 16) & (xag_m5_h5['consecutive_bear'] >= 4)
    )
    
    comp_all = []
    results_all = {}
    for name, mask in [
        ("旧基准: RSI<18+CB>=3", us_mask_old_h5),
        ("新荐:   RSI<14+CB>=3", us_mask_new_h5),
        ("过渡:   RSI<16+CB>=4", us_mask_mid_h5),
        ("最严:   RSI<16+CB>=5", us_mask_strict1),
        ("极严2:  RSI<14+CB>=4", us_mask_strict2),
        ("中间:   RSI<15+CB>=5", us_mask_strict3),
    ]:
        n, wr, avg = get_stats(xag_m5_h5, mask, 105)
        comp_all.append((name, str(n), "105", f"{wr:.1f}%", f"{avg:.3f}%"))
        results_all[name.strip()] = {"n": n, "wr": wr, "avg": avg}
    
    print_compact_comparison("XAGUSD 美盘全部候选对比 (hold=105)", comp_all)
    
    # 推荐决策
    print(f"\n--- 推荐决策 ---")
    if results_all:
        best_name = max(results_all, key=lambda k: results_all[k]['wr'] * 0.6 + min(results_all[k]['n'] / 30, 1) * 40)
        print(f"  🏆 综合最佳: {best_name}")
        print(f"     WR={results_all[best_name]['wr']:.1f}% n={results_all[best_name]['n']} avg={results_all[best_name]['avg']:.3f}%")

print("\n" + "=" * 70)
print("ROUND 24 — 完成")
print(f"Time: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 70)
