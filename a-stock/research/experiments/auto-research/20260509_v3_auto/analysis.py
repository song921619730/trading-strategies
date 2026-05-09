#!/usr/bin/env python3
"""
实验 20260509_v3_auto: 涨停股资金流向结构 vs 次日溢价
假设：涨停日大单/超大单净流入占比高的股票，次日溢价率和连板概率显著更高
"""
import requests
import pandas as pd
import numpy as np
from io import StringIO
from datetime import datetime, timedelta

URL = 'http://172.24.224.1:8123/'
AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(query, fmt='TabSeparatedWithNames'):
    full = f"{query} FORMAT {fmt}"
    r = requests.get(URL, params={'query': full}, auth=AUTH, timeout=120)
    r.raise_for_status()
    return r.text

def ch_to_df(text):
    return pd.read_csv(StringIO(text), sep='\t')

# ============================================================
# 步骤 1: 获取所有涨停记录（U=涨停），排除 ST 和 北交所
# ============================================================
print("步骤 1: 获取涨停股票列表...")
q = """
SELECT trade_date, ts_code, name, industry, close, pct_chg, amount, 
       turnover_ratio, fd_amount, open_times, limit_times, up_stat,
       float_mv, total_mv, limit
FROM tushare.tushare_limit_list_d FINAL
WHERE limit = 'U'
  AND trade_date >= '20260101' AND trade_date <= '20260507'
  AND NOT (ts_code LIKE '8%' OR ts_code LIKE '4%')
"""
limit_df = ch_to_df(ch_query(q))
print(f"  涨停记录数: {len(limit_df)}")
print(f"  日期范围: {limit_df['trade_date'].min()} ~ {limit_df['trade_date'].max()}")
print(f"  up_stat 示例: {limit_df['up_stat'].head(20).tolist()}")

# 解析 up_stat 获取连板数
# up_stat like "1/1" means 1-board, "2/3" means 2-board in a 3-day streak
def parse_board_count(up_stat):
    if pd.isna(up_stat) or up_stat == '':
        return 0
    parts = str(up_stat).split('/')
    try:
        return int(parts[0])
    except:
        return 0

limit_df['board_count'] = limit_df['up_stat'].apply(parse_board_count)
print(f"  连板数分布: {limit_df['board_count'].value_counts().sort_index().to_dict()}")

# ============================================================
# 步骤 2: 获取这些涨停股当日的资金流向数据
# ============================================================
print("\n步骤 2: 获取资金流向数据...")
# Build a list of (ts_code, trade_date) pairs
pairs = limit_df[['ts_code', 'trade_date']].copy()
pairs['trade_date'] = pd.to_datetime(pairs['trade_date'])
# Convert to string YYYYMMDD for ClickHouse
pairs['date_str'] = pairs['trade_date'].dt.strftime('%Y-%m-%d')

# We'll chunk to avoid huge queries
all_mf = []
unique_dates = sorted(pairs['date_str'].unique())
print(f"  涉及交易日数: {len(unique_dates)}")

for i in range(0, len(unique_dates), 30):
    date_chunk = unique_dates[i:i+30]
    date_list = "','".join(date_chunk)
    q2 = f"""
    SELECT ts_code, toDate(trade_date) as trade_date,
           buy_lg_amount, sell_lg_amount, buy_elg_amount, sell_elg_amount,
           buy_sm_amount, sell_sm_amount, buy_md_amount, sell_md_amount,
           net_mf_amount
    FROM tushare.tushare_moneyflow FINAL
    WHERE trade_date IN ('{date_list}')
    """
    try:
        mf_chunk = ch_to_df(ch_query(q2))
        all_mf.append(mf_chunk)
    except Exception as e:
        print(f"  警告: 日期块 {date_chunk[0]} 查询失败: {e}")

if all_mf:
    mf_df = pd.concat(all_mf, ignore_index=True)
    print(f"  资金流向记录数: {len(mf_df)}")
else:
    print("  无资金流向数据")
    exit(1)

# ============================================================
# 步骤 3: 合并涨停和资金流向数据，计算特征
# ============================================================
print("\n步骤 3: 合并数据并计算特征...")
limit_df['trade_date'] = pd.to_datetime(limit_df['trade_date'])
# 确保 trade_date 类型一致
mf_df['trade_date'] = pd.to_datetime(mf_df['trade_date'])
merged = limit_df.merge(mf_df, on=['ts_code', 'trade_date'], how='inner')
print(f"  成功匹配: {len(merged)} / {len(limit_df)}")

# 计算资金流向特征
merged['lg_net'] = merged['buy_lg_amount'] - merged['sell_lg_amount']
merged['elg_net'] = merged['buy_elg_amount'] - merged['sell_elg_amount']
merged['large_net'] = merged['lg_net'] + merged['elg_net']
merged['total_amount'] = merged['amount']

# 大单超大单净买入占比
merged['large_net_ratio'] = merged['large_net'] / (merged['total_amount'] * 10000)  # amount in 千元
merged['elg_ratio'] = merged['elg_net'] / (merged['total_amount'] * 10000)

# 换手率
merged['turnover'] = merged['turnover_ratio']

# 开板次数
merged['open_count'] = merged['open_times']

print(f"\n特征统计:")
print(merged[['board_count', 'large_net_ratio', 'elg_ratio', 'turnover', 'open_count']].describe())

# ============================================================
# 步骤 4: 获取次日数据计算溢价
# ============================================================
print("\n步骤 4: 获取次日行情计算溢价...")
# Get all unique next trading dates
next_dates = (merged['trade_date'] + timedelta(days=1)).dt.strftime('%Y-%m-%d').unique()
next_date_list = "','".join(sorted(next_dates)[:200])  # chunk

all_next = []
for i in range(0, len(sorted(next_dates)), 30):
    nd_chunk = sorted(next_dates)[i:i+30]
    nd_list = "','".join(nd_chunk)
    q3 = f"""
    SELECT ts_code, toDate(trade_date) as trade_date, open, high, low, close, pct_chg, vol
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date IN ('{nd_list}')
    """
    try:
        next_chunk = ch_to_df(ch_query(q3))
        all_next.append(next_chunk)
    except Exception as e:
        print(f"  警告: 次日数据查询失败: {e}")

if all_next:
    next_df = pd.concat(all_next, ignore_index=True)
    next_df['trade_date'] = pd.to_datetime(next_df['trade_date'])
    merged['next_date'] = merged['trade_date'] + timedelta(days=1)
    result = merged.merge(next_df, left_on=['ts_code', 'next_date'], right_on=['ts_code', 'trade_date'], how='left', suffixes=('', '_next'))
    print(f"  匹配次日数据: {result['open'].notna().sum()} / {len(result)}")
else:
    print("  次日数据获取失败")
    exit(1)

# ============================================================
# 步骤 5: 计算溢价指标
# ============================================================
print("\n步骤 5: 计算溢价指标...")
r = result.copy()
# 溢价率 = (次日最高价 - 涨停收盘价) / 涨停收盘价
r['premium_rate'] = (r['high'] - r['close']) / r['close']
# 开盘溢价 = (次日开盘 - 涨停收盘价) / 涨停收盘价
r['open_premium'] = (r['open'] - r['close']) / r['close']
# 次日是否涨停 (pct_chg >= 9.9)
r['next_limit_up'] = (r['pct_chg'] >= 9.9).astype(int)
# 次日是否盈利 (收盘价 > 涨停收盘价)
r['next_profit'] = (r['close'] > r['close_next']).astype(int)
# 实际盈亏
r['next_return'] = r['pct_chg']

# 排除无效数据
r = r[r['open'].notna()].copy()
print(f"  有效样本: {len(r)}")

# ============================================================
# 步骤 6: 按大单净买入占比分组分析
# ============================================================
print("\n步骤 6: 按大单净买入占比分组分析...")

# 分5组
r['large_net_quintile'] = pd.qcut(r['large_net_ratio'].fillna(0), 5, labels=['Q1(最低)', 'Q2', 'Q3', 'Q4', 'Q5(最高)'], duplicates='drop')

group_stats = r.groupby('large_net_quintile', observed=True).agg(
    sample_count=('ts_code', 'count'),
    avg_premium=('premium_rate', 'mean'),
    median_premium=('premium_rate', 'median'),
    avg_open_premium=('open_premium', 'mean'),
    limit_up_rate=('next_limit_up', 'mean'),
    avg_next_return=('next_return', 'mean'),
    win_rate=('next_return', lambda x: (x > 0).mean()),
).round(4)

print("\n【大单净买入占比分组表现】")
print(group_stats.to_string())

# ============================================================
# 步骤 7: 按连板高度 x 资金流向交叉分析
# ============================================================
print("\n\n步骤 7: 连板高度 x 资金流向交叉分析...")
r['board_group'] = pd.cut(r['board_count'], bins=[0, 1, 2, 3, 100], labels=['1板', '2板', '3板', '4板+'])
r['large_direction'] = np.where(r['large_net_ratio'] > 0, '大单净买入', '大单净卖出')

cross = r.groupby(['board_group', 'large_direction'], observed=True).agg(
    count=('ts_code', 'count'),
    avg_premium=('premium_rate', 'mean'),
    limit_up_rate=('next_limit_up', 'mean'),
    win_rate=('next_return', lambda x: (x > 0).mean()),
    avg_next_return=('next_return', 'mean'),
).round(4)

print("\n【连板高度 x 资金流向交叉表】")
print(cross.to_string())

# ============================================================
# 步骤 8: 统计检验
# ============================================================
from scipy import stats

print("\n\n步骤 8: 统计检验...")

# Q5 vs Q1 的溢价率差异
q5 = r[r['large_net_quintile'] == 'Q5(最高)']['premium_rate'].dropna()
q1 = r[r['large_net_quintile'] == 'Q1(最低)']['premium_rate'].dropna()
t_stat, p_val = stats.ttest_ind(q5, q1)
print(f"\nQ5 vs Q1 溢价率 t检验: t={t_stat:.4f}, p={p_val:.6f}")

# 大单净买入 vs 净卖出的连板概率差异
buy_grp = r[r['large_direction'] == '大单净买入']['next_limit_up']
sell_grp = r[r['large_direction'] == '大单净卖出']['next_limit_up']
chi2, p_chi, dof, expected = stats.chi2_contingency(pd.crosstab(r['large_direction'], r['next_limit_up']))
print(f"大单方向 vs 连板 卡方检验: chi2={chi2:.4f}, p={p_chi:.6f}")

# ============================================================
# 步骤 9: 开板次数分析
# ============================================================
print("\n\n步骤 9: 开板次数 x 资金流向分析...")
r['open_category'] = pd.cut(r['open_count'], bins=[-1, 0, 1, 3, 100], labels=['未开板', '开1次', '开2-3次', '开4次+'])
open_analysis = r.groupby('open_category', observed=True).agg(
    count=('ts_code', 'count'),
    avg_large_ratio=('large_net_ratio', 'mean'),
    avg_premium=('premium_rate', 'mean'),
    limit_up_rate=('next_limit_up', 'mean'),
    win_rate=('next_return', lambda x: (x > 0).mean()),
).round(4)
print("\n【开板次数分析】")
print(open_analysis.to_string())

# ============================================================
# 步骤 10: 生成可操作的分层策略信号
# ============================================================
print("\n\n步骤 10: 生成可操作策略信号...")
# 最优条件组合
optimal = r[(r['board_count'] == 2) & (r['large_net_ratio'] > 0) & (r['open_count'] == 0)]
print(f"\n最优条件: 2板 + 大单净买入 + 未开板")
print(f"  样本数: {len(optimal)}")
print(f"  平均溢价: {optimal['premium_rate'].mean():.4f}")
print(f"  平均次日收益: {optimal['next_return'].mean():.2f}%")
print(f"  次日涨停率: {optimal['next_limit_up'].mean():.2%}")
print(f"  胜率: {(optimal['next_return'] > 0).mean():.2%}")

# 对比基准
baseline = r[(r['board_count'] == 2)]
print(f"\n对比基准: 仅2板")
print(f"  样本数: {len(baseline)}")
print(f"  平均溢价: {baseline['premium_rate'].mean():.4f}")
print(f"  平均次日收益: {baseline['next_return'].mean():.2f}%")
print(f"  次日涨停率: {baseline['next_limit_up'].mean():.2%}")
print(f"  胜率: {(baseline['next_return'] > 0).mean():.2%}")

# 最差条件
worst = r[(r['board_count'] == 1) & (r['large_net_ratio'] < 0)]
print(f"\n最差条件: 1板 + 大单净卖出")
print(f"  样本数: {len(worst)}")
print(f"  平均溢价: {worst['premium_rate'].mean():.4f}")
print(f"  平均次日收益: {worst['next_return'].mean():.2f}%")
print(f"  胜率: {(worst['next_return'] > 0).mean():.2%}")

# ============================================================
# 保存数据供后续分析
# ============================================================
r.to_csv('analysis_data.csv', index=False)
print(f"\n数据已保存到 analysis_data.csv ({len(r)} 条记录)")
