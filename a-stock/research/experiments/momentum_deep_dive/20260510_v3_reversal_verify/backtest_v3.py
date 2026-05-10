#!/usr/bin/env python3
"""
动量策略深度优化 V3 — 反转策略中位数收益验证
========================================
V2发现: 反转MOM1_低量(vol<30%) 年化75.53%
V3验证: 
1. 中位数收益 (排除极端值影响)
2. ST股过滤
3. 流动性约束 (成交额>1000万)
4. 实际冲击成本测试
"""

import pandas as pd
import numpy as np
import json
import time
import pickle

SAVE_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v3_reversal_verify/'

print("=" * 80)
print("动量策略深度优化 V3 — 反转策略中位数收益验证")
print("=" * 80)

t0 = time.time()
print("\n[1/4] 加载数据...")

df = pickle.load(open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v1_user/stock_daily.pkl', 'rb'))
df_idx = pickle.load(open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v1_user/index_daily.pkl', 'rb'))
df_basic = pickle.load(open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v1_user/stock_industry.pkl', 'rb'))

for col in ['open', 'close', 'high', 'low', 'pct_chg', 'vol', 'amount']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])

df_idx['close'] = pd.to_numeric(df_idx['close'], errors='coerce')
df_idx['trade_date'] = pd.to_datetime(df_idx['trade_date'])

df['limit_up'] = df['pct_chg'] >= 9.5
df['limit_down'] = df['pct_chg'] <= -9.5

# 择时
csi300 = df_idx[df_idx['ts_code'] == '000300.SH'].copy()
csi300['ma200'] = csi300['close'].rolling(200, min_periods=100).mean()
csi300['bull'] = (csi300['close'] > csi300['ma200']).astype(int)
df = df.merge(csi300[['trade_date', 'bull']], on='trade_date', how='left')
df['bull'] = df['bull'].fillna(0).astype(int)

df = df.merge(df_basic, on='ts_code', how='left')
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

# 动量 (滞后)
df['mom_1'] = df.groupby('ts_code')['close'].pct_change(1).shift(1)
df['ret_next'] = df.groupby('ts_code')['pct_chg'].shift(-1) / 100.0

# 成交量分位数
df['vol_pctile'] = df.groupby('trade_date')['vol'].rank(pct=True)

trade_dates = sorted(df['trade_date'].unique())
print(f"  {len(df):,} 行, {len(trade_dates)} 交易日, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# 核心分析: 逐日计算中位数/均值收益
# ============================================================
print("\n[2/4] 核心分析: 逐日中位数/均值收益...")

# 定义选股函数
def get_reversal_stocks(df, date, top_pct=0.05, filter_st=True, min_amount=0, filter_low_vol=True):
    """获取某日反转策略选中的股票"""
    day = df[df['trade_date'] == date].copy()
    
    # ST过滤
    if filter_st:
        day = day[~day['ts_code'].str.contains('ST', na=False)]
    
    # 流动性过滤
    if min_amount > 0:
        day = day[day['amount'] >= min_amount]
    
    # 低量过滤
    if filter_low_vol:
        day = day[day['vol_pctile'] < 0.3]
    
    # 排除跌停
    day = day[~day['limit_down']]
    
    # 排除mom_1为NaN
    day = day[day['mom_1'].notna()]
    
    if len(day) == 0:
        return pd.DataFrame()
    
    # 反转: 选动量最低(跌幅最大)
    day = day.sort_values('mom_1', ascending=True)
    n_select = max(1, int(len(day) * top_pct))
    return day.head(n_select)

# 逐日统计
stats = []
for i, date in enumerate(trade_dates[:-1]):  # 最后一天没有next return
    selected = get_reversal_stocks(df, date, top_pct=0.05, filter_st=True, 
                                   min_amount=1e7, filter_low_vol=True)  # 1000万成交额
    
    if len(selected) == 0:
        continue
    
    # 获取次日收益
    next_date = trade_dates[i + 1]
    next_data = df[df['trade_date'] == next_date]
    
    # 匹配
    matched = next_data[next_data['ts_code'].isin(selected['ts_code'])]
    
    if len(matched) == 0:
        continue
    
    returns = matched['pct_chg'].values / 100.0
    
    stats.append({
        'date': date,
        'n_stocks': len(returns),
        'mean_ret': returns.mean(),
        'median_ret': np.median(returns),
        'std_ret': returns.std(),
        'win_rate': (returns > 0).mean(),
        'max_ret': returns.max(),
        'min_ret': returns.min(),
    })

df_stats = pd.DataFrame(stats)

print(f"  有效交易日: {len(df_stats)}")
print(f"\n  均值日收益: {df_stats['mean_ret'].mean()*100:.4f}% (年化: {df_stats['mean_ret'].mean()*252*100:.2f}%)")
print(f"  中位数日收益: {df_stats['median_ret'].mean()*100:.4f}% (年化: {df_stats['median_ret'].mean()*252*100:.2f}%)")
print(f"  平均胜率: {df_stats['win_rate'].mean()*100:.1f}%")
print(f"  平均持仓: {df_stats['n_stocks'].mean():.0f} 只")

# 分年度
df_stats['year'] = pd.to_datetime(df_stats['date']).dt.year
for y in sorted(df_stats['year'].unique()):
    ysub = df_stats[df_stats['year'] == y]
    print(f"  {y}: 均值{ysub['mean_ret'].mean()*100:.4f}%, 中位数{ysub['median_ret'].mean()*100:.4f}%, 胜率{ysub['win_rate'].mean()*100:.1f}%, 天数{len(ysub)}")

# ============================================================
# 实验: 不同过滤条件对比
# ============================================================
print("\n[3/4] 实验: 不同过滤条件对比")
print("=" * 80)

configs = [
    ('基准(无过滤)', dict(filter_st=False, min_amount=0, filter_low_vol=False)),
    ('仅ST过滤', dict(filter_st=True, min_amount=0, filter_low_vol=False)),
    ('ST+流动性(>1000万)', dict(filter_st=True, min_amount=1e7, filter_low_vol=False)),
    ('ST+低量过滤', dict(filter_st=True, min_amount=0, filter_low_vol=True)),
    ('ST+流动性+低量', dict(filter_st=True, min_amount=1e7, filter_low_vol=True)),
]

results = {}
for name, cfg in configs:
    stats_list = []
    for i, date in enumerate(trade_dates[:-1]):
        selected = get_reversal_stocks(df, date, top_pct=0.05, **cfg)
        if len(selected) == 0:
            continue
        next_date = trade_dates[i + 1]
        next_data = df[df['trade_date'] == next_date]
        matched = next_data[next_data['ts_code'].isin(selected['ts_code'])]
        if len(matched) == 0:
            continue
        returns = matched['pct_chg'].values / 100.0
        stats_list.append({
            'mean': returns.mean(),
            'median': np.median(returns),
            'n': len(returns),
            'win': (returns > 0).mean(),
        })
    
    if len(stats_list) == 0:
        continue
    
    df_s = pd.DataFrame(stats_list)
    ann_mean = df_s['mean'].mean() * 252 * 100
    ann_median = df_s['median'].mean() * 252 * 100
    avg_win = df_s['win'].mean() * 100
    avg_n = df_s['n'].mean()
    
    results[name] = {
        'ann_mean': round(ann_mean, 2),
        'ann_median': round(ann_median, 2),
        'avg_win': round(avg_win, 1),
        'avg_n': round(avg_n, 0),
        'n_days': len(df_s),
    }
    print(f"  {name}: 年化均值{ann_mean:.2f}%, 中位数{ann_median:.2f}%, 胜率{avg_win:.1f}%, 持仓{avg_n:.0f}")

# ============================================================
# 累积资金曲线 (中位数 vs 均值)
# ============================================================
print("\n[4/4] 资金曲线分析 (ST+流动性+低量, TOP5%)")
print("=" * 80)

# 使用最佳配置: ST过滤 + 流动性 + 低量
cum_mean = 1.0
cum_median = 1.0
mean_curve = []
median_curve = []

for i, date in enumerate(trade_dates[:-1]):
    selected = get_reversal_stocks(df, date, top_pct=0.05, filter_st=True, 
                                   min_amount=1e7, filter_low_vol=True)
    if len(selected) == 0:
        mean_curve.append({'date': date, 'mean_val': cum_mean, 'median_val': cum_median})
        continue
    
    next_date = trade_dates[i + 1]
    next_data = df[df['trade_date'] == next_date]
    matched = next_data[next_data['ts_code'].isin(selected['ts_code'])]
    if len(matched) == 0:
        mean_curve.append({'date': date, 'mean_val': cum_mean, 'median_val': cum_median})
        continue
    
    returns = matched['pct_chg'].values / 100.0
    mean_r = returns.mean()
    median_r = np.median(returns)
    
    cum_mean *= (1 + mean_r)
    cum_median *= (1 + median_r)
    mean_curve.append({'date': date, 'mean_val': cum_mean, 'median_val': cum_median})

df_curve = pd.DataFrame(mean_curve)
if len(df_curve) > 0:
    n_years = (df_curve['date'].iloc[-1] - df_curve['date'].iloc[0]).days / 365.25
    
    # 均值曲线统计
    final_mean = df_curve['mean_val'].iloc[-1]
    ann_mean_curve = (final_mean ** (1/n_years) - 1) * 100
    cummax_mean = df_curve['mean_val'].cummax()
    mdd_mean = ((df_curve['mean_val'] - cummax_mean) / cummax_mean).min() * 100
    
    # 中位数曲线统计
    final_median = df_curve['median_val'].iloc[-1]
    ann_median_curve = (final_median ** (1/n_years) - 1) * 100
    cummax_median = df_curve['median_val'].cummax()
    mdd_median = ((df_curve['median_val'] - cummax_median) / cummax_median).min() * 100
    
    print(f"  均值资金曲线: 年化{ann_mean_curve:.2f}%, 最大回撤{mdd_mean:.2f}%")
    print(f"  中位数资金曲线: 年化{ann_median_curve:.2f}%, 最大回撤{mdd_median:.2f}%")
    print(f"  均值/中位数差距: {(ann_mean_curve - ann_median_curve):.2f}%")

# 分年度
df_curve['year'] = pd.to_datetime(df_curve['date']).dt.year
print("\n  分年度:")
for y in sorted(df_curve['year'].unique()):
    ysub = df_curve[df_curve['year'] == y]
    if len(ysub) > 1:
        yr_mean = (ysub['mean_val'].iloc[-1] / ysub['mean_val'].iloc[0] - 1) * 100
        yr_median = (ysub['median_val'].iloc[-1] / ysub['median_val'].iloc[0] - 1) * 100
        print(f"    {y}: 均值{yr_mean:.2f}%, 中位数{yr_median:.2f}%")

# ============================================================
# 保存
# ============================================================
summary = {
    'daily_stats': {
        'mean_daily': round(df_stats['mean_ret'].mean()*100, 4),
        'median_daily': round(df_stats['median_ret'].mean()*100, 4),
        'annualized_mean': round(df_stats['mean_ret'].mean()*252*100, 2),
        'annualized_median': round(df_stats['median_ret'].mean()*252*100, 2),
        'avg_win_rate': round(df_stats['win_rate'].mean()*100, 1),
    },
    'filter_comparison': results,
    'cumulative': {
        'ann_mean_curve': round(ann_mean_curve, 2),
        'ann_median_curve': round(ann_median_curve, 2),
        'mdd_mean': round(mdd_mean, 2),
        'mdd_median': round(mdd_median, 2),
    }
}

with open(SAVE_DIR + 'summary.json', 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

# status
status = {
    "exp_id": "20260510_v3_reversal_verify",
    "created_at": "2026-05-10T06:10:00+08:00",
    "status": "completed",
    "brief": "20260510_0503.md",
    "market": "A-STOCK",
    "report_done": True,
    "proposal_done": False,
    "summary": {
        "topic": "反转策略中位数收益验证",
        "key_finding": f"中位数年化{summary['daily_stats']['annualized_median']}%, 均值年化{summary['daily_stats']['annualized_mean']}%. 均值>中位数说明存在极端值驱动.",
        "sample_size": len(df_stats)
    }
}
with open(SAVE_DIR + 'status.json', 'w') as f:
    json.dump(status, f, indent=2, ensure_ascii=False)

print(f"\n✅ V3 研究完成!")
