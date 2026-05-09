#!/usr/bin/env python3
"""
补充分析：涨停股开盘溢价预测因子 + 资金流结构深度分析
重点关注：资金流结构对次日开盘溢价（可操作信号）的预测力
"""
import requests
import pandas as pd
import numpy as np
from io import StringIO

URL = 'http://172.24.224.1:8123/'
AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(query, fmt='TabSeparatedWithNames'):
    full = f"{query} FORMAT {fmt}"
    r = requests.get(URL, params={'query': full}, auth=AUTH, timeout=120)
    r.raise_for_status()
    return r.text

def ch_to_df(text):
    return pd.read_csv(StringIO(text), sep='\t')

# 加载已有数据
r = pd.read_csv('analysis_data.csv')
r['trade_date'] = pd.to_datetime(r['trade_date'])
r['next_trade_date'] = pd.to_datetime(r['next_trade_date'])

print("=== 补充分析 ===\n")

# ============================================================
# 1. 开盘溢价 (open_premium) 作为核心预测目标
# ============================================================
print("【1. 开盘溢价分布】")
print(r['open_premium'].describe())

# 按 open_premium 分3组
r['open_prem_group'] = pd.qcut(r['open_premium'], 3, labels=['低溢价', '中溢价', '高溢价'], duplicates='drop')

# 各组特征
op_analysis = r.groupby('open_prem_group', observed=True).agg(
    count=('ts_code', 'count'),
    avg_large_ratio=('large_net_ratio', 'mean'),
    avg_elg_ratio=('elg_ratio', 'mean'),
    avg_turnover=('turnover_ratio', 'mean'),
    avg_open_times=('open_times', 'mean'),
    avg_premium=('premium_rate', 'mean'),
    avg_board=('board_count', 'mean'),
    avg_next_return=('next_return', 'mean'),
).round(4)
print("\n开盘溢价分组特征:")
print(op_analysis.to_string())

# ============================================================
# 2. 大单净买入占比 vs 开盘溢价的回归分析
# ============================================================
print("\n\n【2. 大单净买入占比 vs 开盘溢价 - 相关性】")
corr = r['large_net_ratio'].corr(r['open_premium'])
print(f"  相关系数: {corr:.4f}")
corr2 = r['elg_ratio'].corr(r['open_premium'])
print(f"  超大单占比 vs 开盘溢价: {corr2:.4f}")
corr3 = r['large_net_ratio'].corr(r['premium_rate'])
print(f"  大单占比 vs 最高溢价: {corr3:.4f}")
corr4 = r['large_net_ratio'].corr(r['close_premium'])
print(f"  大单占比 vs 收盘溢价: {corr4:.4f}")

# 大单净买入占比 vs 换手率
corr5 = r['large_net_ratio'].corr(r['turnover_ratio'])
print(f"  大单占比 vs 换手率: {corr5:.4f}")

# ============================================================
# 3. 分连板高度的开盘溢价特征
# ============================================================
print("\n\n【3. 分连板高度的开盘溢价特征】")
r['board_label'] = r['board_count'].apply(lambda x: f'{int(x)}板')
board_analysis = r.groupby('board_label', observed=True).agg(
    count=('ts_code', 'count'),
    avg_large_ratio=('large_net_ratio', 'mean'),
    avg_open_premium=('open_premium', 'mean'),
    median_open_premium=('open_premium', 'median'),
    high_open_prem=('open_premium', lambda x: (x > 0.03).mean()),  # 高开>3%的比例
    avg_turnover=('turnover_ratio', 'mean'),
    avg_open_times=('open_times', 'mean'),
).round(4)
print(board_analysis.to_string())

# ============================================================
# 4. 综合评分模型：预测次日高开 > 3%
# ============================================================
print("\n\n【4. 综合评分 - 预测高开 > 3%】")
r['high_open'] = (r['open_premium'] > 0.03).astype(int)
print(f"  高开>3%比例: {r['high_open'].mean():.2%}")

# 大单净买入占比分档
r['mf_quartile'] = pd.qcut(r['large_net_ratio'], 4, labels=['Q1', 'Q2', 'Q3', 'Q4'], duplicates='drop')

# 各因素与高开的关系
for col in ['mf_quartile', 'board_label']:
    print(f"\n  {col}:")
    grp = r.groupby(col, observed=True).agg(
        count=('ts_code', 'count'),
        high_open_rate=('high_open', 'mean'),
        avg_large_ratio=('large_net_ratio', 'mean'),
    ).round(4)
    print(grp.to_string())

# ============================================================
# 5. 市值分组分析
# ============================================================
print("\n\n【5. 市值分组分析】")
r['mv_group'] = pd.qcut(r['total_mv'], 4, labels=['小市值', '中小', '中大', '大市值'], duplicates='drop')
mv_analysis = r.groupby('mv_group', observed=True).agg(
    count=('ts_code', 'count'),
    avg_large_ratio=('large_net_ratio', 'mean'),
    avg_open_premium=('open_premium', 'mean'),
    avg_turnover=('turnover_ratio', 'mean'),
    high_open_rate=('high_open', 'mean'),
).round(4)
print(mv_analysis.to_string())

# ============================================================
# 6. 换手率与资金流向的关系
# ============================================================
print("\n\n【6. 换手率分组分析】")
r['to_group'] = pd.qcut(r['turnover_ratio'], 4, labels=['低换手', '中低', '中高', '高换手'], duplicates='drop')
to_analysis = r.groupby('to_group', observed=True).agg(
    count=('ts_code', 'count'),
    avg_large_ratio=('large_net_ratio', 'mean'),
    avg_open_premium=('open_premium', 'mean'),
    avg_board=('board_count', 'mean'),
    high_open_rate=('high_open', 'mean'),
).round(4)
print(to_analysis.to_string())

# ============================================================
# 7. 关键信号：大单净买入 + 未开板 + 适当换手
# ============================================================
print("\n\n【7. 高信号组合分析】")
# 强信号：大单净买入(top 50%) + 未开板 + 换手率适中(5-15%)
strong_signal = r[(r['large_net_ratio'] > r['large_net_ratio'].median()) & 
                  (r['open_times'] == 0) & 
                  (r['turnover_ratio'] >= 5) & (r['turnover_ratio'] <= 15)]
print(f"强信号样本数: {len(strong_signal)}")
if len(strong_signal) > 0:
    print(f"  平均开盘溢价: {strong_signal['open_premium'].mean()*100:.2f}%")
    print(f"  高开>3%比例: {strong_signal['high_open'].mean():.2%}")
    print(f"  平均最高溢价: {strong_signal['premium_rate'].mean()*100:.2f}%")

# 弱信号：大单净卖出 或 频繁开板
weak_signal = r[(r['large_net_ratio'] < 0) | (r['open_times'] >= 3)]
print(f"\n弱信号样本数: {len(weak_signal)}")
if len(weak_signal) > 0:
    print(f"  平均开盘溢价: {weak_signal['open_premium'].mean()*100:.2f}%")
    print(f"  高开>3%比例: {weak_signal['high_open'].mean():.2%}")

# 基准
print(f"\n基准(全部):")
print(f"  平均开盘溢价: {r['open_premium'].mean()*100:.2f}%")
print(f"  高开>3%比例: {r['high_open'].mean():.2%}")

# 保存补充数据
r.to_csv('analysis_data_full.csv', index=False)
print("\n数据已保存到 analysis_data_full.csv")
