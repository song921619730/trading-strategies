#!/usr/bin/env python3
"""
Round 33 — 超短线 M1/M5 + H1/M30 深度验证与月度跟踪
目标:
  1. XAGUSD M30 做空深度验证 (CBull>=4+RSI>80)
  2. USDJPY H1 做多交叉验证 (CB>=5+RSI<25)
  3. 双枪策略月度跟踪 (欧盘+美盘)
  4. AUDUSD/GBPUSD/USOIL 积累检查
  5. USOIL M30 做空交叉验证
  6. M1超短线快速回测
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
            pnl = (df.iloc[pos + hold]['close'] - row['close']) / row['close'] * 100
            total += pnl
            count += 1
            if pnl > 0: hits += 1
    return count, hits/count*100 if count else 0, total/count if count else 0

def test_pattern(df, cond, label, hold_list, min_sig=5):
    n = cond.sum()
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

def bootstrap_ci(df, mask, hold, n_iter=5000):
    entries = df[mask]
    profits = []
    for idx, row in entries.iterrows():
        pos = df.index.get_loc(idx)
        if pos + hold < len(df):
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

def cross_period_validation(df, mask, hold, n_periods=3):
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

print("=" * 120)
print("ROUND 33 — M1/M5 超短线深度验证 + 月度跟踪")
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
# 01: XAGUSD M30 深度验证
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 01 — XAGUSD M30 做空深度验证")
print(f"{'='*120}")
m30 = load_data('M30', symbols=['XAGUSD','USOIL','USDJPY'])
if 'XAGUSD' in m30:
    xag = add_session(compute_indicators(m30['XAGUSD']))
    hold_range = list(range(30, 121, 5))
    
    cond1 = (xag['consecutive_bull'] >= 4) & (xag['rsi14'] > 80)
    print(f"\n  --- A: CBull>=4+RSI>80 (核心策略) ---")
    r1 = test_pattern(xag, cond1, 'XAGUSD M30 CBull>=4+RSI>80', hold_range, 3)
    if r1 and r1['n'] >= 10:
        ow, lo, hi, nb = bootstrap_ci(xag, cond1, r1['hold'])
        print(f"  Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb})")
        periods = cross_period_validation(xag, cond1, r1['hold'], 3)
        print(f"  跨周期:")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"     P{p['period']}: n={p['n']} WR={p['wr']:.1f}% {m}")
        if 'spread' in xag.columns:
            asp = xag['spread'].mean()
            scost = asp * 0.01 / 24 * 100
            print(f"  平均点差={asp:.1f} 成本≈{scost:.4f}% 净收益={r1['avg']-scost:.3f}%")
    
    for cb,rsi in [(5,80),(5,75)]:
        cond = (xag['consecutive_bull'] >= cb) & (xag['rsi14'] > rsi)
        print(f"\n  --- B: CBull>={cb}+RSI>{rsi} ---")
        r = test_pattern(xag, cond, f'XAGUSD M30 CBull>={cb}+RSI>{rsi}', hold_range, 3)
        if r and r['n'] >= 10:
            ow, lo, hi, nb = bootstrap_ci(xag, cond, r['hold'])
            print(f"  Bootstrap CI: [{lo:.1f}%, {hi:.1f}%]")

    # Doji + RSI>75 + US
    doji = (abs(xag['close']-xag['open'])/(xag['high']-xag['low']).replace(0,np.nan)) < 0.1
    cond4 = doji & (xag['rsi14']>75) & (xag['session']=='us')
    print(f"\n  --- C: Doji+RSI>75+US ---")
    test_pattern(xag, cond4, 'XAGUSD M30 Doji+RSI>75+US', hold_range, 3)

# ═══════════════════════════════════════════════════════════
# 02: USDJPY H1 交叉验证
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 02 — USDJPY H1 做多交叉验证")
print(f"{'='*120}")
h1 = load_data('H1', symbols=['USDJPY','XAGUSD'])
if 'USDJPY' in h1:
    uj = add_session(compute_indicators(h1['USDJPY']))
    hr = list(range(10, 181, 5))
    
    cond = (uj['consecutive_bear'] >= 5) & (uj['rsi14'] < 25)
    print(f"\n  --- A: CB>=5+RSI<25 (做多) ---")
    r = test_pattern(uj, cond, 'USDJPY H1 CB>=5+RSI<25', hr, 3)
    if r and r['n'] >= 10:
        ow, lo, hi, nb = bootstrap_ci(uj, cond, r['hold'])
        print(f"  Bootstrap CI: [{lo:.1f}%, {hi:.1f}%] (n={nb})")
    
    print(f"\n  --- B: 时段细化 ---")
    for sess in ['asia','europe','us']:
        cs = (uj['consecutive_bear']>=5) & (uj['rsi14']<25) & (uj['session']==sess)
        test_pattern(uj, cs, f'USDJPY H1 CB>=5+RSI<25+{sess}', hr, 2)
    
    print(f"\n  --- C: 阈值微调 ---")
    for cb in [4,5,6]:
        for rsi in [20,25,30]:
            ca = (uj['consecutive_bear']>=cb) & (uj['rsi14']<rsi)
            test_pattern(uj, ca, f'USDJPY H1 CB>={cb}+RSI<{rsi}', hr, 3)

# ═══════════════════════════════════════════════════════════
# 03: 双枪策略月度跟踪
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📊 03 — 双枪策略月度跟踪 (M5 XAUUSD)")
print(f"{'='*120}")
m5 = load_data('M5', symbols=['XAUUSD','AUDUSD','GBPUSD','US30','JP225'])
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
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}%")
            teu += cnt; weu += cnt*wr; aeu += cnt*avg
    if teu > 0:
        print(f"  → 总计: n={teu} WR={weu/teu:.1f}% avg={aeu/teu:.3f}%")
    
    print(f"\n  美盘: US 15-16 RSI<20+CB>=2 hold=115")
    tus, wus, aus = 0, 0.0, 0.0
    for month, grp in xu.groupby('month'):
        cnt, wr, avg = get_stats(grp, cus.loc[grp.index], 115)
        if cnt > 0:
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}%")
            tus += cnt; wus += cnt*wr; aus += cnt*avg
    if tus > 0:
        print(f"  → 总计: n={tus} WR={wus/tus:.1f}% avg={aus/tus:.3f}%")
    
    combo_n = teu + tus
    combo_wr = (weu + wus) / combo_n if combo_n > 0 else 0
    print(f"\n  双枪组合: n={combo_n} WR={combo_wr:.1f}% 频率={combo_n/5:.1f}次/月")
    
    cres = (xu['session']=='us') & (xu['hour'].between(15,16)) & (xu['rsi14']<18) & (xu['consecutive_bear']>=1)
    cnt, wr, avg = get_stats(xu, cres, 115)
    print(f"\n  共振美盘: US 15-16 RSI<18+CB>=1 hold=115")
    print(f"  n={cnt} WR={wr:.1f}% avg={avg:.3f}%")

# ═══════════════════════════════════════════════════════════
# 04: AUDUSD/GBPUSD 积累检查
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📡 04 — AUDUSD/GBPUSD 积累检查")
print(f"{'='*120}")
for sym, params in [('AUDUSD',(16,3,125,29)), ('GBPUSD',(14,3,145,13))]:
    if sym not in m5:
        print(f"  {sym}: 无数据"); continue
    df = add_session(compute_indicators(m5[sym]))
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

# ═══════════════════════════════════════════════════════════
# 05: USOIL M30 做空
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🛢️  05 — USOIL M30 做空验证")
print(f"{'='*120}")
if 'USOIL' in m30:
    usl = add_session(compute_indicators(m30['USOIL']))
    hr = list(range(30, 121, 5))
    for cb in [4,5]:
        for rsi in [75,80]:
            cond = (usl['consecutive_bull']>=cb) & (usl['rsi14']>rsi)
            test_pattern(usl, cond, f'USOIL M30 CBull>={cb}+RSI>{rsi}', hr, 3)
    for sess in ['us','europe']:
        cond = (usl['consecutive_bull']>=5) & (usl['rsi14']>75) & (usl['session']==sess)
        test_pattern(usl, cond, f'USOIL M30 CBull>=5+RSI>75+{sess}', hr, 2)

# ═══════════════════════════════════════════════════════════
# 06: M1 超短线快测
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("⚡ 06 — M1 超短线快测 (XAUUSD)")
print(f"{'='*120}")
m1 = load_data('M1', symbols=['XAUUSD'])
if 'XAUUSD' in m1:
    x1 = add_session(compute_indicators(m1['XAUUSD']))
    hr = list(range(5, 61, 5))
    for sess, sym in [('us','US'),('europe','EU')]:
        for cb in [3,4]:
            for rsi in [10,12,14]:
                cond = (x1['consecutive_bear']>=cb) & (x1['rsi14']<rsi) & (x1['session']==sess)
                test_pattern(x1, cond, f'XAUUSD M1 CB>={cb}+RSI<{rsi}+{sym}', hr, 5)

# ═══════════════════════════════════════════════════════════
# 07: US30/JP225 M5 快速检查
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏁 07 — US30/JP225 M5 快速检查")
print(f"{'='*120}")
for sym in ['US30','JP225']:
    if sym not in m5: continue
    df = add_session(compute_indicators(m5[sym]))
    usm = (df['session']=='us') & (df['hour'].between(15,16))
    cond = usm & (df['rsi14']<14) & (df['consecutive_bear']>=2)
    cnt, wr, avg = get_stats(df, cond, 55)
    if cnt > 0:
        print(f"  {sym}: n={cnt} WR={wr:.1f}% avg={avg:.3f}% (US 15-16 RSI<14+CB>=2 hold=55)")

print(f"\n{'='*120}")
print("ROUND 33 COMPLETE")
print(f"完成于: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"{'='*120}")
