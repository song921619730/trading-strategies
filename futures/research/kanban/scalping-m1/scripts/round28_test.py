#!/usr/bin/env python3
"""
Round 28 — 超短线研究循环
Testing priority hypotheses from round27 next_actions:
1. round28_001: M1 EU仿双枪验证 — 更多M1数据积累后复查跨周期稳定性
2. round28_002: 共振美盘→XAU vs 双枪美盘互补策略 — 组合调度优化
3. round28_003: 双枪策略继续月度跟踪 — 近6月表现监测
4. round28_004: XAG美盘极端阈值持续积累 — RSI<14+CB>=4 数据积累
5. round28_005: XAUUSD H1/M30框架探索 (概念探索, 用M5数据模拟)
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# HELPERS (consistent with round24-27)
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

def print_compact_comparison(title, data):
    print(f"\n  ** {title} **")
    print(f"  {'条件':<55} {'信号数':<8} {'Hold':<6} {'胜率':<8} {'平均收益':<12}")
    print(f"  {'-'*55} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")
    for row in data:
        print(f"  {row[0]:<55} {row[1]:<8} {row[2]:<6} {row[3]:<8} {row[4]:<12}")

def get_monthly_stats(df, mask, hold):
    """月度统计 helper"""
    df = df.copy()
    entries = df[mask]
    monthly = {}
    for idx, row in entries.iterrows():
        month = row.name.to_period('M')
        pos = df.index.get_loc(idx)
        if pos + hold < len(df):
            pnl = (df.iloc[pos + hold]['close'] - row['close']) / row['close'] * 100
            if month not in monthly:
                monthly[month] = {'n': 0, 'hits': 0, 'total_pnl': 0.0}
            monthly[month]['n'] += 1
            monthly[month]['total_pnl'] += pnl
            if pnl > 0:
                monthly[month]['hits'] += 1
    return monthly


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 90)
print("ROUND 28 — Scalping M1/M5 组合调度优化 + 数据积累")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=28, testing round28_001~005")
print("=" * 90)

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

# ── Load M1 data (for H1) ──
print(f"\n--- M1 Data Summary ---")
all_data_m1 = {}
for sym in ["XAUUSD", "XAGUSD"]:
    raw = load_data("M1", symbols=[sym])
    if raw:
        df = compute_indicators(raw[sym])
        df = add_session_and_cb(df)
        all_data_m1[sym] = df
        print(f"  {sym:8s} M1: {len(df):>8} rows  [{df.index[0].date()} → {df.index[-1].date()}]  "
              f"Close={df['close'].iloc[-1]:.1f}  RSI={df['rsi14'].iloc[-1]:.1f}")
    else:
        print(f"  ⚠️  {sym} M1: data not available")


# ═══════════════════════════════════════════════════════════════
# H1: M1 EU 仿双枪验证 — 跨周期稳定性验证 (round28_001)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("H1: M1 EU 仿双枪验证 — 跨周期稳定性验证 (round28_001)")
print("=" * 90)
print("目标: Round27 发现 M1 EU 9-11 RSI<16+CB>=3 WR=85.2% n=54 hold=24")
print("      但数据仅104天(2026-01~2026-05), 无法做跨周期P1/P2/P3验证")
print("      现在复查M1数据积累情况, 如果已增长则进行跨周期验证")
print("      条件: M1 EU 9-11 RSI<16+CB>=3")

if "XAUUSD" in all_data_m1:
    xau_m1 = all_data_m1["XAUUSD"]
    m1_days = (xau_m1.index[-1] - xau_m1.index[0]).days
    print(f"  M1 XAUUSD 数据覆盖: {m1_days} 天 [{xau_m1.index[0].date()} → {xau_m1.index[-1].date()}]")
    
    eu_mask_m1 = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 9) & (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 16) &
        (xau_m1['consecutive_bear'] >= 3)
    )
    
    # M1 hold_range: 5~60 (minutes)
    m1_hold_range = list(range(5, 66, 2))
    
    if m1_days >= 180:
        # Enough data for proper P1/P2/P3 split
        print(f"  ✅ M1数据已覆盖{m1_days}天, 可以进行跨周期验证!")
        test_condition_with_periods(xau_m1, eu_mask_m1,
                                    f"M1 EU 9-11 RSI<16+CB>=3 (hold={m1_hold_range})",
                                    hold_range=m1_hold_range,
                                    min_signals=15)
    else:
        print(f"  ⚠️  M1数据仅覆盖{m1_days}天 (不足180天), 仍不满足跨周期验证条件")
        print(f"  🔄 距满足条件还需至少{180-m1_days}天数据积累")
        # Still run normal test for comparison with round27
        test_condition(xau_m1, eu_mask_m1,
                       f"M1 EU 9-11 RSI<16+CB>=3 (状态追踪)",
                       hold_range=m1_hold_range)
    
    # Also try broader condition: RSI<18+CB>=2 (more signals, potentially stable)
    print(f"\n--- M1 EU 拓宽条件探索: RSI<18+CB>=2 ---")
    eu_mask_m1_broad = (
        (xau_m1['session'] == 'europe') &
        (xau_m1.index.hour >= 9) & (xau_m1.index.hour < 11) &
        (xau_m1['rsi14'] < 18) &
        (xau_m1['consecutive_bear'] >= 2)
    )
    test_condition(xau_m1, eu_mask_m1_broad,
                   f"M1 EU 9-11 RSI<18+CB>=2 (拓宽条件)",
                   hold_range=m1_hold_range)

    # M1 US version for comparison
    print(f"\n--- M1 US 仿共振: RSI<18+CB>=1 ---")
    us_mask_m1 = (
        (xau_m1['session'] == 'us') &
        (xau_m1.index.hour >= 15) & (xau_m1.index.hour < 16) &
        (xau_m1['rsi14'] < 18) &
        (xau_m1['consecutive_bear'] >= 1)
    )
    test_condition(xau_m1, us_mask_m1,
                   f"M1 US 15-16 RSI<18+CB>=1 (美盘M1探索)",
                   hold_range=m1_hold_range)

else:
    print("  ⚠️  XAUUSD M1 data not available, skipping H1")


# ═══════════════════════════════════════════════════════════════
# H2: 共振美盘→XAU vs 双枪美盘 互补策略 (round28_002)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("H2: 共振美盘→XAU vs 双枪美盘 互补策略 (round28_002)")
print("=" * 90)
print("目标: 共振美盘WR=91.7% n=36 (2.1/月) vs 双枪美盘WR=87.1% n=62 (3.6/月)")
print("      探索组合调度优化: 高胜率共振优先, 次优选双枪")

if "XAUUSD" in all_data_m5:
    xau_h2 = all_data_m5["XAUUSD"]
    
    # Define conditions
    # 共振美盘: US 15-16 RSI<18+CB>=1 (XAG共振)
    # Need XAG data
    if "XAGUSD" in all_data_m5:
        xag_h2 = all_data_m5["XAGUSD"]
        common_idx = xau_h2.index.intersection(xag_h2.index)
        xau_h2_align = xau_h2.loc[common_idx]
        xag_h2_align = xag_h2.loc[common_idx]
        
        res_mask = (
            (xau_h2_align['session'] == 'us') &
            (xau_h2_align.index.hour >= 15) & (xau_h2_align.index.hour < 16) &
            (xau_h2_align['rsi14'] < 18) &
            (xau_h2_align['consecutive_bear'] >= 1) &
            (xag_h2_align['consecutive_bear'] >= 1)
        )
        xau_for_res = xau_h2_align
    else:
        res_mask = (
            (xau_h2['session'] == 'us') &
            (xau_h2.index.hour >= 15) & (xau_h2.index.hour < 16) &
            (xau_h2['rsi14'] < 18) &
            (xau_h2['consecutive_bear'] >= 1)
        )
        xau_for_res = xau_h2
    
    # 双枪美盘: US 15-16 RSI<20+CB>=2
    dual_us_mask = (
        (xau_h2['session'] == 'us') &
        (xau_h2.index.hour >= 15) & (xau_h2.index.hour < 16) &
        (xau_h2['rsi14'] < 20) &
        (xau_h2['consecutive_bear'] >= 2)
    )
    
    # 双枪欧盘: EU 9-11 RSI<18+CB>=4
    dual_eu_mask = (
        (xau_h2['session'] == 'europe') &
        (xau_h2.index.hour >= 9) & (xau_h2.index.hour < 11) &
        (xau_h2['rsi14'] < 18) &
        (xau_h2['consecutive_bear'] >= 4)
    )
    
    # ── H2a: 共振 vs 双枪 详细对比 ──
    print(f"\n--- H2a: 共振美盘 vs 双枪美盘 详细对比 ---")
    
    # Use xau_for_res if available
    e1_res = xau_for_res[res_mask] if 'xau_for_res' in dir() else xau_h2[res_mask]
    e2_dual = xau_h2[dual_us_mask]
    
    hold_test = 115
    recent_cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
    
    comp_data = []
    for name, entries, src_df in [
        ("共振美盘 RSI<18+CB>=1 (XAG共振)", e1_res, xau_for_res if 'xau_for_res' in dir() else xau_h2),
        ("双枪美盘 RSI<20+CB>=2", e2_dual, xau_h2),
    ]:
        n_all = len(entries)
        if n_all >= 5:
            rets = compute_returns_from_entries(src_df, entries, hold_test)
            wr_all = np.mean(rets > 0) * 100 if len(rets) > 0 else 0
            avg_all = np.mean(rets) if len(rets) > 0 else 0
            print(f"  {name}: 全历史 n={n_all} hold={hold_test} WR={wr_all:.1f}% avg={avg_all:.3f}%")
            
            recent_entries = entries[entries.index >= recent_cutoff]
            if len(recent_entries) >= 5:
                rets_rec = compute_returns_from_entries(src_df, recent_entries, hold_test)
                wr_rec = np.mean(rets_rec > 0) * 100
                print(f"    近6月({recent_cutoff.date()}~): n={len(recent_entries)} WR={wr_rec:.1f}%")
            
            # 信号频率
            months_covered = max(1, (entries.index[-1] - entries.index[0]).days / 30)
            freq = n_all / months_covered
            print(f"    信号频率: {freq:.1f}/月")
            comp_data.append((name, n_all, hold_test, wr_all, avg_all, freq))
    
    # ── H2b: 组合策略模拟 (共振优先, 双枪补充) ──
    print(f"\n--- H2b: 组合策略模拟 (共振优先, 双枪补充) ---")
    
    if 'xau_for_res' in dir() and len(e1_res) >= 5 and len(e2_dual) >= 5:
        # 共振条件信号 (优先)
        res_rets = compute_returns_from_entries(xau_for_res, e1_res, hold_test)
        # 双枪中非共振的信号 (排除已共振的)
        dual_excl = e2_dual[~e2_dual.index.isin(e1_res.index)]
        dual_excl_rets = compute_returns_from_entries(xau_h2, dual_excl, hold_test)
        
        # 组合
        if len(dual_excl_rets) > 0:
            combo_rets = np.concatenate([res_rets, dual_excl_rets])
            combo_wr = np.mean(combo_rets > 0) * 100
            combo_n = len(combo_rets)
            combo_avg = np.mean(combo_rets)
            res_wr = np.mean(res_rets > 0) * 100
            dual_excl_wr = np.mean(dual_excl_rets > 0) * 100
            
            print(f"  共振美盘 (优先):       n={len(res_rets)} WR={res_wr:.1f}% avg={np.mean(res_rets):.3f}%")
            print(f"  双枪美盘 (补充信号):   n={len(dual_excl_rets)} WR={dual_excl_wr:.1f}% avg={np.mean(dual_excl_rets):.3f}%")
            print(f"  ├── 非共振信号数量: {len(dual_excl_rets)}/{len(e2_dual)} ({len(dual_excl_rets)/len(e2_dual)*100:.0f}%)")
            print(f"  └── 重复信号(共振∩双枪): {len(e2_dual) - len(dual_excl_rets)}")
            print(f"  组合策略 (共振优先+双枪补充): n={combo_n} WR={combo_wr:.1f}% avg={combo_avg:.3f}%")
            print(f"  信号频率: {combo_n / max(1, (xau_h2.index[-1] - xau_h2.index[0]).days / 30):.1f}/月")
            
            # 近6月组合
            rec_res = e1_res[e1_res.index >= recent_cutoff]
            rec_dual = dual_excl[dual_excl.index >= recent_cutoff]
            if len(rec_res) >= 3 or len(rec_dual) >= 3:
                rec_rets_res = compute_returns_from_entries(xau_for_res, rec_res, hold_test) if len(rec_res) >= 3 else np.array([])
                rec_rets_dual = compute_returns_from_entries(xau_h2, rec_dual, hold_test) if len(rec_dual) >= 3 else np.array([])
                all_rec = np.concatenate([r for r in [rec_rets_res, rec_rets_dual] if len(r) > 0])
                if len(all_rec) > 0:
                    rec_wr = np.mean(all_rec > 0) * 100
                    print(f"  近6月组合: n={len(all_rec)} WR={rec_wr:.1f}%")
        else:
            print(f"  所有双枪信号都被共振包含, 无需优化")
    
    # ── H2c: 双枪欧盘 vs 共振欧盘 (if applicable) ──
    print(f"\n--- H2c: 双枪欧盘 hold=42 状态 ---")
    eu_entries = xau_h2[dual_eu_mask]
    if len(eu_entries) >= 5:
        eu_rets = compute_returns_from_entries(xau_h2, eu_entries, 42)
        eu_wr = np.mean(eu_rets > 0) * 100
        eu_avg = np.mean(eu_rets)
        print(f"  双枪欧盘: n={len(eu_entries)} hold=42 WR={eu_wr:.1f}% avg={eu_avg:.3f}%")
        rec_eu = eu_entries[eu_entries.index >= recent_cutoff]
        if len(rec_eu) >= 5:
            rec_eu_rets = compute_returns_from_entries(xau_h2, rec_eu, 42)
            rec_eu_wr = np.mean(rec_eu_rets > 0) * 100
            print(f"  近6月: n={len(rec_eu)} WR={rec_eu_wr:.1f}%")
    else:
        print(f"  双枪欧盘信号不足 ({len(eu_entries)})")
    
    # ── H2d: Bootstrap for combo strategy ──
    if 'xau_for_res' in dir() and len(combo_rets) >= 15:
        print(f"\n--- H2d: 组合策略 Bootstrap 置信区间 ---")
        ci_low, ci_high = bootstrap_confidence(combo_rets)
        print(f"  组合策略 WR={combo_wr:.1f}% n={combo_n} 95% CI=[{ci_low:.1f}%, {ci_high:.1f}%]")
    
    # Print comparison table
    if comp_data:
        print(f"\n--- 策略对比汇总 ---")
        print(f"  {'策略':<45} {'n':<6} {'Hold':<6} {'WR':<8} {'avg%':<10} {'信号/月':<8}")
        print(f"  {'-'*45} {'-'*6} {'-'*6} {'-'*8} {'-'*10} {'-'*8}")
        for row in comp_data:
            print(f"  {row[0]:<45} {row[1]:<6} {row[2]:<6} {row[3]:.1f}%{'':<2} {row[4]:.3f}%{'':<3} {row[5]:.1f}")
        if 'xau_for_res' in dir() and len(combo_rets) >= 5:
            sig_per_month = combo_n / max(1, (xau_h2.index[-1] - xau_h2.index[0]).days / 30)
            print(f"  {'▶ 组合策略 (共振优先+双枪补充)':<45} {combo_n:<6} {hold_test:<6} {combo_wr:.1f}%{'':<2} {combo_avg:.3f}%{'':<3} {sig_per_month:.1f}")


# ═══════════════════════════════════════════════════════════════
# H3: 双枪策略月度跟踪 (round28_003)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("H3: 双枪策略月度跟踪 — 近6月表现监测 (round28_003)")
print("=" * 90)
print("目标: 持续监测双枪策略近6月表现. 关注2026-05~06是否再次出现回撤")
print("      双枪欧盘: EU 9-11 RSI<18+CB>=4 hold=42")
print("      双枪美盘: US 15-16 RSI<20+CB>=2 hold=115")

if "XAUUSD" in all_data_m5:
    xau_h3 = all_data_m5["XAUUSD"]
    
    recent_cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
    early_mask = xau_h3.index < recent_cutoff
    recent_mask = xau_h3.index >= recent_cutoff
    
    print(f"  数据分割点: {recent_cutoff.date()}")
    print(f"  早期: {early_mask.sum():,} 行, 近期: {recent_mask.sum():,} 行")
    
    # Define conditions
    eu_mask_h3 = (
        (xau_h3['session'] == 'europe') &
        (xau_h3.index.hour >= 9) & (xau_h3.index.hour < 11) &
        (xau_h3['rsi14'] < 18) & (xau_h3['consecutive_bear'] >= 4)
    )
    us_mask_h3 = (
        (xau_h3['session'] == 'us') &
        (xau_h3.index.hour >= 15) & (xau_h3.index.hour < 16) &
        (xau_h3['rsi14'] < 20) & (xau_h3['consecutive_bear'] >= 2)
    )
    
    # ── 全历史 vs 近6月 ──
    print(f"\n--- 全历史 vs 近6月 ---")
    print(f"  {'策略':<50} {'全历史n':<8} {'全历史WR':<10} {'近6月n':<8} {'近6月WR':<10} {'近6月avg':<10}")
    print(f"  {'-'*50} {'-'*8} {'-'*10} {'-'*8} {'-'*10} {'-'*10}")
    
    for name, mask, hold in [
        ("双枪欧盘 (EU 9-11 RSI<18+CB>=4)", eu_mask_h3, 42),
        ("双枪美盘 (US 15-16 RSI<20+CB>=2)", us_mask_h3, 115),
    ]:
        n_all, wr_all, avg_all = get_stats(xau_h3, mask, hold)
        n_rec, wr_rec, avg_rec = get_stats(xau_h3, mask & recent_mask, hold)
        print(f"  {name:<50} {n_all:<8} {wr_all:.1f}%{'':>4} {n_rec:<8} {wr_rec:.1f}%{'':>4} {avg_rec:.3f}%")
    
    # 组合统计
    eu_all_rets = compute_returns_from_entries(xau_h3, xau_h3[eu_mask_h3], 42) if len(xau_h3[eu_mask_h3]) >= 5 else np.array([])
    us_all_rets = compute_returns_from_entries(xau_h3, xau_h3[us_mask_h3], 115) if len(xau_h3[us_mask_h3]) >= 5 else np.array([])
    eu_rec_rets = compute_returns_from_entries(xau_h3, xau_h3[eu_mask_h3 & recent_mask], 42) if len(xau_h3[eu_mask_h3 & recent_mask]) >= 5 else np.array([])
    us_rec_rets = compute_returns_from_entries(xau_h3, xau_h3[us_mask_h3 & recent_mask], 115) if len(xau_h3[us_mask_h3 & recent_mask]) >= 5 else np.array([])
    
    comb_all_rets = np.concatenate([r for r in [eu_all_rets, us_all_rets] if len(r) > 0])
    comb_rec_rets = np.concatenate([r for r in [eu_rec_rets, us_rec_rets] if len(r) > 0])
    
    if len(comb_all_rets) > 0:
        comb_all_wr = np.mean(comb_all_rets > 0) * 100
        print(f"  {'▶ 双枪组合 (欧+美)':<50} {len(comb_all_rets):<8} {comb_all_wr:.1f}%{'':>4} ", end="")
        if len(comb_rec_rets) > 0:
            comb_rec_wr = np.mean(comb_rec_rets > 0) * 100
            comb_rec_avg = np.mean(comb_rec_rets)
            print(f"{len(comb_rec_rets):<8} {comb_rec_wr:.1f}%{'':>4} {comb_rec_avg:.3f}%")
        else:
            print(f"{'N/A':<8} {'N/A':<10} {'N/A':<10}")
    
    # ── 月度表现 (近12月) ──
    print(f"\n--- 月度表现 (近12月) ---")
    xau_h3['month'] = xau_h3.index.to_period('M')
    recent_data = xau_h3[xau_h3.index >= (pd.Timestamp.now() - pd.DateOffset(months=12))]
    
    print(f"  {'月份':<10} {'欧盘n':<6} {'欧盘WR':<8} {'美盘n':<6} {'美盘WR':<8} {'组合n':<6} {'组合WR':<8}")
    print(f"  {'-'*10} {'-'*6} {'-'*8} {'-'*6} {'-'*8} {'-'*6} {'-'*8}")
    
    monthly_rows = []
    for month, grp in recent_data.groupby('month'):
        grp_mask_eu = eu_mask_h3.reindex(grp.index, fill_value=False)
        grp_mask_us = us_mask_h3.reindex(grp.index, fill_value=False)
        n_eu, wr_eu, _ = get_stats(grp, grp_mask_eu, 42)
        n_us, wr_us, _ = get_stats(grp, grp_mask_us, 115)
        n_comb = n_eu + n_us
        wr_comb = (wr_eu * n_eu + wr_us * n_us) / n_comb if n_comb > 0 else 0
        print(f"  {str(month):<10} {n_eu:<6} {wr_eu:.1f}%{'':>2} {n_us:<6} {wr_us:.1f}%{'':>2} {n_comb:<6} {wr_comb:.1f}%")
        monthly_rows.append((str(month), n_eu, wr_eu, n_us, wr_us, n_comb, wr_comb))
    
    # 近6月汇总
    print(f"\n--- 双枪策略近6月汇总 ---")
    if len(comb_rec_rets) > 0:
        print(f"  双枪组合近6月: n={len(comb_rec_rets)} WR={comb_rec_wr:.1f}% avg={comb_rec_avg:.3f}%")
        ci_low, ci_high = bootstrap_confidence(comb_rec_rets)
        if ci_low is not None:
            print(f"  Bootstrap 95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]")
    
    # 检查回撤恢复情况
    print(f"\n--- 回撤分析 ---")
    # Look for months with WR < 70%
    low_months = [r for r in monthly_rows if r[6] < 70 and r[5] >= 2]
    if low_months:
        print(f"  ⚠️ 以下月份出现组合WR<70%回撤:")
        for m in low_months:
            print(f"    {m[0]}: n={m[5]} WR={m[6]:.1f}%")
    else:
        print(f"  ✅ 近12月无显著回撤(组合WR<70%且n≥2), 策略持续有效")
    
    # Check specific for 2026-05 and 2026-06
    current_month = pd.Timestamp.now().to_period('M')
    print(f"  当前月份: {current_month}")
    for r in monthly_rows:
        if r[0] == str(current_month):
            print(f"  本月({r[0]}): 欧盘n={r[1]} WR={r[2]:.1f}%, 美盘n={r[3]} WR={r[4]:.1f}%, 组合WR={r[6]:.1f}%")
            if r[6] >= 80:
                print(f"  ✅ 本月表现优秀! (WR≥80%)")
            elif r[6] >= 70:
                print(f"  ⚠️ 本月表现中等 (WR 70-80%)")
            else:
                print(f"  🔴 本月出现回撤! (WR<70%)")
            break


# ═══════════════════════════════════════════════════════════════
# H4: XAG美盘极端阈值持续积累 (round28_004)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("H4: XAG美盘极端阈值持续积累 (round28_004)")
print("=" * 90)
print("目标: round27 发现 RSI<14+CB>=4 进度12/20, RSI<16+CB>=5 进度11/20")
print("      旧基准 RSI<18+CB>=3 WR=87.1% n=31 hold=105 依然最优")
print("      检查数据积累情况")

if "XAGUSD" in all_data_m5:
    xag_h4 = all_data_m5["XAGUSD"]
    
    # US session conditions
    us_base = (xag_h4['session'] == 'us') & (xag_h4.index.hour >= 15) & (xag_h4.index.hour < 16)
    
    thresholds = [
        ("RSI<14+CB>=4 （极端1）", (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 4)),
        ("RSI<16+CB>=5 （极端2）", (xag_h4['rsi14'] < 16) & (xag_h4['consecutive_bear'] >= 5)),
        ("RSI<14+CB>=5 （极端3）", (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 5)),
        ("RSI<12+CB>=3 （极端RSI）", (xag_h4['rsi14'] < 12) & (xag_h4['consecutive_bear'] >= 3)),
        ("旧基准 RSI<18+CB>=3", (xag_h4['rsi14'] < 18) & (xag_h4['consecutive_bear'] >= 3)),
        ("RSI<18+CB>=2 （宽松）", (xag_h4['rsi14'] < 18) & (xag_h4['consecutive_bear'] >= 2)),
        ("RSI<16+CB>=3 （中位）", (xag_h4['rsi14'] < 16) & (xag_h4['consecutive_bear'] >= 3)),
    ]
    
    print(f"\n--- XAG美盘极端阈值数据积累进度 ---")
    print(f"  {'条件':<30} {'信号数':<8} {'进度':<10} {'最佳hold':<10} {'最佳WR':<10} {'趋势':<10}")
    print(f"  {'-'*30} {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    
    for name, cond in thresholds:
        mask_full = us_base & cond
        entries = xag_h4[mask_full].copy()
        n = len(entries)
        
        # Progress toward n=20
        progress = f"{n}/20" if n < 20 else "✅ 已达标"
        
        # Best hold and WR
        best_wr, best_hold = 0, 0
        if n >= 5:
            results = {}
            for hold in range(30, 151, 5):
                hits, total_pnl, count = 0, 0.0, 0
                for idx, row in entries.iterrows():
                    pos = xag_h4.index.get_loc(idx)
                    if pos + hold < len(xag_h4):
                        exit_price = xag_h4.iloc[pos + hold]['close']
                        pnl = (exit_price - row['close']) / row['close'] * 100
                        total_pnl += pnl
                        count += 1
                        if pnl > 0: hits += 1
                if count >= 5:
                    results[hold] = {'n': count, 'wr': hits/count*100, 'avg_ret': total_pnl/count}
            if results:
                best_hold = max(results, key=lambda h: results[h]['wr'])
                best_wr = results[best_hold]['wr']
                
                # Compare with round27 (n value)
                # We just show the current WR
                trend = ""
                if n >= 20:
                    trend = "✅ 达标"
                elif n >= 15:
                    trend = f"接近 (还需{20-n})"
                else:
                    trend = f"积累中 (还需{20-n})"
                
                print(f"  {name:<30} {n:<8} {progress:<10} hold={best_hold:<5} {best_wr:.1f}%{'':>4} {trend:<10}")
            else:
                print(f"  {name:<30} {n:<8} {progress:<10} {'-':<10} {'-':<10} {'-':<10}")
        else:
            print(f"  {name:<30} {n:<8} {progress:<10} {'-':<10} {'-':<10} {'-':<10}")
    
    # ── H4b: 宽时段 XAG 极端阈值 ──
    print(f"\n--- H4b: XAG 宽时段(14-16) 极端阈值 ---")
    wide_base = (xag_h4['session'] == 'us') & (xag_h4.index.hour >= 14) & (xag_h4.index.hour < 17)
    
    wide_conds = [
        ("US 14-16 RSI<14+CB>=4", (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 4)),
        ("US 14-16 RSI<16+CB>=4", (xag_h4['rsi14'] < 16) & (xag_h4['consecutive_bear'] >= 4)),
        ("US 14-16 RSI<14+CB>=3", (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 3)),
    ]
    
    for name, cond in wide_conds:
        mask = wide_base & cond
        n, wr, avg = get_stats(xag_h4, mask, 125)  # Use hold=125 from round27
        print(f"  {name:<40} n={n:<5} WR={wr:.1f}% avg={avg:.3f}%" if n >= 5 else f"  {name:<40} n={n:<5} (信号不足)")
    
    # ── H4c: XAG 欧盘稳定性复查 ──
    print(f"\n--- H4c: XAG 欧盘稳定性复查 ---")
    eu_base_h4 = (xag_h4['session'] == 'europe') & (xag_h4.index.hour >= 9) & (xag_h4.index.hour < 11)
    
    eu_conds = [
        ("XAG EU 9-11 RSI<14+CB>=3 hold=85", (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 3), 85),
        ("XAG EU 9-11 RSI<14+CB>=3 hold=95", (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 3), 95),
        ("XAG EU 9-11 RSI<14+CB>=3 hold=105", (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 3), 105),
    ]
    
    for name, cond, hold in eu_conds:
        mask = eu_base_h4 & cond
        n, wr, avg = get_stats(xag_h4, mask, hold)
        print(f"  {name:<45} n={n:<5} WR={wr:.1f}% avg={avg:.3f}%" if n >= 5 else f"  {name:<45} n={n:<5} (信号不足)")
    
    # 置信区间 for XAG EU hold=85
    print(f"\n--- XAG EU hold=85 Bootstrap 置信区间复查 ---")
    eu_mask_85 = eu_base_h4 & (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 3)
    entries_85 = xag_h4[eu_mask_85]
    if len(entries_85) >= 10:
        rets_85 = compute_returns_from_entries(xag_h4, entries_85, 85)
        ci_low, ci_high = bootstrap_confidence(rets_85)
        wr_85 = np.mean(rets_85 > 0) * 100
        print(f"  XAG EU hold=85: n={len(rets_85)} WR={wr_85:.1f}% CI=[{ci_low:.1f}%, {ci_high:.1f}%]")
    
    # 跨周期验证 XAG EU hold=85
    print(f"\n--- XAG EU hold=85 跨周期验证 ---")
    test_condition_with_periods(xag_h4, eu_mask_85,
                                "XAG EU 9-11 RSI<14+CB>=3",
                                hold_range=[75, 80, 85, 90, 95, 100, 105, 110, 115],
                                min_signals=15)


# ═══════════════════════════════════════════════════════════════
# H5: H1/M30 框架探索 (round28_005) — 概念验证
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("H5: H1/M30 框架探索 (round28_005) — 概念验证")
print("=" * 90)
print("目标: 扩展时间框架到H1/M30, 探索RSI超卖+支撑位等中长线模式")
print("注意: 当前数据系统仅支持M1/M5. H1/M30数据不可直接加载")
print("      使用M5数据合成M30/H1模拟探索")
print("")

# ── H5a: 合成M30数据 from M5 ──
if "XAUUSD" in all_data_m5:
    xau_m5 = all_data_m5["XAUUSD"]
    print(f"--- H5a: 合成M30数据 (M5→M30 resample) ---")
    
    # Resample M5 to M30
    m30 = xau_m5[['open','high','low','close','tick_volume']].resample('30min').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'tick_volume': 'sum',
    }).dropna()
    m30 = compute_indicators(m30)
    
    # Add session
    m30['session'] = 'asia'
    m30.loc[(m30.index.hour >= 8) & (m30.index.hour < 13), 'session'] = 'europe'
    m30.loc[(m30.index.hour >= 13) & (m30.index.hour < 22), 'session'] = 'us'
    
    print(f"  M30 XAUUSD: {len(m30)} rows  [{m30.index[0].date()} → {m30.index[-1].date()}]")
    print(f"  Latest: Close={m30['close'].iloc[-1]:.1f} RSI={m30['rsi14'].iloc[-1]:.1f}")
    
    # Test: US session RSI<25 on M30, hold=1 (30min) to 8 (4hr)
    print(f"\n--- M30 US RSI<25 超卖反弹 ---")
    m30_us_mask = (m30['session'] == 'us') & (m30['rsi14'] < 25) & (m30['consecutive_bear'] >= 1)
    test_condition(m30, m30_us_mask,
                   "M30 US RSI<25+CB>=1 (超卖反弹, hold=1~8 candles = 30min~4hr)",
                   hold_range=list(range(1, 17, 1)))
    
    # Test: EU session RSI<20 on M30
    print(f"\n--- M30 EU RSI<20 超卖反弹 ---")
    m30_eu_mask = (m30['session'] == 'europe') & (m30['rsi14'] < 20) & (m30['consecutive_bear'] >= 2)
    test_condition(m30, m30_eu_mask,
                   "M30 EU RSI<20+CB>=2 (超卖反弹, hold=1~16)",
                   hold_range=list(range(1, 17, 1)))
    
    # Test: US RSI<20 on M30
    print(f"\n--- M30 US RSI<20+CB>=1 ---")
    m30_us_20 = (m30['session'] == 'us') & (m30['rsi14'] < 20) & (m30['consecutive_bear'] >= 1)
    test_condition(m30, m30_us_20,
                   "M30 US RSI<20+CB>=1 (hold=1~16)",
                   hold_range=list(range(1, 17, 1)))
    
    # ── H5b: 合成H1 data from M5 ──
    print(f"\n--- H5b: 合成H1数据 (M5→H1 resample) ---")
    h1 = xau_m5[['open','high','low','close','tick_volume']].resample('1h').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'tick_volume': 'sum',
    }).dropna()
    h1 = compute_indicators(h1)
    
    h1['session'] = 'asia'
    h1.loc[(h1.index.hour >= 8) & (h1.index.hour < 13), 'session'] = 'europe'
    h1.loc[(h1.index.hour >= 13) & (h1.index.hour < 22), 'session'] = 'us'
    
    print(f"  H1 XAUUSD: {len(h1)} rows  [{h1.index[0].date()} → {h1.index[-1].date()}]")
    print(f"  Latest: Close={h1['close'].iloc[-1]:.1f} RSI={h1['rsi14'].iloc[-1]:.1f}")
    
    # H1: US RSI<30超卖
    print(f"\n--- H1 US RSI<30 超卖反弹 ---")
    h1_us_mask = (h1['session'] == 'us') & (h1['rsi14'] < 30) & (h1['consecutive_bear'] >= 1)
    test_condition(h1, h1_us_mask,
                   "H1 US RSI<30+CB>=1 (hold=1~8 candles = 1~8hr)",
                   hold_range=list(range(1, 9, 1)))
    
    # H1: EU RSI<25超卖
    print(f"\n--- H1 EU RSI<25 超卖反弹 ---")
    h1_eu_mask = (h1['session'] == 'europe') & (h1['rsi14'] < 25) & (h1['consecutive_bear'] >= 2)
    test_condition(h1, h1_eu_mask,
                   "H1 EU RSI<25+CB>=2 (hold=1~8)",
                   hold_range=list(range(1, 9, 1)))
    
    # H1: RSI<20 极端超卖 (任何时段)
    print(f"\n--- H1 RSI<20 极端超卖 (全天候) ---")
    h1_extreme = (h1['rsi14'] < 20) & (h1['consecutive_bear'] >= 2)
    test_condition(h1, h1_extreme,
                   "H1 RSI<20+CB>=2 全天候 (hold=1~12)",
                   hold_range=list(range(1, 13, 1)))
    
    # Cross-timeframe: H1 RSI<25 + M5 tick_volume surge
    print(f"\n--- H5c: 多时间框架组合 (H1 RSI<25 + M5 成交量激增) ---")
    # Simple approach: Use H1 RSI<25 signals, then check if last M5 candle had volume surge
    # For now, just test H1 RSI<25 + CB>=1
    h1_comb = (h1['rsi14'] < 25) & (h1['consecutive_bear'] >= 1)
    test_condition(h1, h1_comb,
                   "H1 RSI<25+CB>=1 (hold=1~12)",
                   hold_range=list(range(1, 13, 1)))

else:
    print("  ⚠️  XAUUSD M5 data not available, skipping H5")


# ═══════════════════════════════════════════════════════════════
# 快速扫描: US30 / JP225 / US500 非重点品种
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("快速扫描: 其他品种状态检查")
print("=" * 90)

for sym in ["JP225", "US30", "US500"]:
    if sym in all_data_m5:
        df_sym = all_data_m5[sym]
        print(f"\n--- {sym} M5 快速扫描 ---")
        
        # Existing best: JP225 US RSI<14+CB>=2 hold=55
        if sym == "JP225":
            jp_mask = (df_sym['session'] == 'us') & (df_sym.index.hour >= 15) & (df_sym.index.hour < 16) & (df_sym['rsi14'] < 14) & (df_sym['consecutive_bear'] >= 2)
            n, wr, avg = get_stats(df_sym, jp_mask, 55)
            print(f"  JP225 US RSI<14+CB>=2 hold=55: n={n} WR={wr:.1f}% avg={avg:.3f}%")
            if n >= 10:
                jp_rets = compute_returns_from_entries(df_sym, df_sym[jp_mask], 55)
                ci_low, ci_high = bootstrap_confidence(jp_rets)
                print(f"    Bootstrap 95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]")
            
            # Try broader condition
            jp_broad = (df_sym['session'] == 'us') & (df_sym.index.hour >= 15) & (df_sym.index.hour < 16) & (df_sym['rsi14'] < 16) & (df_sym['consecutive_bear'] >= 2)
            n2, wr2, avg2 = get_stats(df_sym, jp_broad, 55)
            print(f"  JP225 US RSI<16+CB>=2 hold=55: n={n2} WR={wr2:.1f}% avg={avg2:.3f}%")
        
        # US30: check if any session works
        elif sym == "US30":
            us30_masks = [
                ("US 15-16 RSI<20+CB>=2", (df_sym['session'] == 'us') & (df_sym.index.hour >= 15) & (df_sym.index.hour < 16) & (df_sym['rsi14'] < 20) & (df_sym['consecutive_bear'] >= 2)),
                ("EU 9-11 RSI<18+CB>=3", (df_sym['session'] == 'europe') & (df_sym.index.hour >= 9) & (df_sym.index.hour < 11) & (df_sym['rsi14'] < 18) & (df_sym['consecutive_bear'] >= 3)),
                ("US 15-16 RSI<14+CB>=2", (df_sym['session'] == 'us') & (df_sym.index.hour >= 15) & (df_sym.index.hour < 16) & (df_sym['rsi14'] < 14) & (df_sym['consecutive_bear'] >= 2)),
            ]
            for name, mask in us30_masks:
                n, wr, avg = get_stats(df_sym, mask, 55)
                if n >= 5:
                    print(f"  US30 {name:<35} n={n:<5} WR={wr:.1f}% avg={avg:.3f}%")
                else:
                    print(f"  US30 {name:<35} n={n:<5} (信号不足)")
        
        # US500
        elif sym == "US500":
            us500_masks = [
                ("US 15-16 RSI<20+CB>=2", (df_sym['session'] == 'us') & (df_sym.index.hour >= 15) & (df_sym.index.hour < 16) & (df_sym['rsi14'] < 20) & (df_sym['consecutive_bear'] >= 2)),
                ("US 15-16 RSI<14+CB>=2", (df_sym['session'] == 'us') & (df_sym.index.hour >= 15) & (df_sym.index.hour < 16) & (df_sym['rsi14'] < 14) & (df_sym['consecutive_bear'] >= 2)),
                ("EU 9-11 RSI<18+CB>=3", (df_sym['session'] == 'europe') & (df_sym.index.hour >= 9) & (df_sym.index.hour < 11) & (df_sym['rsi14'] < 18) & (df_sym['consecutive_bear'] >= 3)),
            ]
            for name, mask in us500_masks:
                n, wr, avg = get_stats(df_sym, mask, 55)
                if n >= 5:
                    print(f"  US500 {name:<35} n={n:<5} WR={wr:.1f}% avg={avg:.3f}%")
                else:
                    print(f"  US500 {name:<35} n={n:<5} (信号不足)")


# ═══════════════════════════════════════════════════════════════
# 总结 & 最佳策略排名 (Round28更新)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("🏆 全策略可行性排名 (Round28更新)")
print("=" * 90)

# Collect best strategies for ranking
all_strategies = []

# XAU 双枪欧盘
if "XAUUSD" in all_data_m5:
    xau_final = all_data_m5["XAUUSD"]
    recent_6m = pd.Timestamp.now() - pd.DateOffset(months=6)
    
    eu_final = (xau_final['session'] == 'europe') & (xau_final.index.hour >= 9) & (xau_final.index.hour < 11) & (xau_final['rsi14'] < 18) & (xau_final['consecutive_bear'] >= 4)
    us_final = (xau_final['session'] == 'us') & (xau_final.index.hour >= 15) & (xau_final.index.hour < 16) & (xau_final['rsi14'] < 20) & (xau_final['consecutive_bear'] >= 2)
    
    n_eu, wr_eu, avg_eu = get_stats(xau_final, eu_final, 42)
    n_us, wr_us, avg_us = get_stats(xau_final, us_final, 115)
    
    if n_eu >= 5:
        all_strategies.append(("双枪欧盘做多XAU", wr_eu, n_eu, avg_eu, 42, "M5 EU 9-11 RSI<18+CB>=4"))
    if n_us >= 5:
        all_strategies.append(("双枪美盘做多XAU", wr_us, n_us, avg_us, 115, "M5 US 15-16 RSI<20+CB>=2"))
    
    # 共振美盘
    if "XAGUSD" in all_data_m5:
        xag_final = all_data_m5["XAGUSD"]
        common_final = xau_final.index.intersection(xag_final.index)
        xau_f_aligned = xau_final.loc[common_final]
        xag_f_aligned = xag_final.loc[common_final]
        res_f = (xau_f_aligned['session'] == 'us') & (xau_f_aligned.index.hour >= 15) & (xau_f_aligned.index.hour < 16) & (xau_f_aligned['rsi14'] < 18) & (xau_f_aligned['consecutive_bear'] >= 1) & (xag_f_aligned['consecutive_bear'] >= 1)
        n_res, wr_res, avg_res = get_stats(xau_f_aligned, res_f, 115)
        if n_res >= 5:
            all_strategies.append(("共振美盘→XAU (XAG共振)", wr_res, n_res, avg_res, 115, "M5 US 15-16 RSI<18+CB>=1+XAG共振"))
    
    # 双枪组合
    eu_rets_f = compute_returns_from_entries(xau_final, xau_final[eu_final], 42) if n_eu >= 5 else np.array([])
    us_rets_f = compute_returns_from_entries(xau_final, xau_final[us_final], 115) if n_us >= 5 else np.array([])
    comb_rets_f = np.concatenate([r for r in [eu_rets_f, us_rets_f] if len(r) > 0])
    if len(comb_rets_f) > 0:
        comb_wr_f = np.mean(comb_rets_f > 0) * 100
        comb_n_f = len(comb_rets_f)
        comb_avg_f = np.mean(comb_rets_f)
        all_strategies.append(("双枪组合(欧+美)", comb_wr_f, comb_n_f, comb_avg_f, "42+115", "M5 EU+US 双枪合并"))

# XAG
if "XAGUSD" in all_data_m5:
    xag_f = all_data_m5["XAGUSD"]
    eu_base_f = (xag_f['session'] == 'europe') & (xag_f.index.hour >= 9) & (xag_f.index.hour < 11)
    us_base_f = (xag_f['session'] == 'us') & (xag_f.index.hour >= 15) & (xag_f.index.hour < 16)
    
    xag_eu = eu_base_f & (xag_f['rsi14'] < 14) & (xag_f['consecutive_bear'] >= 3)
    xag_us = us_base_f & (xag_f['rsi14'] < 18) & (xag_f['consecutive_bear'] >= 3)
    
    n_xag_eu, wr_xag_eu, avg_xag_eu = get_stats(xag_f, xag_eu, 85)
    n_xag_us, wr_xag_us, avg_xag_us = get_stats(xag_f, xag_us, 105)
    
    if n_xag_eu >= 5:
        all_strategies.append(("XAG欧盘RSI<14+CB>=3", wr_xag_eu, n_xag_eu, avg_xag_eu, 85, "M5 EU 9-11 RSI<14+CB>=3 hold=85"))
    if n_xag_us >= 5:
        all_strategies.append(("XAG美盘RSI<18+CB>=3", wr_xag_us, n_xag_us, avg_xag_us, 105, "M5 US 15-16 RSI<18+CB>=3 hold=105"))

# JP225
if "JP225" in all_data_m5:
    jp_f = all_data_m5["JP225"]
    jp_mask_f = (jp_f['session'] == 'us') & (jp_f.index.hour >= 15) & (jp_f.index.hour < 16) & (jp_f['rsi14'] < 14) & (jp_f['consecutive_bear'] >= 2)
    n_jp, wr_jp, avg_jp = get_stats(jp_f, jp_mask_f, 55)
    if n_jp >= 5:
        all_strategies.append(("JP225美盘RSI<14+CB>=2", wr_jp, n_jp, avg_jp, 55, "M5 US 15-16 RSI<14+CB>=2 hold=55"))

# M1 EU 仿双枪
if "XAUUSD" in all_data_m1:
    xau_m1_f = all_data_m1["XAUUSD"]
    m1_eu_f = (xau_m1_f['session'] == 'europe') & (xau_m1_f.index.hour >= 9) & (xau_m1_f.index.hour < 11) & (xau_m1_f['rsi14'] < 16) & (xau_m1_f['consecutive_bear'] >= 3)
    n_m1, wr_m1, avg_m1 = get_stats(xau_m1_f, m1_eu_f, 24)
    if n_m1 >= 5:
        all_strategies.append(("M1 EU仿双枪XAU", wr_m1, n_m1, avg_m1, 24, "M1 EU 9-11 RSI<16+CB>=3 hold=24"))

# Sort by composite score: WR * 0.5 + min(n/30, 1) * 0.3 + min(abs(avg)*50, 1) * 0.2
def composite_score(strat):
    wr, n, avg = strat[1], strat[2], strat[3]
    return wr * 0.5 + min(n / 30, 1) * 0.3 + min(abs(avg) * 50, 1) * 0.2

all_strategies.sort(key=composite_score, reverse=True)

# Header
print(f"\n| {'排名':<4} | {'策略':<30} | {'WR':<7} | {'n':<6} | {'avg%':<8} | {'Hold':<6} | {'信号/月':<8} | {'描述':<40} |")
print(f"|{'':->4}|{'':->30}|{'':->7}|{'':->6}|{'':->8}|{'':->6}|{'':->8}|{'':->40}|")

for i, (name, wr, n, avg, hold, desc) in enumerate(all_strategies, 1):
    # Signal frequency estimation
    if "XAU" in name:
        total_days = (xau_final.index[-1] - xau_final.index[0]).days if "xau_final" in dir() else 365
    elif "XAG" in name:
        total_days = (xag_f.index[-1] - xag_f.index[0]).days if "xag_f" in dir() else 365
    elif "JP225" in name:
        total_days = (jp_f.index[-1] - jp_f.index[0]).days
    else:
        total_days = 365
    months_covered = max(1, total_days / 30)
    freq = n / months_covered
    print(f"| {i:<4} | {name:<30} | {wr:.1f}%{'':>3} | {n:<6} | {avg:.3f}%{'':>3} | {str(hold):<6} | {freq:.1f}/月{'':>3} | {desc:<40} |")


print("\n" + "=" * 90)
print("ROUND 28 COMPLETE")
print(f"Completed at: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 90)
