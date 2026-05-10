#!/usr/bin/env python3
"""
动量策略深度优化 V2 — 短期反转策略
========================================
核心假设: A股短期(1-5日)存在均值回归, 买入跌多的股票比买入涨多的股票更有效
方法: 选择动量最低的TOP5% (而非最高), 持有T+1日
"""

import pandas as pd
import numpy as np
import json
import time
import pickle

SAVE_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v2_reversal/'

print("=" * 80)
print("动量策略深度优化 V2 — 短期反转策略")
print("=" * 80)

t0 = time.time()
print("\n[1/4] 加载数据...")

df = pickle.load(open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v1_user/stock_daily.pkl', 'rb'))
df_idx = pickle.load(open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/动量策略深度优化_(momentum_strategy_deep_dive)/20260510_v1_user/index_daily.pkl', 'rb'))

for col in ['open', 'close', 'high', 'low', 'pct_chg', 'vol', 'amount']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['trade_date'] = pd.to_datetime(df['trade_date'])

df_idx['close'] = pd.to_numeric(df_idx['close'], errors='coerce')
df_idx['trade_date'] = pd.to_datetime(df_idx['trade_date'])

df['limit_up'] = df['pct_chg'] >= 9.5
df['limit_down'] = df['pct_chg'] <= -9.5

csi300 = df_idx[df_idx['ts_code'] == '000300.SH'].copy()
csi300['ma200'] = csi300['close'].rolling(200, min_periods=100).mean()
csi300['bull'] = (csi300['close'] > csi300['ma200']).astype(int)

df = df.merge(csi300[['trade_date', 'bull']], on='trade_date', how='left')
df['bull'] = df['bull'].fillna(0).astype(int)
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

# 动量 (滞后1日, 避免前视偏差)
for w in [1, 3, 5, 10, 20]:
    df[f'mom_{w}'] = df.groupby('ts_code')['close'].pct_change(w).shift(1)

# 下一日收益
df['ret_next'] = df.groupby('ts_code')['pct_chg'].shift(-1) / 100.0

trade_dates = sorted(df['trade_date'].unique())
print(f"  {len(df):,} 行, {len(trade_dates)} 交易日, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# 回测引擎
# ============================================================
def run_reversal(df, trade_dates, mom_col, top_pct=0.05, cost=0.0015,
                 use_timing=True, filter_limit_down=True, timing_col='bull'):
    """反转策略: 选择动量最低的股票 (买入跌多的)"""
    working = df[df[mom_col].notna()].copy()
    if filter_limit_down:
        working = working[~working['limit_down']]  # 跌停股排除(可能继续跌)
    
    # 排名: ascending=True → 最低动量(跌幅最大)排名靠前
    working['_rank'] = working.groupby('trade_date')[mom_col].rank(ascending=True, method='first')
    working['_count'] = working.groupby('trade_date')[mom_col].transform('count')
    n_select = (working['_count'] * top_pct).astype(int).clip(lower=1)
    working['_is_selected'] = working['_rank'] <= n_select
    
    sel = working[working['_is_selected']].copy()
    if len(sel) == 0:
        return None
    
    n_per_day = sel.groupby('trade_date').size()
    sel['_weight'] = sel['trade_date'].map(1.0 / n_per_day)
    
    sel['port_ret'] = sel['_weight'] * sel['ret_next']
    daily_ret = sel.groupby('trade_date')['port_ret'].sum()
    daily_ret = daily_ret.reindex(trade_dates, fill_value=0.0)
    
    if use_timing:
        timing = df.groupby('trade_date')[timing_col].first().reindex(trade_dates, fill_value=0)
        daily_ret = daily_ret * timing.astype(float)
    
    TURNOVER = 0.6
    cost_arr = np.zeros(len(trade_dates))
    for i in range(4, len(trade_dates), 5):
        cost_arr[i] = TURNOVER * cost
    
    net_ret = daily_ret.values - cost_arr
    cum = np.cumprod(1 + net_ret)
    n_years = (trade_dates[-1] - trade_dates[0]).days / 365.25
    total = cum[-1] / cum[0] - 1
    ann = ((1 + total) ** (1/n_years) - 1) * 100
    cummax = np.maximum.accumulate(cum)
    mdd = ((cum - cummax) / cummax).min() * 100
    sharpe = net_ret.mean() / net_ret.std() * np.sqrt(252) if net_ret.std() > 0 else 0
    
    date_s = pd.Series(trade_dates)
    by_year = {}
    for y in sorted(date_s.dt.year.unique()):
        mask = (date_s.dt.year == y).values
        if mask.sum() > 0:
            yr = (np.prod(1 + net_ret[mask]) - 1) * 100
            by_year[int(y)] = round(yr, 2)
    
    return {
        'ann_ret': round(ann, 2),
        'total_ret': round(total * 100, 2),
        'max_dd': round(mdd, 2),
        'sharpe': round(sharpe, 2),
        'avg_holdings': round(n_per_day.mean(), 0),
        'bull_pct': round(timing.mean() * 100, 1) if use_timing else 100.0,
        'by_year': by_year,
    }

# ============================================================
# 实验1: 反转 vs 动量对比
# ============================================================
print("\n[2/4] 实验1: 反转 vs 动量对比")
print("=" * 80)

results = {}

for mom_w in [1, 3, 5, 10]:
    mom_col = f'mom_{mom_w}'
    
    # 动量 (选涨最多的)
    r_mom = run_reversal(df, trade_dates, mom_col=mom_col, top_pct=0.05, cost=0.002,
                         use_timing=True, filter_limit_down=True)
    
    # 反转 (选跌最多的) — 用负的动量列
    df_rev = df.copy()
    df_rev[mom_col] = -df_rev[mom_col]  # 负值 → 排名反转
    r_rev = run_reversal(df_rev, trade_dates, mom_col=mom_col, top_pct=0.05, cost=0.002,
                         use_timing=True, filter_limit_down=True)
    
    results[f'MOM{mom_w}_动量'] = r_mom
    results[f'MOM{mom_w}_反转'] = r_rev
    
    print(f"  MOM{mom_w} 动量: 年化{r_mom['ann_ret']:.2f}%, 回撤{r_mom['max_dd']:.2f}%, 夏普{r_mom['sharpe']:.2f}")
    print(f"  MOM{mom_w} 反转: 年化{r_rev['ann_ret']:.2f}%, 回撤{r_rev['max_dd']:.2f}%, 夏普{r_rev['sharpe']:.2f}")

# ============================================================
# 实验2: 反转策略参数优化
# ============================================================
print("\n[3/4] 实验2: 反转策略参数优化")
print("=" * 80)

rev_params = {}
for mom_w in [1, 3, 5]:
    for top_pct in [0.02, 0.05, 0.10, 0.20]:
        mom_col = f'mom_{mom_w}'
        df_rev = df.copy()
        df_rev[mom_col] = -df_rev[mom_col]
        r = run_reversal(df_rev, trade_dates, mom_col=mom_col, top_pct=top_pct, cost=0.002,
                         use_timing=True, filter_limit_down=True)
        key = f'反转MOM{mom_w}_TOP{int(top_pct*100)}%'
        rev_params[key] = r
        print(f"  {key}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 实验3: 反转 + 成交量过滤
# ============================================================
print("\n[4/4] 实验3: 反转 + 成交量/换手率过滤")
print("=" * 80)

# 计算成交量分位数
df['vol_pctile'] = df.groupby('trade_date')['vol'].rank(pct=True)
df['amt_pctile'] = df.groupby('trade_date')['amount'].rank(pct=True)

vol_results = {}
for vol_filter in ['all', 'low_vol', 'high_vol']:
    working = df.copy()
    if vol_filter == 'low_vol':
        working = working[working['vol_pctile'] < 0.3]  # 低成交量
    elif vol_filter == 'high_vol':
        working = working[working['vol_pctile'] > 0.7]  # 高成交量
    
    mom_col = 'mom_1'
    working_rev = working.copy()
    working_rev[mom_col] = -working_rev[mom_col]
    
    r = run_reversal(working_rev, trade_dates, mom_col=mom_col, top_pct=0.05, cost=0.002,
                     use_timing=True, filter_limit_down=True)
    vol_results[f'反转MOM1_{vol_filter}'] = r
    print(f"  反转MOM1_{vol_filter}: 年化{r['ann_ret']:.2f}%, 回撤{r['max_dd']:.2f}%, 夏普{r['sharpe']:.2f}")

# ============================================================
# 总结
# ============================================================
print("\n" + "=" * 80)
print("📊 总结")
print("=" * 80)

all_r = {}
all_r.update(results)
all_r.update(rev_params)
all_r.update(vol_results)

sorted_r = sorted(all_r.items(), key=lambda x: x[1]['ann_ret'], reverse=True)

print(f"\n{'策略':<30} {'年化收益':>10} {'最大回撤':>10} {'夏普':>8}")
print("-" * 65)
for name, r in sorted_r[:20]:
    print(f"{name:<30} {r['ann_ret']:>9.2f}% {r['max_dd']:>9.2f}% {r['sharpe']:>8.2f}")

best_name, best_r = sorted_r[0]
print(f"\n🏆 最佳: {best_name}")
print(f"  年化: {best_r['ann_ret']}%, 回撤: {best_r['max_dd']}%, 夏普: {best_r['sharpe']}")
print(f"  分年: {best_r['by_year']}")

# 保存
summary = {
    'all_results': {k: {kk: vv for kk, vv in v.items()} for k, v in all_r.items()},
    'best': best_name,
    'best_details': best_r,
}
with open(SAVE_DIR + 'summary.json', 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

# 更新status
status = {
    "exp_id": "20260510_v2_reversal",
    "created_at": "2026-05-10T06:00:00+08:00",
    "status": "completed",
    "brief": "20260510_0503.md",
    "market": "A-STOCK",
    "report_done": True,
    "proposal_done": False,
    "summary": {
        "topic": "动量策略V2 — 短期反转策略",
        "key_finding": f"反转策略最佳: {best_name}, 年化{best_r['ann_ret']}%, 回撤{best_r['max_dd']}%",
        "sample_size": len(df)
    }
}
with open(SAVE_DIR + 'status.json', 'w') as f:
    json.dump(status, f, indent=2, ensure_ascii=False)

print(f"\n✅ V2 反转策略研究完成!")
