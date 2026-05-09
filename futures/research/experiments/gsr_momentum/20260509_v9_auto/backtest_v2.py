#!/usr/bin/env python3
"""
实验 v9 - 深度分析: GSR-能源交叉信号
"""

import sys
import warnings
warnings.filterwarnings('ignore')

mt5_path = 'C:/Users/gj/AppData/Local/Programs/Python/Python312'
sys.path.insert(0, mt5_path)

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime

# Add statsmodels
sys.path.insert(0, 'C:/Users/gj/AppData/Local/Programs/Python/Python312/Lib/site-packages')
import statsmodels.api as sm

if not mt5.initialize():
    print(f"MT5 初始化失败: {mt5.last_error()}")
    sys.exit(1)

def load_data(symbol, bars=5000):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, bars)
    df = pd.DataFrame(rates)
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('datetime', inplace=True)
    return df[['open', 'high', 'low', 'close', 'tick_volume']]

# 加载核心数据
gold = load_data('XAUUSDm')
silver = load_data('XAGUSDm')
brent = load_data('UKOILm')
wti = load_data('USOILm')
ustec = load_data('USTECm')
us500 = load_data('US500m')

print("数据加载完成:")
for name, df in [('黄金', gold), ('白银', silver), ('布油', brent), 
                  ('WTI', wti), ('纳指', ustec), ('标普', us500)]:
    print(f"  {name}: {len(df)} 天 ({df.index[0].date()} ~ {df.index[-1].date()})")

# ============ 构建统一数据集 ============
merged = gold[['close']].rename(columns={'close': 'gold'})
merged = merged.join(silver[['close']].rename(columns={'close': 'silver'}), how='inner')
merged = merged.join(brent[['close']].rename(columns={'close': 'brent'}), how='inner')
merged = merged.join(wti[['close']].rename(columns={'close': 'wti'}), how='inner')
merged = merged.join(ustec[['close']].rename(columns={'close': 'ustec'}), how='inner')
merged = merged.join(us500[['close']].rename(columns={'close': 'us500'}), how='inner')
merged = merged.dropna()

print(f"\n合并后: {len(merged)} 交易日 ({merged.index[0].date()} ~ {merged.index[-1].date()})")

# ============ 计算因子 ============
merged['gold_ret'] = merged['gold'].pct_change()
merged['silver_ret'] = merged['silver'].pct_change()
merged['brent_ret'] = merged['brent'].pct_change()
merged['ustec_ret'] = merged['ustec'].pct_change()
merged['us500_ret'] = merged['us500'].pct_change()

merged['gsr'] = merged['gold'] / merged['silver']
merged['silver_relative'] = merged['silver_ret'] - merged['gold_ret']
merged['gsr_change'] = merged['gsr'].pct_change()
merged['gsr_ma5'] = merged['gsr'].rolling(5).mean()
merged['gsr_ma20'] = merged['gsr'].rolling(20).mean()
merged['gsr_mom_20'] = merged['gsr'].pct_change(20)
merged['gsr_mom_10'] = merged['gsr'].pct_change(10)
merged['gsr_mom_5'] = merged['gsr'].pct_change(5)

merged['brent_ret_20d'] = (merged['brent'] / merged['brent'].shift(20) - 1) * 100
merged['brent_ma20'] = merged['brent'].rolling(20).mean()
merged['brent_ma60'] = merged['brent'].rolling(60).mean()

merged['energy_crisis'] = (merged['brent_ret_20d'] > 15).astype(int)

merged['oil_regime'] = 'normal'
merged.loc[merged['brent'] > 90, 'oil_regime'] = 'high'
merged.loc[merged['brent'] < 70, 'oil_regime'] = 'low'

merged['brent_vol_20'] = merged['brent_ret'].rolling(20).std() * np.sqrt(252)
merged['silver_vol_20'] = merged['silver_ret'].rolling(20).std() * np.sqrt(252)

merged = merged.dropna()
print(f"因子计算后: {len(merged)} 有效交易日")

# ============================================================
# 假设1: GSR动量信号在能源高油价期间的不对称性
# ============================================================
print("\n" + "=" * 80)
print("假设1: GSR动量信号在能源高油价期间的不对称性")
print("=" * 80)

# 1A. 不同regime下的GSR预测力
print("\n【1A】不同能源Regime下 GSR动量 → 白银相对收益 的预测力 (OLS回归)")
print("-" * 70)

for regime in ['low', 'normal', 'high']:
    sub = merged[merged['oil_regime'] == regime]
    if len(sub) < 30:
        continue
    
    y = sub['silver_relative']
    X = sm.add_constant(pd.DataFrame({
        'gsr_mom_20': sub['gsr_mom_20'],
        'brent_ret': sub['brent_ret'],
    }).dropna())
    y = y.loc[X.index]
    
    model = sm.OLS(y, X).fit()
    
    print(f"\n  {regime} Regime (n={len(sub)}):")
    print(f"  {'变量':<15} {'系数':>10} {'t值':>8} {'p值':>8}")
    print(f"  {'-'*50}")
    for var in model.params.index:
        coef = model.params[var]
        tval = model.tvalues[var]
        pval = model.pvalues[var]
        star = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
        print(f"  {var:<15} {coef:>10.4f} {tval:>8.2f} {pval:>8.4f} {star}")
    print(f"  R² = {model.rsquared:.4f}, Adj R² = {model.rsquared_adj:.4f}")

# 1B. GSR信号方向性检验
print("\n\n【1B】GSR信号方向性 — 按能源Regime × GSR方向 交叉分组")
print("-" * 70)

merged['gsr_bucket'] = pd.cut(merged['gsr_mom_20'], 
                               bins=[-np.inf, -0.05, -0.01, 0.0, 0.01, 0.05, np.inf],
                               labels=['极强收缩', '强收缩', '弱收缩', '弱扩张', '强扩张', '极强扩张'])

for regime in ['low', 'normal', 'high']:
    sub = merged[merged['oil_regime'] == regime]
    print(f"\n  {regime} Regime (n={len(sub)}):")
    for bucket in ['极强收缩', '强收缩', '弱收缩', '弱扩张', '强扩张', '极强扩张']:
        bucket_data = sub[sub['gsr_bucket'] == bucket]
        if len(bucket_data) > 10:
            mean_ret = bucket_data['silver_relative'].mean() * 100
            t_stat = mean_ret / (bucket_data['silver_relative'].std() / np.sqrt(len(bucket_data)))
            sig = "***" if abs(t_stat) > 3.29 else "**" if abs(t_stat) > 2.58 else "*" if abs(t_stat) > 1.96 else ""
            print(f"    {bucket} (n={len(bucket_data):>4}): 日均相对收益={mean_ret:+.3f}%  t={t_stat:+.2f} {sig}")

# 1C. 策略回测
print("\n\n【1C】策略回测对比")
print("-" * 70)

def calc_performance(returns, name="Strategy"):
    cum = (1 + returns).cumprod()
    total_ret = cum.iloc[-1] - 1
    n_years = len(returns) / 252
    ann_ret = (1 + total_ret) ** (1/n_years) - 1 if n_years > 0 else 0
    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    downside = returns[returns < 0]
    sortino = returns.mean() / downside.std() * np.sqrt(252) if len(downside) > 0 else 0
    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = dd.min()
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0
    win_rate = (returns > 0).sum() / len(returns) * 100
    avg_win = returns[returns > 0].mean() if (returns > 0).any() else 0
    avg_loss = abs(returns[returns < 0].mean()) if (returns < 0).any() else 1
    profit_factor = avg_win / avg_loss if avg_loss > 0 else 0
    
    return {
        '策略': name, '总收益': f"{total_ret*100:.1f}%", '年化': f"{ann_ret*100:.1f}%",
        '夏普': f"{sharpe:.2f}", '索提诺': f"{sortino:.2f}",
        '最大回撤': f"{max_dd*100:.1f}%", '卡尔马': f"{calmar:.2f}",
        '胜率': f"{win_rate:.1f}%", '盈亏比': f"{profit_factor:.2f}", '天数': len(returns),
    }

# 策略A: 纯GSR动量
merged['sig_gsr'] = np.where(merged['gsr_mom_20'] < 0, 1, -1)
merged['ret_A'] = merged['sig_gsr'].shift(1) * merged['silver_relative']

# 策略B: GSR + 能源危机过滤
merged['weight_B'] = np.where(merged['energy_crisis'] == 1, 0.5, 1.0)
merged['ret_B'] = merged['sig_gsr'].shift(1) * merged['silver_relative'] * merged['weight_B']

# 策略C: GSR + 动态油价权重
merged['weight_C'] = 1.0 - (merged['brent'].clip(40, 130) - 40) / 90 * 0.7
merged['ret_C'] = merged['sig_gsr'].shift(1) * merged['silver_relative'] * merged['weight_C']

# 策略D: GSR + 波动率调整
merged['weight_D'] = 1.0 - (merged['brent_vol_20'].clip(0.2, 1.0) - 0.2) / 0.8 * 0.5
merged['ret_D'] = merged['sig_gsr'].shift(1) * merged['silver_relative'] * merged['weight_D']

# 策略E: GSR阈值策略
merged['sig_E'] = 0
merged.loc[merged['gsr_mom_20'] < -0.02, 'sig_E'] = 1
merged.loc[merged['gsr_mom_20'] > 0.02, 'sig_E'] = -1
merged['ret_E'] = merged['sig_E'].shift(1) * merged['silver_relative']

# 策略F: GSR均线交叉
merged['gsr_cross'] = 0
merged.loc[merged['gsr_ma5'] > merged['gsr_ma20'], 'gsr_cross'] = -1
merged.loc[merged['gsr_ma5'] < merged['gsr_ma20'], 'gsr_cross'] = 1
merged['ret_F'] = merged['gsr_cross'].shift(1) * merged['silver_relative']

# 基准: 买入持有
merged['ret_buyhold'] = merged['silver_relative']

strategies = [
    ('ret_A', '纯GSR动量'), ('ret_B', 'GSR+危机过滤'),
    ('ret_C', 'GSR+动态油价权重'), ('ret_D', 'GSR+波动率调整'),
    ('ret_E', 'GSR阈值策略'), ('ret_F', 'GSR均线交叉'),
    ('ret_buyhold', '买入持有(相对)'),
]

results_table = []
for col, name in strategies:
    ret = merged[col].dropna()
    metrics = calc_performance(ret, name)
    results_table.append(metrics)

# 打印对比表
print(f"\n{'策略':<20} {'总收益':>10} {'年化':>10} {'夏普':>8} {'索提诺':>8} {'最大回撤':>10} {'卡尔马':>8} {'胜率':>8}")
print("-" * 100)
for m in results_table:
    print(f"{m['策略']:<20} {m['总收益']:>10} {m['年化']:>10} {m['夏普']:>8} {m['索提诺']:>8} {m['最大回撤']:>10} {m['卡尔马']:>8} {m['胜率']:>8}")

# ============================================================
# 假设2: 能源危机对跨资产相关性的影响
# ============================================================
print("\n\n" + "=" * 80)
print("假设2: 能源危机对跨资产相关性的影响")
print("=" * 80)

for asset, label in [('ustec_ret', '纳指'), ('us500_ret', '标普'), ('silver_ret', '白银')]:
    merged[f'corr_{asset}_brent'] = merged[asset].rolling(60).corr(merged['brent_ret'])

print("\n【2A】60日滚动相关性 — 危机期 vs 正常期")
print("-" * 70)

for asset, label in [('ustec_ret', '纳指-布油'), ('us500_ret', '标普-布油'), ('silver_ret', '白银-布油')]:
    col = f'corr_{asset}_brent'
    crisis_corr = merged.loc[merged['energy_crisis'] == 1, col].dropna()
    normal_corr = merged.loc[merged['energy_crisis'] == 0, col].dropna()
    
    if len(crisis_corr) > 5 and len(normal_corr) > 5:
        print(f"\n  {label}:")
        print(f"    危机期(n={len(crisis_corr)}): 均值={crisis_corr.mean():.3f}, 中位数={crisis_corr.median():.3f}, 最小值={crisis_corr.min():.3f}")
        print(f"    正常期(n={len(normal_corr)}): 均值={normal_corr.mean():.3f}, 中位数={normal_corr.median():.3f}, 最小值={normal_corr.min():.3f}")
        t_stat, t_p = stats.ttest_ind(crisis_corr, normal_corr)
        print(f"    差异: t={t_stat:.2f}, p={t_p:.4f}")

print("\n\n【2B】能源危机期间 vs 正常期的股指年化收益")
print("-" * 70)

for asset_ret, label in [('ustec_ret', '纳指'), ('us500_ret', '标普')]:
    crisis_ann = merged.loc[merged['energy_crisis'] == 1, asset_ret].mean() * 252 * 100
    normal_ann = merged.loc[merged['energy_crisis'] == 0, asset_ret].mean() * 252 * 100
    t_stat, t_p = stats.ttest_ind(
        merged.loc[merged['energy_crisis'] == 1, asset_ret].dropna(),
        merged.loc[merged['energy_crisis'] == 0, asset_ret].dropna()
    )
    print(f"  {label}: 危机期年化={crisis_ann:+.2f}%, 正常期年化={normal_ann:+.2f}%, t={t_stat:.2f}, p={t_p:.4f}")

# ============================================================
# 假设3: GSR信号最优参数搜索 + 样本外检验
# ============================================================
print("\n\n" + "=" * 80)
print("假设3: GSR信号最优参数搜索")
print("=" * 80)

best_sharpe = -999
best_params = {}

for window in [5, 10, 20, 30, 40, 60]:
    for threshold in [0.0, 0.005, 0.01, 0.02, 0.03, 0.05]:
        gsr_mom = merged['gsr'].pct_change(window)
        if threshold == 0:
            signal = np.where(gsr_mom < 0, 1, -1).astype(float)
        else:
            signal = np.zeros(len(merged))
            signal[gsr_mom < -threshold] = 1
            signal[gsr_mom > threshold] = -1
        
        ret = signal * merged['silver_relative']
        ret = ret.dropna()
        if len(ret) < 100:
            continue
        
        sharpe = ret.mean() / ret.std() * np.sqrt(252)
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_params = {'window': window, 'threshold': threshold, 'sharpe': sharpe, 'n_days': len(ret)}

print(f"\n最优参数: 窗口={best_params['window']}天, 阈值={best_params['threshold']}, 夏普={best_params['sharpe']:.3f}")

# 样本外检验
mid_point = len(merged) // 2
first_half = merged.iloc[:mid_point]
second_half = merged.iloc[mid_point:]

bw = best_params['window']
bt = best_params['threshold']

for period_name, period_data in [('样本内(前半)', first_half), ('样本外(后半)', second_half)]:
    gsr_mom = period_data['gsr'].pct_change(bw)
    if bt == 0:
        sig = np.where(gsr_mom < 0, 1, -1).astype(float)
    else:
        sig = np.zeros(len(period_data))
        sig[gsr_mom < -bt] = 1
        sig[gsr_mom > bt] = -1
    
    ret = sig * period_data['silver_relative']
    ret = ret.dropna()
    metrics = calc_performance(ret, period_name)
    print(f"\n  {period_name} ({period_data.index[0].date()} ~ {period_data.index[-1].date()}):")
    for k, v in metrics.items():
        if k != '策略':
            print(f"    {k}: {v}")

mt5.shutdown()

print("\n\n" + "=" * 80)
print("📊 实验完成")
print("=" * 80)
print(f"数据范围: {merged.index[0].date()} 至 {merged.index[-1].date()}")
print(f"有效交易: {len(merged)}")
print(f"覆盖品种: XAUUSDm, XAGUSDm, UKOILm, USOILm, USTECm, US500m")
