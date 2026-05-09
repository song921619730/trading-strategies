#!/usr/bin/env python3
"""
实验 20260509_v3_auto: 涨停股资金流向结构 vs 次日溢价 (修正版)
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
# 步骤 1: 获取所有涨停记录
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

def parse_board_count(up_stat):
    if pd.isna(up_stat) or up_stat == '':
        return 0
    parts = str(up_stat).split('/')
    try:
        return int(parts[0])
    except:
        return 0

limit_df['board_count'] = limit_df['up_stat'].apply(parse_board_count)
limit_df['trade_date'] = pd.to_datetime(limit_df['trade_date'])

# ============================================================
# 步骤 2: 获取资金流向数据
# ============================================================
print("\n步骤 2: 获取资金流向数据...")
unique_dates = sorted(limit_df['trade_date'].dt.strftime('%Y-%m-%d').unique())
print(f"  涉及交易日: {unique_dates}")

all_mf = []
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
        print(f"  警告: {e}")

mf_df = pd.concat(all_mf, ignore_index=True)
mf_df['trade_date'] = pd.to_datetime(mf_df['trade_date'])
print(f"  资金流向记录数: {len(mf_df)}")

# ============================================================
# 步骤 3: 合并涨停和资金流向
# ============================================================
print("\n步骤 3: 合并数据...")
merged = limit_df.merge(mf_df, on=['ts_code', 'trade_date'], how='inner')
print(f"  匹配: {len(merged)}")

# 检查单位
print(f"\n  amount (limit_list_d) 样例: {merged['amount'].head(3).tolist()}")
print(f"  buy_elg_amount 样例: {merged['buy_elg_amount'].head(3).tolist()}")

# amount 在 limit_list_d 中是 千元 (thousands of yuan)
# moneyflow 中的 amount 也是 千元
# 验证: 总成交额 = buy + sell 各种单
merged['mf_total_buy'] = merged['buy_sm_amount'] + merged['buy_md_amount'] + merged['buy_lg_amount'] + merged['buy_elg_amount']
merged['mf_total_sell'] = merged['sell_sm_amount'] + merged['sell_md_amount'] + merged['sell_lg_amount'] + merged['sell_elg_amount']
merged['mf_total'] = merged['mf_total_buy'] + merged['mf_total_sell']
print(f"  limit_list_d amount: {merged['amount'].describe()}")
print(f"  mf_total (buy+sell): {merged['mf_total'].describe()}")
print(f"  比值 mf_total/amount: {(merged['mf_total'] / merged['amount']).describe()}")

# 大单超大单净买入
merged['lg_net'] = merged['buy_lg_amount'] - merged['sell_lg_amount']
merged['elg_net'] = merged['buy_elg_amount'] - merged['sell_elg_amount']
merged['large_net'] = merged['lg_net'] + merged['elg_net']

# 用 mf_total 作为分母 (千元)
merged['large_net_ratio'] = merged['large_net'] / merged['mf_total']
merged['elg_ratio'] = merged['elg_net'] / merged['mf_total']

print(f"\n  large_net_ratio 统计: {merged['large_net_ratio'].describe()}")

# ============================================================
# 步骤 4: 获取实际下一交易日数据
# ============================================================
print("\n步骤 4: 获取下一交易日数据...")

# 获取所有交易日历
cal_q = """
SELECT cal_date as cal_date, is_open 
FROM tushare.tushare_trade_cal FINAL
WHERE exchange = 'SSE'
  AND cal_date >= '20260101' AND cal_date <= '20260515'
ORDER BY cal_date
"""
cal_df = ch_to_df(ch_query(cal_q))
cal_df['cal_date'] = pd.to_datetime(cal_df['cal_date'])
trade_days = sorted(cal_df[cal_df['is_open'] == 1]['cal_date'].tolist())
print(f"  交易日数: {len(trade_days)}")

# 为每个涨停日找到下一交易日
def get_next_trade_day(d):
    for td in trade_days:
        if td > d:
            return td
    return None

merged['next_trade_date'] = merged['trade_date'].apply(get_next_trade_day)
valid_next = merged[merged['next_trade_date'].notna()].copy()
print(f"  有下一交易日: {len(valid_next)}")

# 获取下一交易日行情
next_dates = sorted(valid_next['next_trade_date'].dt.strftime('%Y-%m-%d').unique())
print(f"  下一交易日列表: {next_dates}")

all_next = []
for i in range(0, len(next_dates), 30):
    nd_chunk = next_dates[i:i+30]
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
        print(f"  警告: {e}")

next_df = pd.concat(all_next, ignore_index=True)
next_df['trade_date'] = pd.to_datetime(next_df['trade_date'])

result = valid_next.merge(next_df, left_on=['ts_code', 'next_trade_date'], 
                           right_on=['ts_code', 'trade_date'], 
                           how='left', suffixes=('', '_next'))
print(f"  匹配次日数据: {result['open'].notna().sum()} / {len(result)}")

# ============================================================
# 步骤 5: 计算溢价指标
# ============================================================
print("\n步骤 5: 计算溢价指标...")
r = result[result['open'].notna()].copy()

# 溢价率 = (次日最高价 - 涨停收盘价) / 涨停收盘价
r['premium_rate'] = (r['high'] - r['close']) / r['close']
r['open_premium'] = (r['open'] - r['close']) / r['close']
r['close_premium'] = (r['close_next'] - r['close']) / r['close']
r['next_limit_up'] = (r['pct_chg'] >= 9.9).astype(int)
r['next_return'] = r['pct_chg']

print(f"  有效样本: {len(r)}")
print(f"\n  次日收益分布:")
print(r['next_return'].describe())
print(f"\n  溢价率分布:")
print(r['premium_rate'].describe())

# 统计涨停和跌停
print(f"\n  次日涨停数: {r['next_limit_up'].sum()}")
print(f"  次日跌停数 (pct_chg <= -9.9): {(r['pct_chg'] <= -9.9).sum()}")
print(f"  次日收涨比例: {(r['next_return'] > 0).mean():.2%}")
print(f"  次日收平比例: {(r['next_return'] == 0).mean():.2%}")
print(f"  次日收跌比例: {(r['next_return'] < 0).mean():.2%}")

# ============================================================
# 步骤 6: 按大单净买入占比分组分析
# ============================================================
print("\n\n步骤 6: 按大单净买入占比分组分析...")
r['large_net_quintile'] = pd.qcut(r['large_net_ratio'], 5, 
    labels=['Q1(净卖出最多)', 'Q2', 'Q3', 'Q4', 'Q5(净买入最多)'], duplicates='drop')

group_stats = r.groupby('large_net_quintile', observed=True).agg(
    sample_count=('ts_code', 'count'),
    avg_premium=('premium_rate', 'mean'),
    median_premium=('premium_rate', 'median'),
    avg_open_premium=('open_premium', 'mean'),
    avg_close_premium=('close_premium', 'mean'),
    limit_up_rate=('next_limit_up', 'mean'),
    avg_next_return=('next_return', 'mean'),
    win_rate=('next_return', lambda x: (x > 0).mean()),
    max_dd=('next_return', 'min'),
).round(4)

print("\n【大单净买入占比分组表现】")
print(group_stats.to_string())

# ============================================================
# 步骤 7: 连板高度 x 资金流向交叉分析
# ============================================================
print("\n\n步骤 7: 连板高度 x 资金流向交叉分析...")
r['board_group'] = pd.cut(r['board_count'], bins=[0, 1, 2, 3, 100], 
                           labels=['1板', '2板', '3板', '4板+'])
r['large_direction'] = np.where(r['large_net_ratio'] > 0, '大单净买入', '大单净卖出')

cross = r.groupby(['board_group', 'large_direction'], observed=True).agg(
    count=('ts_code', 'count'),
    avg_premium=('premium_rate', 'mean'),
    avg_close_premium=('close_premium', 'mean'),
    limit_up_rate=('next_limit_up', 'mean'),
    win_rate=('next_return', lambda x: (x > 0).mean()),
    avg_next_return=('next_return', 'mean'),
    max_dd=('next_return', 'min'),
).round(4)

print("\n【连板高度 x 资金流向交叉表】")
print(cross.to_string())

# ============================================================
# 步骤 8: 开板次数分析
# ============================================================
print("\n\n步骤 8: 开板次数分析...")
r['open_category'] = pd.cut(r['open_times'], bins=[-1, 0, 1, 3, 100], 
                             labels=['未开板', '开1次', '开2-3次', '开4次+'])
open_analysis = r.groupby('open_category', observed=True).agg(
    count=('ts_code', 'count'),
    avg_large_ratio=('large_net_ratio', 'mean'),
    avg_premium=('premium_rate', 'mean'),
    avg_close_premium=('close_premium', 'mean'),
    limit_up_rate=('next_limit_up', 'mean'),
    win_rate=('next_return', lambda x: (x > 0).mean()),
    avg_next_return=('next_return', 'mean'),
).round(4)
print("\n【开板次数分析】")
print(open_analysis.to_string())

# ============================================================
# 步骤 9: 生成可操作信号
# ============================================================
print("\n\n步骤 9: 生成可操作策略信号...")

# 最优条件
optimal = r[(r['board_count'] == 2) & (r['large_net_ratio'] > 0) & (r['open_times'] == 0)]
print(f"\n最优条件: 2板 + 大单净买入 + 未开板")
print(f"  样本数: {len(optimal)}")
if len(optimal) > 0:
    print(f"  平均溢价(最高): {optimal['premium_rate'].mean()*100:.2f}%")
    print(f"  平均收盘溢价: {optimal['close_premium'].mean()*100:.2f}%")
    print(f"  次日涨停率: {optimal['next_limit_up'].mean():.2%}")
    print(f"  胜率: {(optimal['next_return'] > 0).mean():.2%}")
    print(f"  平均次日收益: {optimal['next_return'].mean():.2f}%")
    print(f"  最大回撤: {optimal['next_return'].min():.2f}%")

# 仅2板基准
baseline = r[r['board_count'] == 2]
print(f"\n对比基准: 仅2板")
print(f"  样本数: {len(baseline)}")
print(f"  平均溢价(最高): {baseline['premium_rate'].mean()*100:.2f}%")
print(f"  次日涨停率: {baseline['next_limit_up'].mean():.2%}")
print(f"  胜率: {(baseline['next_return'] > 0).mean():.2%}")

# 大单净卖出 2板
weak = r[(r['board_count'] == 2) & (r['large_net_ratio'] < 0)]
print(f"\n弱势条件: 2板 + 大单净卖出")
print(f"  样本数: {len(weak)}")
if len(weak) > 0:
    print(f"  平均溢价(最高): {weak['premium_rate'].mean()*100:.2f}%")
    print(f"  胜率: {(weak['next_return'] > 0).mean():.2%}")

# ============================================================
# 步骤 10: 统计检验 (手动实现，不用 scipy)
# ============================================================
print("\n\n步骤 10: 统计检验...")

# t检验 (手动)
def t_test_ind(a, b):
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 0, 1.0
    m1, m2 = a.mean(), b.mean()
    v1, v2 = a.var(), b.var()
    se = np.sqrt(v1/n1 + v2/n2)
    if se == 0:
        return 0, 1.0
    t = (m1 - m2) / se
    # 近似 p-value (使用正态分布近似)
    from math import erf, sqrt
    p = 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2))))
    return t, p

q5_data = r[r['large_net_quintile'] == 'Q5(净买入最多)']['next_return']
q1_data = r[r['large_net_quintile'] == 'Q1(净卖出最多)']['next_return']
t_stat, p_val = t_test_ind(q5_data, q1_data)
print(f"\nQ5 vs Q1 次日收益 t检验: t={t_stat:.4f}, p={p_val:.4f}")

buy_grp = r[r['large_direction'] == '大单净买入']['next_limit_up']
sell_grp = r[r['large_direction'] == '大单净卖出']['next_limit_up']
if len(buy_grp) > 0 and len(sell_grp) > 0:
    t2, p2 = t_test_ind(buy_grp, sell_grp)
    print(f"大单买入 vs 卖出 连板率 t检验: t={t2:.4f}, p={p2:.4f}")

# ============================================================
# 保存数据
# ============================================================
r.to_csv('analysis_data.csv', index=False)
print(f"\n数据已保存到 analysis_data.csv ({len(r)} 条记录)")

# 输出关键结论摘要
print("\n\n========== 关键结论摘要 ==========")
print(f"总样本: {len(r)} 条涨停记录")
print(f"整体胜率: {(r['next_return'] > 0).mean():.2%}")
print(f"整体次日涨停率: {r['next_limit_up'].mean():.2%}")
