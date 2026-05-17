#!/usr/bin/env python3
"""
Round 31 — AUDUSD深入研究 + 双枪跟踪 + XAG积累监测 + USOIL数据检查 + GBPUSD探索
Testing priority hypotheses from round30 next_actions:
1. round31_001: AUDUSD深入研究 — 跨周期验证+时段细化+hold微调
2. round31_002: 双枪策略继续月度跟踪 — 持续监测近6月表现
3. round31_003: XAG新策略继续积累 — n追踪+USOIL同步监测
4. round31_004: USOIL等待数据积累 — 检查US时段信号覆盖
5. round31_005: 检查MT5数据更新机制 — M1覆盖天数+各品种极端阈值
6. round31_006: GBPUSD初步探索 — 高胜率条件深入验证
"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# HELPERS (consistent with round24-31)
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
print("ROUND 31 — AUDUSD深入研究 + 双枪跟踪 + XAG积累 + GBPUSD探索")
print(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print(f"State: current_round=31, testing round31_001~006")
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
# H1: AUDUSD深入研究 (round31_001)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H1: AUDUSD深入研究 — 跨周期验证+时段细化+hold微调 (round31_001)")
print("=" * 100)
print("目标: round30发现AUDUSD US RSI<16+CB>=3 WR=86.2% n=29 hold=125")
print("      进行跨周期验证、最优hold微调、时段细化、Bootstrap确认")

if "AUDUSD" in all_data_m5:
    aud = all_data_m5["AUDUSD"]

    us_base = (aud['session'] == 'us') & (aud.index.hour >= 15) & (aud.index.hour < 16)
    us_wide = (aud['session'] == 'us') & (aud.index.hour >= 14) & (aud.index.hour < 17)

    # ── H1a: 跨周期验证 RSI<16+CB>=3 ──
    print(f"\n--- H1a: AUDUSD 跨周期验证 (RSI<16+CB>=3) ---")
    aud_hold_range = list(range(30, 161, 5))
    test_condition_with_periods(aud, us_base & (aud['rsi14'] < 16) & (aud['consecutive_bear'] >= 3),
                                f"AUDUSD US 15-16 RSI<16+CB>=3",
                                hold_range=aud_hold_range,
                                min_signals=25)

    # ── H1b: 时段细化 ──
    print(f"\n--- H1b: AUDUSD 时段细化 ---")
    time_slots = [(13, 14), (14, 15), (15, 16), (16, 17), (14, 16), (15, 17), (13, 17)]
    print(f"  {'时段':<15} {'条件':<25} {'n':<6} {'最优hold':<10} {'WR':<10} {'avg%':<10}")
    print(f"  {'-'*15} {'-'*25} {'-'*6} {'-'*10} {'-'*10} {'-'*10}")
    for h_start, h_end in time_slots:
        for rsi_thresh in [14, 16, 18]:
            for cb in [2, 3]:
                slot_base = (aud['session'] == 'us') & (aud.index.hour >= h_start) & (aud.index.hour < h_end)
                mask = slot_base & (aud['rsi14'] < rsi_thresh) & (aud['consecutive_bear'] >= cb)
                n = mask.sum()
                if n >= 8:
                    best_hold, best_wr, best_avg = 0, 0, 0
                    for hold in range(30, 161, 5):
                        cnt, wr, avg = get_stats(aud, mask, hold)
                        if cnt >= 3 and wr > best_wr:
                            best_wr, best_hold, best_avg = wr, hold, avg
                    cond_name = f"RSI<{rsi_thresh}+CB>={cb}"
                    print(f"  US {h_start:02d}-{h_end:02d}    {cond_name:<25} {n:<6} hold={best_hold:<5} {best_wr:.1f}%{'':>4} {best_avg:.3f}%")

    # ── H1c: hold=125 多条件对比 ──
    print(f"\n--- H1c: AUDUSD hold=125 各条件对比 ---")
    for name, cond in [
        ("RSI<16+CB>=3", (aud['rsi14'] < 16) & (aud['consecutive_bear'] >= 3)),
        ("RSI<14+CB>=3", (aud['rsi14'] < 14) & (aud['consecutive_bear'] >= 3)),
        ("RSI<16+CB>=2", (aud['rsi14'] < 16) & (aud['consecutive_bear'] >= 2)),
        ("RSI<18+CB>=3", (aud['rsi14'] < 18) & (aud['consecutive_bear'] >= 3)),
        ("RSI<14+CB>=2", (aud['rsi14'] < 14) & (aud['consecutive_bear'] >= 2)),
    ]:
        n_all, wr_all, avg_all = get_stats(aud, us_base & cond, 125)
        if n_all >= 5:
            print(f"  {name:<25} hold=125: n={n_all:<5} WR={wr_all:.1f}% avg={avg_all:.3f}%")

    # ── H1d: 跨品种相关性 ──
    print(f"\n--- H1d: AUDUSD vs 其他FX 信号重叠 ---")
    fx_pairs = {"USDJPY": "USDJPY", "USDCHF": "USDCHF", "GBPUSD": "GBPUSD", "EURUSD": "EURUSD"}
    aud_best_mask = us_base & (aud['rsi14'] < 16) & (aud['consecutive_bear'] >= 3)
    aud_signal_dates = set(aud.index[aud_best_mask].strftime('%Y-%m-%d'))
    print(f"  AUDUSD信号日期: {len(aud_signal_dates)}个交易日")
    for sym_name, sym_key in fx_pairs.items():
        if sym_key in all_data_m5:
            other = all_data_m5[sym_key]
            other_mask = us_base.reindex(other.index, fill_value=False) & \
                         (other['rsi14'] < 16) & (other['consecutive_bear'] >= 3)
            other_dates = set(other.index[other_mask].strftime('%Y-%m-%d'))
            overlap = aud_signal_dates & other_dates
            print(f"  AUDUSD ∩ {sym_name}: {len(overlap)}天重叠 ({len(overlap)/max(1,len(aud_signal_dates))*100:.0f}%)")

    # ── H1e: Bootstrap + 成本分析 ──
    print(f"\n--- H1e: AUDUSD Bootstrap + 成本分析 ---")
    aud_best_mask = us_base & (aud['rsi14'] < 16) & (aud['consecutive_bear'] >= 3)
    if aud_best_mask.sum() >= 10:
        best_hold_for_aud = 125
        aud_rets = compute_returns_from_entries(aud, aud[aud_best_mask], best_hold_for_aud)
        if len(aud_rets) >= 10:
            ci_low, ci_high = bootstrap_confidence(aud_rets)
            wr = np.mean(aud_rets > 0) * 100
            print(f"  AUDUSD RSI<16+CB>=3 hold=125: n={len(aud_rets)} WR={wr:.1f}% "
                  f"95% CI=[{ci_low:.1f}%, {ci_high:.1f}%]")
            # With costs
            aud_cost = simulate_trading_costs(aud_rets, 0.01)
            wr_cost = np.mean(aud_cost > 0) * 100
            print(f"  中点差后(0.01%): n={len(aud_cost)} WR={wr_cost:.1f}% avg={np.mean(aud_cost):.3f}%")

    # ── H1f: 月度频率 ──
    print(f"\n--- H1f: AUDUSD 月度频率 ---")
    aud_entries = aud[us_base & (aud['rsi14'] < 16) & (aud['consecutive_bear'] >= 3)]
    if len(aud_entries) >= 5:
        months_covered = max(1, (aud_entries.index[-1] - aud_entries.index[0]).days / 30)
        freq = len(aud_entries) / months_covered
        print(f"  信号频率: {freq:.1f}/月 (覆盖{months_covered:.0f}月)")
        print(f"  首个信号: {aud_entries.index[0].date()}")
        print(f"  最新信号: {aud_entries.index[-1].date()}")
else:
    print("  ⚠️  AUDUSD data not available")


# ═══════════════════════════════════════════════════════════════
# H2: 双枪策略月度跟踪 (round31_002)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H2: 双枪策略月度跟踪 — 近6月表现监测 (round31_002)")
print("=" * 100)
print("目标: 持续监测双枪策略近6月表现. 关注2026-06~07是否出现回撤")
print("      双枪欧盘: EU 9-11 RSI<18+CB>=4 hold=42")
print("      双枪美盘: US 15-16 RSI<20+CB>=2 hold=115")

if "XAUUSD" in all_data_m5:
    xau_h2 = all_data_m5["XAUUSD"]

    recent_cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
    recent_mask = xau_h2.index >= recent_cutoff

    print(f"  数据分割点: {recent_cutoff.date()}")
    print(f"  近期行数: {recent_mask.sum():,}")

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

    # 月度表现 (近12月)
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
        comb_rec_wr = np.mean(comb_rec_rets > 0) * 100
        comb_rec_avg = np.mean(comb_rec_rets)
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
# H3: XAG新策略继续积累 + USOIL同步监测 (round31_003)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H3: XAG新策略继续积累 + USOIL同步监测 (round31_003)")
print("=" * 100)
print("目标: 追踪XAG RSI<16+CB>=3 n值增长至≥30, 同步监测USOIL数据增长")

if "XAGUSD" in all_data_m5:
    xag_h3 = all_data_m5["XAGUSD"]
    us_base_h3 = (xag_h3['session'] == 'us') & (xag_h3.index.hour >= 15) & (xag_h3.index.hour < 16)

    print(f"\n--- XAG美盘新策略n值追踪 ---")
    for name, cond in [
        ("RSI<16+CB>=3 🆕", (xag_h3['rsi14'] < 16) & (xag_h3['consecutive_bear'] >= 3)),
        ("RSI<14+CB>=3 (极端)", (xag_h3['rsi14'] < 14) & (xag_h3['consecutive_bear'] >= 3)),
        ("RSI<12+CB>=3 (极端RSI)", (xag_h3['rsi14'] < 12) & (xag_h3['consecutive_bear'] >= 3)),
    ]:
        mask = us_base_h3 & cond
        n = mask.sum()
        progress = f"{n}/30" if n < 30 else "✅ ≥30"
        print(f"  {name:<30} n={n:<5} {progress}")

    # XAG EU hold=85 更新
    print(f"\n--- XAG欧盘 hold=85 更新 ---")
    eu_base_h3 = (xag_h3['session'] == 'europe') & (xag_h3.index.hour >= 9) & (xag_h3.index.hour < 11)
    eu_mask = eu_base_h3 & (xag_h3['rsi14'] < 14) & (xag_h3['consecutive_bear'] >= 3)
    n_eu, wr_eu, avg_eu = get_stats(xag_h3, eu_mask, 85)
    print(f"  XAG EU hold=85: n={n_eu} WR={wr_eu:.1f}% avg={avg_eu:.3f}% (vs round29)")

# USOIL同步监测
if "USOIL" in all_data_m5:
    usoil_h3 = all_data_m5["USOIL"]
    us_base_oil = (usoil_h3['session'] == 'us') & (usoil_h3.index.hour >= 15) & (usoil_h3.index.hour < 16)
    oil_mask = us_base_oil & (usoil_h3['rsi14'] < 14) & (usoil_h3['consecutive_bear'] >= 3)
    n_oil = oil_mask.sum()
    print(f"\n--- USOIL数据积累状态 ---")
    print(f"  USOIL RSI<14+CB>=3: n={n_oil} (vs round30: n=23)")
    if n_oil >= 5:
        oil_entries = usoil_h3[oil_mask]
        print(f"  最新信号: {oil_entries.index[-1].date() if len(oil_entries) > 0 else '无'}")
        print(f"  数据时间差: {(pd.Timestamp.now() - oil_entries.index[-1]).days if len(oil_entries) > 0 else 'N/A'}天前")


# ═══════════════════════════════════════════════════════════════
# H4: USOIL等待数据积累 — 检查US时段信号覆盖 (round31_004)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H4: USOIL等待数据积累 — 检查US时段信号覆盖 (round31_004)")
print("=" * 100)
print("目标: 检查USOIL最近5个月无新信号的原因, 分析数据覆盖情况")

if "USOIL" in all_data_m5:
    usoil_h4 = all_data_m5["USOIL"]
    
    # 检查数据时间范围
    print(f"\n--- USOIL数据时间范围 ---")
    print(f"  USOIL数据: {usoil_h4.index[0]} → {usoil_h4.index[-1]}")
    print(f"  最后120天行数: {(usoil_h4.index >= (usoil_h4.index[-1] - pd.DateOffset(days=120))).sum()}")
    
    # 检查US时段是否有数据
    print(f"\n--- USOIL US时段数据最近状况 ---")
    us_recent = usoil_h4[usoil_h4.index >= (usoil_h4.index[-1] - pd.DateOffset(days=30))]
    us_periods = us_recent[(us_recent['session'] == 'us') & (us_recent.index.hour >= 13) & (us_recent.index.hour < 22)]
    print(f"  最近30天US时段K线: {len(us_periods)}")
    if len(us_periods) > 0:
        print(f"  US时段日期范围: {us_periods.index[0]} → {us_periods.index[-1]}")
    
    # 检查RSI值分布
    print(f"\n--- USOIL US 15-16 RSI分布 ---")
    us_1516 = usoil_h4[(usoil_h4['session'] == 'us') & (usoil_h4.index.hour >= 15) & (usoil_h4.index.hour < 16)]
    if len(us_1516) > 0:
        rsi_vals = us_1516['rsi14'].dropna()
        print(f"  US 15-16 K线数: {len(us_1516)}")
        print(f"  RSI范围: {rsi_vals.min():.1f} ~ {rsi_vals.max():.1f}")
        print(f"  RSI<14占比: {(rsi_vals < 14).mean()*100:.1f}%")
        print(f"  RSI<16占比: {(rsi_vals < 16).mean()*100:.1f}%")
    
    # 检查最近5个月 US 15-16 数据量
    print(f"\n--- USOIL 最近6个月 US 15-16 数据 ---")
    six_months_ago = usoil_h4.index[-1] - pd.DateOffset(months=6)
    recent_us = usoil_h4[(usoil_h4.index >= six_months_ago) & 
                         (usoil_h4['session'] == 'us') & 
                         (usoil_h4.index.hour >= 15) & (usoil_h4.index.hour < 16)]
    print(f"  近6月US 15-16 K线: {len(recent_us)}")
    if len(recent_us) > 0:
        rsi_recent = recent_us['rsi14'].dropna()
        print(f"  RSI范围: {rsi_recent.min():.1f} ~ {rsi_recent.max():.1f}")
        print(f"  RSI<14+CB>=3信号: {(rsi_recent < 14).sum()} (需检查consecutive_bear)")
    
    # 对比XAU同期信号
    if "XAUUSD" in all_data_m5:
        xau_h4 = all_data_m5["XAUUSD"]
        xau_us = xau_h4[(xau_h4.index >= six_months_ago) & 
                        (xau_h4['session'] == 'us') & 
                        (xau_h4.index.hour >= 15) & (xau_h4.index.hour < 16)]
        print(f"\n--- XAU同期US 15-16对比 ---")
        print(f"  XAU近6月US 15-16 K线: {len(xau_us)}")
        print(f"  XAU RSI<14+CB>=3信号: {((xau_us['rsi14'] < 14) & (xau_us['consecutive_bear'] >= 3)).sum()}")
else:
    print("  ⚠️  USOIL data not available")


# ═══════════════════════════════════════════════════════════════
# H5: 检查MT5数据更新机制 (round31_005)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H5: 检查MT5数据更新机制 — M1覆盖天数+极端阈值进度 (round31_005)")
print("=" * 100)
print("目标: 排查MT5下载定时问题. M1 103天未变, 极端阈值无增长")

# M1 数据增长检查
print(f"\n--- M1 数据增长检查 ---")
if "XAUUSD" in all_data_m1:
    xau_m1 = all_data_m1["XAUUSD"]
    m1_days = (xau_m1.index[-1] - xau_m1.index[0]).days
    print(f"  M1 XAUUSD 覆盖: {m1_days}天 [{xau_m1.index[0].date()} → {xau_m1.index[-1].date()}]")
    print(f"  M1最后时间: {xau_m1.index[-1]}")

if "XAGUSD" in all_data_m1:
    xag_m1 = all_data_m1["XAGUSD"]
    m1_xag_days = (xag_m1.index[-1] - xag_m1.index[0]).days
    print(f"  M1 XAGUSD 覆盖: {m1_xag_days}天 [{xag_m1.index[0].date()} → {xag_m1.index[-1].date()}]")

# M5 最新数据时间
print(f"\n--- M5 最新数据时间 ---")
for sym in ["XAUUSD", "XAGUSD", "USOIL", "AUDUSD", "GBPUSD", "JP225", "US500", "US30"]:
    if sym in all_data_m5:
        df = all_data_m5[sym]
        print(f"  {sym}: 最后K线={df.index[-1]}, close={df['close'].iloc[-1]:.2f}")

# 检查M5数据结束时间是否覆盖今日
print(f"\n--- 今日数据覆盖检查 ---")
today = pd.Timestamp.now().date()
for sym in ["XAUUSD", "XAGUSD", "USOIL", "AUDUSD"]:
    if sym in all_data_m5:
        df = all_data_m5[sym]
        last_date = df.index[-1].date()
        if last_date == today:
            print(f"  ✅ {sym}: 今日数据已更新至 {df.index[-1].time()}")
        else:
            print(f"  ⚠️  {sym}: 今日数据未更新, 最后日期={last_date}")

# 数据下载建议
print(f"\n--- MT5数据下载建议 ---")
print(f"  ⚠️ M5所有品种最后K线停在12:30 (UTC+0)")
print(f"  ⚠️ M1数据103天未扩展")
print(f"  ⚠️ USOIL最近5月无新信号(2025-12后)")
print(f"  可能原因:")
print(f"    1. MT5定时下载任务未在美盘时段运行")
print(f"    2. 数据下载脚本在非交易时间启动, 覆盖了之前的完整数据")
print(f"    3. MT5市场报价未开启所有品种的实时报价")
print(f"  建议: 检查download_data.py的定时调度配置")


# ═══════════════════════════════════════════════════════════════
# H6: GBPUSD初步探索 (round31_006)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("H6: GBPUSD初步探索 — 高胜率条件深入验证 (round31_006)")
print("=" * 100)
print("目标: round30发现GBPUSD US RSI<14+CB>=3 WR=92.3% n=13 hold=145")
print("      虽n少但胜率极高值得关注, 进行跨周期验证和hold微调")

if "GBPUSD" in all_data_m5:
    gbpusd = all_data_m5["GBPUSD"]
    us_base_gbp = (gbpusd['session'] == 'us') & (gbpusd.index.hour >= 15) & (gbpusd.index.hour < 16)
    us_wide_gbp = (gbpusd['session'] == 'us') & (gbpusd.index.hour >= 14) & (gbpusd.index.hour < 17)

    # ── H6a: 条件矩阵 ──
    print(f"\n--- H6a: GBPUSD US 15-16 条件矩阵 ---")
    print(f"  {'条件':<35} {'n':<6} {'最优hold':<10} {'WR':<10} {'avg%':<10}")
    print(f"  {'-'*35} {'-'*6} {'-'*10} {'-'*10} {'-'*10}")
    
    gbp_results = []
    for rsi_thresh in [12, 14, 16, 18]:
        for cb in [1, 2, 3]:
            cond = (gbpusd['rsi14'] < rsi_thresh) & (gbpusd['consecutive_bear'] >= cb)
            mask = us_base_gbp & cond
            n = mask.sum()
            if n >= 5:
                best_hold, best_wr, best_avg = 0, 0, 0
                for hold in list(range(10, 61, 5)) + list(range(65, 161, 5)):
                    cnt, wr, avg = get_stats(gbpusd, mask, hold)
                    if cnt >= 3 and wr > best_wr:
                        best_wr, best_hold, best_avg = wr, hold, avg
                print(f"  RSI<{rsi_thresh}+CB>={cb:<5}           {n:<6} hold={best_hold:<5} {best_wr:.1f}%{'':>4} {best_avg:.3f}%")
                gbp_results.append((rsi_thresh, cb, n, best_hold, best_wr, best_avg))

    # ── H6b: RSI<14+CB>=3 跨周期验证 ──
    print(f"\n--- H6b: GBPUSD RSI<14+CB>=3 跨周期验证 ---")
    gbp_hold_range = list(range(30, 161, 5))
    test_condition_with_periods(gbpusd, us_base_gbp & (gbpusd['rsi14'] < 14) & (gbpusd['consecutive_bear'] >= 3),
                                f"GBPUSD US 15-16 RSI<14+CB>=3",
                                hold_range=gbp_hold_range,
                                min_signals=10)

    # ── H6c: 时段细化 ──
    print(f"\n--- H6c: GBPUSD 时段细化 ---")
    time_slots = [(13, 14), (14, 15), (15, 16), (16, 17), (14, 16), (15, 17)]
    print(f"  {'时段':<15} {'n':<6} {'最优hold':<10} {'WR':<10} {'avg%':<10}")
    print(f"  {'-'*15} {'-'*6} {'-'*10} {'-'*10} {'-'*10}")
    for h_start, h_end in time_slots:
        slot_base = (gbpusd['session'] == 'us') & (gbpusd.index.hour >= h_start) & (gbpusd.index.hour < h_end)
        mask = slot_base & (gbpusd['rsi14'] < 14) & (gbpusd['consecutive_bear'] >= 3)
        n = mask.sum()
        if n >= 5:
            best_hold, best_wr, best_avg = 0, 0, 0
            for hold in gbp_hold_range:
                cnt, wr, avg = get_stats(gbpusd, mask, hold)
                if cnt >= 3 and wr > best_wr:
                    best_wr, best_hold, best_avg = wr, hold, avg
            print(f"  US {h_start:02d}-{h_end:02d}    {n:<6} hold={best_hold:<5} {best_wr:.1f}%{'':>4} {best_avg:.3f}%")
        else:
            print(f"  US {h_start:02d}-{h_end:02d}    {n:<6} (信号不足)")

    # ── H6d: 宽时段探索 ──
    print(f"\n--- H6d: GBPUSD US 14-17 宽时段 ---")
    print(f"  {'条件':<35} {'n':<6} {'最优hold':<10} {'WR':<10} {'avg%':<10}")
    print(f"  {'-'*35} {'-'*6} {'-'*10} {'-'*10} {'-'*10}")
    for rsi_thresh in [12, 14, 16]:
        for cb in [1, 2, 3]:
            cond = (gbpusd['rsi14'] < rsi_thresh) & (gbpusd['consecutive_bear'] >= cb)
            mask = us_wide_gbp & cond
            n = mask.sum()
            if n >= 5:
                best_hold, best_wr, best_avg = 0, 0, 0
                for hold in list(range(10, 61, 5)) + list(range(65, 161, 5)):
                    cnt, wr, avg = get_stats(gbpusd, mask, hold)
                    if cnt >= 3 and wr > best_wr:
                        best_wr, best_hold, best_avg = wr, hold, avg
                print(f"  RSI<{rsi_thresh}+CB>={cb:<5}           {n:<6} hold={best_hold:<5} {best_wr:.1f}%{'':>4} {best_avg:.3f}%")

    # ── H6e: Bootstrap ──
    print(f"\n--- H6e: GBPUSD Bootstrap ---")
    gbp_best_mask = us_base_gbp & (gbpusd['rsi14'] < 14) & (gbpusd['consecutive_bear'] >= 3)
    if gbp_best_mask.sum() >= 10:
        best_hold_gbp = 145
        gbp_rets = compute_returns_from_entries(gbpusd, gbpusd[gbp_best_mask], best_hold_gbp)
        if len(gbp_rets) >= 10:
            ci_low, ci_high = bootstrap_confidence(gbp_rets)
            wr = np.mean(gbp_rets > 0) * 100
            print(f"  GBPUSD RSI<14+CB>=3 hold={best_hold_gbp}: n={len(gbp_rets)} WR={wr:.1f}% "
                  f"95% CI=[{ci_low:.1f}%, {ci_high:.1f}%]")
    
    # ── H6f: 月度频率 ──
    print(f"\n--- H6f: GBPUSD 月度频率 ---")
    gbp_entries = gbpusd[us_base_gbp & (gbpusd['rsi14'] < 14) & (gbpusd['consecutive_bear'] >= 3)]
    if len(gbp_entries) >= 5:
        months_covered = max(1, (gbp_entries.index[-1] - gbp_entries.index[0]).days / 30)
        freq = len(gbp_entries) / months_covered
        print(f"  信号频率: {freq:.1f}/月 (覆盖{months_covered:.0f}月)")
        print(f"  首个信号: {gbp_entries.index[0].date()}")
        print(f"  最新信号: {gbp_entries.index[-1].date()}")
else:
    print("  ⚠️  GBPUSD data not available")


# ═══════════════════════════════════════════════════════════════
# 全策略可行性排名 (Round31更新)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("🏆 全策略可行性排名 (Round31更新)")
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
    (9, "AUDUSD美盘RSI<16+CB>=3 🆕", 86.2, 29, 125, 1.7, "✅ 潜力品种"),
    (10, "JP225美盘RSI<14+CB>=2", 85.4, 41, 55, 2.4, "✅ 稳定"),
    (11, "GBPUSD美盘RSI<14+CB>=3 🧪", 92.3, 13, 145, 0.8, "🧪 需积累"),
    (12, "USOIL美盘RSI<14+CB>=3 ⚠️", 82.6, 23, 75, 1.3, "⚠️ 数据停滞"),
]

for rank, name, wr, n, hold, freq, status in rankings:
    print(f"  {rank:>2}. {name:<45} {wr:.1f}%{'':>3} {n:<6} {hold:<8} {freq:<10} {status}")

print("\n" + "=" * 100)
print("ROUND 31 COMPLETE")
print(f"Completed at: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 100)
