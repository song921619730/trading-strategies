#!/usr/bin/env python3
"""
低开高走选股策略回测 - v13实验
基于阶段1分析结果构建的回测脚本

策略逻辑:
1. 多因子共振: 前日大涨5%+ + 量比0.8-3x + 当日低开
2. 放量反转: 前日量比1.5-2x + 当日低开
3. 超跌反弹: 前日跌停 + 当日低开

核心发现:
- 放量1.5-2x是最强独立因子 (低开后高走率44.76%)
- 前日跌停是最佳低开预测因子 (54.7%低开率, 44.7%反转率)
- 多因子共振高走率40.5%, 强信号率35.6%
"""

import requests
import pandas as pd
import numpy as np
import json

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

def load_data():
    """加载回测数据"""
    q = """
    SELECT ts_code, trade_date, open, close, pre_close, vol, pct_chg
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101' AND trade_date <= '20260506'
      AND pre_close > 0 AND open > 0 AND close > 0 AND vol > 0
      AND rand() % 20 = 0
    ORDER BY ts_code, trade_date
    """
    df = parse_tab(ch_query(q, timeout=300))
    df = num_cols(df, ['open','close','pre_close','vol','pct_chg'])
    
    df = df.sort_values(['ts_code', 'trade_date'])
    df['prev_pct'] = df.groupby('ts_code')['pct_chg'].shift(1)
    df['prev_vol'] = df.groupby('ts_code')['vol'].shift(1)
    df['next_open'] = df.groupby('ts_code')['open'].shift(-1)
    df['next_close'] = df.groupby('ts_code')['close'].shift(-1)
    df['next_pct'] = df.groupby('ts_code')['pct_chg'].shift(-1)
    
    df = df.dropna(subset=['prev_pct', 'prev_vol', 'next_open', 'next_close'])
    return df

def calculate_signals(df):
    """生成信号"""
    df['vol_ratio'] = df['vol'] / df['prev_vol']
    
    # 低开信号
    df['is_lo'] = ((df['open'] - df['pre_close']) / df['pre_close'] * 100 < -1)
    df['is_hg'] = ((df['close'] - df['open']) / df['open'] * 100 > 2)
    df['is_strong'] = df['is_lo'] & df['is_hg'] & (df['close'] > df['pre_close'])
    
    # 次日收益
    df['next_return'] = (df['next_close'] - df['next_open']) / df['next_open'] * 100
    
    # 策略信号
    # 策略1: 多因子共振
    df['signal_combo'] = (
        (df['prev_pct'] >= 5) & 
        (df['vol_ratio'] >= 0.8) & (df['vol_ratio'] < 3) & 
        df['is_lo']
    )
    
    # 策略2: 放量反转
    df['signal_volume'] = (
        (df['vol_ratio'] >= 1.5) & (df['vol_ratio'] < 2) & 
        df['is_lo']
    )
    
    # 策略3: 超跌反弹
    df['signal_limitdown'] = (
        (df['prev_pct'] <= -9.5) & 
        df['is_lo']
    )
    
    return df

def run_backtest(df, signals=None):
    """运行回测"""
    results = {}
    
    for name, col in [
        ('多因子共振', 'signal_combo'),
        ('放量反转', 'signal_volume'),
        ('超跌反弹', 'signal_limitdown'),
    ]:
        subset = df[df[col] == True]
        if len(subset) == 0:
            continue
            
        results[name] = {
            '样本数': int(len(subset)),
            '高走率': float(subset['is_hg'].mean() * 100),
            '强信号率': float(subset['is_strong'].mean() * 100),
            '次日收益均值': float(subset['next_return'].mean()),
            '次日胜率': float((subset['next_return'] > 0).mean() * 100),
            '次日收益中位数': float(subset['next_return'].median()),
        }
    
    # 基准对比
    baseline = {
        '样本数': int(len(df)),
        '低开率': float(df['is_lo'].mean() * 100),
        '低开后高走率': float(df.loc[df['is_lo'], 'is_hg'].mean() * 100),
        '次日收益均值': float(df['next_return'].mean()),
        '次日胜率': float((df['next_return'] > 0).mean() * 100),
    }
    
    return results, baseline

if __name__ == "__main__":
    print("加载数据...")
    df = load_data()
    print(f"有效样本: {len(df)} 条")
    
    print("计算信号...")
    df = calculate_signals(df)
    
    print("运行回测...")
    results, baseline = run_backtest(df)
    
    print("\n=== 基准对比 ===")
    for k, v in baseline.items():
        print(f"  {k}: {v}")
    
    print("\n=== 策略表现 ===")
    for name, metrics in results.items():
        print(f"\n--- {name} ---")
        for k, v in metrics.items():
            print(f"  {k}: {v}")
    
    # 保存结果
    with open('backtest_results.json', 'w', encoding='utf-8') as f:
        json.dump({
            'baseline': baseline,
            'strategies': results,
        }, f, ensure_ascii=False, indent=2)
    print("\n✅ 回测结果已保存至 backtest_results.json")
