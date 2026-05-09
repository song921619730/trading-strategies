#!/usr/bin/env python3
"""
V23 Experiment: VCP (Volatility Contraction Pattern) 主升浪潜伏研究

假设: ATR/振幅持续收缩后放量突破，20日收益显著优于基准
不同于V22的均线粘合(MA_CV)，VCP关注价格波动率的收敛程度

VCP定义:
1. ATR_20 降至 ATR_120 的 X% 以下 (波动率收缩)
2. 过去20日振幅(最高-最低)/中价 的均值 < 历史分位阈值
3. 突破日放量 (量比>1.5) 且涨幅2-5% (V22验证温和突破最优)

"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime

# ClickHouse config
CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(sql, fmt='TabSeparatedWithNames'):
    """Execute ClickHouse query and return DataFrame"""
    full_sql = f"{sql} FORMAT {fmt}"
    r = requests.get(CH_URL, params={'query': full_sql}, auth=CH_AUTH, timeout=60)
    r.raise_for_status()
    lines = r.text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    rows = [line.split('\t') for line in lines[1:]]
    df = pd.DataFrame(rows, columns=cols)
    return df

print("=" * 60)
print("V23: VCP (波动率收缩模式) 全市场回测")
print("=" * 60)

# Step 1: Get all stock codes
print("\n[1/6] 获取全市场股票列表...")
codes_df = ch_query("""
    SELECT DISTINCT ts_code 
    FROM tushare.tushare_stock_daily FINAL 
    WHERE trade_date >= '20200101'
""")
all_codes = codes_df['ts_code'].tolist()
print(f"  总股票数: {len(all_codes)}")

# Step 2: Fetch full market daily data (2020 to max)
print("\n[2/6] 拉取全市场日线数据...")
daily_sql = """
    SELECT ts_code, trade_date, open, high, low, close, vol, pct_chg, amount
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101'
    ORDER BY ts_code, trade_date
"""
daily_df = ch_query(daily_sql)
print(f"  日线记录数: {len(daily_df)}")

# Convert types
daily_df['trade_date'] = pd.to_datetime(daily_df['trade_date'])
for col in ['open', 'high', 'low', 'close', 'vol', 'pct_chg', 'amount']:
    daily_df[col] = pd.to_numeric(daily_df[col], errors='coerce')

# Step 3: Fetch daily_basic for turnover rate, market cap
print("\n[3/6] 拉取 daily_basic (换手率/市值)...")
basic_sql = """
    SELECT ts_code, trade_date, turnover_rate, total_mv, circ_mv
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date >= '20200101'
"""
basic_df = ch_query(basic_sql)
basic_df['trade_date'] = pd.to_datetime(basic_df['trade_date'])
for col in ['turnover_rate', 'total_mv', 'circ_mv']:
    basic_df[col] = pd.to_numeric(basic_df[col], errors='coerce')

# Merge
daily_df = daily_df.merge(basic_df, on=['ts_code', 'trade_date'], how='left')

# Filter: exclude ST (name contains ST), exclude new IPO (<60 days listing)
# For simplicity, we'll use price > 2 as rough ST filter and skip first 60 trading days per stock
print(f"  合并后记录数: {len(daily_df)}")
print(f"  数据范围: {daily_df['trade_date'].min().strftime('%Y-%m-%d')} 至 {daily_df['trade_date'].max().strftime('%Y-%m-%d')}")

# Step 4: Compute VCP indicators per stock
print("\n[4/6] 计算 VCP 指标 (ATR, 波动率收缩比)...")

results = []
processed = 0
total = len(all_codes)

for ts_code in all_codes:
    sdf = daily_df[daily_df['ts_code'] == ts_code].sort_values('trade_date').copy()
    if len(sdf) < 150:  # Need enough history
        continue
    
    # True Range
    sdf['prev_close'] = sdf['close'].shift(1)
    sdf['tr'] = sdf[['sdf.high - sdf.prev_close', 'sdf.prev_close - sdf.low', 'sdf.high - sdf.low']].max(axis=1, skipna=False)
    
    # Actually compute TR properly
    sdf['tr'] = np.maximum(
        sdf['high'] - sdf['low'],
        np.maximum(
            abs(sdf['high'] - sdf['prev_close']),
            abs(sdf['low'] - sdf['prev_close'])
        )
    )
    
    # ATR(20) and ATR(120)
    sdf['atr_20'] = sdf['tr'].rolling(20).mean()
    sdf['atr_120'] = sdf['tr'].rolling(120).mean()
    
    # VCP Ratio: short-term ATR / long-term ATR
    # Lower = more contraction
    sdf['vcp_ratio'] = sdf['atr_20'] / sdf['atr_120']
    
    # 20-day price range contraction: (high_20 - low_20) / close
    sdf['high_20'] = sdf['high'].rolling(20).max()
    sdf['low_20'] = sdf['low'].rolling(20).min()
    sdf['range_20'] = (sdf['high_20'] - sdf['low_20']) / sdf['close']
    
    # Volume ratio: today vol / 20-day avg vol
    sdf['vol_ma20'] = sdf['vol'].rolling(20).mean()
    sdf['vol_ratio'] = sdf['vol'] / sdf['vol_ma20']
    
    # MA convergence (for comparison with V22)
    sdf['ma5'] = sdf['close'].rolling(5).mean()
    sdf['ma10'] = sdf['close'].rolling(10).mean()
    sdf['ma20'] = sdf['close'].rolling(20).mean()
    sdf['ma60'] = sdf['close'].rolling(60).mean()
    ma_cols = ['ma5', 'ma10', 'ma20', 'ma60']
    sdf['ma_cv'] = sdf[ma_cols].std(axis=1, ddof=0) / sdf['close']
    
    processed += 1
    if processed % 500 == 0:
        print(f"  处理进度: {processed}/{total} ({processed/total*100:.1f}%)")

print(f"  处理完成: {processed} 只股票")

# Step 5: Identify VCP signals and measure forward returns
print("\n[5/6] 识别 VCP 突破信号 + 计算前向收益...")

# Filter valid rows
valid = daily_df[
    (daily_df['vcp_ratio'].notna()) & 
    (daily_df['range_20'].notna()) &
    (daily_df['vol_ratio'].notna()) &
    (daily_df['ma_cv'].notna()) &
    (daily_df['close'] > 2) &  # Rough ST filter
    (daily_df['vol_ma20'] > 0)
].copy()

print(f"  有效信号行: {len(valid)}")

# VCP Signal: VCP收缩 + 温和放量 + 温和突破 + MA粘合辅助
# VCP核心: vcp_ratio < 0.6 (ATR20 < 60% of ATR120) = 波动率极度收缩
# 突破确认: 涨幅2-5%, 量比1.5-3 (V22最优区间)
# MA粘合辅助: ma_cv < 0.01

signal = valid[
    (valid['vcp_ratio'] < 0.6) &
    (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
    (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0) &
    (valid['ma_cv'] < 0.01)
].copy()

print(f"  VCP+温和突破 信号数: {len(signal)}")

# Compute forward returns
for fwd in [5, 10, 20]:
    signal[f'fwd_ret_{fwd}'] = signal.groupby('ts_code')['close'].shift(-fwd) / signal['close'] - 1

# Baseline: all valid rows forward returns (market average)
baseline = valid.copy()
for fwd in [5, 10, 20]:
    baseline[f'fwd_ret_{fwd}'] = baseline.groupby('ts_code')['close'].shift(-fwd) / baseline['close'] - 1

# Step 6: Analyze results
print("\n[6/6] 统计分析...")
print("=" * 60)

# Overall VCP signal performance
print("\n📊 VCP信号整体表现:")
print(f"  信号总数: {len(signal)}")
for fwd in [5, 10, 20]:
    col = f'fwd_ret_{fwd}'
    ret = signal[col].dropna()
    print(f"  {fwd}日: 均收益={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, "
          f"胜率={(ret>0).mean()*100:.1f}%, 样本={len(ret)}")

# Baseline comparison
print(f"\n📊 全市场基准 (对照):")
for fwd in [5, 10, 20]:
    col = f'fwd_ret_{fwd}'
    ret = baseline[col].dropna()
    print(f"  {fwd}日: 均收益={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, "
          f"胜率={(ret>0).mean()*100:.1f}%, 样本={len(ret)}")

# Alpha
print(f"\n📊 VCP Alpha (vs 全市场):")
for fwd in [5, 10, 20]:
    col = f'fwd_ret_{fwd}'
    sig_ret = signal[col].dropna()
    base_ret = baseline[col].dropna()
    alpha = sig_ret.mean() - base_ret.mean()
    print(f"  {fwd}日 Alpha: {alpha*100:+.2f}%")

# Breakdown by VCP Ratio tiers
print(f"\n📊 VCP Ratio 分层分析 (vcp_ratio < 0.6 前提下):")
vcp_cond = (valid['vcp_ratio'] < 0.6) & (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) & (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0)
vcp_signals = valid[vcp_cond].copy()

for tier_name, tier_cond in [
    ("极收缩 (<0.4)", valid['vcp_ratio'] < 0.4),
    ("强收缩 (0.4-0.5)", (valid['vcp_ratio'] >= 0.4) & (valid['vcp_ratio'] < 0.5)),
    ("中收缩 (0.5-0.6)", (valid['vcp_ratio'] >= 0.5) & (valid['vcp_ratio'] < 0.6)),
]:
    tier = valid[tier_cond & vcp_cond].copy()
    if len(tier) < 10:
        continue
    for fwd in [5, 10, 20]:
        col = f'fwd_ret_{fwd}'
        tier[f'fwd_ret_{fwd}'] = tier.groupby('ts_code')['close'].shift(-fwd) / tier['close'] - 1
        ret = tier[col].dropna()
        if fwd == 20:
            print(f"  {tier_name}: 信号={len(ret)}, 20日均收益={ret.mean()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%")

# Breakdown by market cap
print(f"\n📊 市值分层:")
signal_with_mv = signal.dropna(subset=['total_mv'])
if len(signal_with_mv) > 0:
    q1 = signal_with_mv['total_mv'].quantile(0.25)
    q3 = signal_with_mv['total_mv'].quantile(0.75)
    for name, cond in [("小盘(<Q1)", signal_with_mv['total_mv'] < q1),
                        ("中盘(Q1-Q3)", (signal_with_mv['total_mv'] >= q1) & (signal_with_mv['total_mv'] <= q3)),
                        ("大盘(>Q3)", signal_with_mv['total_mv'] > q3)]:
        sub = signal_with_mv[cond]
        if len(sub) < 10:
            continue
        ret20 = sub['fwd_ret_20'].dropna()
        print(f"  {name}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# Breakdown by turnover rate
print(f"\n📊 换手率分层:")
signal_with_turn = signal.dropna(subset=['turnover_rate'])
if len(signal_with_turn) > 0:
    q1t = signal_with_turn['turnover_rate'].quantile(0.25)
    q3t = signal_with_turn['turnover_rate'].quantile(0.75)
    for name, cond in [("低换手(<Q1)", signal_with_turn['turnover_rate'] < q1t),
                        ("中换手(Q1-Q3)", (signal_with_turn['turnover_rate'] >= q1t) & (signal_with_turn['turnover_rate'] <= q3t)),
                        ("高换手(>Q3)", signal_with_turn['turnover_rate'] > q3t)]:
        sub = signal_with_turn[cond]
        if len(sub) < 10:
            continue
        ret20 = sub['fwd_ret_20'].dropna()
        print(f"  {name}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# Environment filter: bull vs bear vs sideways
print(f"\n📊 市场环境过滤 (以沪深300 MA200 趋势判断):")
# Get index daily data
idx_sql = """
    SELECT ts_code, trade_date, close
    FROM tushare.tushare_index_daily FINAL
    WHERE ts_code = '000300.SH' AND trade_date >= '20190101'
    ORDER BY trade_date
"""
idx_df = ch_query(idx_sql)
idx_df['trade_date'] = pd.to_datetime(idx_df['trade_date'])
idx_df['close'] = pd.to_numeric(idx_df['close'], errors='coerce')
idx_df['ma200'] = idx_df['close'].rolling(200).mean()
idx_df['market_regime'] = np.where(idx_df['close'] > idx_df['ma200'], 'bull', 'bear')

signal_with_regime = signal.merge(idx_df[['trade_date', 'market_regime']], on='trade_date', how='left')
for regime in ['bull', 'bear']:
    sub = signal_with_regime[signal_with_regime['market_regime'] == regime]
    if len(sub) < 10:
        continue
    ret20 = sub['fwd_ret_20'].dropna()
    print(f"  {regime}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

# Compare VCP-only vs VCP+MA_CV (pure VCP without MA convergence filter)
print(f"\n📊 VCP-only vs VCP+MA_CV 对比:")
# Pure VCP: vcp_ratio + breakout without ma_cv filter
pure_vcp = valid[
    (valid['vcp_ratio'] < 0.6) &
    (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
    (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0)
].copy()
for fwd in [5, 10, 20]:
    col = f'fwd_ret_{fwd}'
    pure_vcp[f'fwd_ret_{fwd}'] = pure_vcp.groupby('ts_code')['close'].shift(-fwd) / pure_vcp['close'] - 1

ret20_pure = pure_vcp['fwd_ret_20'].dropna()
ret20_vcp = signal['fwd_ret_20'].dropna()  # VCP + MA_CV
print(f"  Pure VCP (无MA粘合): 信号={len(ret20_pure)}, 20日均收益={ret20_pure.mean()*100:.2f}%, 胜率={(ret20_pure>0).mean()*100:.1f}%")
print(f"  VCP+MA_CV (有粘合):  信号={len(ret20_vcp)}, 20日均收益={ret20_vcp.mean()*100:.2f}%, 胜率={(ret20_vcp>0).mean()*100:.1f}%")

# Year-by-year breakdown
print(f"\n📊 年度分解:")
signal_year = signal.copy()
signal_year['year'] = signal_year['trade_date'].dt.year
for year in sorted(signal_year['year'].unique()):
    sub = signal_year[signal_year['year'] == year]
    ret20 = sub['fwd_ret_20'].dropna()
    if len(ret20) < 10:
        continue
    print(f"  {year}: 信号={len(ret20)}, 20日均收益={ret20.mean()*100:.2f}%, 胜率={(ret20>0).mean()*100:.1f}%")

print("\n" + "=" * 60)
print("V23 VCP 回测完成")
print("=" * 60)

# Save signal summary for report
signal_summary = {
    'total_signals': len(signal),
    'fwd_ret_5_mean': signal['fwd_ret_5'].dropna().mean() * 100,
    'fwd_ret_5_win_rate': (signal['fwd_ret_5'].dropna() > 0).mean() * 100,
    'fwd_ret_10_mean': signal['fwd_ret_10'].dropna().mean() * 100,
    'fwd_ret_10_win_rate': (signal['fwd_ret_10'].dropna() > 0).mean() * 100,
    'fwd_ret_20_mean': signal['fwd_ret_20'].dropna().mean() * 100,
    'fwd_ret_20_win_rate': (signal['fwd_ret_20'].dropna() > 0).mean() * 100,
    'baseline_5_mean': baseline['fwd_ret_5'].dropna().mean() * 100,
    'baseline_10_mean': baseline['fwd_ret_10'].dropna().mean() * 100,
    'baseline_20_mean': baseline['fwd_ret_20'].dropna().mean() * 100,
    'data_start': daily_df['trade_date'].min().strftime('%Y-%m-%d'),
    'data_end': daily_df['trade_date'].max().strftime('%Y-%m-%d'),
    'universe_size': len(all_codes),
}

import json
with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/20260509_v23_breakout/results.json', 'w') as f:
    json.dump(signal_summary, f, indent=2, ensure_ascii=False)

print(f"\n结果已保存至 results.json")
print(json.dumps(signal_summary, indent=2, ensure_ascii=False))
