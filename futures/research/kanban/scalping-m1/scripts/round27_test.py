#!/usr/bin/env python3
"""
Round 27 — 超短线研究循环
Testing priority hypotheses from round26 next_actions:
1. round27_001: 共振美盘→XAU深度验证 — hold精细扫描+更严格RSI阈值
2. round27_002: 双枪策略月度跟踪 — 继续监测近6月表现
3. round27_003: XAG美盘极端阈值β版 — RSI<14+CB>=4数据积累
4. round27_004: XAG欧盘hold=85最终确认 — hold=85正式切换后P2观察
5. round27_005: XAUUSD M1动量崩塌探索 — RSI快速崩溃+成交量激增
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# HELPERS (same as round24/25/26)
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
    df = df.copy()
    df['year_month'] = df.index.to_period('M')
    return df

def print_heatmap(results_dict, label="Hold×WR Heatmap"):
    """Print a compact heatmap showing WR for multiple holds and conditions."""
    print(f"\n  ** {label} **")
    conditions = list(results_dict.keys())
    holds = sorted(set(h for cond in conditions for h in results_dict[cond].keys()))
    if not holds:
        return
    # Header
    header = f"  {'条件':<30}"
    for h in holds:
        header += f" {h:>4}"
    header += " 最佳"
    print(header)
    print(f"  {'-'*30} {'-'*4*len(holds)} {'-'*8}")
    for cond in conditions:
        line = f"  {cond:<30}"
        best_wr, best_hold = 0, 0
        for h in holds:
            if h in results_dict[cond]:
                wr = results_dict[cond][h]['wr']
                n = results_dict[cond][h]['n']
                if n >= 5:
                    line += f" {wr:>3.0f}%"
                    if wr > best_wr and n >= 5:
                        best_wr = wr
                        best_hold = h
                else:
                    line += "  — "
            else:
                line += "  — "
        line += f"  hold={best_hold} WR={best_wr:.0f}%"
        print(line)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 80)
print("ROUND 27 — Scalping M1/M5 深度验证 + 新维度探索")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=27, testing round27_001~005")
print("=" * 80)

# ── Load M5 data ──
print(f"\n--- M5 Data Summary ---")
all_data_m5 = {}
for sym in ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]:
    raw = load_data("M5", symbols=[sym])
    if raw:
        df = compute_indicators(raw[sym])
        df = add_session_and_cb(df)
        all_data_m5[sym] = df
        print(f"  {sym:8s} M5: {len(df):>8} rows  [{df.index[0].date()} → {df.index[-1].date()}]  "
              f"Close={df['close'].iloc[-1]:.1f}  RSI={df['rsi14'].iloc[-1]:.1f}")
    else:
        print(f"  ⚠️  {sym}: data not available")

# ── Load M1 data (for H5) ──
print(f"\n--- M1 Data Summary ---")
all_data_m1 = {}
for sym in ["XAUUSD"]:
    raw = load_data("M1", symbols=[sym])
    if raw:
        df = compute_indicators(raw[sym])
        df = add_session_and_cb(df)
        all_data_m1[sym] = df
        print(f"  {sym:8s} M1: {len(df):>8} rows  [{df.index[0].date()} → {df.index[-1].date()}]  "
              f"Close={df['close'].iloc[-1]:.1f}  RSI={df['rsi14'].iloc[-1]:.1f}  ATR%={df['atr14_pct'].iloc[-1]:.3f}%")
    else:
        print(f"  ⚠️  {sym} M1: data not available")


# ═══════════════════════════════════════════════════════════════
# H1: 共振美盘→XAU 深度验证 — hold精细扫描+更严格RSI阈值
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H1: 共振美盘→XAU 深度验证 — hold精细扫描+RSI阈值探索")
print("=" * 80)
print("目标: round26确认共振美盘→XAU WR=91.7% n=36 hold=115, 跨周期稳定")
print("      现在进行hold=30~150精细扫描 + 更严格RSI阈值(<16, <14, <12)")
print("      条件: US 15-16 RSI<? + CB>=1 (XAU+XAG同时满足)")

if "XAUUSD" in all_data_m5 and "XAGUSD" in all_data_m5:
    xau_h1 = all_data_m5["XAUUSD"]
    xag_h1 = all_data_m5["XAGUSD"]
    common_idx = xau_h1.index.intersection(xag_h1.index)
    xau_aligned = xau_h1.loc[common_idx]
    xag_aligned = xag_h1.loc[common_idx]
    
    # ── H1a: hold精细扫描 (30~150 step=3) for RSI<18+CB>=1 ──
    print(f"\n--- H1a: hold精细扫描 RSI<18+CB>=1 ---")
    res_us_mask_r18 = (
        (xau_aligned['session'] == 'us') &
        (xau_aligned.index.hour >= 15) &
        (xau_aligned.index.hour < 16) &
        (xau_aligned['rsi14'] < 18) &
        (xau_aligned['consecutive_bear'] >= 1) &
        (xag_aligned['consecutive_bear'] >= 1)
    )
    fine_holds = list(range(30, 151, 3))
    test_condition_with_periods(xau_aligned, res_us_mask_r18,
                                "共振美盘→XAU US 15-16 RSI<18+CB>=1 (精细hold扫描)",
                                hold_range=fine_holds,
                                min_signals=8)
    
    # ── H1b: RSI更严格阈值探索 ──
    print(f"\n--- H1b: RSI更严格阈值探索 (hold扫描) ---")
    rsi_thresholds = [18, 16, 14, 12]
    heatmap_data = {}
    
    for rsi_th in rsi_thresholds:
        mask = (
            (xau_aligned['session'] == 'us') &
            (xau_aligned.index.hour >= 15) &
            (xau_aligned.index.hour < 16) &
            (xau_aligned['rsi14'] < rsi_th) &
            (xau_aligned['consecutive_bear'] >= 1) &
            (xag_aligned['consecutive_bear'] >= 1)
        )
        entries = xau_aligned[mask].copy()
        n_total = len(entries)
        label = f"RSI<{rsi_th}+CB>=1"
        print(f"  {label}: {n_total} signals")
        
        if n_total >= 5:
            results = {}
            for hold in range(30, 151, 5):
                hits, total_pnl, count = 0, 0.0, 0
                for idx, row in entries.iterrows():
                    pos = xau_aligned.index.get_loc(idx)
                    if pos + hold < len(xau_aligned):
                        exit_price = xau_aligned.iloc[pos + hold]['close']
                        pnl = (exit_price - row['close']) / row['close'] * 100
                        total_pnl += pnl
                        count += 1
                        if pnl > 0: hits += 1
                if count >= 5:
                    results[hold] = {'n': count, 'wr': hits/count*100, 'avg_ret': total_pnl/count}
            if results:
                best_hold = max(results, key=lambda h: results[h]['wr'] * 0.7 + min(results[h]['n'] / 200, 1) * 30)
                best = results[best_hold]
                print(f"    Best: hold={best_hold} WR={best['wr']:.1f}% n={best['n']} avg={best['avg_ret']:.3f}%")
                # Top 3
                top3 = sorted(results.items(), key=lambda x: x[1]['wr'], reverse=True)[:3]
                for h, r in top3:
                    print(f"      hold={h:3d}: WR={r['wr']:.1f}% n={r['n']} avg={r['avg_ret']:.3f}%")
                heatmap_data[label] = results
    
    # Print heatmap for key holds
    if heatmap_data:
        key_holds = [30, 45, 60, 75, 90, 105, 115, 120, 135, 150]
        print(f"\n--- 共振美盘 RSI阈值 Heatmap ---")
        print(f"  {'RSI阈值':<20}", end="")
        for h in key_holds:
            print(f" {h:>4}", end="")
        print(f" {'最佳':>10}")
        print(f"  {'-'*20} {'-'*4*len(key_holds)} {'-'*10}")
        for label, results in heatmap_data.items():
            line = f"  {label:<20}"
            best_wr, best_h = 0, 0
            for h in key_holds:
                if h in results and results[h]['n'] >= 5:
                    wr = results[h]['wr']
                    line += f" {wr:>3.0f}%"
                    if wr > best_wr:
                        best_wr = wr
                        best_h = h
                else:
                    line += "  — "
            line += f"  h={best_h} WR={best_wr:.0f}%"
            print(line)
    
    # ── H1c: Bootstrap CI for best config ──
    print(f"\n--- H1c: Bootstrap置信区间 (RSI<18+CB>=1 hold=115) ---")
    entries_best = xau_aligned[res_us_mask_r18].copy()
    if len(entries_best) >= 10:
        rets_best = compute_returns_from_entries(xau_aligned, entries_best, 115)
        ci_low, ci_high = bootstrap_confidence(rets_best)
        wr_actual = np.mean(rets_best > 0) * 100
        print(f"  n={len(rets_best)} WR={wr_actual:.1f}% avg={np.mean(rets_best):.3f}%")
        print(f"  Bootstrap 95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]")
        
        # Also do CI for hold=90, 105, 130
        for alt_hold in [90, 105, 130]:
            rets_alt = compute_returns_from_entries(xau_aligned, entries_best, alt_hold)
            if len(rets_alt) >= 10:
                ci_low_a, ci_high_a = bootstrap_confidence(rets_alt)
                wr_a = np.mean(rets_alt > 0) * 100
                print(f"  hold={alt_hold}: n={len(rets_alt)} WR={wr_a:.1f}% CI=[{ci_low_a:.1f}%, {ci_high_a:.1f}%]")
    
    # ── H1d: 对比双枪美盘 vs 共振美盘 ──
    print(f"\n--- H1d: 双枪美盘 vs 共振美盘 对比 ---")
    # 双枪美盘: US 15-16 RSI<20+CB>=2
    dual_us_mask = (
        (xau_aligned['session'] == 'us') &
        (xau_aligned.index.hour >= 15) &
        (xau_aligned.index.hour < 16) &
        (xau_aligned['rsi14'] < 20) &
        (xau_aligned['consecutive_bear'] >= 2)
    )
    # 共振美盘: US 15-16 RSI<18+CB>=1 (XAG共振)
    
    for name, mask, default_hold in [
        ("双枪美盘 RSI<20+CB>=2", dual_us_mask, 115),
        ("共振美盘 RSI<18+CB>=1 (XAG共振)", res_us_mask_r18, 115),
    ]:
        entries = xau_aligned[mask].copy()
        n_all = len(entries)
        if n_all >= 5:
            rets = compute_returns_from_entries(xau_aligned, entries, default_hold)
            wr = np.mean(rets > 0) * 100 if len(rets) > 0 else 0
            avg = np.mean(rets) if len(rets) > 0 else 0
            print(f"  {name}: n={n_all} hold={default_hold} WR={wr:.1f}% avg={avg:.3f}%")
            # Recent 6mo
            cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
            recent_entries = entries[entries.index >= cutoff]
            if len(recent_entries) >= 5:
                rets_rec = compute_returns_from_entries(xau_aligned, recent_entries, default_hold)
                wr_rec = np.mean(rets_rec > 0) * 100 if len(rets_rec) > 0 else 0
                print(f"   近6月: n={len(recent_entries)} WR={wr_rec:.1f}%")


# ═══════════════════════════════════════════════════════════════
# H2: 双枪策略月度跟踪
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H2: 双枪策略月度跟踪 — 继续监测近6月表现")
print("=" * 80)
print("目标: round26确认近6月双枪组合WR=88.4% n=43. 关注2026-03回撤(50%)是否周期性出现")
print("      双枪欧盘: EU 9-11 RSI<18+CB>=4 hold=42")
print("      双枪美盘: US 15-16 RSI<20+CB>=2 hold=115")

if "XAUUSD" in all_data_m5:
    xau_h2 = all_data_m5["XAUUSD"]
    
    recent_cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
    early_mask = xau_h2.index < recent_cutoff
    recent_mask = xau_h2.index >= recent_cutoff
    
    print(f"  数据分割点: {recent_cutoff.date()}")
    print(f"  早期: {early_mask.sum()} 行, 近期: {recent_mask.sum()} 行")
    
    # 双枪欧盘
    eu_mask_h2 = (
        (xau_h2['session'] == 'europe') &
        (xau_h2.index.hour >= 9) & (xau_h2.index.hour < 11) &
        (xau_h2['rsi14'] < 18) & (xau_h2['consecutive_bear'] >= 4)
    )
    # 双枪美盘
    us_mask_h2 = (
        (xau_h2['session'] == 'us') &
        (xau_h2.index.hour >= 15) & (xau_h2.index.hour < 16) &
        (xau_h2['rsi14'] < 20) & (xau_h2['consecutive_bear'] >= 2)
    )
    
    print(f"\n--- 双枪欧盘 hold=42 ---")
    for period_name, period_df in [("早期 (全历史-近6月)", xau_h2[early_mask]),
                                    ("近期 (近6月)", xau_h2[recent_mask])]:
        if len(period_df) < 1000:
            print(f"  {period_name}: 数据不足")
            continue
        period_mask = eu_mask_h2.reindex(period_df.index, fill_value=False)
        n, wr, avg = get_stats(period_df, period_mask, 42)
        print(f"  {period_name}: n={n} WR={wr:.1f}% avg={avg:.3f}%")
    
    print(f"\n--- 双枪美盘 hold=115 ---")
    for period_name, period_df in [("早期 (全历史-近6月)", xau_h2[early_mask]),
                                    ("近期 (近6月)", xau_h2[recent_mask])]:
        if len(period_df) < 1000:
            continue
        period_mask = us_mask_h2.reindex(period_df.index, fill_value=False)
        n, wr, avg = get_stats(period_df, period_mask, 115)
        print(f"  {period_name}: n={n} WR={wr:.1f}% avg={avg:.3f}%")
    
    # 分月跟踪 (近12月)
    print(f"\n--- 双枪策略 月度表现跟踪 (近12月) ---")
    xau_h2['month'] = xau_h2.index.to_period('M')
    recent_data = xau_h2[xau_h2.index >= (pd.Timestamp.now() - pd.DateOffset(months=12))]
    
    print(f"  {'月份':<10} {'欧盘信号':<8} {'欧盘WR':<8} {'美盘信号':<8} {'美盘WR':<8} {'组合信号':<8} {'组合WR':<8}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    
    for month, grp in recent_data.groupby('month'):
        grp_mask_eu = eu_mask_h2.reindex(grp.index, fill_value=False)
        grp_mask_us = us_mask_h2.reindex(grp.index, fill_value=False)
        n_eu, wr_eu, _ = get_stats(grp, grp_mask_eu, 42)
        n_us, wr_us, _ = get_stats(grp, grp_mask_us, 115)
        n_comb = n_eu + n_us
        if n_comb > 0:
            wr_comb = (wr_eu * n_eu + wr_us * n_us) / n_comb
        else:
            wr_comb = 0
        print(f"  {str(month):<10} {n_eu:<8} {wr_eu:.1f}%{'':>3} {n_us:<8} {wr_us:.1f}%{'':>3} {n_comb:<8} {wr_comb:.1f}%")
    
    # 近6月 vs 全历史汇总
    print(f"\n--- 双枪策略总结对比 ---")
    comp_h2 = []
    for name, mask, hold in [
        ("双枪欧盘 XAU (EU 9-11 RSI<18+CB>=4)", eu_mask_h2, 42),
        ("双枪美盘 XAU (US 15-16 RSI<20+CB>=2)", us_mask_h2, 115),
    ]:
        n_all, wr_all, avg_all = get_stats(xau_h2, mask, hold)
        n_recent, wr_recent, avg_recent = get_stats(xau_h2, mask & recent_mask, hold)
        comp_h2.append((f"{name} [全历史]", str(n_all), str(hold), f"{wr_all:.1f}%", f"{avg_all:.3f}%"))
        comp_h2.append((f"{name} [近6月]", str(n_recent), str(hold), f"{wr_recent:.1f}%", f"{avg_recent:.3f}%"))
    # 组合
    eu_all_rets = compute_returns_from_entries(xau_h2, xau_h2[eu_mask_h2], 42) if len(xau_h2[eu_mask_h2]) >= 5 else np.array([])
    us_all_rets = compute_returns_from_entries(xau_h2, xau_h2[us_mask_h2], 115) if len(xau_h2[us_mask_h2]) >= 5 else np.array([])
    if len(eu_all_rets) > 0 or len(us_all_rets) > 0:
        comb_all = np.concatenate([eu_all_rets, us_all_rets]) if len(eu_all_rets) > 0 and len(us_all_rets) > 0 else (eu_all_rets if len(eu_all_rets) > 0 else us_all_rets)
        eu_rec_rets = compute_returns_from_entries(xau_h2, xau_h2[eu_mask_h2 & recent_mask], 42) if len(xau_h2[eu_mask_h2 & recent_mask]) >= 5 else np.array([])
        us_rec_rets = compute_returns_from_entries(xau_h2, xau_h2[us_mask_h2 & recent_mask], 115) if len(xau_h2[us_mask_h2 & recent_mask]) >= 5 else np.array([])
        if len(eu_rec_rets) > 0 or len(us_rec_rets) > 0:
            comb_rec = np.concatenate([eu_rec_rets, us_rec_rets]) if len(eu_rec_rets) > 0 and len(us_rec_rets) > 0 else (eu_rec_rets if len(eu_rec_rets) > 0 else us_rec_rets)
            comp_h2.append(("双枪组合 [全历史]", str(len(comb_all)), "—", f"{np.mean(comb_all>0)*100:.1f}%", f"{np.mean(comb_all):.3f}%"))
            comp_h2.append(("双枪组合 [近6月]", str(len(comb_rec)), "—", f"{np.mean(comb_rec>0)*100:.1f}%", f"{np.mean(comb_rec):.3f}%"))
    print_compact_comparison("双枪策略 全历史 vs 近6月", comp_h2)
    
    # 检查2026-03回撤是否重现
    print(f"\n--- 2026-03回撤分析 ---")
    mar_data = xau_h2[(xau_h2.index.year == 2026) & (xau_h2.index.month == 3)]
    mar_eu = eu_mask_h2.reindex(mar_data.index, fill_value=False)
    mar_us = us_mask_h2.reindex(mar_data.index, fill_value=False)
    n_mar_eu, wr_mar_eu, _ = get_stats(mar_data, mar_eu, 42)
    n_mar_us, wr_mar_us, _ = get_stats(mar_data, mar_us, 115)
    print(f"  2026-03 欧盘: n={n_mar_eu} WR={wr_mar_eu:.1f}%")
    print(f"  2026-03 美盘: n={n_mar_us} WR={wr_mar_us:.1f}%")
    n_mar_comb = n_mar_eu + n_mar_us
    wr_mar_comb = (wr_mar_eu * n_mar_eu + wr_mar_us * n_mar_us) / n_mar_comb if n_mar_comb > 0 else 0
    print(f"  2026-03 组合: n={n_mar_comb} WR={wr_mar_comb:.1f}%")
    
    # 检查2026-04和2026-05是否恢复
    apr_data = xau_h2[(xau_h2.index.year == 2026) & (xau_h2.index.month == 4)]
    may_data = xau_h2[(xau_h2.index.year == 2026) & (xau_h2.index.month == 5)]
    for month_name, mdata in [("2026-04", apr_data), ("2026-05 (至今)", may_data)]:
        if len(mdata) > 0:
            me = eu_mask_h2.reindex(mdata.index, fill_value=False)
            mu = us_mask_h2.reindex(mdata.index, fill_value=False)
            ne, wre, _ = get_stats(mdata, me, 42)
            nu, wru, _ = get_stats(mdata, mu, 115)
            nc = ne + nu
            wrc = (wre * ne + wru * nu) / nc if nc > 0 else 0
            print(f"  {month_name}: 欧{n}={ne} WR={wre:.1f}% | 美{n}={nu} WR={wru:.1f}% | 组合{n}={nc} WR={wrc:.1f}%")


# ═══════════════════════════════════════════════════════════════
# H3: XAG美盘极端阈值β版 — 数据积累 (n≥20评估)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H3: XAG美盘极端阈值β版 — 数据积累等待n≥20")
print("=" * 80)
print("目标: round24发现极端阈值(RSI<14+CB>=4 91.7% n=12). 继续积累数据")
print("      看是否达到n≥20评估下限. 同时尝试更细分的hold扫描")

if "XAGUSD" in all_data_m5:
    xag_h3 = all_data_m5["XAGUSD"]
    
    extreme_conditions = [
        ("XAG US 15-16 RSI<14+CB>=4 (极端1)",
         (xag_h3['session'] == 'us') & (xag_h3.index.hour >= 15) & (xag_h3.index.hour < 16) &
         (xag_h3['rsi14'] < 14) & (xag_h3['consecutive_bear'] >= 4)),
        ("XAG US 15-16 RSI<16+CB>=5 (极端2)",
         (xag_h3['session'] == 'us') & (xag_h3.index.hour >= 15) & (xag_h3.index.hour < 16) &
         (xag_h3['rsi14'] < 16) & (xag_h3['consecutive_bear'] >= 5)),
        ("XAG US 15-16 RSI<14+CB>=5 (极端3)",
         (xag_h3['session'] == 'us') & (xag_h3.index.hour >= 15) & (xag_h3.index.hour < 16) &
         (xag_h3['rsi14'] < 14) & (xag_h3['consecutive_bear'] >= 5)),
        ("XAG US 15-16 RSI<12+CB>=3 (极端RSI)",
         (xag_h3['session'] == 'us') & (xag_h3.index.hour >= 15) & (xag_h3.index.hour < 16) &
         (xag_h3['rsi14'] < 12) & (xag_h3['consecutive_bear'] >= 3)),
        ("XAG US 14-16 RSI<14+CB>=4 (宽时段)",
         (xag_h3['session'] == 'us') & (xag_h3.index.hour >= 14) & (xag_h3.index.hour < 16) &
         (xag_h3['rsi14'] < 14) & (xag_h3['consecutive_bear'] >= 4)),
        ("XAG US 15-16 RSI<18+CB>=3 (旧基准)",
         (xag_h3['session'] == 'us') & (xag_h3.index.hour >= 15) & (xag_h3.index.hour < 16) &
         (xag_h3['rsi14'] < 18) & (xag_h3['consecutive_bear'] >= 3)),
    ]
    
    print(f"\n--- XAG美盘极端阈值扫描 (精细hold) ---")
    extreme_summary = []
    for name, mask in extreme_conditions:
        entries = xag_h3[mask].copy()
        print(f"\n  [{name}]")
        print(f"    信号数: {len(entries)}")
        if len(entries) >= 5:
            # 精细hold扫描 (75~135 step=5)
            best_n, best_wr, best_hold = 0, 0, 0
            all_res = []
            for hold in range(75, 141, 5):
                n, wr, avg = get_stats(xag_h3, mask, hold)
                if n >= 5:
                    all_res.append((hold, n, wr, avg))
                    if wr > best_wr:
                        best_wr, best_n, best_hold = wr, n, hold
            print(f"    Hold扫描 (75~140):")
            for h, n, wr, avg in sorted(all_res, key=lambda x: x[2], reverse=True)[:5]:
                print(f"      hold={h}: WR={wr:.1f}% n={n} avg={avg:.3f}%")
            if best_n >= 5:
                print(f"    → 最佳: hold={best_hold} WR={best_wr:.1f}% n={best_n}")
                extreme_summary.append((name, best_n, best_hold, best_wr))
                
                # 跨周期验证
                if best_n >= 10:
                    test_condition_with_periods(xag_h3, mask,
                                                f"XAG {name} (hold={best_hold})",
                                                hold_range=list(range(max(75, best_hold-15), min(141, best_hold+16), 5)),
                                                min_signals=5)
        else:
            print(f"    信号太少, 跳过")
    
    # 极端阈值汇总
    if extreme_summary:
        print(f"\n  ** XAG美盘极端阈值汇总 **")
        print(f"  {'条件':<45} {'n':<6} {'最佳hold':<10} {'最佳WR':<8}")
        print(f"  {'-'*45} {'-'*6} {'-'*10} {'-'*8}")
        for name, n, hold, wr in sorted(extreme_summary, key=lambda x: x[3], reverse=True):
            print(f"  {name:<45} {n:<6} {hold:<10} {wr:.1f}%")
    
    # 数据积累进度追踪
    print(f"\n--- 极端阈值数据积累进度 ---")
    print(f"  目标: n≥20 才能正式评估")
    for name, mask in extreme_conditions:
        n = len(xag_h3[mask])
        status = "✅ 已达标" if n >= 20 else (f"⚠️ 还需{20-n}条 ({n}/{20})" if n >= 10 else f"❌ 远不足 ({n}/20)")
        print(f"  {name:<45} n={n:<5} {status}")


# ═══════════════════════════════════════════════════════════════
# H4: XAG欧盘hold=85最终确认 — hold=85正式切换后观察
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H4: XAG欧盘hold=85最终确认 — hold=85正式切换后P2表现观察")
print("=" * 80)
print("目标: round26确认hold=85与115等价(均86.5%), hold=85在P2更优(85.7% vs 71.4%)")
print("      建议正式切换为hold=85. 检查更细粒度hold (75~100) 确认85是否最优")
print("      条件: EU 9-11 RSI<14+CB>=3")

if "XAGUSD" in all_data_m5:
    xag_h4 = all_data_m5["XAGUSD"]
    
    eu_mask_xag = (
        (xag_h4['session'] == 'europe') &
        (xag_h4.index.hour >= 9) & (xag_h4.index.hour < 11) &
        (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 3)
    )
    
    entries_xag_eu = xag_h4[eu_mask_xag].copy()
    print(f"  总信号数: {len(entries_xag_eu)}")
    
    if len(entries_xag_eu) >= 10:
        # ── H4a: 精细hold扫描 (75~100 step=2) ──
        print(f"\n  --- H4a: 精细hold扫描 (75~100) ---")
        fine_range = list(range(75, 101, 2))
        test_condition_with_periods(xag_h4, eu_mask_xag,
                                     "XAG EU 9-11 RSI<14+CB>=3 (精细hold)",
                                     hold_range=fine_range,
                                     min_signals=8)
        
        # ── H4b: hold=85 vs hold=95 vs hold=105 详细对比 ──
        print(f"\n  --- H4b: hold=85 vs 95 vs 105 逐周期对比 ---")
        
        dates = xag_h4.index.sort_values()
        n_idx = len(dates)
        split1 = dates[int(n_idx * 0.33)]
        split2 = dates[int(n_idx * 0.67)]
        periods = {
            'P1 (最早)': xag_h4[xag_h4.index < split1],
            'P2 (中段)': xag_h4[(xag_h4.index >= split1) & (xag_h4.index < split2)],
            'P3 (最近)': xag_h4[xag_h4.index >= split2],
        }
        
        print(f"  {'周期':<12} {'hold=85 WR':<12} {'hold=85 n':<10} {'hold=95 WR':<12} {'hold=95 n':<10} {'hold=105 WR':<13} {'hold=105 n':<10} {'最佳':<8}")
        print(f"  {'-'*12} {'-'*12} {'-'*10} {'-'*12} {'-'*10} {'-'*13} {'-'*10} {'-'*8}")
        
        for pname, pdf in periods.items():
            pmask = eu_mask_xag.reindex(pdf.index, fill_value=False)
            n85, wr85, _ = get_stats(pdf, pmask, 85)
            n95, wr95, _ = get_stats(pdf, pmask, 95)
            n105, wr105, _ = get_stats(pdf, pmask, 105)
            best_hold = max([(85, wr85), (95, wr95), (105, wr105)], key=lambda x: x[1])
            print(f"  {pname:<12} {wr85:.1f}%{'':>6} {n85:<10} {wr95:.1f}%{'':>6} {n95:<10} {wr105:.1f}%{'':>7} {n105:<10} hold={best_hold[0]} ✅")
        
        # 全周期
        n85_all, wr85_all, avg85_all = get_stats(xag_h4, eu_mask_xag, 85)
        n95_all, wr95_all, avg95_all = get_stats(xag_h4, eu_mask_xag, 95)
        n105_all, wr105_all, avg105_all = get_stats(xag_h4, eu_mask_xag, 105)
        best_all = max([(85, wr85_all), (95, wr95_all), (105, wr105_all)], key=lambda x: x[1])
        print(f"  {'全周期':<12} {wr85_all:.1f}%{'':>6} {n85_all:<10} {wr95_all:.1f}%{'':>6} {n95_all:<10} {wr105_all:.1f}%{'':>7} {n105_all:<10} hold={best_all[0]} ✅")
        
        # ── H4c: Bootstrap CI ──
        print(f"\n  --- H4c: Bootstrap置信区间 (hold=85 vs 95 vs 105) ---")
        rets85 = compute_returns_from_entries(xag_h4, entries_xag_eu, 85)
        rets95 = compute_returns_from_entries(xag_h4, entries_xag_eu, 95)
        rets105 = compute_returns_from_entries(xag_h4, entries_xag_eu, 105)
        for hold, rets in [(85, rets85), (95, rets95), (105, rets105)]:
            if len(rets) >= 10:
                ci_low, ci_high = bootstrap_confidence(rets)
                wr = np.mean(rets > 0) * 100
                print(f"    hold={hold}: n={len(rets)} WR={wr:.1f}% CI=[{ci_low:.1f}%, {ci_high:.1f}%] avg={np.mean(rets):.3f}%")


# ═══════════════════════════════════════════════════════════════
# H5: XAUUSD M1动量崩塌探索 — RSI快速崩溃+成交量激增
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H5: XAUUSD M1动量崩塌探索 — RSI快速崩溃+成交量激增")
print("=" * 80)
print("目标: 在M1框架下探索RSI快速崩溃(多根阴线RSI急速下降) + 成交量激增的短线反弹模式")
print("      M1数据覆盖约3.5个月(2026-01~2026-05), 探索后告知M1可用的数据范围")

if "XAUUSD" in all_data_m1:
    xau_m1 = all_data_m1["XAUUSD"]
    print(f"  M1数据范围: {xau_m1.index[0]} → {xau_m1.index[-1]}")
    print(f"  M1数据量: {len(xau_m1)} rows")
    
    # ── H5a: RSI快速崩溃 (RSI从>40跌到<20在N根K线内) ──
    print(f"\n  --- H5a: RSI快速崩溃 (RSI速降) ---")
    # 计算RSI变化率: 过去5根K线RSI下降>15
    xau_m1['rsi_change5'] = xau_m1['rsi14'].diff(5)
    
    # 条件: RSI<20 + 过去5根RSI下降>15 + 连续阴线>=2
    rsi_crash_mask = (
        (xau_m1['rsi14'] < 20) &
        (xau_m1['rsi_change5'] < -15) &
        (xau_m1['consecutive_bear'] >= 2)
    )
    print(f"    RSI速降条件 (RSI<20 + RSI5根降>15 + CB>=2):")
    test_condition(xau_m1, rsi_crash_mask,
                   "XAU M1 RSI速降 (RSI<20+ΔRSI<-15+CB>=2)",
                   hold_range=list(range(5, 61, 2)) + [72, 96, 120])
    
    # ── H5b: 成交量激增 (Tick Volume爆量) ──
    print(f"\n  --- H5b: 成交量激增 + RSI超卖 ---")
    # 成交量相比前20根均值
    xau_m1['vol_ma20'] = xau_m1['tick_volume'].rolling(20).mean()
    xau_m1['vol_ratio'] = xau_m1['tick_volume'] / xau_m1['vol_ma20']
    
    vol_surge_mask = (
        (xau_m1['rsi14'] < 25) &
        (xau_m1['vol_ratio'] > 2.0) &  # 成交量 > 2倍20期均值
        (xau_m1['consecutive_bear'] >= 1)
    )
    print(f"    成交量激增 (RSI<25 + Vol>2xMA20 + CB>=1):")
    test_condition(xau_m1, vol_surge_mask,
                   "XAU M1 成交量激增+RSI超卖",
                   hold_range=list(range(5, 61, 2)) + [72, 96, 120])
    
    # ── H5c: 组合条件 (崩溃+放量) ──
    print(f"\n  --- H5c: 动量崩塌综合 (RSI速降 + 放量) ---")
    combo_mask = (
        (xau_m1['rsi14'] < 20) &
        (xau_m1['rsi_change5'] < -15) &
        (xau_m1['vol_ratio'] > 1.5) &
        (xau_m1['consecutive_bear'] >= 1)
    )
    test_condition(xau_m1, combo_mask,
                   "XAU M1 动量崩塌 (RSI<20+ΔRSI<-15+Vol>1.5x+CB>=1)",
                   hold_range=list(range(5, 61, 2)) + [72, 96, 120])
    # Bootstrap
    entries_combo = xau_m1[combo_mask].copy()
    if len(entries_combo) >= 10:
        rets_combo = compute_returns_from_entries(xau_m1, entries_combo, 30)
        if len(rets_combo) >= 10:
            ci_low, ci_high = bootstrap_confidence(rets_combo)
            print(f"    Bootstrap hold=30: n={len(rets_combo)} WR={np.mean(rets_combo>0)*100:.1f}% CI=[{ci_low:.1f}%, {ci_high:.1f}%]")
    
    # ── H5d: M1欧盘/美盘时段 + RSI<18 (仿M5双枪) ──
    print(f"\n  --- H5d: M1时段+RSI超卖 (仿M5双枪) ---")
    # 欧盘 M1
    m1_eu_mask = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 9) & (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 16) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    test_condition(xau_m1, m1_eu_mask,
                   "XAU M1 EU 9-11 RSI<16+CB>=3",
                   hold_range=list(range(5, 61, 2)) + [72, 96, 120, 144])
    
    # 美盘 M1
    m1_us_mask = (
        (xau_m1['session'] == 'us') &
        (xau_m1.index.hour >= 15) & (xau_m1.index.hour < 16) &
        (xau_m1['rsi14'] < 18) &
        (xau_m1['consecutive_bear'] >= 2)
    )
    test_condition(xau_m1, m1_us_mask,
                   "XAU M1 US 15-16 RSI<18+CB>=2",
                   hold_range=list(range(5, 61, 2)) + [72, 96, 120, 144])
    
    # ── H5e: 汇总对比 ──
    print(f"\n  --- H5e: M1各策略汇总对比 ---")
    comp_m1 = []
    for name, mask, hold in [
        ("RSI速降 (RSI<20+ΔRSI<-15+CB>=2)", rsi_crash_mask, 30),
        ("成交量激增 (RSI<25+Vol>2x+CB>=1)", vol_surge_mask, 20),
        ("动量崩塌综合 (组合条件)", combo_mask, 30),
        ("M1 EU 9-11 RSI<16+CB>=3", m1_eu_mask, 24),
        ("M1 US 15-16 RSI<18+CB>=2", m1_us_mask, 48),
    ]:
        n, wr, avg = get_stats(xau_m1, mask, hold)
        if n >= 5:
            comp_m1.append((name, str(n), str(hold), f"{wr:.1f}%", f"{avg:.3f}%"))
    if comp_m1:
        print_compact_comparison("XAU M1 策略探索", comp_m1)
        best_m1 = max(comp_m1, key=lambda r: float(r[3].strip('%')) * 0.5 + min(int(r[1]) / 20, 1) * 50)
        print(f"\n  🏆 M1最佳: {best_m1[0]} WR={best_m1[3]} n={best_m1[1]} hold={best_m1[2]}")
    
    # 数据可用性告知
    print(f"\n  ** M1数据可用性 **")
    print(f"  XAUUSD M1: {len(xau_m1)} rows, {xau_m1.index[0]} → {xau_m1.index[-1]}")
    print(f"  覆盖约{(xau_m1.index[-1] - xau_m1.index[0]).days}天")
    print(f"  注意: M1数据量虽大但时间跨度较短(仅3.5月), 跨周期验证受限")


# ═══════════════════════════════════════════════════════════════
# 全策略可行性对比 (更新round27)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("全策略可行性对比 (round27更新)")
print("=" * 80)

all_strategies = []

if "XAUUSD" in all_data_m5 and "XAGUSD" in all_data_m5:
    xau_s = all_data_m5["XAUUSD"]
    xag_s = all_data_m5["XAGUSD"]
    common_s = xau_s.index.intersection(xag_s.index)
    xau_aligned_s = xau_s.loc[common_s]
    xag_aligned_s = xag_s.loc[common_s]
    
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
    
    # 双枪组合
    eu_rets_s = compute_returns_from_entries(xau_s, xau_s[eu_mask_s], 42) if len(xau_s[eu_mask_s]) >= 5 else np.array([])
    us_rets_s = compute_returns_from_entries(xau_s, xau_s[us_mask_s], 115) if len(xau_s[us_mask_s]) >= 5 else np.array([])
    if len(eu_rets_s) > 0 and len(us_rets_s) > 0:
        dual_all_s = np.concatenate([eu_rets_s, us_rets_s])
        all_strategies.append(("双枪组合(欧+美)", "XAUUSD", len(dual_all_s), np.mean(dual_all_s>0)*100, np.mean(dual_all_s), dual_all_s.std()))
    
    # 共振美盘→XAU (RSI<18+CB>=1 hold=115)
    res_us_xau_mask_s = (
        (xau_aligned_s['session'] == 'us') & (xau_aligned_s.index.hour >= 15) & (xau_aligned_s.index.hour < 16) &
        (xau_aligned_s['rsi14'] < 18) & (xau_aligned_s['consecutive_bear'] >= 1) & (xag_aligned_s['consecutive_bear'] >= 1)
    )
    ents = xau_aligned_s[res_us_xau_mask_s]
    if len(ents) >= 5:
        rets = compute_returns_from_entries(xau_aligned_s, ents, 115)
        all_strategies.append(("共振美盘→XAU RSI<18+CB>=1", "XAUUSD", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # XAG欧盘
    xag_eu_mask_s = (xag_s['session'] == 'europe') & (xag_s.index.hour >= 9) & (xag_s.index.hour < 11) & (xag_s['rsi14'] < 14) & (xag_s['consecutive_bear'] >= 3)
    ents = xag_s[xag_eu_mask_s]
    if len(ents) >= 5:
        rets = compute_returns_from_entries(xag_s, ents, 85)
        all_strategies.append(("XAG欧盘RSI<14+CB>=3 hold=85★", "XAGUSD", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # XAG美盘
    xag_us_mask_s = (xag_s['session'] == 'us') & (xag_s.index.hour >= 15) & (xag_s.index.hour < 16) & (xag_s['rsi14'] < 18) & (xag_s['consecutive_bear'] >= 3)
    ents = xag_s[xag_us_mask_s]
    if len(ents) >= 5:
        rets = compute_returns_from_entries(xag_s, ents, 105)
        all_strategies.append(("XAG美盘RSI<18+CB>=3", "XAGUSD", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))
    
    # JP225
    if "JP225" in all_data_m5:
        jp_s = all_data_m5["JP225"]
        jp_mask_s = (jp_s['session'] == 'us') & (jp_s.index.hour >= 15) & (jp_s.index.hour < 16) & (jp_s['rsi14'] < 14) & (jp_s['consecutive_bear'] >= 2)
        ents = jp_s[jp_mask_s]
        if len(ents) >= 5:
            rets = compute_returns_from_entries(jp_s, ents, 55)
            all_strategies.append(("JP225美盘RSI<14+CB>=2", "JP225", len(rets), np.mean(rets>0)*100, np.mean(rets), rets.std()))

# 排序
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

print(f"\n--- 所有策略实盘可行性排名 (round27更新) ---")
print(f"{'排名':<6} {'策略名称':<32} {'品种':<8} {'信号数':<7} {'WR':<7} {'avg%':<8} {'std%':<8} {'信号/月':<9} {'稳定性':<8}")
print(f"  {'-'*6} {'-'*32} {'-'*8} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*9} {'-'*8}")

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
    marker = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else ""))
    print(f"  {marker}{i:<3} {name:<32} {sym:<8} {n:<7} {wr:.1f}% {avg:+.3f}% {std:.3f}% {signal_per_month:.1f}/月 {stability:<8}")

if all_strategies:
    best = all_strategies[0]
    print(f"\n  🏆 实盘可行性第1名: {best[0]} ({best[1]})")
    print(f"     WR={best[3]:.1f}% n={best[2]} avg={best[4]:+.3f}%")

# ═══════════════════════════════════════════════════════════════
# 总结 & 下一轮建议
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ROUND 27 — 完成")
print(f"Time: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 80)
