#!/usr/bin/env python3
"""
假设2: 能源价格冲击对股指期货的非对称影响

测试: 当布油>$100或原油出现大幅上涨时，股指期货(USTEC/US500)是否表现出不
对称下行风险？能否作为风险预警信号用于仓位管理？

数据源: MT5 D1历史数据
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import json
import sys

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

def main():
    if not mt5.initialize(path=MT5_PATH):
        print(f"MT5 init failed: {mt5.last_error()}")
        sys.exit(1)
    
    print("=== 假设2: 能源价格冲击对股指期货的非对称影响 ===\n")
    
    symbols_mt5 = {
        "XAUUSD": "XAUUSDm",
        "USOIL": "USOILm",
        "UKOIL": "UKOILm",
        "USTEC": "USTECm",
        "US500": "US500m",
        "US30": "US30m",
    }
    
    all_data = {}
    for name, sym in symbols_mt5.items():
        mt5.symbol_select(sym, True)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 3000)
        if rates is None or len(rates) == 0:
            print(f"警告: 无法获取 {name} 数据")
            continue
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df['return'] = df['close'].pct_change()
        df['log_return'] = np.log(df['close'] / df['close'].shift(1))
        df['range_pct'] = (df['high'] - df['low']) / df['close']
        
        # 滚动波动率 (20日)
        df['vol_20'] = df['return'].rolling(20).std() * np.sqrt(252)
        
        all_data[name] = df
        print(f"{name}: {len(df)} 根D1K线, 范围 {df.index[0].strftime('%Y-%m-%d')} 到 {df.index[-1].strftime('%Y-%m-%d')}")
    
    # 对齐所有品种
    keys_to_merge = [k for k in ['USOIL', 'UKOIL', 'USTEC', 'US500', 'US30'] if k in all_data]
    if len(keys_to_merge) < 4:
        print("数据不足")
        mt5.shutdown()
        sys.exit(1)
    
    merge_dict = {}
    for k in keys_to_merge:
        merge_dict[f'{k.lower()}_return'] = all_data[k]['return']
        merge_dict[f'{k.lower()}_close'] = all_data[k]['close']
        merge_dict[f'{k.lower()}_vol'] = all_data[k]['vol_20']
    
    # 加入黄金
    if 'XAUUSD' in all_data:
        merge_dict['gold_return'] = all_data['XAUUSD']['return']
        merge_dict['gold_close'] = all_data['XAUUSD']['close']
    
    merged = pd.DataFrame(merge_dict).dropna()
    print(f"\n对齐后样本量: {len(merged)} 个交易日")
    print(f"时间范围: {merged.index[0].strftime('%Y-%m-%d')} 到 {merged.index[-1].strftime('%Y-%m-%d')}")
    
    # ============ 分析1: 高油价环境对股指期货的影响 ============
    print("\n--- 高油价环境 ($100+) 对股指期货的影响 ---")
    
    # 找到布油 > $100 的时期
    if 'ukoil_close' in merged.columns:
        high_oil_mask = merged['ukoil_close'] > 100
        normal_oil_mask = merged['ukoil_close'] <= 100
        
        n_high = high_oil_mask.sum()
        n_normal = normal_oil_mask.sum()
        
        print(f"布油 > $100: {n_high} 天")
        print(f"布油 <= $100: {n_normal} 天")
        
        for idx in ['ustec', 'us500', 'us30']:
            col = f'{idx}_return'
            if col not in merged.columns:
                continue
            high_mean = merged.loc[high_oil_mask, col].mean()
            normal_mean = merged.loc[normal_oil_mask, col].mean()
            high_std = merged.loc[high_oil_mask, col].std()
            normal_std = merged.loc[normal_oil_mask, col].std()
            
            # t检验 (手动实现)
            high_vals = merged.loc[high_oil_mask, col].dropna()
            normal_vals = merged.loc[normal_oil_mask, col].dropna()
            if len(high_vals) > 5 and len(normal_vals) > 5:
                n1, n2 = len(high_vals), len(normal_vals)
                m1, m2 = high_vals.mean(), normal_vals.mean()
                v1, v2 = high_vals.var(), normal_vals.var()
                se = np.sqrt(v1/n1 + v2/n2)
                t_stat = (m1 - m2) / se if se > 0 else 0
                # Welch's t-test p-value 近似
                df = (v1/n1 + v2/n2)**2 / ((v1/n1)**2/(n1-1) + (v2/n2)**2/(n2-1))
                # 简化: 如果 |t| > 2.58 则 p < 0.01, |t| > 1.96 则 p < 0.05
                if abs(t_stat) > 2.58:
                    p_value = 0.005
                elif abs(t_stat) > 1.96:
                    p_value = 0.025
                else:
                    p_value = 0.10
            else:
                t_stat, p_value = 0, 1
            
            print(f"\n  {idx.upper()}:")
            print(f"    高油价期日均收益: {high_mean*100:.4f}% (std={high_std*100:.4f}%)")
            print(f"    正常期日均收益: {normal_mean*100:.4f}% (std={normal_std*100:.4f}%)")
            print(f"    t-stat={t_stat:.3f}, p-value={p_value:.4f}")
            print(f"    高油价期年化: {high_mean*252*100:.2f}%, 正常期: {normal_mean*252*100:.2f}%")
    
    # ============ 分析2: 原油大幅上涨事件后的股指期货表现 ============
    print("\n--- 原油大幅上涨事件后的股指期货表现 ---")
    
    # 原油上涨超过 20日波动率的1.5倍
    oil_return = merged['usoil_return']
    oil_vol_20 = merged['usoil_vol'] / np.sqrt(252)
    big_oil_up = oil_return > oil_vol_20 * 1.5
    
    n_events = big_oil_up.sum()
    print(f"原油大幅上涨事件 (日收益 > 1.5x 20日波动率): {n_events} 次")
    
    if n_events > 5:
        event_dates = merged.index[big_oil_up]
        
        for idx in ['ustec', 'us500', 'us30']:
            col = f'{idx}_return'
            if col not in merged.columns:
                continue
            
            print(f"\n  {idx.upper()} 在原油大涨后的表现:")
            for horizon in [1, 2, 3, 5, 10]:
                fwd_rets = []
                for date in event_dates:
                    try:
                        idx_pos = merged.index.get_loc(date)
                        if idx_pos + horizon < len(merged):
                            fwd_ret = merged.iloc[idx_pos + horizon][col]
                            fwd_rets.append(fwd_ret)
                    except:
                        pass
                
                if len(fwd_rets) > 2:
                    arr = np.array(fwd_rets)
                    avg = arr.mean()
                    pos_pct = (arr > 0).mean()
                    t_val = avg / (arr.std() / np.sqrt(len(arr))) if arr.std() > 0 else 0
                    print(f"    {horizon}日后: 平均收益={avg*100:.4f}%, 上涨概率={pos_pct*100:.1f}%, t={t_val:.2f}, 样本={len(fwd_rets)}")
    
    # ============ 分析3: 原油趋势与股指期货的相关性 (滚动) ============
    print("\n--- 滚动相关性 (60日窗口): 原油 vs 股指期货 ---")
    
    for idx in ['ustec', 'us500']:
        col = f'{idx}_return'
        if col not in merged.columns:
            continue
        
        rolling_corr = merged['usoil_return'].rolling(60).corr(merged[col])
        
        print(f"\n  {idx.upper()} vs WTI原油 滚动相关性:")
        
        # 找到相关性最高和最低的时期
        valid = rolling_corr.dropna()
        if len(valid) > 0:
            max_corr_idx = valid.idxmax()
            min_corr_idx = valid.idxmin()
            print(f"    最高: {valid.max():.4f} ({max_corr_idx.strftime('%Y-%m-%d')})")
            print(f"    最低: {valid.min():.4f} ({min_corr_idx.strftime('%Y-%m-%d')})")
            print(f"    当前: {rolling_corr.iloc[-1]:.4f}")
            print(f"    均值: {valid.mean():.4f}")
            
            # 负相关的时期 (原油上涨对股指不利)
            neg_corr_periods = valid[valid < -0.3]
            if len(neg_corr_periods) > 0:
                print(f"    强负相关 (<-0.3) 天数: {len(neg_corr_periods)}")
                for d in neg_corr_periods.index[:5]:
                    print(f"      {d.strftime('%Y-%m-%d')}: {neg_corr_periods[d]:.4f}")
    
    # ============ 分析4: 风险预警信号回测 ============
    print("\n--- 风险预警信号回测 ---")
    print("策略: 当原油20日收益率 > 15% 时减仓股指期货至50%")
    
    for idx in ['ustec', 'us500']:
        col = f'{idx}_return'
        if col not in merged.columns:
            continue
        
        oil_20d = merged['usoil_return'].rolling(20).sum()
        warning = oil_20d > 0.15  # 20日涨幅超过15%
        
        # 基准: 全仓持有
        bench_cum = (1 + merged[col]).cumprod()
        bench_total = bench_cum.iloc[-1] - 1
        bench_dd = ((bench_cum - bench_cum.cummax()) / bench_cum.cummax()).min()
        
        # 信号策略: 预警期半仓
        position = pd.Series(1.0, index=merged.index)
        position[warning] = 0.5
        
        strat_ret = position * merged[col]
        strat_cum = (1 + strat_ret).cumprod()
        strat_total = strat_cum.iloc[-1] - 1
        strat_dd = ((strat_cum - strat_cum.cummax()) / strat_cum.cummax()).min()
        
        # 夏普
        bench_sharpe = merged[col].mean() / merged[col].std() * np.sqrt(252)
        strat_sharpe = strat_ret.mean() / strat_ret.std() * np.sqrt(252)
        
        warning_days = warning.sum()
        print(f"\n  {idx.upper()}:")
        print(f"    预警天数: {warning_days}/{len(merged)} ({warning_days/len(merged)*100:.1f}%)")
        print(f"    基准收益: {bench_total*100:.2f}%, 策略收益: {strat_total*100:.2f}%")
        print(f"    基准最大回撤: {bench_dd*100:.2f}%, 策略最大回撤: {strat_dd*100:.2f}%")
        print(f"    基准夏普: {bench_sharpe:.3f}, 策略夏普: {strat_sharpe:.3f}")
    
    # ============ 分析5: 2026年美伊冲突期间的详细分析 ============
    print("\n--- 2026年美伊冲突期间详细分析 ---")
    
    conflict_2026 = merged[(merged.index >= '2026-04-01')]
    if len(conflict_2026) > 5:
        print(f"冲突期样本: {len(conflict_2026)} 天 ({conflict_2026.index[0].strftime('%Y-%m-%d')} 到 {conflict_2026.index[-1].strftime('%Y-%m-%d')})")
        
        for idx in ['ustec', 'us500', 'us30', 'gold']:
            col = f'{idx}_return' if idx != 'gold' else 'gold_return'
            if col not in conflict_2026.columns:
                continue
            avg = conflict_2026[col].mean()
            total = conflict_2026[col].sum()
            vol = conflict_2026[col].std() * np.sqrt(252)
            print(f"  {idx.upper()}: 日均收益={avg*100:.4f}%, 累计={total*100:.2f}%, 年化波动率={vol*100:.2f}%")
        
        # 相关性
        if 'usoil_return' in conflict_2026.columns:
            for idx in ['ustec', 'us500', 'gold']:
                col = f'{idx}_return' if idx != 'gold' else 'gold_return'
                if col in conflict_2026.columns:
                    c = conflict_2026['usoil_return'].corr(conflict_2026[col])
                    print(f"  原油-{idx.upper()}相关: {c:.4f}")
    
    # ============ 分析6: 原油波动率对股指期货波动率的影响 ============
    print("\n--- 原油波动率对股指期货波动率的影响 (Granger因果) ---")
    
    try:
        from statsmodels.tsa.stattools import grangercausalitytests
        
        # 使用对数收益率
        test_data = pd.DataFrame({
            'equity': merged['ustec_return'] if 'ustec_return' in merged.columns else merged['us500_return'],
            'oil': merged['usoil_return'],
        }).dropna()
        
        if len(test_data) > 50:
            print("\n  Granger因果检验: 原油波动率 → 股指期货波动率")
            for lag in [1, 3, 5]:
                try:
                    result = grangercausalitytests(test_data[['equity', 'oil']], maxlag=lag, verbose=False)
                    f_stat = result[lag][0]['ssr_ftest'][0]
                    p_val = result[lag][0]['ssr_ftest'][1]
                    print(f"    Lag={lag}: F={f_stat:.4f}, p-value={p_val:.4f} {'**' if p_val < 0.01 else '*' if p_val < 0.05 else ''}")
                except:
                    print(f"    Lag={lag}: 计算失败")
    except ImportError:
        print("  statsmodels 未安装，跳过Granger检验")
    
    # ============ 保存结果 ============
    results = {
        "sample_size": len(merged),
        "date_range": {
            "start": merged.index[0].strftime('%Y-%m-%d'),
            "end": merged.index[-1].strftime('%Y-%m-%d'),
        },
    }
    
    with open('h2_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n结果已保存到 h2_results.json")
    
    mt5.shutdown()
    print("MT5 连接已关闭")

if __name__ == "__main__":
    main()
