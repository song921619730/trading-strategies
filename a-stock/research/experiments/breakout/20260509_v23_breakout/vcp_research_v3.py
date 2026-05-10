#!/usr/bin/env python3
"""
V23 Experiment: VCP (Volatility Contraction Pattern) 主升浪潜伏研究 — SQL加速版

假设: ATR/振幅持续收缩后放量突破，20日收益显著优于基准
VCP定义:
1. ATR_20 降至 ATR_120 的 X% 以下 (波动率收缩)
2. 突破日放量 (量比>1.5) 且涨幅2-5%
3. MA粘合辅助: ma_cv < 0.01
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

print("=" * 60)
print("V23: VCP (波动率收缩模式) 全市场回测 — SQL加速版")
print("=" * 60)

# Step 1: Fetch indicator data from ClickHouse
print("\n[1/5] 拉取全市场指标数据...")
indicator_sql = """
WITH 
daily AS (
    SELECT 
        ts_code, trade_date, 
        toFloat64(high) as high, 
        toFloat64(low) as low, 
        toFloat64(close) as close, 
        toFloat64(vol) as vol, 
        toFloat64(pct_chg) as pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20190601'
),
with_prev AS (
    SELECT *,
        lagInFrame(close, 1) OVER w as prev_close
    FROM daily
    WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
),
with_tr AS (
    SELECT *,
        greatest(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        ) as tr
    FROM with_prev
),
with_atr AS (
    SELECT *,
        avg(tr) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as atr_20,
        avg(tr) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 119 PRECEDING AND CURRENT ROW) as atr_120
    FROM with_tr
),
with_ma AS (
    SELECT *,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as ma5,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as ma10,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as ma20,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) as ma60,
        avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as vol_ma20
    FROM with_atr
),
with_vcp AS (
    SELECT *,
        atr_20 / NULLIF(atr_120, 0) as vcp_ratio,
        vol / NULLIF(vol_ma20, 0) as vol_ratio,
        (ma5 + ma10 + ma20 + ma60) / 4.0 as ma_mean,
        sqrt(
            (power(ma5 - ma_mean, 2) + power(ma10 - ma_mean, 2) + power(ma20 - ma_mean, 2) + power(ma60 - ma_mean, 2)) / 4.0
        ) / NULLIF(close, 0) as ma_cv
    FROM with_ma
)
SELECT 
    ts_code, trade_date, close, pct_chg, vol_ratio, vcp_ratio, ma_cv
FROM with_vcp
WHERE trade_date >= '20200102'
  AND vcp_ratio IS NOT NULL
  AND vol_ratio IS NOT NULL
  AND ma_cv IS NOT NULL
  AND close > 2
  AND vol_ma20 > 0
ORDER BY ts_code, trade_date
"""

print("  执行 SQL 查询...")
df = ch_query(indicator_sql)
print(f"  获取记录数: {len(df)}")

for col in ['close', 'pct_chg', 'vol_ratio', 'vcp_ratio', 'ma_cv']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])

# Step 2: Compute forward returns in pandas (vectorized groupby)
print("\n[2/5] 计算前向收益率 (pandas vectorized)...")
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

for fwd in [5, 10, 20]:
    df[f'fwd_ret_{fwd}'] = df.groupby('ts_code')['close'].shift(-fwd) / df['close'] - 1

# Step 3: Fetch daily_basic
print("\n[3/5] 拉取市值和换手率...")
basic_sql = """
SELECT ts_code, trade_date, 
       toFloat64(turnover_rate) as turnover_rate,
       toFloat64(total_mv) as total_mv
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '20200102'
"""
basic_df = ch_query(basic_sql)
basic_df['trade_date'] = pd.to_datetime(basic_df['trade_date'])
basic_df['turnover_rate'] = pd.to_numeric(basic_df['turnover_rate'], errors='coerce')
basic_df['total_mv'] = pd.to_numeric(basic_df['total_mv'], errors='coerce')

df = df.merge(basic_df, on=['ts_code', 'trade_date'], how='left')
print(f"  合并后记录数: {len(df)}")

# Step 4: Define signals
print("\n[4/5] 识别信号 + 分层分析...")
valid = df.dropna(subset=['vcp_ratio', 'vol_ratio', 'ma_cv'])

vcp_signal = valid[
    (valid['vcp_ratio'] < 0.6) &
    (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
    (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0) &
    (valid['ma_cv'] < 0.01)
].copy()

print(f"  有效样本行数: {len(valid)}")
print(f"  VCP信号总数: {len(vcp_signal)}")

# Helper
def analyze(col, data):
    ret = data[col].dropna()
    if len(ret) == 0:
        return "N/A"
    return f"均收益={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%, 样本={len(ret)}"

print(f"\n{'='*60}")
print("📊 VCP信号整体表现:")
for fwd in [5, 10, 20]:
    print(f"  {fwd}日: {analyze(f'fwd_ret_{fwd}', vcp_signal)}")

print(f"\n📊 全市场基准:")
for fwd in [5, 10, 20]:
    print(f"  {fwd}日: {analyze(f'fwd_ret_{fwd}', valid)}")

print(f"\n📊 VCP Alpha (vs 全市场):")
for fwd in [5, 10, 20]:
    col = f'fwd_ret_{fwd}'
    sig_ret = vcp_signal[col].dropna()
    base_ret = valid[col].dropna()
    if len(sig_ret) > 0 and len(base_ret) > 0:
        print(f"  {fwd}日 Alpha: {(sig_ret.mean() - base_ret.mean())*100:+.2f}%")

# VCP Ratio tiers
print(f"\n📊 VCP Ratio 分层 (VCP+温和突破+MA_CV):")
vcp_base = valid[
    (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
    (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0)
]
for tier_name, tier_cond in [
    ("极收缩 (<0.4)", valid['vcp_ratio'] < 0.4),
    ("强收缩 (0.4-0.5)", (valid['vcp_ratio'] >= 0.4) & (valid['vcp_ratio'] < 0.5)),
    ("中收缩 (0.5-0.6)", (valid['vcp_ratio'] >= 0.5) & (valid['vcp_ratio'] < 0.6)),
]:
    tier = vcp_base[tier_cond]
    if len(tier) >= 10:
        print(f"  {tier_name}: {analyze('fwd_ret_20', tier)}")

# Pure VCP vs VCP+MA_CV
print(f"\n📊 Pure VCP vs VCP+MA_CV 对比:")
pure_vcp = valid[
    (valid['vcp_ratio'] < 0.6) &
    (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
    (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0)
]
print(f"  Pure VCP (无MA粘合): {analyze('fwd_ret_20', pure_vcp)}")
print(f"  VCP+MA_CV (有粘合):  {analyze('fwd_ret_20', vcp_signal)}")

# VCP Ratio threshold sensitivity
print(f"\n📊 VCP Ratio 阈值敏感性:")
for vcp_thresh in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    sig_t = valid[
        (valid['vcp_ratio'] < vcp_thresh) &
        (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
        (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0) &
        (valid['ma_cv'] < 0.01)
    ]
    if len(sig_t) >= 10:
        print(f"  VCP<{vcp_thresh}: {analyze('fwd_ret_20', sig_t)}")

# MA_CV threshold sensitivity
print(f"\n📊 MA_CV 阈值敏感性 (VCP<0.6):")
for ma_thresh in [0.005, 0.01, 0.015, 0.02]:
    sig_m = valid[
        (valid['vcp_ratio'] < 0.6) &
        (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
        (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0) &
        (valid['ma_cv'] < ma_thresh)
    ]
    if len(sig_m) >= 10:
        print(f"  MA_CV<{ma_thresh}: {analyze('fwd_ret_20', sig_m)}")

# Market cap
print(f"\n📊 市值分层:")
sig_mv = vcp_signal.dropna(subset=['total_mv']).copy()
if len(sig_mv) > 50:
    sig_mv['total_mv'] = pd.to_numeric(sig_mv['total_mv'], errors='coerce')
    q1, q3 = sig_mv['total_mv'].quantile(0.25), sig_mv['total_mv'].quantile(0.75)
    for name, cond in [("小盘", sig_mv['total_mv'] < q1),
                        ("中盘", (sig_mv['total_mv'] >= q1) & (sig_mv['total_mv'] <= q3)),
                        ("大盘", sig_mv['total_mv'] > q3)]:
        sub = sig_mv[cond]
        if len(sub) >= 10:
            print(f"  {name}: {analyze('fwd_ret_20', sub)}")

# Turnover
print(f"\n📊 换手率分层:")
sig_turn = vcp_signal.dropna(subset=['turnover_rate']).copy()
if len(sig_turn) > 50:
    sig_turn['turnover_rate'] = pd.to_numeric(sig_turn['turnover_rate'], errors='coerce')
    q1t, q3t = sig_turn['turnover_rate'].quantile(0.25), sig_turn['turnover_rate'].quantile(0.75)
    for name, cond in [("低换手", sig_turn['turnover_rate'] < q1t),
                        ("中换手", (sig_turn['turnover_rate'] >= q1t) & (sig_turn['turnover_rate'] <= q3t)),
                        ("高换手", sig_turn['turnover_rate'] > q3t)]:
        sub = sig_turn[cond]
        if len(sub) >= 10:
            print(f"  {name}: {analyze('fwd_ret_20', sub)}")

# Market regime
print(f"\n📊 市场环境过滤 (沪深300 MA200):")
idx_sql = """
SELECT trade_date, toFloat64(close) as close
FROM tushare.tushare_index_daily FINAL
WHERE ts_code = '000300.SH' AND trade_date >= '20190101'
ORDER BY trade_date
"""
idx_df = ch_query(idx_sql)
idx_df['trade_date'] = pd.to_datetime(idx_df['trade_date'])
idx_df['close'] = pd.to_numeric(idx_df['close'], errors='coerce')
idx_df['ma200'] = idx_df['close'].rolling(200).mean()
idx_df['regime'] = np.where(idx_df['close'] > idx_df['ma200'], 'bull', 'bear')

sig_regime = vcp_signal.merge(idx_df[['trade_date', 'regime']], on='trade_date', how='left')
for regime in ['bull', 'bear']:
    sub = sig_regime[sig_regime['regime'] == regime]
    if len(sub) >= 10:
        print(f"  {regime}: {analyze('fwd_ret_20', sub)}")

# Year-by-year
print(f"\n📊 年度分解:")
sig_year = vcp_signal.copy()
sig_year['year'] = sig_year['trade_date'].dt.year
for year in sorted(sig_year['year'].unique()):
    sub = sig_year[sig_year['year'] == year]
    if len(sub) >= 10:
        print(f"  {year}: {analyze('fwd_ret_20', sub)}")

# VCP-only (no breakout filter) vs VCP+breakout
print(f"\n📊 VCP-only (仅波动率收缩, 无突破确认):")
vcp_only = valid[
    (valid['vcp_ratio'] < 0.5) &
    (valid['ma_cv'] < 0.015)
]
if len(vcp_only) >= 10:
    print(f"  仅VCP收缩: {analyze('fwd_ret_20', vcp_only)}")
    print(f"  VCP+突破:  {analyze('fwd_ret_20', vcp_signal)}")

print("\n" + "=" * 60)
print("V23 VCP 回测完成")
print("=" * 60)

# Save summary
summary = {
    'total_signals': int(len(vcp_signal)),
    'valid_rows': int(len(valid)),
    'data_start': str(df['trade_date'].min()),
    'data_end': str(df['trade_date'].max()),
}
for fwd in [5, 10, 20]:
    col = f'fwd_ret_{fwd}'
    ret = vcp_signal[col].dropna()
    if len(ret) > 0:
        summary[f'fwd_{fwd}_mean'] = round(float(ret.mean() * 100), 3)
        summary[f'fwd_{fwd}_win'] = round(float((ret > 0).mean() * 100), 2)
        summary[f'fwd_{fwd}_median'] = round(float(ret.median() * 100), 3)

with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/breakout/20260509_v23_breakout/results.json', 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print(json.dumps(summary, indent=2, ensure_ascii=False))
