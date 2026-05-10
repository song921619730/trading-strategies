#!/usr/bin/env python3
"""
动量策略深度优化 V1 — 高效向量化回测
========================================
使用纯pandas/numpy向量化操作, 避免Python循环
"""

import pandas as pd
import numpy as np
import json
import time
import pickle

SAVE_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v1_user/'

print("=" * 80)
print("动量策略深度优化 V1 — 高效向量化回测")
print("=" * 80)

# ============================================================
# [1] 加载数据
# ============================================================
t0 = time.time()
print("\n[1/5] 加载数据...")

df = pickle.load(open(SAVE_DIR + 'stock_daily.pkl', 'rb'))
df_idx = pickle.load(open(SAVE_DIR + 'index_daily.pkl', 'rb'))
df_ind = pickle.load(open(SAVE_DIR + 'stock_industry.pkl', 'rb'))

for col in ['open', 'close', 'high', 'low', 'pct_chg', 'vol', 'amount']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])

df_idx['close'] = pd.to_numeric(df_idx['close'], errors='coerce')
df_idx['trade_date'] = pd.to_datetime(df_idx['trade_date'])

# 涨跌停标记
df['limit_up'] = df['pct_chg'] >= 9.5
df['limit_down'] = df['pct_chg'] <= -9.5

# 择时信号
csi300 = df_idx[df_idx['ts_code'] == '000300.SH'].copy()
csi300['ma200'] = csi300['close'].rolling(200, min_periods=100).mean()
csi300['bull'] = (csi300['close'] > csi300['ma200']).astype(int)

csi500 = df_idx[df_idx['ts_code'] == '000905.SH'].copy()
csi500['ma100'] = csi500['close'].rolling(100, min_periods=50).mean()
csi500['bull500'] = (csi500['close'] > csi500['ma100']).astype(int)

df = df.merge(csi300[['trade_date', 'bull']], on='trade_date', how='left')
df = df.merge(csi500[['trade_date', 'bull500']], on='trade_date', how='left')
df['bull'] = df['bull'].fillna(0).astype(int)
df['bull500'] = df['bull500'].fillna(0).astype(int)

df = df.merge(df_ind, on='ts_code', how='left')
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

trade_dates = sorted(df['trade_date'].unique())
print(f"  {len(df):,} 行, {len(df['ts_code'].unique()):,} 只股票, {len(trade_dates)} 交易日")
print(f"  耗时 {time.time()-t0:.1f}s")

# ============================================================
# [2] 计算动量
# ============================================================
t0 = time.time()
print("\n[2/5] 计算动量因子...")

for w in [1, 3, 5, 10, 20, 60]:
    df[f'mom_{w}'] = df.groupby('ts_code')['close'].transform(lambda x: x.pct_change(w))

# 行业中性动量
df['mom_5_ind_neutral'] = df.groupby(['trade_date', 'industry'])['mom_5'].transform(
    lambda x: x - x.mean() if x.notna().sum() > 1 else x
)

print(f"  耗时 {time.time()-t0:.1f}s")

# ============================================================
# [3] 高效向量化回测引擎
# ============================================================
print("\n[3/5] 回测引擎 (向量化)...")

def run_momentum_backtest_vec(df, trade_dates, mom_col='mom_5', top_pct=0.05,
                              cost_per_trade=0.0015, use_timing=True,
                              filter_limit_up=True, filter_limit_down=True,
                              position_cap=None, timing_col='bull'):
    """
    向量化回测: 使用groupby和rank操作, 避免逐日循环
    """
    # ⚠️ 关键修复: 先在整个df上计算下一日收益, 再过滤
    # 在filtered DataFrame上做groupby().shift(-1)会导致对齐错误
    df_work = df.copy()
    df_work['ret_next'] = df_work.groupby('ts_code')['pct_chg'].shift(-1) / 100.0
    
    working = df_work[df_work[mom_col].notna()].copy()
    
    # 涨跌停过滤
    if filter_limit_up:
        working = working[~working['limit_up']]
    if filter_limit_down:
        working = working[~working['limit_down']]
    
    if len(working) == 0:
        return None
    
    # 按动量排名
    working['_rank'] = working.groupby('trade_date')[mom_col].rank(ascending=False, method='first')
    working['_count'] = working.groupby('trade_date')[mom_col].transform('count')
    n_select = (working['_count'] * top_pct).astype(int).clip(lower=1)
    working['_is_selected'] = working['_rank'] <= n_select
    
    # 只保留选中的股票 (此时ret_next已经在上面正确计算了)
    sel = working[working['_is_selected']].copy()
    
    if len(sel) == 0:
        return None
    
    # 计算等权权重
    n_per_day = sel.groupby('trade_date').size()
    sel['_eq_weight'] = sel['trade_date'].map(1.0 / n_per_day)
    
    # 仓位上限
    if position_cap and position_cap < 1.0:
        sel['_eq_weight'] = sel['_eq_weight'].clip(upper=position_cap)
        # 重新归一化
        weight_sum = sel.groupby('trade_date')['_eq_weight'].transform('sum')
        sel['_eq_weight'] = sel['_eq_weight'] / weight_sum
    
    # ⚠️ 使用预计算的ret_next (T日信号 → T+1日收益)
    # ret_next = pct_chg(T+1) / 100, 已经shift过了
    sel['weighted_ret'] = sel['_eq_weight'] * sel['ret_next']
    daily_ret = sel.groupby('trade_date')['weighted_ret'].sum()
    
    # 对齐到trade_dates, 最后一天没有未来收益
    daily_ret = daily_ret.reindex(trade_dates, fill_value=0.0)
    daily_ret.iloc[-1] = 0.0
    
    # 择时信号
    if use_timing:
        timing = df.groupby('trade_date')[timing_col].first().reindex(trade_dates, fill_value=0)
        # 只在牛市交易日应用收益, 熊市收益=0 (空仓)
        daily_ret = daily_ret * timing.astype(float)
    
    # 成本: 每5个交易日扣一次
    TURNOVER_PER_REBALANCE = 0.6
    cost_array = np.zeros(len(trade_dates))
    for i in range(4, len(trade_dates), 5):
        cost_array[i] = TURNOVER_PER_REBALANCE * cost_per_trade
    
    # 如果择时: 熊市空仓无成本, 但牛转熊时有卖出成本
    # 简化: 在牛转熊的第一个交易日扣成本
    if use_timing:
        timing_arr = timing.values.astype(float)
        bull_changes = np.diff(timing_arr)
        # 牛转熊 (1->0): diff = -1
        for i in range(len(bull_changes)):
            if bull_changes[i] == -1:
                cost_array[i+1] += cost_per_trade  # 清仓成本
            elif bull_changes[i] == 1:
                cost_array[i+1] += TURNOVER_PER_REBALANCE * cost_per_trade  # 建仓成本
    
    # 净收益
    gross_returns = daily_ret.values - cost_array
    
    # 资金曲线
    cum_returns = np.cumprod(1 + gross_returns)
    
    # 统计
    n_years = (trade_dates[-1] - trade_dates[0]).days / 365.25
    total_ret = cum_returns[-1] / cum_returns[0] - 1
    ann_ret = ((1 + total_ret) ** (1/n_years) - 1) * 100 if n_years > 0 else 0
    
    # 最大回撤
    cummax = np.maximum.accumulate(cum_returns)
    dd = (cum_returns - cummax) / cummax
    max_dd = dd.min() * 100
    
    # 夏普
    if gross_returns.std() > 0:
        sharpe = gross_returns.mean() / gross_returns.std() * np.sqrt(252)
    else:
        sharpe = 0.0
    
    # 分年度
    date_series = pd.Series(trade_dates)
    by_year = {}
    for y in sorted(date_series.dt.year.unique()):
        mask = (date_series.dt.year == y).values
        if mask.sum() > 0:
            y_rets = gross_returns[mask]
            y_ret = (np.prod(1 + y_rets) - 1) * 100
            by_year[int(y)] = round(y_ret, 2)
    
    # 平均持仓数
    avg_holdings = n_per_day.mean()
    
    # 牛市比例
    if use_timing:
        bull_pct = timing.mean() * 100
    else:
        bull_pct = 100.0
    
    # 总交易次数
    total_trades = int(len(trade_dates) / 5 * avg_holdings * 2)
    
    return {
        'ann_ret': round(ann_ret, 2),
        'total_ret': round(total_ret * 100, 2),
        'max_dd': round(max_dd, 2),
        'sharpe': round(sharpe, 2),
        'avg_holdings': round(avg_holdings, 0),
        'bull_pct': round(bull_pct, 1),
        'total_trades': total_trades,
        'by_year': by_year,
        'n_days': len(trade_dates),
    }

# ============================================================
# 实验1: 涨跌停过滤
# ============================================================
print("\n" + "=" * 80)
print("📊 实验1: 涨跌停过滤 (MOM5, TOP5%, cost=0.15%)")
print("=" * 80)

experiments = {}
configs = [
    ('V2基准(无过滤)', dict(filter_limit_up=False, filter_limit_down=False)),
    ('仅过滤涨停', dict(filter_limit_up=True, filter_limit_down=False)),
    ('仅过滤跌停', dict(filter_limit_up=False, filter_limit_down=True)),
    ('过滤涨跌停', dict(filter_limit_up=True, filter_limit_down=True)),
]

for name, cfg in configs:
    r = run_momentum_backtest_vec(df, trade_dates, mom_col='mom_5', top_pct=0.05,
                                   cost_per_trade=0.0015, **cfg)
    experiments[name] = r
    print(f"  {name}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 实验2: 冲击成本
# ============================================================
print("\n" + "=" * 80)
print("📊 实验2: 冲击成本 (过滤涨跌停, MOM5, TOP5%)")
print("=" * 80)

cost_exp = {}
for cost in [0.0015, 0.002, 0.0025, 0.003, 0.005]:
    r = run_momentum_backtest_vec(df, trade_dates, mom_col='mom_5', top_pct=0.05,
                                   cost_per_trade=cost, filter_limit_up=True, filter_limit_down=True)
    cost_exp[f'cost={cost*100:.2f}%'] = r
    print(f"  单边{cost*100:.2f}%: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 实验3: 仓位上限
# ============================================================
print("\n" + "=" * 80)
print("📊 实验3: 仓位上限 (过滤涨跌停, cost=0.2%)")
print("=" * 80)

pos_cap_exp = {}
for cap in [None, 0.10, 0.05, 0.03, 0.02]:
    label = '无上限' if cap is None else f'上限{cap*100:.0f}%'
    r = run_momentum_backtest_vec(df, trade_dates, mom_col='mom_5', top_pct=0.05,
                                   cost_per_trade=0.002, filter_limit_up=True, filter_limit_down=True,
                                   position_cap=cap)
    pos_cap_exp[label] = r
    print(f"  {label}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}, 持仓{r['avg_holdings']:.0f}")

# ============================================================
# 实验4: 动量衰减
# ============================================================
print("\n" + "=" * 80)
print("📊 实验4: 动量窗口衰减 (过滤涨跌停, cost=0.2%, TOP5%)")
print("=" * 80)

decay_exp = {}
for mom_w in [1, 3, 5, 10, 20, 60]:
    r = run_momentum_backtest_vec(df, trade_dates, mom_col=f'mom_{mom_w}', top_pct=0.05,
                                   cost_per_trade=0.002, filter_limit_up=True, filter_limit_down=True)
    decay_exp[f'MOM{mom_w}'] = r
    print(f"  MOM{mom_w}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 实验5: 行业中性
# ============================================================
print("\n" + "=" * 80)
print("📊 实验5: 行业中性 vs 原始 (过滤涨跌停, cost=0.2%)")
print("=" * 80)

ind_exp = {}
r_raw = run_momentum_backtest_vec(df, trade_dates, mom_col='mom_5', top_pct=0.05,
                                   cost_per_trade=0.002, filter_limit_up=True, filter_limit_down=True)
ind_exp['原始动量'] = r_raw
print(f"  原始动量: 年化{r_raw['ann_ret']:.2f}%, 回撤{r_raw['max_dd']:.2f}%, 夏普{r_raw['sharpe']:.2f}")

r_ind = run_momentum_backtest_vec(df, trade_dates, mom_col='mom_5_ind_neutral', top_pct=0.05,
                                   cost_per_trade=0.002, filter_limit_up=True, filter_limit_down=True)
ind_exp['行业中性'] = r_ind
print(f"  行业中性: 年化{r_ind['ann_ret']:.2f}%, 回撤{r_ind['max_dd']:.2f}%, 夏普{r_ind['sharpe']:.2f}")

# ============================================================
# 实验6: 择时对比
# ============================================================
print("\n" + "=" * 80)
print("📊 实验6: 择时信号 (过滤涨跌停, cost=0.2%)")
print("=" * 80)

timing_exp = {}

r = run_momentum_backtest_vec(df, trade_dates, mom_col='mom_5', top_pct=0.05,
                               cost_per_trade=0.002, use_timing=False,
                               filter_limit_up=True, filter_limit_down=True)
timing_exp['无择时'] = r
print(f"  无择时: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

r = run_momentum_backtest_vec(df, trade_dates, mom_col='mom_5', top_pct=0.05,
                               cost_per_trade=0.002, use_timing=True,
                               filter_limit_up=True, filter_limit_down=True, timing_col='bull')
timing_exp['CSI300>MA200'] = r
print(f"  CSI300>MA200: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

r = run_momentum_backtest_vec(df, trade_dates, mom_col='mom_5', top_pct=0.05,
                               cost_per_trade=0.002, use_timing=True,
                               filter_limit_up=True, filter_limit_down=True, timing_col='bull500')
timing_exp['CSI500>MA100'] = r
print(f"  CSI500>MA100: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 实验7: TOP10%
# ============================================================
print("\n" + "=" * 80)
print("📊 实验7: TOP10%配置 (过滤涨跌停, cost=0.2%)")
print("=" * 80)

top10_exp = {}
for mom_w in [5, 10, 20]:
    r = run_momentum_backtest_vec(df, trade_dates, mom_col=f'mom_{mom_w}', top_pct=0.10,
                                   cost_per_trade=0.002, filter_limit_up=True, filter_limit_down=True)
    top10_exp[f'MOM{mom_w}_TOP10%'] = r
    print(f"  MOM{mom_w}_TOP10%: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 总结
# ============================================================
print("\n" + "=" * 80)
print("📊 全策略排名")
print("=" * 80)

all_results = {}
all_results.update({f'涨跌停_{k}': v for k, v in experiments.items()})
all_results.update({f'成本_{k}': v for k, v in cost_exp.items()})
all_results.update({f'仓位_{k}': v for k, v in pos_cap_exp.items()})
all_results.update({f'动量_{k}': v for k, v in decay_exp.items()})
all_results.update({f'行业_{k}': v for k, v in ind_exp.items()})
all_results.update({f'择时_{k}': v for k, v in timing_exp.items()})
all_results.update({f'TOP10_{k}': v for k, v in top10_exp.items()})

sorted_results = sorted(all_results.items(), key=lambda x: x[1]['ann_ret'], reverse=True)

print(f"\n{'策略':<35} {'年化收益':>10} {'最大回撤':>10} {'夏普':>8}")
print("-" * 70)
for name, r in sorted_results[:25]:
    print(f"{name:<35} {r['ann_ret']:>9.2f}% {r['max_dd']:>9.2f}% {r['sharpe']:>8.2f}")

best_name, best_r = sorted_results[0]
print(f"\n🏆 最佳: {best_name}")
print(f"  年化: {best_r['ann_ret']}%, 回撤: {best_r['max_dd']}%, 夏普: {best_r['sharpe']}")
print(f"  分年度:")
for y, ret in best_r['by_year'].items():
    print(f"    {y}: {ret}%")

# 保存
with open(SAVE_DIR + 'summary.json', 'w') as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)

# 更新status.json
import os
status = {
    "exp_id": "20260510_v1_user",
    "created_at": "2026-05-10T05:03:00+08:00",
    "status": "completed",
    "brief": "20260510_0503.md",
    "market": "A-STOCK",
    "report_done": True,
    "proposal_done": True,
    "summary": {
        "topic": "动量策略深度优化 V1 — 真实交易约束验证",
        "key_finding": f"最佳配置: {best_name}, 年化{best_r['ann_ret']}%, 回撤{best_r['max_dd']}%, 夏普{best_r['sharpe']}",
        "sample_size": len(df)
    }
}
with open(SAVE_DIR + 'status.json', 'w') as f:
    json.dump(status, f, indent=2, ensure_ascii=False)

print(f"\n✅ V1 研究完成!")
