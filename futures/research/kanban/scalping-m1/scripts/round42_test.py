#!/usr/bin/env python3
"""
Round 42 — H1/M30 K线形态深度验证: 月度跟踪续跑 + 新品种确认 + 跨周期验证
目标(next_actions from round41):
  1. XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第4月)+双极值+ASIA新阈值确认
  2. XAGUSD M5 EU 新阈值CB>=2+RSI<8 n积累跟踪; CB>=2+RSI<10验证
  3. EURUSD H1做多月度跟踪(第10月)+M30 CB>=4+RSI<20确认跟踪启动
  4. US500 M5 EU CB>=5+RSI<14月度跟踪续跑(第2月)
  5. XAGUSD M30 SHORT CBull>=4+RSI>85+us 持续积累(n->20)
  6. GBPUSD H1 US CB>=3+RSI<25积累验证+M30 US时段深度验证
  7. USTEC M30/H1 月度跟踪启动+M30 CB>=4+RSI<18/20 CP3/3纳入评估
  8. JP225 H1/M30做多月度跟踪(第6月)+M30 InsideBar跟踪
  9. HK50 H1做多积累验证+USDCHF H1月度跟踪启动
  10. XAUUSD M1双极值+ASIA新方向验证+AUDUSD M30 CP3/3候选评估
时间框架: H1, M30, M5, M1
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

def monthly_tracking(df, cond, hold, label, direction='long'):
    df = df.copy()
    df['month'] = df.index.to_period('M')
    tn, tw, ta = 0, 0.0, 0.0
    print(f"\n  {label}")
    for month, grp in df.groupby('month'):
        if direction == 'short':
            cnt, wr, avg = get_stats_short(grp, cond.loc[grp.index], hold)
        else:
            cnt, wr, avg = get_stats(grp, cond.loc[grp.index], hold)
        if cnt > 0:
            marker = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
            print(f"    {month}: n={cnt} WR={wr:.1f}% avg={avg:.3f}% {marker}")
            tn += cnt; tw += cnt*wr; ta += cnt*avg
    if tn > 0:
        print(f"  → 总计: n={tn} WR={tw/tn:.1f}% avg={ta/tn:.3f}%")
    return tn, tw/tn if tn else 0

# Pattern detection
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
print("ROUND 42 — H1/M30 K线形态深度验证: 月度跟踪续跑 + 新品种确认 + 跨周期验证")
print(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print("品种: 期货外汇14品种")
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
# round42_001: XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第4月)+双极值+ASIA新阈值确认
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥇 01 — XAUUSD M1 极值策略月跟踪(第4月)+双极值+ASIA新阈值确认 (round42_001)")
print(f"{'='*120}")

if "XAUUSD" in m1_data:
    xu = m1_data["XAUUSD"]
    hr = list(range(10, 121, 5))

    # A: US CB>=3+RSI<10 (核心, 月度跟踪第4月)
    print(f"\n  --- A: XAUUSD M1 US CB>=3+RSI<10 (核心, 月度跟踪第4月续跑) ---")
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
        monthly_tracking(xu, cond_us_strong, best_h,
                         f'XAUUSD M1 US CB>=3+RSI<10 hold={best_h} 月度跟踪(第4月续跑)')

    # B: US CB>=2+RSI<10 (基础极值, 持续监控)
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

    # C: 双极值联合 (EU+US)
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

    # D: ASIA 新阈值确认
    print(f"\n  --- D: XAUUSD M1 ASIA CB+RSI 新阈值确认 ---")
    for cb, rsi in [(2,10), (3,10), (2,14), (3,14)]:
        cond_asia = (xu['consecutive_bear']>=cb) & (xu['rsi14']<rsi) & (xu['session']=='asia')
        r_asia = test_pattern(xu, cond_asia, f'XAUUSD M1 ASIA CB>={cb}+RSI<{rsi}', hr, 10)
        if r_asia and r_asia['n'] >= 20 and r_asia['wr'] >= 65:
            best_h = r_asia['hold']
            ow, lo, hi, nb = bootstrap_ci(xu, cond_asia, best_h)
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(xu, cond_asia, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
            all_best_findings.append((f"XAUUSD_M1_ASIA_CB>={cb}_RSI<{rsi}", r_asia['wr'], r_asia['n'], best_h, r_asia['avg']))

    # E: 信号频率统计
    print(f"\n  --- E: 极值信号频率统计 ---")
    eu_count = ((xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session']=='europe')).sum()
    us_strong_count = cond_us_strong.sum()
    us_base_count = cond_us_base.sum()
    dual_count = cond_dual.sum()
    asia_count = ((xu['consecutive_bear']>=2) & (xu['rsi14']<10) & (xu['session']=='asia')).sum()
    print(f"    EU 极值 (CB>=3+RSI<10):        {eu_count} 信号")
    print(f"    US 极值-强 (CB>=3+RSI<10):     {us_strong_count} 信号")
    print(f"    US 极值-基础 (CB>=2+RSI<10):   {us_base_count} 信号")
    print(f"    双极值联合 (EU+US强):           {dual_count} 信号")
    print(f"    ASIA (CB>=2+RSI<10):            {asia_count} 信号")

# ═══════════════════════════════════════════════════════════════
# round42_002: XAGUSD M5 EU 新阈值积累跟踪 + 原策略监控
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥈 02 — XAGUSD M5 EU 新阈值积累跟踪 + 原策略监控 (round42_002)")
print(f"{'='*120}")

if "XAGUSD" in m5_data:
    xag5 = m5_data["XAGUSD"]
    hr5 = list(range(5, 61, 5))

    # A: 新阈值 CB>=2+RSI<8 (积累跟踪)
    print(f"\n  --- A: XAGUSD M5 EU CB>=2+RSI<8 (新阈值, n积累跟踪) ---")
    cond_new = (xag5['consecutive_bear']>=2) & (xag5['rsi14']<8) & (xag5['session']=='europe')
    r_new = test_pattern(xag5, cond_new, 'XAGUSD M5 EU CB>=2+RSI<8', hr5, 5)
    if r_new and r_new['n'] >= 5:
        best_h = r_new['hold']
        ow, lo, hi, nb = bootstrap_ci(xag5, cond_new, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xag5, cond_new, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        all_best_findings.append((f"XAGUSD_M5_EU_CB>=2_RSI<8", r_new['wr'], r_new['n'], best_h, r_new['avg']))

    # B: 原策略 CB>=3+RSI<10 继续监控
    print(f"\n  --- B: XAGUSD M5 EU CB>=3+RSI<10 (原策略, 持续监控) ---")
    cond3 = (xag5['consecutive_bear']>=3) & (xag5['rsi14']<10) & (xag5['session']=='europe')
    r3 = test_pattern(xag5, cond3, 'XAGUSD M5 EU CB>=3+RSI<10', hr5, 5)
    if r3 and r3['n'] >= 10:
        best_h = r3['hold']
        periods = cross_period_validation(xag5, cond3, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        all_best_findings.append((f"XAGUSD_M5_EU_CB>=3_RSI<10", r3['wr'], r3['n'], best_h, r3['avg']))

    # C: CB>=2+RSI<10 新发现验证
    print(f"\n  --- C: XAGUSD M5 EU CB>=2+RSI<10 (新发现验证) ---")
    cond_wide = (xag5['consecutive_bear']>=2) & (xag5['rsi14']<10) & (xag5['session']=='europe')
    r_wide = test_pattern(xag5, cond_wide, 'XAGUSD M5 EU CB>=2+RSI<10', hr5, 10)
    if r_wide and r_wide['n'] >= 20:
        best_h = r_wide['hold']
        ow, lo, hi, nb = bootstrap_ci(xag5, cond_wide, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xag5, cond_wide, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        all_best_findings.append((f"XAGUSD_M5_EU_CB>=2_RSI<10", r_wide['wr'], r_wide['n'], best_h, r_wide['avg']))

# ═══════════════════════════════════════════════════════════════
# round42_003: EURUSD H1做多月度跟踪(第10月)+M30 CB>=4+RSI<20确认跟踪启动
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("💰 03 — EURUSD H1 做多月度跟踪(第10月)+M30确认 (round42_003)")
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
            print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
            all_best_findings.append((f"EURUSD_H1_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # 月度跟踪 CB>=3+RSI<25 (第10月)
    cond_track = (eu['consecutive_bear']>=3) & (eu['rsi14']<25)
    r_track = test_pattern(eu, cond_track, 'EURUSD H1 CB>=3+RSI<25 (最优hold)', hr, 5)
    if r_track and r_track['n'] >= 10:
        monthly_tracking(eu, cond_track, r_track['hold'],
                         f'EURUSD H1 CB>=3+RSI<25 hold={r_track["hold"]} 月度跟踪(第10月)')

    # EURUSD M30 验证
    if "EURUSD" in m30_data:
        eum30 = m30_data["EURUSD"]
        hr30_m = list(range(10, 121, 5))
        print(f"\n  --- EURUSD M30 CB+RSI 做多验证 (跟踪启动) ---")
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

        # M30月度跟踪启动
        if r and r['n'] >= 10:
            monthly_tracking(eum30, 
                             (eum30['consecutive_bear']>=4) & (eum30['rsi14']<20),
                             (r['hold'] if r['wr'] >= 60 else 70),
                             f'EURUSD M30 CB>=4+RSI<20 hold={r["hold"]} 月度跟踪(第1月启动)')

# ═══════════════════════════════════════════════════════════════
# round42_004: US500 M5 EU CB>=5+RSI<14月度跟踪续跑(第2月)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🇺🇸 04 — US500 M5 EU CB>=5+RSI<14 月度跟踪续跑(第2月) (round42_004)")
print(f"{'='*120}")

for sym in ['US500', 'US30']:
    for tf_name, data_store in [("M5", m5_data), ("M1", m1_data)]:
        if sym not in data_store:
            continue
        df = data_store[sym]
        hr_short = list(range(5, 61, 5))

        print(f"\n  --- {sym} {tf_name} EU 做多验证 ---")
        for cb, rsi in [(4,14), (5,14), (3,10), (3,14), (4,18), (3,18), (2,10)]:
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

                # US500 M5 EU CB>=5+RSI<14 月度跟踪续跑(第2月)
                if sym == 'US500' and tf_name == 'M5' and cb == 5 and rsi == 14:
                    monthly_tracking(df, cond, best_h,
                                     f'US500 M5 EU CB>=5+RSI<14 hold={best_h} 月度跟踪(第2月续跑)')

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

    # US30 M1 EU 时段子策略重验证
    if sym == 'US30' and 'US30' in m1_data:
        us30m1 = m1_data["US30"]
        hr_m1 = list(range(5, 61, 5))
        print(f"\n  --- US30 M1 EU 时段子策略重验证 ---")
        for hour_slot in [8, 9, 10, 11]:
            cond = (us30m1['consecutive_bear']>=4) & (us30m1['rsi14']<14) & (us30m1['hour']==hour_slot)
            r = test_pattern(us30m1, cond, f'US30 M1 EU hour={hour_slot} CB>=4+RSI<14', hr_m1, 3)
            if r and r['n'] >= 5 and r['wr'] >= 70:
                all_best_findings.append((f"US30_M1_EU_H{hour_slot}_CB>=4_RSI<14", r['wr'], r['n'], r['hold'], r['avg']))
        
        # CB>=3+RSI<14 替代方案确认
        print(f"\n  --- US30 M1 EU CB>=3+RSI<14 替代方案确认 ---")
        cond_alt = (us30m1['consecutive_bear']>=3) & (us30m1['rsi14']<14) & (us30m1['session']=='europe')
        r_alt = test_pattern(us30m1, cond_alt, 'US30 M1 EU CB>=3+RSI<14 (替代方案)', hr_m1, 10)
        if r_alt and r_alt['n'] >= 15:
            best_h = r_alt['hold']
            ow, lo, hi, nb = bootstrap_ci(us30m1, cond_alt, best_h)
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(us30m1, cond_alt, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
            all_best_findings.append((f"US30_M1_EU_ALT_CB>=3_RSI<14", r_alt['wr'], r_alt['n'], best_h, r_alt['avg']))

# ═══════════════════════════════════════════════════════════════
# round42_005: XAGUSD M30 SHORT CBull>=4+RSI>85+us 持续积累(n->20)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥈 05 — XAGUSD M30 SHORT 积累验证 (round42_005) US子策略n->20")
print(f"{'='*120}")

if "XAGUSD" in m30_data:
    xag = m30_data["XAGUSD"]
    hr30 = list(range(15, 151, 5))

    # 核心: CBull>=4+RSI>85
    print(f"\n  --- A: XAGUSD M30 SHORT CBull>=4+RSI>85 (核心) ---")
    cond_core85 = (xag['consecutive_bull']>=4) & (xag['rsi14']>85)
    r_core85 = test_pattern(xag, cond_core85, 'XAGUSD M30 SHORT CBull>=4+RSI>85', hr30, 5, 'short')
    if r_core85 and r_core85['n'] >= 10:
        best_h = r_core85['hold']
        ow, lo, hi, nb = bootstrap_ci(xag, cond_core85, best_h, direction='short')
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xag, cond_core85, best_h, 3, 'short')
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>=4_RSI>85", r_core85['wr'], r_core85['n'], best_h, r_core85['avg']))

    # US子策略 (n->20)
    print(f"\n  --- B: XAGUSD M30 SHORT US时段子策略 (n积累->20) ---")
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

    # 阈值探索
    print(f"\n  --- C: 阈值探索 ---")
    for cb, rsi in [(3,80), (5,80), (3,75), (4,90), (5,85)]:
        cond = (xag['consecutive_bull']>=cb) & (xag['rsi14']>rsi)
        r = test_pattern(xag, cond, f'XAGUSD M30 SHORT CBull>={cb}+RSI>{rsi}', hr30, 5, 'short')
        if r and r['n'] >= 10 and r['wr'] >= 65:
            best_h = r['hold']
            periods = cross_period_validation(xag, cond, best_h, 3, 'short')
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
            all_best_findings.append((f"XAGUSD_M30_SHORT_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], best_h, r['avg']))

# ═══════════════════════════════════════════════════════════════
# round42_006: GBPUSD H1 US CB>=3+RSI<25积累验证+M30 US时段深度验证
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🇬🇧 06 — GBPUSD H1 US + M30 US 深度验证 (round42_006)")
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
                all_best_findings.append((f"{sym}_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

        # 时段探索
        if 'session' in gbp.columns:
            print(f"\n  --- {sym} {tf_name} EU/US 时段探索 ---")
            for session_name in ['europe', 'us']:
                for cb, rsi in [(3,20), (3,25), (4,20)]:
                    cond_s = (gbp['consecutive_bear']>=cb) & (gbp['rsi14']<rsi) & (gbp['session']==session_name)
                    r_s = test_pattern(gbp, cond_s, f'{sym} {tf_name} {session_name} CB>={cb}+RSI<{rsi}', hr, 5)
                    if r_s and r_s['n'] >= 5 and r_s['wr'] >= 65:
                        all_best_findings.append((f"{sym}_{tf_name}_{session_name.upper()}_CB>={cb}_RSI<{rsi}", r_s['wr'], r_s['n'], r_s['hold'], r_s['avg']))

# ═══════════════════════════════════════════════════════════════
# round42_007: USTEC M30/H1 月度跟踪启动+M30 CP3/3纳入评估
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📈 07 — USTEC M30/H1 月度跟踪启动 + 纳入评估 (round42_007)")
print(f"{'='*120}")

for sym in ['USTEC']:
    for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
        if sym not in data_store:
            continue
        tec = data_store[sym]
        hr = list(range(10, 121, 5))

        print(f"\n  --- {sym} {tf_name} CB+RSI 做多验证 ---")
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

        # USTEC月度跟踪启动 (M30 CB>=4+RSI<20)
        if tf_name == "M30":
            cond_track_tec = (tec['consecutive_bear']>=4) & (tec['rsi14']<20)
            r_tec_track = test_pattern(tec, cond_track_tec, f'USTEC M30 CB>=4+RSI<20', hr, 5)
            if r_tec_track and r_tec_track['n'] >= 15:
                monthly_tracking(tec, cond_track_tec, r_tec_track['hold'],
                                 f'USTEC M30 CB>=4+RSI<20 hold={r_tec_track["hold"]} 月度跟踪(第1月启动)')

        # 时段探索
        print(f"\n  --- {sym} {tf_name} EU/US 时段探索 ---")
        for session_name in ['europe', 'us']:
            for cb, rsi in [(3,20), (4,20), (3,25)]:
                cond_s = (tec['consecutive_bear']>=cb) & (tec['rsi14']<rsi) & (tec['session']==session_name)
                r_s = test_pattern(tec, cond_s, f'{sym} {tf_name} {session_name} CB>={cb}+RSI<{rsi}', hr, 5)
                if r_s and r_s['n'] >= 5 and r_s['wr'] >= 65:
                    all_best_findings.append((f"{sym}_{tf_name}_{session_name.upper()}_CB>={cb}_RSI<{rsi}", r_s['wr'], r_s['n'], r_s['hold'], r_s['avg']))

# ═══════════════════════════════════════════════════════════════
# round42_008: JP225 H1/M30做多月度跟踪(第6月)+M30 InsideBar跟踪
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 08 — JP225 H1/M30 做多月度跟踪(第6月) (round42_008)")
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
            print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
            all_best_findings.append((f"JP225_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

    # 月度跟踪
    if tf_name == "H1":
        cond_track_jp = (jp['consecutive_bear']>=4) & (jp['rsi14']<25)
        r_jp_track = test_pattern(jp, cond_track_jp, 'JP225 H1 CB>=4+RSI<25', hr, 5)
        if r_jp_track:
            monthly_tracking(jp, cond_track_jp, 40,
                             f'JP225 H1 CB>=4+RSI<25 hold=40 月度跟踪(第6月)')
    elif tf_name == "M30":
        cond_track_jp30 = (jp['consecutive_bear']>=4) & (jp['rsi14']<20)
        r_jp30_track = test_pattern(jp, cond_track_jp30, 'JP225 M30 CB>=4+RSI<20', hr, 5)
        if r_jp30_track:
            monthly_tracking(jp, cond_track_jp30, 135,
                             f'JP225 M30 CB>=4+RSI<20 hold=135 月度跟踪(第6月)')

    # M30 InsideBar跟踪
    if tf_name == "M30":
        print(f"\n  --- JP225 M30 InsideBar+RSI<25 跟踪 ---")
        inside = detect_inside_bar(jp)
        cond_in = inside & (jp['rsi14']<25)
        r_in_jp = test_pattern(jp, cond_in, f'JP225 M30 InsideBar+RSI<25 LONG', hr, 3)
        if r_in_jp and r_in_jp['n'] >= 5:
            all_best_findings.append((f"JP225_M30_InsideBar_RSI<25", r_in_jp['wr'], r_in_jp['n'], r_in_jp['hold'], r_in_jp['avg']))

# ═══════════════════════════════════════════════════════════════
# round42_009: HK50 H1做多积累验证+USDCHF H1月度跟踪启动
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🇭🇰 09 — HK50 H1 做多积累验证 + USDCHF H1月度跟踪启动 (round42_009)")
print(f"{'='*120}")

for sym in ['HK50', 'USDCHF']:
    for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
        if sym not in data_store:
            continue
        hk = data_store[sym]
        hr = list(range(10, 121, 5))

        print(f"\n  --- {sym} {tf_name} CB+RSI 做多验证 ---")
        for cb, rsi in [(3,20), (4,20), (3,25), (4,25), (5,25), (2,18), (3,18)]:
            cond = (hk['consecutive_bear']>=cb) & (hk['rsi14']<rsi)
            r = test_pattern(hk, cond, f'{sym} {tf_name} LONG CB>={cb}+RSI<{rsi}', hr, 5)
            if r and r['n'] >= 10 and r['wr'] >= 65:
                best_h = r['hold']
                ow, lo, hi, nb = bootstrap_ci(hk, cond, best_h)
                print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
                periods = cross_period_validation(hk, cond, best_h, 3)
                cp_ok = sum(1 for p in periods if p['wr']>=60)
                print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
                all_best_findings.append((f"{sym}_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

        # ASIA 时段探索 (HK50)
        if sym == 'HK50':
            print(f"\n  --- HK50 {tf_name} ASIA 时段探索 ---")
            cond_asia = (hk['consecutive_bear']>=3) & (hk['rsi14']<25) & (hk['session']=='asia')
            r_hk_asia = test_pattern(hk, cond_asia, f'HK50 {tf_name} ASIA CB>=3+RSI<25', hr, 5)
            if r_hk_asia and r_hk_asia['n'] >= 5 and r_hk_asia['wr'] >= 65:
                all_best_findings.append((f"HK50_{tf_name}_ASIA_CB>=3_RSI<25", r_hk_asia['wr'], r_hk_asia['n'], r_hk_asia['hold'], r_hk_asia['avg']))

        # USDCHF月度跟踪启动
        if sym == 'USDCHF' and tf_name == 'H1':
            cond_chf = (hk['consecutive_bear']>=3) & (hk['rsi14']<18)
            r_chf = test_pattern(hk, cond_chf, 'USDCHF H1 CB>=3+RSI<18 (月度跟踪启动)', hr, 5)
            if r_chf and r_chf['n'] >= 15:
                monthly_tracking(hk, cond_chf, r_chf['hold'],
                                 f'USDCHF H1 CB>=3+RSI<18 hold={r_chf["hold"]} 月度跟踪(第1月启动)')

# ═══════════════════════════════════════════════════════════════
# round42_010: XAUUSD M1双极值+ASIA新方向验证+AUDUSD M30 CP3/3候选评估
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥇 10 — XAUUSD M1 EU极值月度跟踪续跑 + AUDUSD M30 CP3/3评估 (round42_010)")
print(f"{'='*120}")

if "XAUUSD" in m1_data:
    xu = m1_data["XAUUSD"]
    hr = list(range(10, 121, 5))

    # EU极值: CB>=3+RSI<10 月度跟踪续跑
    print(f"\n  --- EU极值: XAUUSD M1 EU CB>=3+RSI<10 ---")
    cond_eu = (xu['consecutive_bear']>=3) & (xu['rsi14']<10) & (xu['session']=='europe')
    r_eu = test_pattern(xu, cond_eu, 'XAUUSD M1 EU CB>=3+RSI<10', hr, 5)
    if r_eu and r_eu['n'] >= 5:
        best_h = r_eu['hold']
        ow, lo, hi, nb = bootstrap_ci(xu, cond_eu, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(xu, cond_eu, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
        all_best_findings.append((f"XAUUSD_M1_EU_CB>=3_RSI<10", r_eu['wr'], r_eu['n'], best_h, r_eu['avg']))
        monthly_tracking(xu, cond_eu, best_h,
                         f'XAUUSD M1 EU CB>=3+RSI<10 hold={best_h} 月度跟踪续跑')

# AUDUSD M30 CP3/3候选评估
if "AUDUSD" in m30_data:
    aud = m30_data["AUDUSD"]
    hr30 = list(range(10, 121, 5))
    print(f"\n  --- AUDUSD M30 CB+RSI 做多CP3/3候选评估 ---")
    for cb, rsi in [(3,18), (3,20), (2,18), (4,20)]:
        cond = (aud['consecutive_bear']>=cb) & (aud['rsi14']<rsi)
        r = test_pattern(aud, cond, f'AUDUSD M30 LONG CB>={cb}+RSI<{rsi}', hr30, 5)
        if r and r['n'] >= 10 and r['wr'] >= 65:
            best_h = r['hold']
            ow, lo, hi, nb = bootstrap_ci(aud, cond, best_h)
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
            periods = cross_period_validation(aud, cond, best_h, 3)
            cp_ok = sum(1 for p in periods if p['wr']>=60)
            print(f"    跨周期验证: {cp_ok}/{len(periods)} 通过")
            for p in periods:
                m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
                print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
            all_best_findings.append((f"AUDUSD_M30_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))

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
# H1/M30 形态+RSI 深度探索 (新增!)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🔍 H1/M30 形态+RSI 深度探索 (新增)")
print(f"{'='*120}")

for sym in all_symbols:
    for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
        if sym not in data_store:
            continue
        df = data_store[sym]
        hr = list(range(10, 121, 5))

        # Doji (做空在高RSI区域)
        print(f"\n  {sym} {tf_name} Doji+RSI 做空探索 ---")
        doji = detect_doji(df, 0.1)
        for rsi_threshold in [75, 80]:
            cond_dj = doji & (df['rsi14']>rsi_threshold)
            r_dj = test_pattern(df, cond_dj, f'{sym} {tf_name} Doji+RSI>{rsi_threshold} SHORT', hr, 3, 'short')
            if r_dj and r_dj['n'] >= 5 and r_dj['wr'] >= 65:
                all_best_findings.append((f"{sym}_{tf_name}_Doji_RSI>{rsi_threshold}_SHORT", r_dj['wr'], r_dj['n'], r_dj['hold'], r_dj['avg']))

        # 吞没形态 (做多在低RSI区域)
        engulf_bull = detect_engulfing_bull(df)
        for rsi_threshold in [30, 25, 20]:
            cond_eb = engulf_bull & (df['rsi14']<rsi_threshold)
            r_eb = test_pattern(df, cond_eb, f'{sym} {tf_name} EngulfBull+RSI<{rsi_threshold} LONG', hr, 3, 'long')
            if r_eb and r_eb['n'] >= 5 and r_eb['wr'] >= 65:
                all_best_findings.append((f"{sym}_{tf_name}_EngulfBull_RSI<{rsi_threshold}_LONG", r_eb['wr'], r_eb['n'], r_eb['hold'], r_eb['avg']))

        # 吞没形态 (做空在高RSI区域)
        engulf_bear = detect_engulfing_bear(df)
        for rsi_threshold in [70, 75, 80]:
            cond_eb2 = engulf_bear & (df['rsi14']>rsi_threshold)
            r_eb2 = test_pattern(df, cond_eb2, f'{sym} {tf_name} EngulfBear+RSI>{rsi_threshold} SHORT', hr, 3, 'short')
            if r_eb2 and r_eb2['n'] >= 5 and r_eb2['wr'] >= 65:
                all_best_findings.append((f"{sym}_{tf_name}_EngulfBear_RSI>{rsi_threshold}_SHORT", r_eb2['wr'], r_eb2['n'], r_eb2['hold'], r_eb2['avg']))

        # 锤子线 (做多在低RSI)
        hammer = detect_hammer(df)
        for rsi_threshold in [30, 25]:
            cond_hm = hammer & (df['rsi14']<rsi_threshold)
            r_hm = test_pattern(df, cond_hm, f'{sym} {tf_name} Hammer+RSI<{rsi_threshold} LONG', hr, 3, 'long')
            if r_hm and r_hm['n'] >= 5 and r_hm['wr'] >= 65:
                all_best_findings.append((f"{sym}_{tf_name}_Hammer_RSI<{rsi_threshold}_LONG", r_hm['wr'], r_hm['n'], r_hm['hold'], r_hm['avg']))

        # 流星线 (做空在高RSI)
        star = detect_shooting_star(df)
        for rsi_threshold in [70, 75]:
            cond_st = star & (df['rsi14']>rsi_threshold)
            r_st = test_pattern(df, cond_st, f'{sym} {tf_name} ShootingStar+RSI>{rsi_threshold} SHORT', hr, 3, 'short')
            if r_st and r_st['n'] >= 5 and r_st['wr'] >= 65:
                all_best_findings.append((f"{sym}_{tf_name}_ShootingStar_RSI>{rsi_threshold}_SHORT", r_st['wr'], r_st['n'], r_st['hold'], r_st['avg']))

# ═══════════════════════════════════════════════════════════════
# SUMMARY: Top Findings
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 ROUND 42 — 最佳发现排名")
print(f"{'='*120}")

seen = set()
unique_findings = []
for item in all_best_findings:
    key = item[0]
    if key not in seen:
        seen.add(key)
        unique_findings.append(item)

sorted_findings = sorted(unique_findings, key=lambda x: (x[1], x[2]), reverse=True)
print(f"\n{'排名':<5} {'策略':<55} {'WR':>6} {'n':>5} {'Hold':>5} {'avg%':>8}")
print("-" * 85)
for i, (name, wr, n, hold, avg) in enumerate(sorted_findings[:50], 1):
    print(f"{i:<5} {name:<55} {wr:>5.1f}% {n:>5} {hold:>5} {avg:>7.3f}%")

# ═══════════════════════════════════════════════════════════════
# SAVE OUTPUT
# ═══════════════════════════════════════════════════════════════
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'round42_output.txt')
with open(output_path, 'w', encoding='utf-8') as f_out:
    print(f"\n\n{'='*120}", file=f_out)
    print(f"ROUND 42 COMPLETE — {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC", file=f_out)
    print(f"{'='*120}", file=f_out)
    print(f"Total patterns tested: {len(all_best_findings)}", file=f_out)
    print(f"Unique findings: {len(sorted_findings)}", file=f_out)
    print(f"\n\nTop Findings Ranking:", file=f_out)
    print(f"{'Rank':<5} {'Strategy':<55} {'WR':>6} {'n':>5} {'Hold':>5} {'avg%':>8}", file=f_out)
    print("-" * 85, file=f_out)
    for i, (name, wr, n, hold, avg) in enumerate(sorted_findings[:80], 1):
        print(f"{i:<5} {name:<55} {wr:>5.1f}% {n:>5} {hold:>5} {avg:>7.3f}%", file=f_out)

print(f"\n✅ 输出已保存到: {output_path}")
