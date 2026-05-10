#!/usr/bin/env python3
"""
V19 (续): 空方力量衰竭 + 机构资金流共振研究

V18结论: 衰竭信号统计显著但胜率<50%
V19假设: 衰竭信号 + 机构资金流入 = 共振信号, 胜率可提升
"""

import requests
import pandas as pd
import numpy as np
import json

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(sql, fmt='TabSeparatedWithNames'):
    full_sql = f"{sql} FORMAT {fmt}"
    r = requests.get(CH_URL, params={'query': full_sql}, auth=CH_AUTH, timeout=120)
    r.raise_for_status()
    lines = r.text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    rows = [line.split('\t') for line in lines[1:]]
    return pd.DataFrame(rows, columns=cols)

def analyze(col, data):
    ret = pd.to_numeric(data[col], errors='coerce').dropna()
    if len(ret) == 0:
        return "N/A"
    return f"均收益={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%, 样本={len(ret)}"

print("=" * 60)
print("V19: 空方力量衰竭 + 机构资金流共振")
print("=" * 60)

# Sample approach: get a representative sample of stocks
# First get all stock codes, then sample
print("\n[1/5] 获取股票列表 (抽样2000只)...")
codes_df = ch_query("SELECT DISTINCT ts_code FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= '20200102'")
all_codes = codes_df['ts_code'].tolist()
np.random.seed(42)
sample_codes = np.random.choice(all_codes, size=min(2000, len(all_codes)), replace=False).tolist()

code_list = "','".join(sample_codes)

# Fetch daily data for sample
print(f"\n[2/5] 拉取{len(sample_codes)}只股票日线数据...")
daily_sql = f"""
SELECT ts_code, trade_date,
       toFloat64(open) as open, toFloat64(high) as high,
       toFloat64(low) as low, toFloat64(close) as close,
       toFloat64(vol) as vol, toFloat64(pct_chg) as pct_chg
FROM tushare.tushare_stock_daily FINAL
WHERE ts_code IN ('{code_list}')
  AND trade_date >= '20190601'
ORDER BY ts_code, trade_date
"""
daily_df = ch_query(daily_sql)
print(f"  记录数: {len(daily_df)}")

daily_df['trade_date'] = pd.to_datetime(daily_df['trade_date'])
for col in ['open', 'high', 'low', 'close', 'vol', 'pct_chg']:
    daily_df[col] = pd.to_numeric(daily_df[col], errors='coerce')

# Compute indicators per stock
print("\n[3/5] 计算指标...")
daily_df = daily_df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

# Volume MA and ratio
daily_df['vol_ma20'] = daily_df.groupby('ts_code')['vol'].transform(lambda x: x.rolling(20, min_periods=10).mean())
daily_df['vol_ratio'] = daily_df['vol'] / daily_df['vol_ma20']

# 3-day shrink detection (vectorized)
daily_df['vol_1'] = daily_df.groupby('ts_code')['vol'].shift(1)
daily_df['vol_2'] = daily_df.groupby('ts_code')['vol'].shift(2)
daily_df['vol_3'] = daily_df.groupby('ts_code')['vol'].shift(3)
daily_df['vol_ma20_1'] = daily_df.groupby('ts_code')['vol_ma20'].shift(1)
daily_df['vol_ma20_2'] = daily_df.groupby('ts_code')['vol_ma20'].shift(2)
daily_df['vol_ma20_3'] = daily_df.groupby('ts_code')['vol_ma20'].shift(3)

daily_df['shrink_3d'] = (
    (daily_df['vol_1'] < daily_df['vol_ma20_1']) &
    (daily_df['vol_2'] < daily_df['vol_ma20_2']) &
    (daily_df['vol_3'] < daily_df['vol_ma20_3'])
)

# Price position (60-day)
daily_df['low_60'] = daily_df.groupby('ts_code')['low'].transform(lambda x: x.rolling(60, min_periods=30).min())
daily_df['high_60'] = daily_df.groupby('ts_code')['high'].transform(lambda x: x.rolling(60, min_periods=30).max())
daily_df['price_position'] = (daily_df['close'] - daily_df['low_60']) / (daily_df['high_60'] - daily_df['low_60'])

# Forward returns
for fwd in [1, 3, 5]:
    daily_df[f'fwd_ret_{fwd}'] = daily_df.groupby('ts_code')['close'].shift(-fwd) / daily_df['close'] - 1

# Filter valid
valid = daily_df[daily_df['vol_ma20'] > 0].copy()

# Define base signal
base_signal = valid[
    valid['shrink_3d'] &
    (valid['vol_ratio'] > 1.5) &
    (valid['pct_chg'] > 0)
].copy()
print(f"  H1 (3日缩量+放量收阳): {len(base_signal)} 信号")

# Step 4: Fetch moneyflow for sample
print(f"\n[4/5] 拉取资金流向...")
mf_sql = f"""
SELECT ts_code, trade_date,
       toFloat64(buy_lg_vol) - toFloat64(sell_lg_vol) + toFloat64(buy_elg_vol) - toFloat64(sell_elg_vol) as net_super
FROM tushare.tushare_moneyflow FINAL
WHERE ts_code IN ('{code_list}')
  AND trade_date >= '20200102'
"""
mf_df = ch_query(mf_sql)
mf_df['trade_date'] = pd.to_datetime(mf_df['trade_date'])
mf_df['net_super'] = pd.to_numeric(mf_df['net_super'], errors='coerce')

base_signal = base_signal.merge(mf_df, on=['ts_code', 'trade_date'], how='left')

# Market cap
mv_sql = f"""
SELECT ts_code, trade_date, toFloat64(total_mv) as total_mv
FROM tushare.tushare_daily_basic FINAL
WHERE ts_code IN ('{code_list}')
  AND trade_date >= '20200102'
"""
mv_df = ch_query(mv_sql)
mv_df['trade_date'] = pd.to_datetime(mv_df['trade_date'])
mv_df['total_mv'] = pd.to_numeric(mv_df['total_mv'], errors='coerce')
base_signal = base_signal.merge(mv_df, on=['ts_code', 'trade_date'], how='left')

# Step 5: Analysis
print("\n[5/5] 信号分析...")
print(f"\n{'='*60}")

# Baseline
print(f"  H1 (3日缩量+放量收阳): {len(base_signal)} 信号")
for fwd in [1, 3, 5]:
    print(f"    {fwd}日: {analyze(f'fwd_ret_{fwd}', base_signal)}")

# + Moneyflow
mf_pos = base_signal[base_signal['net_super'] > 0].copy()
print(f"\n  H1 + 超大单净流入: {len(mf_pos)} 信号")
for fwd in [1, 3, 5]:
    print(f"    {fwd}日: {analyze(f'fwd_ret_{fwd}', mf_pos)}")

mf_neg = base_signal[(base_signal['net_super'] <= 0) | base_signal['net_super'].isna()].copy()
print(f"  H1 + 超大单非净流入: {len(mf_neg)} 信号")
for fwd in [1, 3, 5]:
    print(f"    {fwd}日: {analyze(f'fwd_ret_{fwd}', mf_neg)}")

# + Bottom
bottom = base_signal[base_signal['price_position'] < 0.15].copy()
print(f"\n  H1 + 底部15%: {len(bottom)} 信号")
for fwd in [1, 3, 5]:
    print(f"    {fwd}日: {analyze(f'fwd_ret_{fwd}', bottom)}")

# Combo
combo = base_signal[
    (base_signal['net_super'] > 0) &
    (base_signal['price_position'] < 0.15)
].copy()
print(f"\n  H1 + 超大单 + 底部: {len(combo)} 信号")
if len(combo) > 5:
    for fwd in [1, 3, 5]:
        print(f"    {fwd}日: {analyze(f'fwd_ret_{fwd}', combo)}")

# Market cap
print(f"\n  📊 市值分层:")
sig_mv = base_signal.dropna(subset=['total_mv']).copy()
if len(sig_mv) > 20:
    q1, q3 = sig_mv['total_mv'].quantile(0.25), sig_mv['total_mv'].quantile(0.75)
    for name, cond in [("小盘", sig_mv['total_mv'] < q1), ("中盘", (sig_mv['total_mv'] >= q1) & (sig_mv['total_mv'] <= q3)), ("大盘", sig_mv['total_mv'] > q3)]:
        sub = sig_mv[cond]
        if len(sub) >= 5:
            print(f"    {name}: {analyze('fwd_ret_3', sub)}")

# Environment
print(f"\n  📊 牛熊过滤:")
idx_sql = """
SELECT trade_date, toFloat64(close) as close
FROM tushare.tushare_index_daily FINAL
WHERE ts_code = '000300.SH' AND trade_date >= '20190101'
ORDER BY trade_date
"""
idx_df = ch_query(idx_sql)
idx_df['trade_date'] = pd.to_datetime(idx_df['trade_date'])
idx_df['close'] = pd.to_numeric(idx_df['close'], errors='coerce')
idx_df['ma60'] = idx_df['close'].rolling(60).mean()
idx_df['regime'] = np.where(idx_df['close'] > idx_df['ma60'], 'bull', 'bear')

sig_regime = base_signal.merge(idx_df[['trade_date', 'regime']], on='trade_date', how='left')
for regime in ['bull', 'bear']:
    sub = sig_regime[sig_regime['regime'] == regime]
    if len(sub) >= 5:
        print(f"    {regime}: {analyze('fwd_ret_3', sub)}")

print("\n" + "=" * 60)
print("V19 回测完成")
print("=" * 60)

summary = {
    'base_signals': len(base_signal),
    'mf_pos': len(mf_pos),
    'bottom': len(bottom),
    'combo': len(combo),
    'sample_stocks': len(sample_codes),
}
for prefix, sig in [('base', base_signal), ('mf', mf_pos), ('bottom', bottom), ('combo', combo)]:
    for fwd in [1, 3, 5]:
        col = f'fwd_ret_{fwd}'
        ret = pd.to_numeric(sig[col], errors='coerce').dropna()
        if len(ret) > 0:
            summary[f'{prefix}_{fwd}d_mean'] = round(float(ret.mean() * 100), 3)
            summary[f'{prefix}_{fwd}d_win'] = round(float((ret > 0).mean() * 100), 2)

with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/exhaustion/20260509_v19_exhaustion/results.json', 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print(json.dumps(summary, indent=2, ensure_ascii=False))
