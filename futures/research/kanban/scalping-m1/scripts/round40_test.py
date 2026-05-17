#!/usr/bin/env python3
"""
Round 40 — XAUUSD M1 US月度跟踪续跑(第2月) + 各策略续跑 + 新品种探索
目标(state next_actions):
  1. XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第2月)+双极值联合监控
  2. XAGUSD M5 EU CB>=3+RSI<10 n=42→目标60持续监控(阈值调整探索)
  3. EURUSD H1做多月度跟踪(第8月)
  4. US500 M5 EU CB>=4+RSI<14 月度跟踪续跑(第2月)
  5. XAGUSD M30 SHORT CBull>=4+RSI>85+us WR=100% n=10 → 积累验证(n→20)
  6. US30 M1 EU 时段子策略(H8/H9/H10)重验证+CB>=3+RSI<14替代方案确认
  7. JP225 H1/M30做多月度跟踪(第4月)
  8. XAUUSD M1 EU极值月度跟踪续跑+US极值月度跟踪(第2月)
  9. UKOIL M30做多n=32数据覆盖深度检查(扩展至M5/M15)
新增探索:
  10. GBPUSD H1/M30 做多策略探索
  11. AUDUSD H1/M30 做多策略探索
  12. HK50 H1/M30 做多策略探索
  13. USOIL M30 InsideBar+RSI 深入探索
时间框架: H1, M30, M5, M1
品种: 多品种 (含XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, US30, US500, USTEC, JP225, HK50, UKOIL, USOIL)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_data, compute_indicators
import pandas as pd
import numpy as np
from datetime import datetime

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

def get_stats_short(df, mask, hold):
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

# 形态检测
def detect_inside_bar(df):
    return (df['high'] < df['high'].shift(1)) & (df['low'] > df['low'].shift(1))

def detect_doji(df, body_pct=0.1):
    body = abs(df['close'] - df['open'])
    total = df['high'] - df['low']
    return (body / total.replace(0, np.nan)) < body_pct

def detect_engulfing_bull(df):
    return (df['close'] > df['open']) & (df['close'].shift(1) < df['open'].shift(1)) & \
           (df['close'] > df['open'].shift(1)) & (df['open'] < df['close'].shift(1))

def detect_engulfing_bear(df):
    return (df['close'] < df['open']) & (df['close'].shift(1) > df['open'].shift(1)) & \
           (df['close'] < df['open'].shift(1)) & (df['open'] > df['close'].shift(1))

def detect_hammer(df, body_ratio=0.3, wick_ratio=2.0):
    body = abs(df['close'] - df['open'])
    lower_wick = df[['open', 'close']].min(axis=1) - df['low']
    upper_wick = df['high'] - df[['open', 'close']].max(axis=1)
    total_range = df['high'] - df['low']
    return (lower_wick > body * wick_ratio) & (upper_wick < body * body_ratio) & (total_range > 0)

def detect_shooting_star(df, body_ratio=0.3, wick_ratio=2.0):
    body = abs(df['close'] - df['open'])
    lower_wick = df[['open', 'close']].min(axis=1) - df['low']
    upper_wick = df['high'] - df[['open', 'close']].max(axis=1)
    total_range = df['high'] - df['low']
    return (upper_wick > body * wick_ratio) & (lower_wick < body * body_ratio) & (total_range > 0)

# ============================================================
# MAIN
# ============================================================

results = {}
all_best_findings = []

print("=" * 120)
print("ROUND 40 — XAUUSD M1 US月度跟踪续跑(第2月) + 各策略续跑 + 新品种探索")
print(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print("品种: 期货外汇14品种 (XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, US30, US500, USTEC, JP225, HK50, UKOIL, USOIL)")
print("时间框架: H1, M30, M5, M1")
print("=" * 120)

# ═══════════════════════════════════════════════════════════════
# 00: DATA FRESHNESS CHECK
# ═══════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════
all_symbols = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
               "US30", "US500", "USTEC", "JP225", "HK50", "UKOIL", "USOIL"]

h1_data = {}
m30_data = {}
m5_data = {}
m1_data = {}

for tf, store in [("H1", h1_data), ("M30", m30_data), ("M5", m5_data), ("M1", m1_data)]:
    print(f"\n{'='*120}")
    print(f"📊 加载 {tf} 数据")
    print(f"{'='*120}")
    raw = load_data(tf, symbols=all_symbols)
    for sym in all_symbols:
        if sym in raw:
            df = compute_indicators(raw[sym])
            df = add_session(df)
            store[sym] = df
            print(f"  {sym:8s}: {len(df):>5} rows  [{df.index[0].date()} → {df.index[-1].date()}]  "
                  f"Close={df['close'].iloc[-1]:.1f}  RSI={df['rsi14'].iloc[-1]:.1f}")
        else:
            print(f"  ⚠️  {sym}: 数据不可用")

# ═══════════════════════════════════════════════════════════════
# round40_001: XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第2月)+双极值联合监控
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏅 01 — XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第2月)+双极值联合监控 (round40_001)")
print(f"{'='*120}")

if "XAUUSD" in m1_data:
    xu = m1_data["XAUUSD"]
    hr = list(range(10, 121, 5))

    # A: XAUUSD M1 US CB>=3+RSI<10 (核心策略, 月度跟踪第2月)
    print(f"\n  --- A: XAUUSD M1 US CB>=3+RSI<10 (核心, 月度跟踪第2月) ---")
    cond_us_strong = (xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session']=='us')
    r_us_strong = test_pattern(xu, cond_us_strong, 'XAUUSD M1 US CB>=3+RSI<10', hr, 10)
    if r_us_strong and r_us_strong['n'] >= 15:
        best_h = r_us_strong['hold']
        ow, lo, hi, nb = bootstrap_ci(xu, cond_us_strong, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xu, cond_us_strong, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        all_best_findings.append((f"XAUUSD_M1_US_CB>=3_RSI<10", r_us_strong['wr'], r_us_strong['n'], best_h, r_us_strong['avg']))

        # 月度跟踪续跑(第2月)
        monthly_tracking(xu, cond_us_strong, best_h,
                         f'XAUUSD M1 US CB>=3+RSI<10 hold={best_h} 月度跟踪(第2月续跑)')

    # B: XAUUSD M1 US CB>=2+RSI<10 (基础极值, 持续监控)
    print(f"\n  --- B: XAUUSD M1 US CB>=2+RSI<10 (基础极值, 持续监控) ---")
    cond_us_base = (xu['consecutive_bear']>=2) & (xu['rsi14']<10) & (xu['session']=='us')
    r_us_base = test_pattern(xu, cond_us_base, 'XAUUSD M1 US CB>=2+RSI<10', hr, 10)
    if r_us_base and r_us_base['n'] >= 15:
        best_h = r_us_base['hold']
        ow, lo, hi, nb = bootstrap_ci(xu, cond_us_base, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xu, cond_us_base, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        all_best_findings.append((f"XAUUSD_M1_US_CB>=2_RSI<10", r_us_base['wr'], r_us_base['n'], best_h, r_us_base['avg']))

    # C: 双极值联合分析 (EU+US)
    print(f"\n  --- C: XAUUSD M1 双极值联合监控 (EU+US) ---")
    cond_dual = ((xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session'].isin(['europe','us'])))
    r_dual = test_pattern(xu, cond_dual, 'XAUUSD M1 US/EU Dual CB>=3+RSI<10', hr, 10)
    if r_dual and r_dual['n'] >= 10:
        best_h = r_dual['hold']
        ow, lo, hi, nb = bootstrap_ci(xu, cond_dual, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xu, cond_dual, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        all_best_findings.append((f"XAUUSD_M1_DUAL_CB>=3_RSI<10", r_dual['wr'], r_dual['n'], r_dual['hold'], r_dual['avg']))

    # D: 极值信号频率统计
    print(f"\n  --- D: 极值信号频率统计 ---")
    eu_count = ((xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session']=='europe')).sum()
    us_strong_count = cond_us_strong.sum()
    us_base_count = cond_us_base.sum()
    dual_count = cond_dual.sum()
    print(f"    EU 极值 (CB>=3+RSI<10):        {eu_count} 信号")
    print(f"    US 极值-强 (CB>=3+RSI<10):     {us_strong_count} 信号")
    print(f"    US 极值-基础 (CB>=2+RSI<10):   {us_base_count} 信号")
    print(f"    双极值联合 (EU+US强):           {dual_count} 信号")

# ═══════════════════════════════════════════════════════════════
# round40_002: XAGUSD M5 EU CB>=3+RSI<10 n=42→目标60持续监控(阈值调整探索)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥈 02 — XAGUSD M5 EU 做多积累监控 (round40_002) n=42→目标60 阈值调整探索")
print(f"{'='*120}")

if "XAGUSD" in m5_data:
    xag5 = m5_data["XAGUSD"]
    hr5 = list(range(5, 61, 5))

    # A: 原策略持续监控 CB>=3+RSI<10
    print(f"\n  --- A: XAGUSD M5 EU CB>=3+RSI<10 (原策略, n跟踪) ---")
    cond3 = (xag5['consecutive_bear']>=3) & (xag5['rsi14']<10) & (xag5['session']=='europe')
    r3 = test_pattern(xag5, cond3, 'XAGUSD M5 EU LONG CB>=3+RSI<10', hr5, 10)
    if r3 and r3['n'] >= 15:
        best_h = r3['hold']
        ow, lo, hi, nb = bootstrap_ci(xag5, cond3, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xag5, cond3, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        all_best_findings.append((f"XAGUSD_M5_EU_LONG_CB>=3_RSI<10", r3['wr'], r3['n'], best_h, r3['avg']))

    # B: 阈值调整探索 — 放宽CB或RSI以增加信号数量
    print(f"\n  --- B: XAGUSD M5 EU 阈值扫描 (放宽阈值以增加信号量) ---")
    for cb, rsi in [(3,14), (2,10), (2,14), (4,14), (3,18), (4,18), (2,8), (5,14)]:
        cond = (xag5['consecutive_bear']>=cb) & (xag5['rsi14']<rsi) & (xag5['session']=='europe')
        r = test_pattern(xag5, cond, f'XAGUSD M5 EU CB>={cb}+RSI<{rsi}', hr5, 5)
        if r and r['n'] >= 15 and r['wr'] >= 65:
            best_h = r['hold']
            periods = cross_period_validation(xag5, cond, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
            all_best_findings.append((f"XAGUSD_M5_EU_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # C: XAGUSD M5 US 时段探索 (美盘信号是否更多?)
    print(f"\n  --- C: XAGUSD M5 US 做多探索 ---")
    for cb, rsi in [(2,10), (3,10), (2,14), (3,14), (4,18), (2,18)]:
        cond = (xag5['consecutive_bear']>=cb) & (xag5['rsi14']<rsi) & (xag5['session']=='us')
        r = test_pattern(xag5, cond, f'XAGUSD M5 US LONG CB>={cb}+RSI<{rsi}', hr5, 5)
        if r and r['n'] >= 10 and r['wr'] >= 65:
            all_best_findings.append((f"XAGUSD_M5_US_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

    # D: XAGUSD M5 形态+RSI 组合
    print(f"\n  --- D: XAGUSD M5 形态+RSI 组合探索 ---")
    # 锤子线+RSI<20
    hammer = detect_hammer(xag5)
    cond_hammer = hammer & (xag5['rsi14']<20)
    r_ham = test_pattern(xag5, cond_hammer, 'XAGUSD M5 Hammer+RSI<20 LONG', hr5, 3)
    if r_ham and r_ham['n'] >= 5:
        all_best_findings.append((f"XAGUSD_M5_Hammer_RSI<20", r_ham['wr'], r_ham['n'], r_ham['hold'], r_ham['avg']))

    # InsideBar + RSI
    inside = detect_inside_bar(xag5)
    cond_inside_xag = inside & (xag5['rsi14']<20)
    r_in_xag = test_pattern(xag5, cond_inside_xag, 'XAGUSD M5 InsideBar+RSI<20 LONG', hr5, 3)
    if r_in_xag and r_in_xag['n'] >= 5:
        all_best_findings.append((f"XAGUSD_M5_InsideBar_RSI<20", r_in_xag['wr'], r_in_xag['n'], r_in_xag['hold'], r_in_xag['avg']))

# ═══════════════════════════════════════════════════════════════
# round40_003: EURUSD H1做多月度跟踪(第8月)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("💰 03 — EURUSD H1 做多月度跟踪 (round40_003) 第8月")
print(f"{'='*120}")

if "EURUSD" in h1_data:
    eu = h1_data["EURUSD"]
    hr = list(range(10, 121, 5))

    print(f"\n  --- EURUSD H1 CB+RSI 做多验证 ---")
    for cb, rsi in [(3,20), (3,25), (4,20), (4,25), (5,25)]:
        cond = (eu['consecutive_bear']>=cb) & (eu['rsi14']<rsi)
        r = test_pattern(eu, cond, f'EURUSD H1 LONG CB>={cb}+RSI<{rsi}', hr, 5)
        if r and r['n'] >= 10:
            best_h = r['hold']
            ow, lo, hi, nb = bootstrap_ci(eu, cond, best_h)
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(eu, cond, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
            for p in periods:
                m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
            all_best_findings.append((f"EURUSD_H1_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # 月度跟踪 CB>=3+RSI<25 (第8月)
    cond_track = (eu['consecutive_bear']>=3) & (eu['rsi14']<25)
    r_track = test_pattern(eu, cond_track, 'EURUSD H1 CB>=3+RSI<25 (最优hold)', hr, 5)
    if r_track and r_track['n'] >= 10:
        monthly_tracking(eu, cond_track, r_track['hold'],
                         f'EURUSD H1 CB>=3+RSI<25 hold={r_track["hold"]} 月度跟踪(第8月)')

    # EURUSD M30 验证
    if "EURUSD" in m30_data:
        eum30 = m30_data["EURUSD"]
        hr30_m = list(range(10, 121, 5))
        print(f"\n  --- EURUSD M30 CB+RSI 做多验证 ---")
        for cb, rsi in [(3,20), (3,25), (4,20), (2,20)]:
            cond = (eum30['consecutive_bear']>=cb) & (eum30['rsi14']<rsi)
            r = test_pattern(eum30, cond, f'EURUSD M30 LONG CB>={cb}+RSI<{rsi}', hr30_m, 5)
            if r and r['n'] >= 10:
                best_h = r['hold']
                ow, lo, hi, nb = bootstrap_ci(eum30, cond, best_h)
                print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
                periods = cross_period_validation(eum30, cond, best_h, 3)
                cp_ok = sum(1 for p in periods if p['wr']>=60)
                print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
                all_best_findings.append((f"EURUSD_M30_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # EURUSD H1 形态探索
    print(f"\n  --- EURUSD H1 形态组合探索 ---")
    hammer = detect_hammer(eu)
    engulf_bull = detect_engulfing_bull(eu)
    inside = detect_inside_bar(eu)
    
    hammer_cond = hammer & (eu['rsi14']<30)
    r_ham_eu = test_pattern(eu, hammer_cond, 'EURUSD H1 Hammer+RSI<30 LONG', hr, 3)
    if r_ham_eu and r_ham_eu['n'] >= 5:
        all_best_findings.append((f"EURUSD_H1_Hammer_RSI<30", r_ham_eu['wr'], r_ham_eu['n'], r_ham_eu['hold'], r_ham_eu['avg']))
    
    engulf_cond = engulf_bull & (eu['rsi14']<30)
    r_eng_eu = test_pattern(eu, engulf_cond, 'EURUSD H1 EngulfBull+RSI<30 LONG', hr, 3)
    if r_eng_eu and r_eng_eu['n'] >= 5:
        all_best_findings.append((f"EURUSD_H1_EngulfBull_RSI<30", r_eng_eu['wr'], r_eng_eu['n'], r_eng_eu['hold'], r_eng_eu['avg']))

# ═══════════════════════════════════════════════════════════════
# round40_004: US500 M5 EU CB>=4+RSI<14 月度跟踪续跑(第2月)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🇺🇸 04 — US500 M5 EU CB>=4+RSI<14 月度跟踪续跑 (round40_004) 第2月")
print(f"{'='*120}")

for sym in ['US500', 'US30']:
    for tf_name, data_store in [("M5", m5_data), ("M1", m1_data)]:
        if sym not in data_store:
            continue
        df = data_store[sym]
        hr_short = list(range(5, 61, 5))

        print(f"\n  --- {sym} {tf_name} EU 做多验证 ---")
        for cb, rsi in [(4,14), (3,10), (3,14), (4,18), (3,18), (5,14), (2,10)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi) & (df['session']=='europe')
            r = test_pattern(df, cond, f'LONG {sym} {tf_name} EU CB>={cb}+RSI<{rsi}', hr_short, 5)
            if r and r['n'] >= 15:
                best_h = r['hold']
                ow, lo, hi, nb = bootstrap_ci(df, cond, best_h)
                print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
                periods = cross_period_validation(df, cond, best_h, 3)
                cp_ok = sum(1 for p in periods if p['wr']>=60)
                print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
                for p in periods:
                    m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                    print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
                all_best_findings.append((f"LONG_{sym}_{tf_name}_EU_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

                # US500 M5 EU 月度跟踪续跑(第2月)
                if sym == 'US500' and tf_name == 'M5' and cb == 4 and rsi == 14:
                    monthly_tracking(df, cond, best_h,
                                     f'US500 M5 EU CB>=4+RSI<14 hold={best_h} 月度跟踪(第2月续跑)')

        # US 做多探索
        print(f"\n  --- {sym} {tf_name} US 做多验证 ---")
        for cb, rsi in [(2,14), (3,14), (2,18), (3,18), (2,10), (4,14)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi) & (df['session']=='us')
            r = test_pattern(df, cond, f'LONG {sym} {tf_name} US CB>={cb}+RSI<{rsi}', hr_short, 5)
            if r and r['n'] >= 10 and r['wr'] >= 65:
                best_h = r['hold']
                ow, lo, hi, nb = bootstrap_ci(df, cond, best_h)
                print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
                periods = cross_period_validation(df, cond, best_h, 3)
                cp_ok = sum(1 for p in periods if p['wr']>=60)
                print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
                all_best_findings.append((f"LONG_{sym}_{tf_name}_US_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # US30 M1 EU 时段子策略重验证(H8/H9/H10)
    if sym == 'US30' and 'US30' in m1_data:
        us30m1 = m1_data["US30"]
        hr_m1 = list(range(5, 61, 5))
        
        print(f"\n  --- US30 M1 EU 时段子策略重验证 (H8/H9/H10) ---")
        for hour_slot in [8, 9, 10, 11]:
            cond = (us30m1['consecutive_bear']>=4) & (us30m1['rsi14']<14) & (us30m1['hour']==hour_slot)
            r = test_pattern(us30m1, cond, f'US30 M1 EU hour={hour_slot} CB>=4+RSI<14', hr_m1, 3)
            if r and r['n'] >= 5 and r['wr'] >= 70:
                all_best_findings.append((f"US30_M1_EU_H{hour_slot}_CB>=4_RSI<14", r['wr'], r['n'], r['hold'], r['avg']))
        
        # CB>=3+RSI<14 替代方案确认
        print(f"\n  --- US30 M1 EU CB>=3+RSI<14 替代方案确认 (跨周期完整) ---")
        cond_alt = (us30m1['consecutive_bear']>=3) & (us30m1['rsi14']<14) & (us30m1['session']=='europe')
        r_alt = test_pattern(us30m1, cond_alt, 'US30 M1 EU CB>=3+RSI<14 (替代方案)', hr_m1, 10)
        if r_alt and r_alt['n'] >= 15:
            best_h = r_alt['hold']
            ow, lo, hi, nb = bootstrap_ci(us30m1, cond_alt, best_h)
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(us30m1, cond_alt, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
            for p in periods:
                m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
            all_best_findings.append((f"US30_M1_EU_ALT_CB>=3_RSI<14", r_alt['wr'], r_alt['n'], best_h, r_alt['avg']))

# ═══════════════════════════════════════════════════════════════
# round40_005: XAGUSD M30 SHORT CBull>=4+RSI>85+us WR=100% n=10 → 积累验证(n→20)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥈 05 — XAGUSD M30 SHORT 积累验证 (round40_005) US子策略n→20")
print(f"{'='*120}")

if "XAGUSD" in m30_data:
    xag = m30_data["XAGUSD"]
    hr30 = list(range(15, 151, 5))

    # 核心策略：CBull>=4+RSI>85
    print(f"\n  --- A: XAGUSD M30 SHORT CBull>=4+RSI>85 (核心, n跟踪) ---")
    cond_core85 = (xag['consecutive_bull']>=4) & (xag['rsi14']>85)
    r_core85 = test_pattern(xag, cond_core85, 'XAGUSD M30 SHORT CBull>=4+RSI>85', hr30, 5, 'short')
    if r_core85 and r_core85['n'] >= 10:
        best_h = r_core85['hold']
        ow, lo, hi, nb = bootstrap_ci(xag, cond_core85, best_h, direction='short')
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xag, cond_core85, best_h, 3, 'short')
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>=4_RSI>85", r_core85['wr'], r_core85['n'], best_h, r_core85['avg']))

    # US时段子策略（重点：CBull>=4+RSI>85+us n→20）
    print(f"\n  --- B: XAGUSD M30 SHORT US时段子策略 (核心积累目标 n→20) ---")
    cond_us = (xag['consecutive_bull']>=4) & (xag['rsi14']>85) & (xag['session']=='us')
    r_us = test_pattern(xag, cond_us, 'XAGUSD M30 SHORT CBull>=4+RSI>85+us', hr30, 3, 'short')
    if r_us and r_us['n'] >= 5:
        best_h = r_us['hold']
        ow, lo, hi, nb = bootstrap_ci(xag, cond_us, best_h, direction='short')
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xag, cond_us, best_h, 3, 'short')
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        all_best_findings.append((f"XAGUSD_M30_SHORT_US_CBull>=4_RSI>85", r_us['wr'], r_us['n'], best_h, r_us['avg']))

    # 放宽阈值探索
    print(f"\n  --- C: 放宽阈值探索 ---")
    for cb, rsi in [(3,80), (5,80), (3,75), (4,90), (5,85), (4,80), (3,85)]:
        cond = (xag['consecutive_bull']>=cb) & (xag['rsi14']>rsi)
        r = test_pattern(xag, cond, f'XAGUSD M30 SHORT CBull>={cb}+RSI>{rsi}', hr30, 5, 'short')
        if r and r['n'] >= 10 and r['wr'] >= 65:
            best_h = r['hold']
            ow, lo, hi, nb = bootstrap_ci(xag, cond, best_h, direction='short')
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(xag, cond, best_h, 3, 'short')
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
            all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # XAGUSD H1 SHORT探索
    if "XAGUSD" in h1_data:
        xagh1 = h1_data["XAGUSD"]
        hr_h1 = list(range(10, 121, 5))
        print(f"\n  --- D: XAGUSD H1 SHORT 探索 ---")
        for cb, rsi in [(3,75), (4,80), (3,80), (4,75), (5,80)]:
            cond = (xagh1['consecutive_bull']>=cb) & (xagh1['rsi14']>rsi)
            r = test_pattern(xagh1, cond, f'XAGUSD H1 SHORT CBull>={cb}+RSI>{rsi}', hr_h1, 3, 'short')
            if r and r['n'] >= 5 and r['wr'] >= 70:
                all_best_findings.append((f"XAGUSD_H1_SHORT_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# round40_006: US30 M1 EU 时段子策略(H8/H9/H10)重验证 (已在round40_004中包含)
# ═══════════════════════════════════════════════════════════════
# 已在 round40_004 的 US30 部分中完成

# ═══════════════════════════════════════════════════════════════
# round40_007: JP225 H1/M30做多月度跟踪(第4月)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 06 — JP225 H1/M30 做多月度跟踪 (round40_007) 第4月")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "JP225" not in data_store:
        continue
    jp = data_store["JP225"]
    hr = list(range(10, 151, 5))

    print(f"\n  --- {tf_name} JP225 CB+RSI 做多验证+月度跟踪 ---")
    for cb, rsi in [(4, 20), (4, 25), (3, 20), (5, 25), (5, 20), (3, 25)]:
        cond = (jp['consecutive_bear']>=cb) & (jp['rsi14']<rsi)
        r = test_pattern(jp, cond, f'JP225 {tf_name} LONG CB>={cb}+RSI<{rsi}', hr, 5)
        if r and r['n'] >= 10:
            best_h = r['hold']
            ow, lo, hi, nb = bootstrap_ci(jp, cond, best_h)
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(jp, cond, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
            for p in periods:
                m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
            all_best_findings.append((f"JP225_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # JP225 月度跟踪
    if tf_name == "H1":
        cond_track_jp = (jp['consecutive_bear']>=4) & (jp['rsi14']<25)
        monthly_tracking(jp, cond_track_jp, 40,
                         f'JP225 H1 CB>=4+RSI<25 hold=40 月度跟踪(第4月)')
    elif tf_name == "M30":
        cond_track_jp30 = (jp['consecutive_bear']>=4) & (jp['rsi14']<20)
        monthly_tracking(jp, cond_track_jp30, 135,
                         f'JP225 M30 CB>=4+RSI<20 hold=135 月度跟踪(第4月)')

    # JP225 形态探索
    if tf_name == "M30":
        print(f"\n  --- JP225 M30 形态+RSI 探索 ---")
        inside = detect_inside_bar(jp)
        cond_in = inside & (jp['rsi14']<25)
        r_in_jp = test_pattern(jp, cond_in, f'JP225 M30 InsideBar+RSI<25 LONG', hr, 3)
        if r_in_jp and r_in_jp['n'] >= 5:
            all_best_findings.append((f"JP225_M30_InsideBar_RSI<25", r_in_jp['wr'], r_in_jp['n'], r_in_jp['hold'], r_in_jp['avg']))

# ═══════════════════════════════════════════════════════════════
# round40_008: XAUUSD M1 EU极值月度跟踪续跑+US极值月度跟踪(第2月)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥇 07 — XAUUSD M1 双极值月度跟踪 (round40_008)")
print(f"{'='*120}")

if "XAUUSD" in m1_data:
    xu = m1_data["XAUUSD"]
    hr = list(range(10, 121, 5))

    # EU极值(已纳入): CB>=3+RSI<10 月度跟踪续跑
    print(f"\n  --- EU极值: XAUUSD M1 EU CB>=3+RSI<10 (WR=97.2% n=36 hold=55) ---")
    cond_eu = (xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session']=='europe')
    r_eu = test_pattern(xu, cond_eu, 'XAUUSD M1 EU CB>=3+RSI<10', hr, 5)
    if r_eu and r_eu['n'] >= 5:
        best_h = r_eu['hold']
        ow, lo, hi, nb = bootstrap_ci(xu, cond_eu, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xu, cond_eu, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        all_best_findings.append((f"XAUUSD_M1_EU_CB>=3_RSI<10", r_eu['wr'], r_eu['n'], best_h, r_eu['avg']))

        # EU极值月度跟踪
        monthly_tracking(xu, cond_eu, best_h,
                         f'XAUUSD M1 EU CB>=3+RSI<10 hold={best_h} 月度跟踪续跑')

    # XAUUSD M1 CB>=2+RSI<10+asia 亚盘探索
    print(f"\n  --- XAUUSD M1 ASIA CB+RSI探索 ---")
    for cb, rsi in [(2,10), (3,10), (2,14), (3,14), (4,14)]:
        cond_asia = (xu['consecutive_bear']>=cb) & (xu['rsi14']<rsi) & (xu['session']=='asia')
        r_asia = test_pattern(xu, cond_asia, f'XAUUSD M1 ASIA CB>={cb}+RSI<{rsi}', hr, 3)
        if r_asia and r_asia['n'] >= 5 and r_asia['wr'] >= 65:
            all_best_findings.append((f"XAUUSD_M1_ASIA_CB>={cb}_RSI<{rsi}", r_asia['wr'], r_asia['n'], r_asia['hold'], r_asia['avg']))

# ═══════════════════════════════════════════════════════════════
# round40_009: UKOIL M30做多n=32数据覆盖深度检查
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🛢️  08 — UKOIL M30 做多数据覆盖深度检查 (round40_009)")
print(f"{'='*120}")

for sym in ['UKOIL', 'USOIL']:
    if sym not in m30_data:
        print(f"  {sym}: 无数据")
        continue
    oil = m30_data[sym]
    hr = list(range(20, 181, 10))

    print(f"\n  --- {sym} M30 CB+RSI 做多积累 ---")
    for cb, rsi in [(4,25), (4,20), (3,25), (3,20), (5,25), (5,20), (2,20)]:
        cond = (oil['consecutive_bear']>=cb) & (oil['rsi14']<rsi)
        r = test_pattern(oil, cond, f'{sym} M30 LONG CB>={cb}+RSI<{rsi}', hr, 5)
        if r and r['n'] >= 10:
            best_h = r['hold']
            ow, lo, hi, nb = bootstrap_ci(oil, cond, best_h)
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(oil, cond, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
            for p in periods:
                m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
            all_best_findings.append((f"{sym}_M30_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # 数据覆盖检查
    print(f"\n  --- {sym} 数据覆盖检查 ---")
    print(f"  总行数 ({sym} M30): {len(oil)}")
    print(f"  日期范围: {oil.index[0]} → {oil.index[-1]}")
    print(f"  最新价格: {oil['close'].iloc[-1]:.2f}")
    print(f"  最新RSI: {oil['rsi14'].iloc[-1]:.1f}")

    # UKOIL M5 扩展检查
    if sym == 'UKOIL' and sym in m5_data:
        oil5 = m5_data[sym]
        hr5_oil = list(range(10, 121, 5))
        inside5 = detect_inside_bar(oil5)
        print(f"\n  --- {sym} M5 扩展检查 (信号稀有度高尝试) ---")
        print(f"  M5数据行数: {len(oil5)}")
        for cb, rsi in [(4,20), (4,25), (5,20), (5,25), (3,20)]:
            cond = (oil5['consecutive_bear']>=cb) & (oil5['rsi14']<rsi)
            r = test_pattern(oil5, cond, f'{sym} M5 LONG CB>={cb}+RSI<{rsi}', hr5_oil, 3)
            if r and r['n'] >= 5 and r['wr'] >= 65:
                best_h = r['hold']
                periods = cross_period_validation(oil5, cond, best_h, 3)
                cp_ok = sum(1 for p in periods if p['wr']>=60)
                print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
                all_best_findings.append((f"{sym}_M5_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

        # InsideBar
        cond_inside5 = inside5 & (oil5['rsi14']<20)
        r_in5 = test_pattern(oil5, cond_inside5, f'{sym} M5 InsideBar+RSI<20', hr5_oil, 3)
        if r_in5 and r_in5['n'] >= 5:
            all_best_findings.append((f"{sym}_M5_InsideBar_RSI<20", r_in5['wr'], r_in5['n'], r_in5['hold'], r_in5['avg']))

    # InsideBar + RSI (M30)
    inside30 = detect_inside_bar(oil)
    cond_inside30 = inside30 & (oil['rsi14']<20)
    r_in30 = test_pattern(oil, cond_inside30, f'{sym} M30 InsideBar+RSI<20 LONG', hr, 3)
    if r_in30 and r_in30['n'] >= 5:
        all_best_findings.append((f"{sym}_M30_InsideBar_RSI<20", r_in30['wr'], r_in30['n'], r_in30['hold'], r_in30['avg']))

# ═══════════════════════════════════════════════════════════════
# NEW: 10 — GBPUSD H1/M30 做多策略探索
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🇬🇧 09 — GBPUSD H1/M30 做多策略探索 (新增)")
print(f"{'='*120}")

for sym in ['GBPUSD', 'AUDUSD', 'USDCHF']:
    for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
        if sym not in data_store:
            continue
        gbp = data_store[sym]
        hr = list(range(10, 121, 5))

        print(f"\n  --- {sym} {tf_name} CB+RSI 做多探索 ---")
        for cb, rsi in [(3,20), (3,25), (4,20), (4,25), (2,18), (5,25), (3,18)]:
            cond = (gbp['consecutive_bear']>=cb) & (gbp['rsi14']<rsi)
            r = test_pattern(gbp, cond, f'{sym} {tf_name} LONG CB>={cb}+RSI<{rsi}', hr, 5)
            if r and r['n'] >= 10 and r['wr'] >= 65:
                best_h = r['hold']
                ow, lo, hi, nb = bootstrap_ci(gbp, cond, best_h)
                print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
                periods = cross_period_validation(gbp, cond, best_h, 3)
                cp_ok = sum(1 for p in periods if p['wr']>=60)
                print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
                for p in periods:
                    m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                    print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
                all_best_findings.append((f"{sym}_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

        # GBPUSD 时段探索
        if sym == 'GBPUSD' and 'session' in gbp.columns:
            print(f"\n  --- {sym} {tf_name} EU/US 时段探索 ---")
            for session_name in ['europe', 'us']:
                for cb, rsi in [(3,20), (3,25), (4,20)]:
                    cond_s = (gbp['consecutive_bear']>=cb) & (gbp['rsi14']<rsi) & (gbp['session']==session_name)
                    r_s = test_pattern(gbp, cond_s, f'{sym} {tf_name} {session_name} CB>={cb}+RSI<{rsi}', hr, 5)
                    if r_s and r_s['n'] >= 5 and r_s['wr'] >= 65:
                        all_best_findings.append((f"{sym}_{tf_name}_{session_name.upper()}_CB>={cb}_RSI<{rsi}", r_s['wr'], r_s['n'], r_s['hold'], r_s['avg']))

# ═══════════════════════════════════════════════════════════════
# NEW: 11 — HK50 H1/M30 做多策略探索
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🇭🇰 10 — HK50 H1/M30 做多策略探索 (新增)")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "HK50" not in data_store:
        continue
    hk = data_store["HK50"]
    hr = list(range(10, 121, 5))

    print(f"\n  --- HK50 {tf_name} CB+RSI 做多探索 ---")
    for cb, rsi in [(3,20), (4,20), (3,25), (4,25), (5,25), (2,18), (3,18)]:
        cond = (hk['consecutive_bear']>=cb) & (hk['rsi14']<rsi)
        r = test_pattern(hk, cond, f'HK50 {tf_name} LONG CB>={cb}+RSI<{rsi}', hr, 5)
        if r and r['n'] >= 10 and r['wr'] >= 65:
            best_h = r['hold']
            ow, lo, hi, nb = bootstrap_ci(hk, cond, best_h)
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(hk, cond, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
            all_best_findings.append((f"HK50_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # HK50 亚盘时段探索
    print(f"\n  --- HK50 {tf_name} ASIA 时段探索 ---")
    cond_asia = (hk['consecutive_bear']>=3) & (hk['rsi14']<25) & (hk['session']=='asia')
    r_hk_asia = test_pattern(hk, cond_asia, f'HK50 {tf_name} ASIA CB>=3+RSI<25', hr, 5)
    if r_hk_asia and r_hk_asia['n'] >= 5 and r_hk_asia['wr'] >= 65:
        all_best_findings.append((f"HK50_{tf_name}_ASIA_CB>=3_RSI<25", r_hk_asia['wr'], r_hk_asia['n'], r_hk_asia['hold'], r_hk_asia['avg']))

# ═══════════════════════════════════════════════════════════════
# NEW: 12 — USTEC M30/H1 做多探索
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📈 11 — USTEC M30/H1 做多策略探索 (新增)")
print(f"{'='*120}")

for sym in ['USTEC']:
    for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
        if sym not in data_store:
            continue
        tec = data_store[sym]
        hr = list(range(10, 121, 5))

        print(f"\n  --- {sym} {tf_name} CB+RSI 做多探索 ---")
        for cb, rsi in [(3,20), (4,20), (3,25), (4,25), (5,25), (4,18), (3,18)]:
            cond = (tec['consecutive_bear']>=cb) & (tec['rsi14']<rsi)
            r = test_pattern(tec, cond, f'{sym} {tf_name} LONG CB>={cb}+RSI<{rsi}', hr, 5)
            if r and r['n'] >= 10 and r['wr'] >= 65:
                best_h = r['hold']
                ow, lo, hi, nb = bootstrap_ci(tec, cond, best_h)
                print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
                periods = cross_period_validation(tec, cond, best_h, 3)
                cp_ok = sum(1 for p in periods if p['wr']>=60)
                print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
                for p in periods:
                    m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                    print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
                all_best_findings.append((f"{sym}_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

        # 时段探索
        print(f"\n  --- {sym} {tf_name} EU/US 时段探索 ---")
        for session_name in ['europe', 'us']:
            for cb, rsi in [(3,20), (4,20), (3,25)]:
                cond_s = (tec['consecutive_bear']>=cb) & (tec['rsi14']<rsi) & (tec['session']==session_name)
                r_s = test_pattern(tec, cond_s, f'{sym} {tf_name} {session_name} CB>={cb}+RSI<{rsi}', hr, 5)
                if r_s and r_s['n'] >= 5 and r_s['wr'] >= 65:
                    all_best_findings.append((f"{sym}_{tf_name}_{session_name.upper()}_CB>={cb}_RSI<{rsi}", r_s['wr'], r_s['n'], r_s['hold'], r_s['avg']))

# ═══════════════════════════════════════════════════════════════
# NEW: 13 — XAUUSD M5 美盘做空探索
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥇 12 — XAUUSD M5 美盘做空探索 (新增)")
print(f"{'='*120}")

if "XAUUSD" in m5_data:
    xu5 = m5_data["XAUUSD"]
    hr5 = list(range(5, 61, 5))

    print(f"\n  --- XAUUSD M5 US 做空 (CBull+RSI高) ---")
    for cb, rsi in [(3, 75), (4, 80), (3, 80), (4, 75), (2, 75), (5, 80)]:
        cond = (xu5['consecutive_bull']>=cb) & (xu5['rsi14']>rsi) & (xu5['session']=='us')
        r = test_pattern(xu5, cond, f'XAUUSD M5 US SHORT CBull>={cb}+RSI>{rsi}', hr5, 5, 'short')
        if r and r['n'] >= 10 and r['wr'] >= 65:
            best_h = r['hold']
            ow, lo, hi, nb = bootstrap_ci(xu5, cond, best_h, direction='short')
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(xu5, cond, best_h, 3, 'short')
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
            all_best_findings.append((f"XAUUSD_M5_US_SHORT_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # XAUUSD M5 形态做空
    print(f"\n  --- XAUUSD M5 Doji+RSI>75 做空 ---")
    doji = detect_doji(xu5)
    shooting = detect_shooting_star(xu5)
    for cond_name, cond in [('Doji', doji), ('ShootingStar', shooting)]:
        cond_short = cond & (xu5['rsi14']>75) & (xu5['session']=='us')
        r_d = test_pattern(xu5, cond_short, f'XAUUSD M5 US {cond_name}+RSI>75 SHORT', hr5, 3, 'short')
        if r_d and r_d['n'] >= 5 and r_d['wr'] >= 65:
            all_best_findings.append((f"XAUUSD_M5_US_{cond_name}_RSI>75", r_d['wr'], r_d['n'], r_d['hold'], r_d['avg']))

# ═══════════════════════════════════════════════════════════════
# XAUUSD M5 双枪策略月度跟踪续跑
# ═══════════════════════════════════════════════════════════════
if "XAUUSD" in m5_data:
    xu5 = m5_data["XAUUSD"]
    print(f"\n{'='*120}")
    print("🔫 双枪策略月度跟踪 (XAUUSD M5) 续跑")
    print(f"{'='*120}")

    xu5['month'] = xu5.index.to_period('M')
    ceu5 = (xu5['session']=='europe') & (xu5['hour'].between(9,11)) & (xu5['rsi14']<18) & (xu5['consecutive_bear']>=4)
    cus5 = (xu5['session']=='us') & (xu5['hour'].between(15,16)) & (xu5['rsi14']<20) & (xu5['consecutive_bear']>=2)

    print(f"\n  欧盘: EU 9-11 RSI<18+CB>=4 hold=42")
    teu, weu, aeu = 0, 0.0, 0.0
    for month, grp in xu5.groupby('month'):
        cnt, wr, avg = get_stats(grp, ceu5.loc[grp.index], 42)
        if cnt > 0:
            marker = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}% {marker}")
            teu += cnt; weu += cnt*wr; aeu += cnt*avg
    if teu > 0:
        print(f"  → 总计: n={teu} WR={weu/teu:.1f}% avg={aeu/teu:.3f}%")

    print(f"\n  美盘: US 15-16 RSI<20+CB>=2 hold=115")
    tus, wus, aus = 0, 0.0, 0.0
    for month, grp in xu5.groupby('month'):
        cnt, wr, avg = get_stats(grp, cus5.loc[grp.index], 115)
        if cnt > 0:
            marker = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}% {marker}")
            tus += cnt; wus += cnt*wr; aus += cnt*avg
    if tus > 0:
        print(f"  → 总计: n={tus} WR={wus/tus:.1f}% avg={aus/tus:.3f}%")
    print(f"  → 双枪组合: n={teu+tus} WR={(weu+wus)/(teu+tus):.1f}%")

# ═══════════════════════════════════════════════════════════════
# SUMMARY: Top Findings
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 ROUND 40 — 最佳发现排名")
print(f"{'='*120}")

seen = set()
unique_findings = []
for item in all_best_findings:
    key = item[0]
    if key not in seen:
        seen.add(key)
        unique_findings.append(item)

sorted_findings = sorted(unique_findings, key=lambda x: (x[1], x[2]), reverse=True)
print(f"\n{'排名':<5} {'策略':<50} {'WR':>6} {'n':>5} {'Hold':>5} {'avg%':>8}")
print("-" * 80)
for i, (name, wr, n, hold, avg) in enumerate(sorted_findings[:40], 1):
    print(f"{i:<5} {name:<50} {wr:>5.1f}% {n:>5} {hold:>5} {avg:>7.3f}%")

# ═══════════════════════════════════════════════════════════════
# SAVE OUTPUT (capture all output to file)
# ═══════════════════════════════════════════════════════════════
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'round40_output.txt')
f_out = open(output_path, 'w', encoding='utf-8')
print(f"\n\n{'='*120}", file=f_out)
print(f"ROUND 40 COMPLETE — {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC", file=f_out)
print(f"{'='*120}", file=f_out)
print(f"Total patterns tested: {len(all_best_findings)}", file=f_out)
print(f"Unique findings: {len(sorted_findings)}", file=f_out)

# Also save the ranked findings to file
print(f"\n\nTop Findings Ranking:", file=f_out)
print(f"{'Rank':<5} {'Strategy':<50} {'WR':>6} {'n':>5} {'Hold':>5} {'avg%':>8}", file=f_out)
print("-" * 80, file=f_out)
for i, (name, wr, n, hold, avg) in enumerate(sorted_findings[:60], 1):
    print(f"{i:<5} {name:<50} {wr:>5.1f}% {n:>5} {hold:>5} {avg:>7.3f}%", file=f_out)

f_out.close()
print(f"\n✅ 输出已保存到: {output_path}")
