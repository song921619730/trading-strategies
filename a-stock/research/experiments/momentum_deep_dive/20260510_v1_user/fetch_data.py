#!/usr/bin/env python3
"""
Step 1: 预取数据并保存为 pickle
"""
import requests
import pandas as pd
import pickle
import time

CK_URL = 'http://172.24.224.1:8123/'
CK_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

SAVE_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v1_user/'

def ck_query(sql, fmt='TabSeparatedWithNames'):
    """Query ClickHouse and return DataFrame"""
    r = requests.get(CK_URL, params={'query': sql + f' FORMAT {fmt}'}, auth=CK_AUTH, timeout=600)
    r.raise_for_status()
    lines = r.text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    data = [line.split('\t') for line in lines[1:]]
    return pd.DataFrame(data, columns=cols)

print("Fetching stock daily data...")
t0 = time.time()
sql = """
SELECT ts_code, trade_date, open, close, high, low, pct_chg, vol, amount
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20190101'
"""
df = ck_query(sql)
print(f"  Stock daily: {len(df):,} rows, {time.time()-t0:.1f}s")

# Convert types
for col in ['open', 'close', 'high', 'low', 'pct_chg', 'vol', 'amount']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])

# Save
with open(SAVE_DIR + 'stock_daily.pkl', 'wb') as f:
    pickle.dump(df, f)
print(f"  Saved stock_daily.pkl ({len(df):,} rows)")

# Index data
print("\nFetching index data...")
sql_idx = """
SELECT ts_code, trade_date, close
FROM tushare.tushare_index_daily FINAL
WHERE trade_date >= '20190101'
AND ts_code IN ('000300.SH', '000905.SH')
"""
df_idx = ck_query(sql_idx)
df_idx['close'] = pd.to_numeric(df_idx['close'], errors='coerce')
df_idx['trade_date'] = pd.to_datetime(df_idx['trade_date'])

with open(SAVE_DIR + 'index_daily.pkl', 'wb') as f:
    pickle.dump(df_idx, f)
print(f"  Saved index_daily.pkl ({len(df_idx):,} rows)")

# Industry data
print("\nFetching industry data...")
sql_ind = """
SELECT ts_code, industry
FROM tushare.tushare_stock_basic FINAL
"""
df_ind = ck_query(sql_ind)
with open(SAVE_DIR + 'stock_industry.pkl', 'wb') as f:
    pickle.dump(df_ind, f)
print(f"  Saved stock_industry.pkl ({len(df_ind):,} rows)")

print("\n✅ Data fetch complete!")
