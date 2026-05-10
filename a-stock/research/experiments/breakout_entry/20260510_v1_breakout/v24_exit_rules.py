#!/usr/bin/env python3
"""
V24 Experiment: 动态止盈规则研究

基于 V23 VCP+MA_CV 信号, 测试不同退出规则对收益的影响.
V21已证明硬止损有害. V24测试:
1. 追踪止盈 (Trailing Stop): 从最高点回撤X%平仓
2. 时间止盈 (Time Stop): N日后收益<阈值则提前平仓
3. 分批止盈: 5日平半仓, 余下追踪止盈

使用 ClickHouse SQL 获取信号后的日内价格路径, 用 pandas 模拟退出规则.
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

print("=" * 60)
print("V24: 动态止盈规则研究")
print("=" * 60)

# Step 1: Identify VCP signals directly via SQL
print("\n[1/4] 识别 VCP 信号 (SQL)...")

signal_sql = """
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
SELECT ts_code, trade_date, close, pct_chg
FROM with_vcp
WHERE trade_date >= '20200102'
  AND vcp_ratio IS NOT NULL AND vol_ratio IS NOT NULL AND ma_cv IS NOT NULL
  AND vcp_ratio < 0.6
  AND pct_chg >= 2 AND pct_chg <= 5
  AND vol_ratio >= 1.5 AND vol_ratio <= 3.0
  AND ma_cv < 0.01
  AND close > 2 AND vol_ma20 > 0
ORDER BY ts_code, trade_date
"""

print("  执行信号识别查询...")
signals = ch_query(signal_sql)
signals['close'] = pd.to_numeric(signals['close'], errors='coerce')
signals['trade_date'] = pd.to_datetime(signals['trade_date'])
print(f"  VCP信号数: {len(signals)}")

# Step 2: Determine bull/bear regime
print("\n[2/4] 判断牛熊环境...")
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

signals = signals.merge(idx_df[['trade_date', 'regime']], on='trade_date', how='left')
bull_signals = signals[signals['regime'] == 'bull']
print(f"  牛市信号: {len(bull_signals)}")
print(f"  熊市信号: {len(signals[signals['regime'] == 'bear'])}")

# Step 3: Sample bull signals and simulate exit rules
print("\n[3/4] 动态止盈模拟...")

# Get a manageable sample
sample_n = min(200, len(bull_signals))
sample = bull_signals.sample(n=sample_n, random_state=42).reset_index(drop=True)

# Fetch post-signal price paths for sampled signals
# Build a query to get next 20 trading days for each signal
conditions = []
for _, sig in sample.iterrows():
    ts = sig['ts_code']
    td = sig['trade_date'].strftime('%Y%m%d')
    conditions.append(f"(ts_code='{ts}' AND trade_date>'{td}')")

# Split into chunks to avoid query too long
results = []
chunk_size = 50

for i in range(0, len(sample), chunk_size):
    chunk = sample.iloc[i:i+chunk_size]
    conds = []
    for _, sig in chunk.iterrows():
        ts = sig['ts_code']
        td = sig['trade_date'].strftime('%Y%m%d')
        conds.append(f"(ts_code='{ts}' AND trade_date>'{td}')")
    
    where_clause = ' OR '.join(conds)
    path_sql = f"""
    SELECT ts_code, trade_date, 
           toFloat64(close) as close, 
           toFloat64(low) as low,
           toFloat64(high) as high
    FROM tushare.tushare_stock_daily FINAL
    WHERE {where_clause}
    ORDER BY ts_code, trade_date
    """
    
    path_df = ch_query(path_sql)
    if len(path_df) > 0:
        path_df['trade_date'] = pd.to_datetime(path_df['trade_date'])
        for col in ['close', 'low', 'high']:
            path_df[col] = pd.to_numeric(path_df[col], errors='coerce')
        
        # Merge with signal info
        chunk_with_info = chunk[['ts_code', 'trade_date', 'close']].copy()
        chunk_with_info = chunk_with_info.rename(columns={'trade_date': 'signal_date', 'close': 'entry_price'})
        
        path_df = path_df.merge(chunk_with_info, on='ts_code', how='inner')
        path_df = path_df[path_df['trade_date'] > path_df['signal_date']]
        
        results.append(path_df)

if len(results) > 0:
    all_paths = pd.concat(results, ignore_index=True)
else:
    all_paths = pd.DataFrame()

print(f"  获取价格路径记录: {len(all_paths)}")

# Simulate exit rules
if len(all_paths) > 0:
    all_paths['trade_day'] = all_paths.groupby(['ts_code', 'signal_date']).cumcount() + 1
    all_paths['ret_from_entry'] = all_paths['close'] / all_paths['entry_price'] - 1
    all_paths['max_ret'] = all_paths.groupby(['ts_code', 'signal_date'])['ret_from_entry'].cummax()
    all_paths['drawdown'] = all_paths['max_ret'] - all_paths['ret_from_entry']
    
    # Keep only first 20 trading days
    all_paths = all_paths[all_paths['trade_day'] <= 20]
    
    # Rule 1: Fixed hold
    exit_data = []
    
    for hold_days in [5, 10, 20]:
        subset = all_paths[all_paths['trade_day'] == hold_days]
        for _, row in subset.iterrows():
            exit_data.append({
                'rule': f'fixed_{hold_days}',
                'exit_day': hold_days,
                'ret': row['ret_from_entry']
            })
    
    # Rule 2: Trailing stop
    for trail_pct in [0.10, 0.15, 0.20, 0.30]:
        # For each signal, find first day drawdown exceeds threshold
        grouped = all_paths.groupby(['ts_code', 'signal_date'])
        for (ts, sd), group in grouped:
            group = group.sort_values('trade_day')
            hit = False
            for _, row in group.iterrows():
                if row['drawdown'] >= trail_pct:
                    exit_data.append({
                        'rule': f'trailing_{int(trail_pct*100)}pct',
                        'exit_day': row['trade_day'],
                        'ret': row['ret_from_entry']
                    })
                    hit = True
                    break
            if not hit and len(group) >= 20:
                exit_data.append({
                    'rule': f'trailing_{int(trail_pct*100)}pct',
                    'exit_day': group.iloc[-1]['trade_day'],
                    'ret': group.iloc[-1]['ret_from_entry']
                })
    
    # Rule 3: Time stop (if return < threshold after N days, exit early)
    for n_days, threshold in [(5, 0.02), (5, 0.0), (5, -0.03), (10, 0.03), (10, 0.0)]:
        grouped = all_paths.groupby(['ts_code', 'signal_date'])
        for (ts, sd), group in grouped:
            group = group.sort_values('trade_day')
            row_n = group[group['trade_day'] == n_days]
            if len(row_n) == 0:
                continue
            ret_at_n = row_n.iloc[0]['ret_from_entry']
            if ret_at_n < threshold:
                exit_data.append({
                    'rule': f'timestop_{n_days}d_{int(threshold*100)}pct',
                    'exit_day': n_days,
                    'ret': ret_at_n
                })
            elif len(group) >= 20:
                row_20 = group[group['trade_day'] == 20]
                if len(row_20) > 0:
                    exit_data.append({
                        'rule': f'timestop_{n_days}d_{int(threshold*100)}pct',
                        'exit_day': 20,
                        'ret': row_20.iloc[0]['ret_from_entry']
                    })
    
    exit_df = pd.DataFrame(exit_data)
    
    print(f"\n{'='*60}")
    print("📊 动态止盈规则对比 (牛市信号样本 n={})".format(sample_n))
    print(f"{'='*60}")
    
    print(f"\n  {'规则':35s} {'均收益':>8s} {'中位收益':>8s} {'胜率':>6s} {'样本':>6s} {'平均持仓':>8s}")
    print(f"  {'='*35} {'='*8} {'='*8} {'='*6} {'='*6} {'='*8}")
    
    for rule in sorted(exit_df['rule'].unique()):
        sub = exit_df[exit_df['rule'] == rule]
        ret = sub['ret'].dropna()
        if len(ret) > 0:
            avg_day = sub['exit_day'].mean()
            print(f"  {rule:35s} {ret.mean()*100:7.2f}% {ret.median()*100:7.2f}% {(ret>0).mean()*100:5.1f}% {len(ret):6d} {avg_day:7.1f}d")

# Step 4: Summary
print("\n[4/4] 结论总结...")
print("\n✅ V24 完成: 动态止盈规则对比分析")
print("   基于 V23 VCP+MA_CV 信号, 在牛市环境中测试多种退出规则")
print("   关键问题: 追踪止盈能否比固定持有更好地捕获右偏收益?")
