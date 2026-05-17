#!/usr/bin/env python3
"""Round 75 M30快速扫描 - 聚焦最佳条件"""
import sys, os, json
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_data, compute_indicators

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

SYMBOLS = ['XAUUSD','XAGUSD','USTEC','US30','US500','JP225','HK50',
           'USOIL','UKOIL','EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF']

SESSION_MAP = {'asia': (0, 8), 'europe': (8, 16), 'us': (16, 24)}

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

def test_condition(df, cond, label, hold_list, min_sig=3, direction='long'):
    if cond.sum() == 0:
        return None
    entries = df[cond]
    best = None
    for hold in hold_list:
        rets = []
        for idx in entries.index:
            pos = df.index.get_loc(idx)
            if isinstance(pos, slice): pos = pos.start
            exit_pos = pos + hold
            if exit_pos >= len(df): continue
            entry_p = df.iloc[pos]['close']
            exit_p = df.iloc[exit_pos]['close']
            r = (exit_p - entry_p) / entry_p if direction == 'long' else (entry_p - exit_p) / entry_p
            rets.append(r)
        if len(rets) < min_sig: continue
        rets = np.array(rets)
        wr = float((rets > 0).mean())
        avg_ret = float(rets.mean())
        std = float(rets.std()) if rets.std() > 1e-10 else 1e-10
        sharpe = (avg_ret / std) * np.sqrt(len(rets) / hold) if avg_ret != 0 else 0
        if best is None or wr > best[0]:
            best = (wr, hold, len(rets), avg_ret, sharpe, float(rets.min()))
    if best and best[0] >= 0.55 and best[2] >= min_sig:
        return {'label': label, 'wr': best[0], 'hold': best[1], 'n': best[2],
                'avg_ret': best[3], 'sharpe': best[4], 'max_dd': best[5]}
    return None

# M30 focuses on most promising patterns from H1 findings
print("=" * 100)
print(f"M30 快速扫描 (聚焦CB≥4+RSI+Session) — {NOW}")
print("=" * 100)

data = load_data(timeframe='M30', symbols=SYMBOLS)
all_results = []

hold_list = [1, 2, 3, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 120]

for sym in SYMBOLS:
    if sym not in data: continue
    df = data[sym]
    df = compute_indicators(df)
    df = add_session_features(df)
    print(f"\n{sym:<10} {len(df):>5} rows", end="")
    
    sym_results = []
    
    for sess in ['asia', 'europe', 'us']:
        sm = df['session'] == sess
        
        # CB patterns (most promising from H1)
        for cb in [4, 5, 6]:
            cond = sm & (df['consecutive_bear'] >= cb)
            r = test_condition(df, cond, f"{sym} M30 {sess} CB>={cb} 做多", hold_list)
            if r: sym_results.append(f"  CB>={cb} WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']}"); all_results.append(r)
        
        # RSI14 oversold
        for rsi_thresh in [20, 25, 30]:
            cond = sm & (df['rsi14'] < rsi_thresh)
            r = test_condition(df, cond, f"{sym} M30 {sess} rsi14<{rsi_thresh} 做多", hold_list)
            if r: sym_results.append(f"  RSI14<{rsi_thresh} WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']}"); all_results.append(r)
        
        # RSI + CB combo
        for rsi_thresh in [20, 25, 30]:
            for cb in [2, 3, 4]:
                cond = sm & (df['rsi14'] < rsi_thresh) & (df['consecutive_bear'] >= cb)
                r = test_condition(df, cond, f"{sym} M30 {sess} CB>={cb} rsi14<{rsi_thresh} 做多", hold_list)
                if r: sym_results.append(f"  CB>={cb}+RSI14<{rsi_thresh} WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']}"); all_results.append(r)
        
        # RSI7, RSI9 oversold
        for rsi_name in ['rsi7', 'rsi9']:
            if rsi_name not in df.columns: continue
            for rsi_thresh in [20, 25]:
                cond = sm & (df[rsi_name] < rsi_thresh)
                r = test_condition(df, cond, f"{sym} M30 {sess} {rsi_name}<{rsi_thresh} 做多", hold_list)
                if r: sym_results.append(f"  {rsi_name}<{rsi_thresh} WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']}"); all_results.append(r)
        
        # Short: RSI overbought + consecutive_bull
        for rsi_thresh in [70, 75, 80]:
            cond = sm & (df['rsi14'] > rsi_thresh)
            r = test_condition(df, cond, f"{sym} M30 {sess} rsi14>{rsi_thresh} 做空", hold_list, direction='short')
            if r: sym_results.append(f"  RSI14>{rsi_thresh}短 WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']}"); all_results.append(r)
        
        for cb in [3, 4, 5]:
            cond = sm & (df['consecutive_bull'] >= cb)
            r = test_condition(df, cond, f"{sym} M30 {sess} CBull>={cb} 做空", hold_list, direction='short')
            if r: sym_results.append(f"  CBull>={cb}短 WR={r['wr']*100:.1f}% n={r['n']} Hold={r['hold']}"); all_results.append(r)
    
    for s in sym_results[:5]:  # Show top 5 per symbol
        print(f"\n    {s}")

# Rank and save
df_results = pd.DataFrame(all_results)
if len(df_results) > 0:
    df_results['wr_pct'] = df_results['wr'] * 100
    df_results = df_results.sort_values('wr_pct', ascending=False)
    
    print(f"\n\n=== M30 合格模式 (WR≥60%, n≥5) ===")
    qualified = df_results[(df_results['n'] >= 5) & (df_results['wr_pct'] >= 60)]
    print(f"共 {len(qualified)} 个合格模式 / {len(df_results)} 总候选")
    
    if len(qualified) > 0:
        for i, (_, row) in enumerate(qualified.head(30).iterrows()):
            print(f"  {i+1}. {row['label'][:80]} | WR={row['wr_pct']:.1f}% n={int(row['n'])} Hold={int(row['hold'])} AvgRet={row['avg_ret']*100:.3f}% Sharpe={row['sharpe']:.2f}")
    
    # Save
    out = os.path.join(BASE, 'reports', 'round75_m30_raw.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump([{k: (round(float(v), 4) if isinstance(v, float) else v) for k, v in r.items()} for r in all_results if r.get('n', 0) >= 5], f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已保存: {out}")
else:
    print("\n⚠️ 无任何候选模式")

print(f"\n✅ M30扫描完成")
