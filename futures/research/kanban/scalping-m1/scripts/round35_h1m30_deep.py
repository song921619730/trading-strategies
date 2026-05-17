#!/usr/bin/env python3
"""
Round 35 — H1/M30 K线形态深度验证与跨周期确认
目标:
  1. XAGUSD H1/M30 做空策略深度验证 (CBull+RSI+时段)
  2. EURUSD H1 连续阴线做多策略跨周期验证
  3. USDJPY H1 做多策略月度跟踪 (延续round34)
  4. H1/M30 新形态组合发现 (InsideBar+CB+RSI)
  5. 跨品种 H1/M30 信号一致性检查 (XAU/XAG联动)
  6. Hold参数敏感性分析
时间框架: H1, M30
品种: 期货外汇14品种 (严禁A股)
"""
import sys, os, json
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts')
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

# ═══════════════════════════════════════════════════════════════
# PATTERN DETECTION (精简版)
# ═══════════════════════════════════════════════════════════════

def detect_inside_bar(df):
    return (df['high'] < df['high'].shift(1)) & (df['low'] > df['low'].shift(1))

def detect_engulfing_bull(df):
    prev_bear = df['close'].shift(1) < df['open'].shift(1)
    curr_bull = df['close'] > df['open']
    engulf = (df['close'] > df['open'].shift(1)) & (df['open'] < df['close'].shift(1))
    return prev_bear & curr_bull & engulf

def detect_engulfing_bear(df):
    prev_bull = df['close'].shift(1) > df['open'].shift(1)
    curr_bear = df['close'] < df['open']
    engulf = (df['open'] > df['close'].shift(1)) & (df['close'] < df['open'].shift(1))
    return prev_bull & curr_bear & engulf

def detect_doji(df, body_pct=0.1):
    body = abs(df['close'] - df['open'])
    total = df['high'] - df['low']
    return (body / total.replace(0, np.nan)) < body_pct

def detect_three_black_crows(df):
    bear1 = (df['close'].shift(2) < df['open'].shift(2)) & ((df['open'].shift(2) - df['close'].shift(2)) > 0)
    bear2 = (df['close'].shift(1) < df['open'].shift(1)) & ((df['open'].shift(1) - df['close'].shift(1)) > 0)
    bear3 = (df['close'] < df['open']) & ((df['open'] - df['close']) > 0)
    return bear1 & bear2 & bear3

def detect_three_white_soldiers(df):
    bull1 = (df['close'].shift(2) > df['open'].shift(2)) & ((df['close'].shift(2) - df['open'].shift(2)) > 0)
    bull2 = (df['close'].shift(1) > df['open'].shift(1)) & ((df['close'].shift(1) - df['open'].shift(1)) > 0)
    bull3 = (df['close'] > df['open']) & ((df['close'] - df['open']) > 0)
    return bull1 & bull2 & bull3

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
print("ROUND 35 — H1/M30 K线形态深度验证与跨周期确认")
print(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print("品种: 期货外汇14品种 (XAUUSD/XAGUSD/EURUSD/GBPUSD/USDJPY/AUDUSD/USDCHF/")
print("                      US30/US500/USTEC/JP225/HK50/USOIL/UKOIL)")
print("=" * 120)

# ═══════════════════════════════════════════════════════════════
# 00: DATA FRESHNESS CHECK
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📡 00 — 数据新鲜度检查")
print(f"{'='*120}")
for tf in ['H1', 'M30']:
    d = os.path.join(BASE, 'data', tf)
    if not os.path.exists(d): continue
    files = [f for f in os.listdir(d) if f.endswith('.parquet')]
    if files:
        df = pd.read_parquet(os.path.join(d, files[0]))
        print(f"  {tf:4s}: 最新={df.index[-1]} 行数={len(df):>6} 品种={len(files)}")
        print(f"        亚洲={(df.index.hour<8).sum():>6} 欧洲={((df.index.hour>=8)&(df.index.hour<13)).sum():>6} 美国={(df.index.hour>=13).sum():>6}")

# ═══════════════════════════════════════════════════════════════
# LOAD DATA FOR H1 AND M30
# ═══════════════════════════════════════════════════════════════
all_symbols = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
               "US30", "US500", "USTEC", "JP225", "HK50", "UKOIL", "USOIL"]

h1_data = {}
m30_data = {}

for tf in ["H1", "M30"]:
    print(f"\n{'='*120}")
    print(f"📊 加载 {tf} 数据")
    print(f"{'='*120}")
    raw = load_data(tf, symbols=all_symbols)
    store = h1_data if tf == "H1" else m30_data
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
# 01: XAGUSD H1/M30 做空策略深度验证 (延续round32/34)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 01 — XAGUSD H1/M30 做空策略深度验证")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "XAGUSD" not in data_store:
        print(f"\n  ⚠️ XAGUSD {tf_name} 无数据")
        continue
    xag = data_store["XAGUSD"]
    hr = list(range(15, 151, 5))
    
    print(f"\n  --- {tf_name} XAGUSD CBull 做空 ---")
    
    # CBull + RSI 组合扫描
    for cb in [3, 4, 5, 6]:
        for rsi in [75, 80, 82]:
            if cb <= 3 and rsi <= 75:  # 跳过过宽松组合
                cond = (xag['consecutive_bull']>=cb) & (xag['rsi14']>rsi)
                r = test_pattern(xag, cond, f'XAGUSD {tf_name} SHORT CBull>={cb}+RSI>{rsi}', hr, 5, 'short')
                if r and r['n'] >= 10:
                    all_best_findings.append((f"XAGUSD_{tf_name}_SHORT_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))
        
        # 严格版 + 时段过滤
        for rsi in [80, 82]:
            for sess in ['us', 'europe']:
                cond = (xag['consecutive_bull']>=cb) & (xag['rsi14']>rsi) & (xag['session']==sess)
                r = test_pattern(xag, cond, f'XAGUSD {tf_name} SHORT CBull>={cb}+RSI>{rsi}+{sess}', hr, 3, 'short')
                if r and r['n'] >= 5:
                    all_best_findings.append((f"XAGUSD_{tf_name}_SHORT_CBull>={cb}_RSI>{rsi}_{sess}", r['wr'], r['n'], r['hold'], r['avg']))
    
    # CB做多 (超卖反弹)
    print(f"\n  --- {tf_name} XAGUSD CB 做多 ---")
    for cb in [3, 4, 5]:
        for rsi in [20, 25, 30]:
            cond = (xag['consecutive_bear']>=cb) & (xag['rsi14']<rsi)
            r = test_pattern(xag, cond, f'XAGUSD {tf_name} LONG CB>={cb}+RSI<{rsi}', hr, 5)
            if r and r['n'] >= 10:
                all_best_findings.append((f"XAGUSD_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))
    
    # Inside Bar + CB + RSI 组合
    print(f"\n  --- {tf_name} XAGUSD InsideBar+组合 ---")
    inside = detect_inside_bar(xag)
    # Inside Bar + 超买做空
    for cb in [2, 3]:
        for rsi in [75, 80]:
            cond = inside & (xag['consecutive_bull']>=cb) & (xag['rsi14']>rsi)
            r = test_pattern(xag, cond, f'XAGUSD {tf_name} InsideBar+CBull>={cb}+RSI>{rsi}', hr, 3, 'short')
            if r and r['n'] >= 5:
                all_best_findings.append((f"XAGUSD_{tf_name}_InsideBar_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))
    # Inside Bar + 超卖做多
    for cb in [2, 3]:
        for rsi in [20, 25]:
            cond = inside & (xag['consecutive_bear']>=cb) & (xag['rsi14']<rsi)
            r = test_pattern(xag, cond, f'XAGUSD {tf_name} InsideBar+CB>={cb}+RSI<{rsi}', hr, 3)
            if r and r['n'] >= 5:
                all_best_findings.append((f"XAGUSD_{tf_name}_InsideBar_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# 02: EURUSD H1 连续阴线做多跨周期验证 (round32发现)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 02 — EURUSD H1/M30 连续阴线做多跨周期验证")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "EURUSD" not in data_store:
        continue
    eu = data_store["EURUSD"]
    hr = list(range(10, 121, 5))
    
    print(f"\n  --- {tf_name} EURUSD CB 做多 ---")
    for cb in [3, 4, 5]:
        for rsi in [20, 25, 30]:
            cond = (eu['consecutive_bear']>=cb) & (eu['rsi14']<rsi)
            r = test_pattern(eu, cond, f'EURUSD {tf_name} LONG CB>={cb}+RSI<{rsi}', hr, 5)
            if r and r['n'] >= 10:
                # 对最佳策略进行Bootstrap和跨周期验证
                best_h = r['hold']
                ow, lo, hi, nb = bootstrap_ci(eu, cond, best_h)
                print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
                periods = cross_period_validation(eu, cond, best_h, 3)
                cp_ok = sum(1 for p in periods if p['wr']>=60)
                print(f"    跨周期验证 (hold={best_h}): {cp_ok}/{len(periods)} 通过")
                for p in periods:
                    m = "✅" if p['wr']>=60 else ("" if p['wr']>=50 else "❌")
                    print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
                all_best_findings.append((f"EURUSD_{tf_name}_LONG_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], best_h, r['avg']))
    
    # MorningStar + RSI
    print(f"\n  --- {tf_name} EURUSD MorningStar/Engulfing ---")
    ms = (eu['open'] - eu['close']).shift(2) > ((eu['high'] - eu['low']).shift(2)) * 0.5  # simplified
    eb = detect_engulfing_bull(eu)
    # EngulfingBull+RSI<30
    cond_eb = eb & (eu['rsi14']<30)
    r = test_pattern(eu, cond_eb, f'EURUSD {tf_name} EngulfingBull+RSI<30', hr, 3)
    if r:
        all_best_findings.append((f"EURUSD_{tf_name}_EngulfingBull_RSI<30", r['wr'], r['n'], r['hold'], r['avg']))
    # RSI回升突破
    cond_rsir = (eu['consecutive_bear']>=2) & eu['rsi14'].between(20, 30) & (eu['rsi14'] < eu['rsi14'].shift(1))
    r = test_pattern(eu, cond_rsir, f'EURUSD {tf_name} CB>=2+RSI20-30+Rising', hr, 3)
    if r:
        all_best_findings.append((f"EURUSD_{tf_name}_CB>=2_RSI20-30_Rising", r['wr'], r['n'], r['hold'], r['avg']))
    
    # 时段细分
    print(f"\n  --- {tf_name} EURUSD 时段细分 CB>=3+RSI<25 ---")
    for sess in ['us', 'europe']:
        cond = (eu['consecutive_bear']>=3) & (eu['rsi14']<25) & (eu['session']==sess)
        r = test_pattern(eu, cond, f'EURUSD {tf_name} CB>=3+RSI<25+{sess}', hr, 3)
        if r and r['n'] >= 5:
            all_best_findings.append((f"EURUSD_{tf_name}_CB>=3_RSI<25_{sess}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# 03: USDJPY H1 做多 月度跟踪 (延续round34)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 03 — USDJPY H1/M30 做多策略月度跟踪")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "USDJPY" not in data_store:
        continue
    uj = data_store["USDJPY"]
    hr_long = list(range(20, 201, 10))
    
    print(f"\n  --- {tf_name} USDJPY CB>=5+RSI<25 (核心) ---")
    cond = (uj['consecutive_bear']>=5) & (uj['rsi14']<25)
    r = test_pattern(uj, cond, f'USDJPY {tf_name} CB>=5+RSI<25', hr_long, 3)
    if r and r['n'] >= 5:
        best_h = r['hold']
        ow, lo, hi, nb = bootstrap_ci(uj, cond, best_h)
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb}, hold={best_h})")
        periods = cross_period_validation(uj, cond, best_h, 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期: {cp_ok}/{len(periods)} 通过")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("⚠️" if p['wr']>=50 else "❌")
            print(f"      P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")
        monthly_tracking(uj, cond, best_h, f'USDJPY {tf_name} CB>=5+RSI<25 hold={best_h} 月度')
        all_best_findings.append((f"USDJPY_{tf_name}_LONG_CB>=5_RSI<25", r['wr'], r['n'], best_h, r['avg']))
    
    # 宽松版
    print(f"\n  --- {tf_name} USDJPY CB>=4+RSI<30 (宽松) ---")
    cond4 = (uj['consecutive_bear']>=4) & (uj['rsi14']<30)
    r4 = test_pattern(uj, cond4, f'USDJPY {tf_name} CB>=4+RSI<30', hr_long, 5)
    if r4 and r4['n'] >= 10:
        ow, lo, hi, nb = bootstrap_ci(uj, cond4, r4['hold'])
        print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb})")
        periods = cross_period_validation(uj, cond4, r4['hold'], 3)
        cp_ok = sum(1 for p in periods if p['wr']>=60)
        print(f"    跨周期: {cp_ok}/{len(periods)} 通过")
        all_best_findings.append((f"USDJPY_{tf_name}_LONG_CB>=4_RSI<30", r4['wr'], r4['n'], r4['hold'], r4['avg']))

# ═══════════════════════════════════════════════════════════════
# 04: H1/M30 全品种快速扫描 — 发现新信号
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🔍 04 — H1/M30 全品种快速扫描 (发现新信号)")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    print(f"\n  --- {tf_name} 全品种CB+RSI扫描 ---")
    hr_short = list(range(1, 31, 2))  # 短线
    hr_med = list(range(30, 151, 10))  # 中线
    
    for sym in sorted(data_store.keys()):
        df = data_store[sym]
        
        # 做多: CB + RSI超卖
        for cb, rsi in [(3,20), (4,20), (3,25), (4,25), (5,25)]:
            cond = (df['consecutive_bear']>=cb) & (df['rsi14']<rsi)
            r = test_pattern(df, cond, f'LONG {sym} {tf_name} CB>={cb}+RSI<{rsi}', hr_med, 3)
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"LONG_{sym}_{tf_name}_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))
        
        # 做空: CBull + RSI超买
        for cb, rsi in [(3,75), (4,75), (4,80), (5,80)]:
            cond = (df['consecutive_bull']>=cb) & (df['rsi14']>rsi)
            r = test_pattern(df, cond, f'SHORT {sym} {tf_name} CBull>={cb}+RSI>{rsi}', hr_med, 3, 'short')
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"SHORT_{sym}_{tf_name}_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))
        
        # 经典形态 + RSI
        inside = detect_inside_bar(df)
        for cond, name, direction in [
            (inside & (df['rsi14']<20), 'InsideBar+RSI<20', 'long'),
            (inside & (df['rsi14']>80), 'InsideBar+RSI>80', 'short'),
        ]:
            r = test_pattern(df, cond, f'{name} {sym} {tf_name}', hr_short + hr_med, 3, direction)
            if r and r['wr'] >= 65:
                all_best_findings.append((f"{direction.upper()}_{sym}_{tf_name}_{name}", r['wr'], r['n'], r['hold'], r['avg']))
        
        # Three Black Crows / Three White Soldiers
        tbc = detect_three_black_crows(df)
        tws = detect_three_white_soldiers(df)
        for cond, name, direction in [
            (tws, 'ThreeWhiteSoldiers', 'long'),   # 三白兵 = 继续看涨
            (tbc, 'ThreeBlackCrows', 'short'),      # 三乌鸦 = 继续看跌
        ]:
            r = test_pattern(df, cond, f'{name} {sym} {tf_name}', hr_short, 3, direction)
            if r and r['wr'] >= 60:
                all_best_findings.append((f"{direction.upper()}_{sym}_{tf_name}_{name}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# 05: XAUUSD H1/M30 — 黄金策略专项
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🥇 05 — XAUUSD H1/M30 黄金策略专项")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "XAUUSD" not in data_store:
        continue
    xu = data_store["XAUUSD"]
    hr = list(range(5, 101, 5))
    
    print(f"\n  --- {tf_name} XAUUSD CB+RSI 做多 ---")
    for cb, rsi in [(3,20), (3,25), (4,20), (4,25), (5,25), (3,30)]:
        cond = (xu['consecutive_bear']>=cb) & (xu['rsi14']<rsi)
        r = test_pattern(xu, cond, f'XAUUSD {tf_name} LONG CB>={cb}+RSI<{rsi}', hr, 3)
        if r and r['n'] >= 5 and r['wr'] >= 65:
            all_best_findings.append((f"LONG_XAUUSD_{tf_name}_CB>={cb}_RSI<{rsi}", r['wr'], r['n'], r['hold'], r['avg']))
    
    print(f"\n  --- {tf_name} XAUUSD CBull+RSI 做空 ---")
    for cb, rsi in [(3,75), (4,75), (4,80), (5,80)]:
        cond = (xu['consecutive_bull']>=cb) & (xu['rsi14']>rsi)
        r = test_pattern(xu, cond, f'XAUUSD {tf_name} SHORT CBull>={cb}+RSI>{rsi}', hr, 3, 'short')
        if r and r['n'] >= 5 and r['wr'] >= 60:
            all_best_findings.append((f"SHORT_XAUUSD_{tf_name}_CBull>={cb}_RSI>{rsi}", r['wr'], r['n'], r['hold'], r['avg']))
    
    # Doji + 时段 + RSI
    print(f"\n  --- {tf_name} XAUUSD Doji组合 ---")
    doji = detect_doji(xu)
    for sess in ['us', 'europe']:
        for rsi_th, direction, dr in [(75, 'short', '>'), (25, 'long', '<')]:
            if direction == 'short':
                cond = doji & (xu['session']==sess) & (xu['rsi14']>rsi_th)
            else:
                cond = doji & (xu['session']==sess) & (xu['rsi14']<rsi_th)
            r = test_pattern(xu, cond, f'XAUUSD {tf_name} Doji+RSI{dr}{rsi_th}+{sess}', hr, 3, direction)
            if r and r['n'] >= 5 and r['wr'] >= 65:
                all_best_findings.append((f"{direction.upper()}_XAUUSD_{tf_name}_Doji_RSI{dr}{rsi_th}_{sess}", r['wr'], r['n'], r['hold'], r['avg']))
    
    # Hammer + RSI
    print(f"\n  --- {tf_name} XAUUSD Hammer ---")
    hammer = detect_hammer(xu)
    for cond, direction, name in [
        (hammer & (xu['rsi14']<25), 'long', 'Hammer+RSI<25'),
        (hammer & (xu['rsi14']>75), 'short', 'Hammer+RSI>75'),
    ]:
        r = test_pattern(xu, cond, f'XAUUSD {tf_name} {name}', hr, 3, direction)
        if r and r['wr'] >= 60:
            all_best_findings.append((f"{direction.upper()}_XAUUSD_{tf_name}_{name}", r['wr'], r['n'], r['hold'], r['avg']))

# ═══════════════════════════════════════════════════════════════
# 06: 跨品种H1/M30信号强度对比 (XAU/XAG/USOIL/EURUSD)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("📊 06 — H1 跨品种信号强度对比")
print(f"{'='*120}")

for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    print(f"\n  --- {tf_name} 做多信号强度 (最佳CB+RSI组合) ---")
    print(f"  {'品种':<10} {'条件':<20} {'n':<6} {'WR':<8} {'hold':<6} {'avg%':<10}")
    print(f"  {'-'*10} {'-'*20} {'-'*6} {'-'*8} {'-'*6} {'-'*10}")
    
    # 统一条件: CB>=3+RSI<25
    for sym in sorted(data_store.keys()):
        df = data_store[sym]
        cond = (df['consecutive_bear']>=3) & (df['rsi14']<25)
        n = cond.sum()
        if n >= 5:
            cnt, wr, avg = get_stats(df, cond, 30)
            print(f"  {sym:<10} {'CB>=3+RSI<25':<20} {cnt:<6} {wr:.1f}%{'':>3} {30:<6} {avg:.3f}%")
    
    print(f"\n  --- {tf_name} 做空信号强度 (最佳CBull+RSI组合) ---")
    print(f"  {'品种':<10} {'条件':<20} {'n':<6} {'WR':<8} {'hold':<6} {'avg%':<10}")
    print(f"  {'-'*10} {'-'*20} {'-'*6} {'-'*8} {'-'*6} {'-'*10}")
    
    for sym in sorted(data_store.keys()):
        df = data_store[sym]
        cond = (df['consecutive_bull']>=3) & (df['rsi14']>75)
        n = cond.sum()
        if n >= 5:
            cnt, wr, avg = get_stats_short(df, cond, 30)
            print(f"  {sym:<10} {'CBull>=3+RSI>75':<20} {cnt:<6} {wr:.1f}%{'':>3} {30:<6} {avg:.3f}%")

# ═══════════════════════════════════════════════════════════════
# 07: HOLD参数敏感性分析 — 对核心XAGUSD策略
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🔬 07 — Hold参数敏感性分析 (XAGUSD M30 CBull>=4+RSI>80)")
print(f"{'='*120}")

if "XAGUSD" in m30_data:
    xag = m30_data["XAGUSD"]
    cond = (xag['consecutive_bull']>=4) & (xag['rsi14']>80)
    hr_sense = list(range(10, 161, 5))
    print(f"\n  Hold敏感性扫描 (CBull>=4+RSI>80):")
    print(f"  {'hold':<8} {'n':<6} {'WR':<8} {'avg%':<10}")
    print(f"  {'-'*8} {'-'*6} {'-'*8} {'-'*10}")
    best_wr, best_hold = 0, 0
    for h in hr_sense:
        cnt, wr, avg = get_stats_short(xag, cond, h)
        if cnt >= 3:
            mark = " ✅" if wr >= 70 else ""
            print(f"  {h:<8} {cnt:<6} {wr:.1f}%{'':>3} {avg:.3f}%{mark}")
            if wr > best_wr:
                best_wr = wr
                best_hold = h
    print(f"\n  最优hold={best_hold} WR={best_wr:.1f}%")
    
    # 跨周期验证最优hold
    if best_hold > 0:
        periods = cross_period_validation(xag, cond, best_hold, 3, 'short')
        print(f"\n  跨周期验证 (hold={best_hold}):")
        for p in periods:
            m = "✅" if p['wr']>=60 else ("" if p['wr']>=50 else "❌")
            print(f"    P{p['period']}: n={p['n']} WR={p['wr']:.1f}% avg={p['avg']:.3f}% {m}")

# ═══════════════════════════════════════════════════════════════
# 08: 跨框架一致性检查
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🔄 08 — H1 vs M30 跨框架一致性检查")
print(f"{'='*120}")

# 对比XAGUSD策略在H1和M30上的表现
print(f"\n  --- XAGUSD CBull>=4+RSI>80 H1 vs M30 ---")
for tf_name, data_store in [("H1", h1_data), ("M30", m30_data)]:
    if "XAGUSD" in data_store:
        df = data_store["XAGUSD"]
        cond = (df['consecutive_bull']>=4) & (df['rsi14']>80)
        hr = list(range(15, 121, 5))
        r = test_pattern(df, cond, f'XAGUSD {tf_name} CBull>=4+RSI>80', hr, 5, 'short')
        if r:
            ow, lo, hi, nb = bootstrap_ci(df, cond, r['hold'], direction='short')
            print(f"    Bootstrap 95% CI: [{lo:.1f}%, {hi:.1f}%] (n={nb})")

# ═══════════════════════════════════════════════════════════════
# 09: 新发现汇总排名
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("🏆 09 — Round 35 最佳发现排名")
print(f"{'='*120}")

if all_best_findings:
    # 去重+排序
    seen = set()
    unique = []
    for item in all_best_findings:
        key = item[0]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    unique.sort(key=lambda x: (-x[1], -x[2]))  # WR降序, n降序
    
    print(f"\n  {'排名':<5} {'策略':<55} {'WR':<8} {'n':<6} {'Hold':<8} {'avg%':<10}")
    print(f"  {'-'*5} {'-'*55} {'-'*8} {'-'*6} {'-'*8} {'-'*10}")
    for i, (name, wr, n, hold, avg) in enumerate(unique, 1):
        if i > 40:  # Top 40
            print(f"  ... 还有 {len(unique)-40} 个发现未显示")
            break
        print(f"  {i:<5} {name:<55} {wr:.1f}%{'':>3} {n:<6} {hold:<8} {avg:.3f}%")
    
    results['best_findings'] = [(n, round(w,1), n_val, h, round(a,3)) for n, w, n_val, h, a in unique]
else:
    print(f"\n  (无可用的最佳发现)")
    results['best_findings'] = []

# ═══════════════════════════════════════════════════════════════
# COMPLETE
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("ROUND 35 COMPLETE")
print(f"完成于: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print(f"下一步: 生成报告 → reports/round35_h1m30_report.md")
print(f"{'='*120}")
