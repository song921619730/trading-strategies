#!/usr/bin/env python3
"""
补充测试: 剩余品种 (JP225m, HK50m, EURUSDm, GBPUSDm, AUDUSDm) 的GSR预测力
以及跨品种Regime表现分析
"""
import sys
sys.path.insert(0, 'C:/Users/gj/AppData/Local/Programs/Python/Python312')

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from scipy import stats
import json

if not mt5.initialize():
    print("MT5初始化失败")
    sys.exit(1)

SYMBOLS = ['XAUUSDm', 'XAGUSDm', 'EURUSDm', 'GBPUSDm', 'USDJPYm', 'AUDUSDm', 'USDCHFm',
           'USOILm', 'UKOILm', 'USTECm', 'US30m', 'US500m', 'JP225m', 'HK50m']

print("获取全部品种数据...")
data = {}
for sym in SYMBOLS:
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 5000)
    if rates is not None and len(rates) > 0:
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df['return'] = df['close'].pct_change() * 100
        data[sym] = df

mt5.shutdown()

# 共同交易日
all_dates = set(data[SYMBOLS[0]].index)
for sym in SYMBOLS[1:]:
    all_dates = all_dates & set(data[sym].index)
common_dates = sorted(list(all_dates))
print(f"共同交易日: {len(common_dates)} 天 ({common_dates[0].date()} ~ {common_dates[-1].date()})")

master = pd.DataFrame(index=common_dates)
for sym in SYMBOLS:
    master[f'{sym}_close'] = data[sym].reindex(common_dates)['close']
    master[f'{sym}_return'] = data[sym].reindex(common_dates)['return']

# Regime
master['USDCHFm_ma200'] = master['USDCHFm_close'].rolling(200).mean()
master['usd_bullish'] = master['USDCHFm_close'] > master['USDCHFm_ma200']
master['USTECm_vol20'] = master['USTECm_return'].rolling(20).std() * np.sqrt(252) * 100
master['high_vol'] = master['USTECm_vol20'] > master['USTECm_vol20'].rolling(252).quantile(0.8)
master['UKOIL_high'] = master['UKOILm_close'] > 80

master['hawkish_conflict'] = master['usd_bullish'] & master['high_vol'] & master['UKOIL_high']
master['pure_hawkish'] = master['usd_bullish'] & ~master['UKOIL_high']
master['normal_regime'] = ~(master['hawkish_conflict'] | master['pure_hawkish'])

# 金银比
master['GSR'] = master['XAUUSDm_close'] / master['XAGUSDm_close']
master['GSR_chg5'] = master['GSR'].pct_change(5) * 100
master['GSR_chg20'] = master['GSR'].pct_change(20) * 100
master['GSR_ma20'] = master['GSR'].rolling(20).mean()
master['GSR_zscore'] = (master['GSR'] - master['GSR_ma20']) / master['GSR'].rolling(20).std()

# ============================================================
# 补充品种1: Regime表现分析 (所有14品种)
# ============================================================
print("\n" + "=" * 60)
print("所有14品种在三种Regime下的表现")
print("=" * 60)

all_symbols_full = SYMBOLS
regime_results = {}

for sym in all_symbols_full:
    ret_col = f'{sym}_return'
    sym_results = {}
    for regime_name, regime_mask in [
        ('hawkish_conflict', master['hawkish_conflict']),
        ('pure_hawkish', master['pure_hawkish']),
        ('normal', master['normal_regime'])
    ]:
        regime_returns = master.loc[regime_mask, ret_col].dropna()
        if len(regime_returns) > 10:
            sym_results[regime_name] = {
                'n': int(len(regime_returns)),
                'mean_daily': float(regime_returns.mean()),
                'annualized': float(regime_returns.mean() * 252),
                'std_daily': float(regime_returns.std()),
                'annualized_vol': float(regime_returns.std() * np.sqrt(252)),
                'sharpe': float((regime_returns.mean() / regime_returns.std()) * np.sqrt(252)) if regime_returns.std() > 0 else 0,
                'win_rate': float((regime_returns > 0).sum() / len(regime_returns)),
            }
        else:
            sym_results[regime_name] = None
    regime_results[sym] = sym_results

print(f"\n{'品种':<12} | {'Regime':<18} | {'天数':>5} | {'年化%':>8} | {'波动%':>8} | {'夏普':>6} | {'胜率%':>6}")
print("-" * 80)
for sym in all_symbols_full:
    for regime_name in ['hawkish_conflict', 'pure_hawkish', 'normal']:
        r = regime_results[sym][regime_name]
        if r:
            print(f"{sym:<12} | {regime_name:<18} | {r['n']:>5} | {r['annualized']:>8.2f} | {r['annualized_vol']:>8.2f} | {r['sharpe']:>6.2f} | {r['win_rate']*100:>6.1f}")

# ============================================================
# 补充品种2: GSR对JP225/HK50/EUR/GBP/AUD的预测力
# ============================================================
print("\n" + "=" * 60)
print("GSR对补充品种的预测力")
print("=" * 60)

extra_symbols = ['JP225m', 'HK50m', 'EURUSDm', 'GBPUSDm', 'AUDUSDm']
predictor_vars = ['GSR_chg5', 'GSR_chg20', 'GSR_zscore']
forward_periods = [1, 5, 20]

extra_results = {}
print(f"\n{'预测因子':<15} | {'目标品种':<12} | {'前瞻':>5} | {'相关系数':>8} | {'p-value':>8} | 显著")
print("-" * 70)

for pred in predictor_vars:
    for target in extra_symbols:
        for fwd in forward_periods:
            fwd_col = f'{target}_fwd{fwd}'
            master[fwd_col] = master[f'{target}_return'].shift(-fwd).rolling(fwd).sum()
            
            valid = master[[pred, fwd_col]].dropna()
            if len(valid) < 100:
                continue
            
            corr, p_val = stats.pearsonr(valid[pred], valid[fwd_col])
            t_stat_val = corr * np.sqrt((len(valid) - 2) / (1 - corr**2 + 1e-10))
            
            key = f"{pred}_{target}_{fwd}d"
            extra_results[key] = {'corr': corr, 'p_value': p_val, 't_stat': float(t_stat_val), 'n': len(valid)}
            
            sig = '✅' if p_val < 0.05 else '  '
            print(f"{pred:<15} | {target:<12} | {fwd}d{'fwd':<2} | {corr:>8.4f} | {p_val:>8.4f} | {sig}")

# ============================================================
# 补充品种3: 简单GSR策略对补充品种的回测
# ============================================================
print("\n" + "=" * 60)
print("GSR策略对补充品种的回测")
print("=" * 60)

gsr_z = master['GSR_zscore'].dropna()

for sym in extra_symbols:
    # 外汇和亚太股指: 类似风险资产逻辑
    signal = (gsr_z < -1.0).astype(int) - (gsr_z > 1.0).astype(int)
    
    aligned = pd.DataFrame({
        'signal': signal,
        'return': master[f'{sym}_return']
    }).dropna()
    
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
    
    cummax = cum_strat.cummax()
    dd = (cum_strat - cummax) / cummax
    max_dd = dd.min()
    
    trade_days = (aligned['signal'].shift(1).abs() > 0).sum()
    
    print(f"\n{sym}:")
    print(f"  策略总收益: {total_strat*100:.2f}% | 基准: {total_bh*100:.2f}%")
    print(f"  策略年化:   {ann_strat*100:.2f}% | 基准: {ann_bh*100:.2f}%")
    print(f"  策略夏普:   {sharpe_strat:.2f} | 基准: {sharpe_bh:.2f}")
    print(f"  最大回撤:   {max_dd*100:.2f}%")
    print(f"  交易天数:   {trade_days}/{len(aligned)}")

# ============================================================
# 综合分析: GSR对USTECm最强预测的详细分解
# ============================================================
print("\n" + "=" * 60)
print("GSR对USTECm预测力的分年度分析")
print("=" * 60)

master['year'] = master.index.year
for year in sorted(master['year'].dropna().unique()):
    year_data = master[master['year'] == year].dropna(subset=['GSR_chg20'])
    if len(year_data) < 100:
        continue
    
    fwd_col = 'USTECm_fwd20'
    valid = year_data[['GSR_chg20', fwd_col]].dropna()
    if len(valid) < 30:
        continue
    
    corr, p_val = stats.pearsonr(valid['GSR_chg20'], valid[fwd_col])
    print(f"  {year}: r={corr:.4f}, p={p_val:.4f}, n={len(valid)}")

# 分Regime分析GSR-USTEC关系
print("\n按Regime分解GSR_chg20 vs USTECm_20d前瞻:")
for regime_name, regime_mask in [
    ('鹰派+冲突', master['hawkish_conflict']),
    ('纯鹰派', master['pure_hawkish']),
    ('正常', master['normal_regime'])
]:
    valid = master.loc[regime_mask, ['GSR_chg20', 'USTECm_fwd20']].dropna()
    if len(valid) < 30:
        print(f"  {regime_name}: 样本不足 (n={len(valid)})")
        continue
    corr, p_val = stats.pearsonr(valid['GSR_chg20'], valid['USTECm_fwd20'])
    print(f"  {regime_name}: r={corr:.4f}, p={p_val:.4f}, n={len(valid)}")

# ============================================================
# 保存补充结果
# ============================================================
output = {
    'all_symbols_regime': regime_results,
    'extra_gsr_predictions': extra_results,
}

with open('research_results_supplement.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2, default=str)

print("\n✅ 补充分析完成! research_results_supplement.json 已保存")
