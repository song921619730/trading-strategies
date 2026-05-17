#!/usr/bin/env python3
"""
Round 39 — XAUUSD M1 US极值正式纳入+月度跟踪启动 + 各策略续跑
目标(state next_actions):
  1. XAUUSD M1 US CB>=3+RSI<10 WR=87.0% n=46 → 正式纳入best_known+月度跟踪启动
  2. XAGUSD M5 EU CB>=3+RSI<10 n=42→目标60持续监控
  3. UKOIL M30做多 n=32→50继续积累(检查UKOIL M30数据覆盖能否扩展)
  4. EURUSD H1做多月度跟踪(第7月)
  5. US500 M5 EU CB>=4+RSI<14 月度跟踪启动(新确认)
  6. XAGUSD M30 SHORT CBull>=4+RSI>85 WR=93.8% n=16 → 积累验证(n→30)
  7. US30 M1 EU 时段子策略验证(hour=8/9 WR=100%)
  8. JP225 H1/M30做多月度跟踪(第3月)
  9. XAUUSD M1 US+EU双极值策略监控(EU极值已纳入+US极值新纳入)
时间框架: M1, M5, M30, H1
品种: 多品种 (含XAUUSD, XAGUSD, JP225, US500, US30, UKOIL, EURUSD等)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_data, compute_indicators
import pandas as pd
import numpy as np
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ═══════════════════════════════════════════════════════════════
# HELPERS (same as Round 38)
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

# ============================================================
# MAIN
# ============================================================

results = {}
all_best_findings = []

print("=" * 120)
print("ROUND 39 — XAUUSD M1 US极值正式纳入+月度跟踪启动 + 各策略续跑")
print(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print("品种: 期货外汇14品种 (XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, US30, US500, USTEC, JP225, HK50, UKOIL, USOIL)")
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
# round39_001: XAUUSD M1 US CB>=3+RSI<10 正式纳入best_known+月度跟踪启动
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏅 01 — XAUUSD M1 US CB>=3+RSI<10 正式纳入+月度跟踪启动 (round39_001)")
print(f"{'='*120}")

if "XAUUSD" in m1_data:
    xu = m1_data["XAUUSD"]
    hr = list(range(10, 121, 5))

    # 核心策略：XAUUSD M1 US CB>=3+RSI<10
    print(f"\n  --- A: XAUUSD M1 US CB>=3+RSI<10 (核心, n=46→正式纳入+月度跟踪) ---")
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

        # 月度跟踪启动
        monthly_tracking(xu, cond_us_strong, best_h,
                         f'XAUUSD M1 US CB>=3+RSI<10 hold={best_h} 月度跟踪(第1月启动)')

    # 补充: XAUUSD M1 US CB>=2+RSI<10 (极值基础版, 持续监控)
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

    # XAUUSD M1 EU 极值策略 月度跟踪
    print(f"\n  --- C: XAUUSD M1 EU CB>=3+RSI<10 (极值, 月度跟踪) ---")
    cond_eu_extreme = (xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session']=='europe')
    r_eu_extreme = test_pattern(xu, cond_eu_extreme, 'XAUUSD M1 EU CB>=3+RSI<10', hr, 5)
    if r_eu_extreme and r_eu_extreme['n'] >= 10:
        best_h = r_eu_extreme['hold']
        monthly_tracking(xu, cond_eu_extreme, best_h,
                         f'XAUUSD M1 EU CB>=3+RSI<10 hold={best_h} 月度跟踪')

    # XAUUSD M1 US+EU 双极值组合统计
    print(f"\n  --- D: XAUUSD M1 双极值组合统计 (EU+US) ---")
    cond_dual = ((xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session'].isin(['europe','us'])))
    r_dual = test_pattern(xu, cond_dual, 'XAUUSD M1 US/EU Dual CB>=3+RSI<10', hr, 10)
    if r_dual and r_dual['n'] >= 10:
        all_best_findings.append((f"XAUUSD_M1_DUAL_CB>=3_RSI<10", r_dual['wr'], r_dual['n'], r_dual['hold'], r_dual['avg']))

# ═══════════════════════════════════════════════════════════════
# round39_002: XAGUSD M5 EU CB>=3+RSI<10 n=42→目标60持续监控
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥈 02 — XAGUSD M5 EU 做多积累监控 (round39_002) n=42→目标60")
print(f"{'='*120}")

if "XAGUSD" in m5_data:
    xag5 = m5_data["XAGUSD"]
    hr5 = list(range(5, 61, 5))

    print(f"\n  --- A: XAGUSD M5 EU CB>=3+RSI<10 (n跟踪, 目标60) ---")
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

    print(f"\n  --- B: XAGUSD M5 EU 其他阈值扫描 ---")
    for cb, rsi in [(4,14), (4,18), (3,14), (4,10), (5,18)]:
        cond = (xag5['consecutive_bear']>=cb) & (xag5['rsi14']<rsi) & (xag5['session']=='europe')
        r = test_pattern(xag5, cond, f'XAGUSD M5 EU CB>={cb}+RSI<{rsi}', hr5, 5)
        if r and r['n'] >= 10 and r['wr'] >= 65:
            best_h = r['hold']
            periods = cross_period_validation(xag5, cond, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
            all_best_findings.append((f"XAGUSD_M5_EU_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

# ═══════════════════════════════════════════════════════════════
# round39_003: UKOIL M30做多 n=32→50继续积累
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🛢️  03 — UKOIL M30 做多积累 (round39_003) n=32→目标50")
print(f"{'='*120}")

for sym in ['UKOIL', 'USOIL']:
    if sym not in m30_data:
        print(f"  {sym}: 无数据")
        continue
    oil = m30_data[sym]
    hr = list(range(20, 181, 10))

    print(f"\n  --- {sym} M30 CB+RSI 做多积累 ---")
    for cb, rsi in [(4,25), (4,20), (3,25), (3,20), (5,25)]:
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

    # 检查数据覆盖范围(UKOIL特别关注)
    print(f"\n  --- {sym} M30 数据覆盖检查 ---")
    print(f"  总行数: {len(oil)}")
    print(f"  日期范围: {oil.index[0]} → {oil.index[-1]}")
    print(f"  最新价格: {oil['close'].iloc[-1]:.2f}")
    print(f"  最新RSI: {oil['rsi14'].iloc[-1]:.1f}")

    # InsideBar + RSI
    print(f"\n  --- {sym} M30 InsideBar+RSI<20 ---")
    inside = detect_inside_bar(oil)
    cond_inside = inside & (oil['rsi14']<20)
    r_in = test_pattern(oil, cond_inside, f'{sym} M30 InsideBar+RSI<20', hr, 3)
    if r_in and r_in['n'] >= 5:
        all_best_findings.append((f"{sym}_M30_InsideBar_RSI<20", r_in['wr'], r_in['n'], r_in['hold'], r_in['avg']))

# ═══════════════════════════════════════════════════════════════
# round39_004: EURUSD H1做多月度跟踪(第7月)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("💰 04 — EURUSD H1 做多月度跟踪 (round39_004) 第7月")
print(f"{'='*120}")

if "EURUSD" in h1_data:
    eu = h1_data["EURUSD"]
    hr = list(range(10, 121, 5))

    print(f"\n  --- EURUSD H1 CB+RSI 做多验证 ---")
    for cb, rsi in [(3,20), (3,25), (4,20), (4,25)]:
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

    # 月度跟踪 CB>=3+RSI<25
    cond_track = (eu['consecutive_bear']>=3) & (eu['rsi14']<25)
    r_track = test_pattern(eu, cond_track, 'EURUSD H1 CB>=3+RSI<25 (最优hold)', hr, 5)
    if r_track and r_track['n'] >= 10:
        monthly_tracking(eu, cond_track, r_track['hold'],
                         f'EURUSD H1 CB>=3+RSI<25 hold={r_track["hold"]} 月度跟踪(第7月)')

    # EURUSD M30 验证
    if "EURUSD" in m30_data:
        eum30 = m30_data["EURUSD"]
        hr30_m = list(range(10, 121, 5))
        print(f"\n  --- EURUSD M30 CB+RSI 做多验证 ---")
        for cb, rsi in [(3,20), (3,25), (4,20)]:
            cond = (eum30['consecutive_bear']>=cb) & (eum30['rsi14']<rsi)
            r = test_pattern(eum30, cond, f'EURUSD M30 LONG CB>={cb}+RSI<{rsi}', hr30_m, 5)
            if r and r['n'] >= 10:
                all_best_findings.append((f"EURUSD_M30_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# round39_005: US500 M5 EU CB>=4+RSI<14 月度跟踪启动(新确认)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🇺🇸 05 — US500 M5 EU CB>=4+RSI<14 月度跟踪启动 (round39_005)")
print(f"{'='*120}")

for sym in ['US500', 'US30']:
    for tf_name, data_store in [("M5", m5_data), ("M1", m1_data)]:
        if sym not in data_store:
            continue
        df = data_store[sym]
        hr_short = list(range(5, 61, 5))

        print(f"\n  --- {sym} {tf_name} EU 做多验证 ---")
        for cb, rsi in [(4,14), (3,10), (3,14), (4,18), (3,18)]:
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

                # US500 M5 EU 月度跟踪
                if sym == 'US500' and tf_name == 'M5' and cb == 4 and rsi == 14:
                    monthly_tracking(df, cond, best_h,
                                     f'US500 M5 EU CB>=4+RSI<14 hold={best_h} 月度跟踪(第1月启动)')

        # US 做多探索
        print(f"\n  --- {sym} {tf_name} US 做多验证 ---")
        for cb, rsi in [(2,14), (3,14), (2,18), (3,18), (2,10)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi) & (df['session']=='us')
            r = test_pattern(df, cond, f'LONG {sym} {tf_name} US CB>={cb}+RSI<{rsi}', hr_short, 5)
            if r and r['n'] >= 10 and r['wr'] >= 65:
                all_best_findings.append((f"LONG_{sym}_{tf_name}_US_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# round39_006: XAGUSD M30 SHORT CBull>=4+RSI>85 n=16→积累验证(n→30)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥈 06 — XAGUSD M30 SHORT CBull>=4+RSI>85 积累验证 (round39_006) n=16→目标30")
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

    # 基础版：CBull>=4+RSI>80
    print(f"\n  --- B: XAGUSD M30 SHORT CBull>=4+RSI>80 (基础版) ---")
    cond_core80 = (xag['consecutive_bull']>=4) & (xag['rsi14']>80)
    r_core80 = test_pattern(xag, cond_core80, 'XAGUSD M30 SHORT CBull>=4+RSI>80', hr30, 5, 'short')
    if r_core80 and r_core80['n'] >= 10:
        best_h = r_core80['hold']
        ow, lo, hi, nb = bootstrap_ci(xag, cond_core80, best_h, direction='short')
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xag, cond_core80, best_h, 3, 'short')
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>=4_RSI>80", r_core80['wr'], r_core80['n'], best_h, r_core80['avg']))

    # 放宽阈值探索
    print(f"\n  --- C: 放宽阈值探索 ---")
    for cb, rsi in [(3,80), (5,80), (3,75), (4,90), (5,85)]:
        cond = (xag['consecutive_bull']>=cb) & (xag['rsi14']>rsi)
        r = test_pattern(xag, cond, f'XAGUSD M30 SHORT CBull>={cb}+RSI>{rsi}', hr30, 5, 'short')
        if r and r['n'] >= 10 and r['wr'] >= 65:
            all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

    # 时段优化
    print(f"\n  --- D: XAGUSD M30 SHORT 时段优化 ---")
    for session_name in ['europe', 'us', 'asia']:
        cond_s = (xag['consecutive_bull']>=4) & (xag['rsi14']>85) & (xag['session']==session_name)
        r_s = test_pattern(xag, cond_s, f'XAGUSD M30 SHORT CBull>=4+RSI>85+{session_name}', hr30, 3, 'short')
        if r_s and r_s['n'] >= 5 and r_s['wr'] >= 70:
            all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>=4_RSI>85_{session_name}", r_s['wr'], r_s['n'], r_s['hold'], r_s['avg']))

# ═══════════════════════════════════════════════════════════════
# round39_007: US30 M1 EU 时段子策略验证(hour=8/9 WR=100%)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🇺🇸 07 — US30 M1 EU 时段子策略验证 (round39_007) hour=8/9 WR=100%")
print(f"{'='*120}")

if "US30" in m1_data:
    us30m1 = m1_data["US30"]
    hr_m1 = list(range(5, 61, 5))

    print(f"\n  --- A: US30 M1 EU CB>=4+RSI<14 (核心, 跨周期重测) ---")
    cond_core30 = (us30m1['consecutive_bear']>=4) & (us30m1['rsi14']<14) & (us30m1['session']=='europe')
    r_core30 = test_pattern(us30m1, cond_core30, 'US30 M1 EU LONG CB>=4+RSI<14', hr_m1, 10)
    if r_core30 and r_core30['n'] >= 15:
        best_h = r_core30['hold']
        ow, lo, hi, nb = bootstrap_ci(us30m1, cond_core30, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(us30m1, cond_core30, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        all_best_findings.append((f"US30_M1_EU_LONG_CB>=4_RSI<14", r_core30['wr'], r_core30['n'], best_h, r_core30['avg']))

    print(f"\n  --- B: US30 M1 EU 时段子策略验证 (hour=8/9) ---")
    for hour_slot in [8, 9, 10, 11, 12]:
        cond = (us30m1['consecutive_bear']>=4) & (us30m1['rsi14']<14) & (us30m1['hour']==hour_slot)
        r = test_pattern(us30m1, cond, f'US30 M1 EU hour={hour_slot} CB>=4+RSI<14', hr_m1, 3)
        if r and r['n'] >= 5 and r['wr'] >= 70:
            all_best_findings.append((f"US30_M1_EU_H{hour_slot}_CB>=4_RSI<14", r['wr'], r['n'], r['hold'], r['avg']))

    print(f"\n  --- C: US30 M1 EU 其他阈值探索 ---")
    for cb, rsi in [(3,10), (3,14), (5,18), (4,18), (3,18)]:
        cond = (us30m1['consecutive_bear']>=cb) & (us30m1['rsi14']<rsi) & (us30m1['session']=='europe')
        r = test_pattern(us30m1, cond, f'US30 M1 EU CB>={cb}+RSI<{rsi}', hr_m1, 5)
        if r and r['n'] >= 10 and r['wr'] >= 65:
            all_best_findings.append((f"US30_M1_EU_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# round39_008: JP225 H1/M30做多月度跟踪(第3月)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 08 — JP225 H1/M30 做多月度跟踪 (round39_008) 第3月")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "JP225" not in data_store:
        continue
    jp = data_store["JP225"]
    hr = list(range(10, 151, 5))

    print(f"\n  --- {tf_name} JP225 CB+RSI 做多验证+月度跟踪 ---")
    if tf_name == "H1":
        for cb, rsi, best_hold in [(4, 20, 50), (4, 25, 40), (3, 20, 40), (5, 25, 40)]:
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
    else:  # M30
        for cb, rsi, best_hold in [(4, 20, 135), (3, 20, 135), (5, 25, 120), (4, 25, 120)]:
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
                         f'JP225 H1 CB>=4+RSI<25 hold=40 月度跟踪(第3月)')

# ═══════════════════════════════════════════════════════════════
# round39_009: XAUUSD M1 US+EU双极值策略监控
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥇 09 — XAUUSD M1 双极值综合监控 (round39_009) EU+US")
print(f"{'='*120}")

if "XAUUSD" in m1_data:
    xu = m1_data["XAUUSD"]
    hr = list(range(10, 121, 5))

    # EU极值(已纳入): CB>=3+RSI<10
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

    # 双极值信号频率统计
    print(f"\n  --- 双极值信号频率统计 ---")
    eu_count = cond_eu.sum()
    us_strong_count = ((xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session']=='us')).sum()
    us_base_count = ((xu['consecutive_bear']>=2) & (xu['rsi14']<10) & (xu['session']=='us')).sum()
    dual_count = ((xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session'].isin(['europe','us']))).sum()
    print(f"    EU 极值 (CB>=3+RSI<10):        {eu_count} 信号")
    print(f"    US 极值-强 (CB>=3+RSI<10):     {us_strong_count} 信号")
    print(f"    US 极值-基础 (CB>=2+RSI<10):   {us_base_count} 信号")
    print(f"    双极值联合 (EU+US强):           {dual_count} 信号")

# ═══════════════════════════════════════════════════════════════
# XAUUSD M5 双枪策略月度跟踪续跑
# ═══════════════════════════════════════════════════════════════
if "XAUUSD" in m5_data:
    xu5 = m5_data["XAUUSD"]
    print(f"\n{'='*120}")
    print("🔫 双枪策略月度跟踪 (XAUUSD M5) 续跑")
    print(f"{'='*120}")

    xu5['month'] = xu5.index.to_period('M')
    ceu = (xu5['session']=='europe') & (xu5['hour'].between(9,11)) & (xu5['rsi14']<18) & (xu5['consecutive_bear']>=4)
    cus = (xu5['session']=='us') & (xu5['hour'].between(15,16)) & (xu5['rsi14']<20) & (xu5['consecutive_bear']>=2)

    print(f"\n  欧盘: EU 9-11 RSI<18+CB>=4 hold=42")
    teu, weu, aeu = 0, 0.0, 0.0
    for month, grp in xu5.groupby('month'):
        cnt, wr, avg = get_stats(grp, ceu.loc[grp.index], 42)
        if cnt > 0:
            marker = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}% {marker}")
            teu += cnt; weu += cnt*wr; aeu += cnt*avg
    if teu > 0:
        print(f"  → 总计: n={teu} WR={weu/teu:.1f}% avg={aeu/teu:.3f}%")

    print(f"\n  美盘: US 15-16 RSI<20+CB>=2 hold=115")
    tus, wus, aus = 0, 0.0, 0.0
    for month, grp in xu5.groupby('month'):
        cnt, wr, avg = get_stats(grp, cus.loc[grp.index], 115)
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
print("🏆 ROUND 39 — 最佳发现排名")
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
for i, (name, wr, n, hold, avg) in enumerate(sorted_findings[:30], 1):
    print(f"{i:<5} {name:<50} {wr:>5.1f}% {n:>5} {hold:>5} {avg:>7.3f}%")

# ═══════════════════════════════════════════════════════════════
# SAVE OUTPUT
# ═══════════════════════════════════════════════════════════════
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'round39_output.txt')
import sys as _sys
class Tee:
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

f_out = open(output_path, 'w', encoding='utf-8')
_sys.stdout = Tee(_sys.stdout, f_out)

print(f"\n\n{'='*120}")
print(f"ROUND 39 COMPLETE — {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print(f"{'='*120}")
print(f"Total patterns tested: {len(all_best_findings)}")
print(f"Unique findings: {len(sorted_findings)}")
_sys.stdout = _sys.__stdout__
f_out.close()
print(f"\n✅ 输出已保存到: {output_path}")
