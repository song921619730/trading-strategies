#!/usr/bin/env python3
"""Debug: Check momentum signal vs next-day return"""
import pandas as pd
import numpy as np
import pickle

SAVE_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v1_user/'

print("Loading data...")
df = pickle.load(open(SAVE_DIR + 'stock_daily.pkl', 'rb'))
for col in ['close', 'pct_chg']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

trade_dates = sorted(df['trade_date'].unique())

# Calculate momentum
df['mom_5'] = df.groupby('ts_code')['close'].pct_change(5)

# Test selection
test_date = pd.Timestamp('2024-01-15')
valid = df[df['trade_date'] == test_date].dropna(subset=['mom_5'])
valid = valid.sort_values('mom_5', ascending=False)
n_select = max(1, int(len(valid) * 0.05))
top_stocks = set(valid.head(n_select)['ts_code'].values)

# Next day
next_date_idx = list(trade_dates).index(test_date) + 1
next_date = trade_dates[next_date_idx]
next_data = df[df['trade_date'] == next_date]

# Top stock next-day returns
top_next = next_data[next_data['ts_code'].isin(top_stocks)]
avg_ret = top_next['pct_chg'].mean() / 100

# All stocks next-day returns
all_next = next_data
all_avg = all_next['pct_chg'].mean() / 100

print(f"Date: {test_date} → Next: {next_date}")
print(f"  Top 5% ({n_select} stocks) avg next-day return: {avg_ret*100:.4f}%")
print(f"  All stocks avg next-day return: {all_avg*100:.4f}%")
print(f"  Excess: {(avg_ret - all_avg)*10000:.2f}bp")

# Now test: does shift(-1) work correctly?
# Pick one top stock
ts = list(top_stocks)[0]
stock_data = df[df['ts_code'] == ts].sort_values('trade_date')
idx = (stock_data['trade_date'] == test_date)
mom_val = stock_data.loc[idx, 'mom_5'].values[0]
close_t = stock_data.loc[idx, 'close'].values[0]

# Next day close
idx_next = (stock_data['trade_date'] == next_date)
close_t1 = stock_data.loc[idx_next, 'close'].values[0]
actual_ret = (close_t1 - close_t) / close_t

print(f"\n  Stock {ts}:")
print(f"    mom_5 = {mom_val:.4f}")
print(f"    close_T = {close_t:.2f}, close_T+1 = {close_t1:.2f}")
print(f"    Actual return = {actual_ret*100:.4f}%")

# Now do a multi-date test: average excess return over many dates
print("\n--- Multi-date test ---")
excess_returns = []
for i in range(100, min(500, len(trade_dates)-1)):
    td = trade_dates[i]
    nd = trade_dates[i+1]
    
    day_data = df[df['trade_date'] == td].dropna(subset=['mom_5'])
    if len(day_data) < 100:
        continue
    day_data = day_data.sort_values('mom_5', ascending=False)
    n_sel = max(1, int(len(day_data) * 0.05))
    top = set(day_data.head(n_sel)['ts_code'].values)
    
    next_day = df[df['trade_date'] == nd]
    top_ret = next_day[next_day['ts_code'].isin(top)]['pct_chg'].mean() / 100
    all_ret = next_day['pct_chg'].mean() / 100
    excess_returns.append(top_ret - all_ret)

excess_arr = np.array(excess_returns)
print(f"  Avg excess return: {excess_arr.mean()*10000:.2f}bp")
print(f"  Std: {excess_arr.std()*10000:.2f}bp")
print(f"  t-stat: {excess_arr.mean() / (excess_arr.std() / np.sqrt(len(excess_arr))):.3f}")
print(f"  Positive: {(excess_arr > 0).sum()}/{len(excess_arr)} ({(excess_arr > 0).mean()*100:.1f}%)")

# What about MOM1?
df['mom_1'] = df.groupby('ts_code')['close'].pct_change(1)
excess_mom1 = []
for i in range(100, min(500, len(trade_dates)-1)):
    td = trade_dates[i]
    nd = trade_dates[i+1]
    day_data = df[df['trade_date'] == td].dropna(subset=['mom_1'])
    if len(day_data) < 100:
        continue
    day_data = day_data.sort_values('mom_1', ascending=False)
    n_sel = max(1, int(len(day_data) * 0.05))
    top = set(day_data.head(n_sel)['ts_code'].values)
    next_day = df[df['trade_date'] == nd]
    top_ret = next_day[next_day['ts_code'].isin(top)]['pct_chg'].mean() / 100
    all_ret = next_day['pct_chg'].mean() / 100
    excess_mom1.append(top_ret - all_ret)

excess_mom1_arr = np.array(excess_mom1)
print(f"\n  MOM1 avg excess return: {excess_mom1_arr.mean()*10000:.2f}bp")
print(f"  MOM1 t-stat: {excess_mom1_arr.mean() / (excess_mom1_arr.std() / np.sqrt(len(excess_mom1_arr))):.3f}")
print(f"  MOM1 positive: {(excess_mom1_arr > 0).sum()}/{len(excess_mom1_arr)}")

print("\n✅ Done")
