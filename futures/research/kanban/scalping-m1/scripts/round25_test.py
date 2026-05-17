#!/usr/bin/env python3
"""
Round 25 — 超短线研究循环
Testing priority hypotheses from round24 next_actions:
1. round25_001: JP225 RSI<14+CB>=2 跨周期稳定性验证 (P1/P2/P3)
2. round25_002: XAUUSD 双枪策略 vs 共振策略 对比
3. round25_003: XAGUSD 欧盘RSI<14+CB>=3 hold参数微调 (80-130精细扫描)
4. round25_004: EURUSD EU 9-11 RSI<14+CB>=3 深度挖掘
5. round25_005: 共振CB>=1 vs 欧盘XAG vs 双枪 — 实盘可行性排序
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# HELPERS (same as round24)
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
        hold_range = list(range(30, 131, 5))
    
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
    print(f"  {'条件':<50} {'信号数':<8} {'Hold':<6} {'胜率':<8} {'平均收益':<12}")
    print(f"  {'-'*50} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")
    for row in data:
        print(f"  {row[0]:<50} {row[1]:<8} {row[2]:<6} {row[3]:<8} {row[4]:<12}")

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
    """Bootstrap 95% CI for win rate."""
    n = len(rets)
    if n < 10:
        return None, None
    wr_dist = np.array([(np.random.choice(rets, n, replace=True) > 0).mean() * 100 for _ in range(n_iter)])
    return np.percentile(wr_dist, 2.5), np.percentile(wr_dist, 97.5)

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 80)
print("ROUND 25 — Scalping M1/M5 深度验证 + 策略对比"
      "")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=25, testing round25_001~005")
print("=" * 80)

# ── Load data ──
print(f"\n--- M5 Data Summary ---")
all_data = {}
for sym in ["XAUUSD", "XAGUSD", "JP225", "EURUSD", "US500", "US30"]:
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
# H1: JP225 RSI<14+CB>=2 跨周期稳定性验证 (P1/P2/P3)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H1: JP225 RSI<14+CB>=2 跨周期稳定性验证 (P1/P2/P3)")
print("=" * 80)
print("目标: round24发现JP225 US美盘RSI<14+CB>=2 WR=85.4% n=41 — 移植后关键跨周期验证")

if "JP225" in all_data:
    jp225 = all_data["JP225"]
    
    # US 15-16 RSI<14+CB>=2 (round24 best)
    us_mask_jp = (
        (jp225['session'] == 'us') &
        (jp225.index.hour >= 15) &
        (jp225.index.hour < 16) &
        (jp225['rsi14'] < 14) &
        (jp225['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(jp225, us_mask_jp,
                                "JP225 US 15-16 RSI<14+CB>=2 (round24最佳)",
                                hold_range=list(range(40, 81, 5)) + [85, 95, 105, 115])
    
    # Also test RSI<16+CB>=2 for comparison
    us_mask_jp2 = (
        (jp225['session'] == 'us') &
        (jp225.index.hour >= 15) &
        (jp225.index.hour < 16) &
        (jp225['rsi14'] < 16) &
        (jp225['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(jp225, us_mask_jp2,
                                "JP225 US 15-16 RSI<16+CB>=2 (稍宽松对比)",
                                hold_range=list(range(40, 81, 5)) + [85, 95, 105, 115])
    
    # Bootstrap confidence for the main strategy
    print(f"\n--- Bootstrap置信区间 ---")
    entries_jp = jp225[us_mask_jp].copy()
    best_hold_jp = 55  # from round24
    rets_jp = compute_returns_from_entries(jp225, entries_jp, best_hold_jp)
    if len(rets_jp) >= 10:
        ci_low, ci_high = bootstrap_confidence(rets_jp)
        print(f"  JP225 RSI<14+CB>=2 hold={best_hold_jp}: n={len(rets_jp)} WR={np.mean(rets_jp>0)*100:.1f}%")
        print(f"  Bootstrap 95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]")

# ═══════════════════════════════════════════════════════════════
# H2: XAUUSD 双枪策略 vs 共振策略 对比
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H2: XAUUSD 双枪策略 vs 共振策略 对比")
print("=" * 80)
print("目标: 双枪策略(欧盘+美盘组合WR=87.7%) vs 共振策略(XAU+XAG共振WR=95.5%)")
print("      哪个更优？能否合并？")

if "XAUUSD" in all_data and "XAGUSD" in all_data:
    xau_h2 = all_data["XAUUSD"]
    xag_h2 = all_data["XAGUSD"]
    
    # ─── 策略1: 双枪 (欧盘9-11 RSI<18+CB>=4, hold=42) ───
    mask_eu = (
        (xau_h2['session'] == 'europe') &
        (xau_h2.index.hour >= 9) &
        (xau_h2.index.hour < 11) &
        (xau_h2['rsi14'] < 18) &
        (xau_h2['consecutive_bear'] >= 4)
    )
    # 美盘15-16 RSI<20+CB>=2, hold=115
    mask_us_dual = (
        (xau_h2['session'] == 'us') &
        (xau_h2.index.hour >= 15) &
        (xau_h2.index.hour < 16) &
        (xau_h2['rsi14'] < 20) &
        (xau_h2['consecutive_bear'] >= 2)
    )
    
    entries_eu = xau_h2[mask_eu].copy()
    entries_us_dual = xau_h2[mask_us_dual].copy()
    
    eu_hold = 42
    us_hold = 115
    
    eu_rets = compute_returns_from_entries(xau_h2, entries_eu, eu_hold)
    us_rets = compute_returns_from_entries(xau_h2, entries_us_dual, us_hold)
    
    print(f"\n--- 策略A: 双枪策略 (欧盘+美盘) ---")
    print(f"  欧盘: n={len(eu_rets)} WR={np.mean(eu_rets>0)*100:.1f}% avg={np.mean(eu_rets):.3f}% hold={eu_hold}")
    print(f"  美盘: n={len(us_rets)} WR={np.mean(us_rets>0)*100:.1f}% avg={np.mean(us_rets):.3f}% hold={us_hold}")
    dual_all = np.concatenate([eu_rets, us_rets])
    print(f"  组合: n={len(dual_all)} WR={np.mean(dual_all>0)*100:.1f}% avg={np.mean(dual_all):.3f}%")
    
    # ─── 策略2: 共振策略 (XAU+XAG同时CB>=1) ───
    print(f"\n--- 策略B: 共振策略 (XAU+XAG同时CB>=1) ---")
    
    # 共振 — XAU和XAG同时满足美盘15-16 CB>=1
    # 将两个df对齐到相同的时间索引
    common_idx = xau_h2.index.intersection(xag_h2.index)
    xau_aligned = xau_h2.loc[common_idx]
    xag_aligned = xag_h2.loc[common_idx]
    
    # 美盘共振: US 15-16, 两者都CB>=1
    res_mask_us = (
        (xau_aligned['session'] == 'us') &
        (xau_aligned.index.hour >= 15) &
        (xau_aligned.index.hour < 16) &
        (xau_aligned['consecutive_bear'] >= 1) &
        (xag_aligned['consecutive_bear'] >= 1)
    )
    res_entries_xau = xau_aligned[res_mask_us].copy()
    res_entries_xag = xag_aligned[res_mask_us].copy()
    
    # 欧盘共振: EU 9-11, 两者都CB>=1
    res_mask_eu = (
        (xau_aligned['session'] == 'europe') &
        (xau_aligned.index.hour >= 9) &
        (xau_aligned.index.hour < 11) &
        (xau_aligned['consecutive_bear'] >= 1) &
        (xag_aligned['consecutive_bear'] >= 1)
    )
    res_entries_eu_xau = xau_aligned[res_mask_eu].copy()
    res_entries_eu_xag = xag_aligned[res_mask_eu].copy()
    
    print(f"\n  美盘共振 (US 15-16 CB>=1):")
    res_hold = 95  # from best_known
    for name, ents, sym in [("做多XAU", res_entries_xau, "XAU"), ("做多XAG", res_entries_xag, "XAG")]:
        if len(ents) >= 5:
            rets_res = compute_returns_from_entries(xau_aligned if sym == "XAU" else xag_aligned, ents, res_hold)
            print(f"    {name}: n={len(rets_res)} WR={np.mean(rets_res>0)*100:.1f}% avg={np.mean(rets_res):.3f}% hold={res_hold}")
        else:
            print(f"    {name}: n={len(ents)} — 样本不足")
    
    print(f"\n  欧盘共振 (EU 9-11 CB>=1):")
    res_hold_eu = 115  # from best_known
    for name, ents, sym in [("做多XAU", res_entries_eu_xau, "XAU"), ("做多XAG", res_entries_eu_xag, "XAG")]:
        if len(ents) >= 5:
            rets_res = compute_returns_from_entries(xau_aligned if sym == "XAU" else xag_aligned, ents, res_hold_eu)
            print(f"    {name}: n={len(rets_res)} WR={np.mean(rets_res>0)*100:.1f}% avg={np.mean(rets_res):.3f}% hold={res_hold_eu}")
        else:
            print(f"    {name}: n={len(ents)} — 样本不足")
    
    # ─── 策略3: 双枪+共振是否可叠加？ ───
    print(f"\n--- 策略C: 双枪+共振叠加分析 ---")
    
    # 检查双枪信号中，有多少是共振信号
    eu_dates_set = set(entries_eu.index.floor('D'))
    us_dual_dates_set = set(entries_us_dual.index.floor('D'))
    res_us_dates_set = set(res_entries_xau.index.floor('D'))
    res_eu_dates_set = set(res_entries_eu_xau.index.floor('D'))
    
    print(f"  双枪欧盘信号日期: {len(eu_dates_set)}")
    print(f"  双枪美盘信号日期: {len(us_dual_dates_set)}")
    print(f"  共振美盘信号日期: {len(res_us_dates_set)}")
    print(f"  共振欧盘信号日期: {len(res_eu_dates_set)}")
    
    overlap_eu_res = eu_dates_set & res_eu_dates_set
    overlap_us_res = us_dual_dates_set & res_us_dates_set
    print(f"  双枪欧盘∩共振欧盘: {len(overlap_eu_res)} 天 ({(len(overlap_eu_res)/len(eu_dates_set)*100 if eu_dates_set else 0):.1f}%)")
    print(f"  双枪美盘∩共振美盘: {len(overlap_us_res)} 天 ({(len(overlap_us_res)/len(us_dual_dates_set)*100 if us_dual_dates_set else 0):.1f}%)")
    
    # 双枪 + 共振是否互相排斥(即交易不同时刻)还是叠加？
    print(f"\n--- 策略ABCD对比表格 ---")
    comp_data = []
    
    # A: 双枪组合
    comp_data.append(("A: 双枪-欧盘 XAU", str(len(eu_rets)), str(eu_hold),
                      f"{np.mean(eu_rets>0)*100:.1f}%", f"{np.mean(eu_rets):.3f}%"))
    comp_data.append(("A: 双枪-美盘 XAU", str(len(us_rets)), str(us_hold),
                      f"{np.mean(us_rets>0)*100:.1f}%", f"{np.mean(us_rets):.3f}%"))
    comp_data.append(("A: 双枪-组合 XAU", str(len(dual_all)), "混合",
                      f"{np.mean(dual_all>0)*100:.1f}%", f"{np.mean(dual_all):.3f}%"))
    
    # B: 共振美盘 (XAU)
    if len(res_entries_xau) >= 5:
        rets_res_xau = compute_returns_from_entries(xau_aligned, res_entries_xau, res_hold)
        comp_data.append(("B: 共振美盘 XAU", str(len(rets_res_xau)), str(res_hold),
                          f"{np.mean(rets_res_xau>0)*100:.1f}%", f"{np.mean(rets_res_xau):.3f}%"))
    # B: 共振美盘 (XAG)
    if len(res_entries_xag) >= 5:
        rets_res_xag = compute_returns_from_entries(xag_aligned, res_entries_xag, res_hold)
        comp_data.append(("B: 共振美盘 XAG", str(len(rets_res_xag)), str(res_hold),
                          f"{np.mean(rets_res_xag>0)*100:.1f}%", f"{np.mean(rets_res_xag):.3f}%"))
    # B: 共振欧盘 (XAG)
    if len(res_entries_eu_xag) >= 5:
        rets_res_eu_xag = compute_returns_from_entries(xag_aligned, res_entries_eu_xag, res_hold_eu)
        comp_data.append(("B: 共振欧盘 XAG", str(len(rets_res_eu_xag)), str(res_hold_eu),
                          f"{np.mean(rets_res_eu_xag>0)*100:.1f}%", f"{np.mean(rets_res_eu_xag):.3f}%"))
    
    print_compact_comparison("双枪 vs 共振 完整对比", comp_data)

# ═══════════════════════════════════════════════════════════════
# H3: XAGUSD 欧盘RSI<14+CB>=3 hold参数微调 (80-130精细扫描)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H3: XAGUSD 欧盘RSI<14+CB>=3 hold参数微调 (80-130精细扫描)")
print("=" * 80)
print("目标: 当前hold=115(全周期最佳), 但P1最佳hold=105 — 需精细调优找出全局最优hold")

if "XAGUSD" in all_data:
    xag_h3 = all_data["XAGUSD"]
    
    # 欧盘9-11 RSI<14+CB>=3
    eu_mask_xag = (
        (xag_h3['session'] == 'europe') &
        (xag_h3.index.hour >= 9) &
        (xag_h3.index.hour < 11) &
        (xag_h3['rsi14'] < 14) &
        (xag_h3['consecutive_bear'] >= 3)
    )
    entries_xag_eu = xag_h3[eu_mask_xag].copy()
    print(f"\nXAG欧盘信号总数: {len(entries_xag_eu)}")
    
    if len(entries_xag_eu) >= 10:
        # 精细扫描 80-130 步长1
        hold_range_fine = list(range(80, 131))
        print(f"精细扫描 hold=80~130 (步长1, {len(hold_range_fine)}个值)...")
        
        results_fine = {}
        for hold in hold_range_fine:
            hits = 0
            total_pnl = 0.0
            count = 0
            for idx, row in entries_xag_eu.iterrows():
                entry_price = row['close']
                pos = xag_h3.index.get_loc(idx)
                if pos + hold < len(xag_h3):
                    exit_price = xag_h3.iloc[pos + hold]['close']
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
                results_fine[hold] = {'n': count, 'wr': wr, 'avg_ret': avg_ret}
        
        if results_fine:
            # 按WR排序
            sorted_by_wr = sorted(results_fine.items(), key=lambda x: x[1]['wr'], reverse=True)
            print(f"\n  Top-10 按胜率: hold | WR | n | avg")
            for hold, r in sorted_by_wr[:10]:
                print(f"    hold={hold:3d}: WR={r['wr']:.1f}% n={r['n']} avg={r['avg_ret']:.3f}%")
            
            # 按综合评分排序 (WR*0.6 + coverage*0.4)
            def combined_score(r):
                wr_score = r['wr'] * 0.6
                n_score = min(r['n'] / 40, 1) * 40  # 40 is max signals expected
                return wr_score + n_score
            
            sorted_by_combined = sorted(results_fine.items(), key=lambda x: combined_score(x[1]), reverse=True)
            print(f"\n  Top-10 按综合评分: hold | WR | n | avg | 评分")
            for hold, r in sorted_by_combined[:10]:
                score = combined_score(r)
                print(f"    hold={hold:3d}: WR={r['wr']:.1f}% n={r['n']} avg={r['avg_ret']:.3f}% score={score:.1f}")
            
            best_comb = sorted_by_combined[0]
            print(f"\n  🏆 综合最优: hold={best_comb[0]} WR={best_comb[1]['wr']:.1f}% n={best_comb[1]['n']} avg={best_comb[1]['avg_ret']:.3f}%")
            
            # 对比原来的hold=115
            if 115 in results_fine:
                r115 = results_fine[115]
                print(f"  当前(hold=115): WR={r115['wr']:.1f}% n={r115['n']} avg={r115['avg_ret']:.3f}%")
            
            # 找出WR>=80%的所有hold区间（稳定区）
            stable_holds = sorted([h for h, r in results_fine.items() if r['wr'] >= 80 and r['n'] >= 20])
            if stable_holds:
                print(f"\n  稳定区间(WR>=80%且n>=20): hold={min(stable_holds)}~{max(stable_holds)} ({len(stable_holds)}个值)")
                
                # 找出连续的最长区间
                from itertools import groupby
                ranges = []
                for k, g in groupby(enumerate(stable_holds), lambda x: x[0]-x[1]):
                    group = list(g)
                    ranges.append((group[0][1], group[-1][1]))
                longest = max(ranges, key=lambda r: r[1]-r[0])
                print(f"  最长连续稳定区间: hold={longest[0]}~{longest[1]} ({longest[1]-longest[0]+1}个值)")
        
        # 也测试CB>=2 宽松版，看是否有更好的稳定区间
        eu_mask_xag_cb2 = (
            (xag_h3['session'] == 'europe') &
            (xag_h3.index.hour >= 9) &
            (xag_h3.index.hour < 11) &
            (xag_h3['rsi14'] < 14) &
            (xag_h3['consecutive_bear'] >= 2)
        )
        entries_xag_eu_cb2 = xag_h3[eu_mask_xag_cb2].copy()
        print(f"\n\nXAG欧盘CB>=2 (宽松版) 信号总数: {len(entries_xag_eu_cb2)}")
        if len(entries_xag_eu_cb2) >= 10:
            results_fine_cb2 = {}
            for hold in hold_range_fine:
                hits = 0
                total_pnl = 0.0
                count = 0
                for idx, row in entries_xag_eu_cb2.iterrows():
                    entry_price = row['close']
                    pos = xag_h3.index.get_loc(idx)
                    if pos + hold < len(xag_h3):
                        exit_price = xag_h3.iloc[pos + hold]['close']
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
                    results_fine_cb2[hold] = {'n': count, 'wr': wr, 'avg_ret': avg_ret}
            
            if results_fine_cb2:
                sorted_cb2 = sorted(results_fine_cb2.items(), key=lambda x: combined_score(x[1]), reverse=True)
                print(f"\n  Top-5 按综合评分 (CB>=2):")
                for hold, r in sorted_cb2[:5]:
                    score = combined_score(r)
                    print(f"    hold={hold:3d}: WR={r['wr']:.1f}% n={r['n']} avg={r['avg_ret']:.3f}% score={score:.1f}")
                best_cb2 = sorted_cb2[0]
                print(f"  🏆 CB>=2最优: hold={best_cb2[0]} WR={best_cb2[1]['wr']:.1f}% n={best_cb2[1]['n']} avg={best_cb2[1]['avg_ret']:.3f}%")

# ═══════════════════════════════════════════════════════════════
# H4: EURUSD EU 9-11 RSI<14+CB>=3 深度挖掘
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H4: EURUSD EU 9-11 RSI<14+CB>=3 深度挖掘")
print("=" * 80)
print("目标: round24发现EURUSD EU 9-11 RSI<14+CB>=3 WR=75% n=28 — 是否值得继续投入研究？")

if "EURUSD" in all_data:
    eur_h4 = all_data["EURUSD"]
    
    # 原条件
    eu_mask_eur = (
        (eur_h4['session'] == 'europe') &
        (eur_h4.index.hour >= 9) &
        (eur_h4.index.hour < 11) &
        (eur_h4['rsi14'] < 14) &
        (eur_h4['consecutive_bear'] >= 3)
    )
    test_condition_with_periods(eur_h4, eu_mask_eur,
                                "EURUSD EU 9-11 RSI<14+CB>=3 (原条件)",
                                hold_range=[30, 35, 40, 45, 50, 55, 60, 70, 85, 100, 115],
                                min_signals=8)
    
    # 尝试更宽松的 RSI<16+CB>=2
    eu_mask_eur2 = (
        (eur_h4['session'] == 'europe') &
        (eur_h4.index.hour >= 9) &
        (eur_h4.index.hour < 11) &
        (eur_h4['rsi14'] < 16) &
        (eur_h4['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(eur_h4, eu_mask_eur2,
                                "EURUSD EU 9-11 RSI<16+CB>=2 (宽松版)",
                                hold_range=[30, 35, 40, 45, 50, 55, 60, 70, 85, 100, 115],
                                min_signals=8)
    
    # 尝试rsi<18+CB>=2 (XAU欧盘移植)
    eu_mask_eur3 = (
        (eur_h4['session'] == 'europe') &
        (eur_h4.index.hour >= 9) &
        (eur_h4.index.hour < 11) &
        (eur_h4['rsi14'] < 18) &
        (eur_h4['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(eur_h4, eu_mask_eur3,
                                "EURUSD EU 9-11 RSI<18+CB>=2 (XAU欧盘移植)",
                                hold_range=[30, 35, 40, 45, 50, 55, 60, 70, 85, 100, 115],
                                min_signals=8)
    
    # 尝试美盘时段
    us_mask_eur = (
        (eur_h4['session'] == 'us') &
        (eur_h4.index.hour >= 15) &
        (eur_h4.index.hour < 16) &
        (eur_h4['rsi14'] < 14) &
        (eur_h4['consecutive_bear'] >= 2)
    )
    test_condition_with_periods(eur_h4, us_mask_eur,
                                "EURUSD US 15-16 RSI<14+CB>=2 (美盘对比)",
                                hold_range=[30, 35, 40, 45, 50, 55, 60, 70, 85, 100, 115],
                                min_signals=8)
    
    # 汇总对比
    print(f"\n--- EURUSD 全部条件对比 ---")
    comp_eur = []
    for name, mask, h in [
        ("EU 9-11 RSI<14+CB>=3", eu_mask_eur, 45),
        ("EU 9-11 RSI<16+CB>=2", eu_mask_eur2, 45),
        ("EU 9-11 RSI<18+CB>=2", eu_mask_eur3, 40),
        ("US 15-16 RSI<14+CB>=2", us_mask_eur, 45),
    ]:
        n, wr, avg = get_stats(eur_h4, mask, h)
        if n >= 5:
            comp_eur.append((name, str(n), str(h), f"{wr:.1f}%", f"{avg:.3f}%"))
    print_compact_comparison("EURUSD 各条件对比", comp_eur)
    
    if comp_eur:
        best_eur = max(comp_eur, key=lambda r: float(r[3].strip('%')) * 0.6 + min(int(r[1]) / 30, 1) * 40)
        print(f"\n  🏆 EURUSD最佳: {best_eur[0]} WR={best_eur[3]} n={best_eur[1]}")
        if float(best_eur[3].strip('%')) >= 70 and int(best_eur[1]) >= 20:
            print(f"  ✅ 值得继续关注 — WR>=70%且n>=20")
        elif float(best_eur[3].strip('%')) >= 75:
            print(f"  ⚠️ 胜率不错但样本偏小 — 建议继续积累数据")
        else:
            print(f"  ❌ 不推荐 — 胜率或样本数不足")
    
    # 检查EURUSD是否有任何高胜率条件
    print(f"\n--- EURUSD 全面扫描更多条件 ---")
    from itertools import product
    
    rsi_thresholds = [12, 14, 16, 18, 20]
    cb_thresholds = [1, 2, 3]
    sessions = {
        'EU': (eur_h4['session'] == 'europe') & (eur_h4.index.hour >= 9) & (eur_h4.index.hour < 11),
        'US_early': (eur_h4.index.hour >= 13) & (eur_h4.index.hour < 15),
        'US_main': (eur_h4.index.hour >= 15) & (eur_h4.index.hour < 16),
        'US_late': (eur_h4.index.hour >= 16) & (eur_h4.index.hour < 18),
    }
    
    scan_results = []
    for (sess_name, sess_mask), rsi_val, cb_val in product(sessions.items(), rsi_thresholds, cb_thresholds):
        mask = sess_mask & (eur_h4['rsi14'] < rsi_val) & (eur_h4['consecutive_bear'] >= cb_val)
        n, wr, avg = get_stats(eur_h4, mask, 45)
        if n >= 10:
            scan_results.append((sess_name, rsi_val, cb_val, n, wr, avg))
    
    scan_results.sort(key=lambda x: -x[4])
    print(f"  全扫描结果 (n>=10, 按WR降序):")
    print(f"  {'时段':<12} {'RSI<':<5} {'CB>=':<4} {'n':<6} {'WR':<7} {'avg%':<8}")
    print(f"  {'-'*12} {'-'*5} {'-'*4} {'-'*6} {'-'*7} {'-'*8}")
    for sess, rsi, cb, n, wr, avg in scan_results[:20]:
        marker = "⭐" if wr >= 70 else ""
        print(f"  {sess:<12} <{rsi:<3} >={cb:<2} {n:<6} {wr:.1f}% {avg:+.3f}% {marker}")
    
    if any(r[4] >= 70 for r in scan_results):
        print(f"\n  发现WR>=70%的条件! 值得继续研究 ✅")
    else:
        print(f"\n  未发现WR>=70%的条件(样本>=10) — EURUSD超卖模式不适合 ❌")

# ═══════════════════════════════════════════════════════════════
# H5: 共振CB>=1 vs 欧盘XAG vs 双枪 — 实盘可行性排序
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("H5: 共振CB>=1 vs 欧盘XAG vs 双枪 — 实盘可行性排序")
print("=" * 80)
print("目标: 将所有BEST策略汇总对比, 从实盘角度(信号频率, 稳定性, 收益率)排序")

# 从state和已有数据汇总对比
all_strategies = []

# ── 策略1: 共振美盘XAU (XAUXAU_resonance_CB1) ──
if "XAUUSD" in all_data and "XAGUSD" in all_data:
    xau_h5 = all_data["XAUUSD"]
    xag_h5 = all_data["XAGUSD"]
    common_idx_h5 = xau_h5.index.intersection(xag_h5.index)
    xau_aligned_h5 = xau_h5.loc[common_idx_h5]
    xag_aligned_h5 = xag_h5.loc[common_idx_h5]
    
    # 共振美盘CB>=1
    res_us_mask_h5 = (
        (xau_aligned_h5['session'] == 'us') &
        (xau_aligned_h5.index.hour >= 15) &
        (xau_aligned_h5.index.hour < 16) &
        (xau_aligned_h5['consecutive_bear'] >= 1) &
        (xag_aligned_h5['consecutive_bear'] >= 1)
    )
    res_us_entries_xau = xau_aligned_h5[res_us_mask_h5].copy()
    if len(res_us_entries_xau) >= 5:
        rets_res_xau_h5 = compute_returns_from_entries(xau_aligned_h5, res_us_entries_xau, 95)
        all_strategies.append(("共振美盘做多XAU", "XAUUSD", len(rets_res_xau_h5),
                               np.mean(rets_res_xau_h5>0)*100, np.mean(rets_res_xau_h5), rets_res_xau_h5.std()))
    
    res_us_entries_xag = xag_aligned_h5[res_us_mask_h5].copy()
    if len(res_us_entries_xag) >= 5:
        rets_res_xag_h5 = compute_returns_from_entries(xag_aligned_h5, res_us_entries_xag, 95)
        all_strategies.append(("共振美盘做多XAG", "XAGUSD", len(rets_res_xag_h5),
                               np.mean(rets_res_xag_h5>0)*100, np.mean(rets_res_xag_h5), rets_res_xag_h5.std()))
    
    # 共振欧盘CB>=1
    res_eu_mask_h5 = (
        (xau_aligned_h5['session'] == 'europe') &
        (xau_aligned_h5.index.hour >= 9) &
        (xau_aligned_h5.index.hour < 11) &
        (xau_aligned_h5['consecutive_bear'] >= 1) &
        (xag_aligned_h5['consecutive_bear'] >= 1)
    )
    res_eu_entries_xag = xag_aligned_h5[res_eu_mask_h5].copy()
    if len(res_eu_entries_xag) >= 5:
        rets_res_eu_xag_h5 = compute_returns_from_entries(xag_aligned_h5, res_eu_entries_xag, 115)
        all_strategies.append(("共振欧盘做多XAG", "XAGUSD", len(rets_res_eu_xag_h5),
                               np.mean(rets_res_eu_xag_h5>0)*100, np.mean(rets_res_eu_xag_h5), rets_res_eu_xag_h5.std()))
    
    # ── 策略2: 双枪欧盘XAU ──
    mask_eu_h5 = (
        (xau_h5['session'] == 'europe') &
        (xau_h5.index.hour >= 9) &
        (xau_h5.index.hour < 11) &
        (xau_h5['rsi14'] < 18) &
        (xau_h5['consecutive_bear'] >= 4)
    )
    entries_eu_h5 = xau_h5[mask_eu_h5].copy()
    if len(entries_eu_h5) >= 5:
        rets_eu_h5 = compute_returns_from_entries(xau_h5, entries_eu_h5, 42)
        all_strategies.append(("双枪欧盘做多XAU", "XAUUSD", len(rets_eu_h5),
                               np.mean(rets_eu_h5>0)*100, np.mean(rets_eu_h5), rets_eu_h5.std()))
    
    # 双枪美盘XAU
    mask_us_h5 = (
        (xau_h5['session'] == 'us') &
        (xau_h5.index.hour >= 15) &
        (xau_h5.index.hour < 16) &
        (xau_h5['rsi14'] < 20) &
        (xau_h5['consecutive_bear'] >= 2)
    )
    entries_us_h5 = xau_h5[mask_us_h5].copy()
    if len(entries_us_h5) >= 5:
        rets_us_h5 = compute_returns_from_entries(xau_h5, entries_us_h5, 115)
        all_strategies.append(("双枪美盘做多XAU", "XAUUSD", len(rets_us_h5),
                               np.mean(rets_us_h5>0)*100, np.mean(rets_us_h5), rets_us_h5.std()))
    
    # 双枪组合
    dual_all_h5 = np.concatenate([rets_eu_h5, rets_us_h5]) if 'rets_eu_h5' in locals() and 'rets_us_h5' in locals() else np.array([])
    if len(dual_all_h5) >= 5:
        all_strategies.append(("双枪组合(欧+美)", "XAUUSD", len(dual_all_h5),
                               np.mean(dual_all_h5>0)*100, np.mean(dual_all_h5), dual_all_h5.std()))
    
    # ── 策略3: XAG欧盘RSI<14+CB>=3 ──
    xag_eu_mask_h5 = (
        (xag_h5['session'] == 'europe') &
        (xag_h5.index.hour >= 9) &
        (xag_h5.index.hour < 11) &
        (xag_h5['rsi14'] < 14) &
        (xag_h5['consecutive_bear'] >= 3)
    )
    xag_eu_entries_h5 = xag_h5[xag_eu_mask_h5].copy()
    if len(xag_eu_entries_h5) >= 5:
        rets_xag_eu_h5 = compute_returns_from_entries(xag_h5, xag_eu_entries_h5, 115)
        all_strategies.append(("XAG欧盘RSI<14+CB>=3", "XAGUSD", len(rets_xag_eu_h5),
                               np.mean(rets_xag_eu_h5>0)*100, np.mean(rets_xag_eu_h5), rets_xag_eu_h5.std()))
    
    # ── 策略4: XAG美盘RSI<18+CB>=3 (旧基准) ──
    xag_us_mask_h5 = (
        (xag_h5['session'] == 'us') &
        (xag_h5.index.hour >= 15) &
        (xag_h5.index.hour < 16) &
        (xag_h5['rsi14'] < 18) &
        (xag_h5['consecutive_bear'] >= 3)
    )
    xag_us_entries_h5 = xag_h5[xag_us_mask_h5].copy()
    if len(xag_us_entries_h5) >= 5:
        rets_xag_us_h5 = compute_returns_from_entries(xag_h5, xag_us_entries_h5, 105)
        all_strategies.append(("XAG美盘RSI<18+CB>=3", "XAGUSD", len(rets_xag_us_h5),
                               np.mean(rets_xag_us_h5>0)*100, np.mean(rets_xag_us_h5), rets_xag_us_h5.std()))
    
    # ── 策略5: JP225 RSI<14+CB>=2 ──
    if "JP225" in all_data:
        jp_h5 = all_data["JP225"]
        jp_mask_h5 = (
            (jp_h5['session'] == 'us') &
            (jp_h5.index.hour >= 15) &
            (jp_h5.index.hour < 16) &
            (jp_h5['rsi14'] < 14) &
            (jp_h5['consecutive_bear'] >= 2)
        )
        jp_entries_h5 = jp_h5[jp_mask_h5].copy()
        if len(jp_entries_h5) >= 5:
            rets_jp_h5 = compute_returns_from_entries(jp_h5, jp_entries_h5, 55)
            all_strategies.append(("JP225美盘RSI<14+CB>=2", "JP225", len(rets_jp_h5),
                                   np.mean(rets_jp_h5>0)*100, np.mean(rets_jp_h5), rets_jp_h5.std()))

# ── 排序 ──
print(f"\n--- 所有策略实盘可行性排名 ---")
print(f"{'排名':<6} {'策略名称':<28} {'品种':<8} {'信号数':<7} {'WR':<7} {'avg%':<8} {'std%':<8} {'信号/月':<9} {'稳定性':<8}")
print(f"  {'-'*6} {'-'*28} {'-'*8} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*9} {'-'*8}")

# 计算每月信号数 (数据跨度约17个月)
months_of_data = 17.0

# 按综合评分排序: WR*40 + n/50*30 + (1-std/avg)*15 + avg*10
def feasibility_score(s):
    name, sym, n, wr, avg, std = s
    wr_score = wr * 0.40
    n_score = min(n / 50, 1) * 30
    signal_per_month = n / months_of_data
    freq_score = min(signal_per_month / 3, 1) * 15  # 3 signals/month = 100%
    ret_score = min(max(avg * 20, 0), 15)  # cap at 15
    return wr_score + n_score + freq_score + ret_score

all_strategies.sort(key=lambda s: -feasibility_score(s))

for i, (name, sym, n, wr, avg, std) in enumerate(all_strategies, 1):
    signal_per_month = n / months_of_data
    # 粗估稳定性
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
    print(f"  {marker}{i:<3} {name:<28} {sym:<8} {n:<7} {wr:.1f}% {avg:+.3f}% {std:.3f}% {signal_per_month:.1f}/月 {stability:<8}")

if all_strategies:
    best = all_strategies[0]
    print(f"\n  🏆 实盘可行性第1名: {best[0]} ({best[1]})")
    print(f"     WR={best[3]:.1f}% n={best[2]} avg={best[4]:+.3f}%")
    
    # 推荐实盘观察清单
    print(f"\n--- 实盘观察清单 (可行性评分排序) ---")
    print(f"  Tier 1 (高优先):")
    tier1 = [(name, sym, n, wr, avg) for name, sym, n, wr, avg, std in all_strategies if wr >= 85 and n >= 25]
    for name, sym, n, wr, avg in tier1:
        print(f"    ⭐ {name:30s} | {sym:8s} | WR={wr:.1f}% n={n} avg={avg:+.3f}%")
    
    print(f"  Tier 2 (中优先):")
    tier2 = [(name, sym, n, wr, avg) for name, sym, n, wr, avg, std in all_strategies if wr >= 80 and n >= 15 and (name, sym, n, wr, avg) not in [(t[0], t[1], t[2], t[3], t[4]) for t in tier1]]
    for name, sym, n, wr, avg in tier2:
        print(f"    📌 {name:30s} | {sym:8s} | WR={wr:.1f}% n={n} avg={avg:+.3f}%")
    
    print(f"  Tier 3 (观察):")
    tier3 = [(name, sym, n, wr, avg) for name, sym, n, wr, avg, std in all_strategies if wr >= 75 and n >= 10 and (name, sym, n, wr, avg) not in [(t[0], t[1], t[2], t[3], t[4]) for t in tier1] and (name, sym, n, wr, avg) not in [(t[0], t[1], t[2], t[3], t[4]) for t in tier2]]
    for name, sym, n, wr, avg in tier3:
        print(f"    👁 {name:30s} | {sym:8s} | WR={wr:.1f}% n={n} avg={avg:+.3f}%")

# ═══════════════════════════════════════════════════════════════
# 总结
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ROUND 25 — 完成")
print(f"Time: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 80)
