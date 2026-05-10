#!/usr/bin/env python3
"""
V19 (续): 空方力量衰竭 + 机构资金流共振研究 — SQL加速版

V18结论: 衰竭信号统计显著但胜率<50%
V19假设: 衰竭信号 + 机构资金流入(超大单净买入) = 共振信号
"""

import requests
import pandas as pd
import numpy as np
import json

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(sql, fmt='TabSeparatedWithNames'):
    full_sql = f"{sql} FORMAT {fmt}"
    r = requests.get(CH_URL, params={'query': full_sql}, auth=CH_AUTH, timeout=180)
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
print("V19: 空方力量衰竭 + 机构资金流共振 — SQL加速版")
print("=" * 60)

# Step 1: Fetch exhaustion signals via SQL
print("\n[1/4] 拉取衰竭信号 (SQL)...")

exhaustion_sql = """
WITH
daily AS (
    SELECT ts_code, trade_date,
        toFloat64(open) as open, toFloat64(high) as high,
        toFloat64(low) as low, toFloat64(close) as close,
        toFloat64(vol) as vol, toFloat64(pct_chg) as pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20190601'
),
with_vol AS (
    SELECT *,
        avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as vol_ma20,
        lagInFrame(vol, 1) OVER w as vol_1,
        lagInFrame(vol, 2) OVER w as vol_2,
        lagInFrame(vol, 3) OVER w as vol_3,
        lagInFrame(vol_ma20, 1) OVER w as vol_ma20_1,
        lagInFrame(vol_ma20, 2) OVER w as vol_ma20_2,
        lagInFrame(vol_ma20, 3) OVER w as vol_ma20_3
    FROM daily
    WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
),
with_shrink AS (
    SELECT *,
        (vol_1 < vol_ma20_1 AND vol_2 < vol_ma20_2 AND vol_3 < vol_ma20_3) as shrink_3d,
        vol / NULLIF(vol_ma20, 0) as vol_ratio,
        greatest(low, open, close) as dummy
    FROM with_vol
),
with_low AS (
    SELECT *,
        min(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) as low_60,
        max(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) as high_60
    FROM with_shrink
),
with_pos AS (
    SELECT *,
        (close - low_60) / NULLIF(high_60 - low_60, 0) as price_position
    FROM with_low
)
SELECT ts_code, trade_date, close, pct_chg, vol_ratio, shrink_3d, price_position
FROM with_pos
WHERE trade_date >= '20200102'
  AND vol_ma20 > 0
  AND shrink_3d IS NOT NULL
  AND vol_ratio IS NOT NULL
  AND price_position IS NOT NULL
ORDER BY ts_code, trade_date
"""

df = ch_query(exhaustion_sql)
print(f"  有效记录: {len(df)}")
df['close'] = pd.to_numeric(df['close'], errors='coerce')
df['pct_chg'] = pd.to_numeric(df['pct_chg'], errors='coerce')
df['vol_ratio'] = pd.to_numeric(df['vol_ratio'], errors='coerce')
df['shrink_3d'] = df['shrink_3d'].isin(['1', 'True', 'true', '1.0'])
df['price_position'] = pd.to_numeric(df['price_position'], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])

# Compute forward returns
print("\n[2/4] 计算前向收益率...")
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)
for fwd in [1, 3, 5]:
    df[f'fwd_ret_{fwd}'] = df.groupby('ts_code')['close'].shift(-fwd) / df['close'] - 1

# Define signals
base_signal = df[
    df['shrink_3d'] &
    (df['vol_ratio'] > 1.5) &
    (df['pct_chg'] > 0)
].copy()
print(f"  H1 (3日缩量+放量收阳): {len(base_signal)} 信号")

# Step 3: Fetch moneyflow
print("\n[3/4] 拉取资金流向...")
mf_sql = """
SELECT ts_code, trade_date,
       toFloat64(buy_lg_vol) - toFloat64(sell_lg_vol) + toFloat64(buy_elg_vol) - toFloat64(sell_elg_vol) as net_super
FROM tushare.tushare_moneyflow FINAL
WHERE trade_date >= '20200102'
"""
mf_df = ch_query(mf_sql)
mf_df['trade_date'] = pd.to_datetime(mf_df['trade_date'])
mf_df['net_super'] = pd.to_numeric(mf_df['net_super'], errors='coerce')

base_signal = base_signal.merge(mf_df, on=['ts_code', 'trade_date'], how='left')

# Fetch market cap
mv_sql = """
SELECT ts_code, trade_date, toFloat64(total_mv) as total_mv
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '20200102'
"""
mv_df = ch_query(mv_sql)
mv_df['trade_date'] = pd.to_datetime(mv_df['trade_date'])
mv_df['total_mv'] = pd.to_numeric(mv_df['total_mv'], errors='coerce')
base_signal = base_signal.merge(mv_df, on=['ts_code', 'trade_date'], how='left')

# Step 4: Analysis
print("\n[4/4] 信号分析...")
print(f"\n{'='*60}")

# H1 baseline
print(f"  H1 (3日缩量+放量收阳): {len(base_signal)} 信号")
for fwd in [1, 3, 5]:
    print(f"    {fwd}日: {analyze(f'fwd_ret_{fwd}', base_signal)}")

# + Moneyflow
mf_pos = base_signal[base_signal['net_super'] > 0].copy()
print(f"\n  H1 + 超大单净流入: {len(mf_pos)} 信号")
for fwd in [1, 3, 5]:
    print(f"    {fwd}日: {analyze(f'fwd_ret_{fwd}', mf_pos)}")

mf_neg = base_signal[base_signal['net_super'] <= 0].copy()
print(f"  H1 + 超大单净流出: {len(mf_neg)} 信号")
for fwd in [1, 3, 5]:
    print(f"    {fwd}日: {analyze(f'fwd_ret_{fwd}', mf_neg)}")

# + Bottom area
bottom = base_signal[base_signal['price_position'] < 0.15].copy()
print(f"\n  H1 + 底部15%: {len(bottom)} 信号")
for fwd in [1, 3, 5]:
    print(f"    {fwd}日: {analyze(f'fwd_ret_{fwd}', bottom)}")

# + Moneyflow + Bottom
combo = base_signal[
    (base_signal['net_super'] > 0) &
    (base_signal['price_position'] < 0.15)
].copy()
print(f"\n  H1 + 超大单 + 底部: {len(combo)} 信号")
for fwd in [1, 3, 5]:
    print(f"    {fwd}日: {analyze(f'fwd_ret_{fwd}', combo)}")

# Market cap
print(f"\n  📊 市值分层:")
sig_mv = base_signal.dropna(subset=['total_mv']).copy()
if len(sig_mv) > 50:
    q1, q3 = sig_mv['total_mv'].quantile(0.25), sig_mv['total_mv'].quantile(0.75)
    for name, cond in [("小盘", sig_mv['total_mv'] < q1), ("中盘", (sig_mv['total_mv'] >= q1) & (sig_mv['total_mv'] <= q3)), ("大盘", sig_mv['total_mv'] > q3)]:
        sub = sig_mv[cond]
        if len(sub) >= 10:
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
    if len(sub) >= 10:
        print(f"    {regime}: {analyze('fwd_ret_3', sub)}")

print("\n" + "=" * 60)
print("V19 回测完成")
print("=" * 60)

summary = {
    'base_signals': len(base_signal),
    'mf_pos_signals': len(mf_pos),
    'bottom_signals': len(bottom),
    'combo_signals': len(combo),
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
