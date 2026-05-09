#!/usr/bin/env python3
"""
低开高走选股策略回测 - 基于阶段1分析结果

策略逻辑:
1. 筛选前日大涨5%+或跌停的股票 (高概率低开高走群体)
2. 前日换手率在5-15%之间 (中等换手,最优区间)
3. 前日成交量正常或放量 (量比>=0.8)
4. 次日开盘买入,收盘卖出
"""

import requests
import pandas as pd
import numpy as np

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(query, fmt='TabSeparatedWithNames', timeout=300):
    full_query = f"{query} FORMAT {fmt}"
    r = requests.get(CH_URL, params={'query': full_query}, auth=CH_AUTH, timeout=timeout)
    if r.status_code != 200:
        raise Exception(f"Query failed: {r.text[:500]}")
    return r.text

def parse_tab(text):
    lines = text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    rows = [line.split('\t') for line in lines[1:]]
    return pd.DataFrame(rows, columns=cols)

def num_cols(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

print("=" * 60)
print("低开高走选股策略回测")
print("=" * 60)

# 获取回测数据 - 使用更简单的查询方式
print("\n【步骤1】获取回测数据 (可能较慢)...")

# 先获取基本数据
q = """
SELECT 
    ts_code, trade_date, open, close, pre_close, vol, pct_chg
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20200101' AND trade_date <= '20260506'
  AND pre_close > 0 AND open > 0 AND close > 0 AND vol > 0
  AND rand() % 20 = 0
ORDER BY ts_code, trade_date
"""

df = parse_tab(ch_query(q, timeout=300))
df = num_cols(df, ['open','close','pre_close','vol','pct_chg'])
print(f"采样数据量: {len(df)} 条")

# 用pandas计算前后日关系
df = df.sort_values(['ts_code', 'trade_date'])
df['prev_pct'] = df.groupby('ts_code')['pct_chg'].shift(1)
df['prev_vol'] = df.groupby('ts_code')['vol'].shift(1)
df['prev_open'] = df.groupby('ts_code')['open'].shift(1)
df['prev_close'] = df.groupby('ts_code')['close'].shift(1)
df['next_open'] = df.groupby('ts_code')['open'].shift(-1)
df['next_close'] = df.groupby('ts_code')['close'].shift(-1)
df['next_pct'] = df.groupby('ts_code')['pct_chg'].shift(-1)

df = df.dropna(subset=['prev_pct', 'prev_vol', 'next_open', 'next_close'])
print(f"有效样本: {len(df)} 条")

# 计算特征
df['vol_ratio'] = df['vol'] / df['prev_vol']
df['prev_turnover_proxy'] = df['prev_vol'] / df['pre_close']  # 用成交量/前收作为换手代理

# 定义低开高走强信号 (当天的)
df['is_lo'] = ((df['open'] - df['pre_close']) / df['pre_close'] * 100 < -1)
df['is_hg'] = ((df['close'] - df['open']) / df['open'] * 100 > 2)
df['is_strong'] = df['is_lo'] & df['is_hg'] & (df['close'] > df['pre_close'])

# 次日收益
df['next_return'] = (df['next_close'] - df['next_open']) / df['next_open'] * 100

# ============================================================
# 策略1: 基础筛选 - 前日大涨5%+ (高概率低开群体)
# ============================================================
print("\n【策略1】前日大涨5%+ → 次日低开高走")
s1 = df[df['prev_pct'] >= 5].copy()
s1_lo = s1[s1['is_lo'] == True]
print(f"  前日大涨样本: {len(s1)}")
print(f"  其中低开: {len(s1_lo)} ({len(s1_lo)/len(s1)*100:.1f}%)")
if len(s1_lo) > 0:
    print(f"  低开后高走: {(s1_lo['is_hg'].sum()/len(s1_lo)*100):.2f}%")
    print(f"  强信号: {(s1_lo['is_strong'].sum()/len(s1_lo)*100):.2f}%")

# ============================================================
# 策略2: 前日跌停 → 次日低开高走 (超跌反弹)
# ============================================================
print("\n【策略2】前日跌停 → 次日低开高走 (超跌反弹)")
s2 = df[df['prev_pct'] <= -9.5].copy()
s2_lo = s2[s2['is_lo'] == True]
print(f"  前日跌停样本: {len(s2)}")
print(f"  其中低开: {len(s2_lo)} ({len(s2_lo)/len(s2)*100:.1f}%)")
if len(s2_lo) > 0:
    print(f"  低开后高走: {(s2_lo['is_hg'].sum()/len(s2_lo)*100):.2f}%")
    print(f"  强信号: {(s2_lo['is_strong'].sum()/len(s2_lo)*100):.2f}%")

# ============================================================
# 策略3: 放量后缩量 → 次日低开高走 (最优组合)
# ============================================================
print("\n【策略3】放量1.5-2x → 次日低开高走 (量价最优组合)")
s3 = df[(df['vol_ratio'] >= 1.5) & (df['vol_ratio'] < 2)].copy()
s3_lo = s3[s3['is_lo'] == True]
print(f"  放量1.5-2x样本: {len(s3)}")
print(f"  其中低开: {len(s3_lo)} ({len(s3_lo)/len(s3)*100:.1f}%)")
if len(s3_lo) > 0:
    print(f"  低开后高走: {(s3_lo['is_hg'].sum()/len(s3_lo)*100):.2f}%")
    print(f"  强信号: {(s3_lo['is_strong'].sum()/len(s3_lo)*100):.2f}%")
    print(f"  次日日内收益均值: {s3_lo['next_return'].mean():.3f}%")
    print(f"  次日胜率: {(s3_lo['next_return'] > 0).mean()*100:.2f}%")

# ============================================================
# 策略4: 综合筛选 - 多因子共振
# ============================================================
print("\n【策略4】多因子共振筛选 (大涨 + 适中换手 + 放量)")
# 使用综合条件
combo = df[
    (df['prev_pct'] >= 5) &  # 前日大涨
    (df['vol_ratio'] >= 0.8) & (df['vol_ratio'] < 3) &  # 量比正常到放量
    (df['is_lo'] == True)  # 当日低开
].copy()

print(f"  筛选样本: {len(combo)}")
if len(combo) > 0:
    print(f"  低开后高走: {(combo['is_hg'].sum()/len(combo)*100):.2f}%")
    print(f"  强信号: {(combo['is_strong'].sum()/len(combo)*100):.2f}%")
    print(f"  次日日内收益均值: {combo['next_return'].mean():.3f}%")
    print(f"  次日胜率: {(combo['next_return'] > 0).mean()*100:.2f}%")
    print(f"  次日收益中位数: {combo['next_return'].median():.3f}%")
    
    # 按不同子条件进一步分析
    print("\n  --- 细分分析 ---")
    for label, mask in [
        ("仅低开不反转", ~combo['is_strong']),
        ("强信号(低开高走收盘>前收)", combo['is_strong']),
    ]:
        subset = combo[mask]
        if len(subset) > 0:
            print(f"  {label} ({len(subset)}条): 次日收益均值={subset['next_return'].mean():.3f}%, 胜率={(subset['next_return']>0).mean()*100:.1f}%")

# ============================================================
# 策略5: 按月分析策略稳定性
# ============================================================
print("\n【策略5】按月分析策略稳定性 (前日大涨+低开)")
df['month'] = pd.to_datetime(df['trade_date']).dt.month
monthly = df[(df['prev_pct'] >= 5) & (df['is_lo'] == True)].groupby('month').agg(
    cnt=('ts_code', 'count'),
    hg_rate=('is_hg', 'mean'),
    next_ret_mean=('next_return', 'mean'),
    next_win_rate=('next_return', lambda x: (x > 0).mean() * 100),
)
print(monthly.to_string())

# 保存回测结果
results = {
    'strategy1': {
        'name': '前日大涨5%+ → 次日低开',
        'lo_count': int(len(s1_lo)),
        'hg_rate': float(s1_lo['is_hg'].mean() * 100) if len(s1_lo) > 0 else 0,
        'strong_rate': float(s1_lo['is_strong'].mean() * 100) if len(s1_lo) > 0 else 0,
    },
    'strategy2': {
        'name': '前日跌停 → 次日低开 (超跌反弹)',
        'lo_count': int(len(s2_lo)),
        'hg_rate': float(s2_lo['is_hg'].mean() * 100) if len(s2_lo) > 0 else 0,
        'strong_rate': float(s2_lo['is_strong'].mean() * 100) if len(s2_lo) > 0 else 0,
    },
    'strategy3': {
        'name': '放量1.5-2x → 次日低开',
        'lo_count': int(len(s3_lo)),
        'hg_rate': float(s3_lo['is_hg'].mean() * 100) if len(s3_lo) > 0 else 0,
        'strong_rate': float(s3_lo['is_strong'].mean() * 100) if len(s3_lo) > 0 else 0,
        'next_ret_mean': float(s3_lo['next_return'].mean()) if len(s3_lo) > 0 else 0,
        'next_win_rate': float((s3_lo['next_return'] > 0).mean() * 100) if len(s3_lo) > 0 else 0,
    },
    'strategy4': {
        'name': '多因子共振 (大涨+正常量+低开)',
        'count': int(len(combo)),
        'hg_rate': float(combo['is_hg'].mean() * 100) if len(combo) > 0 else 0,
        'strong_rate': float(combo['is_strong'].mean() * 100) if len(combo) > 0 else 0,
        'next_ret_mean': float(combo['next_return'].mean()) if len(combo) > 0 else 0,
        'next_win_rate': float((combo['next_return'] > 0).mean() * 100) if len(combo) > 0 else 0,
    },
}

import json
with open('backtest_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print("\n✅ 回测完成, backtest_results.json 已保存")
