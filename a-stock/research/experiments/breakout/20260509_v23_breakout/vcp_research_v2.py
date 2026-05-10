#!/usr/bin/env python3
"""
V23 Experiment: VCP (Volatility Contraction Pattern) 主升浪潜伏研究 — SQL加速版

假设: ATR/振幅持续收缩后放量突破，20日收益显著优于基准
不同于V22的均线粘合(MA_CV)，VCP关注价格波动率的收敛程度

VCP定义:
1. ATR_20 降至 ATR_120 的 X% 以下 (波动率收缩)
2. 突破日放量 (量比>1.5) 且涨幅2-5% (V22验证温和突破最优)
3. MA粘合辅助: ma_cv < 0.01

用 ClickHouse SQL 计算指标，避免 Python 循环遍历5000+只股票
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime
import json

# ClickHouse config
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

def ch_exec(sql):
    """Execute without returning results"""
    r = requests.get(CH_URL, params={'query': sql}, auth=CH_AUTH, timeout=120)
    r.raise_for_status()

print("=" * 60)
print("V23: VCP (波动率收缩模式) 全市场回测 — SQL加速版")
print("=" * 60)

# Step 1: Use ClickHouse to compute all indicators via window functions
print("\n[1/4] 使用 ClickHouse 计算全市场指标 (ATR, MA, VCP ratio)...")

# Compute daily data with indicators using ClickHouse window functions
indicator_sql = """
WITH 
daily AS (
    SELECT 
        ts_code, trade_date, 
        toFloat64(open) as open, 
        toFloat64(high) as high, 
        toFloat64(low) as low, 
        toFloat64(close) as close, 
        toFloat64(vol) as vol, 
        toFloat64(pct_chg) as pct_chg,
        toFloat64(amount) as amount
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20190601'
),
with_prev AS (
    SELECT *,
        lagInFrame(close, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) as prev_close
    FROM daily
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
with_range AS (
    SELECT *,
        (max(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) -
         min(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
        ) / close as range_20
    FROM with_ma
),
with_vcp AS (
    SELECT *,
        atr_20 / NULLIF(atr_120, 0) as vcp_ratio,
        vol / NULLIF(vol_ma20, 0) as vol_ratio,
        (ma5 + ma10 + ma20 + ma60) / 4.0 as ma_mean,
        sqrt(
            (power(ma5 - ma_mean, 2) + power(ma10 - ma_mean, 2) + power(ma20 - ma_mean, 2) + power(ma60 - ma_mean, 2)) / 4.0
        ) / NULLIF(close, 0) as ma_cv
    FROM with_range
)
SELECT 
    ts_code, trade_date, close, pct_chg, vol_ratio, vcp_ratio, range_20, ma_cv, atr_20, atr_120
FROM with_vcp
WHERE trade_date >= '20200102'
  AND vcp_ratio IS NOT NULL
  AND vol_ratio IS NOT NULL
  AND ma_cv IS NOT NULL
  AND close > 2
  AND vol_ma20 > 0
ORDER BY ts_code, trade_date
"""

print("  执行 SQL 查询 (预计30-60秒)...")
df = ch_query(indicator_sql)
print(f"  获取记录数: {len(df)}")

# Convert types
for col in ['close', 'pct_chg', 'vol_ratio', 'vcp_ratio', 'range_20', 'ma_cv', 'atr_20', 'atr_120']:
    df[col] = pd.to_numeric(df[col], errors='coerce')

df['trade_date'] = pd.to_datetime(df['trade_date'])

# Step 2: Fetch daily_basic for market cap and turnover
print("\n[2/4] 拉取市值和换手率数据...")
basic_sql = """
SELECT ts_code, trade_date, 
       toFloat64(turnover_rate) as turnover_rate,
       toFloat64(total_mv) as total_mv,
       toFloat64(circ_mv) as circ_mv
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '20200102'
"""
basic_df = ch_query(basic_sql)
basic_df['trade_date'] = pd.to_datetime(basic_df['trade_date'])
for col in ['turnover_rate', 'total_mv', 'circ_mv']:
    basic_df[col] = pd.to_numeric(basic_df[col], errors='coerce')

df = df.merge(basic_df, on=['ts_code', 'trade_date'], how='left')

# Step 3: Compute forward returns using ClickHouse (much faster)
print("\n[3/4] 计算前向收益率...")

fwd_sql = """
WITH
base AS (
    SELECT 
        ts_code, trade_date, 
        toFloat64(close) as close
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200102'
)
SELECT 
    ts_code, trade_date, close,
    leadInFrame(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) as close_5d,
    leadInFrame(close, 10) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) as close_10d,
    leadInFrame(close, 20) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) as close_20d
FROM base
"""
print("  执行前向收益查询...")
fwd_df = ch_query(fwd_sql)
fwd_df['trade_date'] = pd.to_datetime(fwd_df['trade_date'])
for col in ['close', 'close_5d', 'close_10d', 'close_20d']:
    fwd_df[col] = pd.to_numeric(fwd_df[col], errors='coerce')

fwd_df['fwd_ret_5'] = fwd_df['close_5d'] / fwd_df['close'] - 1
fwd_df['fwd_ret_10'] = fwd_df['close_10d'] / fwd_df['close'] - 1
fwd_df['fwd_ret_20'] = fwd_df['close_20d'] / fwd_df['close'] - 1

fwd_df = fwd_df[['ts_code', 'trade_date', 'fwd_ret_5', 'fwd_ret_10', 'fwd_ret_20']]
df = df.merge(fwd_df, on=['ts_code', 'trade_date'], how='left')

# Step 4: Analysis
print("\n[4/4] VCP信号分析...")
print("=" * 60)

# Define signals
valid = df.dropna(subset=['vcp_ratio', 'vol_ratio', 'ma_cv', 'close'])

# VCP Signal
vcp_signal = valid[
    (valid['vcp_ratio'] < 0.6) &
    (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
    (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0) &
    (valid['ma_cv'] < 0.01)
].copy()

print(f"\n📊 有效样本行数: {len(valid)}")
print(f"📊 VCP信号总数: {len(vcp_signal)}")

# Overall performance
print(f"\n📊 VCP信号整体表现:")
for fwd in [5, 10, 20]:
    col = f'fwd_ret_{fwd}'
    ret = pd.to_numeric(vcp_signal[col], errors='coerce').dropna()
    if len(ret) > 0:
        print(f"  {fwd}日: 均收益={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, "
              f"胜率={(ret>0).mean()*100:.1f}%, 样本={len(ret)}")

# Baseline
print(f"\n📊 全市场基准:")
for fwd in [5, 10, 20]:
    col = f'fwd_ret_{fwd}'
    ret = pd.to_numeric(valid[col], errors='coerce').dropna()
    if len(ret) > 0:
        print(f"  {fwd}日: 均收益={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, "
              f"胜率={(ret>0).mean()*100:.1f}%, 样本={len(ret)}")

# Alpha
print(f"\n📊 VCP Alpha (vs 全市场):")
for fwd in [5, 10, 20]:
    col = f'fwd_ret_{fwd}'
    sig_ret = pd.to_numeric(vcp_signal[col], errors='coerce').dropna()
    base_ret = pd.to_numeric(valid[col], errors='coerce').dropna()
    if len(sig_ret) > 0 and len(base_ret) > 0:
        alpha = sig_ret.mean() - base_ret.mean()
        print(f"  {fwd}日 Alpha: {alpha*100:+.2f}%")

# VCP Ratio tiers
print(f"\n📊 VCP Ratio 分层分析:")
vcp_base = valid[
    (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
    (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0)
]

for tier_name, tier_cond in [
    ("极收缩 (<0.4)", valid['vcp_ratio'] < 0.4),
    ("强收缩 (0.4-0.5)", (valid['vcp_ratio'] >= 0.4) & (valid['vcp_ratio'] < 0.5)),
    ("中收缩 (0.5-0.6)", (valid['vcp_ratio'] >= 0.5) & (valid['vcp_ratio'] < 0.6)),
]:
    tier = vcp_base[tier_cond].copy()
    ret20 = pd.to_numeric(tier['fwd_ret_20'], errors='coerce').dropna()
    if len(ret20) >= 10:
        print(f"  {tier_name}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# Pure VCP vs VCP+MA_CV
print(f"\n📊 Pure VCP vs VCP+MA_CV 对比:")
pure_vcp = valid[
    (valid['vcp_ratio'] < 0.6) &
    (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
    (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0)
]
ret20_pure = pd.to_numeric(pure_vcp['fwd_ret_20'], errors='coerce').dropna()
ret20_vcp = pd.to_numeric(vcp_signal['fwd_ret_20'], errors='coerce').dropna()
print(f"  Pure VCP (无MA粘合): 信号={len(ret20_pure)}, 20日均收益={ret20_pure.mean()*100:.2f}%, 胜率={(ret20_pure>0).mean()*100:.1f}%")
print(f"  VCP+MA_CV (有粘合):  信号={len(ret20_vcp)}, 20日均收益={ret20_vcp.mean()*100:.2f}%, 胜率={(ret20_vcp>0).mean()*100:.1f}%")

# Market cap
print(f"\n📊 市值分层:")
sig_mv = vcp_signal.dropna(subset=['total_mv']).copy()
sig_mv['total_mv'] = pd.to_numeric(sig_mv['total_mv'], errors='coerce')
if len(sig_mv) > 50:
    q1 = sig_mv['total_mv'].quantile(0.25)
    q3 = sig_mv['total_mv'].quantile(0.75)
    for name, cond in [("小盘(<Q1)", sig_mv['total_mv'] < q1),
                        ("中盘(Q1-Q3)", (sig_mv['total_mv'] >= q1) & (sig_mv['total_mv'] <= q3)),
                        ("大盘(>Q3)", sig_mv['total_mv'] > q3)]:
        sub = sig_mv[cond]
        ret20 = pd.to_numeric(sub['fwd_ret_20'], errors='coerce').dropna()
        if len(ret20) >= 10:
            print(f"  {name}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# Turnover rate
print(f"\n📊 换手率分层:")
sig_turn = vcp_signal.dropna(subset=['turnover_rate']).copy()
sig_turn['turnover_rate'] = pd.to_numeric(sig_turn['turnover_rate'], errors='coerce')
if len(sig_turn) > 50:
    q1t = sig_turn['turnover_rate'].quantile(0.25)
    q3t = sig_turn['turnover_rate'].quantile(0.75)
    for name, cond in [("低换手(<Q1)", sig_turn['turnover_rate'] < q1t),
                        ("中换手(Q1-Q3)", (sig_turn['turnover_rate'] >= q1t) & (sig_turn['turnover_rate'] <= q3t)),
                        ("高换手(>Q3)", sig_turn['turnover_rate'] > q3t)]:
        sub = sig_turn[cond]
        ret20 = pd.to_numeric(sub['fwd_ret_20'], errors='coerce').dropna()
        if len(ret20) >= 10:
            print(f"  {name}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# Market regime (CSI 300 MA200)
print(f"\n📊 市场环境过滤 (沪深300 MA200):")
idx_sql = """
SELECT ts_code, trade_date, toFloat64(close) as close
FROM tushare.tushare_index_daily FINAL
WHERE ts_code = '000300.SH' AND trade_date >= '20190101'
ORDER BY trade_date
"""
idx_df = ch_query(idx_sql)
idx_df['trade_date'] = pd.to_datetime(idx_df['trade_date'])
idx_df['close'] = pd.to_numeric(idx_df['close'], errors='coerce')
idx_df['ma200'] = idx_df['close'].rolling(200).mean()
idx_df['market_regime'] = np.where(idx_df['close'] > idx_df['ma200'], 'bull', 'bear')

sig_regime = vcp_signal.merge(idx_df[['trade_date', 'market_regime']], on='trade_date', how='left')
for regime in ['bull', 'bear']:
    sub = sig_regime[sig_regime['market_regime'] == regime]
    ret20 = pd.to_numeric(sub['fwd_ret_20'], errors='coerce').dropna()
    if len(ret20) >= 10:
        print(f"  {regime}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# Year-by-year
print(f"\n📊 年度分解:")
sig_year = vcp_signal.copy()
sig_year['year'] = sig_year['trade_date'].dt.year
for year in sorted(sig_year['year'].unique()):
    sub = sig_year[sig_year['year'] == year]
    ret20 = pd.to_numeric(sub['fwd_ret_20'], errors='coerce').dropna()
    if len(ret20) >= 10:
        print(f"  {year}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# Additional: VCP with different thresholds
print(f"\n📊 VCP Ratio 阈值敏感性分析:")
for vcp_thresh in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    sig_t = valid[
        (valid['vcp_ratio'] < vcp_thresh) &
        (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
        (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0) &
        (valid['ma_cv'] < 0.01)
    ]
    ret20 = pd.to_numeric(sig_t['fwd_ret_20'], errors='coerce').dropna()
    if len(ret20) >= 10:
        print(f"  VCP<{vcp_thresh}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# Additional: VCP + MA_CV threshold sensitivity
print(f"\n📊 MA_CV 阈值敏感性 (VCP<0.6):")
for ma_thresh in [0.005, 0.01, 0.015, 0.02]:
    sig_m = valid[
        (valid['vcp_ratio'] < 0.6) &
        (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
        (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0) &
        (valid['ma_cv'] < ma_thresh)
    ]
    ret20 = pd.to_numeric(sig_m['fwd_ret_20'], errors='coerce').dropna()
    if len(ret20) >= 10:
        print(f"  MA_CV<{ma_thresh}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# Compare VCP vs V22 MA_CV-only approach
print(f"\n📊 VCP vs V22 (仅MA_CV) 对比:")
ma_only = valid[
    (valid['ma_cv'] < 0.01) &
    (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
    (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0)
]
ret20_ma = pd.to_numeric(ma_only['fwd_ret_20'], errors='coerce').dropna()
ret20_vcp2 = pd.to_numeric(vcp_signal['fwd_ret_20'], errors='coerce').dropna()
print(f"  仅MA_CV<0.01: 信号={len(ret20_ma)}, 20日均收益={ret20_ma.mean()*100:.2f}%, 胜率={(ret20_ma>0).mean()*100:.1f}%")
print(f"  VCP+MA_CV:    信号={len(ret20_vcp2)}, 20日均收益={ret20_vcp2.mean()*100:.2f}%, 胜率={(ret20_vcp2>0).mean()*100:.1f}%")

print("\n" + "=" * 60)
print("V23 VCP 回测完成")
print("=" * 60)

# Save summary
signal_summary = {
    'total_signals': len(vcp_signal),
    'valid_rows': len(valid),
    'data_start': str(df['trade_date'].min()),
    'data_end': str(df['trade_date'].max()),
}
for fwd in [5, 10, 20]:
    col = f'fwd_ret_{fwd}'
    ret = pd.to_numeric(vcp_signal[col], errors='coerce').dropna()
    if len(ret) > 0:
        signal_summary[f'fwd_ret_{fwd}_mean'] = round(ret.mean() * 100, 3)
        signal_summary[f'fwd_ret_{fwd}_win_rate'] = round((ret > 0).mean() * 100, 2)
        signal_summary[f'fwd_ret_{fwd}_median'] = round(ret.median() * 100, 3)

with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/breakout/20260509_v23_breakout/results.json', 'w') as f:
    json.dump(signal_summary, f, indent=2, ensure_ascii=False)

print(f"\n结果已保存至 results.json")
print(json.dumps(signal_summary, indent=2, ensure_ascii=False))
