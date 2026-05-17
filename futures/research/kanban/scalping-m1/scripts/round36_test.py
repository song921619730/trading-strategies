#!/usr/bin/env python3
"""
Round 36 — H1/M30 策略积累验证 + M1/M5 超短线扫描
目标(state next_actions):
  1. EURUSD H1 CB>=3+RSI<20/25继续积累并开启月度跟踪
  2. XAGUSD M30 SHORT CBull>=4+RSI>80继续积累 n=28→目标50
  3. JP225 H1/M30 做多策略深度验证 — WR>95% 跨周期检查
  4. UKOIL/USOIL M30 做多策略验证 — WR>96% 需跨周期+Bootstrap确认
  5. US500/US30 H1 做多策略验证 — WR>94% 需跨周期确认
  6. XAUUSD M30 Doji+RSI>75+us做空 — WR=100% n=12 需更多数据
  7. M1/M5 目标品种快速扫描 (XAUUSD/XAGUSD/JP225/US500/US30)
  8. H1/M30 信号频率统计
时间框架: M1, M5, M30, H1
品种: 多品种 (含XAUUSD, XAGUSD, JP225, US500, US30等)
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

def detect_hammer(df, body_pct=0.3, lower_wig_pct=0.6):
    body = abs(df['close'] - df['open'])
    total = df['high'] - df['low']
    lower_shadow = df[['open', 'close']].min(axis=1) - df['low']
    upper_shadow = df['high'] - df[['open', 'close']].max(axis=1)
    return (body / total.replace(0, np.nan) < body_pct) & \
           (lower_shadow / total.replace(0, np.nan) > lower_wig_pct) & \
           (upper_shadow / total.replace(0, np.nan) < 0.1)

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

results = {}
all_best_findings = []

print("=" * 120)
print("ROUND 36 — H1/M30 策略积累验证 + M1/M5 超短线扫描")
print(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print("品种: 期货外汇14品种 + M1/M5目标5品种")
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
# 01: EURUSD H1 CB>=3+RSI<20/25 继续积累 + 月度跟踪
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 01 — EURUSD H1/M30 CB+RSI 积累与月度跟踪 (round36_001)")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "EURUSD" not in data_store:
        continue
    eu = data_store["EURUSD"]
    hr = list(range(10, 121, 5))

    print(f"\n  --- {tf_name} EURUSD CB+RSI 做多 ---")
    # 核心: CB>=3+RSI<20
    for cb, rsi in [(3,20), (3,25), (4,20), (4,25)]:
        cond = (eu['consecutive_bear']>=cb) & (eu['rsi14']<rsi)
        r = test_pattern(eu, cond, f'EURUSD {tf_name} LONG CB>={cb}+RSI<{rsi}', hr, 5)
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
            all_best_findings.append((f"EURUSD_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # CB>=3+RSI<25 月度跟踪
    if tf_name == "H1":
        cond_track = (eu['consecutive_bear']>=3) & (eu['rsi14']<25)
        r_track = test_pattern(eu, cond_track, f'EURUSD H1 CB>=3+RSI<25 (hold找最优)', hr, 5)
        if r_track and r_track['n'] >= 10:
            monthly_tracking(eu, cond_track, r_track['hold'], f'EURUSD H1 CB>=3+RSI<25 hold={r_track["hold"]} 月度')

# ═══════════════════════════════════════════════════════════════
# 02: XAGUSD M30 SHORT CBull>=4+RSI>80 积累 (round36_002)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 02 — XAGUSD M30 SHORT 积累 (round36_002) n=28→目标50")
print(f"{'='*120}")

if "XAGUSD" in m30_data:
    xag = m30_data["XAGUSD"]
    hr30 = list(range(15, 151, 5))

    print(f"\n  --- A: CBull>=4+RSI>80 (核心, n=28→目标50) ---")
    cond_core = (xag['consecutive_bull']>=4) & (xag['rsi14']>80)
    r_core = test_pattern(xag, cond_core, 'XAGUSD M30 SHORT CBull>=4+RSI>80', hr30, 10, 'short')
    if r_core and r_core['n'] >= 15:
        best_h = r_core['hold']
        ow, lo, hi, nb = bootstrap_ci(xag, cond_core, best_h, direction='short')
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xag, cond_core, best_h, 3, 'short')
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>=4_RSI>80", r_core['wr'], r_core['n'], best_h, r_core['avg']))

    print(f"\n  --- B: CBull>=5+RSI>80 (严格版, n=17) ---")
    cond_strict = (xag['consecutive_bull']>=5) & (xag['rsi14']>80)
    r_strict = test_pattern(xag, cond_strict, 'XAGUSD M30 SHORT CBull>=5+RSI>80', hr30, 5, 'short')
    if r_strict and r_strict['n'] >= 10:
        ow, lo, hi, nb = bootstrap_ci(xag, cond_strict, r_strict['hold'], direction='short')
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb})")
        all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>=5_RSI>80", r_strict['wr'], r_strict['n'], r_strict['hold'], r_strict['avg']))

    print(f"\n  --- C: 时段细化 (CBull>=4+RSI>80+us/europe) ---")
    for sess in ['us', 'europe']:
        cond = (xag['consecutive_bull']>=4) & (xag['rsi14']>80) & (xag['session']==sess)
        r = test_pattern(xag, cond, f'XAGUSD M30 SHORT CBull>=4+RSI>80+{sess}', hr30, 3, 'short')
        if r and r['n'] >= 5:
            all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>=4_RSI>80_{sess}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# 03: JP225 H1/M30 做多策略深度验证 (round36_003)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 03 — JP225 H1/M30 做多深度验证 (round36_003)")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "JP225" not in data_store:
        continue
    jp = data_store["JP225"]
    hr = list(range(10, 151, 5))

    print(f"\n  --- {tf_name} JP225 CB+RSI 做多 ---")
    for cb, rsi in [(5,25), (4,20), (4,25), (5,20), (3,20)]:
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

    # 时段细化
    print(f"\n  --- {tf_name} JP225 时段细化 ---")
    for sess in ['us', 'europe']:
        for cb, rsi in [(4,20), (5,25)]:
            cond = (jp['consecutive_bear']>=cb) & (jp['rsi14']<rsi) & (jp['session']==sess)
            r = test_pattern(jp, cond, f'JP225 {tf_name} CB>={cb}+RSI<{rsi}+{sess}', hr, 3)
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"JP225_{tf_name}_LONG_CB>={cb}_RSI<{rsi}_{sess}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# 04: UKOIL/USOIL M30 做多策略验证 (round36_004)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🛢️  04 — UKOIL/USOIL M30 做多验证 (round36_004)")
print(f"{'='*120}")

for sym in ['UKOIL', 'USOIL']:
    if sym not in m30_data:
        print(f"  {sym}: 无数据")
        continue
    oil = m30_data[sym]
    hr = list(range(20, 181, 10))

    print(f"\n  --- {sym} M30 CB+RSI 做多 ---")
    for cb, rsi in [(4,25), (4,20), (3,25), (5,25), (3,20)]:
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

    # InsideBar + RSI
    print(f"\n  --- {sym} M30 InsideBar+RSI<20 ---")
    inside = detect_inside_bar(oil)
    cond_inside = inside & (oil['rsi14']<20)
    r_in = test_pattern(oil, cond_inside, f'{sym} M30 InsideBar+RSI<20', hr, 3)
    if r_in and r_in['n'] >= 5:
        all_best_findings.append((f"{sym}_M30_InsideBar_RSI<20", r_in['wr'], r_in['n'], r_in['hold'], r_in['avg']))

# ═══════════════════════════════════════════════════════════════
# 05: US500/US30 H1 做多策略验证 (round36_005)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 05 — US500/US30 H1/M30 做多验证 (round36_005)")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    for sym in ['US500', 'US30']:
        if sym not in data_store:
            continue
        df = data_store[sym]
        hr = list(range(10, 121, 5))

        print(f"\n  --- {sym} {tf_name} CB+RSI 做多 ---")
        for cb, rsi in [(4,20), (4,25), (3,20), (5,25), (3,25)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi)
            r = test_pattern(df, cond, f'{sym} {tf_name} LONG CB>={cb}+RSI<{rsi}', hr, 5)
            if r and r['n'] >= 10:
                best_h = r['hold']
                ow, lo, hi, nb = bootstrap_ci(df, cond, best_h)
                print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
                periods = cross_period_validation(df, cond, best_h, 3)
                cp_ok = sum(1 for p in periods if p['wr']>=60)
                print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
                for p in periods:
                    m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                    print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
                all_best_findings.append((f"{sym}_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

# ═══════════════════════════════════════════════════════════════
# 06: XAUUSD M30 Doji+RSI>75+us 做空 (round36_006)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥇 06 — XAUUSD M30 Doji+RSI>75+us 做空验证 (round36_006)")
print(f"{'='*120}")

if "XAUUSD" in m30_data:
    xu = m30_data["XAUUSD"]
    hr = list(range(5, 101, 5))
    doji = detect_doji(xu)

    print(f"\n  --- A: XAUUSD M30 Doji+RSI>75+us (n=12→积累) ---")
    cond_doji = doji & (xu['rsi14']>75) & (xu['session']=='us')
    r_d = test_pattern(xu, cond_doji, 'XAUUSD M30 SHORT Doji+RSI>75+us', hr, 5, 'short')
    if r_d and r_d['n'] >= 8:
        ow, lo, hi, nb = bootstrap_ci(xu, cond_doji, r_d['hold'], direction='short')
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb})")
        periods = cross_period_validation(xu, cond_doji, r_d['hold'], 3, 'short')
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        all_best_findings.append((f"XAUUSD_M30_SHORT_Doji_RSI>75_us", r_d['wr'], r_d['n'], r_d['hold'], r_d['avg']))

    print(f"\n  --- B: XAUUSD M30 CBull+RSI 做空 ---")
    for cb, rsi in [(5,80), (4,80), (5,75)]:
        cond = (xu['consecutive_bull']>=cb) & (xu['rsi14']>rsi)
        r = test_pattern(xu, cond, f'XAUUSD M30 SHORT CBull>={cb}+RSI>{rsi}', hr, 5, 'short')
        if r and r['n'] >= 5:
            all_best_findings.append((f"XAUUSD_M30_SHORT_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

    print(f"\n  --- C: XAUUSD M30 CB 做多 ---")
    for cb, rsi in [(3,20), (4,20), (3,25)]:
        cond = (xu['consecutive_bear']>=cb) & (xu['rsi14']<rsi)
        r = test_pattern(xu, cond, f'XAUUSD M30 LONG CB>={cb}+RSI<{rsi}', hr, 5)
        if r and r['n'] >= 5:
            all_best_findings.append((f"XAUUSD_M30_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# 07: M1/M5 目标品种超短线扫描 (XAUUSD, XAGUSD, JP225, US500, US30)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("⚡ 07 — M1/M5 目标品种快速扫描")
print(f"品种: XAUUSD, XAGUSD, JP225, US500, US30")
print(f"{'='*120}")

target_symbols = ['XAUUSD', 'XAGUSD', 'JP225', 'US500', 'US30']

for tf_name, data_store in [("M5", m5_data), ("M1", m1_data)]:
    print(f"\n  --- {tf_name} 目标品种 CB+RSI+时段 扫描 ---")
    hr_short = list(range(5, 61, 5))

    for sym in target_symbols:
        if sym not in data_store:
            print(f"  ⚠️ {sym}: {tf_name}数据不可用")
            continue
        df = data_store[sym]

        # 欧盘做多 (连续阴线+超卖)
        for cb, rsi in [(3,10), (3,14), (4,14), (3,18), (4,18)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi) & (df['session']=='europe')
            r = test_pattern(df, cond, f'LONG {sym} {tf_name} EU CB>={cb}+RSI<{rsi}', hr_short, 3)
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"LONG_{sym}_{tf_name}_EU_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

        # 美盘做多
        for cb, rsi in [(2,14), (3,14), (2,18), (3,18), (4,20)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi) & (df['session']=='us')
            r = test_pattern(df, cond, f'LONG {sym} {tf_name} US CB>={cb}+RSI<{rsi}', hr_short, 3)
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"LONG_{sym}_{tf_name}_US_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

        # 美盘做空 (连续阳线+超买)
        for cb, rsi in [(2,80), (3,80), (3,75), (4,80)]:
            cond = (df['consecutive_bull']>=cb) & (df['rsi14']>rsi) & (df['session']=='us')
            r = test_pattern(df, cond, f'SHORT {sym} {tf_name} US CBull>={cb}+RSI>{rsi}', hr_short, 3, 'short')
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"SHORT_{sym}_{tf_name}_US_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

        # 欧洲做空
        for cb, rsi in [(3,80), (4,80), (3,75)]:
            cond = (df['consecutive_bull']>=cb) & (df['rsi14']>rsi) & (df['session']=='europe')
            r = test_pattern(df, cond, f'SHORT {sym} {tf_name} EU CBull>={cb}+RSI>{rsi}', hr_short, 3, 'short')
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"SHORT_{sym}_{tf_name}_EU_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

    # XAUUSD 双枪策略月度跟踪 (M5)
    if tf_name == "M5" and "XAUUSD" in data_store:
        xu5 = data_store["XAUUSD"]
        print(f"\n  --- XAUUSD M5 双枪策略月度跟踪 ---")
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

        combo_n = teu + tus
        combo_wr = (weu + wus) / combo_n if combo_n > 0 else 0
        print(f"\n  双枪组合: n={combo_n} WR={combo_wr:.1f}% 频率={combo_n/5:.1f}次/月")

# ═══════════════════════════════════════════════════════════════
# 08: H1/M30 信号频率统计 (round36_008)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📊 08 — H1/M30 信号频率统计 (round36_008)")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    print(f"\n  --- {tf_name} 最佳策略信号频率 ---")
    print(f"  {'品种':<10} {'策略':<30} {'总信号':<8} {'月均':<8} {'月均天数':<8}")
    print(f"  {'-'*10} {'-'*30} {'-'*8} {'-'*8} {'-'*8}")

    # 估算月份数 (数据跨度)
    first_sym = list(data_store.keys())[0] if data_store else None
    if first_sym:
        df = data_store[first_sym]
        months_span = max(1, (df.index[-1] - df.index[0]).days / 30)

        strategies = []
        # 做多
        for sym in sorted(data_store.keys()):
            df_sym = data_store[sym]
            for cb, rsi in [(3,25), (4,25), (5,25), (3,20), (4,20)]:
                cond = (df_sym['consecutive_bear']>=cb) & (df_sym['rsi14']<rsi)
                n = cond.sum()
                if n >= 10:
                    freq_month = n / months_span
                    strategies.append((sym, f'CB>={cb}+RSI<{rsi}', n, freq_month))
            # 做空
            for cb, rsi in [(4,80), (5,80), (3,80)]:
                cond = (df_sym['consecutive_bull']>=cb) & (df_sym['rsi14']>rsi)
                n = cond.sum()
                if n >= 5:
                    freq_month = n / months_span
                    strategies.append((sym, f'SHORT CBull>={cb}+RSI>{rsi}', n, freq_month))

        strategies.sort(key=lambda x: -x[3])
        for sym, strat, n, freq in strategies[:15]:
            print(f"  {sym:<10} {strat:<30} {n:<8} {freq:<8.1f} {freq/22:<8.1f}")

# ═══════════════════════════════════════════════════════════════
# 09: 新发现汇总排名
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 09 — Round 36 最佳发现排名")
print(f"{'='*120}")

if all_best_findings:
    seen = set()
    unique = []
    for item in all_best_findings:
        key = item[0]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    unique.sort(key=lambda x: (-x[1], -x[2]))

    print(f"\n  {'排名':<5} {'策略':<60} {'WR':<8} {'n':<6} {'Hold':<8} {'avg%':<10}")
    print(f"  {'-'*5} {'-'*60} {'-'*8} {'-'*6} {'-'*8} {'-'*10}")
    for i, (name, wr, n, hold, avg) in enumerate(unique, 1):
        if i > 40:
            print(f"  ... 还有 {len(unique)-40} 个发现未显示")
            break
        print(f"  {i:<5} {name:<60} {wr:.1f}%{'':>3} {n:<6} {hold:<8} {avg:.3f}%")

    results['best_findings'] = [(n, round(w,1), n_val, h, round(a,3)) for n, w, n_val, h, a in unique]
else:
    print(f"\n  (无可用的最佳发现)")
    results['best_findings'] = []

# ═══════════════════════════════════════════════════════════════
# COMPLETE
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("ROUND 36 COMPLETE")
print(f"完成于: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print(f"下一步: 生成报告 → reports/round36_report.md")
print(f"{'='*120}")
