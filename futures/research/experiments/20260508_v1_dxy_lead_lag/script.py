#!/usr/bin/env python3
"""
Reference Script: DXY Lead-Lag Analysis for Gold & Oil
Methodology:
1. Calculate H1 returns for XAUUSD, XTIUSD, DXY
2. Compute 24h/72h rolling Pearson correlation
3. Cross-Correlation Function (CCF) to detect lead/lag hours
4. Regime Filter: High Volatility (ATR > 1.5x median) vs Low Volatility
5. Statistical Significance: t-test on correlation coefficients
"""

import pandas as pd
import numpy as np
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

def load_data():
    # Placeholder paths - AI will replace with actual data paths
    gold = pd.read_csv('../data/gold_h1.csv', parse_dates=['time'], index_col='time')
    oil = pd.read_csv('../data/oil_h1.csv', parse_dates=['time'], index_col='time')
    dxy = pd.read_csv('../data/dxy_h1.csv', parse_dates=['time'], index_col='time')
    
    # Resample to ensure aligned timestamps
    df = pd.concat([gold['close'], oil['close'], dxy['close']], axis=1, keys=['gold', 'oil', 'dxy'])
    df = df.dropna()
    return df

def calculate_returns(df):
    df['ret_gold'] = df['gold'].pct_change()
    df['ret_oil'] = df['oil'].pct_change()
    df['ret_dxy'] = df['dxy'].pct_change() * -1  # Invert DXY (negative correlation expected)
    return df.dropna()

def rolling_correlation(df, window=24):
    corr_gold_dxy = df['ret_gold'].rolling(window).corr(df['ret_dxy'])
    corr_oil_dxy = df['ret_oil'].rolling(window).corr(df['ret_dxy'])
    return pd.DataFrame({'gold_dxy': corr_gold_dxy, 'oil_dxy': corr_oil_dxy})

def cross_correlation_lag(series_x, series_y, max_lag=12):
    """Find optimal lead/lag hours"""
    ccf = [series_x.corr(series_y.shift(lag)) for lag in range(-max_lag, max_lag+1)]
    lags = range(-max_lag, max_lag+1)
    optimal_lag = lags[np.argmax(np.abs(ccf))]
    max_corr = max(ccf)
    return optimal_lag, max_corr

def regime_filter(df, atr_window=20):
    """Filter by volatility regime"""
    # Simplified ATR proxy using rolling std of returns
    vol = df['ret_gold'].rolling(atr_window).std()
    median_vol = vol.median()
    df['high_vol_regime'] = vol > (median_vol * 1.5)
    return df

def statistical_test(df, window=24):
    """Test if correlation is significantly different from 0"""
    corr = df['ret_gold'].rolling(window).corr(df['ret_dxy']).dropna()
    # Approximate t-statistic for correlation
    n = window
    t_stat = corr * np.sqrt((n - 2) / (1 - corr**2))
    p_value = 2 * (1 - stats.t.cdf(np.abs(t_stat), df=n-2))
    return p_value

if __name__ == "__main__":
    print("=== DXY Lead-Lag Analysis ===")
    df = load_data()
    df = calculate_returns(df)
    
    # 1. Rolling Correlation
    roll_corr = rolling_correlation(df, window=24)
    print(f"Avg 24h Correlation (Gold-DXY): {roll_corr['gold_dxy'].mean():.3f}")
    print(f"Avg 24h Correlation (Oil-DXY):  {roll_corr['oil_dxy'].mean():.3f}")
    
    # 2. Lead-Lag Detection
    lag_gold, corr_gold = cross_correlation_lag(df['ret_gold'], df['ret_dxy'], max_lag=6)
    print(f"Optimal Lag (Gold): {lag_gold}h, Max Correlation: {corr_gold:.3f}")
    
    # 3. Regime Analysis
    df = regime_filter(df)
    high_vol_corr = df[df['high_vol_regime']]['ret_gold'].corr(df[df['high_vol_regime']]['ret_dxy'])
    low_vol_corr = df[~df['high_vol_regime']]['ret_gold'].corr(df[~df['high_vol_regime']]['ret_dxy'])
    print(f"Correlation in High Vol Regime: {high_vol_corr:.3f}")
    print(f"Correlation in Low Vol Regime:  {low_vol_corr:.3f}")
    
    # 4. Significance
    p_vals = statistical_test(df, window=24)
    sig_pct = (p_vals < 0.05).mean()
    print(f"Percentage of Significant Correlations (p<0.05): {sig_pct:.1%}")
    
    print("\n=== Conclusion ===")
    if lag_gold < 0:
        print(f"⚠️ DXY leads Gold by {abs(lag_gold)} hours. Trade filter recommended.")
    else:
        print("✅ No significant lead-lag detected. DXY filter may not be necessary.")
