#!/usr/bin/env python3
"""
Round 26 — 超短线研究循环
Testing priority hypotheses from round25 next_actions:
1. round26_001: 共振欧盘→XAU (RSI<18+CB>=1 hold=42 WR=91.7% n=24) 跨周期稳定性验证
2. round26_002: XAGUSD 美盘极端阈值 (RSI<14+CB>=4 / RSI<16+CB>=5) 数据积累
3. round26_003: 双枪策略跟踪 — 近6月表现监测
4. round26_004: XAGUSD 欧盘hold=85 新参数跨周期验证
5. round26_005: US30 非超卖方向探索
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# HELPERS (same as round24/25)
# ═══════════════════════════════════════════════════════════════

def add_session_and_cb(df):
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
    entries = df[condition_mask].copy()
    print(f"\n--- {label} ---")
    print(f"Entry signals: {len(entries)}")
    if len(entries) < 5:
        print(f"  ⚠️  Too few signals ({len(entries)}), skipping")
        return entries
    if hold_range is None:
        hold_range = list(range(10, 131, 5))
    results = {}
    for hold in hold_range:
        hits, total_pnl, count = 0, 0.0, 0
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

def test_condition_with_periods(df, condition_mask, label, hold_range=None, min_signals=10):
    entries_all = df[condition_mask].copy()
    print(f"\n--- {label} (跨周期稳定性验证) ---")
    print(f"Total signals: {len(entries_all)}")
    if len(entries_all) < min_signals:
        print(f"  ⚠️  Too few signals ({len(entries_all)}), skipping period breakdown")
        if len(entries_all) >= 5:
            return test_condition(df, condition_mask, label, hold_range)
        return entries_all
    if hold_range is None:
        hold_range = list(range(10, 131, 5))
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
            hits, total_pnl, count = 0, 0.0, 0
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
        hits, total_pnl, count = 0, 0.0, 0
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
    print(f"\n  ** {title} **")
    print(f"  {'条件':<55} {'信号数':<8} {'Hold':<6} {'胜率':<8} {'平均收益':<12}")
    print(f"  {'-'*55} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")
    for row in data:
        print(f"  {row[0]:<55} {row[1]:<8} {row[2]:<6} {row[3]:<8} {row[4]:<12}")

def compute_returns_from_entries(df, entries, hold):
    rets = []
    for idx, row in entries.iterrows():
        entry_price = row['close']
        pos = df.index.get_loc(idx)
        if pos + hold < len(df):
            exit_price = df.iloc[pos + hold]['close']
            ret = (exit_price - entry_price) / entry_price * 100
            rets.append(ret)
    return np.array(rets)

def bootstrap_confidence(rets, n_iter=10000):
    n = len(rets)
    if n < 10:
        return None, None
    wr_dist = np.array([(np.random.choice(rets, n, replace=True) > 0).mean() * 100 for _ in range(n_iter)])
    return np.percentile(wr_dist, 2.5), np.percentile(wr_dist, 97.5)

def monthly_split(df):
    """Split data by month for tracking performance over time."""
    df = df.copy()
    df['year_month'] = df.index.to_period('M')
    return df

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 80)
print("ROUND 26 — Scalping M1/M5 深度验证 + 新方向探索")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=26, testing round26_001~005")
print("=" * 80)

# ── Load data ──
print(f"\n--- M5 Data Summary ---")
all_data = {}
for sym in ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]:
    raw = load_data("M5", symbols=[sym])
    if raw:
        df = compute_indicators(raw[sym])
        df = add_session_and_cb(df)
        all_data[sym] = df
        print(f"  {sym:8s} M5: {len(df):>8} rows  [{df.index[0].date()} → {df.index[-1].date()}]  "
              f"Close={df['close'].iloc[-1]:.1f}  RSI={df['rsi14'].iloc[-1]:.1f}  "
              f"ATR%={df['atr14_pct'].iloc[-1]:.3f}%")
    else:
        print(f"  ⚠️  {sym}: data not available")

# ═══════════════════════════════════════════════════════════════
# H1: 共振欧盘→XAU (RSI<18+CB>=1) 跨周期稳定性验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H1: 共振欧盘→XAU (RSI<18+CB>=1) 跨周期稳定性验证")
print("=" * 80)
print("目标: round25新发现 欧盘共振→XAU WR=91.7% n=24 — 需P1/P2/P3跨周期验证")
print("      条件: EU 9-11 RSI<18+CB>=1 (XAU+XAG同时满足) hold=42")

if "XAUUSD" in all_data and "XAGUSD" in all_data:
    xau_h1 = all_data["XAUUSD"]
    xag_h1 = all_data["XAGUSD"]
    
    # 对齐两个品种
    common_idx = xau_h1.index.intersection(xag_h1.index)
    xau_aligned = xau_h1.loc[common_idx]
    xag_aligned = xag_h1.loc[common_idx]
    
    # 共振欧盘 RSI<18+CB>=1 (round25 best)
    res_eu_mask = (
        (xau_aligned['session'] == 'europe') &
        (xau_aligned.index.hour >= 9) &
        (xau_aligned.index.hour < 11) &
        (xau_aligned['rsi14'] < 18) &
        (xau_aligned['consecutive_bear'] >= 1) &
        (xag_aligned['consecutive_bear'] >= 1)
    )
    test_condition_with_periods(xau_aligned, res_eu_mask,
                                "共振欧盘→XAU EU 9-11 RSI<18+CB>=1",
                                hold_range=list(range(30, 61, 2)) + [42, 55, 65, 75, 95, 115],
                                min_signals=8)
    
    # 同时验证共振欧盘→XAG
    res_eu_mask_xag = (
        (xag_aligned['session'] == 'europe') &
        (xag_aligned.index.hour >= 9) &
        (xag_aligned.index.hour < 11) &
        (xag_aligned['rsi14'] < 18) &
        (xag_aligned['consecutive_bear'] >= 1) &
        (xau_aligned['consecutive_bear'] >= 1)
    )
    test_condition_with_periods(xag_aligned, res_eu_mask_xag,
                                "共振欧盘→XAG EU 9-11 RSI<18+CB>=1",
                                hold_range=list(range(30, 61, 2)) + [42, 55, 65, 75, 95, 115, 130],
                                min_signals=8)
    
    # Bootstrap CI
    print(f"\n--- Bootstrap置信区间 (共振欧盘→XAU) ---")
    entries_res_xau = xau_aligned[res_eu_mask].copy()
    if len(entries_res_xau) >= 10:
        rets_res_xau = compute_returns_from_entries(xau_aligned, entries_res_xau, 42)
        ci_low, ci_high = bootstrap_confidence(rets_res_xau)
        print(f"  共振欧盘→XAU hold=42: n={len(rets_res_xau)} WR={np.mean(rets_res_xau>0)*100:.1f}%")
        print(f"  Bootstrap 95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]")
    
    # 对比共振美盘→XAU (RSI<18+CB>=1)
    print(f"\n--- 共振美盘→XAU 对比 ---")
    res_us_mask = (
        (xau_aligned['session'] == 'us') &
        (xau_aligned.index.hour >= 15) &
        (xau_aligned.index.hour < 16) &
        (xau_aligned['rsi14'] < 18) &
        (xau_aligned['consecutive_bear'] >= 1) &
        (xag_aligned['consecutive_bear'] >= 1)
    )
    test_condition_with_periods(xau_aligned, res_us_mask,
                                "共振美盘→XAU US 15-16 RSI<18+CB>=1",
                                hold_range=list(range(30, 121, 5)),
                                min_signals=8)
    
    # 共振美盘→XAG 对比
    res_us_mask_xag = (
        (xag_aligned['session'] == 'us') &
        (xag_aligned.index.hour >= 15) &
        (xag_aligned.index.hour < 16) &
        (xag_aligned['rsi14'] < 18) &
        (xag_aligned['consecutive_bear'] >= 1) &
        (xau_aligned['consecutive_bear'] >= 1)
    )
    test_condition_with_periods(xag_aligned, res_us_mask_xag,
                                "共振美盘→XAG US 15-16 RSI<18+CB>=1",
                                hold_range=list(range(30, 121, 5)),
                                min_signals=8)

# ═══════════════════════════════════════════════════════════════
# H2: XAGUSD 美盘极端阈值 数据积累
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H2: XAGUSD 美盘极端阈值 数据积累 (n>=20目标)")
print("=" * 80)
print("目标: round24发现 XAG美盘RSI<14+CB>=4 91.7% n=12 / RSI<16+CB>=5 90.9% n=11")
print("      现在用更多数据验证这些极端阈值是否持续有效")

if "XAGUSD" in all_data:
    xag_h2 = all_data["XAGUSD"]
    
    # 极端阈值条件集合
    extreme_conditions = [
        ("XAG US 15-16 RSI<14+CB>=4 (极端1)",
         (xag_h2['session'] == 'us') & (xag_h2.index.hour >= 15) & (xag_h2.index.hour < 16) &
         (xag_h2['rsi14'] < 14) & (xag_h2['consecutive_bear'] >= 4)),
        ("XAG US 15-16 RSI<16+CB>=5 (极端2)",
         (xag_h2['session'] == 'us') & (xag_h2.index.hour >= 15) & (xag_h2.index.hour < 16) &
         (xag_h2['rsi14'] < 16) & (xag_h2['consecutive_bear'] >= 5)),
        ("XAG US 15-16 RSI<14+CB>=5 (极端3)",
         (xag_h2['session'] == 'us') & (xag_h2.index.hour >= 15) & (xag_h2.index.hour < 16) &
         (xag_h2['rsi14'] < 14) & (xag_h2['consecutive_bear'] >= 5)),
        ("XAG US 13-16 RSI<14+CB>=4 (宽时段)",
         (xag_h2['session'] == 'us') & (xag_h2.index.hour >= 13) & (xag_h2.index.hour < 16) &
         (xag_h2['rsi14'] < 14) & (xag_h2['consecutive_bear'] >= 4)),
        ("XAG US 15-16 RSI<12+CB>=3 (更极端RSI)",
         (xag_h2['session'] == 'us') & (xag_h2.index.hour >= 15) & (xag_h2.index.hour < 16) &
         (xag_h2['rsi14'] < 12) & (xag_h2['consecutive_bear'] >= 3)),
        ("XAG US 15-16 RSI<14+CB>=3 (基准对比)",
         (xag_h2['session'] == 'us') & (xag_h2.index.hour >= 15) & (xag_h2.index.hour < 16) &
         (xag_h2['rsi14'] < 14) & (xag_h2['consecutive_bear'] >= 3)),
    ]
    
    print(f"\n--- XAG美盘极端阈值扫描 ---")
    # 对每个条件测试多个hold值
    for name, mask in extreme_conditions:
        entries = xag_h2[mask].copy()
        print(f"\n  [{name}]")
        print(f"    信号数: {len(entries)}")
        if len(entries) >= 5:
            # 尝试hold=85,95,105,115,125 (XAG典型范围)
            best_n, best_wr, best_hold = 0, 0, 0
            for hold in [85, 95, 105, 115, 125, 135]:
                n, wr, avg = get_stats(xag_h2, mask, hold)
                if n >= 5:
                    print(f"    hold={hold}: WR={wr:.1f}% n={n} avg={avg:.3f}%")
                    if wr > best_wr:
                        best_wr, best_n, best_hold = wr, n, hold
            if best_n >= 5:
                print(f"    → 最佳: hold={best_hold} WR={best_wr:.1f}% n={best_n}")
                
                # 跨周期验证
                if best_n >= 10:
                    print(f"    → 跨周期验证 (hold={best_hold})...")
                    test_condition_with_periods(xag_h2, mask, 
                                                f"XAG {name} (hold={best_hold})",
                                                hold_range=[best_hold-10, best_hold-5, best_hold, best_hold+5, best_hold+10],
                                                min_signals=5)
        else:
            print(f"    信号太少, 跳过")
    
    # 更新基准对比: XAG美盘旧基准 (RSI<18+CB>=3 hold=105)
    print(f"\n--- XAG美盘基准策略更新 ---")
    xag_us_mask = (
        (xag_h2['session'] == 'us') &
        (xag_h2.index.hour >= 15) &
        (xag_h2.index.hour < 16) &
        (xag_h2['rsi14'] < 18) &
        (xag_h2['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(xag_h2, xag_us_mask,
                                "XAG US 15-16 RSI<18+CB>=3 (旧基准)",
                                hold_range=list(range(80, 131, 5)))

# ═══════════════════════════════════════════════════════════════
# H3: 双枪策略跟踪 — 近6月表现监测
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H3: 双枪策略跟踪 — 近6月表现监测")
print("=" * 80)
print("目标: round25双枪组合WR=87.7% n=114 (全历史). 检查近6月是否持续有效")
print("      双枪欧盘: EU 9-11 RSI<18+CB>=4 hold=42")
print("      双枪美盘: US 15-16 RSI<20+CB>=2 hold=115")

if "XAUUSD" in all_data:
    xau_h3 = all_data["XAUUSD"]
    
    # 将数据分成近期 vs 早期
    # 近6月: 从 2025-11-13 到 2026-05-13
    recent_cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
    early_mask = xau_h3.index < recent_cutoff
    recent_mask = xau_h3.index >= recent_cutoff
    
    print(f"  数据分割点: {recent_cutoff.date()}")
    print(f"  早期: {early_mask.sum()} 行, 近期: {recent_mask.sum()} 行")
    
    # 双枪欧盘
    eu_mask_h3 = (
        (xau_h3['session'] == 'europe') &
        (xau_h3.index.hour >= 9) &
        (xau_h3.index.hour < 11) &
        (xau_h3['rsi14'] < 18) &
        (xau_h3['consecutive_bear'] >= 4)
    )
    
    # 双枪美盘
    us_mask_h3 = (
        (xau_h3['session'] == 'us') &
        (xau_h3.index.hour >= 15) &
        (xau_h3.index.hour < 16) &
        (xau_h3['rsi14'] < 20) &
        (xau_h3['consecutive_bear'] >= 2)
    )
    
    print(f"\n--- 双枪欧盘 hold=42 ---")
    for period_name, period_df in [("早期 (全历史-近6月)", xau_h3[early_mask]),
                                    ("近期 (近6月)", xau_h3[recent_mask])]:
        if len(period_df) < 1000:
            print(f"  {period_name}: 数据不足")
            continue
        period_mask_eu = eu_mask_h3.reindex(period_df.index, fill_value=False)
        n, wr, avg = get_stats(period_df, period_mask_eu, 42)
        print(f"  {period_name}: n={n} WR={wr:.1f}% avg={avg:.3f}%")
    
    print(f"\n--- 双枪美盘 hold=115 ---")
    for period_name, period_df in [("早期 (全历史-近6月)", xau_h3[early_mask]),
                                    ("近期 (近6月)", xau_h3[recent_mask])]:
        if len(period_df) < 1000:
            continue
        period_mask_us = us_mask_h3.reindex(period_df.index, fill_value=False)
        n, wr, avg = get_stats(period_df, period_mask_us, 115)
        print(f"  {period_name}: n={n} WR={wr:.1f}% avg={avg:.3f}%")
    
    # 分月跟踪
    print(f"\n--- 双枪策略 月度表现跟踪 ---")
    xau_h3['month'] = xau_h3.index.to_period('M')
    recent_data = xau_h3[xau_h3.index >= (pd.Timestamp.now() - pd.DateOffset(months=12))]
    
    print(f"  {'月份':<10} {'欧盘信号':<8} {'欧盘WR':<8} {'美盘信号':<8} {'美盘WR':<8} {'组合信号':<8} {'组合WR':<8}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    
    for month, grp in recent_data.groupby('month'):
        grp_mask_eu = eu_mask_h3.reindex(grp.index, fill_value=False)
        grp_mask_us = us_mask_h3.reindex(grp.index, fill_value=False)
        n_eu, wr_eu, _ = get_stats(grp, grp_mask_eu, 42)
        n_us, wr_us, _ = get_stats(grp, grp_mask_us, 115)
        n_comb = n_eu + n_us
        # 组合WR: 加权平均
        if n_eu + n_us > 0:
            wr_comb = (wr_eu * n_eu + wr_us * n_us) / (n_eu + n_us) if (n_eu + n_us) > 0 else 0
        else:
            wr_comb = 0
        print(f"  {str(month):<10} {n_eu:<8} {wr_eu:.1f}%{'':>3} {n_us:<8} {wr_us:.1f}%{'':>3} {n_comb:<8} {wr_comb:.1f}%")
    
    # 近6月 vs 全历史汇总对比
    print(f"\n--- 双枪策略总结对比 ---")
    comp_h3 = []
    for name, mask, hold in [
        ("双枪欧盘 XAU (EU 9-11 RSI<18+CB>=4)", eu_mask_h3, 42),
        ("双枪美盘 XAU (US 15-16 RSI<20+CB>=2)", us_mask_h3, 115),
    ]:
        n_all, wr_all, avg_all = get_stats(xau_h3, mask, hold)
        n_recent, wr_recent, avg_recent = get_stats(xau_h3, mask & recent_mask, hold)
        comp_h3.append((f"{name} [全历史]", str(n_all), str(hold), f"{wr_all:.1f}%", f"{avg_all:.3f}%"))
        comp_h3.append((f"{name} [近6月]", str(n_recent), str(hold), f"{wr_recent:.1f}%", f"{avg_recent:.3f}%"))
    print_compact_comparison("双枪策略 全历史 vs 近6月", comp_h3)

# ═══════════════════════════════════════════════════════════════
# H4: XAGUSD 欧盘hold=85 新参数跨周期验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H4: XAGUSD 欧盘hold=85 新参数跨周期验证")
print("=" * 80)
print("目标: round25将hold从115→85优化. 需确认P1/P2/P3各周期hold=85稳定性")
print("      条件: EU 9-11 RSI<14+CB>=3")

if "XAGUSD" in all_data:
    xag_h4 = all_data["XAGUSD"]
    
    eu_mask_xag = (
        (xag_h4['session'] == 'europe') &
        (xag_h4.index.hour >= 9) &
        (xag_h4.index.hour < 11) &
        (xag_h4['rsi14'] < 14) &
        (xag_h4['consecutive_bear'] >= 3)
    )
    
    entries_xag_eu = xag_h4[eu_mask_xag].copy()
    print(f"  总信号数: {len(entries_xag_eu)}")
    
    if len(entries_xag_eu) >= 10:
        # 跨周期验证hold=85 vs hold=115
        print(f"\n  --- hold=85 跨周期分解 ---")
        test_condition_with_periods(xag_h4, eu_mask_xag,
                                    "XAG EU 9-11 RSI<14+CB>=3 hold=85验证",
                                    hold_range=[75, 80, 85, 90, 95, 105, 115],
                                    min_signals=8)
        
        # 对比hold=85 vs hold=115在每个周期
        print(f"\n  --- hold=85 vs hold=115 逐周期对比 ---")
        
        dates = xag_h4.index.sort_values()
        n_idx = len(dates)
        split1 = dates[int(n_idx * 0.33)]
        split2 = dates[int(n_idx * 0.67)]
        periods = {
            'P1 (最早)': xag_h4[xag_h4.index < split1],
            'P2 (中段)': xag_h4[(xag_h4.index >= split1) & (xag_h4.index < split2)],
            'P3 (最近)': xag_h4[xag_h4.index >= split2],
        }
        
        print(f"  {'周期':<12} {'hold=85 WR':<12} {'hold=85 n':<10} {'hold=115 WR':<13} {'hold=115 n':<10} {'优劣':<8}")
        print(f"  {'-'*12} {'-'*12} {'-'*10} {'-'*13} {'-'*10} {'-'*8}")
        
        for pname, pdf in periods.items():
            pmask = eu_mask_xag.reindex(pdf.index, fill_value=False)
            n85, wr85, _ = get_stats(pdf, pmask, 85)
            n115, wr115, _ = get_stats(pdf, pmask, 115)
            verdict = "hold=85 ✅" if wr85 >= wr115 else ("hold=115 ✅" if wr115 > wr85 else "持平")
            print(f"  {pname:<12} {wr85:.1f}%{'':>6} {n85:<10} {wr115:.1f}%{'':>7} {n115:<10} {verdict:<8}")
        
        # 全周期对比
        n85_all, wr85_all, avg85_all = get_stats(xag_h4, eu_mask_xag, 85)
        n115_all, wr115_all, avg115_all = get_stats(xag_h4, eu_mask_xag, 115)
        verdict_all = "hold=85 ✅" if wr85_all >= wr115_all else ("hold=115 ✅" if wr115_all > wr85_all else "持平")
        print(f"  {'全周期':<12} {wr85_all:.1f}%{'':>6} {n85_all:<10} {wr115_all:.1f}%{'':>7} {n115_all:<10} {verdict_all:<8}")
        
        # Bootstrap CI
        print(f"\n  --- Bootstrap置信区间 ---")
        rets85 = compute_returns_from_entries(xag_h4, entries_xag_eu, 85)
        rets115 = compute_returns_from_entries(xag_h4, entries_xag_eu, 115)
        if len(rets85) >= 10:
            ci_low85, ci_high85 = bootstrap_confidence(rets85)
            print(f"  hold=85: n={len(rets85)} WR={np.mean(rets85>0)*100:.1f}% Bootstrap 95% CI: [{ci_low85:.1f}%, {ci_high85:.1f}%]")
        if len(rets115) >= 10:
            ci_low115, ci_high115 = bootstrap_confidence(rets115)
            print(f"  hold=115: n={len(rets115)} WR={np.mean(rets115>0)*100:.1f}% Bootstrap 95% CI: [{ci_low115:.1f}%, {ci_high115:.1f}%]")

# ═══════════════════════════════════════════════════════════════
# H5: US30 非超卖方向探索
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H5: US30 非超卖方向探索 — 布林带突破/波动率/缺口填补")
print("=" * 80)
print("目标: 之前研究集中在超卖RSI<20, US30超卖信号极少. 探索其他维度的交易模式")
print("      方向: 布林带上轨突破, 波动率扩张, 开盘缺口填补")

if "US30" in all_data:
    us30 = all_data["US30"]
    
    # 计算布林带 (20,2)
    us30['ma20'] = us30['close'].rolling(20).mean()
    us30['bb_std'] = us30['close'].rolling(20).std()
    us30['bb_upper'] = us30['ma20'] + 2 * us30['bb_std']
    us30['bb_lower'] = us30['ma20'] - 2 * us30['bb_std']
    us30['bb_width'] = (us30['bb_upper'] - us30['bb_lower']) / us30['ma20'] * 100
    
    # 开盘缺口 (与前日收盘比)
    us30['prev_close'] = us30['close'].shift(1)
    us30['gap_pct'] = (us30['open'] - us30['prev_close']) / us30['prev_close'] * 100
    
    # 波动率变化
    us30['prev_atr14'] = us30['atr14'].shift(1)
    us30['atr_expansion'] = (us30['atr14'] / us30['prev_atr14'] - 1) * 100
    
    print(f"\n  US30 基础统计:")
    print(f"    布林带宽度: mean={us30['bb_width'].mean():.3f}% std={us30['bb_width'].std():.3f}%")
    print(f"    开盘缺口: mean={us30['gap_pct'].mean():.3f}% std={us30['gap_pct'].std():.3f}%")
    print(f"    ATR%: mean={us30['atr14_pct'].mean():.3f}%")
    
    # ── H5a: 布林带下轨反弹 (超卖替代) ──
    print(f"\n  --- H5a: 布林带下轨反弹 (close < bb_lower) ---")
    bb_lower_mask = (
        (us30['close'] < us30['bb_lower']) &
        (us30['consecutive_bear'] >= 1)
    )
    test_condition_with_periods(us30, bb_lower_mask,
                                "US30 布林带下轨+阴线",
                                hold_range=list(range(5, 61, 5)),
                                min_signals=8)
    
    # ── H5b: 布林带上轨突破做空 ──
    print(f"\n  --- H5b: 布林带上轨突破做空 (close > bb_upper + 阴线) ---")
    bb_upper_mask = (
        (us30['close'] > us30['bb_upper']) &
        (us30['close'] < us30['open'])  # 阴线
    )
    test_condition_with_periods(us30, bb_upper_mask,
                                "US30 布林带上轨+阴线 (做空信号)",
                                hold_range=list(range(5, 61, 5)),
                                min_signals=8)
    
    # ── H5c: 开盘跳空填补策略 ──
    print(f"\n  --- H5c: 开盘跳空填补 (开盘大幅低开后的反弹) ---")
    gap_down_mask = (
        (us30['gap_pct'] < -0.1) &  # 低开>0.1%
        (us30['rsi14'] < 40) &      # 非超买
        (us30['close'] > us30['open'])  # 阳线=开始反弹
    )
    test_condition_with_periods(us30, gap_down_mask,
                                "US30 低开>0.1%+RSI<40+阳线",
                                hold_range=list(range(10, 121, 10)),
                                min_signals=8)
    
    # ── H5d: ATR扩张后的均值回归 ──
    print(f"\n  --- H5d: ATR扩张 (波动率激增) → 均值回归 ---")
    atr_expand_mask = (
        (us30['atr_expansion'] > 30) &  # ATR比前根扩张>30%
        (us30['rsi14'] < 45)            # 非超买区域
    )
    test_condition_with_periods(us30, atr_expand_mask,
                                "US30 ATR扩张>30%+RSI<45",
                                hold_range=list(range(5, 61, 5)),
                                min_signals=8)
    
    # ── H5e: 美盘特定时段 + 布林带 ──
    print(f"\n  --- H5e: 美盘15-16 布林带下轨反弹 ---")
    bb_us_mask = (
        (us30['session'] == 'us') &
        (us30.index.hour >= 15) &
        (us30.index.hour < 16) &
        (us30['close'] < us30['bb_lower']) &
        (us30['consecutive_bear'] >= 1)
    )
    test_condition_with_periods(us30, bb_us_mask,
                                "US30 美盘15-16 BB下轨+阴线",
                                hold_range=list(range(5, 61, 5)),
                                min_signals=8)
    
    # 汇总对比
    print(f"\n--- US30 各策略汇总 ---")
    comp_us30 = []
    for name, mask, hold in [
        ("BB下轨+阴线", bb_lower_mask, 25),
        ("BB上轨+阴线(做空)", bb_upper_mask, 25),
        ("低开>0.1%+RSI<40+阳线", gap_down_mask, 40),
        ("ATR扩张>30%+RSI<45", atr_expand_mask, 20),
        ("美盘15-16 BB下轨+阴线", bb_us_mask, 20),
    ]:
        n, wr, avg = get_stats(us30, mask, hold)
        if n >= 5:
            comp_us30.append((name, str(n), str(hold), f"{wr:.1f}%", f"{avg:.3f}%"))
    if comp_us30:
        print_compact_comparison("US30 非超卖策略探索", comp_us30)
        best_us30 = max(comp_us30, key=lambda r: float(r[3].strip('%')) * 0.5 + min(int(r[1]) / 20, 1) * 50)
        print(f"\n  🏆 US30最佳: {best_us30[0]} WR={best_us30[3]} n={best_us30[1]}")

# ═══════════════════════════════════════════════════════════════
# 全策略可行性对比 (更新)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("全策略可行性对比 (round26更新)")
print("=" * 80)

# Collect all strategies with consistent metrics
all_strategies = []

if "XAUUSD" in all_data and "XAGUSD" in all_data:
    xau_s = all_data["XAUUSD"]
    xag_s = all_data["XAGUSD"]
    common_s = xau_s.index.intersection(xag_s.index)
    xau_aligned_s = xau_s.loc[common_s]
    xag_aligned_s = xag_s.loc[common_s]
    
    # 共振欧盘→XAU (RSI<18+CB>=1 hold=42)
    res_eu_xau_mask_s = (
        (xau_aligned_s['session'] == 'europe') & (xau_aligned_s.index.hour >= 9) & (xau_aligned_s.index.hour < 11) &
        (xau_aligned_s['rsi14'] < 18) & (xau_aligned_s['consecutive_bear'] >= 1) & (xag_aligned_s['consecutive_bear'] >= 1)
    )
    ents = xau_aligned_s[res_eu_xau_mask_s]
    if len(ents) >= 5:
        rets = compute_returns_from_entries(xau_aligned_s, ents, 42)
        all_strategies.append(("共振欧盘→XAU RSI<18+CB>=1", "XAUUSD", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # 共振欧盘→XAG (RSI<18+CB>=1 hold=115)
    res_eu_xag_mask_s = (
        (xag_aligned_s['session'] == 'europe') & (xag_aligned_s.index.hour >= 9) & (xag_aligned_s.index.hour < 11) &
        (xag_aligned_s['rsi14'] < 18) & (xag_aligned_s['consecutive_bear'] >= 1) & (xau_aligned_s['consecutive_bear'] >= 1)
    )
    ents = xag_aligned_s[res_eu_xag_mask_s]
    if len(ents) >= 5:
        rets = compute_returns_from_entries(xag_aligned_s, ents, 115)
        all_strategies.append(("共振欧盘→XAG RSI<18+CB>=1", "XAGUSD", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # 共振美盘→XAU (RSI<18+CB>=1 hold=95)
    res_us_xau_mask_s = (
        (xau_aligned_s['session'] == 'us') & (xau_aligned_s.index.hour >= 15) & (xau_aligned_s.index.hour < 16) &
        (xau_aligned_s['rsi14'] < 18) & (xau_aligned_s['consecutive_bear'] >= 1) & (xag_aligned_s['consecutive_bear'] >= 1)
    )
    ents = xau_aligned_s[res_us_xau_mask_s]
    if len(ents) >= 5:
        rets = compute_returns_from_entries(xau_aligned_s, ents, 95)
        all_strategies.append(("共振美盘→XAU RSI<18+CB>=1", "XAUUSD", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # 双枪欧盘
    eu_mask_s = (xau_s['session'] == 'europe') & (xau_s.index.hour >= 9) & (xau_s.index.hour < 11) & (xau_s['rsi14'] < 18) & (xau_s['consecutive_bear'] >= 4)
    ents = xau_s[eu_mask_s]
    if len(ents) >= 5:
        rets = compute_returns_from_entries(xau_s, ents, 42)
        all_strategies.append(("双枪欧盘做多XAU", "XAUUSD", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # 双枪美盘
    us_mask_s = (xau_s['session'] == 'us') & (xau_s.index.hour >= 15) & (xau_s.index.hour < 16) & (xau_s['rsi14'] < 20) & (xau_s['consecutive_bear'] >= 2)
    ents = xau_s[us_mask_s]
    if len(ents) >= 5:
        rets = compute_returns_from_entries(xau_s, ents, 115)
        all_strategies.append(("双枪美盘做多XAU", "XAUUSD", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # XAG欧盘
    xag_eu_mask_s = (xag_s['session'] == 'europe') & (xag_s.index.hour >= 9) & (xag_s.index.hour < 11) & (xag_s['rsi14'] < 14) & (xag_s['consecutive_bear'] >= 3)
    ents = xag_s[xag_eu_mask_s]
    if len(ents) >= 5:
        rets = compute_returns_from_entries(xag_s, ents, 85)  # updated from 115 to 85
        all_strategies.append(("XAG欧盘RSI<14+CB>=3 hold=85★", "XAGUSD", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # XAG美盘
    xag_us_mask_s = (xag_s['session'] == 'us') & (xag_s.index.hour >= 15) & (xag_s.index.hour < 16) & (xag_s['rsi14'] < 18) & (xag_s['consecutive_bear'] >= 3)
    ents = xag_s[xag_us_mask_s]
    if len(ents) >= 5:
        rets = compute_returns_from_entries(xag_s, ents, 105)
        all_strategies.append(("XAG美盘RSI<18+CB>=3", "XAGUSD", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # JP225
    if "JP225" in all_data:
        jp_s = all_data["JP225"]
        jp_mask_s = (jp_s['session'] == 'us') & (jp_s.index.hour >= 15) & (jp_s.index.hour < 16) & (jp_s['rsi14'] < 14) & (jp_s['consecutive_bear'] >= 2)
        ents = jp_s[jp_mask_s]
        if len(ents) >= 5:
            rets = compute_returns_from_entries(jp_s, ents, 55)
            all_strategies.append(("JP225美盘RSI<14+CB>=2", "JP225", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # 双枪组合
    eu_rets_s = compute_returns_from_entries(xau_s, xau_s[eu_mask_s], 42) if len(xau_s[eu_mask_s]) >= 5 else np.array([])
    us_rets_s = compute_returns_from_entries(xau_s, xau_s[us_mask_s], 115) if len(xau_s[us_mask_s]) >= 5 else np.array([])
    if len(eu_rets_s) > 0 and len(us_rets_s) > 0:
        dual_all_s = np.concatenate([eu_rets_s, us_rets_s])
        all_strategies.append(("双枪组合(欧+美)", "XAUUSD", len(dual_all_s), np.mean(dual_all_s>0)*100, np.mean(dual_all_s), dual_all_s.std()))

# 排序
print(f"\n--- 所有策略实盘可行性排名 (round26更新) ---")
print(f"{'排名':<6} {'策略名称':<32} {'品种':<8} {'信号数':<7} {'WR':<7} {'avg%':<8} {'std%':<8} {'信号/月':<9} {'稳定性':<8}")
print(f"  {'-'*6} {'-'*32} {'-'*8} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*9} {'-'*8}")

months_of_data = 17.0

def feasibility_score(s):
    name, sym, n, wr, avg, std = s
    wr_score = wr * 0.40
    n_score = min(n / 50, 1) * 30
    signal_per_month = n / months_of_data
    freq_score = min(signal_per_month / 3, 1) * 15
    ret_score = min(max(avg * 20, 0), 15)
    return wr_score + n_score + freq_score + ret_score

all_strategies.sort(key=lambda s: -feasibility_score(s))

for i, (name, sym, n, wr, avg, std) in enumerate(all_strategies, 1):
    signal_per_month = n / months_of_data
    if n >= 30 and wr >= 80:
        stability = "✅ 稳定"
    elif n >= 20 and wr >= 80:
        stability = "⚠️ 偏少"
    elif n >= 20 and wr >= 75:
        stability = "⚠️ 波动"
    elif n >= 10:
        stability = "❌ 不足"
    else:
        stability = "❌ 极少"
    score = feasibility_score((name, sym, n, wr, avg, std))
    marker = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else ""))
    print(f"  {marker}{i:<3} {name:<32} {sym:<8} {n:<7} {wr:.1f}% {avg:+.3f}% {std:.3f}% {signal_per_month:.1f}/月 {stability:<8}")

if all_strategies:
    best = all_strategies[0]
    print(f"\n  🏆 实盘可行性第1名: {best[0]} ({best[1]})")
    print(f"     WR={best[3]:.1f}% n={best[2]} avg={best[4]:+.3f}%")

# ═══════════════════════════════════════════════════════════════
# 总结
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ROUND 26 — 完成")
print(f"Time: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 80)
