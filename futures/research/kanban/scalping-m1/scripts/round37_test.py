#!/usr/bin/env python3
"""
Round 37 — M1/M5 超短线模式挖掘 + JP225/UKOIL 积累 + XAUUSD M1 极值验证
目标(state next_actions):
  1. JP225 H1/M30做多正式纳入best_known+月度跟踪启动
  2. UKOIL M30做多继续积累 n=32→目标50
  3. XAUUSD M1 EU CB>=3+RSI<10跨周期再确认(n=36)+纳入best_known
  4. EURUSD H1做多月度跟踪(第5月)
  5. XAGUSD M30 SHORT积累 n=28→目标50
  6. XAGUSD M5/M1 EU做多策略验证(WR>74% n>40)
  7. US500 M5 EU CB>=4+RSI<14做多验证 WR=78.1% n=73 → 跨周期检查
  8. M1/M5 超短线新品种策略挖掘(J224/US500/US30 M1)
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

# ============================================================
# MAIN
# ============================================================

results = {}
all_best_findings = []
all_freq_stats = {}

print("=" * 120)
print("ROUND 37 — M1/M5 超短线模式挖掘 + 跨周期验证 + 积累续跑")
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
# round37_001: JP225 H1/M30做多正式纳入best_known+月度跟踪启动
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 01 — JP225 H1/M30 做多月度跟踪启动 (round37_001)")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "JP225" not in data_store:
        continue
    jp = data_store["JP225"]
    hr = list(range(10, 151, 5))

    print(f"\n  --- {tf_name} JP225 CB+RSI 做多验证+月度跟踪 ---")
    # 核心策略：CB>=4+RSI<20 (H1) 或 CB>=4+RSI<20 (M30)
    if tf_name == "H1":
        for cb, rsi, best_hold in [(4, 20, 50), (4, 25, 40), (3, 20, 40)]:
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
        for cb, rsi, best_hold in [(4, 20, 135), (3, 20, 135), (5, 25, 120)]:
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
        cond_track = (jp['consecutive_bear']>=4) & (jp['rsi14']<25)
        monthly_tracking(jp, cond_track, 40, f'JP225 H1 CB>=4+RSI<25 hold=40 月度跟踪启动')

# ═══════════════════════════════════════════════════════════════
# round37_002: UKOIL M30做多继续积累 n=32→目标50
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🛢️  02 — UKOIL M30 做多继续积累 (round37_002) n=32→目标50")
print(f"{'='*120}")

for sym in ['UKOIL', 'USOIL']:
    if sym not in m30_data:
        print(f"  {sym}: 无数据")
        continue
    oil = m30_data[sym]
    hr = list(range(20, 181, 10))

    print(f"\n  --- {sym} M30 CB+RSI 做多积累 ---")
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
# round37_003: XAUUSD M1 EU CB>=3+RSI<10 跨周期再确认(n=36)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏅 03 — XAUUSD M1 EU CB>=3+RSI<10 跨周期再确认 (round37_003)")
print(f"{'='*120}")

if "XAUUSD" in m1_data:
    xu = m1_data["XAUUSD"]
    hr = list(range(10, 121, 5))

    print(f"\n  --- XAUUSD M1 欧盘做多极值验证 ---")
    cond_extreme = (xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session']=='europe')
    r_extreme = test_pattern(xu, cond_extreme, 'XAUUSD M1 EU CB>=3+RSI<10', hr, 10)
    if r_extreme and r_extreme['n'] >= 15:
        best_h = r_extreme['hold']
        ow, lo, hi, nb = bootstrap_ci(xu, cond_extreme, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xu, cond_extreme, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        all_best_findings.append((f"XAUUSD_M1_EU_CB>=3_RSI<10", r_extreme['wr'], r_extreme['n'], best_h, r_extreme['avg']))

    # 补充: XAUUSD M1 EU CB>=4+RSI<14
    cond_safe = (xu['consecutive_bear']>=4) & (xu['rsi14']<14) & (xu['session']=='europe')
    r_safe = test_pattern(xu, cond_safe, 'XAUUSD M1 EU CB>=4+RSI<14', hr, 5)
    if r_safe and r_safe['n'] >= 10:
        best_h = r_safe['hold']
        ow, lo, hi, nb = bootstrap_ci(xu, cond_safe, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xu, cond_safe, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        all_best_findings.append((f"XAUUSD_M1_EU_CB>=4_RSI<14", r_safe['wr'], r_safe['n'], best_h, r_safe['avg']))

# ═══════════════════════════════════════════════════════════════
# round37_004: EURUSD H1做多月度跟踪(第5月)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("💰 04 — EURUSD H1 做多月度跟踪 (round37_004) 第5月")
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

    # 月度跟踪
    cond_track = (eu['consecutive_bear']>=3) & (eu['rsi14']<25)
    r_track = test_pattern(eu, cond_track, 'EURUSD H1 CB>=3+RSI<25 (hold找最优)', hr, 5)
    if r_track and r_track['n'] >= 10:
        monthly_tracking(eu, cond_track, r_track['hold'], f'EURUSD H1 CB>=3+RSI<25 hold={r_track["hold"]} 月度(第5月)')

# ═══════════════════════════════════════════════════════════════
# round37_005: XAGUSD M30 SHORT积累 n=28→目标50
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥈 05 — XAGUSD M30 SHORT 积累 (round37_005) n=28→目标50")
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

    print(f"\n  --- C: 时段细化 ---")
    for sess in ['us', 'europe']:
        cond = (xag['consecutive_bull']>=4) & (xag['rsi14']>80) & (xag['session']==sess)
        r = test_pattern(xag, cond, f'XAGUSD M30 SHORT CBull>=4+RSI>80+{sess}', hr30, 3, 'short')
        if r and r['n'] >= 5:
            all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>=4_RSI>80_{sess}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# round37_006: XAGUSD M5/M1 EU做多策略验证 (WR>74% n>40)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥈 06 — XAGUSD M5/M1 EU做多策略验证 (round37_006)")
print(f"{'='*120}")

for tf_name, data_store in [("M5", m5_data), ("M1", m1_data)]:
    if "XAGUSD" not in data_store:
        continue
    xag = data_store["XAGUSD"]
    hr = list(range(5, 61, 5))

    print(f"\n  --- XAGUSD {tf_name} EU 做多策略验证 ---")
    for cb, rsi in [(3,10), (3,14), (4,14), (3,18), (4,18)]:
        cond = (xag['consecutive_bear']>=cb) & (xag['rsi14']<rsi) & (xag['session']=='europe')
        r = test_pattern(xag, cond, f'LONG XAGUSD {tf_name} EU CB>={cb}+RSI<{rsi}', hr, 5)
        if r and r['n'] >= 10:
            best_h = r['hold']
            ow, lo, hi, nb = bootstrap_ci(xag, cond, best_h)
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(xag, cond, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
            for p in periods:
                m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
            all_best_findings.append((f"LONG_XAGUSD_{tf_name}_EU_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # XAGUSD US 做多也扫一遍
    print(f"\n  --- XAGUSD {tf_name} US 做多扫描 ---")
    for cb, rsi in [(2,14), (3,14), (2,18), (3,18)]:
        cond = (xag['consecutive_bear']>=cb) & (xag['rsi14']<rsi) & (xag['session']=='us')
        r = test_pattern(xag, cond, f'LONG XAGUSD {tf_name} US CB>={cb}+RSI<{rsi}', hr, 5)
        if r and r['n'] >= 10 and r['wr'] >= 65:
            all_best_findings.append((f"LONG_XAGUSD_{tf_name}_US_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# round37_007: US500 M5 EU CB>=4+RSI<14 做多验证 WR=78.1% n=73 → 跨周期
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🇺🇸 07 — US500 M5 EU做多验证 + US30 M5扫描 (round37_007)")
print(f"{'='*120}")

for sym in ['US500', 'US30']:
    for tf_name, data_store in [("M5", m5_data), ("M1", m1_data)]:
        if sym not in data_store:
            continue
        df = data_store[sym]
        hr = list(range(5, 61, 5))

        print(f"\n  --- {sym} {tf_name} EU 做多验证 ---")
        for cb, rsi in [(4,14), (3,10), (3,14), (4,18), (3,18)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi) & (df['session']=='europe')
            r = test_pattern(df, cond, f'LONG {sym} {tf_name} EU CB>={cb}+RSI<{rsi}', hr, 5)
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

        # US 做多
        print(f"\n  --- {sym} {tf_name} US 做多验证 ---")
        for cb, rsi in [(2,14), (3,14), (2,18), (3,18)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi) & (df['session']=='us')
            r = test_pattern(df, cond, f'LONG {sym} {tf_name} US CB>={cb}+RSI<{rsi}', hr, 5)
            if r and r['n'] >= 10 and r['wr'] >= 65:
                all_best_findings.append((f"LONG_{sym}_{tf_name}_US_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# round37_008: M1/M5 超短线新品种策略挖掘 (JP225/US500/US30 M1)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("⚡ 08 — M1/M5 超短线新品种策略挖掘")
print(f"{'='*120}")

target_symbols = ['XAUUSD', 'XAGUSD', 'JP225', 'US500', 'US30']

for tf_name, data_store in [("M5", m5_data), ("M1", m1_data)]:
    print(f"\n  --- {tf_name} 全面扫描 ---")
    hr_short = list(range(5, 61, 5))

    for sym in target_symbols:
        if sym not in data_store:
            continue
        df = data_store[sym]

        # 欧盘做多 (连续阴线+超卖)
        for cb, rsi in [(3,10), (3,14), (4,14), (3,18), (4,18), (5,20)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi) & (df['session']=='europe')
            r = test_pattern(df, cond, f'LONG {sym} {tf_name} EU CB>={cb}+RSI<{rsi}', hr_short, 3)
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"LONG_{sym}_{tf_name}_EU_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

        # 美盘做多
        for cb, rsi in [(2,14), (3,14), (2,18), (3,18), (4,20), (2,10)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi) & (df['session']=='us')
            r = test_pattern(df, cond, f'LONG {sym} {tf_name} US CB>={cb}+RSI<{rsi}', hr_short, 3)
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"LONG_{sym}_{tf_name}_US_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

        # 美盘做空 (连续阳线+超买)
        for cb, rsi in [(2,80), (3,80), (3,75), (4,80), (5,75)]:
            cond = (df['consecutive_bull']>=cb) & (df['rsi14']>rsi) & (df['session']=='us')
            r = test_pattern(df, cond, f'SHORT {sym} {tf_name} US CBull>={cb}+RSI>{rsi}', hr_short, 3, 'short')
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"SHORT_{sym}_{tf_name}_US_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

        # 欧盘做空
        for cb, rsi in [(3,80), (4,80), (3,75)]:
            cond = (df['consecutive_bull']>=cb) & (df['rsi14']>rsi) & (df['session']=='europe')
            r = test_pattern(df, cond, f'SHORT {sym} {tf_name} EU CBull>={cb}+RSI>{rsi}', hr_short, 3, 'short')
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"SHORT_{sym}_{tf_name}_EU_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# XAUUSD M5 双枪策略月度跟踪
# ═══════════════════════════════════════════════════════════════
if "XAUUSD" in m5_data:
    xu5 = m5_data["XAUUSD"]
    print(f"\n{'='*120}")
    print("🔫 双枪策略月度跟踪 (XAUUSD M5)")
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
print("🏆 ROUND 37 — 最佳发现排名")
print(f"{'='*120}")

# 去重+排序
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
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'round37_output.txt')
# Redirect prints to file as well
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

# Print summary again to file
print(f"\n\n{'='*120}")
print(f"ROUND 37 COMPLETE — {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print(f"{'='*120}")
print(f"Total patterns tested: {len(all_best_findings)}")
print(f"Unique findings: {len(sorted_findings)}")
_sys.stdout = _sys.__stdout__
f_out.close()
print(f"\n✅ 输出已保存到: {output_path}")
