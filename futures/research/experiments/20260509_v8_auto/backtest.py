#!/usr/bin/env python3
"""
黄金-白银分化模型研究
研究贵金属在复合风险环境下的结构性差异

假设 H1: 在复合鹰派 Regime（高油价+美元走强）下，金银比(GSR)显著走阔，
       白银因工业属性受损而相对黄金大幅跑输。

假设 H2: 金银比的动量（20日变化率）对未来30日白银-黄金相对收益具有预测能力。

数据源: MT5 (XAUUSDm, XAGUSDm, UKOILm, USDCHFm, USTECm, EURUSDm)
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
import json
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def initialize_mt5():
    if not mt5.initialize():
        raise RuntimeError("MT5 initialization failed")
    print("✅ MT5 initialized")

def fetch_data(symbol, timeframe=mt5.TIMEFRAME_D1, bars=5000):
    """获取历史K线数据"""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['date'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('date', inplace=True)
    df = df[['open', 'high', 'low', 'close', 'tick_volume']].copy()
    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    return df

def compute_returns(df):
    """计算对数收益率"""
    df['Return'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Return_1d'] = df['Return']
    return df

def compute_gsr(gold_df, silver_df):
    """计算金银比 (Gold-Silver Ratio)"""
    gsr = pd.DataFrame(index=gold_df.index)
    gsr['GSR'] = gold_df['Close'] / silver_df['Close']
    gsr['GSR_Return'] = np.log(gsr['GSR'] / gsr['GSR'].shift(1))
    gsr['GSR_20d_chg'] = (gsr['GSR'] - gsr['GSR'].shift(20)) / gsr['GSR'].shift(20)
    gsr['GSR_60d_chg'] = (gsr['GSR'] - gsr['GSR'].shift(60)) / gsr['GSR'].shift(60)
    return gsr

def compute_regime(oil_df, usdchf_df):
    """
    定义 Regime 信号 (复用 v7 的定义以保持一致性):
    - high_oil: UKOIL > $95
    - dollar_strong: USDCHF 20日收益率 > 0
    - composite_hawkish: high_oil AND dollar_strong
    """
    regime = pd.DataFrame(index=oil_df.index)
    regime['oil_price'] = oil_df['Close']
    regime['high_oil'] = (oil_df['Close'] > 95).astype(int)
    regime['usdchf_ret_20d'] = usdchf_df['Close'].pct_change(20)
    regime['dollar_strong'] = (regime['usdchf_ret_20d'] > 0).astype(int)
    regime['composite_hawkish'] = regime['high_oil'] & regime['dollar_strong']
    
    # Oil volatility regime
    regime['oil_vol_60d'] = oil_df['Return'].rolling(60).std() * np.sqrt(252)
    oil_vol_median = regime['oil_vol_60d'].median()
    regime['oil_vol_high'] = (regime['oil_vol_60d'] > oil_vol_median).astype(int)
    
    return regime

def run_h1_analysis(gold_df, silver_df, gsr, regime):
    """
    H1: 复合鹰派 Regime 下金银比走阔、白银跑输黄金
    """
    print("\n" + "="*60)
    print("假设 H1: 复合鹰派 Regime 下金银比走阔分析")
    print("="*60)
    
    # 对齐数据
    common_idx = gsr.index.intersection(regime.index)
    gsr_aligned = gsr.loc[common_idx].copy()
    regime_aligned = regime.loc[common_idx].copy()
    
    # 剔除预热期 (前365天)
    warmup = 365
    gsr_aligned = gsr_aligned.iloc[warmup:]
    regime_aligned = regime_aligned.iloc[warmup:]
    
    # 白银相对黄金的日度超额收益
    gsr_aligned['silver_excess'] = silver_df.loc[gsr_aligned.index, 'Return'] - gold_df.loc[gsr_aligned.index, 'Return']
    gsr_aligned['silver_cumulative'] = (1 + gsr_aligned['silver_excess']).cumprod()
    gsr_aligned['gold_cumulative'] = (1 + gold_df.loc[gsr_aligned.index, 'Return']).cumprod()
    
    # Regime 分析
    hawkish_mask = regime_aligned['composite_hawkish'] == 1
    normal_mask = regime_aligned['composite_hawkish'] == 0
    
    # 1. 金银比水平对比
    gsr_in = gsr_aligned.loc[hawkish_mask, 'GSR']
    gsr_out = gsr_aligned.loc[normal_mask, 'GSR']
    
    # 2. 白银相对收益对比
    silver_excess_in = gsr_aligned.loc[hawkish_mask, 'silver_excess']
    silver_excess_out = gsr_aligned.loc[normal_mask, 'silver_excess']
    
    # 3. GSR 变化率对比
    gsr_chg_in = gsr_aligned.loc[hawkish_mask, 'GSR_Return']
    gsr_chg_out = gsr_aligned.loc[normal_mask, 'GSR_Return']
    
    # 统计检验
    t_stat_gsr, p_gsr = stats.ttest_ind(gsr_chg_in, gsr_chg_out, equal_var=False)
    t_stat_excess, p_excess = stats.ttest_ind(silver_excess_in, silver_excess_out, equal_var=False)
    
    # 年化相对收益
    ann_excess_in = silver_excess_in.mean() * 252 * 100
    ann_excess_out = silver_excess_out.mean() * 252 * 100
    
    # GSR 在 Regime 内的平均变化
    avg_gsr_in = gsr_in.mean()
    avg_gsr_out = gsr_out.mean()
    
    # Cohen's d
    def cohens_d(a, b):
        n1, n2 = len(a), len(b)
        s1, s2 = a.std(), b.std()
        s_pooled = np.sqrt(((n1-1)*s1**2 + (n2-1)*s2**2) / (n1+n2-2))
        if s_pooled == 0:
            return 0
        return (a.mean() - b.mean()) / s_pooled
    
    d_gsr = cohens_d(gsr_chg_in, gsr_chg_out)
    d_excess = cohens_d(silver_excess_in, silver_excess_out)
    
    # 20日累计窗口检验（降低噪音）
    gsr_20d = gsr_aligned['GSR_Return'].rolling(20).sum()
    silver_excess_20d = gsr_aligned['silver_excess'].rolling(20).sum()
    
    # 将 regime 标签传播到20日窗口
    gsr_20d_in = gsr_20d[hawkish_mask].dropna()
    gsr_20d_out = gsr_20d[normal_mask].dropna()
    se_20d_in = silver_excess_20d[hawkish_mask].dropna()
    se_20d_out = silver_excess_20d[normal_mask].dropna()
    
    t_20d_gsr, p_20d_gsr = stats.ttest_ind(gsr_20d_in, gsr_20d_out, equal_var=False)
    t_20d_se, p_20d_se = stats.ttest_ind(se_20d_in, se_20d_out, equal_var=False)
    
    # 高油价单独分析
    high_oil_mask = regime_aligned['high_oil'] == 1
    se_high_oil = gsr_aligned.loc[high_oil_mask, 'silver_excess']
    se_no_oil = gsr_aligned.loc[~high_oil_mask, 'silver_excess']
    t_oil, p_oil = stats.ttest_ind(se_high_oil, se_no_oil, equal_var=False)
    ann_excess_oil = se_high_oil.mean() * 252 * 100
    ann_excess_no_oil = se_no_oil.mean() * 252 * 100
    
    results = {
        "h1_daily": {
            "gsr_mean_in_regime": float(avg_gsr_in),
            "gsr_mean_out_regime": float(avg_gsr_out),
            "gsr_delta": float(avg_gsr_in - avg_gsr_out),
            "silver_annualized_excess_in": float(ann_excess_in),
            "silver_annualized_excess_out": float(ann_excess_out),
            "gsr_t_stat": float(t_stat_gsr),
            "gsr_p_value": float(p_gsr),
            "gsr_cohens_d": float(d_gsr),
            "excess_t_stat": float(t_stat_excess),
            "excess_p_value": float(p_excess),
            "excess_cohens_d": float(d_excess),
            "n_regime_days": int(hawkish_mask.sum()),
            "n_normal_days": int(normal_mask.sum()),
        },
        "h1_20day": {
            "gsr_20d_t_stat": float(t_20d_gsr),
            "gsr_20d_p_value": float(p_20d_gsr),
            "se_20d_t_stat": float(t_20d_se),
            "se_20d_p_value": float(p_20d_se),
            "se_20d_mean_in": float(se_20d_in.mean()) * 100,
            "se_20d_mean_out": float(se_20d_out.mean()) * 100,
        },
        "h1_oil_only": {
            "silver_annualized_excess_high_oil": float(ann_excess_oil),
            "silver_annualized_excess_no_oil": float(ann_excess_no_oil),
            "t_stat": float(t_oil),
            "p_value": float(p_oil),
        }
    }
    
    print(f"\n--- 日度收益检验 ---")
    print(f"复合鹰派 Regime 天数: {hawkish_mask.sum()} / 总天数 {len(regime_aligned)}")
    print(f"金银比均值 (Regime内): {avg_gsr_in:.2f}")
    print(f"金银比均值 (Regime外): {avg_gsr_out:.2f}")
    print(f"金银比差异: {avg_gsr_in - avg_gsr_out:+.2f}")
    print(f"白银年化超额收益 (Regime内): {ann_excess_in:+.2f}%")
    print(f"白银年化超额收益 (Regime外): {ann_excess_out:+.2f}%")
    print(f"GSR 变化 t检验: t={t_stat_gsr:.3f}, p={p_gsr:.4f}, d={d_gsr:.3f}")
    print(f"白银超额 t检验: t={t_stat_excess:.3f}, p={p_excess:.4f}, d={d_excess:.3f}")
    
    print(f"\n--- 20日累计窗口检验 ---")
    print(f"GSR: t={t_20d_gsr:.3f}, p={p_20d_gsr:.6f}")
    print(f"白银超额: t={t_20d_se:.3f}, p={p_20d_se:.6f}")
    print(f"白银20日超额均值 (内): {se_20d_in.mean()*100:+.3f}%")
    print(f"白银20日超额均值 (外): {se_20d_out.mean()*100:+.3f}%")
    
    print(f"\n--- 单一高油价信号 ---")
    print(f"白银年化超额 (高油价): {ann_excess_oil:+.2f}%")
    print(f"白银年化超额 (非高油价): {ann_excess_no_oil:+.2f}%")
    print(f"t={t_oil:.3f}, p={p_oil:.4f}")
    
    return results

def run_h2_analysis(gold_df, silver_df, gsr, regime):
    """
    H2: 金银比动量对未来白银-黄金相对收益的预测能力
    """
    print("\n" + "="*60)
    print("假设 H2: 金银比动量预测能力")
    print("="*60)
    
    common_idx = gsr.index.intersection(gold_df.index).intersection(silver_df.index)
    gsr_aligned = gsr.loc[common_idx].copy()
    
    warmup = 365
    gsr_aligned = gsr_aligned.iloc[warmup:]
    
    # 白银相对黄金的日度超额收益
    gsr_aligned['silver_excess'] = silver_df.loc[gsr_aligned.index, 'Return'] - gold_df.loc[gsr_aligned.index, 'Return']
    
    # 白银相对收益 (前向)
    silver_ret = silver_df.loc[gsr_aligned.index, 'Return']
    gold_ret = gold_df.loc[gsr_aligned.index, 'Return']
    silver_excess = gsr_aligned['silver_excess']
    
    # 前向20日累计收益: 从t+1到t+20的累计
    # shift(-1) 把t+1的值放到t位置，rolling(20).sum() 取t到t+19共20个值 = 原始t+1到t+20
    gsr_aligned['silver_excess_fwd_20d'] = silver_excess.shift(-1).rolling(20).sum()
    gsr_aligned['silver_excess_fwd_30d'] = silver_excess.shift(-1).rolling(30).sum()
    gsr_aligned['gold_excess_fwd_20d'] = gold_ret.shift(-1).rolling(20).sum()
    gsr_aligned['relative_fwd_20d'] = silver_excess.shift(-1).rolling(20).sum() - gold_ret.shift(-1).rolling(20).sum()
    
    valid = gsr_aligned.dropna(subset=['GSR_20d_chg', 'relative_fwd_20d'])
    
    # 相关性分析
    corr_20d = valid['GSR_20d_chg'].corr(valid['relative_fwd_20d'])
    corr_60d = valid['GSR_60d_chg'].corr(valid['relative_fwd_20d'])
    
    # 回归分析
    from scipy import stats as scipy_stats
    slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(
        valid['GSR_20d_chg'], valid['relative_fwd_20d']
    )
    
    # 分位数分组分析
    valid['gsr_quintile'] = pd.qcut(valid['GSR_20d_chg'], 5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
    quintile_means = valid.groupby('gsr_quintile')['relative_fwd_20d'].mean() * 100
    quintile_counts = valid.groupby('gsr_quintile')['relative_fwd_20d'].count()
    
    # 顶部 vs 底部五分位 t检验
    q1_data = valid[valid['gsr_quintile'] == 'Q1']['relative_fwd_20d']
    q5_data = valid[valid['gsr_quintile'] == 'Q5']['relative_fwd_20d']
    t_q, p_q = stats.ttest_ind(q1_data, q5_data, equal_var=False)
    
    # 策略模拟: GSR动量信号
    # 当 GSR_20d_chg > 0 (金银比走阔) → 做多黄金/做空白银
    # 当 GSR_20d_chg < 0 (金银比收窄) → 做多白银/做空黄金
    gsr_aligned['signal'] = np.sign(gsr_aligned['GSR_20d_chg'])
    gsr_aligned['strategy_return'] = gsr_aligned['signal'] * (-gsr_aligned['silver_excess'])
    
    strategy = gsr_aligned.dropna(subset=['strategy_return'])
    total_return = (1 + strategy['strategy_return']).prod() - 1
    sharpe = strategy['strategy_return'].mean() / strategy['strategy_return'].std() * np.sqrt(252) if strategy['strategy_return'].std() > 0 else 0
    
    # 买入持有黄金基准
    gold_ret_for_benchmark = gold_df.loc[strategy.index, 'Return']
    gold_total = (1 + gold_ret_for_benchmark).prod() - 1
    gold_sharpe = gold_ret_for_benchmark.mean() / gold_ret_for_benchmark.std() * np.sqrt(252)
    
    results = {
        "h2_correlation": {
            "corr_20d": float(corr_20d),
            "corr_60d": float(corr_60d),
        },
        "h2_regression": {
            "slope": float(slope),
            "intercept": float(intercept),
            "r_squared": float(r_value**2),
            "p_value": float(p_value),
            "std_error": float(std_err),
            "n_observations": int(len(valid)),
        },
        "h2_quintiles": {
            str(k): {"mean_relative_return_pct": float(v), "count": int(quintile_counts[k])}
            for k, v in quintile_means.items()
        },
        "h2_quintile_test": {
            "t_stat": float(t_q),
            "p_value": float(p_q),
        },
        "h2_strategy": {
            "total_return": float(total_return),
            "sharpe_ratio": float(sharpe),
            "gold_total_return": float(gold_total),
            "gold_sharpe": float(gold_sharpe),
            "n_trading_days": int(len(strategy)),
        }
    }
    
    print(f"\n--- 相关性分析 ---")
    print(f"GSR 20日变化 vs 白银相对20日前向收益: r={corr_20d:.4f}")
    print(f"GSR 60日变化 vs 白银相对20日前向收益: r={corr_60d:.4f}")
    
    print(f"\n--- 回归分析 ---")
    print(f"斜率: {slope:.4f}, 截距: {intercept:.4f}")
    print(f"R²={r_value**2:.4f}, p={p_value:.6f}")
    print(f"观测数: {len(valid)}")
    
    print(f"\n--- 五分位分组 ---")
    for q in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
        print(f"  {q}: 平均相对收益 = {quintile_means[q]:+.3f}% (n={quintile_counts[q]})")
    print(f"Q1 vs Q5: t={t_q:.3f}, p={p_q:.4f}")
    
    print(f"\n--- GSR动量策略 vs 买入持有黄金 ---")
    print(f"GSR动量策略: 总收益={total_return*100:.2f}%, 夏普={sharpe:.3f}")
    print(f"买入持有黄金: 总收益={gold_total*100:.2f}%, 夏普={gold_sharpe:.3f}")
    
    return results

def run_cross_asset_analysis(gold_df, silver_df, regime, oil_df):
    """补充分析: 贵金属与原油/股指的相关性结构"""
    print("\n" + "="*60)
    print("补充分析: 跨资产相关性结构")
    print("="*60)
    
    # 60日滚动相关性
    common_idx = gold_df.index.intersection(silver_df.index).intersection(oil_df.index)
    analysis = pd.DataFrame(index=common_idx)
    analysis['gold_ret'] = gold_df.loc[common_idx, 'Return']
    analysis['silver_ret'] = silver_df.loc[common_idx, 'Return']
    analysis['oil_ret'] = oil_df.loc[common_idx, 'Return']
    
    analysis['corr_gold_oil_60d'] = analysis['gold_ret'].rolling(60).corr(analysis['oil_ret'])
    analysis['corr_silver_oil_60d'] = analysis['silver_ret'].rolling(60).corr(analysis['oil_ret'])
    analysis['corr_gold_silver_60d'] = analysis['gold_ret'].rolling(60).corr(analysis['silver_ret'])
    
    hawkish_mask = regime.loc[analysis.index, 'composite_hawkish'] == 1
    
    print(f"\n--- 60日滚动相关性 (Regime内 vs 外) ---")
    for name in ['corr_gold_oil_60d', 'corr_silver_oil_60d', 'corr_gold_silver_60d']:
        in_mean = analysis.loc[hawkish_mask, name].mean()
        out_mean = analysis.loc[~hawkish_mask, name].mean()
        in_min = analysis.loc[hawkish_mask, name].min()
        out_min = analysis.loc[~hawkish_mask, name].min()
        print(f"  {name}: Regime内均值={in_mean:.3f}, Regime外均值={out_mean:.3f}, 内最低={in_min:.3f}")
    
    # 白银波动率对比
    analysis['silver_vol_20d'] = analysis['silver_ret'].rolling(20).std() * np.sqrt(252)
    analysis['gold_vol_20d'] = analysis['gold_ret'].rolling(20).std() * np.sqrt(252)
    
    silver_vol_in = analysis.loc[hawkish_mask, 'silver_vol_20d'].mean()
    silver_vol_out = analysis.loc[~hawkish_mask, 'silver_vol_20d'].mean()
    gold_vol_in = analysis.loc[hawkish_mask, 'gold_vol_20d'].mean()
    gold_vol_out = analysis.loc[~hawkish_mask, 'gold_vol_20d'].mean()
    
    print(f"\n--- 20日年化波动率 ---")
    print(f"白银: Regime内={silver_vol_in:.2%}, Regime外={silver_vol_out:.2%}, 差异={silver_vol_in-silver_vol_out:+.2%}")
    print(f"黄金: Regime内={gold_vol_in:.2%}, Regime外={gold_vol_out:.2%}, 差异={gold_vol_in-gold_vol_out:+.2%}")
    
    return {
        "correlations": {
            "gold_oil_in": float(analysis.loc[hawkish_mask, 'corr_gold_oil_60d'].mean()),
            "gold_oil_out": float(analysis.loc[~hawkish_mask, 'corr_gold_oil_60d'].mean()),
            "silver_oil_in": float(analysis.loc[hawkish_mask, 'corr_silver_oil_60d'].mean()),
            "silver_oil_out": float(analysis.loc[~hawkish_mask, 'corr_silver_oil_60d'].mean()),
            "gold_silver_in": float(analysis.loc[hawkish_mask, 'corr_gold_silver_60d'].mean()),
            "gold_silver_out": float(analysis.loc[~hawkish_mask, 'corr_gold_silver_60d'].mean()),
        },
        "volatility": {
            "silver_vol_in": float(silver_vol_in),
            "silver_vol_out": float(silver_vol_out),
            "gold_vol_in": float(gold_vol_in),
            "gold_vol_out": float(gold_vol_out),
        }
    }

def main():
    print("="*60)
    print("黄金-白银分化模型研究")
    print("实验 ID: 20260509_v8_auto")
    print("="*60)
    
    initialize_mt5()
    
    try:
        # 获取数据
        print("\n📥 获取数据...")
        gold_df = fetch_data('XAUUSDm', bars=5000)
        silver_df = fetch_data('XAGUSDm', bars=5000)
        oil_df = fetch_data('UKOILm', bars=5000)
        usdchf_df = fetch_data('USDCHFm', bars=5000)
        
        if any(df is None for df in [gold_df, silver_df, oil_df, usdchf_df]):
            print("❌ 数据获取失败")
            return
        
        print(f"黄金: {gold_df.index[0].date()} to {gold_df.index[-1].date()} ({len(gold_df)} bars)")
        print(f"白银: {silver_df.index[0].date()} to {silver_df.index[-1].date()} ({len(silver_df)} bars)")
        print(f"布油: {oil_df.index[0].date()} to {oil_df.index[-1].date()} ({len(oil_df)} bars)")
        print(f"USDCHF: {usdchf_df.index[0].date()} to {usdchf_df.index[-1].date()} ({len(usdchf_df)} bars)")
        
        # 计算收益率
        for df in [gold_df, silver_df, oil_df, usdchf_df]:
            compute_returns(df)
        
        # 计算金银比
        gsr = compute_gsr(gold_df, silver_df)
        
        # 计算 Regime
        regime = compute_regime(oil_df, usdchf_df)
        
        # H1 分析
        h1_results = run_h1_analysis(gold_df, silver_df, gsr, regime)
        
        # H2 分析
        h2_results = run_h2_analysis(gold_df, silver_df, gsr, regime)
        
        # 跨资产分析
        cross_results = run_cross_asset_analysis(gold_df, silver_df, regime, oil_df)
        
        # 保存结果
        all_results = {
            "h1": h1_results,
            "h2": h2_results,
            "cross_asset": cross_results,
            "metadata": {
                "gold_range": f"{gold_df.index[0].date()} to {gold_df.index[-1].date()}",
                "silver_range": f"{silver_df.index[0].date()} to {silver_df.index[-1].date()}",
                "oil_range": f"{oil_df.index[0].date()} to {oil_df.index[-1].date()}",
                "usdchf_range": f"{usdchf_df.index[0].date()} to {usdchf_df.index[-1].date()}",
                "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        }
        
        output_path = os.path.join(OUTPUT_DIR, "backtest_results.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\n✅ 结果已保存: {output_path}")
        
    finally:
        mt5.shutdown()
        print("\n✅ MT5 shutdown")

if __name__ == "__main__":
    main()
