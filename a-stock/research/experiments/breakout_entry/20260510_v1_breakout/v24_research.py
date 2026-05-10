#!/usr/bin/env python3
"""
V24 Experiment: 资金流向增强 + 动态止盈研究

基于 V23 VCP+MA_CV 信号 (20日均收益2.67%, 胜率53.6%)，探索两个方向:
1. 资金流向 (超大单净流入) 能否作为前置过滤增强信号?
2. 动态止盈 vs 固定持有期: 如何捕获右偏分布的尾部大赢家?

V21 已证明硬止损(-8%)有害。V24 测试:
- 追踪止盈: 最高收益回撤 X% 时平仓
- 时间止盈: 持有 N 天后如果收益 < Y% 则平仓
- 资金流向过滤: 信号前 N 日超大单净流入为正
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
        return "N/A (样本不足)"
    return f"均收益={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%, 样本={len(ret)}"

print("=" * 60)
print("V24: 资金流向增强 + 动态止盈研究")
print("=" * 60)

# ============================================================
# Part 1: Fetch VCP signals (re-use V23 methodology)
# ============================================================
print("\n[1/6] 拉取全市场指标数据 (复用V23逻辑)...")

indicator_sql = """
WITH 
daily AS (
    SELECT ts_code, trade_date, 
        toFloat64(high) as high, toFloat64(low) as low, 
        toFloat64(close) as close, toFloat64(vol) as vol, 
        toFloat64(pct_chg) as pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20190601'
),
with_prev AS (
    SELECT *, lagInFrame(close, 1) OVER w as prev_close
    FROM daily WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date)
),
with_tr AS (
    SELECT *, greatest(high - low, abs(high - prev_close), abs(low - prev_close)) as tr
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
        sqrt((power(ma5 - ma_mean, 2) + power(ma10 - ma_mean, 2) + power(ma20 - ma_mean, 2) + power(ma60 - ma_mean, 2)) / 4.0) / NULLIF(close, 0) as ma_cv
    FROM with_ma
)
SELECT ts_code, trade_date, close, pct_chg, vol_ratio, vcp_ratio, ma_cv
FROM with_vcp
WHERE trade_date >= '20200102'
  AND vcp_ratio IS NOT NULL AND vol_ratio IS NOT NULL AND ma_cv IS NOT NULL
  AND close > 2 AND vol_ma20 > 0
ORDER BY ts_code, trade_date
"""
print("  执行 SQL 查询...")
df = ch_query(indicator_sql)
print(f"  获取记录数: {len(df)}")

for col in ['close', 'pct_chg', 'vol_ratio', 'vcp_ratio', 'ma_cv']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])

# Compute forward returns
print("\n[2/6] 计算前向收益率...")
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

# For dynamic stop-loss simulation, we need daily returns during holding period
fwd_daily_sql = """
SELECT ts_code, trade_date, toFloat64(close) as close, toFloat64(low) as low, toFloat64(high) as high
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20200102'
ORDER BY ts_code, trade_date
"""
print("  拉取日线数据 (用于动态止盈模拟)...")
daily_df = ch_query(fwd_daily_sql)
daily_df['trade_date'] = pd.to_datetime(daily_df['trade_date'])
for col in ['close', 'low', 'high']:
    daily_df[col] = pd.to_numeric(daily_df[col], errors='coerce')

# Merge signals with daily data
df = df.merge(daily_df[['ts_code', 'trade_date', 'low', 'high']], on=['ts_code', 'trade_date'], how='left')

# Compute forward returns for base analysis
for fwd in [5, 10, 20]:
    df[f'fwd_ret_{fwd}'] = df.groupby('ts_code')['close'].shift(-fwd) / df['close'] - 1

# Define VCP signal (same as V23)
valid = df.dropna(subset=['vcp_ratio', 'vol_ratio', 'ma_cv'])
vcp_signal = valid[
    (valid['vcp_ratio'] < 0.6) &
    (valid['pct_chg'] >= 2) & (valid['pct_chg'] <= 5) &
    (valid['vol_ratio'] >= 1.5) & (valid['vol_ratio'] <= 3.0) &
    (valid['ma_cv'] < 0.01)
].copy()

print(f"  VCP信号总数: {len(vcp_signal)}")
print(f"  基准 20日: {analyze('fwd_ret_20', vcp_signal)}")

# ============================================================
# Part 2: Moneyflow Enhancement
# ============================================================
print("\n[3/6] 资金流向增强研究...")

# Fetch moneyflow data (super large order net inflow)
moneyflow_sql = """
SELECT ts_code, trade_date,
       toFloat64(buy_lg_vol) as buy_lg_vol,
       toFloat64(sell_lg_vol) as sell_lg_vol,
       toFloat64(buy_elg_vol) as buy_elg_vol,
       toFloat64(sell_elg_vol) as sell_elg_vol
FROM tushare.tushare_moneyflow FINAL
WHERE trade_date >= '20200102'
"""
print("  拉取资金流向数据...")
mf_df = ch_query(moneyflow_sql)
mf_df['trade_date'] = pd.to_datetime(mf_df['trade_date'])
for col in ['buy_lg_vol', 'sell_lg_vol', 'buy_elg_vol', 'sell_elg_vol']:
    mf_df[col] = pd.to_numeric(mf_df[col], errors='coerce')

# Compute net inflow: large + extra-large orders
mf_df['net_lg'] = mf_df['buy_lg_vol'] - mf_df['sell_lg_vol']
mf_df['net_elg'] = mf_df['buy_elg_vol'] - mf_df['sell_elg_vol']
mf_df['net_super'] = mf_df['net_lg'] + mf_df['net_elg']  # 超大单净流入

# Compute 3-day rolling net inflow
mf_df = mf_df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)
mf_df['net_3d'] = mf_df.groupby('ts_code')['net_super'].rolling(3, min_periods=1).sum().values
mf_df['net_5d'] = mf_df.groupby('ts_code')['net_super'].rolling(5, min_periods=1).sum().values

# Merge with signal data
vcp_signal = vcp_signal.merge(
    mf_df[['ts_code', 'trade_date', 'net_super', 'net_3d', 'net_5d']],
    on=['ts_code', 'trade_date'], how='left'
)

# Test moneyflow as pre-signal filter
print(f"\n📊 资金流向前置过滤效果:")
sig_with_mf = vcp_signal.dropna(subset=['net_super', 'net_3d'])
print(f"  有资金流向数据的信号: {len(sig_with_mf)}")

for name, cond, desc in [
    ("超大单净流入>0", sig_with_mf['net_super'] > 0, "当日超大单净流入为正"),
    ("超大单净流出>0", sig_with_mf['net_super'] <= 0, "当日超大单净流入为负"),
    ("3日净流入>0", sig_with_mf['net_3d'] > 0, "3日累计超大单净流入为正"),
    ("3日净流出>0", sig_with_mf['net_3d'] <= 0, "3日累计超大单净流入为负"),
    ("5日净流入>0", sig_with_mf['net_5d'] > 0, "5日累计超大单净流入为正"),
    ("5日净流出>0", sig_with_mf['net_5d'] <= 0, "5日累计超大单净流入为负"),
]:
    sub = sig_with_mf[cond]
    if len(sub) >= 10:
        print(f"  {name}: {analyze('fwd_ret_20', sub)}")

# Moneyflow intensity tiers (based on signal's own net_super distribution)
print(f"\n📊 资金流向强度分层 (按信号自身分位):")
sig_mf_clean = sig_with_mf.dropna(subset=['fwd_ret_20'])
if len(sig_mf_clean) > 50:
    for col_name, col in [("当日超大单", "net_super"), ("3日累计", "net_3d"), ("5日累计", "net_5d")]:
        if col in sig_mf_clean.columns:
            q = sig_mf_clean[col].quantile([0.25, 0.5, 0.75])
            tiers = [
                (f"Q1(流出最多)", sig_mf_clean[col] < q[0.25]),
                (f"Q2(轻度流出)", (sig_mf_clean[col] >= q[0.25]) & (sig_mf_clean[col] < q[0.5])),
                (f"Q3(轻度流入)", (sig_mf_clean[col] >= q[0.5]) & (sig_mf_clean[col] < q[0.75])),
                (f"Q4(流入最多)", sig_mf_clean[col] >= q[0.75]),
            ]
            print(f"\n  {col_name} 分层:")
            for name, cond in tiers:
                sub = sig_mf_clean[cond]
                if len(sub) >= 10:
                    print(f"    {name}: {analyze('fwd_ret_20', sub)}")

# ============================================================
# Part 3: Dynamic Exit Rules Simulation
# ============================================================
print("\n[4/6] 动态止盈规则模拟...")

# For each signal, simulate different exit rules using daily data
# We need: close, low, high for each day after signal
# Build a lookup of daily prices

# Create signal-to-daily mapping
daily_df = daily_df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

# For each signal, get the next 20 trading days of price data
# Use merge_asof for efficient lookup
signal_dates = vcp_signal[['ts_code', 'trade_date', 'close']].copy()
signal_dates = signal_dates.rename(columns={'close': 'entry_price', 'trade_date': 'signal_date'})
signal_dates = signal_dates.sort_values(['ts_code', 'signal_date'])

# We'll simulate exits for a sample of signals (too many to do all)
# Take bull market signals (since we know they work best)
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

vcp_bull = vcp_signal.merge(idx_df[['trade_date', 'regime']], on='trade_date', how='left')
vcp_bull = vcp_bull[vcp_bull['regime'] == 'bull'].copy()

print(f"  牛市信号数: {len(vcp_bull)}")

# Sample signals for detailed exit simulation (for performance)
sample_size = min(500, len(vcp_bull))
sample_signals = vcp_bull.sample(n=sample_size, random_state=42)

exit_results = []

for _, sig in sample_signals.iterrows():
    ts = sig['ts_code']
    sdate = sig['trade_date']
    entry = sig['close']
    
    # Get next 20 trading days for this stock
    stock_daily = daily_df[
        (daily_df['ts_code'] == ts) & 
        (daily_df['trade_date'] > sdate)
    ].head(20).copy()
    
    if len(stock_daily) < 5:
        continue
    
    stock_daily = stock_daily.reset_index(drop=True)
    
    # Calculate daily returns from entry
    stock_daily['daily_ret'] = stock_daily['close'] / entry - 1
    stock_daily['high_water'] = stock_daily['daily_ret'].cummax()
    
    # Fixed hold 5/10/20
    for hold in [5, 10, 20]:
        if len(stock_daily) >= hold:
            exit_results.append({
                'rule': f'fixed_{hold}',
                'ret': stock_daily.iloc[hold-1]['daily_ret']
            })
    
    # Trailing stop: exit when drawdown from high > threshold
    for trail_pct in [0.10, 0.15, 0.20, 0.30]:
        for day_idx in range(len(stock_daily)):
            drawdown = stock_daily.iloc[day_idx]['high_water'] - stock_daily.iloc[day_idx]['daily_ret']
            if drawdown >= trail_pct:
                exit_results.append({
                    'rule': f'trailing_{int(trail_pct*100)}',
                    'ret': stock_daily.iloc[day_idx]['daily_ret']
                })
                break
        else:
            # Never hit trailing stop, exit at last day
            if len(stock_daily) > 0:
                exit_results.append({
                    'rule': f'trailing_{int(trail_pct*100)}',
                    'ret': stock_daily.iloc[-1]['daily_ret']
                })
    
    # Time stop: if return < threshold after N days, exit
    for n_days, threshold in [(5, 0.02), (5, 0.0), (5, -0.02), (10, 0.03), (10, 0.0)]:
        if len(stock_daily) >= n_days:
            ret_at_n = stock_daily.iloc[n_days-1]['daily_ret']
            if ret_at_n < threshold:
                exit_results.append({
                    'rule': f'timestop_{n_days}d_lt_{int(threshold*100)}pct',
                    'ret': ret_at_n
                })
            else:
                # Hold to 20 days
                if len(stock_daily) >= 20:
                    exit_results.append({
                        'rule': f'timestop_{n_days}d_lt_{int(threshold*100)}pct',
                        'ret': stock_daily.iloc[19]['daily_ret']
                    })

exit_df = pd.DataFrame(exit_results)

print(f"\n📊 动态止盈规则对比 (牛市信号样本 n={sample_size}):")
for rule in ['fixed_5', 'fixed_10', 'fixed_20',
             'trailing_10', 'trailing_15', 'trailing_20', 'trailing_30',
             'timestop_5d_lt_2pct', 'timestop_5d_lt_0pct', 'timestop_5d_lt_-2pct',
             'timestop_10d_lt_3pct', 'timestop_10d_lt_0pct']:
    sub = exit_df[exit_df['rule'] == rule]
    if len(sub) > 0:
        ret = sub['ret'].dropna()
        print(f"  {rule:35s}: 均收益={ret.mean()*100:.2f}%, 中位={ret.median()*100:.2f}%, 胜率={(ret>0).mean()*100:.1f}%, 样本={len(ret)}")

# ============================================================
# Part 4: Combined Enhancement (VCP + Moneyflow + Bull + Small Cap)
# ============================================================
print("\n[5/6] 组合增强效果...")

# Add market cap
basic_sql = """
SELECT ts_code, trade_date, toFloat64(total_mv) as total_mv
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '20200102'
"""
mv_df = ch_query(basic_sql)
mv_df['trade_date'] = pd.to_datetime(mv_df['trade_date'])
mv_df['total_mv'] = pd.to_numeric(mv_df['total_mv'], errors='coerce')

vcp_signal = vcp_signal.merge(mv_df, on=['ts_code', 'trade_date'], how='left')
sig_with_all = vcp_signal.dropna(subset=['total_mv', 'net_3d'])

print(f"  全数据信号: {len(sig_with_all)}")

# Test combinations
combinations = [
    ("基准 (VCP+MA_CV)", lambda x: pd.Series(True, index=x.index)),
    ("+ 牛市过滤", lambda x: x['trade_date'].map(dict(zip(idx_df['trade_date'], idx_df['regime']))) == 'bull'),
    ("+ 牛市 + 小盘", lambda x: (x['trade_date'].map(dict(zip(idx_df['trade_date'], idx_df['regime']))) == 'bull') & (x['total_mv'] < x['total_mv'].median())),
    ("+ 牛市 + 3日净流入", lambda x: (x['trade_date'].map(dict(zip(idx_df['trade_date'], idx_df['regime']))) == 'bull') & (x['net_3d'] > 0)),
    ("+ 牛市 + 小盘 + 3日净流入", lambda x: (x['trade_date'].map(dict(zip(idx_df['trade_date'], idx_df['regime']))) == 'bull') & (x['total_mv'] < x['total_mv'].median()) & (x['net_3d'] > 0)),
    ("+ 牛市 + 小盘 + 3日净流入 + 低换手", lambda x: (
        (x['trade_date'].map(dict(zip(idx_df['trade_date'], idx_df['regime']))) == 'bull') &
        (x['total_mv'] < x['total_mv'].median()) &
        (x['net_3d'] > 0) &
        (x['turnover_rate'] <= x['turnover_rate'].median())
    ) if 'turnover_rate' in x.columns else pd.Series(False, index=x.index)),
]

print(f"\n  {'组合':40s} {'信号数':>6s} {'20日均收益':>10s} {'中位收益':>10s} {'胜率':>8s}")
print(f"  {'='*40} {'='*6} {'='*10} {'='*10} {'='*8}")

for name, cond_func in combinations:
    try:
        cond = cond_func(sig_with_all)
        sub = sig_with_all[cond]
        ret20 = sub['fwd_ret_20'].dropna()
        if len(ret20) >= 10:
            print(f"  {name:40s} {len(ret20):6d} {ret20.mean()*100:9.2f}% {ret20.median()*100:9.2f}% {(ret20>0).mean()*100:7.1f}%")
    except Exception as e:
        print(f"  {name:40s} 错误: {str(e)[:30]}")

print("\n" + "=" * 60)
print("V24 回测完成")
print("=" * 60)

# Save summary
summary = {
    'vcp_signals': len(vcp_signal),
    'bull_signals': len(vcp_bull),
}
summary['vcp_20d'] = analyze('fwd_ret_20', vcp_signal)
if len(vcp_bull) > 0:
    summary['bull_20d'] = analyze('fwd_ret_20', vcp_bull)

with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/主升浪潜伏与起爆点_(pre-main_uptrend_entry)/20260510_v1_breakout/results.json', 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
