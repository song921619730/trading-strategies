#!/usr/bin/env python3
"""
补充分析: GSR动量策略回测 (含交易成本) + 分期间分析
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
from scipy import stats
import json, os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def initialize_mt5():
    if not mt5.initialize():
        raise RuntimeError("MT5 initialization failed")

def fetch_data(symbol, bars=5000):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, bars)
    df = pd.DataFrame(rates)
    df['date'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('date', inplace=True)
    return df[['open', 'high', 'low', 'close', 'tick_volume']].rename(
        columns={'open':'Open','high':'High','low':'Low','close':'Close','tick_volume':'Volume'})

def main():
    initialize_mt5()
    
    try:
        gold = fetch_data('XAUUSDm')
        silver = fetch_data('XAGUSDm')
        oil = fetch_data('UKOILm')
        usdchf = fetch_data('USDCHFm')
        
        for df in [gold, silver, oil, usdchf]:
            df['Return'] = np.log(df['Close'] / df['Close'].shift(1))
        
        common_idx = gold.index.intersection(silver.index).intersection(oil.index).intersection(usdchf.index)
        gold = gold.loc[common_idx]
        silver = silver.loc[common_idx]
        oil = oil.loc[common_idx]
        usdchf = usdchf.loc[common_idx]
        
        # 金银比
        gsr = gold['Close'] / silver['Close']
        gsr_ret = np.log(gsr / gsr.shift(1))
        gsr_20d = (gsr - gsr.shift(20)) / gsr.shift(20)
        silver_excess = silver['Return'] - gold['Return']
        
        warmup = 365
        data = pd.DataFrame({
            'gsr_20d': gsr_20d.iloc[warmup:],
            'silver_excess': silver_excess.iloc[warmup:],
            'gold_ret': gold['Return'].iloc[warmup:],
            'silver_ret': silver['Return'].iloc[warmup:],
            'oil_price': oil['Close'].iloc[warmup:],
        })
        data = data.dropna()
        
        # ====== 策略1: GSR动量方向策略 ======
        # 当GSR走阔(>0) → 做空白银/做多黄金 (捕获白银相对下跌)
        # 当GSR收窄(<0) → 做多白银/做空黄金 (捕获白银相对上涨)
        data['signal'] = np.sign(data['gsr_20d'])
        data['strategy_raw'] = -data['signal'] * data['silver_excess']
        
        # 交易成本: 假设每次调仓成本 5bp (双边)
        data['position_change'] = data['signal'].diff().abs()
        data['cost'] = data['position_change'] * 0.0005
        data['strategy_net'] = data['strategy_raw'] - data['cost']
        
        strat = data.dropna(subset=['strategy_net'])
        
        total_gross = (1 + strat['strategy_raw']).prod() - 1
        total_net = (1 + strat['strategy_net']).prod() - 1
        sharpe_gross = strat['strategy_raw'].mean() / strat['strategy_raw'].std() * np.sqrt(252)
        sharpe_net = strat['strategy_net'].mean() / strat['strategy_net'].std() * np.sqrt(252)
        
        # 最大回撤
        cum_net = (1 + strat['strategy_net']).cumprod()
        peak = cum_net.cummax()
        dd = (cum_net - peak) / peak
        max_dd = dd.min()
        
        # 年化交易次数
        n_trades = data['position_change'].sum() / 2  # 每次开+平 = 1次完整交易
        annual_trades = n_trades / (len(data) / 252)
        
        print(f"=== GSR动量策略 (含交易成本) ===")
        print(f"总收益(毛): {total_gross*100:.1f}%")
        print(f"总收益(净): {total_net*100:.1f}%")
        print(f"夏普(毛): {sharpe_gross:.3f}")
        print(f"夏普(净): {sharpe_net:.3f}")
        print(f"最大回撤: {max_dd*100:.2f}%")
        print(f"年化交易次数: {annual_trades:.0f}")
        print(f"交易天数: {len(strat)}")
        
        # ====== 策略2: Regime过滤的GSR策略 ======
        # 仅在复合鹰派Regime内交易
        regime = pd.DataFrame(index=oil.index)
        regime['high_oil'] = (oil['Close'] > 95).astype(int)
        regime['usdchf_ret_20d'] = usdchf['Close'].pct_change(20)
        regime['dollar_strong'] = (regime['usdchf_ret_20d'] > 0).astype(int)
        regime['composite_hawkish'] = regime['high_oil'] & regime['dollar_strong']
        
        regime_aligned = regime.loc[data.index].copy()
        data['hawkish'] = regime_aligned['composite_hawkish']
        
        # 策略: 鹰派Regime内做空白银相对黄金
        data['regime_strategy'] = np.where(data['hawkish'].astype(bool), -data['silver_excess'], 0)
        hawkish_now = data['hawkish'].astype(bool)
        hawkish_prev = hawkish_now.shift(1).fillna(False)
        data['regime_cost'] = np.where(hawkish_now & ~hawkish_prev, 0.0005, 0)
        data['regime_net'] = data['regime_strategy'] - data['regime_cost']
        
        reg_strat = data.dropna(subset=['regime_net'])
        reg_total = (1 + reg_strat['regime_net']).prod() - 1
        reg_sharpe = reg_strat['regime_net'].mean() / reg_strat['regime_net'].std() * np.sqrt(252) if reg_strat['regime_net'].std() > 0 else 0
        reg_cum = (1 + reg_strat['regime_net']).cumprod()
        reg_peak = reg_cum.cummax()
        reg_dd = (reg_cum - reg_peak) / reg_peak
        reg_max_dd = reg_dd.min()
        
        hawkish_days = data['hawkish'].sum()
        print(f"\n=== Regime过滤策略 (仅鹰派期做空白银/做多黄金) ===")
        print(f"鹰派Regime天数: {hawkish_days} / {len(data)}")
        print(f"总收益(净): {reg_total*100:.2f}%")
        print(f"夏普(净): {reg_sharpe:.3f}")
        print(f"最大回撤: {reg_max_dd*100:.2f}%")
        
        # ====== 分期间分析 ======
        data['year'] = data.index.year
        print(f"\n=== 分年度白银超额收益 ===")
        yearly = data.groupby('year').agg(
            silver_excess_mean=('silver_excess', 'mean'),
            silver_excess_ann=('silver_excess', lambda x: x.mean() * 252 * 100),
            hawkish_days=('hawkish', 'sum'),
            total_days=('silver_excess', 'count'),
        )
        for year, row in yearly.iterrows():
            print(f"  {year}: 白银年化超额={row['silver_excess_ann']:+.1f}%, 鹰派天数={int(row['hawkish_days'])}/{int(row['total_days'])}")
        
        # ====== GSR阈值搜索 ======
        print(f"\n=== GSR动量阈值优化 ===")
        best_sharpe = 0
        best_thresh = 0
        for thresh in np.arange(0, 0.10, 0.005):
            mask = data['gsr_20d'].abs() > thresh
            if mask.sum() < 50:
                continue
            sub = data.loc[mask]
            ret = -np.sign(sub['gsr_20d']) * sub['silver_excess']
            sh = ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else 0
            if sh > best_sharpe:
                best_sharpe = sh
                best_thresh = thresh
        print(f"最佳阈值: {best_thresh:.3f}, 夏普: {best_sharpe:.3f}")
        
        # 保存补充结果
        supplementary = {
            "gsr_strategy": {
                "total_return_gross": float(total_gross),
                "total_return_net": float(total_net),
                "sharpe_gross": float(sharpe_gross),
                "sharpe_net": float(sharpe_net),
                "max_drawdown": float(max_dd),
                "annual_trades": float(annual_trades),
                "trading_days": int(len(strat)),
            },
            "regime_strategy": {
                "hawkish_days": int(hawkish_days),
                "total_days": int(len(data)),
                "total_return_net": float(reg_total),
                "sharpe_net": float(reg_sharpe),
                "max_drawdown": float(reg_max_dd),
            },
            "threshold_optimization": {
                "best_threshold": float(best_thresh),
                "best_sharpe": float(best_sharpe),
            },
            "yearly_excess": {str(k): {
                "silver_annualized_excess_pct": float(v['silver_excess_ann']),
                "hawkish_days": int(v['hawkish_days']),
                "total_days": int(v['total_days']),
            } for k, v in yearly.iterrows()},
        }
        
        path = os.path.join(OUTPUT_DIR, "supplementary_results.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(supplementary, f, indent=2, ensure_ascii=False)
        print(f"\n✅ 补充结果已保存: {path}")
        
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
