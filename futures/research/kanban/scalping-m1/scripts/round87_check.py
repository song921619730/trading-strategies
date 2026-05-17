#!/usr/bin/env python3
"""Check XAU M1 EU RSI12 CB4 trend and EU CB3+RSI10 latest month"""
import pandas as pd, numpy as np

def compute_indicators(df):
    df = df.copy()
    if 'rsi14' not in df.columns:
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_g = gain.rolling(14, min_periods=14).mean()
        avg_l = loss.rolling(14, min_periods=14).mean()
        rs = avg_g / avg_l.replace(0, np.nan)
        df['rsi14'] = 100.0 - (100.0 / (1.0 + rs))
    if 'consecutive_bear' not in df.columns:
        bear = (df['close'] < df['open']).astype(int)
        c = 0
        result = np.zeros(len(df), dtype=int)
        for i in range(len(df)):
            c = c + 1 if bear.iloc[i] else 0
            result[i] = c
        df['consecutive_bear'] = result
    return df

m1_df = pd.read_parquet('../data/M1/XAUUSD.parquet')
m1_df = m1_df.set_index(pd.to_datetime(m1_df['time'])) if 'time' in m1_df.columns else m1_df
m1_df = m1_df.sort_index()

hour = m1_df.index.hour
m1_df['session'] = 'asia'
m1_df.loc[(hour >= 8) & (hour < 13), 'session'] = 'europe'
m1_df.loc[(hour >= 13) & (hour < 22), 'session'] = 'us'

m1_df = compute_indicators(m1_df)

now = pd.Timestamp('2026-05-14', tz='UTC')

print('\n=== XAU M1 EU CB4+RSI12 第7月跟踪 ===')
print('=' * 50)
mask = (m1_df['session'] == 'europe') & (m1_df['rsi14'] < 12) & (m1_df['consecutive_bear'] >= 4)
signals = m1_df[mask]
print(f'Total historical signals: {len(signals)}')
print(f'Date range: {signals.index[0]} to {signals.index[-1]}')

for months_back in [1, 2, 3, 6]:
    cutoff = (now - pd.DateOffset(months=months_back))
    recent_mask = signals.index >= cutoff
    recent = signals[recent_mask]
    if len(recent) >= 3:
        n_eligible = 0
        wins = 0
        for t in recent.index:
            pos = m1_df.index.get_loc(t)
            exit_pos = pos + 40
            if exit_pos < len(m1_df):
                ret = (m1_df.iloc[exit_pos]['close'] - m1_df.loc[t, 'close']) / m1_df.loc[t, 'close']
                n_eligible += 1
                if ret > 0:
                    wins += 1
        wr = (wins / n_eligible * 100) if n_eligible > 0 else 0
        print(f'  Last {months_back}mo ({cutoff.date()}→): {len(recent)} signals, {n_eligible} eligible, WR={wr:.1f}%')
    else:
        print(f'  Last {months_back}mo: only {len(recent)} signals')

print()
print('=== XAU M1 EU CB3+RSI10 第49月跟踪 ===')
print('=' * 50)
mask2 = (m1_df['session'] == 'europe') & (m1_df['rsi14'] < 10) & (m1_df['consecutive_bear'] >= 3)
signals2 = m1_df[mask2]
print(f'Total historical signals: {len(signals2)}')
print(f'Date range: {signals2.index[0]} to {signals2.index[-1]}')

for hold in [55]:
    for months_back in [1, 2, 3, 6]:
        cutoff = (now - pd.DateOffset(months=months_back))
        recent_mask = signals2.index >= cutoff
        recent = signals2[recent_mask]
        if len(recent) >= 3:
            n_eligible = 0
            wins = 0
            for t in recent.index:
                pos = m1_df.index.get_loc(t)
                exit_pos = pos + hold
                if exit_pos < len(m1_df):
                    ret = (m1_df.iloc[exit_pos]['close'] - m1_df.loc[t, 'close']) / m1_df.loc[t, 'close']
                    n_eligible += 1
                    if ret > 0:
                        wins += 1
            wr = (wins / n_eligible * 100) if n_eligible > 0 else 0
            print(f'  hold={hold}, last {months_back}mo: {len(recent)} signals, {n_eligible} eligible, WR={wr:.1f}%')
        else:
            print(f'  hold={hold}, last {months_back}mo: only {len(recent)} signals')
