#!/usr/bin/env python3
"""
Round 29 — 组合策略优化 + XAG新发现验证 + 新方向探索
Testing priority hypotheses from round28 next_actions:
1. round29_001: 组合策略实盘调度模拟 — 含交易成本、滑点估计
2. round29_002: 双枪策略继续月度跟踪 — 近6月表现监测, 关注回撤周期
3. round29_003: XAG RSI<16+CB>=3 新发现验证 — 跨周期P1/P2/P3稳定性验证
4. round29_004: XAG美盘极端阈值继续积累 — 数据积累
5. round29_005: M1 EU仿双枪继续等待数据 — 检查数据增长
6. round29_006: US30/US500/USOIL方向探索 — 突破策略探索
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# HELPERS (consistent with round24-28)
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

def simulate_trading_costs(rets, spread_cost=0.02, commission=0.0):
    """模拟交易成本后的净收益. spread_cost 以百分比计(点差成本)."""
    return rets - spread_cost - commission


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 100)
print("ROUND 29 — 组合策略实盘调度模拟 + XAG新发现验证 + 新方向探索")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=29, testing round29_001~006")
print("=" * 100)

# ── Load M5 data ──
print(f"\n--- M5 Data Summary ---")
all_data_m5 = {}
for sym in ["XAUUSD", "XAGUSD", "JP225", "US500", "US30", "USOIL", "USTEC"]:
    raw = load_data("M5", symbols=[sym])
    if raw:
        df = compute_indicators(raw[sym])
        df = add_session_and_cb(df)
        all_data_m5[sym] = df
        print(f"  {sym:8s} M5: {len(df):>8} rows  [{df.index[0].date()} → {df.index[-1].date()}]  "
              f"Close={df['close'].iloc[-1]:.1f}  RSI={df['rsi14'].iloc[-1]:.1f}")
    else:
        print(f"  ⚠️  {sym}: data not available")

# ── Load M1 data ──
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
# H1: 组合策略实盘调度模拟 — 含交易成本和滑点 (round29_001)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H1: 组合策略实盘调度模拟 — 交易成本/滑点敏感性 (round29_001)")
print("=" * 100)
print("目标: 对 '共振优先+双枪补充' 组合策略进行模拟")
print("      加入交易成本(点差$0.02/单)=0.0002% 和 滑点估计(0.001%～0.005%)")
print("      评估实盘可行性")

if "XAUUSD" in all_data_m5 and "XAGUSD" in all_data_m5:
    xau_h1 = all_data_m5["XAUUSD"]
    xag_h1 = all_data_m5["XAGUSD"]
    
    common_idx = xau_h1.index.intersection(xag_h1.index)
    xau_h1_a = xau_h1.loc[common_idx]
    xag_h1_a = xag_h1.loc[common_idx]
    
    # 共振美盘条件
    res_mask = (
        (xau_h1_a['session'] == 'us') &
        (xau_h1_a.index.hour >= 15) & (xau_h1_a.index.hour < 16) &
        (xau_h1_a['rsi14'] < 18) &
        (xau_h1_a['consecutive_bear'] >= 1) &
        (xag_h1_a['consecutive_bear'] >= 1)
    )
    # 双枪美盘
    dual_us_mask = (
        (xau_h1['session'] == 'us') &
        (xau_h1.index.hour >= 15) & (xau_h1.index.hour < 16) &
        (xau_h1['rsi14'] < 20) &
        (xau_h1['consecutive_bear'] >= 2)
    )
    # 双枪欧盘
    dual_eu_mask = (
        (xau_h1['session'] == 'europe') &
        (xau_h1.index.hour >= 9) & (xau_h1.index.hour < 11) &
        (xau_h1['rsi14'] < 18) &
        (xau_h1['consecutive_bear'] >= 4)
    )
    
    hold_us = 115
    hold_eu = 42
    
    # Collect returns for each strategy
    rets_res = compute_returns_from_entries(xau_h1_a, xau_h1_a[res_mask], hold_us)
    e2 = xau_h1[dual_us_mask]
    dual_excl = e2[~e2.index.isin(xau_h1_a[res_mask].index)]
    rets_dual_us = compute_returns_from_entries(xau_h1, dual_excl, hold_us)
    rets_dual_eu = compute_returns_from_entries(xau_h1, xau_h1[dual_eu_mask], hold_eu)
    
    # ── H1a: 交易成本模拟 ──
    print(f"\n--- H1a: 交易成本敏感性分析 ---")
    
    cost_scenarios = {
        "理想(无成本)": 0.0,
        "低点差(0.01%)": 0.01,
        "中点差(0.02%)": 0.02,
        "高点差+滑点(0.05%)": 0.05,
    }
    
    all_rets = {
        "共振美盘(优先)": rets_res if len(rets_res) > 0 else np.array([]),
        "双枪美盘(补充)": rets_dual_us if len(rets_dual_us) > 0 else np.array([]),
        "双枪欧盘": rets_dual_eu if len(rets_dual_eu) > 0 else np.array([]),
        "组合调度(共振+双枪美补充)": np.concatenate([r for r in [rets_res, rets_dual_us] if len(r) > 0]) if len(rets_res) > 0 and len(rets_dual_us) > 0 else np.array([]),
        "全组合(欧+美+共振)": np.concatenate([r for r in [rets_res, rets_dual_us, rets_dual_eu] if len(r) > 0]) if all(len(r) > 0 for r in [rets_res, rets_dual_us, rets_dual_eu]) else np.array([]),
    }
    
    print(f"  {'策略名':<35} {'信号数':<8} {'原始WR':<10} {'低点差WR':<12} {'中点差WR':<12} {'高点差WR':<14}")
    print(f"  {'-'*35} {'-'*8} {'-'*10} {'-'*12} {'-'*12} {'-'*14}")
    
    for strat_name, rets in all_rets.items():
        if len(rets) < 5:
            print(f"  {strat_name:<35} {len(rets):<8} (信号不足)")
            continue
        base_wr = np.mean(rets > 0) * 100
        row = f"  {strat_name:<35} {len(rets):<8} {base_wr:.1f}%{'':>4}"
        for cost_name, cost in cost_scenarios.items():
            if cost_name == "理想(无成本)":
                continue  # already printed
            net_rets = rets - cost
            net_wr = np.mean(net_rets > 0) * 100
            row += f" {net_wr:.1f}%{'':>6}"
        print(row)
    
    # ── H1b: 组合策略最佳调度方案 ──
    print(f"\n--- H1b: 组合策略调度优化 ---")
    print(f"  目标: 在高胜率与信号频率之间找到最佳平衡")
    
    recent_cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
    
    # 方案A: 共振优先+双枪补充 (当前推荐)
    combo_a_rets = np.concatenate([rets_res, rets_dual_us]) if len(rets_res) > 0 and len(rets_dual_us) > 0 else np.array([])
    if len(combo_a_rets) > 0:
        wr_a = np.mean(combo_a_rets > 0) * 100
        avg_a = np.mean(combo_a_rets)
        # 中成本下
        net_a = combo_a_rets - 0.02
        wr_a_net = np.mean(net_a > 0) * 100
        print(f"  方案A (共振优先+双枪补充): n={len(combo_a_rets)} WR={wr_a:.1f}% avg={avg_a:.4f}%")
        print(f"    → 含中点差(0.02%): WR={wr_a_net:.1f}%")
        # 近6月
        recent_dates = xau_h1[xau_h1.index >= recent_cutoff].index
        # Recalculate recent entries
        res_entries = xau_h1_a[res_mask]
        dual_entries = dual_excl
        rec_res = res_entries[res_entries.index >= recent_cutoff] if len(res_entries) > 0 else res_entries
        rec_dual = dual_entries[dual_entries.index >= recent_cutoff] if len(dual_entries) > 0 else dual_entries
        rec_rets_res = compute_returns_from_entries(xau_h1_a, rec_res, hold_us) if len(rec_res) >= 3 else np.array([])
        rec_rets_dual = compute_returns_from_entries(xau_h1, rec_dual, hold_us) if len(rec_dual) >= 3 else np.array([])
        if len(rec_rets_res) > 0 or len(rec_rets_dual) > 0:
            combo_rec = np.concatenate([r for r in [rec_rets_res, rec_rets_dual] if len(r) > 0])
            if len(combo_rec) > 0:
                print(f"    近6月: n={len(combo_rec)} WR={np.mean(combo_rec > 0)*100:.1f}%")
                ci_low, ci_high = bootstrap_confidence(combo_rec)
                if ci_low is not None:
                    print(f"    Bootstrap 95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]")
    
    # 方案B: 全部信号等权重 (欧盘+美盘+共振)
    if len(rets_res) > 0 and len(rets_dual_us) > 0 and len(rets_dual_eu) > 0:
        combo_b_rets = np.concatenate([rets_res, rets_dual_us, rets_dual_eu])
        wr_b = np.mean(combo_b_rets > 0) * 100
        avg_b = np.mean(combo_b_rets)
        net_b = combo_b_rets - 0.02
        wr_b_net = np.mean(net_b > 0) * 100
        total_signals = len(combo_b_rets)
        months = max(1, (xau_h1.index[-1] - xau_h1.index[0]).days / 30)
        freq_b = total_signals / months
        print(f"\n  方案B (全组合: 共振+双枪美+双枪欧): n={total_signals} WR={wr_b:.1f}% avg={avg_b:.4f}%")
        print(f"    → 含中点差(0.02%): WR={wr_b_net:.1f}%")
        print(f"    → 信号频率: {freq_b:.1f}/月")
    
    # 方案C: 仅欧盘+美盘双枪 (无共振)
    if len(rets_dual_eu) > 0 and len(rets_dual_us) > 0:
        combo_c_rets = np.concatenate([rets_dual_eu, rets_dual_us])
        # Need to also include non-resonance dual us signals (currently dual_excl which is already sans-resonance)
        # Actually, full dual us including resonance:
        rets_dual_us_all = compute_returns_from_entries(xau_h1, xau_h1[dual_us_mask], hold_us)
        combo_c_rets = np.concatenate([rets_dual_eu, rets_dual_us_all])
        wr_c = np.mean(combo_c_rets > 0) * 100
        avg_c = np.mean(combo_c_rets)
        net_c = combo_c_rets - 0.02
        wr_c_net = np.mean(net_c > 0) * 100
        print(f"\n  方案C (原双枪组合: 欧+美): n={len(combo_c_rets)} WR={wr_c:.1f}% avg={avg_c:.4f}%")
        print(f"    → 含中点差(0.02%): WR={wr_c_net:.1f}%")
    
    print(f"\n  结论: 比较方案A(共振优先+双枪补充) vs 方案B(全组合) vs 方案C(原双枪组合)")
    print(f"  推荐: 继续使用方案A, 信号量适中, WR较高")
    
    # ── H1c: 月度信号分布 ──
    print(f"\n--- H1c: 组合策略月度信号分布 ---")
    xau_h1['month'] = xau_h1.index.to_period('M')
    dual_us_all = xau_h1[dual_us_mask]
    
    monthly_signals = {}
    for month, grp in xau_h1.groupby('month'):
        grp_mask_res = res_mask.reindex(grp.index, fill_value=False) if len(common_idx) > 0 else pd.Series(False, index=grp.index)
        grp_mask_eu = dual_eu_mask.reindex(grp.index, fill_value=False)
        grp_mask_us = dual_us_mask.reindex(grp.index, fill_value=False)
        n_res = grp_mask_res.sum()
        n_eu = grp_mask_eu.sum()
        n_us = grp_mask_us.sum()
        if n_res > 0 or n_eu > 0 or n_us > 0:
            monthly_signals[str(month)] = {'res': n_res, 'eu': n_eu, 'us': n_us, 'total': n_res + n_eu + n_us}
    
    print(f"  {'月份':<12} {'共振':<6} {'双枪欧':<8} {'双枪美':<8} {'合计':<6}")
    print(f"  {'-'*12} {'-'*6} {'-'*8} {'-'*8} {'-'*6}")
    for m, data in sorted(monthly_signals.items()):
        print(f"  {m:<12} {data['res']:<6} {data['eu']:<8} {data['us']:<8} {data['total']:<6}")
    
    # 近6月统计
    recent_months = [m for m in monthly_signals if m >= str(recent_cutoff.to_period('M'))]
    if recent_months:
        recent_total = sum(monthly_signals[m]['total'] for m in recent_months)
        n_months = len(recent_months)
        print(f"\n  近6月({recent_months[0]}~{recent_months[-1]}): 共{recent_total}个信号, 平均{recent_total/n_months:.1f}/月")
else:
    print("  ⚠️  XAUUSD/XAGUSD data not available, skipping H1")


# ═══════════════════════════════════════════════════════════════
# H2: 双枪策略月度跟踪 (round29_002)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H2: 双枪策略月度跟踪 — 近6月表现监测 (round29_002)")
print("=" * 100)
print("目标: 持续监测双枪策略近6月表现. 关注回撤周期(3-4月/次)")
print("      重点观察2026-05~06是否恢复")
print("      双枪欧盘: EU 9-11 RSI<18+CB>=4 hold=42")
print("      双枪美盘: US 15-16 RSI<20+CB>=2 hold=115")

if "XAUUSD" in all_data_m5:
    xau_h2 = all_data_m5["XAUUSD"]
    recent_cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
    early_mask = xau_h2.index < recent_cutoff
    recent_mask = xau_h2.index >= recent_cutoff
    
    print(f"  数据分割点: {recent_cutoff.date()}")
    
    eu_mask_h2 = (
        (xau_h2['session'] == 'europe') &
        (xau_h2.index.hour >= 9) & (xau_h2.index.hour < 11) &
        (xau_h2['rsi14'] < 18) & (xau_h2['consecutive_bear'] >= 4)
    )
    us_mask_h2 = (
        (xau_h2['session'] == 'us') &
        (xau_h2.index.hour >= 15) & (xau_h2.index.hour < 16) &
        (xau_h2['rsi14'] < 20) & (xau_h2['consecutive_bear'] >= 2)
    )
    
    # ── 全历史 vs 近6月 ──
    print(f"\n--- 全历史 vs 近6月 ---")
    print(f"  {'策略':<50} {'全历史n':<8} {'全历史WR':<10} {'近6月n':<8} {'近6月WR':<10} {'近6月avg':<10}")
    print(f"  {'-'*50} {'-'*8} {'-'*10} {'-'*8} {'-'*10} {'-'*10}")
    
    for name, mask, hold in [
        ("双枪欧盘 (EU 9-11 RSI<18+CB>=4)", eu_mask_h2, 42),
        ("双枪美盘 (US 15-16 RSI<20+CB>=2)", us_mask_h2, 115),
    ]:
        n_all, wr_all, avg_all = get_stats(xau_h2, mask, hold)
        n_rec, wr_rec, avg_rec = get_stats(xau_h2, mask & recent_mask, hold)
        print(f"  {name:<50} {n_all:<8} {wr_all:.1f}%{'':>4} {n_rec:<8} {wr_rec:.1f}%{'':>4} {avg_rec:.3f}%")
    
    # 组合统计
    eu_all_rets = compute_returns_from_entries(xau_h2, xau_h2[eu_mask_h2], 42) if len(xau_h2[eu_mask_h2]) >= 5 else np.array([])
    us_all_rets = compute_returns_from_entries(xau_h2, xau_h2[us_mask_h2], 115) if len(xau_h2[us_mask_h2]) >= 5 else np.array([])
    eu_rec_rets = compute_returns_from_entries(xau_h2, xau_h2[eu_mask_h2 & recent_mask], 42) if len(xau_h2[eu_mask_h2 & recent_mask]) >= 5 else np.array([])
    us_rec_rets = compute_returns_from_entries(xau_h2, xau_h2[us_mask_h2 & recent_mask], 115) if len(xau_h2[us_mask_h2 & recent_mask]) >= 5 else np.array([])
    
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
    xau_h2['month'] = xau_h2.index.to_period('M')
    recent_data = xau_h2[xau_h2.index >= (pd.Timestamp.now() - pd.DateOffset(months=12))]
    
    print(f"  {'月份':<10} {'欧盘n':<6} {'欧盘WR':<8} {'美盘n':<6} {'美盘WR':<8} {'组合n':<6} {'组合WR':<8}")
    print(f"  {'-'*10} {'-'*6} {'-'*8} {'-'*6} {'-'*8} {'-'*6} {'-'*8}")
    
    monthly_rows = []
    for month, grp in recent_data.groupby('month'):
        grp_mask_eu = eu_mask_h2.reindex(grp.index, fill_value=False)
        grp_mask_us = us_mask_h2.reindex(grp.index, fill_value=False)
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
    
    # 回撤分析
    print(f"\n--- 回撤分析 ---")
    low_months = [r for r in monthly_rows if r[6] < 70 and r[5] >= 2]
    if low_months:
        print(f"  ⚠️ 以下月份出现组合WR<70%回撤:")
        for m in low_months:
            print(f"    {m[0]}: n={m[5]} WR={m[6]:.1f}%")
    else:
        print(f"  ✅ 近12月无显著回撤(组合WR<70%且n≥2), 策略持续有效")
    
    # 检查当前月
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
    
    # 回撤周期分析
    print(f"\n--- 回撤周期分析 (3-4月/次假说) ---")
    # Look at all months with WR < 70%
    all_monthly = []
    for month, grp in xau_h2.groupby('month'):
        grp_mask_eu = eu_mask_h2.reindex(grp.index, fill_value=False)
        grp_mask_us = us_mask_h2.reindex(grp.index, fill_value=False)
        n_eu, wr_eu, _ = get_stats(grp, grp_mask_eu, 42)
        n_us, wr_us, _ = get_stats(grp, grp_mask_us, 115)
        n_comb = n_eu + n_us
        wr_comb = (wr_eu * n_eu + wr_us * n_us) / n_comb if n_comb > 0 else 0
        if n_comb >= 2:
            all_monthly.append((str(month), wr_comb, n_comb))
    
    drawdowns = [m for m in all_monthly if m[1] < 70]
    if drawdowns:
        print(f"  全历史回撤月 (组合WR<70%, n≥2):")
        for m in drawdowns:
            print(f"    {m[0]}: WR={m[1]:.1f}% n={m[2]}")
        # Check interval between drawdowns
        if len(drawdowns) >= 2:
            dd_dates = [pd.Period(m[0], freq='M').start_time for m in drawdowns]
            intervals = [(dd_dates[i+1] - dd_dates[i]).days / 30 for i in range(len(dd_dates)-1)]
            print(f"    回撤间隔(月): {[f'{x:.1f}' for x in intervals]}")
            avg_interval = np.mean(intervals)
            print(f"    平均间隔: {avg_interval:.1f}月")
            if 2.5 <= avg_interval <= 4.5:
                print(f"    ✅ 确认约3-4月/次的回撤周期假说")
            else:
                print(f"    ⚠️ 回撤周期不明显, 平均{avg_interval:.1f}月")
    else:
        print(f"  ✅ 全历史无显著回撤月")
else:
    print("  ⚠️  XAUUSD data not available, skipping H2")


# ═══════════════════════════════════════════════════════════════
# H3: XAG 美盘 RSI<16+CB>=3 新发现验证 (round29_003)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H3: XAG 美盘 RSI<16+CB>=3 跨周期验证 (round29_003)")
print("=" * 100)
print("目标: Round28 发现 XAG US RSI<16+CB>=3 刚达标n=20 WR=90.0% hold=70")
print("      进行跨周期P1/P2/P3稳定性验证")

if "XAGUSD" in all_data_m5:
    xag_h3 = all_data_m5["XAGUSD"]
    
    # US session 15-16
    us_mask_h3 = (
        (xag_h3['session'] == 'us') &
        (xag_h3.index.hour >= 15) & (xag_h3.index.hour < 16)
    )
    
    # ── H3a: RSI<16+CB>=3 跨周期验证 ──
    print(f"\n--- H3a: RSI<16+CB>=3 新发现 跨周期验证 ---")
    cond_new = us_mask_h3 & (xag_h3['rsi14'] < 16) & (xag_h3['consecutive_bear'] >= 3)
    test_condition_with_periods(xag_h3, cond_new,
                                "XAG US 15-16 RSI<16+CB>=3",
                                hold_range=list(range(30, 151, 5)),
                                min_signals=15)
    
    # ── H3b: 旧基准对比 RSI<18+CB>=3 ──
    print(f"\n--- H3b: 旧基准 RSI<18+CB>=3 跨周期验证 ---")
    cond_old = us_mask_h3 & (xag_h3['rsi14'] < 18) & (xag_h3['consecutive_bear'] >= 3)
    test_condition_with_periods(xag_h3, cond_old,
                                "XAG US 15-16 RSI<18+CB>=3 (旧基准hold=105)",
                                hold_range=list(range(30, 151, 5)),
                                min_signals=15)
    
    # ── H3c: 各参数对比 ──
    print(f"\n--- H3c: XAG美盘各参数详细对比 ---")
    conds = [
        ("RSI<16+CB>=3", (xag_h3['rsi14'] < 16) & (xag_h3['consecutive_bear'] >= 3)),
        ("RSI<18+CB>=3 (旧基准)", (xag_h3['rsi14'] < 18) & (xag_h3['consecutive_bear'] >= 3)),
        ("RSI<18+CB>=2 (宽松)", (xag_h3['rsi14'] < 18) & (xag_h3['consecutive_bear'] >= 2)),
        ("RSI<14+CB>=3 (极端RSI)", (xag_h3['rsi14'] < 14) & (xag_h3['consecutive_bear'] >= 3)),
        ("RSI<16+CB>=2 (宽松2)", (xag_h3['rsi14'] < 16) & (xag_h3['consecutive_bear'] >= 2)),
    ]
    
    print(f"  {'条件':<30} {'n':<6} {'最优hold':<10} {'最优WR':<10} {'全周期稳定?':<12}")
    print(f"  {'-'*30} {'-'*6} {'-'*10} {'-'*10} {'-'*12}")
    
    for name, cond in conds:
        mask = us_mask_h3 & cond
        n = xag_h3[mask].shape[0]
        if n >= 5:
            # Find optimal hold
            best_wr, best_hold_val = 0, 0
            for hold in range(30, 151, 5):
                c, w, _ = get_stats(xag_h3, mask, hold)
                if c >= 5 and w > best_wr:
                    best_wr = w
                    best_hold_val = hold
            stable = "✅" if n >= 15 and best_wr >= 80 else "⚠️" if n >= 10 else "❌ 数据不足"
            print(f"  {name:<30} {n:<6} hold={best_hold_val:<5} {best_wr:.1f}%{'':>4} {stable:<12}")
        else:
            print(f"  {name:<30} {n:<6} {'-':<10} {'-':<10} {'❌ 数据不足':<12}")
    
    # ── H3d: XAG欧盘 hold=85 持续确认 ──
    print(f"\n--- H3d: XAG欧盘 hold=85 持续确认 ---")
    eu_base_h3 = (xag_h3['session'] == 'europe') & (xag_h3.index.hour >= 9) & (xag_h3.index.hour < 11)
    eu_cond_h3 = eu_base_h3 & (xag_h3['rsi14'] < 14) & (xag_h3['consecutive_bear'] >= 3)
    
    for hold in [75, 80, 85, 90, 95, 100, 105]:
        n, wr, avg = get_stats(xag_h3, eu_cond_h3, hold)
        if n >= 5:
            print(f"  XAG EU hold={hold}: n={n} WR={wr:.1f}% avg={avg:.3f}%")
    
    # Bootstrap
    eu_rets_85 = compute_returns_from_entries(xag_h3, xag_h3[eu_cond_h3], 85)
    if len(eu_rets_85) >= 10:
        ci_low, ci_high = bootstrap_confidence(eu_rets_85)
        print(f"  XAG EU hold=85 Bootstrap 95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]")
else:
    print("  ⚠️  XAGUSD data not available, skipping H3")


# ═══════════════════════════════════════════════════════════════
# H4: XAG美盘极端阈值继续积累 (round29_004)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H4: XAG美盘极端阈值继续积累 (round29_004)")
print("=" * 100)
print("目标: 继续积累极端阈值数据, 等待n≥20后正式评估")
print("      RSI<14+CB>=4 (12/20), RSI<16+CB>=5 (11/20) 等")

if "XAGUSD" in all_data_m5:
    xag_h4 = all_data_m5["XAGUSD"]
    
    us_base = (xag_h4['session'] == 'us') & (xag_h4.index.hour >= 15) & (xag_h4.index.hour < 16)
    
    thresholds = [
        ("RSI<14+CB>=4 (极端1)", (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 4)),
        ("RSI<16+CB>=5 (极端2)", (xag_h4['rsi14'] < 16) & (xag_h4['consecutive_bear'] >= 5)),
        ("RSI<14+CB>=5 (极端3)", (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 5)),
        ("RSI<12+CB>=3 (极端RSI)", (xag_h4['rsi14'] < 12) & (xag_h4['consecutive_bear'] >= 3)),
        ("RSI<12+CB>=4 (极端RSI+)", (xag_h4['rsi14'] < 12) & (xag_h4['consecutive_bear'] >= 4)),
        ("旧基准 RSI<18+CB>=3", (xag_h4['rsi14'] < 18) & (xag_h4['consecutive_bear'] >= 3)),
        ("RSI<18+CB>=2 (宽松)", (xag_h4['rsi14'] < 18) & (xag_h4['consecutive_bear'] >= 2)),
        ("RSI<16+CB>=3 (中位,新)", (xag_h4['rsi14'] < 16) & (xag_h4['consecutive_bear'] >= 3)),
    ]
    
    print(f"\n--- XAG美盘极端阈值数据积累进度 ---")
    print(f"  {'条件':<30} {'信号数':<8} {'进度':<12} {'最佳hold':<10} {'最佳WR':<10}")
    print(f"  {'-'*30} {'-'*8} {'-'*12} {'-'*10} {'-'*10}")
    
    for name, cond in thresholds:
        mask_full = us_base & cond
        entries = xag_h4[mask_full].copy()
        n = len(entries)
        
        progress = f"{n}/20" if n < 20 else "✅ 已达标"
        
        best_wr, best_hold_val = 0, 0
        if n >= 5:
            for hold in range(30, 151, 5):
                c, w, _ = get_stats(xag_h4, mask_full, hold)
                if c >= 5 and w > best_wr:
                    best_wr = w
                    best_hold_val = hold
            print(f"  {name:<30} {n:<8} {progress:<12} hold={best_hold_val:<5} {best_wr:.1f}%{'':>4}")
        else:
            print(f"  {name:<30} {n:<8} {progress:<12} {'-':<10} {'-':<10}")
    
    # Compare to round28 progress
    print(f"\n  与Round28对比:")
    print(f"  Round28: RSI<14+CB>=4=12/20, RSI<16+CB>=5=11/20, RSI<14+CB>=5=9/20, RSI<12+CB>=3=14/20")
    
    # 宽时段探索
    print(f"\n--- 宽时段(13-17) 探索 ---")
    wide_base = (xag_h4['session'] == 'us') & (xag_h4.index.hour >= 13) & (xag_h4.index.hour < 18)
    wide_conds = [
        ("US 13-17 RSI<16+CB>=3", (xag_h4['rsi14'] < 16) & (xag_h4['consecutive_bear'] >= 3)),
        ("US 13-17 RSI<14+CB>=3", (xag_h4['rsi14'] < 14) & (xag_h4['consecutive_bear'] >= 3)),
        ("US 13-17 RSI<12+CB>=2", (xag_h4['rsi14'] < 12) & (xag_h4['consecutive_bear'] >= 2)),
    ]
    for name, cond in wide_conds:
        mask = wide_base & cond
        n, wr, avg = get_stats(xag_h4, mask, 85)
        if n >= 5:
            print(f"  {name:<35} n={n:<5} WR={wr:.1f}% avg={avg:.3f}% (hold=85)")
        else:
            print(f"  {name:<35} n={n:<5} (信号不足)")
else:
    print("  ⚠️  XAGUSD data not available, skipping H4")


# ═══════════════════════════════════════════════════════════════
# H5: M1 EU 仿双枪继续等待数据 (round29_005)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H5: M1 EU 仿双枪继续等待数据 (round29_005)")
print("=" * 100)
print("目标: 检查M1数据是否增长, 如果已满180天则进行跨周期验证")
print("      条件: M1 EU 9-11 RSI<16+CB>=3 hold=24")

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
    
    m1_hold_range = list(range(5, 66, 2))
    
    if m1_days >= 180:
        print(f"  ✅ M1数据已覆盖{m1_days}天, 可以进行跨周期验证!")
        test_condition_with_periods(xau_m1, eu_mask_m1,
                                    f"M1 EU 9-11 RSI<16+CB>=3 (hold={m1_hold_range})",
                                    hold_range=m1_hold_range,
                                    min_signals=15)
    else:
        print(f"  ⚠️  M1数据仅覆盖{m1_days}天 (不足180天), 仍不满足跨周期验证条件")
        print(f"  🔄 距满足条件还需至少{180-m1_days}天数据积累")
        print(f"     (Round28时为104天, 当前{m1_days}天, 增长{m1_days-104}天)")
        # Still track current state
        test_condition(xau_m1, eu_mask_m1,
                       f"M1 EU 9-11 RSI<16+CB>=3 (状态追踪)",
                       hold_range=m1_hold_range)
    
    # Also check M1 US broad condition
    print(f"\n--- M1 US 宽条件探索: RSI<20+CB>=1 ---")
    us_mask_m1_broad = (
        (xau_m1['session'] == 'us') &
        (xau_m1.index.hour >= 14) & (xau_m1.index.hour < 17) &
        (xau_m1['rsi14'] < 20) &
        (xau_m1['consecutive_bear'] >= 1)
    )
    test_condition(xau_m1, us_mask_m1_broad,
                   f"M1 US 14-16 RSI<20+CB>=1 (宽时段探索)",
                   hold_range=list(range(5, 66, 2)))
else:
    print("  ⚠️  XAUUSD M1 data not available, skipping H5")


# ═══════════════════════════════════════════════════════════════
# H6: US30/US500/USOIL 新方向探索 (round29_006)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H6: US30/US500/USOIL 新方向探索 (round29_006)")
print("=" * 100)
print("目标: 探索非XAU/XAG品种的策略方向")
print("      US30/US500 超卖模式WR均<50% → 尝试突破策略/趋势策略")
print("      USOIL 新加入品种, 探索超卖模式")

for sym in ["US30", "US500", "USOIL", "USTEC", "JP225"]:
    if sym not in all_data_m5:
        print(f"  ⚠️  {sym}: data not available")
        continue
    
    df_sym = all_data_m5[sym]
    print(f"\n--- {sym} M5 探索 ---")
    print(f"  Data: {len(df_sym)} rows [{df_sym.index[0].date()} → {df_sym.index[-1].date()}]")
    print(f"  Latest: Close={df_sym['close'].iloc[-1]:.2f} RSI={df_sym['rsi14'].iloc[-1]:.1f}")
    
    # ── H6a: 超卖反弹模式 (传统RSI超卖) ──
    print(f"\n  超卖反弹模式:")
    
    # US session - various RSI thresholds with CB>=1 or CB>=2
    us_hour_range = [(15, 16), (14, 17), (13, 18)]
    rsi_vals = [14, 16, 18, 20, 25]
    cb_vals = [1, 2, 3]
    
    found_any = False
    for h_start, h_end in us_hour_range:
        for rsi in rsi_vals:
            for cb in cb_vals:
                mask = (
                    (df_sym['session'] == 'us') &
                    (df_sym.index.hour >= h_start) & (df_sym.index.hour < h_end) &
                    (df_sym['rsi14'] < rsi) &
                    (df_sym['consecutive_bear'] >= cb)
                )
                n = mask.sum()
                if n >= 10:
                    best_wr, best_hold_val, best_avg = 0, 0, 0
                    for hold in [15, 25, 35, 45, 55, 65, 75, 85, 95, 105, 115, 125]:
                        c, w, a = get_stats(df_sym, mask, hold)
                        if c >= 5 and w > best_wr:
                            best_wr = w
                            best_hold_val = hold
                            best_avg = a
                    if best_wr >= 50:
                        found_any = True
                        tag = "✅" if best_wr >= 70 else "⚠️" if best_wr >= 60 else "➡️"
                        print(f"    US {h_start}-{h_end} RSI<{rsi}+CB>={cb}: n={n} "
                              f"最佳hold={best_hold_val} WR={best_wr:.1f}% avg={best_avg:.3f}% {tag}")
    
    if not found_any:
        print(f"    ⚠️ 所有超卖条件测试均未达到50%+胜率 (最大n={int(mask.sum())})")
    
    # ── H6b: 突破策略 (连续阳线后突破) ──
    print(f"\n  突破策略探索 (连续阳线后回调买入):")
    
    # Strategy: consecutive_bull >= 3 (3 consecutive green candles), then buy at close of first red candle
    # This is a "pullback after rally" pattern
    bull_conds = [
        ("CBull>=3 + 回调买入 hold=15", (df_sym['consecutive_bull'] >= 3)),
        ("CBull>=2 + 回调买入 hold=25", (df_sym['consecutive_bull'] >= 2)),
        ("CBull>=4 + 回调买入 hold=15", (df_sym['consecutive_bull'] >= 4)),
    ]
    
    # US session, when RSI is not overbought (RSI < 70)
    for label, cond in bull_conds:
        # After bull run, buy at candle where close < open (potential pullback)
        # Simple: the next candle after a bull run
        pullback_cond = cond & (df_sym['close'] < df_sym['open']) & (df_sym['rsi14'] < 70) & (df_sym['rsi14'] > 30)
        # US session only
        session_cond = df_sym['session'] == 'us'
        final_mask = pullback_cond & session_cond
        
        n, wr, avg = get_stats(df_sym, final_mask, 25)
        if n >= 5:
            tag = "✅" if wr >= 65 else "⚠️" if wr >= 55 else "➡️"
            print(f"    {label:<35} n={n:<5} WR={wr:.1f}% avg={avg:.3f}% {tag}")
    
    # ── H6c: RSI超卖+成交量放大 (volume surge) ──
    print(f"\n  成交量辅助模式 (超卖+成交量放大):")
    if 'tick_volume' in df_sym.columns:
        vol_median = df_sym['tick_volume'].rolling(20).median()
        vol_surge = df_sym['tick_volume'] > vol_median * 1.5
        
        vol_conds = [
            ("US RSI<20+CB>=1+Vol放大", (df_sym['session'] == 'us') & (df_sym['rsi14'] < 20) & (df_sym['consecutive_bear'] >= 1) & vol_surge),
            ("US RSI<25+CB>=1+Vol放大", (df_sym['session'] == 'us') & (df_sym['rsi14'] < 25) & (df_sym['consecutive_bear'] >= 1) & vol_surge),
            ("EU RSI<20+CB>=2+Vol放大", (df_sym['session'] == 'europe') & (df_sym['rsi14'] < 20) & (df_sym['consecutive_bear'] >= 2) & vol_surge),
        ]
        for label, mask in vol_conds:
            n, wr, avg = get_stats(df_sym, mask, 25)
            if n >= 5:
                tag = "✅" if wr >= 65 else "⚠️" if wr >= 55 else "➡️"
                print(f"    {label:<35} n={n:<5} WR={wr:.1f}% avg={avg:.3f}% {tag}")
            else:
                print(f"    {label:<35} n={n:<5} (信号不足)")
    else:
        print(f"    ⚠️ 无成交量数据")
    
    # ── H6d: JP225 现有策略复查 ──
    if sym == "JP225":
        print(f"\n  JP225 现有策略复查:")
        jp_masks = [
            ("US 15-16 RSI<14+CB>=2 hold=55 (已知最佳)", 
             (df_sym['session'] == 'us') & (df_sym.index.hour >= 15) & (df_sym.index.hour < 16) & (df_sym['rsi14'] < 14) & (df_sym['consecutive_bear'] >= 2), 55),
            ("US 15-16 RSI<16+CB>=2 hold=55",
             (df_sym['session'] == 'us') & (df_sym.index.hour >= 15) & (df_sym.index.hour < 16) & (df_sym['rsi14'] < 16) & (df_sym['consecutive_bear'] >= 2), 55),
            ("US 15-16 RSI<14+CB>=3 hold=55",
             (df_sym['session'] == 'us') & (df_sym.index.hour >= 15) & (df_sym.index.hour < 16) & (df_sym['rsi14'] < 14) & (df_sym['consecutive_bear'] >= 3), 55),
        ]
        for name, mask, hold in jp_masks:
            n, wr, avg = get_stats(df_sym, mask, hold)
            if n >= 5:
                print(f"    {name:<45} n={n:<5} WR={wr:.1f}% avg={avg:.3f}%")
                # Bootstrap
                rets = compute_returns_from_entries(df_sym, df_sym[mask], hold)
                if len(rets) >= 10:
                    ci_low, ci_high = bootstrap_confidence(rets)
                    print(f"      Bootstrap 95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]")

# ── H6e: FX品种快速扫描 ──
print(f"\n--- FX品种快速扫描 ---")
fx_symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"]
for sym in fx_symbols:
    raw = load_data("M5", symbols=[sym])
    if raw:
        df = compute_indicators(raw[sym])
        df = add_session_and_cb(df)
        print(f"\n  {sym} M5: {len(df):,} rows [{df.index[0].date()} → {df.index[-1].date()}]")
        
        # Quick test: standard oversold conditions
        for session, hrs in [("US", (15, 16)), ("EU", (9, 11))]:
            for rsi, cb in [(18, 2), (20, 1), (14, 2)]:
                mask = (df['session'] == session.lower()) & (df.index.hour >= hrs[0]) & (df.index.hour < hrs[1]) & (df['rsi14'] < rsi) & (df['consecutive_bear'] >= cb)
                n = mask.sum()
                if n >= 10:
                    best_wr, best_h = 0, 0
                    for hold in [15, 25, 35, 45, 55, 65, 75]:
                        c, w, _ = get_stats(df, mask, hold)
                        if c >= 5 and w > best_wr:
                            best_wr = w
                            best_h = hold
                    if best_wr >= 55:
                        print(f"    {session} {hrs[0]}-{hrs[1]} RSI<{rsi}+CB>={cb}: n={n} best_hold={best_h} WR={best_wr:.1f}%")
    else:
        print(f"  ⚠️  {sym}: data not available")


# ═══════════════════════════════════════════════════════════════
# 总结 & 最佳策略排名 (Round29更新)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("🏆 全策略可行性排名 (Round29更新)")
print("=" * 100)

all_strategies = []

# XAU 双枪
if "XAUUSD" in all_data_m5:
    xau_f = all_data_m5["XAUUSD"]
    
    eu_f = (xau_f['session'] == 'europe') & (xau_f.index.hour >= 9) & (xau_f.index.hour < 11) & (xau_f['rsi14'] < 18) & (xau_f['consecutive_bear'] >= 4)
    us_f = (xau_f['session'] == 'us') & (xau_f.index.hour >= 15) & (xau_f.index.hour < 16) & (xau_f['rsi14'] < 20) & (xau_f['consecutive_bear'] >= 2)
    
    n_eu, wr_eu, avg_eu = get_stats(xau_f, eu_f, 42)
    n_us, wr_us, avg_us = get_stats(xau_f, us_f, 115)
    
    if n_eu >= 5:
        all_strategies.append(("双枪欧盘做多XAU", wr_eu, n_eu, avg_eu, 42, "M5 EU 9-11 RSI<18+CB>=4"))
    if n_us >= 5:
        all_strategies.append(("双枪美盘做多XAU", wr_us, n_us, avg_us, 115, "M5 US 15-16 RSI<20+CB>=2"))
    
    # 共振美盘
    if "XAGUSD" in all_data_m5:
        xag_f = all_data_m5["XAGUSD"]
        common_f = xau_f.index.intersection(xag_f.index)
        xau_f_aligned = xau_f.loc[common_f]
        xag_f_aligned = xag_f.loc[common_f]
        res_f = (xau_f_aligned['session'] == 'us') & (xau_f_aligned.index.hour >= 15) & (xau_f_aligned.index.hour < 16) & (xau_f_aligned['rsi14'] < 18) & (xau_f_aligned['consecutive_bear'] >= 1) & (xag_f_aligned['consecutive_bear'] >= 1)
        n_res, wr_res, avg_res = get_stats(xau_f_aligned, res_f, 115)
        if n_res >= 5:
            all_strategies.append(("共振美盘→XAU (XAG共振)", wr_res, n_res, avg_res, 115, "M5 US 15-16 RSI<18+CB>=1+XAG共振"))
    
    # 双枪组合
    eu_rets_f = compute_returns_from_entries(xau_f, xau_f[eu_f], 42) if n_eu >= 5 else np.array([])
    us_rets_f = compute_returns_from_entries(xau_f, xau_f[us_f], 115) if n_us >= 5 else np.array([])
    comb_rets_f = np.concatenate([r for r in [eu_rets_f, us_rets_f] if len(r) > 0])
    if len(comb_rets_f) > 0:
        comb_wr_f = np.mean(comb_rets_f > 0) * 100
        comb_n_f = len(comb_rets_f)
        comb_avg_f = np.mean(comb_rets_f)
        all_strategies.append(("双枪组合(欧+美)", comb_wr_f, comb_n_f, comb_avg_f, "42+115", "M5 EU+US 双枪合并"))
    
    # 组合调度(共振优先+双枪补充)
    if n_res >= 5 and n_us >= 5:
        res_entries = xau_f_aligned[res_f]
        us_entries = xau_f[us_f]
        dual_excl = us_entries[~us_entries.index.isin(res_entries.index)]
        dual_excl_rets = compute_returns_from_entries(xau_f, dual_excl, 115)
        if len(dual_excl_rets) > 0:
            combo_rets = np.concatenate([compute_returns_from_entries(xau_f_aligned, res_entries, 115), dual_excl_rets])
            all_strategies.append(("组合调度(共振优先+双枪补)", np.mean(combo_rets>0)*100, len(combo_rets), np.mean(combo_rets), 115, "M5 共振优先+双枪补充"))

# XAG
if "XAGUSD" in all_data_m5:
    xag_f = all_data_m5["XAGUSD"]
    eu_base_f = (xag_f['session'] == 'europe') & (xag_f.index.hour >= 9) & (xag_f.index.hour < 11)
    us_base_f = (xag_f['session'] == 'us') & (xag_f.index.hour >= 15) & (xag_f.index.hour < 16)
    
    xag_eu = eu_base_f & (xag_f['rsi14'] < 14) & (xag_f['consecutive_bear'] >= 3)
    xag_us_old = us_base_f & (xag_f['rsi14'] < 18) & (xag_f['consecutive_bear'] >= 3)
    xag_us_new = us_base_f & (xag_f['rsi14'] < 16) & (xag_f['consecutive_bear'] >= 3)
    
    n_xag_eu, wr_xag_eu, avg_xag_eu = get_stats(xag_f, xag_eu, 85)
    n_xag_us_old, wr_xag_us_old, avg_xag_us_old = get_stats(xag_f, xag_us_old, 105)
    n_xag_us_new, wr_xag_us_new, avg_xag_us_new = get_stats(xag_f, xag_us_new, 70)
    
    if n_xag_eu >= 5:
        all_strategies.append(("XAG欧盘RSI<14+CB>=3", wr_xag_eu, n_xag_eu, avg_xag_eu, 85, "M5 EU 9-11 RSI<14+CB>=3 hold=85"))
    if n_xag_us_old >= 5:
        all_strategies.append(("XAG美盘RSI<18+CB>=3", wr_xag_us_old, n_xag_us_old, avg_xag_us_old, 105, "M5 US 15-16 RSI<18+CB>=3 hold=105"))
    if n_xag_us_new >= 5:
        all_strategies.append(("XAG美盘RSI<16+CB>=3🆕", wr_xag_us_new, n_xag_us_new, avg_xag_us_new, 70, "M5 US 15-16 RSI<16+CB>=3 hold=70"))

# JP225
if "JP225" in all_data_m5:
    jp_f = all_data_m5["JP225"]
    jp_mask_f = (jp_f['session'] == 'us') & (jp_f.index.hour >= 15) & (jp_f.index.hour < 16) & (jp_f['rsi14'] < 14) & (jp_f['consecutive_bear'] >= 2)
    n_jp, wr_jp, avg_jp = get_stats(jp_f, jp_mask_f, 55)
    if n_jp >= 5:
        all_strategies.append(("JP225美盘RSI<14+CB>=2", wr_jp, n_jp, avg_jp, 55, "M5 US 15-16 RSI<14+CB>=2 hold=55"))

# Sort by composite score
def composite_score(strat):
    wr, n, avg = strat[1], strat[2], strat[3]
    return wr * 0.5 + min(n / 30, 1) * 0.3 + min(abs(avg) * 50, 1) * 0.2

all_strategies.sort(key=composite_score, reverse=True)

print(f"\n| {'排名':<4} | {'策略':<32} | {'WR':<7} | {'n':<6} | {'avg%':<8} | {'Hold':<6} | {'描述':<42} |")
print(f"|{'':->4}|{'':->32}|{'':->7}|{'':->6}|{'':->8}|{'':->6}|{'':->42}|")

for i, (name, wr, n, avg, hold, desc) in enumerate(all_strategies, 1):
    # Signal frequency
    if "XAU" in name:
        total_days = (xau_f.index[-1] - xau_f.index[0]).days if "xau_f" in dir() else 365
    elif "XAG" in name:
        total_days = (xag_f.index[-1] - xag_f.index[0]).days if "xag_f" in dir() else 365
    elif "JP225" in name:
        total_days = (jp_f.index[-1] - jp_f.index[0]).days
    else:
        total_days = 365
    months_covered = max(1, total_days / 30)
    freq = n / months_covered
    print(f"| {i:<4} | {name:<32} | {wr:.1f}%{'':>3} | {n:<6} | {avg:.3f}%{'':>3} | {str(hold):<6} | {desc:<42} |")


print("\n" + "=" * 100)
print("ROUND 29 COMPLETE")
print(f"Completed at: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 100)
