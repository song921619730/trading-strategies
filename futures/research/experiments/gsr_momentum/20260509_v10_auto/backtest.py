#!/usr/bin/env python3
"""
H1: 鹰派+冲突复合Regime下黄金避险属性增强
H2: 金银比(GSR)作为跨资产风险情绪指标对股指期货的预测力
"""
import sys
sys.path.insert(0, 'C:/Users/gj/AppData/Local/Programs/Python/Python312')

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime
import json

if not mt5.initialize():
    print("MT5初始化失败")
    sys.exit(1)

# ============================================================
# 1. 获取全部14品种D1数据
# ============================================================
SYMBOLS = [
    'XAUUSDm', 'XAGUSDm', 'EURUSDm', 'GBPUSDm', 'USDJPYm', 'AUDUSDm', 'USDCHFm',
    'USOILm', 'UKOILm', 'USTECm', 'US30m', 'US500m', 'JP225m', 'HK50m'
]

print("=" * 60)
print("正在获取全部14品种D1数据...")
print("=" * 60)

data = {}
for sym in SYMBOLS:
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 5000)
    if rates is not None and len(rates) > 0:
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df['return'] = df['close'].pct_change() * 100  # 百分比收益率
        df['log_return'] = np.log(df['close'] / df['close'].shift(1))
        data[sym] = df
        print(f"  {sym}: {len(df)} bars ({df.index.min().date()} ~ {df.index.max().date()})")
    else:
        print(f"  {sym}: 无数据!")

mt5.shutdown()

# ============================================================
# 2. 构建复合Regime识别
# ============================================================
print("\n" + "=" * 60)
print("构建复合Regime识别系统...")
print("=" * 60)

# 找到所有品种的交集日期
all_dates = set(data[SYMBOLS[0]].index)
for sym in SYMBOLS[1:]:
    all_dates = all_dates & set(data[sym].index)
common_dates = sorted(list(all_dates))
print(f"共同交易日: {len(common_dates)} 天 ({common_dates[0].date()} ~ {common_dates[-1].date()})")

# 构建统一DataFrame
master = pd.DataFrame(index=common_dates)
for sym in SYMBOLS:
    master[f'{sym}_close'] = data[sym].reindex(common_dates)['close']
    master[f'{sym}_return'] = data[sym].reindex(common_dates)['return']

# --- Regime 1: 鹰派期 (基于之前已知: 94天复合鹰派Regime) ---
# 用联邦基金利率变动 + 美元强势来近似鹰派
# USDCHF作为美元强度代理，上涨=美元强势=倾向鹰派
# 同时结合Fed利率路径变化：当USDCHFm处于长期上升趋势时定义为鹰派

# 计算USDCHF的200日均线关系来定义鹰派/鸽派
master['USDCHFm_ma200'] = master['USDCHFm_close'].rolling(200).mean()
master['usd_bullish'] = master['USDCHFm_close'] > master['USDCHFm_ma200']

# 用VIX代理(这里用USTEC的波动率作为风险情绪代理)
master['USTECm_vol20'] = master['USTECm_return'].rolling(20).std() * np.sqrt(252) * 100
master['high_vol'] = master['USTECm_vol20'] > master['USTECm_vol20'].rolling(252).quantile(0.8)

# 油价高位 (>80美元视为压力区，>100视为危机区)
master['UKOIL_high'] = master['UKOILm_close'] > 80
master['UKOIL_crisis'] = master['UKOILm_close'] > 100

# 综合Regime定义：
# "鹰派+冲突" = 美元强势 + 高波动 + 油价高位
master['hawkish_conflict'] = master['usd_bullish'] & master['high_vol'] & master['UKOIL_high']
# "纯鹰派" = 美元强势 + 油价不高
master['pure_hawkish'] = master['usd_bullish'] & ~master['UKOIL_high']
# "鸽派/正常" = 其他
master['normal_regime'] = ~(master['hawkish_conflict'] | master['pure_hawkish'])

# 统计Regime分布
hwc_count = master['hawkish_conflict'].sum()
ph_count = master['pure_hawkish'].sum()
normal_count = master['normal_regime'].sum()
print(f"\nRegime分布:")
print(f"  鹰派+冲突: {hwc_count} 天 ({hwc_count/len(master)*100:.1f}%)")
print(f"  纯鹰派:    {ph_count} 天 ({ph_count/len(master)*100:.1f}%)")
print(f"  正常/鸽派: {normal_count} 天 ({normal_count/len(master)*100:.1f}%)")

# 找出鹰派+冲突期的具体时间段
hwc_periods = master[master['hawkish_conflict']]
if len(hwc_periods) > 0:
    print(f"\n鹰派+冲突期起止: {hwc_periods.index.min().date()} ~ {hwc_periods.index.max().date()}")

# ============================================================
# 3. H1: 黄金在鹰派+冲突Regime下的避险属性
# ============================================================
print("\n" + "=" * 60)
print("H1测试: 黄金避险属性在不同Regime下的表现")
print("=" * 60)

# 定义测试品种
test_symbols_h1 = ['XAUUSDm', 'XAGUSDm', 'UKOILm', 'USOILm', 'USTECm', 'US500m', 'USDJPYm', 'USDCHFm']

h1_results = {}
for sym in test_symbols_h1:
    ret_col = f'{sym}_return'
    results = {}
    for regime_name, regime_mask in [
        ('hawkish_conflict', master['hawkish_conflict']),
        ('pure_hawkish', master['pure_hawkish']),
        ('normal', master['normal_regime'])
    ]:
        regime_returns = master.loc[regime_mask, ret_col].dropna()
        if len(regime_returns) > 10:
            results[regime_name] = {
                'n': len(regime_returns),
                'mean_daily': regime_returns.mean(),
                'annualized': regime_returns.mean() * 252,
                'std_daily': regime_returns.std(),
                'annualized_vol': regime_returns.std() * np.sqrt(252),
                'sharpe': (regime_returns.mean() / regime_returns.std()) * np.sqrt(252) if regime_returns.std() > 0 else 0,
                'win_rate': (regime_returns > 0).sum() / len(regime_returns),
                'max_single_day': regime_returns.min(),
                'best_single_day': regime_returns.max(),
            }
        else:
            results[regime_name] = None
    h1_results[sym] = results

# 打印H1结果
print(f"\n{'品种':<12} | {'Regime':<18} | {'天数':>5} | {'年化%':>8} | {'波动%':>8} | {'夏普':>6} | {'胜率%':>6}")
print("-" * 80)
for sym in test_symbols_h1:
    for regime_name in ['hawkish_conflict', 'pure_hawkish', 'normal']:
        r = h1_results[sym][regime_name]
        if r:
            print(f"{sym:<12} | {regime_name:<18} | {r['n']:>5} | {r['annualized']:>8.2f} | {r['annualized_vol']:>8.2f} | {r['sharpe']:>6.2f} | {r['win_rate']*100:>6.1f}")
        else:
            print(f"{sym:<12} | {regime_name:<18} | 数据不足")

# 统计检验: 黄金在鹰派+冲突期 vs 正常期的收益差异
gold_ret_hwc = master.loc[master['hawkish_conflict'], 'XAUUSDm_return'].dropna()
gold_ret_normal = master.loc[master['normal_regime'], 'XAUUSDm_return'].dropna()

if len(gold_ret_hwc) > 10 and len(gold_ret_normal) > 10:
    t_stat, p_value = stats.ttest_ind(gold_ret_hwc, gold_ret_normal, equal_var=False)
    print(f"\n📊 统计检验 (黄金): 鹰派+冲突 vs 正常期")
    print(f"  鹰派+冲突期日均收益: {gold_ret_hwc.mean():.4f}% (n={len(gold_ret_hwc)})")
    print(f"  正常期日均收益:      {gold_ret_normal.mean():.4f}% (n={len(gold_ret_normal)})")
    print(f"  t-statistic: {t_stat:.4f}, p-value: {p_value:.4f}")
    print(f"  显著性: {'✅ 显著 (p<0.05)' if p_value < 0.05 else '❌ 不显著 (p>=0.05)'}")

# ============================================================
# 4. H2: 金银比(GSR)对股指期货的预测力
# ============================================================
print("\n" + "=" * 60)
print("H2测试: 金银比(GSR)对跨资产的预测力")
print("=" * 60)

# 计算金银比
master['GSR'] = master['XAUUSDm_close'] / master['XAGUSDm_close']

# 计算GSR的变化率
master['GSR_chg5'] = master['GSR'].pct_change(5) * 100  # 5日变化率
master['GSR_chg20'] = master['GSR'].pct_change(20) * 100  # 20日变化率
master['GSR_ma20'] = master['GSR'].rolling(20).mean()
master['GSR_zscore'] = (master['GSR'] - master['GSR_ma20']) / master['GSR'].rolling(20).std()

# GSR上升 = 银弱金强 = 风险厌恶
# GSR下降 = 银强金弱 = 风险偏好

# 测试GSR对各类资产未来收益的预测力
forward_periods = [1, 5, 20]
predictor_vars = ['GSR_chg5', 'GSR_chg20', 'GSR_zscore']
target_symbols = ['XAUUSDm', 'XAGUSDm', 'USTECm', 'US500m', 'US30m', 'UKOILm', 'USDJPYm']

h2_results = {}
print(f"\n{'预测因子':<15} | {'目标品种':<12} | {'前瞻':>5} | {'相关系数':>8} | {'t-stat':>8} | {'p-value':>8}")
print("-" * 80)

for pred in predictor_vars:
    for target in target_symbols:
        for fwd in forward_periods:
            # 计算前瞻收益
            fwd_col = f'{target}_fwd{fwd}'
            master[fwd_col] = master[f'{target}_return'].shift(-fwd).rolling(fwd).sum()
            
            # 对齐数据
            valid = master[[pred, fwd_col]].dropna()
            if len(valid) < 100:
                continue
                
            corr, p_val = stats.pearsonr(valid[pred], valid[fwd_col])
            t_stat_val = corr * np.sqrt((len(valid) - 2) / (1 - corr**2 + 1e-10))
            
            key = f"{pred}_{target}_{fwd}d"
            h2_results[key] = {
                'corr': corr,
                'p_value': p_val,
                't_stat': t_stat_val,
                'n': len(valid),
            }
            
            sig = '✅' if p_val < 0.05 else '  '
            print(f"{pred:<15} | {target:<12} | {fwd}d{'fwd':<2} | {corr:>8.4f} | {t_stat_val:>8.2f} | {p_val:>8.4f} {sig}")

# ============================================================
# 5. 基于GSR的简单策略回测
# ============================================================
print("\n" + "=" * 60)
print("GSR动量策略回测 (全品种)")
print("=" * 60)

# 策略逻辑:
# GSR 20日Z-score > +1.5 (银弱金强, 风险厌恶) → 做多黄金, 做空股指/原油
# GSR 20日Z-score < -1.5 (银强金弱, 风险偏好) → 做多白银/股指
# 否则保持现金

strategy_symbols = ['XAUUSDm', 'XAGUSDm', 'USTECm', 'US500m', 'UKOILm', 'USDJPYm']
gsr_z = master['GSR_zscore'].dropna()

strategy_results = {}
for sym in strategy_symbols:
    # 多头信号: GSR低(风险偏好)时做多风险资产
    if sym in ['USTECm', 'US500m', 'UKOILm']:
        # 风险资产: GSR低时做多
        signal = (gsr_z < -1.0).astype(int) - (gsr_z > 1.0).astype(int)
    elif sym == 'XAUUSDm':
        # 黄金: GSR高时(避险)做多
        signal = (gsr_z > 1.0).astype(int) - (gsr_z < -1.0).astype(int)
    elif sym == 'XAGUSDm':
        # 白银: GSR低时(风险偏好)做多
        signal = (gsr_z < -1.0).astype(int) * 1
    else:
        # 默认
        signal = (gsr_z < -1.0).astype(int) - (gsr_z > 1.0).astype(int)
    
    # 对齐
    aligned = pd.DataFrame({
        'signal': signal,
        'return': master[f'{sym}_return']
    }).dropna()
    
    # 计算策略收益 (T日信号 → T+1日收益)
    aligned['strat_return'] = aligned['signal'].shift(1) * aligned['return']
    
    cum_strat = (1 + aligned['strat_return'] / 100).cumprod()
    cum_bh = (1 + aligned['return'] / 100).cumprod()
    
    total_strat = cum_strat.iloc[-1] - 1
    total_bh = cum_bh.iloc[-1] - 1
    
    ann_strat = total_strat * (252 / len(aligned))
    ann_bh = total_bh * (252 / len(aligned))
    
    vol_strat = aligned['strat_return'].std() * np.sqrt(252)
    vol_bh = aligned['return'].std() * np.sqrt(252)
    
    sharpe_strat = (aligned['strat_return'].mean() / aligned['strat_return'].std()) * np.sqrt(252) if aligned['strat_return'].std() > 0 else 0
    sharpe_bh = (aligned['return'].mean() / aligned['return'].std()) * np.sqrt(252) if aligned['return'].std() > 0 else 0
    
    # 最大回撤
    cummax = cum_strat.cummax()
    dd = (cum_strat - cummax) / cummax
    max_dd = dd.min()
    
    trade_days = (aligned['signal'].shift(1).abs() > 0).sum()
    
    strategy_results[sym] = {
        'total_strategy': total_strat * 100,
        'total_benchmark': total_bh * 100,
        'ann_strategy': ann_strat * 100,
        'ann_benchmark': ann_bh * 100,
        'vol_strategy': vol_strat,
        'vol_benchmark': vol_bh,
        'sharpe_strategy': sharpe_strat,
        'sharpe_benchmark': sharpe_bh,
        'max_dd': max_dd * 100,
        'trade_days': trade_days,
        'total_days': len(aligned),
    }
    
    print(f"\n{sym}:")
    print(f"  策略总收益: {strategy_results[sym]['total_strategy']:.2f}% | 基准: {strategy_results[sym]['total_benchmark']:.2f}%")
    print(f"  策略年化:   {strategy_results[sym]['ann_strategy']:.2f}% | 基准: {strategy_results[sym]['ann_benchmark']:.2f}%")
    print(f"  策略夏普:   {strategy_results[sym]['sharpe_strategy']:.2f} | 基准: {strategy_results[sym]['sharpe_benchmark']:.2f}")
    print(f"  策略波动:   {strategy_results[sym]['vol_strategy']:.2f}% | 基准: {strategy_results[sym]['vol_benchmark']:.2f}%")
    print(f"  最大回撤:   {strategy_results[sym]['max_dd']:.2f}%")
    print(f"  交易天数:   {trade_days}/{len(aligned)}")

# ============================================================
# 6. 综合分析: 当前Regime判定
# ============================================================
print("\n" + "=" * 60)
print("当前市场Regime判定 (截至最新交易日)")
print("=" * 60)

latest = master.iloc[-1]
latest_date = master.index[-1]
print(f"最新日期: {latest_date.date()}")
print(f"  黄金价格: ${latest['XAUUSDm_close']:.2f}")
print(f"  白银价格: ${latest['XAGUSDm_close']:.2f}")
print(f"  金银比:   {latest['GSR']:.2f}")
print(f"  GSR Z-Score: {latest['GSR_zscore']:.2f}")
print(f"  布油价格: ${latest['UKOILm_close']:.2f}")
print(f"  USDCHF:   {latest['USDCHFm_close']:.4f}")
print(f"  USTEC波动率(年化): {latest['USTECm_vol20']:.2f}%")

current_regime = []
if latest['usd_bullish']:
    current_regime.append("美元强势(鹰派)")
if latest['high_vol']:
    current_regime.append("高波动")
if latest['UKOIL_high']:
    current_regime.append("油价高位")
if latest['hawkish_conflict']:
    current_regime.append("→ 鹰派+冲突复合Regime")
    
print(f"\n当前Regime: {', '.join(current_regime) if current_regime else '正常/鸽派'}")

# 历史相似Regime
hwc_indices = master[master['hawkish_conflict']].index
if len(hwc_indices) > 0:
    print(f"历史鹰派+冲突期: {hwc_indices[0].date()} ~ {hwc_indices[-1].date()} (共{len(hwc_indices)}天)")

# ============================================================
# 7. 保存结果
# ============================================================
print("\n" + "=" * 60)
print("保存研究结果...")
print("=" * 60)

# 导出为JSON供report使用
output = {
    'h1': {
        'test': '黄金避险属性在鹰派+冲突Regime下的表现',
        'regime_distribution': {
            'hawkish_conflict': int(hwc_count),
            'pure_hawkish': int(ph_count),
            'normal': int(normal_count),
        },
        'gold_test': {
            'hwc_mean': float(gold_ret_hwc.mean()),
            'normal_mean': float(gold_ret_normal.mean()),
            't_stat': float(t_stat),
            'p_value': float(p_value),
            'significant': bool(p_value < 0.05),
            'hwc_n': int(len(gold_ret_hwc)),
            'normal_n': int(len(gold_ret_normal)),
        },
        'all_symbols': {sym: {k: (float(v) if v is not None else None) 
                              for k, v in regime_data.items()} 
                       if regime_data else None
                       for sym, regimes in h1_results.items()
                       for regime_name, regime_data in [(rn, regimes[rn]) 
                                                        for rn in ['hawkish_conflict', 'pure_hawkish', 'normal']]
                       if regime_data is not None},
    },
    'h2': {
        'test': 'GSR对跨资产的预测力',
        'significant_pairs': {k: v for k, v in h2_results.items() if v['p_value'] < 0.05},
    },
    'strategy': {sym: {k: float(v) for k, v in res.items()} 
                 for sym, res in strategy_results.items()},
    'data_range': {
        'start': str(common_dates[0].date()),
        'end': str(common_dates[-1].date()),
        'total_days': len(common_dates),
    },
    'current_regime': {
        'date': str(latest_date.date()),
        'regime': current_regime,
        'GSR': float(latest['GSR']),
        'GSR_zscore': float(latest['GSR_zscore']),
        'gold_price': float(latest['XAUUSDm_close']),
        'silver_price': float(latest['XAGUSDm_close']),
        'brent_price': float(latest['UKOILm_close']),
    }
}

with open('research_results.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2, default=str)

print("✅ research_results.json 已保存")
print("\n研究完成!")
