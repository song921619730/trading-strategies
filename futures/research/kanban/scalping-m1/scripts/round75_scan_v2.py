#!/usr/bin/env python3
"""Round 75 M30 高效扫描 - 向量化版本"""
import sys, os, json, time
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_data, compute_indicators

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW_STR = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
SYMBOLS = ['XAUUSD','XAGUSD','USTEC','US30','US500','JP225','HK50',
           'USOIL','UKOIL','EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF']

# Pre-load & compute all data
print("Loading and computing indicators for all symbols...")
t0 = time.time()
data_h1 = load_data(timeframe='H1', symbols=SYMBOLS)
for sym in SYMBOLS:
    if sym in data_h1:
        data_h1[sym] = compute_indicators(data_h1[sym])
print(f"H1 done: {time.time()-t0:.1f}s")

t0 = time.time()
data_m30 = load_data(timeframe='M30', symbols=SYMBOLS)
for sym in SYMBOLS:
    if sym in data_m30:
        data_m30[sym] = compute_indicators(data_m30[sym])
print(f"M30 done: {time.time()-t0:.1f}s")

def add_session_features(df):
    df = df.copy()
    hour = df.index.hour
    df['session'] = 'asia'
    df.loc[(hour >= 8) & (hour < 16), 'session'] = 'europe'
    df.loc[(hour >= 16), 'session'] = 'us'
    bull = (df['close'] > df['open']).astype(int)
    df['consecutive_bull'] = bull.groupby((bull == 0).cumsum()).cumsum()
    bear = (df['close'] < df['open']).astype(int)
    df['consecutive_bear'] = bear.groupby((bear == 0).cumsum()).cumsum()
    df['hour'] = hour
    return df

def fast_test(df, mask, hold_list, min_sig=3, direction='long'):
    """Vectorized return calculation"""
    n_total = mask.sum()
    if n_total < min_sig:
        return None
    
    entry_idx = df.index[mask]
    entry_prices = df.loc[mask, 'close'].values
    
    results = []
    for hold in hold_list:
        rets = []
        for i in range(len(entry_idx)):
            pos = df.index.get_loc(entry_idx[i])
            if isinstance(pos, slice): pos = pos.start
            exit_pos = pos + hold
            if exit_pos >= len(df): continue
            ep = df.iloc[exit_pos]['close']
            if direction == 'long':
                rets.append((ep - entry_prices[i]) / entry_prices[i])
            else:
                rets.append((entry_prices[i] - ep) / entry_prices[i])
        
        if len(rets) < min_sig: continue
        rets = np.array(rets, dtype=float)
        wr = float((rets > 0).mean())
        avg = float(rets.mean())
        std = float(rets.std()) if rets.std() > 1e-10 else 1e-10
        sharpe = (avg / std) * np.sqrt(len(rets) / hold) if avg != 0 else 0
        results.append((wr, hold, len(rets), avg, sharpe, float(rets.min())))
    
    if not results: return None
    best = max(results, key=lambda x: x[0])
    return best  # (wr, hold, n, avg_ret, sharpe, max_dd)

def scan_timeframe(tf, data, tf_name):
    """Scan one timeframe"""
    print(f"\n{'='*80}")
    print(f"Scanning {tf_name}...")
    
    tf_results = []
    hold_list_H1 = [1,2,3,5,8,10,13,15,20,25,30,40,50,60]
    hold_list_M30 = [1,2,3,5,8,10,12,15,20,25,30,40,50,60,80,100,120]
    hold_list = hold_list_H1 if tf == 'H1' else hold_list_M30
    
    for sym in SYMBOLS:
        if sym not in data: continue
        df = data[sym]
        df = add_session_features(df)
        
        for sess in ['asia', 'europe', 'us']:
            sm = df['session'] == sess
            
            # CB patterns
            for cb in [4, 5, 6]:
                mask = sm & (df['consecutive_bear'] >= cb)
                r = fast_test(df, mask, hold_list, min_sig=3)
                if r and r[0] >= 0.55:
                    tf_results.append({'label': f"{sym} {tf_name} {sess} CB>={cb} 做多", 'wr': r[0], 'hold': r[1], 'n': r[2], 'avg_ret': r[3], 'sharpe': r[4], 'max_dd': r[5]})
            
            # RSI14 oversold
            for th in [20, 25, 30]:
                mask = sm & (df['rsi14'] < th)
                r = fast_test(df, mask, hold_list, min_sig=3)
                if r and r[0] >= 0.55:
                    tf_results.append({'label': f"{sym} {tf_name} {sess} rsi14<{th} 做多", 'wr': r[0], 'hold': r[1], 'n': r[2], 'avg_ret': r[3], 'sharpe': r[4], 'max_dd': r[5]})
            
            # RSI14 + CB combo
            for th in [20, 25, 30]:
                for cb in [2, 3, 4]:
                    mask = sm & (df['rsi14'] < th) & (df['consecutive_bear'] >= cb)
                    r = fast_test(df, mask, hold_list, min_sig=3)
                    if r and r[0] >= 0.55:
                        tf_results.append({'label': f"{sym} {tf_name} {sess} CB>={cb}+rsi14<{th} 做多", 'wr': r[0], 'hold': r[1], 'n': r[2], 'avg_ret': r[3], 'sharpe': r[4], 'max_dd': r[5]})
            
            # RSI short
            for th in [70, 75, 80]:
                mask = sm & (df['rsi14'] > th)
                r = fast_test(df, mask, hold_list, min_sig=3, direction='short')
                if r and r[0] >= 0.55:
                    tf_results.append({'label': f"{sym} {tf_name} {sess} rsi14>{th} 做空", 'wr': r[0], 'hold': r[1], 'n': r[2], 'avg_ret': r[3], 'sharpe': r[4], 'max_dd': r[5]})
            
            # ASIA/EU specific: hour-based patterns
            if sess == 'asia':
                for h in [0, 1, 2, 3]:
                    mask = sm & (df['hour'] == h) & (df['rsi14'] < 30)
                    r = fast_test(df, mask, hold_list, min_sig=3)
                    if r and r[0] >= 0.55:
                        tf_results.append({'label': f"{sym} {tf_name} ASIA {h}:00 rsi14<30 做多", 'wr': r[0], 'hold': r[1], 'n': r[2], 'avg_ret': r[3], 'sharpe': r[4], 'max_dd': r[5]})
            
            if sess == 'europe':
                for h in [8, 9]:
                    mask = sm & (df['hour'] == h) & (df['rsi14'] < 30)
                    r = fast_test(df, mask, hold_list, min_sig=3)
                    if r and r[0] >= 0.55:
                        tf_results.append({'label': f"{sym} {tf_name} EU {h}:00 rsi14<30 做多", 'wr': r[0], 'hold': r[1], 'n': r[2], 'avg_ret': r[3], 'sharpe': r[4], 'max_dd': r[5]})
    
    print(f"  Found {len(tf_results)} candidates")
    df_r = pd.DataFrame(tf_results)
    if len(df_r) > 0:
        df_r['wr_pct'] = df_r['wr'] * 100
        # Filter
        qual = df_r[(df_r['n'] >= 5) & (df_r['wr_pct'] >= 60)].sort_values('wr_pct', ascending=False)
        print(f"  Qualified (WR≥60%, n≥5): {len(qual)}")
        return df_r, qual
    return df_r, pd.DataFrame()

# Run scans
h1_all, h1_qual = scan_timeframe('H1', data_h1, 'H1')
m30_all, m30_qual = scan_timeframe('M30', data_m30, 'M30')

# Print results
print(f"\n{'='*80}")
print(f"H1 最佳模式 (WR≥60%, n≥5)")
print(f"{'='*80}")
if len(h1_qual) > 0:
    for i, (_, row) in enumerate(h1_qual.head(40).iterrows()):
        print(f"  {i+1:2d}. {row['label'][:80]:80s} | WR={row['wr_pct']:.1f}% n={int(row['n'])} Hold={int(row['hold'])} AvgRet={row['avg_ret']*100:.3f}%")

print(f"\n{'='*80}")
print(f"M30 最佳模式 (WR≥60%, n≥5)")
print(f"{'='*80}")
if len(m30_qual) > 0:
    for i, (_, row) in enumerate(m30_qual.head(40).iterrows()):
        print(f"  {i+1:2d}. {row['label'][:80]:80s} | WR={row['wr_pct']:.1f}% n={int(row['n'])} Hold={int(row['hold'])} AvgRet={row['avg_ret']*100:.3f}%")

# EU/ASIA focused analysis
print(f"\n{'='*80}")
print(f"欧盘(EU)专题")
print(f"{'='*80}")
for tf_name, qual in [('H1', h1_qual), ('M30', m30_qual)]:
    eu = qual[qual['label'].str.contains('europe', case=False, na=False)].head(10)
    if len(eu) > 0:
        print(f"\n  {tf_name} 欧盘最佳:")
        for _, row in eu.iterrows():
            print(f"    {row['label'][:85]} | WR={row['wr_pct']:.1f}% n={int(row['n'])} Hold={int(row['hold'])}")

print(f"\n{'='*80}")
print(f"亚盘(ASIA)专题")
print(f"{'='*80}")
for tf_name, qual in [('H1', h1_qual), ('M30', m30_qual)]:
    asia = qual[qual['label'].str.contains('asia', case=False, na=False)].head(10)
    if len(asia) > 0:
        print(f"\n  {tf_name} 亚盘最佳:")
        for _, row in asia.iterrows():
            print(f"    {row['label'][:85]} | WR={row['wr_pct']:.1f}% n={int(row['n'])} Hold={int(row['hold'])}")

# Save report  
report = []
report.append(f"# Round 75 — H1/M30 欧盘/亚盘模式研究报告\n")
report.append(f"生成时间: {NOW_STR}\n")
report.append(f"\n## H1 合格模式 (n≥5, WR≥60%)\n")
if len(h1_qual) > 0:
    for _, row in h1_qual.iterrows():
        report.append(f"- {row['label']} | WR={row['wr_pct']:.1f}% n={int(row['n'])} Hold={int(row['hold'])} AvgRet={row['avg_ret']*100:.3f}% Sharpe={row['sharpe']:.2f}\n")

report.append(f"\n## M30 合格模式 (n≥5, WR≥60%)\n")
if len(m30_qual) > 0:
    for _, row in m30_qual.iterrows():
        report.append(f"- {row['label']} | WR={row['wr_pct']:.1f}% n={int(row['n'])} Hold={int(row['hold'])} AvgRet={row['avg_ret']*100:.3f}% Sharpe={row['sharpe']:.2f}\n")

report.append(f"\n## 欧盘专题\n")
for tf_name, qual in [('H1', h1_qual), ('M30', m30_qual)]:
    eu = qual[qual['label'].str.contains('europe', case=False, na=False)]
    report.append(f"\n### {tf_name} 欧盘\n")
    for _, row in eu.iterrows():
        report.append(f"- {row['label']} | WR={row['wr_pct']:.1f}% n={int(row['n'])}\n")

report.append(f"\n## 亚盘专题\n")
for tf_name, qual in [('H1', h1_qual), ('M30', m30_qual)]:
    asia = qual[qual['label'].str.contains('asia', case=False, na=False)]
    report.append(f"\n### {tf_name} 亚盘\n")
    for _, row in asia.iterrows():
        report.append(f"- {row['label']} | WR={row['wr_pct']:.1f}% n={int(row['n'])}\n")

report_path = os.path.join(BASE, 'reports', 'round75_h1m30_report.txt')
with open(report_path, 'w', encoding='utf-8') as f:
    f.writelines(report)
print(f"\n✅ 报告已保存: {report_path}")

# Save JSON data
json_out = os.path.join(BASE, 'reports', 'round75_h1m30_data.json')
output_data = {
    'timestamp': NOW_STR,
    'round': 75,
    'focus': 'H1/M30 欧盘/亚盘模式研究',
    'H1_count': len(h1_qual),
    'M30_count': len(m30_qual),
    'H1_top10': [{'label': r['label'], 'wr': round(r['wr_pct'], 1), 'n': int(r['n']), 'hold': int(r['hold']), 'avg_ret_pct': round(r['avg_ret']*100, 3), 'sharpe': round(r['sharpe'], 2)} for _, r in h1_qual.head(10).iterrows()] if len(h1_qual) > 0 else [],
    'M30_top10': [{'label': r['label'], 'wr': round(r['wr_pct'], 1), 'n': int(r['n']), 'hold': int(r['hold']), 'avg_ret_pct': round(r['avg_ret']*100, 3), 'sharpe': round(r['sharpe'], 2)} for _, r in m30_qual.head(10).iterrows()] if len(m30_qual) > 0 else [],
}
with open(json_out, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)
print(f"✅ 数据已保存: {json_out}")
