#!/usr/bin/env python3
"""
空方力量衰竭与底部反转 - 修正版
"""

import requests
import pandas as pd
import numpy as np
from math import erf, sqrt
import json, os

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(query, fmt='TabSeparatedWithNames'):
    q = f"{query} FORMAT {fmt}"
    r = requests.get(CH_URL, params={'query': q}, auth=CH_AUTH, timeout=120)
    if r.status_code != 200:
        raise Exception(f"CH Error: {r.text}")
    lines = r.text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    data = [line.split('\t') for line in lines[1:] if len(line.split('\t')) == len(cols)]
    return pd.DataFrame(data, columns=cols)

def ttest_1samp(arr, popmean=0):
    n = len(arr)
    if n < 2:
        return type('T', (), {'statistic': 0, 'pvalue': 1.0})()
    m = np.mean(arr)
    s = np.std(arr, ddof=1)
    if s < 1e-12:
        return type('T', (), {'statistic': 0, 'pvalue': 1.0})()
    t = (m - popmean) / (s / sqrt(n))
    p = 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2))))
    return type('T', (), {'statistic': t, 'pvalue': p})()

print("=" * 60)
print("空方力量衰竭与底部反转 - 修正版")
print("=" * 60)

# 加载已处理的数据
data_path = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/20260509_v18_exhaustion/data/processed.pkl'
if os.path.exists(data_path):
    print("\n加载已处理数据...")
    df = pd.read_pickle(data_path)
    print(f"  {len(df):,} 条记录")
else:
    print("数据文件不存在，请先运行数据获取步骤")
    sys.exit(1)

# ============================================================
# 假设检验 (修正版)
# ============================================================
results = {}
base_1d = df['ret_1d'].mean()
base_3d = df['ret_3d'].mean()
print(f"\n基准: 1日={base_1d:.4f}, 3日={base_3d:.4f}")

# ============================================================
# H1: 连续N日缩量后放量收阳 (修正逻辑)
# ============================================================
print("\n" + "=" * 60)
print("H1: 连续N日缩量后放量收阳 (修正)")
print("=" * 60)

# 修正: 前一日连续缩量 >= N，今天放量收阳
# shrink_streak 是今天的连续缩量天数，如果今天放量，shrink_streak=0
# 我们需要看"今天之前的连续缩量天数"
df['prev_shrink_streak'] = df.groupby('ts_code')['shrink_streak'].shift(1)

# 信号: 前一日有连续N天缩量 + 今天放量收阳
for n in [2, 3, 4, 5]:
    h1 = df[(df['prev_shrink_streak'] >= n) & (df['vol_ratio'] > 1.5) & (df['pct_chg'] > 0)]
    if len(h1) > 30:
        wr1 = (h1['ret_1d'] > 0).sum() / h1['ret_1d'].notna().sum()
        mr1 = h1['ret_1d'].mean()
        t = ttest_1samp(h1['ret_1d'].dropna().values)
        wr3 = (h1['ret_3d'] > 0).sum() / h1['ret_3d'].notna().sum()
        mr3 = h1['ret_3d'].mean()
        wr5 = (h1['ret_5d'] > 0).sum() / h1['ret_5d'].notna().sum()
        mr5 = h1['ret_5d'].mean()
        print(f"\n  前{n}日缩量 → 放量收阳: {len(h1):,}信号")
        print(f"    1日: 胜率={wr1:.1%}, 均值={mr1:.4f}, t={t.statistic:.3f}, p={t.pvalue:.6f}")
        print(f"    3日: 胜率={wr3:.1%}, 均值={mr3:.4f}")
        print(f"    5日: 胜率={wr5:.1%}, 均值={mr5:.4f}")
        
        if n == 3:
            results['H1'] = {
                'signal_count': len(h1),
                'win_rate_1d': f"{wr1:.1%}",
                'mean_ret_1d': f"{mr1:.4f}",
                'win_rate_3d': f"{wr3:.1%}",
                'mean_ret_3d': f"{mr3:.4f}",
                't_stat': f"{t.statistic:.4f}",
                'p_value': f"{t.pvalue:.6f}",
                'significant': bool(t.pvalue < 0.05),
            }
    else:
        print(f"\n  前{n}日缩量 → 放量收阳: 信号不足({len(h1)})")

# ============================================================
# H2: MACD底背离金叉 (已有结果，补充分析)
# ============================================================
print("\n" + "=" * 60)
print("H2: MACD底背离金叉 (深度分析)")
print("=" * 60)

h2 = df[df['divergence_cross']]
print(f"  总信号: {len(h2):,}")

if len(h2) > 30:
    # 已经知道1日胜率49.3%，现在做更多细分
    
    # 按价格位置细分
    print("\n  按价格位置细分:")
    for pct in [0.2, 0.3, 0.4, 0.5]:
        sub = h2[h2['close_pct_rank'] < pct]
        if len(sub) > 30:
            wr = (sub['ret_1d'] > 0).sum() / sub['ret_1d'].notna().sum()
            mr = sub['ret_1d'].mean()
            print(f"    价格底部{pct:.0%}: {len(sub)}信号, 胜率={wr:.1%}, 均值={mr:.4f}")
    
    # 按缩量状态细分
    print("\n  按缩量状态细分:")
    sub_shrink = h2[h2['prev_shrink_streak'] >= 3]
    if len(sub_shrink) > 30:
        wr = (sub_shrink['ret_1d'] > 0).sum() / sub_shrink['ret_1d'].notna().sum()
        mr = sub_shrink['ret_1d'].mean()
        print(f"    含前3日缩量: {len(sub_shrink)}信号, 胜率={wr:.1%}, 均值={mr:.4f}")
    
    # 按形态细分
    print("\n  按K线形态细分:")
    sub_hammer = h2[h2['is_hammer'] == 1]
    if len(sub_hammer) > 30:
        wr = (sub_hammer['ret_1d'] > 0).sum() / sub_hammer['ret_1d'].notna().sum()
        mr = sub_hammer['ret_1d'].mean()
        print(f"    锤子线: {len(sub_hammer)}信号, 胜率={wr:.1%}, 均值={mr:.4f}")
    
    # 保存H2结果
    results['H2'] = {
        'signal_count': len(h2),
        'win_rate_1d': f"{(h2['ret_1d']>0).sum()/h2['ret_1d'].notna().sum():.1%}",
        'mean_ret_1d': f"{h2['ret_1d'].mean():.4f}",
        'win_rate_3d': f"{(h2['ret_3d']>0).sum()/h2['ret_3d'].notna().sum():.1%}",
        'mean_ret_3d': f"{h2['ret_3d'].mean():.4f}",
    }

# ============================================================
# H3: 地量 + 长下影线 (已有结果)
# ============================================================
print("\n" + "=" * 60)
print("H3: 地量 + 长下影线 (补充)")
print("=" * 60)

h3 = df[(df['vol_ratio'] < 0.5) & (df['is_long_lower'] == 1)]
print(f"  信号: {len(h3):,}")

# 尝试不同地量阈值
print("\n  不同地量阈值:")
for thresh in [0.3, 0.4, 0.5, 0.6]:
    sub = df[(df['vol_ratio'] < thresh) & (df['is_long_lower'] == 1)]
    if len(sub) > 30:
        wr = (sub['ret_1d'] > 0).sum() / sub['ret_1d'].notna().sum()
        mr = sub['ret_1d'].mean()
        t = ttest_1samp(sub['ret_1d'].dropna().values)
        print(f"    vol_ratio<{thresh}: {len(sub):,}信号, 胜率={wr:.1%}, 均值={mr:.4f}, p={t.pvalue:.6f}")

# 叠加RSI超卖
print("\n  叠加RSI超卖:")
for rsi_bound in [20, 25, 30]:
    sub = df[(df['vol_ratio'] < 0.5) & (df['is_long_lower'] == 1) & (df['rsi14'] < rsi_bound)]
    if len(sub) > 30:
        wr = (sub['ret_1d'] > 0).sum() / sub['ret_1d'].notna().sum()
        mr = sub['ret_1d'].mean()
        print(f"    RSI<{rsi_bound}: {len(sub)}信号, 胜率={wr:.1%}, 均值={mr:.4f}")

# ============================================================
# H4: 市值过滤
# ============================================================
print("\n" + "=" * 60)
print("H4: 叠加市值过滤")
print("=" * 60)

# 获取样本股票列表用于市值查询
sample_str = "','".join(df['ts_code'].unique())
q_mv = f"""
SELECT ts_code, trade_date, total_mv, turnover_rate
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '20200101' AND trade_date <= '20260508'
  AND ts_code IN ('{sample_str}')
"""
print("  获取市值数据...")
df_mv = ch_query(q_mv)
df_mv['trade_date'] = pd.to_datetime(df_mv['trade_date'])
df_mv['total_mv'] = pd.to_numeric(df_mv['total_mv'], errors='coerce')
df_mv['turnover_rate'] = pd.to_numeric(df_mv['turnover_rate'], errors='coerce')

df = df.merge(df_mv[['ts_code', 'trade_date', 'total_mv', 'turnover_rate']], 
              on=['ts_code', 'trade_date'], how='left')

g = df.groupby('ts_code', sort=False)
df['mv_pctile'] = g['total_mv'].transform(lambda x: x.rank(pct=True))

# H4a: 地量+长下影+低位+小市值
h4 = df[
    (df['vol_ratio'] < 0.5) &
    (df['is_long_lower'] == 1) &
    (df['close_pct_rank'] < 0.3) &
    (df['mv_pctile'] < 0.5)
]
print(f"\n  地量+长下影+低位+小市值: {len(h4):,}信号")
if len(h4) > 30:
    wr = (h4['ret_1d'] > 0).sum() / h4['ret_1d'].notna().sum()
    mr = h4['ret_1d'].mean()
    wr3 = (h4['ret_3d'] > 0).sum() / h4['ret_3d'].notna().sum()
    print(f"  1日: 胜率={wr:.1%}, 均值={mr:.4f}")
    print(f"  3日: 胜率={wr3:.1%}, 均值={h4['ret_3d'].mean():.4f}")
    results['H4'] = {'signal_count': len(h4), 'win_rate_1d': f"{wr:.1%}", 'mean_ret_1d': f"{mr:.4f}"}

# H4b: 地量+长下影+大市值
h4b = df[
    (df['vol_ratio'] < 0.5) &
    (df['is_long_lower'] == 1) &
    (df['close_pct_rank'] < 0.3) &
    (df['mv_pctile'] > 0.8)
]
print(f"\n  地量+长下影+低位+大市值: {len(h4b):,}信号")
if len(h4b) > 30:
    wr = (h4b['ret_1d'] > 0).sum() / h4b['ret_1d'].notna().sum()
    mr = h4b['ret_1d'].mean()
    print(f"  1日: 胜率={wr:.1%}, 均值={mr:.4f}")

# ============================================================
# H5: 综合最强信号
# ============================================================
print("\n" + "=" * 60)
print("H5: 综合最强衰竭信号")
print("=" * 60)

# 方案: 前3日缩量 + RSI超卖 + 长下影 + 放量阳线
h5 = df[
    (df['prev_shrink_streak'] >= 3) &
    (df['rsi14'] < 35) &
    (df['lower_shadow_ratio'] > 0.3) &
    (df['vol_ratio'] > 1.3) &
    (df['pct_chg'] > 0)
]
print(f"  综合信号: {len(h5):,}")

if len(h5) >= 30:
    wr = (h5['ret_1d'] > 0).sum() / h5['ret_1d'].notna().sum()
    mr = h5['ret_1d'].mean()
    t = ttest_1samp(h5['ret_1d'].dropna().values)
    wr3 = (h5['ret_3d'] > 0).sum() / h5['ret_3d'].notna().sum()
    mr3 = h5['ret_3d'].mean()
    wr5 = (h5['ret_5d'] > 0).sum() / h5['ret_5d'].notna().sum()
    mr5 = h5['ret_5d'].mean()
    excess = mr - base_1d
    
    print(f"  1日: 胜率={wr:.1%}, 均值={mr:.4f}, 超额={excess:.4f}, p={t.pvalue:.6f}")
    print(f"  3日: 胜率={wr3:.1%}, 均值={mr3:.4f}")
    print(f"  5日: 胜率={wr5:.1%}, 均值={mr5:.4f}")
    
    results['H5'] = {
        'signal_count': len(h5),
        'win_rate_1d': f"{wr:.1%}",
        'mean_ret_1d': f"{mr:.4f}",
        'win_rate_3d': f"{wr3:.1%}",
        'mean_ret_3d': f"{mr3:.4f}",
        'win_rate_5d': f"{wr5:.1%}",
        'mean_ret_5d': f"{mr5:.4f}",
        'excess_vs_base': f"{excess:.4f}",
        't_stat': f"{t.statistic:.4f}",
        'p_value': f"{t.pvalue:.6f}",
    }
else:
    print("  信号不足，尝试放宽条件...")
    h5b = df[
        (df['prev_shrink_streak'] >= 2) &
        (df['rsi14'] < 40) &
        (df['vol_ratio'] > 1.2) &
        (df['pct_chg'] > 0)
    ]
    print(f"  放宽信号: {len(h5b):,}")
    if len(h5b) > 30:
        wr = (h5b['ret_1d'] > 0).sum() / h5b['ret_1d'].notna().sum()
        mr = h5b['ret_1d'].mean()
        print(f"  1日: 胜率={wr:.1%}, 均值={mr:.4f}")
        results['H5'] = {'signal_count': len(h5b), 'win_rate_1d': f"{wr:.1%}", 'mean_ret_1d': f"{mr:.4f}"}

# ============================================================
# H6: 事件研究 - 衰竭信号在熊市 vs 牛市的表现
# ============================================================
print("\n" + "=" * 60)
print("H6: 市场环境分析")
print("=" * 60)

df['year'] = df['trade_date'].dt.year
df['month'] = df['trade_date'].dt.month

# 按年度分析 H1 信号
if 'H1' in results:
    h1_df = df[(df['prev_shrink_streak'] >= 3) & (df['vol_ratio'] > 1.5) & (df['pct_chg'] > 0)]
    print("\n  H1信号年度表现:")
    for yr in sorted(df['year'].unique()):
        sub = h1_df[df['year'] == yr]
        if len(sub) > 30:
            wr = (sub['ret_1d'] > 0).sum() / sub['ret_1d'].notna().sum()
            mr = sub['ret_1d'].mean()
            print(f"    {yr}: {len(sub)}信号, 胜率={wr:.1%}, 均值={mr:.4f}")

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 60)
print("📊 假设检验汇总")
print("=" * 60)
for k, v in results.items():
    print(f"  {k}: {v}")

# 保存
os.makedirs('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/20260509_v18_exhaustion/data', exist_ok=True)
with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/20260509_v18_exhaustion/data/results.json', 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# 保存完整数据供后续分析
df.to_pickle('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/20260509_v18_exhaustion/data/processed_full.pkl')

print("\n✅ 所有测试完成")
