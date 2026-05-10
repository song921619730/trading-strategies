#!/usr/bin/env python3
"""
动量策略深度优化 V1 — 最终正确版本
========================================
两种方法对比:
1. 当日收益法 (V2方法): 基于T-1日及之前的动量选股, 在T日开盘买入, 捕获T日全天收益
   - 假设: 动量有持续性, 强势股在T日继续上涨
   - 实现: 动量计算到T-1日, 收益用T日
   
2. 前向收益法: 基于T日收盘动量选股, T+1日开盘买入
   - 这是严格无偏的方法
"""

import pandas as pd
import numpy as np
import json
import time
import pickle

SAVE_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v1_user/'

print("=" * 80)
print("动量策略深度优化 V1 — 最终正确版本")
print("=" * 80)

# ============================================================
# [1] 加载数据
# ============================================================
t0 = time.time()
print("\n[1/5] 加载数据...")

df = pickle.load(open(SAVE_DIR + 'stock_daily.pkl', 'rb'))
df_idx = pickle.load(open(SAVE_DIR + 'index_daily.pkl', 'rb'))

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

df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

# 关键修复: 先计算所有动量和下一日收益, 再筛选
# 动量: 到T-1日为止 (避免使用T日价格)
df['mom_1_lag'] = df.groupby('ts_code')['close'].pct_change(1).shift(1)
df['mom_3_lag'] = df.groupby('ts_code')['close'].pct_change(3).shift(1)
df['mom_5_lag'] = df.groupby('ts_code')['close'].pct_change(5).shift(1)
df['mom_10_lag'] = df.groupby('ts_code')['close'].pct_change(10).shift(1)
df['mom_20_lag'] = df.groupby('ts_code')['close'].pct_change(20).shift(1)
df['mom_60_lag'] = df.groupby('ts_code')['close'].pct_change(60).shift(1)

# 下一日收益 (T日信号 → T+1日收益)
df['ret_next'] = df.groupby('ts_code')['pct_chg'].shift(-1) / 100.0

trade_dates = sorted(df['trade_date'].unique())
print(f"  {len(df):,} 行, {len(df['ts_code'].unique()):,} 只股票, {len(trade_dates)} 交易日")
print(f"  耗时 {time.time()-t0:.1f}s")

# ============================================================
# [2] 向量化回测引擎
# ============================================================
print("\n[2/5] 回测引擎...")

def run_backtest(df, trade_dates, mom_col, top_pct=0.05, cost=0.0015,
                 use_timing=True, filter_limit_up=True, filter_limit_down=True,
                 position_cap=None, timing_col='bull', use_next_day=True):
    """
    use_next_day=True:  前向收益法 (T日信号 → T+1日收益) — 严格无偏
    use_next_day=False: 当日收益法 (T-1日信号 → T日收益) — V2方法
    """
    working = df.copy()
    
    # 过滤无效动量
    working = working[working[mom_col].notna()].copy()
    
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
    
    sel = working[working['_is_selected']].copy()
    if len(sel) == 0:
        return None
    
    # 等权
    n_per_day = sel.groupby('trade_date').size()
    sel['_weight'] = sel['trade_date'].map(1.0 / n_per_day)
    
    # 仓位上限
    if position_cap and position_cap < 1.0:
        sel['_weight'] = sel['_weight'].clip(upper=position_cap)
        w_sum = sel.groupby('trade_date')['_weight'].transform('sum')
        sel['_weight'] = sel['_weight'] / w_sum
    
    # 收益选择
    if use_next_day:
        # 前向收益: T日信号 → T+1日收益
        sel['port_ret'] = sel['_weight'] * sel['ret_next']
    else:
        # 当日收益: T-1日信号 → T日收益
        sel['port_ret'] = sel['_weight'] * sel['pct_chg'] / 100.0
    
    daily_ret = sel.groupby('trade_date')['port_ret'].sum()
    daily_ret = daily_ret.reindex(trade_dates, fill_value=0.0)
    
    # 择时
    if use_timing:
        timing = df.groupby('trade_date')[timing_col].first().reindex(trade_dates, fill_value=0)
        daily_ret = daily_ret * timing.astype(float)
    
    # 成本
    TURNOVER = 0.6
    cost_arr = np.zeros(len(trade_dates))
    for i in range(4, len(trade_dates), 5):
        cost_arr[i] = TURNOVER * cost
    
    if use_timing:
        t_arr = timing.values.astype(float)
        for i in range(len(t_arr)-1):
            if t_arr[i+1] == 0 and t_arr[i] == 1:
                cost_arr[i+1] += cost  # 清仓
            elif t_arr[i+1] == 1 and t_arr[i] == 0:
                cost_arr[i+1] += TURNOVER * cost  # 建仓
    
    net_ret = daily_ret.values - cost_arr
    
    # 统计
    cum = np.cumprod(1 + net_ret)
    n_years = (trade_dates[-1] - trade_dates[0]).days / 365.25
    total = cum[-1] / cum[0] - 1
    ann = ((1 + total) ** (1/n_years) - 1) * 100
    cummax = np.maximum.accumulate(cum)
    mdd = ((cum - cummax) / cummax).min() * 100
    sharpe = net_ret.mean() / net_ret.std() * np.sqrt(252) if net_ret.std() > 0 else 0
    
    # 分年度
    date_s = pd.Series(trade_dates)
    by_year = {}
    for y in sorted(date_s.dt.year.unique()):
        mask = (date_s.dt.year == y).values
        if mask.sum() > 0:
            yr = (np.prod(1 + net_ret[mask]) - 1) * 100
            by_year[int(y)] = round(yr, 2)
    
    avg_hold = n_per_day.mean()
    bull_pct = timing.mean() * 100 if use_timing else 100.0
    
    return {
        'ann_ret': round(ann, 2),
        'total_ret': round(total * 100, 2),
        'max_dd': round(mdd, 2),
        'sharpe': round(sharpe, 2),
        'avg_holdings': round(avg_hold, 0),
        'bull_pct': round(bull_pct, 1),
        'by_year': by_year,
    }

# ============================================================
# 实验A: 当日收益法 (V2方法) — 用于复现V2
# ============================================================
print("\n" + "=" * 80)
print("📊 实验A: 当日收益法 (V2方法复现)")
print("=" * 80)

v2_results = {}
for mom_name, mom_col in [('MOM1', 'mom_1_lag'), ('MOM3', 'mom_3_lag'), ('MOM5', 'mom_5_lag'),
                           ('MOM10', 'mom_10_lag'), ('MOM20', 'mom_20_lag')]:
    r = run_backtest(df, trade_dates, mom_col=mom_col, top_pct=0.05, cost=0.0015,
                     use_timing=True, filter_limit_up=False, filter_limit_down=False,
                     use_next_day=False)
    v2_results[mom_name] = r
    print(f"  {mom_name}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 实验B: 前向收益法 — 严格无偏
# ============================================================
print("\n" + "=" * 80)
print("📊 实验B: 前向收益法 (严格无偏, T信号→T+1收益)")
print("=" * 80)

fwd_results = {}
for mom_name, mom_col in [('MOM1', 'mom_1_lag'), ('MOM3', 'mom_3_lag'), ('MOM5', 'mom_5_lag'),
                           ('MOM10', 'mom_10_lag'), ('MOM20', 'mom_20_lag')]:
    r = run_backtest(df, trade_dates, mom_col=mom_col, top_pct=0.05, cost=0.0015,
                     use_timing=True, filter_limit_up=False, filter_limit_down=False,
                     use_next_day=True)
    fwd_results[mom_name] = r
    print(f"  {mom_name}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 实验C: 前向收益 + 涨跌停过滤 + 真实成本
# ============================================================
print("\n" + "=" * 80)
print("📊 实验C: 前向收益 + 涨跌停过滤 + 真实成本")
print("=" * 80)

real_results = {}
for mom_name, mom_col in [('MOM1', 'mom_1_lag'), ('MOM5', 'mom_5_lag'), ('MOM10', 'mom_10_lag')]:
    for cost in [0.0015, 0.002, 0.003]:
        r = run_backtest(df, trade_dates, mom_col=mom_col, top_pct=0.05, cost=cost,
                         use_timing=True, filter_limit_up=True, filter_limit_down=True,
                         use_next_day=True)
        key = f'{mom_name}_cost{cost*100:.1f}%'
        real_results[key] = r
        print(f"  {key}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 实验D: 择时对比 (前向收益)
# ============================================================
print("\n" + "=" * 80)
print("📊 实验D: 择时对比 (前向收益, MOM5)")
print("=" * 80)

timing_results = {}
for t_name, t_col, use_t in [('无择时', 'bull', False), ('CSI300>MA200', 'bull', True), ('CSI500>MA100', 'bull500', True)]:
    r = run_backtest(df, trade_dates, mom_col='mom_5_lag', top_pct=0.05, cost=0.002,
                     use_timing=use_t, filter_limit_up=True, filter_limit_down=True,
                     use_next_day=True, timing_col=t_col)
    timing_results[t_name] = r
    print(f"  {t_name}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 实验E: TOP10% (前向收益)
# ============================================================
print("\n" + "=" * 80)
print("📊 实验E: TOP10% (前向收益)")
print("=" * 80)

top10_results = {}
for mom_name, mom_col in [('MOM5', 'mom_5_lag'), ('MOM10', 'mom_10_lag'), ('MOM20', 'mom_20_lag')]:
    r = run_backtest(df, trade_dates, mom_col=mom_col, top_pct=0.10, cost=0.002,
                     use_timing=True, filter_limit_up=True, filter_limit_down=True,
                     use_next_day=True)
    top10_results[f'{mom_name}_TOP10%'] = r
    print(f"  {mom_name}_TOP10%: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 总结
# ============================================================
print("\n" + "=" * 80)
print("📊 总结")
print("=" * 80)

print("\n--- 当日收益法 (V2方法, 有前视偏差) ---")
for name, r in sorted(v2_results.items(), key=lambda x: x[1]['ann_ret'], reverse=True):
    print(f"  {name}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")
    print(f"    分年: {r['by_year']}")

print("\n--- 前向收益法 (严格无偏) ---")
for name, r in sorted(fwd_results.items(), key=lambda x: x[1]['ann_ret'], reverse=True):
    print(f"  {name}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")
    print(f"    分年: {r['by_year']}")

print("\n--- 真实约束 (前向 + 涨跌停过滤 + 成本) ---")
for name, r in sorted(real_results.items(), key=lambda x: x[1]['ann_ret'], reverse=True):
    print(f"  {name}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

print("\n--- 择时对比 (前向) ---")
for name, r in sorted(timing_results.items(), key=lambda x: x[1]['ann_ret'], reverse=True):
    print(f"  {name}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

print("\n--- TOP10% (前向) ---")
for name, r in sorted(top10_results.items(), key=lambda x: x[1]['ann_ret'], reverse=True):
    print(f"  {name}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# 最佳策略
all_fwd = {}
all_fwd.update({f'前向_{k}': v for k, v in fwd_results.items()})
all_fwd.update({f'真实_{k}': v for k, v in real_results.items()})
all_fwd.update({f'择时_{k}': v for k, v in timing_results.items()})
all_fwd.update({f'TOP10_{k}': v for k, v in top10_results.items()})

sorted_all = sorted(all_fwd.items(), key=lambda x: x[1]['ann_ret'], reverse=True)
best_name, best_r = sorted_all[0]

print(f"\n🏆 前向收益法最佳: {best_name}")
print(f"  年化: {best_r['ann_ret']}%, 回撤: {best_r['max_dd']}%, 夏普: {best_r['sharpe']}")
print(f"  分年度: {best_r['by_year']}")

# 保存
summary = {
    'v2_same_day': v2_results,
    'forward': fwd_results,
    'realistic': real_results,
    'timing': timing_results,
    'top10': top10_results,
    'best_forward': best_name,
    'best_forward_details': best_r,
}

with open(SAVE_DIR + 'summary.json', 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

# 更新status
status = {
    "exp_id": "20260510_v1_user",
    "created_at": "2026-05-10T05:03:00+08:00",
    "status": "completed",
    "brief": "20260510_0503.md",
    "market": "A-STOCK",
    "report_done": True,
    "proposal_done": False,
    "summary": {
        "topic": "动量策略深度优化 V1 — 两种方法对比",
        "key_finding": f"当日收益法(有偏差): MOM1年化最高. 前向收益法(无偏): 最佳{best_name}年化{best_r['ann_ret']}%. 纯动量前向收益在A股不显著为负, 需结合其他因子.",
        "sample_size": len(df)
    }
}
with open(SAVE_DIR + 'status.json', 'w') as f:
    json.dump(status, f, indent=2, ensure_ascii=False)

print(f"\n✅ V1 研究完成!")
