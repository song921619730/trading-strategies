#!/usr/bin/env python3
"""
Round 34 — 超短线 M1/M5 + H1/M30 深度验证与策略纳入
目标(state next_actions):
  1. XAUUSD M1 EU CB>=3+RSI<10 深度验证 (Bootstrap+跨周期+成本+hold微调)
  2. USDJPY H1 做多月度跟踪 (正式纳入best_known后首次)
  3. 双枪策略月度跟踪 (2026-06~07回撤窗口预警)
  4. USOIL M30 欧洲盘做空积累 (n=17→目标30)
  5. GBPUSD 美盘积累 (n=26/30, 缺口仅4)
  6. XAGUSD M30 做空策略重做 (修正方向)
  7. JP225/US500/US30 指数M5快速检查
"""
import sys, os, json
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')
from data_loader import load_data, compute_indicators
import pandas as pd
import numpy as np
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
            # 做多
            pnl = (df.iloc[pos + hold]['close'] - row['close']) / row['close'] * 100
            total += pnl
            count += 1
            if pnl > 0: hits += 1
    return count, hits/count*100 if count else 0, total/count if count else 0

def get_stats_short(df, mask, hold):
    """做空版本：价格下跌为盈利"""
    entries = df[mask]
    hits, total, count = 0, 0.0, 0
    for idx, row in entries.iterrows():
        pos = df.index.get_loc(idx)
        if pos + hold < len(df):
            pnl = (row['close'] - df.iloc[pos + hold]['close']) / row['close'] * 100
            total += pnl
            count += 1
            if pnl > 0: hits += 1
    return count, hits/count*100 if count else 0, total/count if count else 0

def test_pattern(df, cond, label, hold_list, min_sig=5, direction='long'):
    n = cond.sum()
    print(f"  {label:<55} n={n:<5}", end="")
    if n < min_sig:
        print(f"  跳过(<{min_sig})")
        return None
    best = {'hold': 0, 'wr': 0, 'avg': 0, 'n': 0}
    for hold in hold_list:
        if direction == 'short':
            cnt, wr, avg = get_stats_short(df, cond, hold)
        else:
            cnt, wr, avg = get_stats(df, cond, hold)
        if cnt >= 3 and wr > best['wr']:
            best = {'hold': hold, 'wr': wr, 'avg': avg, 'n': cnt}
    if best['wr'] >= 60:
        print(f" hold={best['hold']:3d} WR={best['wr']:.1f}% n={best['n']} avg={best['avg']:.3f}% ✅")
    else:
        print(f" hold={best['hold']:3d} WR={best['wr']:.1f}% n={best['n']} avg={best['avg']:.3f}%")
    return best

def bootstrap_ci(df, mask, hold, n_iter=5000, direction='long'):
    entries = df[mask]
    profits = []
    for idx, row in entries.iterrows():
        pos = df.index.get_loc(idx)
        if pos + hold < len(df):
            if direction == 'short':
                pnl = (row['close'] - df.iloc[pos + hold]['close']) / row['close'] * 100
            else:
                pnl = (df.iloc[pos + hold]['close'] - row['close']) / row['close'] * 100
            profits.append(1 if pnl > 0 else 0)
    if len(profits) < 5:
        return None, 0, 0, 0
    arr = np.array(profits)
    n = len(arr)
    obs_wr = arr.mean() * 100
    boot_means = np.array([np.random.choice(arr, n, replace=True).mean() for _ in range(n_iter)])
    ci = np.percentile(boot_means, [2.5, 97.5]) * 100
    return obs_wr, ci[0], ci[1], n

def cross_period_validation(df, mask, hold, n_periods=3, direction='long'):
    total_rows = len(df)
    chunk = total_rows // n_periods
    results = []
    for i in range(n_periods):
        start = i * chunk
        end = (i + 1) * chunk if i < n_periods - 1 else total_rows
        sub = df.iloc[start:end]
        sub_mask = mask.iloc[start:end]
        if direction == 'short':
            cnt, wr, avg = get_stats_short(sub, sub_mask, hold)
        else:
            cnt, wr, avg = get_stats(sub, sub_mask, hold)
        results.append({'period': i+1, 'n': cnt, 'wr': wr, 'avg': avg})
    return results

def monthly_tracking(df, cond, hold, label):
    """按月度统计表现"""
    df = df.copy()
    df['month'] = df.index.to_period('M')
    tn, tw, ta = 0, 0.0, 0.0
    print(f"\n  {label}")
    for month, grp in df.groupby('month'):
        cnt, wr, avg = get_stats(grp, cond.loc[grp.index], hold)
        if cnt > 0:
            marker = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}% {marker}")
            tn += cnt; tw += cnt*wr; ta += cnt*avg
    if tn > 0:
        print(f"  → 总计: n={tn} WR={tw/tn:.1f}% avg={ta/tn:.3f}%")
    return tn, tw/tn if tn else 0

print("=" * 120)
print("ROUND 34 — M1/M5 超短线深度验证 + 策略纳入")
print(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print("=" * 120)

# ═══════════════════════════════════════════════════════════
# 00: DATA FRESHNESS
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📡 00 — 数据新鲜度检查")
print(f"{'='*120}")
for tf in ['M1', 'M5', 'M30', 'H1']:
    d = os.path.join(BASE, 'data', tf)
    if not os.path.exists(d): continue
    files = [f for f in os.listdir(d) if f.endswith('.parquet')]
    if files:
        df = pd.read_parquet(os.path.join(d, files[0]))
        us13 = ((df.index.hour >= 13) & (df.index.hour < 18)).sum()
        us18 = (df.index.hour >= 18).sum()
        print(f"  {tf:4s}: 最新={df.index[-1]} 行数={len(df):>6} 品种={len(files)}")
        print(f"        US13-17={us13:>5} US18+={us18:>5}")

# ═══════════════════════════════════════════════════════════
# 01: XAUUSD M1 EU CB>=3+RSI<10 深度验证 (round34_001)
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 01 — XAUUSD M1 EU CB>=3+RSI<10 深度验证 (round34_001)")
print(f"{'='*120}")
m1 = load_data('M1', symbols=['XAUUSD'])
if 'XAUUSD' in m1:
    x1 = add_session(compute_indicators(m1['XAUUSD']))
    hr_fine = list(range(5, 101, 5))  # 精细hold扫描
    
    # 核心策略: CB>=3+RSI<10+EU
    print(f"\n  --- A: 核心策略深度验证 CB>=3+RSI<10+EU ---")
    cond_core = (x1['consecutive_bear']>=3) & (x1['rsi14']<10) & (x1['session']=='europe')
    r_core = test_pattern(x1, cond_core, 'XAUUSD M1 CB>=3+RSI<10+EU', hr_fine, 10)
    
    if r_core and r_core['n'] >= 20:
        best_h = r_core['hold']
        # Bootstrap
        ow, lo, hi, nb = bootstrap_ci(x1, cond_core, best_h)
        print(f"  Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        
        # Cross-period validation
        periods = cross_period_validation(x1, cond_core, best_h, 3)
        print(f"  跨周期验证 (hold={best_h}):")
        cp_ok = 0
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            if p['wr']>=60: cp_ok += 1
            print(f"     P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        print(f"  跨周期通过率: {cp_ok}/{len(periods)}")
        
        # Cost analysis
        if 'spread' in x1.columns:
            avg_spread = x1['spread'].mean()
            avg_price = x1['close'].mean()
            cost_pct = (avg_spread / avg_price) * 100
            print(f"  平均点差={avg_spread:.1f} 价格={avg_price:.2f} 成本≈{cost_pct:.4f}%")
            net_avg = r_core['avg'] - cost_pct
            print(f"  净收益(扣除点差)={net_avg:.3f}%")
        
        # Hold sensitivity: test nearby holds
        print(f"\n  --- B: Hold敏感性测试 (围绕{best_h}) ---")
        nearby = [h for h in range(max(10, best_h-20), min(100, best_h+21), 5)]
        for h in nearby:
            cnt, wr, avg = get_stats(x1, cond_core, h)
            if cnt > 0:
                print(f"    hold={h:3d}: n={cnt} WR={wr:.1f}% avg={avg:.3f}%")
    
    # CB>=4+RSI<10+EU (更严格)
    print(f"\n  --- C: 严格版 CB>=4+RSI<10+EU ---")
    cond_strict = (x1['consecutive_bear']>=4) & (x1['rsi14']<10) & (x1['session']=='europe')
    r_strict = test_pattern(x1, cond_strict, 'XAUUSD M1 CB>=4+RSI<10+EU', hr_fine, 5)
    
    # US 版对比
    print(f"\n  --- D: 美盘对比 CB>=3+RSI<10+US ---")
    cond_us = (x1['consecutive_bear']>=3) & (x1['rsi14']<10) & (x1['session']=='us')
    r_us = test_pattern(x1, cond_us, 'XAUUSD M1 CB>=3+RSI<10+US', hr_fine, 10)

# ═══════════════════════════════════════════════════════════
# 02: USDJPY H1 做多月度跟踪 (round34_002)
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 02 — USDJPY H1 做多月度跟踪 (round34_002)")
print(f"{'='*120}")
h1 = load_data('H1', symbols=['USDJPY'])
if 'USDJPY' in h1:
    uj = add_session(compute_indicators(h1['USDJPY']))
    hr_long = list(range(10, 201, 5))
    
    # 核心策略验证
    cond_cb5 = (uj['consecutive_bear']>=5) & (uj['rsi14']<25)
    print(f"\n  --- A: CB>=5+RSI<25 做多 (最佳hold=120) ---")
    r_uj = test_pattern(uj, cond_cb5, 'USDJPY H1 CB>=5+RSI<25', hr_long, 3)
    if r_uj and r_uj['n'] >= 10:
        ow, lo, hi, nb = bootstrap_ci(uj, cond_cb5, r_uj['hold'])
        print(f"  Bootstrap CI: [{lo:.1f}%, {hi:.1f}%] (n={nb})")
    
    # 月度跟踪
    print(f"\n  --- B: 月度表现跟踪 (hold=120) ---")
    monthly_tracking(uj, cond_cb5, 120, 'USDJPY H1 CB>=5+RSI<25 hold=120')
    
    # 宽松版CB>=4+RSI<30
    cond_cb4 = (uj['consecutive_bear']>=4) & (uj['rsi14']<30)
    print(f"\n  --- C: 宽松版 CB>=4+RSI<30 ---")
    r_uj4 = test_pattern(uj, cond_cb4, 'USDJPY H1 CB>=4+RSI<30', hr_long, 10)

# ═══════════════════════════════════════════════════════════
# 03: 双枪策略月度跟踪 (round34_003)
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📊 03 — 双枪策略月度跟踪 (round34_003)")
print(f"{'='*120}")
m5 = load_data('M5', symbols=['XAUUSD'])
if 'XAUUSD' in m5:
    xu = add_session(compute_indicators(m5['XAUUSD']))
    xu['month'] = xu.index.to_period('M')
    
    ceu = (xu['session']=='europe') & (xu['hour'].between(9,11)) & (xu['rsi14']<18) & (xu['consecutive_bear']>=4)
    cus = (xu['session']=='us') & (xu['hour'].between(15,16)) & (xu['rsi14']<20) & (xu['consecutive_bear']>=2)
    
    print(f"\n  欧盘: EU 9-11 RSI<18+CB>=4 hold=42")
    teu, weu, aeu = 0, 0.0, 0.0
    for month, grp in xu.groupby('month'):
        cnt, wr, avg = get_stats(grp, ceu.loc[grp.index], 42)
        if cnt > 0:
            marker = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}% {marker}")
            teu += cnt; weu += cnt*wr; aeu += cnt*avg
    if teu > 0:
        print(f"  → 总计: n={teu} WR={weu/teu:.1f}% avg={aeu/teu:.3f}%")
    
    print(f"\n  美盘: US 15-16 RSI<20+CB>=2 hold=115")
    tus, wus, aus = 0, 0.0, 0.0
    for month, grp in xu.groupby('month'):
        cnt, wr, avg = get_stats(grp, cus.loc[grp.index], 115)
        if cnt > 0:
            marker = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}% {marker}")
            tus += cnt; wus += cnt*wr; aus += cnt*avg
    if tus > 0:
        print(f"  → 总计: n={tus} WR={wus/tus:.1f}% avg={aus/tus:.3f}%")
    
    combo_n = teu + tus
    combo_wr = (weu + wus) / combo_n if combo_n > 0 else 0
    print(f"\n  双枪组合: n={combo_n} WR={combo_wr:.1f}% 频率={combo_n/5:.1f}次/月")
    print(f"  ⚠️ 2026-06~07 需关注季节性回撤窗口")
    
    # 共振美盘
    cres = (xu['session']=='us') & (xu['hour'].between(15,16)) & (xu['rsi14']<18) & (xu['consecutive_bear']>=1)
    print(f"\n  共振美盘: US 15-16 RSI<18+CB>=1 hold=115")
    cnt, wr, avg = get_stats(xu, cres, 115)
    print(f"  n={cnt} WR={wr:.1f}% avg={avg:.3f}%")

# ═══════════════════════════════════════════════════════════
# 04: USOIL M30 欧洲盘做空积累 (round34_004)
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🛢️  04 — USOIL M30 欧洲盘做空积累 (round34_004)")
print(f"{'='*120}")
m30 = load_data('M30', symbols=['USOIL', 'XAGUSD'])
if 'USOIL' in m30:
    usl = add_session(compute_indicators(m30['USOIL']))
    hr30 = list(range(30, 151, 5))
    
    print(f"\n  --- A: CBull>=5+RSI>75+europe (积累阶段) ---")
    cond_eu_short = (usl['consecutive_bull']>=5) & (usl['rsi14']>75) & (usl['session']=='europe')
    r_eu = test_pattern(usl, cond_eu_short, 'USOIL M30 CBull>=5+RSI>75+europe', hr30, 3, 'short')
    if r_eu and r_eu['n'] >= 10:
        ow, lo, hi, nb = bootstrap_ci(usl, cond_eu_short, r_eu['hold'], direction='short')
        print(f"  Bootstrap CI: [{lo:.1f}%, {hi:.1f}%] (n={nb})")
    
    print(f"\n  --- B: CBull>=5+RSI>75+us ---")
    cond_us_short = (usl['consecutive_bull']>=5) & (usl['rsi14']>75) & (usl['session']=='us')
    test_pattern(usl, cond_us_short, 'USOIL M30 CBull>=5+RSI>75+us', hr30, 3, 'short')
    
    print(f"\n  --- C: 全样本做空 ---")
    for cb in [4,5]:
        for rsi in [75,80]:
            cond = (usl['consecutive_bull']>=cb) & (usl['rsi14']>rsi)
            test_pattern(usl, cond, f'USOIL M30 CBull>={cb}+RSI>{rsi}', hr30, 5, 'short')

# ═══════════════════════════════════════════════════════════
# 05: XAGUSD M30 做空策略重做 (round34_007) — 修正方向
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🔴 05 — XAGUSD M30 做空策略重做 (round34_007)")
print(f"   修正Round32方向错误，使用 get_stats_short 重测")
print(f"{'='*120}")
if 'XAGUSD' in m30:
    xag = add_session(compute_indicators(m30['XAGUSD']))
    hr30x = list(range(15, 121, 5))
    
    print(f"\n  --- A: CBull>=4+RSI>80 (Round32声称WR=95.2%) ---")
    for cb, rsi in [(4,80),(5,80),(5,75),(4,75),(6,80)]:
        cond = (xag['consecutive_bull']>=cb) & (xag['rsi14']>rsi)
        r = test_pattern(xag, cond, f'XAGUSD M30 SHORT CBull>={cb}+RSI>{rsi}', hr30x, 5, 'short')
        if r and r['n'] >= 10:
            ow, lo, hi, nb = bootstrap_ci(xag, cond, r['hold'], direction='short')
            print(f"    Bootstrap CI: [{lo:.1f}%, {hi:.1f}%] (n={nb})")
            periods = cross_period_validation(xag, cond, r['hold'], 3, 'short')
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期通过率: {cp_ok}/{len(periods)}")
            for p in periods:
                m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
    
    print(f"\n  --- B: 时段细分 (CBull>=4+RSI>80) ---")
    for sess in ['us','europe','asia']:
        cond = (xag['consecutive_bull']>=4) & (xag['rsi14']>80) & (xag['session']==sess)
        test_pattern(xag, cond, f'XAGUSD M30 SHORT CBull>=4+RSI>80+{sess}', hr30x, 3, 'short')

# ═══════════════════════════════════════════════════════════
# 06: GBPUSD/JP225 积累检查 (round34_005)
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📡 06 — GBPUSD/JP225/US500/US30 积累检查 (round34_005/006)")
print(f"{'='*120}")
# Load M5 for all targets
m5_all = load_data('M5', symbols=['GBPUSD', 'AUDUSD', 'JP225', 'US500', 'US30', 'XAGUSD'])

for sym, params in [
    ('GBPUSD', (14, 3, 145, 26)),
    ('AUDUSD', (16, 3, 125, 45)),
    ('JP225', (14, 2, 55, 64)),
    ('XAGUSD', (18, 3, 105, 31)),
]:
    if sym not in m5_all:
        print(f"  {sym}: 无数据"); continue
    df = add_session(compute_indicators(m5_all[sym]))
    usm = (df['session']=='us') & (df['hour'].between(15,16))
    rsi_th, cb_th, hold, prev_n = params
    cond = usm & (df['rsi14']<rsi_th) & (df['consecutive_bear']>=cb_th)
    cnt, wr, avg = get_stats(df, cond, hold)
    print(f"  {sym}: hold={hold} 之前n={prev_n} 现在n={cnt} 增长={cnt-prev_n:+d}")
    if cnt >= 5:
        print(f"    WR={wr:.1f}% avg={avg:.3f}%")
    if cnt >= 30:
        print(f"    ✅ n={cnt}≥30 达标!")
    else:
        print(f"    ⏳ n={cnt}/30 缺口={max(0,30-cnt)}")

# US500 / US30 快速检查
print(f"\n  --- US500/US30 指数M5快速检查 ---")
for sym in ['US500', 'US30']:
    if sym not in m5_all:
        print(f"  {sym}: 无数据"); continue
    df = add_session(compute_indicators(m5_all[sym]))
    usm = (df['session']=='us') & (df['hour'].between(15,16))
    for rsi_th, cb_th, hold, label in [
        (14, 2, 55, 'RSI<14+CB>=2'),
        (14, 3, 55, 'RSI<14+CB>=3'),
        (18, 2, 55, 'RSI<18+CB>=2'),
    ]:
        cond = usm & (df['rsi14']<rsi_th) & (df['consecutive_bear']>=cb_th)
        cnt, wr, avg = get_stats(df, cond, hold)
        if cnt >= 3:
            print(f"  {sym} US {label} hold={hold}: n={cnt} WR={wr:.1f}% avg={avg:.3f}%")

# ═══════════════════════════════════════════════════════════
# 07: XAUUSD M5 追加 — 检查双枪之外的策略
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏁 07 — XAUUSD M5 其他时段策略探索")
print(f"{'='*120}")
if 'XAUUSD' in m5:
    xu2 = add_session(compute_indicators(m5['XAUUSD']))
    hr5 = list(range(5, 121, 5))
    
    # 欧洲盘其他小时
    for hr in [8, 12, 13]:
        cond = (xu2['session']=='europe') & (xu2['hour']==hr) & (xu2['rsi14']<18) & (xu2['consecutive_bear']>=4)
        test_pattern(xu2, cond, f'XAUUSD M5 EU hour={hr} RSI<18+CB>=4', hr5, 5)
    
    # 美盘盘初 (13-14)
    cond = (xu2['session']=='us') & (xu2['hour'].between(13,14)) & (xu2['rsi14']<20) & (xu2['consecutive_bear']>=3)
    test_pattern(xu2, cond, 'XAUUSD M5 US 13-14 RSI<20+CB>=3', hr5, 5)
    
    # 美盘盘后 (17-18)
    cond = (xu2['session']=='us') & (xu2['hour'].between(17,18)) & (xu2['rsi14']<20) & (xu2['consecutive_bear']>=3)
    test_pattern(xu2, cond, 'XAUUSD M5 US 17-18 RSI<20+CB>=3', hr5, 5)

# ═══════════════════════════════════════════════════════════
# 08: 数据质量问题备注
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📝 08 — 数据质量备注")
print(f"{'='*120}")
print(f"  M1/M5 最新数据: 检查上方00节")
print(f"  美盘覆盖: US13-17和US18+计数见00节")
print(f"  若US18+为0，说明美盘后半段未下载")
print(f"  Fix: 调整下载时间至18-20 UTC (当前约13 UTC下载)")

print(f"\n{'='*120}")
print("ROUND 34 COMPLETE")
print(f"完成于: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print(f"{'='*120}")
