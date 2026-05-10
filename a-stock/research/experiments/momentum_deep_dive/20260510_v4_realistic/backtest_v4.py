#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动量策略深度优化 V4 — 真实约束验证 (高效版)
============================================
测试6个待验证假设:
1. 涨跌停过滤: 剔除涨停股(无法买入)和跌停股(风险高)
2. 冲击成本: 实际滑点0.2-0.3%对TOP5%高换手策略的影响
3. 仓位上限: 单股≤5%仓位对组合收益/回撤的影响
4. 动量衰减: MOM5信号在不同持有期(1d/3d/5d/10d)的衰减曲线
5. 行业中性: 行业去偏后的动量是否仍然有效
6. 波动率加权: 用波动率倒数加权替代等权/市值加权

方法论: 严格前向收益法 — T日收盘计算信号 → T+1日开盘→收盘收益率执行
"""

import requests
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

SAVE_DIR = os.path.dirname(os.path.abspath(__file__)) + '/'
CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(sql, fmt='TabSeparatedWithNames'):
    r = requests.get(CH_URL, params={'query': sql + f' FORMAT {fmt}'},
                     auth=CH_AUTH, timeout=120)
    r.raise_for_status()
    lines = r.text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    data = [line.split('\t') for line in lines[1:]]
    return pd.DataFrame(data, columns=cols)

print("=" * 60)
print("动量策略 V4 — 真实约束验证 (高效版)")
print("=" * 60)

# ============================================================
# 第一步: 获取数据
# ============================================================
print("\n[1/5] 获取数据...")

# 日线行情
print("  获取日线数据...")
daily_sql = """
SELECT ts_code, trade_date, open, high, low, close, vol, pct_chg, amount
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20190601'
"""
daily = ch_query(daily_sql)
for c in ['open', 'high', 'low', 'close', 'vol', 'pct_chg', 'amount']:
    daily[c] = pd.to_numeric(daily[c], errors='coerce')
daily['trade_date'] = pd.to_datetime(daily['trade_date'])
print(f"  日线: {len(daily):,} 条, {daily['ts_code'].nunique():,} 只股票")

# 基本面
print("  获取基本面数据...")
basic_sql = """
SELECT ts_code, trade_date, turnover_rate, total_mv, circ_mv
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '20190601'
"""
basic = ch_query(basic_sql)
for c in ['turnover_rate', 'total_mv', 'circ_mv']:
    basic[c] = pd.to_numeric(basic[c], errors='coerce')
basic['trade_date'] = pd.to_datetime(basic['trade_date'])

# 股票信息 (行业) — 用内置字典替代, 不需要查询
# 行业中性化在V5中单独测试

# CSI300
print("  获取CSI300...")
idx_sql = """
SELECT trade_date, close
FROM tushare.tushare_index_daily FINAL
WHERE ts_code = '000300.SH' AND trade_date >= '20190601'
"""
csi300 = ch_query(idx_sql)
csi300['close'] = pd.to_numeric(csi300['close'], errors='coerce')
csi300['trade_date'] = pd.to_datetime(csi300['trade_date'])
csi300 = csi300.sort_values('trade_date').reset_index(drop=True)

print("  数据获取完成!")

# ============================================================
# 第二步: 数据预处理
# ============================================================
print("\n[2/5] 预处理...")

df = daily.merge(basic, on=['ts_code', 'trade_date'], how='left')
# 过滤新股 (简化: 用list_date在daily数据之前60天)
df['days_since_ipo'] = 999  # 假设都满足, 后续可以改进

# 涨跌停标记 (简化: pct_chg >= 9.8% = 涨停)
df['is_limit_up'] = (df['pct_chg'] >= 9.8).astype(int)
df['is_limit_down'] = (df['pct_chg'] <= -9.8).astype(int)

# CSI300择时
csi300['ma200'] = csi300['close'].rolling(200).mean()
csi300['bull'] = (csi300['close'] > csi300['ma200']).astype(int)
csi300_timing = csi300[['trade_date', 'close', 'ma200', 'bull']].copy()

# 计算MOM5
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)
df['close_lag5'] = df.groupby('ts_code')['close'].shift(5)
df['mom5'] = df['close'] / df['close_lag5'] - 1

# 计算20日波动率
df['vol_20d'] = df.groupby('ts_code')['pct_chg'].transform(lambda x: x.rolling(20).std())

# 计算T+1日收益率 (严格前向: T日信号 → T+1日open→close)
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)
df['next_open'] = df.groupby('ts_code')['open'].shift(-1)
df['next_close'] = df.groupby('ts_code')['close'].shift(-1)
df['forward_ret'] = (df['next_close'] - df['next_open']) / df['next_open']
# 多持有期收益率
for h in [3, 5, 10]:
    df[f'fwd_ret_{h}d'] = (df.groupby('ts_code')['close'].shift(-h) - df['next_open']) / df['next_open']

# 只保留2020年后的数据
df = df[df['trade_date'] >= '2020-01-01'].copy()
df = df.dropna(subset=['mom5', 'forward_ret']).copy()

# 合并择时信号
df = df.merge(csi300_timing[['trade_date', 'bull']], on='trade_date', how='left')
df['bull'] = df['bull'].fillna(0).astype(int)

print(f"  处理后: {len(df):,} 条, {df['ts_code'].nunique():,} 只股票")
print(f"  交易日: {df['trade_date'].nunique()}")

# ============================================================
# 第三步: 信号截面筛选 + 策略组合收益计算
# ============================================================
print("\n[3/5] 计算各策略组合收益...")

# 只取牛市日的信号
bull_df = df[df['bull'] == 1].copy()
trade_dates_sorted = sorted(df['trade_date'].unique())

def compute_portfolio_returns(signal_df, top_pct, signal_col='mom5', 
                               limit_filter=False, hold_days=1,
                               weight_method='equal', pos_cap=1.0,
                               cost=0.0015, ret_col='forward_ret'):
    """
    计算组合收益序列
    signal_df: 包含信号的股票池 (已过滤牛市)
    top_pct: 持仓比例 (0.05 = TOP5%)
    signal_col: 信号列名
    limit_filter: 是否过滤涨跌停
    hold_days: 持有天数 (1, 3, 5, 10)
    weight_method: 'equal', 'vol_inv'
    pos_cap: 单股最大仓位
    cost: 单边交易成本
    ret_col: 收益率列名
    """
    data = signal_df.copy()
    
    if limit_filter:
        data = data[(data['is_limit_up'] == 0) & (data['is_limit_down'] == 0)]
    
    # 每个交易日选TOP_pct的股票
    def select_top(group):
        valid = group[group[signal_col].notna()]
        if len(valid) < 5:
            return pd.Series({'portfolio_ret': np.nan, 'n_stocks': 0})
        threshold = valid[signal_col].quantile(1 - top_pct)
        selected = valid[valid[signal_col] >= threshold]
        
        # 计算权重
        if weight_method == 'vol_inv' and 'vol_20d' in selected.columns:
            sel = selected[selected['vol_20d'] > 0].copy()
            if len(sel) > 0:
                sel['weight'] = (1.0 / sel['vol_20d'])
                sel['weight'] = sel['weight'] / sel['weight'].sum()
            else:
                sel = selected.copy()
                sel['weight'] = 1.0 / len(sel)
        else:
            sel = selected.copy()
            sel['weight'] = 1.0 / len(sel)
        
        # 仓位上限
        if pos_cap < 1.0:
            sel['weight'] = sel['weight'].clip(upper=pos_cap)
            sel['weight'] = sel['weight'] / sel['weight'].sum()
        
        # 返回选中的股票及其收益率
        valid_ret = sel[sel[ret_col].notna()]
        if len(valid_ret) == 0:
            return pd.Series({'portfolio_ret': np.nan, 'n_stocks': 0})
        
        port_ret = (valid_ret['weight'] * valid_ret[ret_col]).sum()
        return pd.Series({
            'portfolio_ret': port_ret,
            'n_stocks': len(valid_ret),
        })
    
    daily_port = data.groupby('trade_date').apply(select_top, include_groups=False)
    
    if len(daily_port) == 0 or daily_port['portfolio_ret'].isna().all():
        return pd.Series(dtype=float), 0, pd.DataFrame()
    
    # 减去交易成本 (每次换仓)
    daily_port['portfolio_ret'] = daily_port['portfolio_ret'] - cost * 2 * 0.5
    
    return daily_port['portfolio_ret'], daily_port['n_stocks'].mean(), daily_port

# 定义策略配置
strategies = {
    'S0_BASE': {
        'name': '基准: 等权全市场',
        'top_pct': 1.0, 'signal_col': 'mom5',
        'limit_filter': False, 'hold_days': 1,
        'weight': 'equal', 'pos_cap': 1.0, 'cost': 0.0,
    },
    'S1_MOM5_TOP5': {
        'name': '原始: MOM5_TOP5% (含0.15%成本, 前向)',
        'top_pct': 0.05, 'signal_col': 'mom5',
        'limit_filter': False, 'hold_days': 1,
        'weight': 'equal', 'pos_cap': 1.0, 'cost': 0.0015,
    },
    'S2_LIMIT_FILTER': {
        'name': '假设1: +涨跌停过滤',
        'top_pct': 0.05, 'signal_col': 'mom5',
        'limit_filter': True, 'hold_days': 1,
        'weight': 'equal', 'pos_cap': 1.0, 'cost': 0.0015,
    },
    'S3_HIGH_COST': {
        'name': '假设2: +冲击成本0.3%(单边)',
        'top_pct': 0.05, 'signal_col': 'mom5',
        'limit_filter': False, 'hold_days': 1,
        'weight': 'equal', 'pos_cap': 1.0, 'cost': 0.0030,
    },
    'S4_POS_CAP': {
        'name': '假设3: 单股≤5%仓位上限',
        'top_pct': 0.05, 'signal_col': 'mom5',
        'limit_filter': False, 'hold_days': 1,
        'weight': 'equal', 'pos_cap': 0.05, 'cost': 0.0015,
    },
    'S5_HOLD1D': {
        'name': '假设4a: 持有1日',
        'top_pct': 0.05, 'signal_col': 'mom5',
        'limit_filter': False, 'hold_days': 1,
        'weight': 'equal', 'pos_cap': 1.0, 'cost': 0.0015,
        'ret_col': 'forward_ret',
    },
    'S6_HOLD3D': {
        'name': '假设4b: 持有3日',
        'top_pct': 0.05, 'signal_col': 'mom5',
        'limit_filter': False, 'hold_days': 1,
        'weight': 'equal', 'pos_cap': 1.0, 'cost': 0.0015,
        'ret_col': 'fwd_ret_3d',
    },
    'S7_HOLD5D': {
        'name': '假设4c: 持有5日',
        'top_pct': 0.05, 'signal_col': 'mom5',
        'limit_filter': False, 'hold_days': 1,
        'weight': 'equal', 'pos_cap': 1.0, 'cost': 0.0015,
        'ret_col': 'fwd_ret_5d',
    },
    'S8_HOLD10D': {
        'name': '假设4d: 持有10日',
        'top_pct': 0.05, 'signal_col': 'mom5',
        'limit_filter': False, 'hold_days': 1,
        'weight': 'equal', 'pos_cap': 1.0, 'cost': 0.0015,
        'ret_col': 'fwd_ret_10d',
    },
    'S10_VOL_WEIGHT': {
        'name': '假设6: 波动率倒数加权',
        'top_pct': 0.05, 'signal_col': 'mom5',
        'limit_filter': False, 'hold_days': 1,
        'weight': 'vol_inv', 'pos_cap': 1.0, 'cost': 0.0015,
    },
    'S11_FULL': {
        'name': '全约束: 涨跌停+高成本+仓位上限',
        'top_pct': 0.05, 'signal_col': 'mom5',
        'limit_filter': True, 'hold_days': 1,
        'weight': 'equal', 'pos_cap': 0.05, 'cost': 0.0030,
    },
}

results = {}

for strat_id, params in strategies.items():
    print(f"  运行 {strat_id}: {params['name']}...")
    
    ret_col = params.get('ret_col', 'forward_ret')
    
    port_ret, avg_stocks, daily_port = compute_portfolio_returns(
        bull_df, params['top_pct'], params['signal_col'],
        params['limit_filter'], params['hold_days'],
        params['weight'], params['pos_cap'], params['cost'],
        ret_col
    )
    
    if len(port_ret) == 0 or port_ret.isna().all():
        print(f"    ⚠️ 无有效信号")
        continue
    
    port_ret_clean = port_ret.dropna()
    nav = (1 + port_ret_clean).cumprod()
    
    total_ret = nav.iloc[-1] / nav.iloc[0] - 1
    years = len(port_ret_clean) / 252
    ann_ret = (1 + total_ret) ** (1 / years) - 1 if years > 0 else 0
    
    cummax = nav.cummax()
    drawdown = (nav - cummax) / cummax
    max_dd = drawdown.min()
    
    sharpe = (port_ret_clean.mean() * 252 - 0.02) / (port_ret_clean.std() * np.sqrt(252)) if port_ret_clean.std() > 0 else 0
    
    # 胜率
    win_rate = (port_ret_clean > 0).mean()
    
    results[strat_id] = {
        'name': params['name'],
        'annual_return': ann_ret,
        'total_return': total_ret,
        'max_drawdown': max_dd,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'years': years,
        'n_days': len(port_ret_clean),
        'avg_stocks': avg_stocks,
        'nav': nav,
        'daily_ret': port_ret_clean,
    }
    
    print(f"    年化: {ann_ret*100:+.2f}%, 回撤: {max_dd*100:.2f}%, "
          f"夏普: {sharpe:.2f}, 胜率: {win_rate*100:.1f}%, 天数: {len(port_ret_clean)}")

# ============================================================
# 第四步: 分年度分析
# ============================================================
print("\n[4/5] 分年度分析...")

yearly_results = {}
for strat_id, res in results.items():
    nav = res['nav']
    yearly = {}
    for year in range(2020, 2027):
        year_nav = nav[nav.index.year == year]
        if len(year_nav) >= 2:
            yearly[str(year)] = year_nav.iloc[-1] / year_nav.iloc[0] - 1
    yearly_results[strat_id] = yearly

# ============================================================
# 第五步: 输出
# ============================================================
print("\n[5/5] 汇总输出...")

print("\n" + "=" * 100)
print("V4 真实约束验证 — 策略对比汇总表")
print("=" * 100)
print(f"{'策略':<12} {'策略名称':<40} {'年化收益':<10} {'最大回撤':<10} "
      f"{'夏普':<8} {'胜率':<8} {'交易天数':<8} {'平均持仓'}")
print("-" * 100)

for strat_id, res in results.items():
    print(f"{strat_id:<12} {res['name']:<40} {res['annual_return']*100:<+10.2f} "
          f"{res['max_drawdown']*100:<10.2f} {res['sharpe']:<8.2f} "
          f"{res['win_rate']*100:<8.1f} {res['n_days']:<8} {res['avg_stocks']:.0f}")

print("=" * 100)

# 分年度
print("\n分年度收益率:")
print(f"{'策略':<12} {'2020':<10} {'2021':<10} {'2022':<10} {'2023':<10} {'2024':<10} {'2025':<10} {'2026':<10}")
print("-" * 82)
for strat_id in results:
    row = [strat_id]
    for y in range(2020, 2027):
        val = yearly_results.get(strat_id, {}).get(str(y), None)
        row.append(f"{val*100:+.1f}%" if val is not None else "N/A")
    print(f"{row[0]:<12} {row[1]:<10} {row[2]:<10} {row[3]:<10} {row[4]:<10} {row[5]:<10} {row[6]:<10} {row[7]:<10}")

# 假设检验结论
print("\n" + "=" * 80)
print("📋 假设检验结论:")
print("=" * 80)

# 假设1: 涨跌停过滤
if 'S1_MOM5_TOP5' in results and 'S2_LIMIT_FILTER' in results:
    s1 = results['S1_MOM5_TOP5']
    s2 = results['S2_LIMIT_FILTER']
    print(f"\n假设1 (涨跌停过滤): {s1['name']} → {s2['name']}")
    print(f"  年化变化: {s1['annual_return']*100:.2f}% → {s2['annual_return']*100:.2f}% "
          f"(Δ{ (s2['annual_return']-s1['annual_return'])*100:+.2f}%)")
    print(f"  回撤变化: {s1['max_drawdown']*100:.2f}% → {s2['max_drawdown']*100:.2f}%")

# 假设2: 冲击成本
if 'S1_MOM5_TOP5' in results and 'S3_HIGH_COST' in results:
    s1 = results['S1_MOM5_TOP5']
    s3 = results['S3_HIGH_COST']
    print(f"\n假设2 (冲击成本0.3%): {s1['name']} → {s3['name']}")
    print(f"  年化变化: {s1['annual_return']*100:.2f}% → {s3['annual_return']*100:.2f}% "
          f"(Δ{(s3['annual_return']-s1['annual_return'])*100:+.2f}%)")

# 假设3: 仓位上限
if 'S1_MOM5_TOP5' in results and 'S4_POS_CAP' in results:
    s1 = results['S1_MOM5_TOP5']
    s4 = results['S4_POS_CAP']
    print(f"\n假设3 (仓位上限5%): {s1['name']} → {s4['name']}")
    print(f"  年化变化: {s1['annual_return']*100:.2f}% → {s4['annual_return']*100:.2f}% "
          f"(Δ{(s4['annual_return']-s1['annual_return'])*100:+.2f}%)")
    print(f"  回撤变化: {s1['max_drawdown']*100:.2f}% → {s4['max_drawdown']*100:.2f}%")

# 假设4: 动量衰减
print(f"\n假设4 (动量衰减曲线):")
for h, sid in [(1, 'S5_HOLD1D'), (3, 'S6_HOLD3D'), (5, 'S7_HOLD5D'), (10, 'S8_HOLD10D')]:
    if sid in results:
        r = results[sid]
        print(f"  持有{h}日: 年化{r['annual_return']*100:+.2f}%, 夏普{r['sharpe']:.2f}, "
              f"胜率{r['win_rate']*100:.1f}%")

# 假设5: 行业中性 (需要行业数据, 留到V5测试)
print(f"\n假设5 (行业中性): 需要行业分类数据, 留到V5测试")

# 假设6: 波动率加权
if 'S1_MOM5_TOP5' in results and 'S10_VOL_WEIGHT' in results:
    s1 = results['S1_MOM5_TOP5']
    s10 = results['S10_VOL_WEIGHT']
    print(f"\n假设6 (波动率加权): {s1['name']} → {s10['name']}")
    print(f"  年化变化: {s1['annual_return']*100:.2f}% → {s10['annual_return']*100:.2f}% "
          f"(Δ{(s10['annual_return']-s1['annual_return'])*100:+.2f}%)")
    print(f"  回撤变化: {s1['max_drawdown']*100:.2f}% → {s10['max_drawdown']*100:.2f}%")

# 全约束
if 'S11_FULL' in results:
    s11 = results['S11_FULL']
    print(f"\n全约束策略: {s11['name']}")
    print(f"  年化: {s11['annual_return']*100:+.2f}%, 回撤: {s11['max_drawdown']*100:.2f}%, "
          f"夏普: {s11['sharpe']:.2f}")

# ─── 保存结果 ───
summary = {}
for sid, res in results.items():
    summary[sid] = {
        'name': res['name'],
        'annual_return': round(res['annual_return'], 4),
        'total_return': round(res['total_return'], 4),
        'max_drawdown': round(res['max_drawdown'], 4),
        'sharpe': round(res['sharpe'], 2),
        'win_rate': round(res['win_rate'], 4),
        'n_days': res['n_days'],
        'years': round(res['years'], 2),
    }

with open(SAVE_DIR + 'results.json', 'w') as f:
    json.dump({'strategies': summary, 'yearly': yearly_results}, f, ensure_ascii=False, indent=2)

print(f"\n结果已保存至 {SAVE_DIR}results.json")

# ─── 更新 status.json ───
best = max(results.items(), key=lambda x: x[1]['sharpe'])
status = {
    "exp_id": "20260510_v4_realistic",
    "created_at": "2026-05-10T07:05:00+08:00",
    "status": "completed",
    "brief": "20260510_0701.md",
    "market": "A-STOCK",
    "report_done": False,
    "proposal_done": False,
    "summary": {
        "topic": "动量策略真实约束验证 (6个假设)",
        "key_finding": f"最佳夏普策略: {best[1]['name']}, "
                       f"年化{best[1]['annual_return']*100:.2f}%, "
                       f"夏普{best[1]['sharpe']:.2f}",
        "sample_size": len(bull_df),
    }
}
with open(SAVE_DIR + 'status.json', 'w') as f:
    json.dump(status, f, ensure_ascii=False, indent=2)

print("status.json 已更新")
print("\n✅ V4 回测完成!")
