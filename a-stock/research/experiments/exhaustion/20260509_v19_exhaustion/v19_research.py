#!/usr/bin/env python3
"""
V19 (续): 空方力量衰竭 + 机构资金流共振研究

V18结论: 衰竭信号统计显著但胜率<50%，不建议独立使用。
V19假设: 衰竭信号 + 机构资金流入(超大单净买入) = 共振信号，胜率可提升至55%+

信号定义:
1. 前3日缩量 (vol < vol_ma20)
2. 今日放量收阳 (vol_ratio > 1.5, pct_chg > 0)
3. 信号日或前1日: 超大单净流入 > 0 (机构在底部吸筹)

额外测试:
- RSI < 35 过滤 (超卖)
- 价格距60日低点 < 10% (底部区域)
- 市值分层 (小盘 vs 大盘)
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
    ret = data[col].dropna()
    if len(ret) == 0:
        return f"N/A"
    return f"均收益={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%, 样本={len(ret)}"

print("=" * 60)
print("V19: 空方力量衰竭 + 机构资金流共振研究")
print("=" * 60)

# Step 1: Fetch daily data with volume indicators
print("\n[1/5] 拉取全市场日线数据...")
daily_sql = """
SELECT ts_code, trade_date,
       toFloat64(open) as open, toFloat64(high) as high,
       toFloat64(low) as low, toFloat64(close) as close,
       toFloat64(vol) as vol, toFloat64(pct_chg) as pct_chg,
       toFloat64(amount) as amount
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20190601'
"""
daily_df = ch_query(daily_sql)
print(f"  日线记录: {len(daily_df)}")

daily_df['trade_date'] = pd.to_datetime(daily_df['trade_date'])
for col in ['open', 'high', 'low', 'close', 'vol', 'pct_chg', 'amount']:
    daily_df[col] = pd.to_numeric(daily_df[col], errors='coerce')

# Compute volume indicators
print("\n[2/5] 计算量价指标...")
daily_df = daily_df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)
daily_df['vol_ma20'] = daily_df.groupby('ts_code')['vol'].transform(lambda x: x.rolling(20).mean())
daily_df['vol_ratio'] = daily_df['vol'] / daily_df['vol_ma20']
daily_df['is_shrink_3d'] = (
    (daily_df.groupby('ts_code')['vol'].shift(1) < daily_df.groupby('ts_code')['vol_ma20'].shift(1)) &
    (daily_df.groupby('ts_code')['vol'].shift(2) < daily_df.groupby('ts_code')['vol_ma20'].shift(2)) &
    (daily_df.groupby('ts_code')['vol'].shift(3) < daily_df.groupby('ts_code')['vol_ma20'].shift(3))
)
daily_df['prev_close'] = daily_df.groupby('ts_code')['close'].shift(1)
daily_df['lower_shadow'] = daily_df[['open', 'close']].min(axis=1) - daily_df['low']
daily_df['body'] = abs(daily_df['close'] - daily_df['open'])
daily_df['lower_shadow_ratio'] = np.where(daily_df['body'] > 0, daily_df['lower_shadow'] / daily_df['body'], 0)

# Price position: distance from 60-day low
daily_df['low_60'] = daily_df.groupby('ts_code')['low'].transform(lambda x: x.rolling(60).min())
daily_df['high_60'] = daily_df.groupby('ts_code')['high'].transform(lambda x: x.rolling(60).max())
daily_df['price_position'] = (daily_df['close'] - daily_df['low_60']) / (daily_df['high_60'] - daily_df['low_60'])

# RSI (14-day)
def calc_rsi(group):
    delta = group.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

daily_df['rsi_14'] = daily_df.groupby('ts_code')['close'].transform(calc_rsi)

# Forward returns
for fwd in [1, 3, 5, 10]:
    daily_df[f'fwd_ret_{fwd}'] = daily_df.groupby('ts_code')['close'].shift(-fwd) / daily_df['close'] - 1

print(f"  指标计算完成")

# Step 3: Fetch moneyflow data
print("\n[3/5] 拉取资金流向数据...")
mf_sql = """
SELECT ts_code, trade_date,
       toFloat64(buy_lg_vol) as buy_lg_vol,
       toFloat64(sell_lg_vol) as sell_lg_vol,
       toFloat64(buy_elg_vol) as buy_elg_vol,
       toFloat64(sell_elg_vol) as sell_elg_vol
FROM tushare.tushare_moneyflow FINAL
WHERE trade_date >= '20200102'
"""
mf_df = ch_query(mf_sql)
mf_df['trade_date'] = pd.to_datetime(mf_df['trade_date'])
for col in ['buy_lg_vol', 'sell_lg_vol', 'buy_elg_vol', 'sell_elg_vol']:
    mf_df[col] = pd.to_numeric(mf_df[col], errors='coerce')
mf_df['net_super'] = (mf_df['buy_lg_vol'] - mf_df['sell_lg_vol']) + (mf_df['buy_elg_vol'] - mf_df['sell_elg_vol'])

daily_df = daily_df.merge(mf_df[['ts_code', 'trade_date', 'net_super']], on=['ts_code', 'trade_date'], how='left')

# Fetch market cap
basic_sql = """
SELECT ts_code, trade_date, toFloat64(total_mv) as total_mv
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '20200102'
"""
mv_df = ch_query(basic_sql)
mv_df['trade_date'] = pd.to_datetime(mv_df['trade_date'])
mv_df['total_mv'] = pd.to_numeric(mv_df['total_mv'], errors='coerce')
daily_df = daily_df.merge(mv_df, on=['ts_code', 'trade_date'], how='left')

# Step 4: Define and test signals
print("\n[4/5] 信号测试...")

valid = daily_df.dropna(subset=['vol_ratio', 'is_shrink_3d', 'fwd_ret_1', 'fwd_ret_3'])

# Base signal: 3-day shrink + volume expansion + positive close
base_signal = valid[
    valid['is_shrink_3d'] &
    (valid['vol_ratio'] > 1.5) &
    (valid['pct_chg'] > 0)
].copy()
print(f"\n  H1 (3日缩量+放量收阳): {len(base_signal)} 信号")
print(f"    1日: {analyze('fwd_ret_1', base_signal)}")
print(f"    3日: {analyze('fwd_ret_3', base_signal)}")
print(f"    5日: {analyze('fwd_ret_5', base_signal)}")

# + Moneyflow resonance
mf_signal = base_signal[base_signal['net_super'] > 0].copy()
print(f"\n  H1 + 超大单净流入: {len(mf_signal)} 信号")
print(f"    1日: {analyze('fwd_ret_1', mf_signal)}")
print(f"    3日: {analyze('fwd_ret_3', mf_signal)}")
print(f"    5日: {analyze('fwd_ret_5', mf_signal)}")

# + RSI oversold
rsi_signal = base_signal[base_signal['rsi_14'] < 35].copy()
print(f"\n  H1 + RSI<35: {len(rsi_signal)} 信号")
print(f"    1日: {analyze('fwd_ret_1', rsi_signal)}")
print(f"    3日: {analyze('fwd_ret_3', rsi_signal)}")
print(f"    5日: {analyze('fwd_ret_5', rsi_signal)}")

# + Price at bottom
bottom_signal = base_signal[base_signal['price_position'] < 0.15].copy()
print(f"\n  H1 + 价格底部15%: {len(bottom_signal)} 信号")
print(f"    1日: {analyze('fwd_ret_1', bottom_signal)}")
print(f"    3日: {analyze('fwd_ret_3', bottom_signal)}")
print(f"    5日: {analyze('fwd_ret_5', bottom_signal)}")

# + Long lower shadow
shadow_signal = base_signal[base_signal['lower_shadow_ratio'] > 0.5].copy()
print(f"\n  H1 + 长下影: {len(shadow_signal)} 信号")
print(f"    1日: {analyze('fwd_ret_1', shadow_signal)}")
print(f"    3日: {analyze('fwd_ret_3', shadow_signal)}")
print(f"    5日: {analyze('fwd_ret_5', shadow_signal)}")

# Combined: 衰竭 + 资金流 + 底部区域 (最强共振)
combined_signal = base_signal[
    (base_signal['net_super'] > 0) &
    (base_signal['price_position'] < 0.15)
].copy()
print(f"\n  H1 + 超大单净流入 + 底部15%: {len(combined_signal)} 信号")
print(f"    1日: {analyze('fwd_ret_1', combined_signal)}")
print(f"    3日: {analyze('fwd_ret_3', combined_signal)}")
print(f"    5日: {analyze('fwd_ret_5', combined_signal)}")

# Ultimate combo
ultimate_signal = base_signal[
    (base_signal['net_super'] > 0) &
    (base_signal['price_position'] < 0.15) &
    (base_signal['rsi_14'] < 35)
].copy()
print(f"\n  H1 + 超大单 + 底部 + RSI<35: {len(ultimate_signal)} 信号")
if len(ultimate_signal) > 10:
    print(f"    1日: {analyze('fwd_ret_1', ultimate_signal)}")
    print(f"    3日: {analyze('fwd_ret_3', ultimate_signal)}")
    print(f"    5日: {analyze('fwd_ret_5', ultimate_signal)}")

# Market cap stratification
print(f"\n  📊 市值分层 (H1信号):")
sig_mv = base_signal.dropna(subset=['total_mv']).copy()
if len(sig_mv) > 50:
    q1 = sig_mv['total_mv'].quantile(0.25)
    q3 = sig_mv['total_mv'].quantile(0.75)
    for name, cond in [("小盘", sig_mv['total_mv'] < q1), ("中盘", (sig_mv['total_mv'] >= q1) & (sig_mv['total_mv'] <= q3)), ("大盘", sig_mv['total_mv'] > q3)]:
        sub = sig_mv[cond]
        if len(sub) >= 10:
            print(f"    {name}: {analyze('fwd_ret_3', sub)}")

# Environment filter
print(f"\n  📊 牛熊环境过滤:")
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

base_with_regime = base_signal.merge(idx_df[['trade_date', 'regime']], on='trade_date', how='left')
for regime in ['bull', 'bear']:
    sub = base_with_regime[base_with_regime['regime'] == regime]
    if len(sub) >= 10:
        print(f"    {regime}: {analyze('fwd_ret_3', sub)}")

print("\n" + "=" * 60)
print("V19 回测完成")
print("=" * 60)

# Save summary
summary = {
    'base_signals': len(base_signal),
    'mf_signals': len(mf_signal),
    'combined_signals': len(combined_signal),
    'ultimate_signals': len(ultimate_signal) if len(ultimate_signal) > 10 else 0,
}
for prefix, sig in [('base', base_signal), ('mf', mf_signal), ('combined', combined_signal)]:
    if len(sig) > 0:
        for fwd in [1, 3, 5]:
            col = f'fwd_ret_{fwd}'
            ret = sig[col].dropna()
            if len(ret) > 0:
                summary[f'{prefix}_{fwd}d_mean'] = round(float(ret.mean() * 100), 3)
                summary[f'{prefix}_{fwd}d_win'] = round(float((ret > 0).mean() * 100), 2)

with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/exhaustion/20260509_v19_exhaustion/results.json', 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print(json.dumps(summary, indent=2, ensure_ascii=False))
