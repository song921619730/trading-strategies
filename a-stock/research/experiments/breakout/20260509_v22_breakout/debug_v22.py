#!/usr/bin/env python3
"""Debug: Check intermediate values for a few stocks"""
import requests
import pandas as pd

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(sql):
    r = requests.get(CH_URL, params={'query': sql}, auth=CH_AUTH, timeout=60)
    r.raise_for_status()
    lines = r.text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    data = [line.split('\t') for line in lines[1:]]
    df = pd.DataFrame(data, columns=cols)
    return df

# Get one stock's data
sql = """
SELECT d.ts_code, d.trade_date, d.open, d.high, d.low, d.close, d.vol, d.pct_chg,
       b.total_mv, b.pe_ttm, b.pb, b.turnover_rate
FROM tushare.tushare_stock_daily d
INNER JOIN tushare.tushare_daily_basic b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE d.ts_code = '000001.SZ' AND d.trade_date >= '20240101'
ORDER BY d.trade_date
FORMAT TabSeparatedWithNames
"""
df = ch_query(sql)
print(f"Rows: {len(df)}")
print(df.head(3))

for c in ['open','high','low','close','vol','pct_chg','total_mv','pe_ttm','pb','turnover_rate']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])

# Compute indicators
df['ma5'] = df['close'].rolling(5).mean()
df['ma10'] = df['close'].rolling(10).mean()
df['ma20'] = df['close'].rolling(20).mean()
df['ma60'] = df['close'].rolling(60).mean()

ma_cols = ['ma5','ma10','ma20','ma60']
df['ma_cv'] = df[ma_cols].std(axis=1) / df[ma_cols].mean(axis=1)
df['ma_cv_10'] = df['ma_cv'].rolling(10).mean()

high_low = df['high'] - df['low']
high_close = (df['high'] - df['close'].shift(1)).abs()
low_close = (df['low'] - df['close'].shift(1)).abs()
tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df['atr'] = tr.rolling(14).mean()
df['atr_pct'] = df['atr'] / df['close']

df['vol_ma20'] = df['vol'].rolling(20).mean()
df['vol_ratio'] = df['vol'] / df['vol_ma20']

# Check conditions
print(f"\npe_ttm > 0: {(df['pe_ttm'] > 0).sum()}")
print(f"total_mv >= 30B: {(df['total_mv'] >= 30e9).sum()}")
print(f"ma_cv_10 < 0.02: {(df['ma_cv_10'] < 0.02).sum()}")
print(f"atr_pct < 0.025: {(df['atr_pct'] < 0.025).sum()}")
print(f"vol_ratio > 1.5: {(df['vol_ratio'] > 1.5).sum()}")
print(f"pct_chg > 2.0: {(df['pct_chg'] > 2.0).sum()}")
print(f"close > ma60: {(df['close'] > df['ma60']).sum()}")

# Combined
cond = (
    (df['ma_cv_10'] < 0.02) &
    (df['atr_pct'] < 0.025) &
    (df['vol_ratio'] > 1.5) &
    (df['pct_chg'] > 2.0) &
    (df['close'] > df['ma60']) &
    (df['pe_ttm'] > 0) &
    (df['total_mv'] >= 30e9)
)
print(f"\nCombined signals: {cond.sum()}")

# Show recent values
print("\nRecent rows:")
cols_show = ['trade_date','close','ma5','ma10','ma20','ma60','ma_cv_10','atr_pct','vol_ratio','pct_chg','pe_ttm','total_mv']
print(df[cols_show].tail(10).to_string())
