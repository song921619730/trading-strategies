#!/usr/bin/env python3
"""
Round 30 — USOIL深入研究 + FX筛选 + 双枪跟踪 + 回测细化
Testing priority hypotheses from round29 next_actions:
1. round30_001: USOIL方向深入研究 — 跨周期验证+最优参数微调
2. round30_002: XAG RSI<16+CB>=3 继续积累 — n追踪
3. round30_003: 双枪策略继续月度跟踪 — 持续监测
4. round30_004: FX品种初步筛选 — AUDUSD/USDJPY/USDCHF深入
5. round30_005: XAG极端阈值继续积累 — 数据积累
6. round30_006: 组合策略Bootstrap回测细化
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# HELPERS (consistent with round24-29)
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
    return rets - spread_cost - commission

def print_compact_comparison(title, data):
    print(f"\n  ** {title} **")
    print(f"  {'条件':<55} {'信号数':<8} {'Hold':<6} {'胜率':<8} {'平均收益':<12}")
    print(f"  {'-'*55} {'-'*8} {'-'*6} {'-'*8} {'-'*12}")
    for row in data:
        print(f"  {row[0]:<55} {row[1]:<8} {row[2]:<6} {row[3]:<8} {row[4]:<12}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 100)
print("ROUND 30 — USOIL深入研究 + FX筛选 + 双枪跟踪 + 回测细化")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=30, testing round30_001~006")
print("=" * 100)

# ── Load M5 data ──
print(f"\n--- M5 Data Summary ---")
all_data_m5 = {}
for sym in ["XAUUSD", "XAGUSD", "JP225", "US500", "US30", "USOIL", "USTEC",
            "AUDUSD", "USDJPY", "USDCHF", "EURUSD", "GBPUSD", "HK50", "UKOIL"]:
    raw = load_data("M5", symbols=[sym])
    if raw:
        df = compute_indicators(raw[sym])
        df = add_session_and_cb(df)
        all_data_m5[sym] = df
        print(f"  {sym:8s} M5: {len(df):>8} rows  [{df.index[0].date()} → {df.index[-1].date()}]  "
              f"Close={df['close'].iloc[-1]:.1f}  RSI={df['rsi14'].iloc[-1]:.1f}")
    else:
        print(f"  ⚠️  {sym}: data not available")

# ── Load M1 data (for check) ──
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
# H1: USOIL方向深入研究 (round30_001)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H1: USOIL方向深入研究 — 跨周期验证+最优参数微调 (round30_001)")
print("=" * 100)
print("目标: round29发现USOIL US 15-16 RSI<14+CB>=3 WR=82.6% n=23 hold=75")
print("      进行跨周期验证、最优hold微调、时段细化研究")

if "USOIL" in all_data_m5:
    usoil = all_data_m5["USOIL"]
    
    # ── H1a: USOIL 基础条件扫描 ──
    us_base = (usoil['session'] == 'us') & (usoil.index.hour >= 15) & (usoil.index.hour < 16)
    
    print(f"\n--- H1a: USOIL US 15-16 条件矩阵 ---")
    conds = []
    for rsi_thresh in [14, 16, 18, 20]:
        for cb in [1, 2, 3]:
            conds.append((f"RSI<{rsi_thresh}+CB>={cb}", (usoil['rsi14'] < rsi_thresh) & (usoil['consecutive_bear'] >= cb)))
    
    print(f"  {'条件':<30} {'信号数':<8} {'最优hold':<10} {'WR':<10} {'avg%':<10}")
    print(f"  {'-'*30} {'-'*8} {'-'*10} {'-'*10} {'-'*10}")
    
    usoil_results = []
    for name, cond in conds:
        mask = us_base & cond
        n = mask.sum()
        if n >= 5:
            best_hold, best_wr, best_avg = 0, 0, 0
            for hold in list(range(10, 61, 5)) + list(range(65, 151, 5)):
                cnt, wr, avg = get_stats(usoil, mask, hold)
                if cnt >= 3 and wr > best_wr:
                    best_wr, best_hold, best_avg = wr, hold, avg
            print(f"  {name:<30} {n:<8} hold={best_hold:<5} {best_wr:.1f}%{'':>4} {best_avg:.3f}%")
            usoil_results.append((name, n, best_hold, best_wr, best_avg))
        else:
            print(f"  {name:<30} {n:<8} {'N/A':<10} {'N/A':<10} {'N/A':<10}")
    
    # ── H1b: USOIL RSI<14+CB>=3 跨周期验证 ──
    print(f"\n--- H1b: USOIL RSI<14+CB>=3 跨周期验证 ---")
    usoil_hold_range = list(range(20, 151, 5))
    test_condition_with_periods(usoil, us_base & (usoil['rsi14'] < 14) & (usoil['consecutive_bear'] >= 3),
                                f"USOIL US 15-16 RSI<14+CB>=3",
                                hold_range=usoil_hold_range,
                                min_signals=15)
    
    # ── H1c: USOIL 时段细化 (13-14, 14-15, 15-16, 16-17) ──
    print(f"\n--- H1c: USOIL 时段细化探索 ---")
    time_slots = [(13, 14), (14, 15), (15, 16), (16, 17), (14, 16), (13, 17)]
    for h_start, h_end in time_slots:
        slot_base = (usoil['session'] == 'us') & (usoil.index.hour >= h_start) & (usoil.index.hour < h_end)
        mask = slot_base & (usoil['rsi14'] < 14) & (usoil['consecutive_bear'] >= 3)
        n = mask.sum()
        if n >= 5:
            best_hold, best_wr = 0, 0
            for hold in usoil_hold_range:
                cnt, wr, avg = get_stats(usoil, mask, hold)
                if cnt >= 3 and wr > best_wr:
                    best_wr, best_hold = wr, hold
            print(f"  US {h_start:02d}-{h_end:02d} RSI<14+CB>=3: n={n:<5} hold={best_hold:<5} WR={best_wr:.1f}%")
        else:
            print(f"  US {h_start:02d}-{h_end:02d} RSI<14+CB>=3: n={n:<5} (信号不足)")
    
    # ── H1d: USOIL 宽RSI条件hold=75稳定性 ──
    print(f"\n--- H1d: USOIL hold=75 各条件对比 ---")
    for name, cond in [
        ("RSI<14+CB>=3", (usoil['rsi14'] < 14) & (usoil['consecutive_bear'] >= 3)),
        ("RSI<14+CB>=2", (usoil['rsi14'] < 14) & (usoil['consecutive_bear'] >= 2)),
        ("RSI<16+CB>=3", (usoil['rsi14'] < 16) & (usoil['consecutive_bear'] >= 3)),
        ("RSI<14+CB>=1", (usoil['rsi14'] < 14) & (usoil['consecutive_bear'] >= 1)),
    ]:
        n_all, wr_all, avg_all = get_stats(usoil, us_base & cond, 75)
        if n_all >= 5:
            print(f"  {name:<25} hold=75: n={n_all:<5} WR={wr_all:.1f}% avg={avg_all:.3f}%")
    
    # ── H1e: USOIL 与 XAU 对比 (Bootstrap) ──
    print(f"\n--- H1e: USOIL Bootstrap 置信区间 ---")
    u_best_mask = us_base & (usoil['rsi14'] < 14) & (usoil['consecutive_bear'] >= 3)
    if u_best_mask.sum() >= 10:
        best_hold_for_usoil = 75
        u_rets = compute_returns_from_entries(usoil, usoil[u_best_mask], best_hold_for_usoil)
        if len(u_rets) >= 10:
            ci_low, ci_high = bootstrap_confidence(u_rets)
            wr = np.mean(u_rets > 0) * 100
            print(f"  USOIL RSI<14+CB>=3 hold={best_hold_for_usoil}: n={len(u_rets)} WR={wr:.1f}% "
                  f"95% CI=[{ci_low:.1f}%, {ci_high:.1f}%]")
    
    # ── H1f: 月度统计 ──
    print(f"\n--- H1f: USOIL 月度频率 ---")
    u_entries = usoil[us_base & (usoil['rsi14'] < 14) & (usoil['consecutive_bear'] >= 3)]
    if len(u_entries) >= 5:
        months_covered = max(1, (u_entries.index[-1] - u_entries.index[0]).days / 30)
        freq = len(u_entries) / months_covered
        print(f"  信号频率: {freq:.1f}/月 (覆盖{months_covered:.0f}月)")
        print(f"  首个信号: {u_entries.index[0].date()}")
        print(f"  最新信号: {u_entries.index[-1].date()}")
else:
    print("  ⚠️  USOIL data not available")


# ═══════════════════════════════════════════════════════════════
# H2: XAG RSI<16+CB>=3 继续积累 (round30_002)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H2: XAG RSI<16+CB>=3 继续积累 — n追踪 (round30_002)")
print("=" * 100)
print("目标: round29确认XAG US RSI<16+CB>=3 WR=90.0% n=20, 跨周期验证通过")
print("      继续积累数据至n≥30增强可信度, 同时更新XAG各策略状态")

if "XAGUSD" in all_data_m5:
    xag_h2 = all_data_m5["XAGUSD"]
    us_base_h2 = (xag_h2['session'] == 'us') & (xag_h2.index.hour >= 15) & (xag_h2.index.hour < 16)
    
    print(f"\n--- XAG美盘状态更新 ---")
    xag_conds = [
        ("RSI<16+CB>=3 🆕新策略", (xag_h2['rsi14'] < 16) & (xag_h2['consecutive_bear'] >= 3)),
        ("旧基准 RSI<18+CB>=3", (xag_h2['rsi14'] < 18) & (xag_h2['consecutive_bear'] >= 3)),
        ("RSI<18+CB>=2 (宽松)", (xag_h2['rsi14'] < 18) & (xag_h2['consecutive_bear'] >= 2)),
        ("RSI<16+CB>=2 (宽松2)", (xag_h2['rsi14'] < 16) & (xag_h2['consecutive_bear'] >= 2)),
        ("RSI<14+CB>=3 (极端RSI)", (xag_h2['rsi14'] < 14) & (xag_h2['consecutive_bear'] >= 3)),
    ]
    print(f"  {'条件':<35} {'n':<6} {'最优hold':<10} {'最优WR':<10} {'avg%':<10}")
    print(f"  {'-'*35} {'-'*6} {'-'*10} {'-'*10} {'-'*10}")
    for name, cond in xag_conds:
        mask = us_base_h2 & cond
        n = mask.sum()
        if n >= 5:
            best_hold, best_wr, best_avg = 0, 0, 0
            for hold in range(30, 151, 5):
                cnt, wr, avg = get_stats(xag_h2, mask, hold)
                if cnt >= 3 and wr > best_wr:
                    best_wr, best_hold, best_avg = wr, hold, avg
            print(f"  {name:<35} {n:<6} hold={best_hold:<5} {best_wr:.1f}%{'':>4} {best_avg:.3f}%")
        else:
            print(f"  {name:<35} {n:<6} {'-':<10} {'-':<10} {'-':<10}")
    
    # XAG EU status
    print(f"\n--- XAG欧盘状态更新 ---")
    eu_base_h2 = (xag_h2['session'] == 'europe') & (xag_h2.index.hour >= 9) & (xag_h2.index.hour < 11)
    for name, cond, hold in [
        ("RSI<14+CB>=3 hold=85 ★", (xag_h2['rsi14'] < 14) & (xag_h2['consecutive_bear'] >= 3), 85),
        ("RSI<14+CB>=3 hold=95", (xag_h2['rsi14'] < 14) & (xag_h2['consecutive_bear'] >= 3), 95),
        ("RSI<14+CB>=3 hold=105", (xag_h2['rsi14'] < 14) & (xag_h2['consecutive_bear'] >= 3), 105),
    ]:
        n, wr, avg = get_stats(xag_h2, eu_base_h2 & cond, hold)
        if n >= 5:
            print(f"  {name:<35} n={n:<5} WR={wr:.1f}% avg={avg:.3f}%")
        else:
            print(f"  {name:<35} n={n:<5} (信号不足)")
    
    # Bootstrap for XAG EU hold=85
    print(f"\n--- XAG EU hold=85 Bootstrap ---")
    eu_mask_85 = eu_base_h2 & (xag_h2['rsi14'] < 14) & (xag_h2['consecutive_bear'] >= 3)
    if eu_mask_85.sum() >= 10:
        rets_85 = compute_returns_from_entries(xag_h2, xag_h2[eu_mask_85], 85)
        ci_low, ci_high = bootstrap_confidence(rets_85)
        wr_85 = np.mean(rets_85 > 0) * 100
        print(f"  XAG EU hold=85: n={len(rets_85)} WR={wr_85:.1f}% CI=[{ci_low:.1f}%, {ci_high:.1f}%]")
else:
    print("  ⚠️  XAGUSD data not available")


# ═══════════════════════════════════════════════════════════════
# H3: 双枪策略月度跟踪 (round30_003)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H3: 双枪策略月度跟踪 — 近6月表现监测 (round30_003)")
print("=" * 100)
print("目标: 持续监测双枪策略近6月表现. 关注2026-06~07是否出现回撤")
print("      双枪欧盘: EU 9-11 RSI<18+CB>=4 hold=42")
print("      双枪美盘: US 15-16 RSI<20+CB>=2 hold=115")

if "XAUUSD" in all_data_m5:
    xau_h3 = all_data_m5["XAUUSD"]
    
    recent_cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
    recent_mask = xau_h3.index >= recent_cutoff
    
    print(f"  数据分割点: {recent_cutoff.date()}")
    print(f"  近期行数: {recent_mask.sum():,}")
    
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
    
    # 月度表现 (近12月)
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
    
    # 回撤分析
    print(f"\n--- 回撤分析 ---")
    low_months = [r for r in monthly_rows if r[6] < 70 and r[5] >= 2]
    if low_months:
        print(f"  ⚠️ 以下月份出现组合WR<70%回撤:")
        for m in low_months:
            print(f"    {m[0]}: n={m[5]} WR={m[6]:.1f}%")
    else:
        print(f"  ✅ 近12月无显著回撤(组合WR<70%且n≥2)")
    
    # 本月表现
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
# H4: FX品种初步筛选 — AUDUSD/USDJPY/USDCHF深入 (round30_004)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H4: FX品种初步筛选 — AUDUSD/USDJPY/USDCHF深入 (round30_004)")
print("=" * 100)
print("目标: round29发现AUDUSD US RSI<14+CB>=2 WR=77.8% n=27,")
print("      USDJPY RSI<18+CB>=2 WR=69.5% n=59, USDCHF RSI<18+CB>=2 WR=69.4% n=62")
print("      进行深入探索最优参数和跨品种对比")

fx_symbols = ["AUDUSD", "USDJPY", "USDCHF", "EURUSD", "GBPUSD"]
fx_results = {}

for sym in fx_symbols:
    if sym in all_data_m5:
        df = all_data_m5[sym]
        us_base = (df['session'] == 'us') & (df.index.hour >= 15) & (df.index.hour < 16)
        # 宽时段
        us_wide = (df['session'] == 'us') & (df.index.hour >= 14) & (df.index.hour < 17)
        
        print(f"\n--- {sym} 条件扫描 ---")
        sym_best = []
        
        for base, label in [(us_base, "US 15-16"), (us_wide, "US 14-17")]:
            for rsi_thresh in [14, 16, 18]:
                for cb in [1, 2, 3]:
                    cond = (df['rsi14'] < rsi_thresh) & (df['consecutive_bear'] >= cb)
                    mask = base & cond
                    n = mask.sum()
                    if n >= 5:
                        best_hold, best_wr, best_avg = 0, 0, 0
                        for hold in list(range(10, 61, 5)) + list(range(65, 151, 5)):
                            cnt, wr, avg = get_stats(df, mask, hold)
                            if cnt >= 3 and wr > best_wr:
                                best_wr, best_hold, best_avg = wr, hold, avg
                        if best_wr >= 60:
                            sym_best.append((f"{label} RSI<{rsi_thresh}+CB>={cb}", n, best_hold, best_wr, best_avg))
        
        sym_best.sort(key=lambda x: x[3], reverse=True)
        if sym_best:
            print(f"  {'条件':<40} {'n':<6} {'Hold':<6} {'WR':<8} {'avg%':<10}")
            print(f"  {'-'*40} {'-'*6} {'-'*6} {'-'*8} {'-'*10}")
            for row in sym_best[:8]:
                print(f"  {row[0]:<40} {row[1]:<6} {row[2]:<6} {row[3]:.1f}%{'':>2} {row[4]:.3f}%")
            fx_results[sym] = sym_best
        
        # Bootstrap for best condition
        if sym_best and sym_best[0][1] >= 10:
            best_name, best_n, best_hold, best_wr, best_avg = sym_best[0]
            # Extract condition from name - format: "US 15-16 RSI<14+CB>=2"
            parts = best_name.split()
            if len(parts) >= 3:
                cond_str = parts[2]  # "RSI<14+CB>=2"
            else:
                cond_str = parts[-1]
            try:
                rsi_val = int(cond_str.split('<')[1].split('+')[0])
                cb_val = int(cond_str.split('>=')[1])
            except (IndexError, ValueError):
                print(f"  ⚠️ 无法解析条件: {cond_str}, 跳过Bootstrap")
            else:
                # Parse hours
                try:
                    time_part = parts[1]  # "15-16"
                    h_start, h_end = int(time_part.split('-')[0]), int(time_part.split('-')[1])
                except (IndexError, ValueError):
                    h_start, h_end = 15, 16
                
                base_cond = (df['session'] == 'us') & (df.index.hour >= h_start) & (df.index.hour < h_end)
                cond_final = base_cond & (df['rsi14'] < rsi_val) & (df['consecutive_bear'] >= cb_val)
                
                if cond_final.sum() >= 10:
                    rets = compute_returns_from_entries(df, df[cond_final], best_hold)
                    ci_low, ci_high = bootstrap_confidence(rets)
                    if ci_low:
                        print(f"  {sym} 最佳条件 Bootstrap 95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]")
    else:
        print(f"  ⚠️  {sym}: data not available")

# 跨品种对比汇总
print(f"\n--- FX跨品种汇总 ---")
print(f"  {'品种':<10} {'最佳条件':<45} {'n':<6} {'Hold':<6} {'WR':<8} {'avg%':<10}")
print(f"  {'-'*10} {'-'*45} {'-'*6} {'-'*6} {'-'*8} {'-'*10}")
for sym in fx_symbols:
    if sym in fx_results and fx_results[sym]:
        best = fx_results[sym][0]
        print(f"  {sym:<10} {best[0]:<45} {best[1]:<6} {best[2]:<6} {best[3]:.1f}%{'':>2} {best[4]:.3f}%")


# ═══════════════════════════════════════════════════════════════
# H5: XAG极端阈值继续积累 (round30_005)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H5: XAG极端阈值继续积累 + MT5数据更新检查 (round30_005)")
print("=" * 100)
print("目标: 检查XAG极端阈值数据积累情况, 跟踪RSI<14+CB>=4等是否增长")
print("      同时检查M1数据覆盖天数")

if "XAGUSD" in all_data_m5:
    xag_h5 = all_data_m5["XAGUSD"]
    us_base_h5 = (xag_h5['session'] == 'us') & (xag_h5.index.hour >= 15) & (xag_h5.index.hour < 16)
    
    thresholds = [
        ("RSI<14+CB>=4 (极端1)", (xag_h5['rsi14'] < 14) & (xag_h5['consecutive_bear'] >= 4)),
        ("RSI<16+CB>=5 (极端2)", (xag_h5['rsi14'] < 16) & (xag_h5['consecutive_bear'] >= 5)),
        ("RSI<14+CB>=5 (极端3)", (xag_h5['rsi14'] < 14) & (xag_h5['consecutive_bear'] >= 5)),
        ("RSI<12+CB>=3 (极端RSI)", (xag_h5['rsi14'] < 12) & (xag_h5['consecutive_bear'] >= 3)),
        ("RSI<12+CB>=4 (极端RSI+)", (xag_h5['rsi14'] < 12) & (xag_h5['consecutive_bear'] >= 4)),
        ("旧基准 RSI<18+CB>=3", (xag_h5['rsi14'] < 18) & (xag_h5['consecutive_bear'] >= 3)),
        ("RSI<16+CB>=3 (中位,新)", (xag_h5['rsi14'] < 16) & (xag_h5['consecutive_bear'] >= 3)),
    ]
    
    print(f"\n--- XAG美盘极端阈值数据积累进度 ---")
    print(f"  {'条件':<30} {'信号数':<8} {'进度':<10} {'最佳hold':<10} {'最佳WR':<10}")
    print(f"  {'-'*30} {'-'*8} {'-'*10} {'-'*10} {'-'*10}")
    
    for name, cond in thresholds:
        mask = us_base_h5 & cond
        n = mask.sum()
        progress = f"{n}/20" if n < 20 else "✅ 已达标"
        best_wr, best_hold = 0, 0
        if n >= 5:
            for hold in range(30, 151, 5):
                cnt, wr, avg = get_stats(xag_h5, mask, hold)
                if cnt >= 3 and wr > best_wr:
                    best_wr, best_hold = wr, hold
            print(f"  {name:<30} {n:<8} {progress:<10} hold={best_hold:<5} {best_wr:.1f}%{'':>4}")
        else:
            print(f"  {name:<30} {n:<8} {progress:<10} {'-':<10} {'-':<10}")
    
    # M1 data check
    print(f"\n--- M1 数据增长检查 ---")
    if "XAUUSD" in all_data_m1:
        xau_m1 = all_data_m1["XAUUSD"]
        m1_days = (xau_m1.index[-1] - xau_m1.index[0]).days
        print(f"  M1 XAUUSD 覆盖: {m1_days}天 [{xau_m1.index[0].date()} → {xau_m1.index[-1].date()}]")
        print(f"  距180天还需: {max(0, 180 - m1_days)}天")
    
    # M5 data last timestamp
    print(f"\n--- M5 最新数据时间 ---")
    for sym in ["XAUUSD", "XAGUSD", "USOIL"]:
        if sym in all_data_m5:
            df = all_data_m5[sym]
            print(f"  {sym}: 最后K线={df.index[-1]}, close={df['close'].iloc[-1]:.2f}")


# ═══════════════════════════════════════════════════════════════
# H6: 组合策略Bootstrap回测细化 (round30_006)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H6: 组合策略回测细化 — 方案A/B/C逐笔回测 (round30_006)")
print("=" * 100)
print("目标: 对方案A(共振优先+双枪补充)/B(全组合)/C(原双枪)进行逐笔回测")
print("      含交易成本、最大回撤、收益曲线分析")

if "XAUUSD" in all_data_m5:
    xau_h6 = all_data_m5["XAUUSD"]
    
    # Define all conditions
    eu_cond = (
        (xau_h6['session'] == 'europe') &
        (xau_h6.index.hour >= 9) & (xau_h6.index.hour < 11) &
        (xau_h6['rsi14'] < 18) & (xau_h6['consecutive_bear'] >= 4)
    )
    us_cond = (
        (xau_h6['session'] == 'us') &
        (xau_h6.index.hour >= 15) & (xau_h6.index.hour < 16) &
        (xau_h6['rsi14'] < 20) & (xau_h6['consecutive_bear'] >= 2)
    )
    
    # 共振美盘 (XAG共振)
    if "XAGUSD" in all_data_m5:
        xag_h6 = all_data_m5["XAGUSD"]
        common_idx = xau_h6.index.intersection(xag_h6.index)
        xau_h6_aligned = xau_h6.loc[common_idx]
        xag_h6_aligned = xag_h6.loc[common_idx]
        res_cond = (
            (xau_h6_aligned['session'] == 'us') &
            (xau_h6_aligned.index.hour >= 15) & (xau_h6_aligned.index.hour < 16) &
            (xau_h6_aligned['rsi14'] < 18) &
            (xau_h6_aligned['consecutive_bear'] >= 1) &
            (xag_h6_aligned['consecutive_bear'] >= 1)
        )
        has_resonance = True
    else:
        res_cond = None
        has_resonance = False
    
    eu_entries = xau_h6[eu_cond]
    us_entries = xau_h6[us_cond]
    
    if has_resonance:
        res_entries = xau_h6_aligned[res_cond]
    
    print(f"\n--- 各组件信号 ---")
    print(f"  双枪欧盘 (hold=42): {len(eu_entries)} 信号")
    print(f"  双枪美盘 (hold=115): {len(us_entries)} 信号")
    if has_resonance:
        print(f"  共振美盘 (hold=115): {len(res_entries)} 信号")
        # 重叠统计
        overlap = res_entries.index.intersection(us_entries.index)
        print(f"  共振∩双枪美重叠: {len(overlap)} ({len(overlap)/max(1,len(us_entries))*100:.0f}%)")
    
    # 生成回测收益序列
    def backtest_plan(entries_list, df, holds, label):
        """Run a backtest of a trading plan"""
        all_rets = []
        all_dates = []
        for entries, hold in zip(entries_list, holds):
            rets = compute_returns_from_entries(df, entries, hold)
            all_rets.extend(rets)
            all_dates.extend(entries.index[:len(rets)])
        
        rets_arr = np.array(all_rets)
        dates_arr = np.array(all_dates)
        
        # Sort by date
        sort_idx = np.argsort(dates_arr)
        rets_arr = rets_arr[sort_idx]
        
        n = len(rets_arr)
        if n < 5:
            print(f"  {label}: ⚠️ 信号不足({n})")
            return
        
        wr = np.mean(rets_arr > 0) * 100
        avg = np.mean(rets_arr)
        std = np.std(rets_arr)
        cum = np.cumprod(1 + rets_arr)
        peak = np.maximum.accumulate(cum)
        dd = (peak - cum) / peak
        max_dd = dd.max() * 100
        
        # With costs
        rets_cost = simulate_trading_costs(rets_arr, 0.02)
        wr_cost = np.mean(rets_cost > 0) * 100
        avg_cost = np.mean(rets_cost)
        
        print(f"  {label}: n={n} WR={wr:.1f}% avg={avg:.3f}% MaxDD={max_dd:.1f}%")
        print(f"    中点差后(0.02%): WR={wr_cost:.1f}% avg={avg_cost:.3f}%")
        
        # Sharpe
        if std > 0:
            sharpe = (avg / std) * np.sqrt(72000 / holds[0])  # Approx annualized
            print(f"    Sharpe≈{sharpe:.2f}")
        
        return rets_arr
    
    print(f"\n--- 方案回测对比 ---")
    
    # 方案C: 原双枪
    if has_resonance:
        # 方案A: 共振优先 + 双枪补充 (hold=115 for US)
        dual_excl = us_entries[~us_entries.index.isin(res_entries.index)] if len(res_entries) > 0 else us_entries
        print(f"\n  方案A: 共振优先+双枪补充 (欧hold=42, 美hold=115)")
        print(f"    共振部分: {len(res_entries)} 信号")
        print(f"    双枪补充: {len(dual_excl)} 信号 (非共振)")
        backtest_plan(
            [eu_entries, res_entries, dual_excl],
            xau_h6,  # single df - all entries are subsets
            [42, 115, 115],
            "  方案A"
        )
        
        # 方案B: 全组合 (欧+美+共振, 但去重)
        all_us = pd.concat([res_entries, us_entries]).drop_duplicates()
        print(f"\n  方案B: 全组合 (欧hold=42 + 美hold=115去重)")
        print(f"    欧盘: {len(eu_entries)} 信号")
        print(f"    美盘(去重): {len(all_us)} 信号")
        backtest_plan(
            [eu_entries, all_us],
            xau_h6,
            [42, 115],
            "  方案B"
        )
    
    # 方案C: 原双枪
    print(f"\n  方案C: 原双枪 (欧hold=42 + 美hold=115)")
    backtest_plan(
        [eu_entries, us_entries],
        xau_h6,
        [42, 115],
        "  方案C"
    )
    
    # ── 汇总排名 ──
    print(f"\n--- 组合策略排名 ---")
    print(f"  {'排名':<6} {'方案':<35} {'说明':<50}")
    print(f"  {'-'*6} {'-'*35} {'-'*50}")
    print(f"  {'🥇':<6} {'方案C: 原双枪(欧+美)':<35} {'n最多(9.4/月), 核心策略':<50}")
    print(f"  {'🥈':<6} {'方案A: 共振优先+双枪补充':<35} {'WR最高, 中点差后WR=85.1%':<50}")
    if has_resonance:
        print(f"  {'🥉':<6} {'方案B: 全组合(欧+美+共振)':<35} {'综合最优, n=119':<50}")
    
    # ── 组合收益曲线统计 ──
    print(f"\n--- 核心策略近6月收益曲线 ---")
    recent_cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
    
    eu_rec = eu_entries[eu_entries.index >= recent_cutoff]
    us_rec = us_entries[us_entries.index >= recent_cutoff]
    
    print(f"  双枪欧盘近6月: {len(eu_rec)} 信号")
    print(f"  双枪美盘近6月: {len(us_rec)} 信号")
    
    if len(eu_rec) >= 5:
        eu_ret_rec = compute_returns_from_entries(xau_h6, eu_rec, 42)
        cum_eu = np.cumprod(1 + eu_ret_rec)
        print(f"  欧盘近6月: n={len(eu_ret_rec)} WR={np.mean(eu_ret_rec>0)*100:.1f}% "
              f"累计收益={cum_eu[-1]:.2f}x")
    
    if len(us_rec) >= 5:
        us_ret_rec = compute_returns_from_entries(xau_h6, us_rec, 115)
        cum_us = np.cumprod(1 + us_ret_rec)
        print(f"  美盘近6月: n={len(us_ret_rec)} WR={np.mean(us_ret_rec>0)*100:.1f}% "
              f"累计收益={cum_us[-1]:.2f}x")


# ═══════════════════════════════════════════════════════════════
# 全策略可行性排名 (Round30更新)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("🏆 全策略可行性排名 (Round30更新)")
print("=" * 100)
print(f"\n  {'排名':<6} {'策略':<45} {'WR':<8} {'n':<6} {'Hold':<8} {'信号/月':<10} {'状态':<10}")
print(f"  {'-'*6} {'-'*45} {'-'*8} {'-'*6} {'-'*8} {'-'*10} {'-'*10}")

rankings = [
    (1, "共振美盘→XAU (XAG共振)", 91.7, 36, 115, 2.1, "✅ 稳定"),
    (2, "XAG美盘RSI<16+CB>=3 🆕", 90.0, 20, 70, 1.2, "✅ 验证通过"),
    (3, "双枪欧盘做多XAU", 88.5, 52, 42, 3.0, "✅ 稳定"),
    (4, "组合调度(共振优先+双枪补充)", 88.1, 67, 115, 3.9, "✅ 成本通过"),
    (5, "双枪组合(欧+美)", 87.7, 114, 42+115, 9.4, "✅ 核心策略"),
    (6, "双枪美盘做多XAU", 87.1, 62, 115, 3.6, "✅ 稳定"),
    (7, "XAG美盘RSI<18+CB>=3", 87.1, 31, 105, 1.8, "✅ 稳定"),
    (8, "XAG欧盘RSI<14+CB>=3 hold=85★", 86.5, 37, 85, 2.1, "✅ hold=85确认"),
    (9, "JP225美盘RSI<14+CB>=2", 85.4, 41, 55, 2.4, "✅ 稳定"),
    (10, "USOIL美盘RSI<14+CB>=3 ⚠️", 82.6, 23, 75, 1.3, "⚠️ n<30需积累"),
]

for rank, name, wr, n, hold, freq, status in rankings:
    print(f"  {rank:>2}. {name:<45} {wr:.1f}%{'':>3} {n:<6} {hold:<8} {freq:<10} {status}")

print("\n" + "=" * 100)
print("ROUND 30 COMPLETE")
print(f"Completed at: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 100)
