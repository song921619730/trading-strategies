#!/usr/bin/env python3
"""
假设1: 原油-黄金跨资产领先-滞后关系 (Oil-Gold Lead-Lag during Geopolitical Crisis)

测试: 在地缘政治冲突期间，原油价格变动是否领先黄金价格变动？
如果是，领先多少天？这个信号能否用于改进交易策略？

数据源: MT5 D1历史数据
Python: Windows Python 3.12
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import json
import sys

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

def main():
    if not mt5.initialize(path=MT5_PATH):
        print(f"MT5 init failed: {mt5.last_error()}")
        sys.exit(1)
    
    print("=== 假设1: 原油-黄金跨资产领先-滞后关系 ===\n")
    
    # 获取最大可用历史数据
    symbols_mt5 = {"XAUUSD": "XAUUSDm", "USOIL": "USOILm", "UKOIL": "UKOILm"}
    
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
        df['high_low_pct'] = (df['high'] - df['low']) / df['close']
        
        all_data[name] = df
        print(f"{name}: {len(df)} 根D1K线, 范围 {df.index[0].strftime('%Y-%m-%d')} 到 {df.index[-1].strftime('%Y-%m-%d')}")
    
    if len(all_data) < 2:
        print("数据不足，退出")
        mt5.shutdown()
        sys.exit(1)
    
    # 对齐数据
    gold = all_data['XAUUSD']
    oil_wti = all_data['USOIL']
    oil_brent = all_data['UKOIL']
    
    # 合并
    merged = pd.DataFrame({
        'gold_return': gold['return'],
        'oil_wti_return': oil_wti['return'],
        'oil_brent_return': oil_brent['return'],
        'gold_close': gold['close'],
        'oil_wti_close': oil_wti['close'],
        'oil_brent_close': oil_brent['close'],
        'gold_hl': gold['high_low_pct'],
        'oil_wti_hl': oil_wti['high_low_pct'],
    }).dropna()
    
    print(f"\n对齐后样本量: {len(merged)} 个交易日")
    print(f"时间范围: {merged.index[0].strftime('%Y-%m-%d')} 到 {merged.index[-1].strftime('%Y-%m-%d')}")
    
    # ============ 分析1: 全样本相关性 ============
    print("\n--- 全样本相关性 ---")
    corr_gold_oil_wti = merged['gold_return'].corr(merged['oil_wti_return'])
    corr_gold_oil_brent = merged['gold_return'].corr(merged['oil_brent_return'])
    print(f"黄金 vs WTI原油 (同期): {corr_gold_oil_wti:.4f}")
    print(f"黄金 vs 布油 (同期): {corr_gold_oil_brent:.4f}")
    
    # ============ 分析2: 领先-滞后分析 (交叉相关) ============
    print("\n--- 领先-滞后交叉相关分析 ---")
    max_lag = 20
    lags = range(-max_lag, max_lag + 1)
    
    ccf_wti = []
    ccf_brent = []
    for lag in lags:
        # 正lag = 原油领先黄金 (oil领先lag天)
        corr = merged['gold_return'].corr(merged['oil_wti_return'].shift(lag))
        ccf_wti.append(corr)
        corr_b = merged['gold_return'].corr(merged['oil_brent_return'].shift(lag))
        ccf_brent.append(corr_b)
    
    best_lag_wti = lags[np.argmax(np.abs(ccf_wti))]
    best_corr_wti = max(ccf_wti, key=abs)
    best_lag_brent = lags[np.argmax(np.abs(ccf_brent))]
    best_corr_brent = max(ccf_brent, key=abs)
    
    print(f"WTI原油领先黄金的最佳lag: {best_lag_wti}天 (相关系数: {best_corr_wti:.4f})")
    print(f"布油领先黄金的最佳lag: {best_lag_brent}天 (相关系数: {best_corr_brent:.4f})")
    
    # 输出完整CCF表格
    print("\n完整交叉相关表 (正值=原油领先):")
    print(f"{'Lag':>5} | {'WTI-Gold':>10} | {'Brent-Gold':>12}")
    print("-" * 35)
    for lag, cw, cb in zip(lags, ccf_wti, ccf_brent):
        marker = " <-- max" if lag == best_lag_wti else ""
        print(f"{lag:5d} | {cw:10.4f} | {cb:12.4f}{marker}")
    
    # ============ 分析3: 地缘政治冲突期 vs 正常期 ============
    print("\n--- 地缘政治冲突期 vs 正常期 ---")
    
    # 定义已知的地缘政治事件窗口 (基于历史事实)
    # 2022-02: 俄乌战争爆发
    # 2023-10: 巴以冲突
    # 2024-04: 伊朗-以色列直接冲突
    # 2024-10: 中东局势升级
    # 2025-04/2026-05: 美伊冲突 (当前简报提到)
    
    crisis_periods = [
        ("2022-02-20", "2022-04-30", "俄乌战争爆发"),
        ("2023-10-07", "2023-12-31", "巴以冲突"),
        ("2024-04-01", "2024-05-31", "伊朗-以色列直接冲突"),
        ("2024-10-01", "2024-12-31", "中东局势升级"),
        ("2025-01-01", "2025-03-31", "美伊紧张期1"),
        ("2025-06-01", "2025-08-31", "美伊紧张期2"),
        ("2026-04-01", "2026-05-09", "美伊冲突/霍尔木兹海峡"),
    ]
    
    crisis_mask = pd.Series(False, index=merged.index)
    for start, end, label in crisis_periods:
        mask = (merged.index >= start) & (merged.index <= end)
        crisis_mask = crisis_mask | mask
        if mask.any():
            n_days = mask.sum()
            print(f"  事件: {label} ({start} 到 {end}): {n_days} 个交易日")
    
    crisis_data = merged[crisis_mask]
    normal_data = merged[~crisis_mask]
    
    print(f"\n冲突期样本: {len(crisis_data)} 天")
    print(f"正常期样本: {len(normal_data)} 天")
    
    if len(crisis_data) > 10:
        corr_crisis = crisis_data['gold_return'].corr(crisis_data['oil_wti_return'])
        corr_normal = normal_data['gold_return'].corr(normal_data['oil_wti_return'])
        print(f"\n冲突期 黄金-WTI相关: {corr_crisis:.4f}")
        print(f"正常期 黄金-WTI相关: {corr_normal:.4f}")
        print(f"差异 (冲突-正常): {corr_crisis - corr_normal:.4f}")
        
        # 冲突期领先滞后
        ccf_crisis = []
        for lag in range(-10, 11):
            c = crisis_data['gold_return'].corr(crisis_data['oil_wti_return'].shift(lag))
            ccf_crisis.append(c)
        best_crisis_lag = range(-10, 11)[np.argmax(np.abs(ccf_crisis))]
        print(f"冲突期最佳lead-lag: WTI领先{best_crisis_lag}天 (r={max(ccf_crisis, key=abs):.4f})")
    
    if len(normal_data) > 10:
        ccf_normal = []
        for lag in range(-10, 11):
            c = normal_data['gold_return'].corr(normal_data['oil_wti_return'].shift(lag))
            ccf_normal.append(c)
        best_normal_lag = range(-10, 11)[np.argmax(np.abs(ccf_normal))]
        print(f"正常期最佳lead-lag: WTI领先{best_normal_lag}天 (r={max(ccf_normal, key=abs):.4f})")
    
    # ============ 分析4: 原油大幅波动日后黄金的表现 ============
    print("\n--- 原油大幅波动日后黄金的表现 ---")
    
    # 定义"大幅波动" = 原油日收益率超过 2倍ATR
    oil_atr_20 = merged['oil_wti_return'].rolling(20).std() * 2
    big_oil_moves = merged['oil_wti_return'].abs() > oil_atr_20
    
    if big_oil_moves.sum() > 5:
        big_moves = merged[big_oil_moves].copy()
        print(f"WTI原油大幅波动日: {big_oil_moves.sum()} 天")
        
        for horizon in [1, 2, 3, 5]:
            fwd_return = big_moves['gold_return'].shift(-horizon)
            avg_fwd = fwd_return.mean()
            positive_pct = (fwd_return > 0).mean()
            t_stat = avg_fwd / (fwd_return.std() / np.sqrt(fwd_return.dropna().shape[0])) if fwd_return.dropna().shape[0] > 1 else 0
            print(f"  原油大涨/大跌后 {horizon}天: 黄金平均收益={avg_fwd*100:.4f}%, 上涨概率={positive_pct*100:.1f}%, t-stat={t_stat:.2f}")
    
    # ============ 分析5: 基于原油动量的黄金交易信号回测 ============
    print("\n--- 基于原油动量的黄金交易信号回测 ---")
    
    # 信号: 当原油N日收益率为正时做多黄金，为负时做空黄金
    for lookback in [3, 5, 10, 20]:
        oil_momentum = merged['oil_wti_return'].rolling(lookback).sum()
        signal = np.sign(oil_momentum.shift(1))  # 前一天信号
        
        strategy_return = signal * merged['gold_return']
        strategy_return = strategy_return.dropna()
        
        cumulative = (1 + strategy_return).cumprod()
        total_return = cumulative.iloc[-1] - 1
        
        # 最大回撤
        rolling_max = cumulative.cummax()
        drawdown = (cumulative - rolling_max) / rolling_max
        max_dd = drawdown.min()
        
        # 夏普比率 (年化)
        sharpe = strategy_return.mean() / strategy_return.std() * np.sqrt(252) if strategy_return.std() > 0 else 0
        
        # 基准 (买入持有黄金)
        gold_cum = (1 + merged['gold_return'].dropna()).cumprod()
        gold_total = gold_cum.iloc[-1] - 1
        gold_sharpe = merged['gold_return'].mean() / merged['gold_return'].std() * np.sqrt(252)
        
        # 交易天数占比
        long_pct = (signal == 1).mean()
        short_pct = (signal == -1).mean()
        flat_pct = (signal == 0).mean()
        
        print(f"\n  原油{lookback}日动量 → 黄金信号:")
        print(f"    总收益: {total_return*100:.2f}% (基准: {gold_total*100:.2f}%)")
        print(f"    夏普: {sharpe:.3f} (基准: {gold_sharpe:.3f})")
        print(f"    最大回撤: {max_dd*100:.2f}%")
        print(f"    多头占比: {long_pct*100:.1f}%, 空头: {short_pct*100:.1f}%, 空仓: {flat_pct*100:.1f}%")
        print(f"    样本量: {len(strategy_return)} 天")
    
    # ============ 分析6: 分阶段详细统计 ============
    print("\n--- 分阶段统计 (年度) ---")
    merged['year'] = merged.index.year
    for year in sorted(merged['year'].unique()):
        year_data = merged[merged['year'] == year]
        corr = year_data['gold_return'].corr(year_data['oil_wti_return'])
        print(f"  {year}: 样本={len(year_data)}天, 黄金-WTI相关={corr:.4f}, "
              f"黄金收益={year_data['gold_return'].sum()*100:.2f}%, "
              f"WTI收益={year_data['oil_wti_return'].sum()*100:.2f}%")
    
    # ============ 保存结果 ============
    results = {
        "full_sample_corr_wti": round(corr_gold_oil_wti, 4),
        "full_sample_corr_brent": round(corr_gold_oil_brent, 4),
        "best_lag_wti": int(best_lag_wti),
        "best_corr_wti": round(best_corr_wti, 4),
        "best_lag_brent": int(best_lag_brent),
        "best_corr_brent": round(best_corr_brent, 4),
        "sample_size": len(merged),
        "date_range": {
            "start": merged.index[0].strftime('%Y-%m-%d'),
            "end": merged.index[-1].strftime('%Y-%m-%d')
        },
        "ccf_wti": {str(lag): round(c, 4) for lag, c in zip(lags, ccf_wti)},
        "ccf_brent": {str(lag): round(c, 4) for lag, c in zip(lags, ccf_brent)},
    }
    
    if len(crisis_data) > 10:
        results["crisis_corr"] = round(corr_crisis, 4)
        results["normal_corr"] = round(corr_normal, 4)
    
    with open('h1_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n结果已保存到 h1_results.json")
    
    mt5.shutdown()
    print("MT5 连接已关闭")

if __name__ == "__main__":
    main()
