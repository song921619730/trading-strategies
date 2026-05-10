"""
V1: 市场择时信号研究 — 指数MA过滤 vs 选股
核心问题: 能否通过择时(而非选股)获得正收益?
"""
import requests
import pandas as pd
import numpy as np
import json
import time

CK_URL = 'http://172.24.224.1:8123/'
CK_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ck_query(sql, fmt='TabSeparatedWithNames'):
    r = requests.get(CK_URL, params={'query': sql + f' FORMAT {fmt}'}, auth=CK_AUTH, timeout=300)
    r.raise_for_status()
    lines = r.text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    data = [line.split('\t') for line in lines[1:]]
    return pd.DataFrame(data, columns=cols)

RESULTS_DIR = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/experiments/市场择时信号_(market_regime_timing)/20260510_v1_timing/'

print("=" * 70)
print("V1: 市场择时信号研究")
print("=" * 70)

# ============================================================
# 加载指数数据
# ============================================================
t0 = time.time()
print("\n[1/4] 加载指数数据...")

indices = {
    'CSI300': '000300.SH',
    'CSI1000': '000852.SH',
    'SSE': '000001.SH',  # 上证指数
    'CSI500': '000905.SH',
}

idx_data = {}
for name, code in indices.items():
    sql = f"SELECT trade_date, close FROM tushare.tushare_index_daily FINAL WHERE ts_code='{code}' AND trade_date>='20190101' ORDER BY trade_date"
    df_idx = ck_query(sql)
    df_idx['close'] = pd.to_numeric(df_idx['close'], errors='coerce')
    df_idx['trade_date'] = pd.to_datetime(df_idx['trade_date'])
    
    for ma in [100, 120, 200, 250]:
        df_idx[f'ma{ma}'] = df_idx['close'].rolling(ma, min_periods=ma//2).mean()
        df_idx[f'bull_ma{ma}'] = df_idx['close'] > df_idx[f'ma{ma}']
    
    idx_data[name] = df_idx
    print(f"  {name} ({code}): {len(df_idx)} 行")

print(f"  耗时 {time.time()-t0:.1f}s")

# ============================================================
# 获取全A股日线 (仅收盘, 用于计算等权组合收益)
# ============================================================
t0 = time.time()
print("\n[2/4] 获取全A股日线...")

sql = """
SELECT ts_code, trade_date, close, pct_chg
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20200101'
ORDER BY trade_date, ts_code
"""
df_all = ck_query(sql)
df_all['close'] = pd.to_numeric(df_all['close'], errors='coerce')
df_all['pct_chg'] = pd.to_numeric(df_all['pct_chg'], errors='coerce')
df_all['trade_date'] = pd.to_datetime(df_all['trade_date'])
print(f"  数据: {len(df_all):,} 行, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# 计算每日全市场等权收益
# ============================================================
t0 = time.time()
print("\n[3/4] 计算每日等权组合收益...")

daily_ret = df_all.groupby('trade_date')['pct_chg'].mean()  # 等权平均收益
daily_ret = daily_ret.reset_index()
daily_ret.columns = ['trade_date', 'ew_ret']

# 累积收益
daily_ret['cum_ew'] = (1 + daily_ret['ew_ret']/100).cumprod()

# 合并指数信号
for idx_name, df_idx in idx_data.items():
    for ma in [100, 120, 200, 250]:
        col = f'{idx_name}_bull_ma{ma}'
        daily_ret = daily_ret.merge(
            df_idx[['trade_date', f'bull_ma{ma}']].rename(columns={f'bull_ma{ma}': col}),
            on='trade_date', how='left'
        )

# 也添加指数自身收益
for idx_name, df_idx in idx_data.items():
    df_idx_copy = df_idx.copy()
    df_idx_copy[f'{idx_name}_ret'] = df_idx_copy['close'].pct_change() * 100
    daily_ret = daily_ret.merge(
        df_idx_copy[['trade_date', f'{idx_name}_ret']],
        on='trade_date', how='left'
    )

daily_ret = daily_ret.dropna()
daily_ret['year'] = daily_ret['trade_date'].dt.year

print(f"  合并后: {len(daily_ret):,} 行, 耗时 {time.time()-t0:.1f}s")

# ============================================================
# 测试择时策略
# ============================================================
print("\n" + "=" * 70)
print("📊 择时策略对比")
print("=" * 70)

# 策略定义
timing_strategies = {}

for idx_name in indices.keys():
    for ma in [100, 120, 200, 250]:
        sig_col = f'{idx_name}_bull_ma{ma}'
        name = f'{idx_name}>MA{ma}'
        timing_strategies[name] = sig_col

# 基准: 始终持有
daily_ret['always_hold'] = 1

results = {}

for name, sig_col in timing_strategies.items():
    if sig_col not in daily_ret.columns:
        continue
    
    sub = daily_ret.dropna(subset=[sig_col, 'ew_ret'])
    
    # 择时策略: 信号=True时持有, =False时空仓(收益=0)
    sub['timing_ret'] = sub.apply(lambda r: r['ew_ret'] if r[sig_col] else 0.0, axis=1)
    
    # 累积收益
    sub['cum_timing'] = (1 + sub['timing_ret']/100).cumprod()
    sub['cum_benchmark'] = (1 + sub['ew_ret']/100).cumprod()
    
    # 年化
    n_years = (sub['trade_date'].max() - sub['trade_date'].min()).days / 365.25
    total_timing = sub['cum_timing'].iloc[-1]
    total_bench = sub['cum_benchmark'].iloc[-1]
    ann_timing = (total_timing ** (1/n_years) - 1) * 100
    ann_bench = (total_bench ** (1/n_years) - 1) * 100
    
    # 最大回撤
    cummax_timing = sub['cum_timing'].cummax()
    max_dd_timing = ((sub['cum_timing'] - cummax_timing) / cummax_timing).min() * 100
    
    cummax_bench = sub['cum_benchmark'].cummax()
    max_dd_bench = ((sub['cum_benchmark'] - cummax_bench) / cummax_bench).min() * 100
    
    # 持仓天数比例
    hold_pct = sub[sig_col].mean() * 100
    
    # 分年度
    by_year = {}
    for y in sorted(sub['year'].unique()):
        ysub = sub[sub['year'] == y]
        t_ret = ysub['timing_ret'].sum()
        b_ret = ysub['ew_ret'].sum()
        by_year[int(y)] = {
            'timing': round(t_ret, 2),
            'benchmark': round(b_ret, 2),
            'hold_days': int(ysub[sig_col].sum()),
            'total_days': len(ysub),
        }
    
    results[name] = {
        'ann_timing': round(ann_timing, 2),
        'ann_bench': round(ann_bench, 2),
        'total_timing': round((total_timing-1)*100, 2),
        'total_bench': round((total_bench-1)*100, 2),
        'max_dd_timing': round(max_dd_timing, 2),
        'max_dd_bench': round(max_dd_bench, 2),
        'hold_pct': round(hold_pct, 1),
        'by_year': by_year,
    }

# 按年化收益排序
sorted_results = sorted(results.items(), key=lambda x: x[1]['ann_timing'], reverse=True)

print(f"\n{'策略':<20} {'年化择时':>10} {'年化基准':>10} {'总收益择时':>12} {'总收益基准':>12} {'最大回撤':>10} {'持仓%':>8}")
print("-" * 90)
for name, r in sorted_results:
    print(f"{name:<20} {r['ann_timing']:>9.2f}% {r['ann_bench']:>9.2f}% {r['total_timing']:>11.2f}% {r['total_bench']:>11.2f}% {r['max_dd_timing']:>9.2f}% {r['hold_pct']:>7.1f}%")

# ============================================================
# 最佳策略详细分析
# ============================================================
best_name, best_r = sorted_results[0]
print(f"\n" + "=" * 70)
print(f"🏆 最佳策略: {best_name}")
print("=" * 70)

print(f"\n分年度对比:")
print(f"{'年份':<6} {'择时收益':>10} {'基准收益':>10} {'持仓天数':>10} {'总天数':>8}")
print("-" * 50)
for y, stats in best_r['by_year'].items():
    print(f"{y:<6} {stats['timing']:>9.2f}% {stats['benchmark']:>9.2f}% {stats['hold_days']:>10} {stats['total_days']:>8}")

# ============================================================
# 测试: 择时 + 动量选股
# ============================================================
print("\n" + "=" * 70)
print("📊 进阶: 择时 + 动量选股")
print("=" * 70)

# 计算每只股票的20日动量
df_all['ret_20d'] = df_all.groupby('ts_code')['close'].transform(lambda x: x.pct_change(20))

# 每日动量排名
df_all['rank'] = df_all.groupby('trade_date')['ret_20d'].rank(pct=True)

# 合并择时信号
df_all = df_all.merge(
    daily_ret[['trade_date', 'CSI300_bull_ma200']].rename(columns={'CSI300_bull_ma200': 'bull'}),
    on='trade_date', how='left'
)

# 策略: 牛市持有前20%动量股, 熊市空仓
bull_days = df_all[df_all['bull'] == True]
bear_days = df_all[df_all['bull'] == False]

top20 = bull_days[bull_days['rank'] >= 0.8]
top20_ret = top20.groupby('trade_date')['pct_chg'].mean()

# 合并
combined = pd.DataFrame({'trade_date': top20_ret.index, 'top20_bull_ret': top20_ret.values})
combined = combined.merge(daily_ret[['trade_date','ew_ret','CSI300_bull_ma200']], on='trade_date', how='left')
combined['strategy_ret'] = combined.apply(
    lambda r: r['top20_bull_ret'] if r['CSI300_bull_ma200'] else 0.0, axis=1
)
combined = combined.dropna()

n_years = (combined['trade_date'].max() - combined['trade_date'].min()).days / 365.25
cum_strategy = (1 + combined['strategy_ret']/100).cumprod()
cum_bench = (1 + combined['ew_ret']/100).cumprod()

ann_strategy = (cum_strategy.iloc[-1] ** (1/n_years) - 1) * 100
ann_bench = (cum_bench.iloc[-1] ** (1/n_years) - 1) * 100

print(f"\n  择时(CSI300>MA200) + 动量前20%:")
print(f"  年化收益: {ann_strategy:.2f}%")
print(f"  基准年化: {ann_bench:.2f}%")
print(f"  超额: {ann_strategy - ann_bench:.2f}%")

# 分年度
print(f"\n  分年度:")
combined['year'] = combined['trade_date'].dt.year
for y in sorted(combined['year'].unique()):
    ysub = combined[combined['year'] == y]
    strat_ret = ysub['strategy_ret'].sum()
    bench_ret = ysub['ew_ret'].sum()
    print(f"    {y}: 择时+动量={strat_ret:.2f}%, 基准={bench_ret:.2f}%, 超额={strat_ret-bench_ret:.2f}%")

# ============================================================
# 保存
# ============================================================
print("\n" + "=" * 70)
print("💾 保存结果")
print("=" * 70)

output = {
    'timing_strategies': results,
    'best': best_name,
    'momentum_timing': {
        'ann_strategy': round(ann_strategy, 2),
        'ann_bench': round(ann_bench, 2),
    }
}
with open(RESULTS_DIR + 'summary.json', 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"  最佳择时: {best_name}")
print(f"  年化收益: {best_r['ann_timing']}%")
print(f"  vs基准: {best_r['ann_bench']}%")

print("\n✅ V1 研究完成!")
