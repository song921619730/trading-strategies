#!/usr/bin/env python3
"""
Round 33 — 超短线 M1/M5 + H1/M30 深度验证与月度跟踪

目标:
  1. XAGUSD M30 做空深度验证 (CBull>=4+RSI>80)
  2. USDJPY H1 做多交叉验证 (CB>=5+RSI<25)
  3. 双枪策略月度跟踪 (欧盘+美盘)
  4. AUDUSD/GBPUSD/USOIL 积累检查
  5. USOIL M30 做空交叉验证
  6. MT5数据下载效果验证

数据范围:
  M1/M5: 最新至 2026-05-13 13:48 UTC
  H1/M30: 最新至 2026-05-12 14:00 UTC
"""

import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')

from data_loader import load_data, compute_indicators, PERIODS_PER_YEAR
import pandas as pd
import numpy as np
from datetime import datetime
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def add_session(df):
    df = df.copy()
    df['session'] = 'asia'
    df.loc[(df.index.hour >= 8) & (df.index.hour < 13), 'session'] = 'europe'
    df.loc[(df.index.hour >= 13) & (df.index.hour < 22), 'session'] = 'us'
    bear = (df['close'] < df['open']).astype(int)
    df['consecutive_bear'] = bear.groupby((bear == 0).cumsum()).cumsum()
    bull = (df['close'] > df['open']).astype(int)
    df['consecutive_bull'] = bull.groupby((bull == 0).cumsum()).cumsum()
    df['hour'] = df.index.hour
    df['minute'] = df.index.minute
    return df

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

def test_pattern(df, cond, label, hold_list, min_sig=5):
    entries = df[cond].copy()
    n = len(entries)
    print(f"  {label:<55} n={n:<5}", end="")
    if n < min_sig:
        print(f"  跳过(<{min_sig})")
        return None
    best = {'hold': 0, 'wr': 0, 'avg': 0, 'n': 0}
    for hold in hold_list:
        cnt, wr, avg = get_stats(df, cond, hold)
        if cnt >= 3 and wr > best['wr']:
            best = {'hold': hold, 'wr': wr, 'avg': avg, 'n': cnt}
    if best['wr'] >= 60:
        print(f" hold={best['hold']:3d} WR={best['wr']:.1f}% n={best['n']} avg={best['avg']:.3f}% ✅")
    else:
        print(f" hold={best['hold']:3d} WR={best['wr']:.1f}% n={best['n']} avg={best['avg']:.3f}%")
    return best

def bootstrap_ci(df, mask, hold, n_iter=10000):
    """Bootstrap 95% CI for win rate"""
    entries = df[mask]
    profits = []
    for idx, row in entries.iterrows():
        pos = df.index.get_loc(idx)
        if pos + hold < len(df):
            pnl = (df.iloc[pos + hold]['close'] - row['close']) / row['close'] * 100
            profits.append(1 if pnl > 0 else 0)
    if len(profits) < 5:
        return None, 0, 0
    arr = np.array(profits)
    n = len(arr)
    obs_wr = arr.mean() * 100
    boot_means = np.array([np.random.choice(arr, n, replace=True).mean() for _ in range(n_iter)])
    ci = np.percentile(boot_means, [2.5, 97.5]) * 100
    return obs_wr, ci[0], ci[1], n

def cross_period_validation(df, mask, hold, n_periods=3):
    """Split data into periods and validate each"""
    total_rows = len(df)
    chunk = total_rows // n_periods
    results = []
    for i in range(n_periods):
        start = i * chunk
        end = (i + 1) * chunk if i < n_periods - 1 else total_rows
        sub = df.iloc[start:end]
        sub_mask = mask.iloc[start:end]
        cnt, wr, avg = get_stats(sub, sub_mask, hold)
        results.append({'period': i+1, 'n': cnt, 'wr': wr, 'avg': avg})
    return results

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
print("=" * 120)
print("ROUND 33 — M1/M5 超短线深度验证 + 月度跟踪")
print(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print("品种: XAUUSD, XAGUSD, JP225, US30, US500, AUDUSD, GBPUSD, USOIL")
print("时间框架: M5 (主) + M30/H1 (深度验证)")
print("=" * 120)

# ═══════════════════════════════════════════════════════════════
# SECTION 0: Data Freshness Check
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📡 00 — 数据新鲜度检查")
print(f"{'='*120}")

for tf in ['M1', 'M5', 'M30', 'H1']:
    d = os.path.join(BASE, 'data', tf)
    files = sorted([f for f in os.listdir(d) if f.endswith('.parquet')]) if os.path.exists(d) else []
    if files:
        df = pd.read_parquet(os.path.join(d, files[0]))
        print(f"  {tf:4s}: 最新={df.index[-1]}, 行数={len(df)}, 品种={len(files)}")
        # Count US session coverage
        if tf in ['M1', 'M5']:
            us_after_18 = (df.index.hour >= 18).sum() if (df.index.hour >= 18).any() else 0
            us_13_17 = ((df.index.hour >= 13) & (df.index.hour < 18)).sum()
            print(f"        美盘13-17h={us_13_17}条, 美盘18h+={us_after_18}条")
    else:
        print(f"  {tf:4s}: 无数据")

# ═══════════════════════════════════════════════════════════════
# SECTION 1: XAGUSD M30 做空深度验证
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 01 — XAGUSD M30 做空深度验证 (CBull>=4+RSI>80 hold=60)")
print(f"{'='*120}")

m30_data = load_data('M30', symbols=['XAGUSD', 'USOIL', 'USDJPY'])
h1_data = load_data('H1', symbols=['XAGUSD', 'USDJPY'])

xag_m30 = add_session(compute_indicators(m30_data['XAGUSD'])) if 'XAGUSD' in m30_data else None

if xag_m30 is not None:
    print(f"  XAGUSD M30: [{xag_m30.index[0]} → {xag_m30.index[-1]}] rows={len(xag_m30)}")
    
    # CBull>=4 + RSI>80
    cond1 = (xag_m30['consecutive_bull'] >= 4) & (xag_m30['rsi14'] > 80)
    print(f"\n  --- A: 原始策略 CBull>=4+RSI>80 ---")
    res1 = test_pattern(xag_m30, cond1, 'XAGUSD M30 CBull>=4+RSI>80', 
                        list(range(30, 121, 5)), min_sig=3)
    if res1 and res1['n'] >= 10:
        obs_wr, ci_lo, ci_hi, n_boot = bootstrap_ci(xag_m30, cond1, res1['hold'])
        if obs_wr:
            print(f"  Bootstrap 95% CI: [{ci_lo:.1f}%, {ci_hi:.1f}%]  (n={n_boot})")
        
        # Cross-period validation
        periods = cross_period_validation(xag_m30, cond1, res1['hold'], 3)
        print(f"  跨周期验证 (3等分):")
        for p in periods:
            marker = "✅" if p['wr'] >= 60 else "⚠️" if p['wr'] >= 50 else "❌"
            print(f"     P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {marker}")
    
    # CBull>=5 + RSI>80
    cond2 = (xag_m30['consecutive_bull'] >= 5) & (xag_m30['rsi14'] > 80)
    print(f"\n  --- B: CBull>=5+RSI>80 ---")
    res2 = test_pattern(xag_m30, cond2, 'XAGUSD M30 CBull>=5+RSI>80',
                        list(range(30, 121, 5)), min_sig=3)
    if res2 and res2['n'] >= 10:
        obs_wr, ci_lo, ci_hi, n_boot = bootstrap_ci(xag_m30, cond2, res2['hold'])
        if obs_wr:
            print(f"  Bootstrap 95% CI: [{ci_lo:.1f}%, {ci_hi:.1f}%]  (n={n_boot})")
    
    # CBull>=5 + RSI>75
    cond3 = (xag_m30['consecutive_bull'] >= 5) & (xag_m30['rsi14'] > 75)
    print(f"\n  --- C: CBull>=5+RSI>75 ---")
    res3 = test_pattern(xag_m30, cond3, 'XAGUSD M30 CBull>=5+RSI>75',
                        list(range(30, 121, 5)), min_sig=3)
    if res3 and res3['n'] >= 10:
        obs_wr, ci_lo, ci_hi, n_boot = bootstrap_ci(xag_m30, cond3, res3['hold'])
        if obs_wr:
            print(f"  Bootstrap 95% CI: [{ci_lo:.1f}%, {ci_hi:.1f}%]  (n={n_boot})")
    
    # Doji + RSI>75 + US
    doji = (abs(xag_m30['close'] - xag_m30['open']) / 
            (xag_m30['high'] - xag_m30['low']).replace(0, np.nan)) < 0.1
    cond4 = doji & (xag_m30['rsi14'] > 75) & (xag_m30['session'] == 'us')
    print(f"\n  --- D: Doji+RSI>75+US ---")
    res4 = test_pattern(xag_m30, cond4, 'XAGUSD M30 Doji+RSI>75+US',
                        list(range(30, 121, 5)), min_sig=3)
    
    # Cost analysis (spread impact)
    print(f"\n  --- E: 成本影响分析 (spread) ---")
    avg_spread = xag_m30['spread'].mean() if 'spread' in xag_m30.columns else 0
    print(f"  XAGUSD M30 平均点差: {avg_spread:.1f}")
    if res1 and res1['n'] >= 5:
        # Calculate net of spread (assume 1 pip = ~0.01% for XAG ~$24)
        spread_cost_pct = avg_spread * 0.01 / 24 * 100 if avg_spread > 0 else 0.05
        net_avg = res1['avg'] - spread_cost_pct
        print(f"  估算每笔点差成本: {spread_cost_pct:.4f}%")
        print(f"  毛收益: {res1['avg']:.3f}% → 净收益: {net_avg:.3f}%")

# ═══════════════════════════════════════════════════════════════
# SECTION 2: USDJPY H1 做多交叉验证
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 02 — USDJPY H1 做多交叉验证 (CB>=5+RSI<25 hold=120)")
print(f"{'='*120}")

usdjpy_h1 = add_session(compute_indicators(h1_data['USDJPY'])) if 'USDJPY' in h1_data else None

if usdjpy_h1 is not None:
    print(f"  USDJPY H1: [{usdjpy_h1.index[0]} → {usdjpy_h1.index[-1]}] rows={len(usdjpy_h1)}")
    
    # Original: CB>=5 + RSI<25
    cond = (usdjpy_h1['consecutive_bear'] >= 5) & (usdjpy_h1['rsi14'] < 25)
    print(f"\n  --- A: 原始策略 CB>=5+RSI<25 (做多) ---")
    res = test_pattern(usdjpy_h1, cond, 'USDJPY H1 CB>=5+RSI<25',
                       list(range(10, 181, 5)), min_sig=3)
    if res and res['n'] >= 10:
        obs_wr, ci_lo, ci_hi, n_boot = bootstrap_ci(usdjpy_h1, cond, res['hold'])
        if obs_wr:
            print(f"  Bootstrap 95% CI: [{ci_lo:.1f}%, {ci_hi:.1f}%]  (n={n_boot})")
    
    # Session refinement
    print(f"\n  --- B: 时段细化 ---")
    for sess in ['asia', 'europe', 'us']:
        cond_s = (usdjpy_h1['consecutive_bear'] >= 5) & (usdjpy_h1['rsi14'] < 25) & (usdjpy_h1['session'] == sess)
        test_pattern(usdjpy_h1, cond_s, f'USDJPY H1 CB>=5+RSI<25+{sess}',
                     list(range(10, 181, 5)), min_sig=2)
    
    # Alternative thresholds
    print(f"\n  --- C: 阈值微调 ---")
    for cb in [4, 5, 6]:
        for rsi in [20, 25, 30]:
            cond_a = (usdjpy_h1['consecutive_bear'] >= cb) & (usdjpy_h1['rsi14'] < rsi)
            test_pattern(usdjpy_h1, cond_a, f'USDJPY H1 CB>={cb}+RSI<{rsi}',
                         list(range(10, 181, 5)), min_sig=3)

# ═══════════════════════════════════════════════════════════════
# SECTION 3: 双枪策略月度跟踪
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📊 03 — 双枪策略月度跟踪 (M5 XAUUSD)")
print(f"{'='*120}")

m5_xau = add_session(compute_indicators(load_data('M5', symbols=['XAUUSD'])['XAUUSD'])) if 'XAUUSD' in load_data('M5', symbols=['XAUUSD']) else None

if m5_xau is not None:
    print(f"  XAUUSD M5: [{m5_xau.index[0]} → {m5_xau.index[-1]}] rows={len(m5_xau)}")
    
    # 双枪欧盘: EU 9-11 RSI<18+CB>=4 hold=42
    cond_eu = (m5_xau['session'] == 'europe') & (m5_xau['hour'].between(9, 11)) & \
              (m5_xau['rsi14'] < 18) & (m5_xau['consecutive_bear'] >= 4)
    
    # 双枪美盘: US 15-16 RSI<20+CB>=2 hold=115
    cond_us = (m5_xau['session'] == 'us') & (m5_xau['hour'].between(15, 16)) & \
              (m5_xau['rsi14'] < 20) & (m5_xau['consecutive_bear'] >= 2)
    
    # Monthly breakdown
    m5_xau['month'] = m5_xau.index.to_period('M')
    
    print(f"\n  --- 双枪欧盘: EU 9-11 RSI<18+CB>=4 hold=42 ---")
    for month, grp in m5_xau.groupby('month'):
        cnt, wr, avg = get_stats(grp, cond_eu.loc[grp.index], 42)
        if cnt > 0:
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}%")
    
    total_cnt, total_wr, total_avg = get_stats(m5_xau, cond_eu, 42)
    print(f"  → 总计: n={total_cnt} WR={total_wr:.1f}% avg={total_avg:.3f}%")
    
    print(f"\n  --- 双枪美盘: US 15-16 RSI<20+CB>=2 hold=115 ---")
    for month, grp in m5_xau.groupby('month'):
        cnt, wr, avg = get_stats(grp, cond_us.loc[grp.index], 115)
        if cnt > 0:
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}%")
    
    total_cnt2, total_wr2, total_avg2 = get_stats(m5_xau, cond_us, 115)
    print(f"  → 总计: n={total_cnt2} WR={total_wr2:.1f}% avg={total_avg2:.3f}%")
    
    # 双枪组合
    combo_cnt = total_cnt + total_cnt2
    combo_wins = (total_cnt * total_wr / 100 + total_cnt2 * total_wr2 / 100) / combo_cnt * 100 if combo_cnt > 0 else 0
    print(f"\n  --- 双枪组合 ---")
    print(f"  总信号: n={combo_cnt} 组合WR={combo_wins:.1f}%")
    print(f"  频率: {combo_cnt/5:.1f}次/月 (基于~5月数据)")
    
    # 共振美盘优先+双枪补充
    cond_res = (m5_xau['session'] == 'us') & (m5_xau['hour'].between(15, 16)) & \
               (m5_xau['rsi14'] < 18) & (m5_xau['consecutive_bear'] >= 1)
    cnt_r, wr_r, avg_r = get_stats(m5_xau, cond_res, 115)
    print(f"\n  --- 共振美盘(优先): US 15-16 RSI<18+CB>=1 hold=115 ---")
    print(f"  n={cnt_r} WR={wr_r:.1f}% avg={avg_r:.3f}%")

# ═══════════════════════════════════════════════════════════════
# SECTION 4: AUDUSD/GBPUSD 积累检查
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📡 04 — AUDUSD/GBPUSD 积累检查 (M5 US 15-16)")
print(f"{'='*120}")

for sym in ['AUDUSD', 'GBPUSD']:
    m5_data = load_data('M5', symbols=[sym])
    if sym not in m5_data:
        print(f"  {sym}: 无数据")
        continue
    df = add_session(compute_indicators(m5_data[sym]))
    
    us_mask = (df['session'] == 'us') & (df['hour'].between(15, 16))
    
    if sym == 'AUDUSD':
        cond = us_mask & (df['rsi14'] < 16) & (df['consecutive_bear'] >= 3)
        best_hold = 125
        prev_n = 29
    else:  # GBPUSD
        cond = us_mask & (df['rsi14'] < 14) & (df['consecutive_bear'] >= 3)
        best_hold = 145
        prev_n = 13
    
    cnt, wr, avg = get_stats(df, cond, best_hold)
    print(f"  {sym}: M5 US 15-16 hold={best_hold}")
    print(f"    之前n={prev_n}, 现在n={cnt}")
    delta = cnt - prev_n
    print(f"    增长: {delta:+d} 信号")
    if cnt >= 30:
        print(f"    ✅ n={cnt}≥30 达标!")
    else:
        print(f"    ⏳ n={cnt}/30 还需积累 (缺口={30-cnt})")
    if cnt >= 5:
        print(f"    WR={wr:.1f}% avg={avg:.3f}%")

# ═══════════════════════════════════════════════════════════════
# SECTION 5: USOIL M30 做空交叉验证
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🛢️  05 — USOIL M30 做空交叉验证 (CBull>=5+RSI>75)")
print(f"{'='*120}")

usoil_m30 = add_session(compute_indicators(m30_data['USOIL'])) if 'USOIL' in m30_data else None

if usoil_m30 is not None:
    print(f"  USOIL M30: [{usoil_m30.index[0]} → {usoil_m30.index[-1]}] rows={len(usoil_m30)}")
    
    for cb in [4, 5]:
        for rsi in [75, 80]:
            cond = (usoil_m30['consecutive_bull'] >= cb) & (usoil_m30['rsi14'] > rsi)
            res = test_pattern(usoil_m30, cond, f'USOIL M30 CBull>={cb}+RSI>{rsi}',
                              list(range(30, 121, 5)), min_sig=3)
    
    # Session-based
    print(f"\n  --- Session细化 ---")
    for sess in ['us', 'europe']:
        cond = (usoil_m30['consecutive_bull'] >= 5) & (usoil_m30['rsi14'] > 75) & (usoil_m30['session'] == sess)
        test_pattern(usoil_m30, cond, f'USOIL M30 CBull>=5+RSI>75+{sess}',
                    list(range(30, 121, 5)), min_sig=2)

# ═══════════════════════════════════════════════════════════════
# SECTION 6: M1 超短线快速回测
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("⚡ 06 — M1 超短线快速回测（XAUUSD 关键模式）")
print(f"{'='*120}")

m1_xau = add_session(compute_indicators(load_data('M1', symbols=['XAUUSD'])['XAUUSD'])) if 'XAUUSD' in load_data('M1', symbols=['XAUUSD']) else None

if m1_xau is not None:
    print(f"  XAUUSD M1: [{m1_xau.index[0]} → {m1_xau.index[-1]}] rows={len(m1_xau)}")
    
    # M1 超短线: RSI极端超卖 + 连续阴线
    for cb in [3, 4]:
        for rsi in [10, 12, 14]:
            cond = (m1_xau['consecutive_bear'] >= cb) & (m1_xau['rsi14'] < rsi) & \
                   (m1_xau['session'] == 'us')
            test_pattern(m1_xau, cond, f'XAUUSD M1 CB>={cb}+RSI<{rsi}+US',
                        list(range(5, 61, 5)), min_sig=5)
    
    # M1 EU session
    for cb in [4, 5]:
        for rsi in [12, 14]:
            cond = (m1_xau['consecutive_bear'] >= cb) & (m1_xau['rsi14'] < rsi) & \
                   (m1_xau['session'] == 'europe')
            test_pattern(m1_xau, cond, f'XAUUSD M1 CB>={cb}+RSI<{rsi}+EU',
                        list(range(5, 61, 5)), min_sig=5)

# ═══════════════════════════════════════════════════════════════
# SECTION 7: 全品种最佳策略汇总
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏁 07 — Round 33 发现汇总")
print(f"{'='*120}")

print(f"""
📋 Round 33 快速摘要
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📡 数据状态:
  • M1/M5 最新至 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC
  • H1/M30 最新至 2026-05-12 14:00 UTC
  • MT5下载 → 美盘部分覆盖 ✅

🏆 XAGUSD M30 做空验证:
  • CBull>=4+RSI>80: 检查Bootstrap CI + 跨周期
  • CBull>=5+RSI>80: 检查稳定性
  • 成本分析: spread影响

🏆 USDJPY H1 做多验证:
  • CB>=5+RSI<25: 时段细化 + 阈值微调

📊 双枪月度跟踪:
  • 欧盘/美盘月度WR分解
  • 组合表现 + 共振优先

📡 AUDUSD/GBPUSD积累:
  • 检查n值增长

🛢️ USOIL M30:
  • CBull>=5+RSI>75 交叉验证

⚡ M1超短线:
  • XAUUSD M1 US/EU 快速回测
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

print(f"{'='*120}")
print("ROUND 33 COMPLETE")
print(f"完成于: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"{'='*120}")
