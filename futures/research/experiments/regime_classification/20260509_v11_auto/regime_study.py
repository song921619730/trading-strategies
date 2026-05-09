"""
Experiment v11: Macro Regime Detection & Cross-Asset Performance
H1: 3-factor regime (equity momentum, gold momentum, oil level) 
    segments market into distinct environments with significantly different asset returns.
H2: Stagflation regime (oil>=100, equity<0, gold>0) produces abnormal returns in precious metals.
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime
import json
import sys
import warnings
warnings.filterwarnings('ignore')

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

SYMBOLS = [
    "XAUUSDm", "XAGUSDm",
    "EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm", "USDCHFm",
    "USOILm", "UKOILm",
    "USTECm", "US30m", "US500m", "JP225m", "HK50m"
]

def connect_mt5():
    if not mt5.initialize(path=MT5_PATH):
        print(f"MT5 init failed: {mt5.last_error()}")
        sys.exit(1)
    print("MT5 connected.")

def fetch_all_d1():
    data = {}
    for sym in SYMBOLS:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 5000)
        if rates is None or len(rates) == 0:
            print(f"  WARN: No data for {sym}")
            continue
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'tick_volume']].dropna()
        data[sym] = df
        print(f"  {sym}: {len(df)} bars, {df.index[0].date()} to {df.index[-1].date()}")
    return data

def compute_regimes(data):
    us500 = data.get("US500m")
    xau = data.get("XAUUSDm")
    ukoil = data.get("UKOILm")
    
    if any(x is None for x in [us500, xau, ukoil]):
        print("ERROR: Missing core data for regime classification")
        return pd.DataFrame()
    
    us500['r20'] = us500['close'].pct_change(20)
    xau['r20'] = xau['close'].pct_change(20)
    
    merged = pd.DataFrame(index=us500.index.intersection(xau.index).intersection(ukoil.index))
    merged['us500_r20'] = us500['r20']
    merged['xau_r20'] = xau['r20']
    merged['ukoil_price'] = ukoil['close']
    merged = merged.dropna()
    
    def classify(row):
        eq_up = row['us500_r20'] > 0
        eq_down = row['us500_r20'] < 0
        gold_up = row['xau_r20'] > 0
        oil_high = row['ukoil_price'] >= 100
        
        if oil_high and eq_down and gold_up:
            return 'STAGFLATION'
        elif eq_up and not oil_high:
            return 'RISK_ON'
        elif gold_up and eq_down:
            return 'RISK_OFF'
        else:
            return 'NORMAL'
    
    merged['regime'] = merged.apply(classify, axis=1)
    merged = merged.sort_index()
    
    print(f"\nRegime distribution ({len(merged)} total days):")
    for r in ['RISK_ON', 'RISK_OFF', 'STAGFLATION', 'NORMAL']:
        n = (merged['regime'] == r).sum()
        pct = n / len(merged) * 100
        print(f"  {r}: {n} days ({pct:.1f}%)")
    
    return merged

def compute_asset_returns_by_regime(data, regimes_df):
    results = {}
    
    for sym in SYMBOLS:
        if sym not in data:
            continue
        df = data[sym].copy()
        df['ret'] = df['close'].pct_change()
        
        merged = df[['ret']].join(regimes_df[['regime']], how='inner')
        merged = merged.dropna()
        
        sym_results = {}
        for r in ['RISK_ON', 'RISK_OFF', 'STAGFLATION', 'NORMAL']:
            subset = merged[merged['regime'] == r]['ret'].dropna()
            if len(subset) < 20:
                sym_results[r] = {
                    'n_days': len(subset),
                    'ann_return': None,
                    'ann_vol': None,
                    'sharpe': None,
                    'max_dd': None,
                    'win_rate': None,
                }
                continue
            
            cum_ret = (1 + subset).cumprod()
            ann_return = (cum_ret.iloc[-1] ** (252 / len(subset))) - 1
            ann_vol = subset.std() * np.sqrt(252)
            sharpe = ann_return / ann_vol if ann_vol > 0 else 0
            
            peak = cum_ret.cummax()
            dd = (cum_ret - peak) / peak
            max_dd = dd.min()
            
            win_rate = (subset > 0).sum() / len(subset)
            
            sym_results[r] = {
                'n_days': int(len(subset)),
                'ann_return': float(ann_return),
                'ann_vol': float(ann_vol),
                'sharpe': float(sharpe),
                'max_dd': float(max_dd),
                'win_rate': float(win_rate),
            }
        
        results[sym] = sym_results
    
    return results

def regime_transition_analysis(regimes_df):
    reg = regimes_df['regime']
    
    transitions = pd.crosstab(reg.shift(1), reg, normalize='index') * 100
    print("\nRegime Transition Matrix (%):")
    print(transitions.round(1).to_string())
    
    durations = []
    current_regime = reg.iloc[0]
    duration = 1
    for i in range(1, len(reg)):
        if reg.iloc[i] == current_regime:
            duration += 1
        else:
            durations.append((current_regime, duration))
            current_regime = reg.iloc[i]
            duration = 1
    durations.append((current_regime, duration))
    
    dur_df = pd.DataFrame(durations, columns=['regime', 'duration'])
    print("\nAverage Regime Duration:")
    for r in ['RISK_ON', 'RISK_OFF', 'STAGFLATION', 'NORMAL']:
        sub = dur_df[dur_df['regime'] == r]['duration']
        if len(sub) > 0:
            print(f"  {r}: mean={sub.mean():.1f} days, median={sub.median():.0f} days, max={sub.max()} days (n={len(sub)} episodes)")
    
    return transitions

def test_hypotheses(results, regimes_df, data):
    print("\n" + "="*60)
    print("HYPOTHESIS TESTS")
    print("="*60)
    
    # H1
    print("\n--- H1: Regime separation test (US500m returns across regimes) ---")
    us500_data = data.get("US500m")
    if us500_data is not None:
        us500_ret = us500_data['close'].pct_change()
        merged = pd.DataFrame({'ret': us500_ret}).join(regimes_df[['regime']], how='inner').dropna()
        
        groups = []
        for r in ['RISK_ON', 'RISK_OFF', 'STAGFLATION', 'NORMAL']:
            g = merged[merged['regime'] == r]['ret'].dropna()
            if len(g) > 10:
                groups.append(g)
                print(f"  {r}: mean_daily_ret={g.mean()*100:.4f}%, n={len(g)}")
        
        if len(groups) >= 2:
            f_stat, p_val = stats.f_oneway(*groups)
            print(f"  ANOVA F={f_stat:.3f}, p={p_val:.2e}")
            if p_val < 0.05:
                print(f"  H1 SUPPORTED: Returns differ significantly across regimes (p={p_val:.2e})")
            else:
                print(f"  H1 NOT SUPPORTED: No significant difference (p={p_val:.2e})")
    
    # H2
    print("\n--- H2: Stagflation gold outperformance test ---")
    xau_data = data.get("XAUUSDm")
    h2_result = None
    if xau_data is not None:
        xau_ret = xau_data['close'].pct_change()
        merged = pd.DataFrame({'ret': xau_ret}).join(regimes_df[['regime']], how='inner').dropna()
        
        stag = merged[merged['regime'] == 'STAGFLATION']['ret']
        others = merged[merged['regime'] != 'STAGFLATION']['ret']
        
        if len(stag) > 10 and len(others) > 10:
            t_stat, p_val = stats.ttest_ind(stag, others, equal_var=False)
            stag_mean = stag.mean()
            others_mean = others.mean()
            print(f"  Stagflation: mean_daily={stag_mean*100:.4f}%, n={len(stag)}")
            print(f"  Other regimes: mean_daily={others_mean*100:.4f}%, n={len(others)}")
            print(f"  Welch's t={t_stat:.3f}, p={p_val:.4f}")
            if p_val < 0.05 and stag_mean > others_mean:
                print(f"  H2 SUPPORTED: Gold significantly outperforms in stagflation (p={p_val:.4f})")
                h2_result = "SUPPORTED"
            elif p_val >= 0.05:
                print(f"  H2 NOT SUPPORTED: No significant outperformance (p={p_val:.4f})")
                h2_result = "NOT_SUPPORTED"
            else:
                print(f"  H2 REJECTED: Gold significantly UNDERPERFORMS in stagflation (p={p_val:.4f})")
                h2_result = "REJECTED"
    
    # H2b: Silver in stagflation
    print("\n--- H2b: Stagflation silver performance ---")
    xag_data = data.get("XAGUSDm")
    h2b_result = None
    if xag_data is not None:
        xag_ret = xag_data['close'].pct_change()
        merged = pd.DataFrame({'ret': xag_ret}).join(regimes_df[['regime']], how='inner').dropna()
        
        stag = merged[merged['regime'] == 'STAGFLATION']['ret']
        others = merged[merged['regime'] != 'STAGFLATION']['ret']
        
        if len(stag) > 10 and len(others) > 10:
            t_stat, p_val = stats.ttest_ind(stag, others, equal_var=False)
            stag_mean = stag.mean()
            others_mean = others.mean()
            print(f"  Stagflation: mean_daily={stag_mean*100:.4f}%, n={len(stag)}")
            print(f"  Other regimes: mean_daily={others_mean*100:.4f}%, n={len(others)}")
            print(f"  Welch's t={t_stat:.3f}, p={p_val:.4f}")
            if p_val < 0.05 and stag_mean > others_mean:
                print(f"  Silver significantly outperforms in stagflation (p={p_val:.4f})")
                h2b_result = "SUPPORTED"
            elif p_val >= 0.05:
                print(f"  No significant outperformance (p={p_val:.4f})")
                h2b_result = "NOT_SUPPORTED"
            else:
                print(f"  Silver significantly UNDERPERFORMS in stagflation (p={p_val:.4f})")
                h2b_result = "REJECTED"

    # Test all symbols in each regime for completeness
    print("\n--- Extended: All symbols stagflation vs normal comparison ---")
    for sym in SYMBOLS:
        if sym not in data:
            continue
        s_ret = data[sym]['close'].pct_change()
        merged = pd.DataFrame({'ret': s_ret}).join(regimes_df[['regime']], how='inner').dropna()
        
        stag = merged[merged['regime'] == 'STAGFLATION']['ret']
        normal = merged[merged['regime'] == 'NORMAL']['ret']
        
        if len(stag) > 10 and len(normal) > 10:
            t_stat, p_val = stats.ttest_ind(stag, normal, equal_var=False)
            print(f"  {sym}: stag={stag.mean()*100:.4f}% vs normal={normal.mean()*100:.4f}%, p={p_val:.4f}")
    
    return h2_result, h2b_result

def regime_filter_backtest(data, regimes_df):
    print("\n" + "="*60)
    print("REGIME-FILTERED STRATEGY BACKTEST")
    print("="*60)
    
    us500_ret = data.get("US500m", pd.DataFrame())
    xau_ret = data.get("XAUUSDm", pd.DataFrame())
    ukoil_ret = data.get("UKOILm", pd.DataFrame())
    
    if any(len(x) == 0 for x in [us500_ret, xau_ret, ukoil_ret]):
        print("Missing data for backtest")
        return None
    
    strat_ret = pd.DataFrame(index=regimes_df.index)
    strat_ret['us500'] = us500_ret['close'].pct_change()
    strat_ret['xau'] = xau_ret['close'].pct_change()
    strat_ret['ukoil'] = ukoil_ret['close'].pct_change()
    strat_ret['regime'] = regimes_df['regime']
    strat_ret = strat_ret.dropna()
    
    def get_strat_ret(row):
        r = row['regime']
        if r == 'RISK_ON':
            return row['us500']
        elif r == 'RISK_OFF':
            return row['xau']
        elif r == 'STAGFLATION':
            return 0.5 * row['xau'] + 0.5 * row['ukoil']
        else:
            return 0.0
    
    strat_ret['strat'] = strat_ret.apply(get_strat_ret, axis=1)
    
    bh_ret = strat_ret['us500']
    s_ret = strat_ret['strat']
    
    print(f"\nPeriod: {strat_ret.index[0].date()} to {strat_ret.index[-1].date()} ({len(strat_ret)} days)")
    
    strat_cum = (1 + s_ret).cumprod()
    strat_ann = float((strat_cum.iloc[-1] ** (252 / len(s_ret))) - 1)
    strat_vol = float(s_ret.std() * np.sqrt(252))
    strat_sharpe = strat_ann / strat_vol if strat_vol > 0 else 0
    strat_peak = strat_cum.cummax()
    strat_dd = float(((strat_cum - strat_peak) / strat_peak).min())
    
    bh_cum = (1 + bh_ret).cumprod()
    bh_ann = float((bh_cum.iloc[-1] ** (252 / len(bh_ret))) - 1)
    bh_vol = float(bh_ret.std() * np.sqrt(252))
    bh_sharpe = bh_ann / bh_vol if bh_vol > 0 else 0
    bh_peak = bh_cum.cummax()
    bh_dd = float(((bh_cum - bh_peak) / bh_peak).min())
    
    print(f"\n{'Metric':<20} {'Regime Strategy':>18} {'B&H US500':>18}")
    print(f"{'Annual Return':<20} {strat_ann:>17.2%} {bh_ann:>17.2%}")
    print(f"{'Annual Volatility':<20} {strat_vol:>17.2%} {bh_vol:>17.2%}")
    print(f"{'Sharpe Ratio':<20} {strat_sharpe:>17.3f} {bh_sharpe:>17.3f}")
    print(f"{'Max Drawdown':<20} {strat_dd:>17.2%} {bh_dd:>17.2%}")
    print(f"{'Total Return':<20} {(strat_cum.iloc[-1]-1):>17.2%} {(bh_cum.iloc[-1]-1):>17.2%}")
    
    invested_days = int((strat_ret['regime'] != 'NORMAL').sum())
    cash_days = int((strat_ret['regime'] == 'NORMAL').sum())
    print(f"\nDays invested: {invested_days} ({invested_days/len(strat_ret)*100:.1f}%)")
    print(f"Days in cash:  {cash_days} ({cash_days/len(strat_ret)*100:.1f}%)")

    return {
        'strat_ann': strat_ann,
        'strat_vol': strat_vol,
        'strat_sharpe': strat_sharpe,
        'strat_dd': strat_dd,
        'bh_ann': bh_ann,
        'bh_vol': bh_vol,
        'bh_sharpe': bh_sharpe,
        'bh_dd': bh_dd,
        'invested_pct': invested_days / len(strat_ret) * 100,
        'total_days': int(len(strat_ret)),
        'start_date': str(strat_ret.index[0].date()),
        'end_date': str(strat_ret.index[-1].date()),
    }


if __name__ == "__main__":
    connect_mt5()
    
    print("\nFetching D1 data for all 14 symbols...")
    data = fetch_all_d1()
    
    print("\nComputing macro regimes...")
    regimes_df = compute_regimes(data)
    
    if len(regimes_df) == 0:
        print("ERROR: No regime data")
        mt5.shutdown()
        sys.exit(1)
    
    print("\nComputing asset returns by regime...")
    results = compute_asset_returns_by_regime(data, regimes_df)
    
    # Print summary table
    print("\n" + "="*60)
    print("ASSET PERFORMANCE BY REGIME (Annualized Return %)")
    print("="*60)
    
    print(f"{'Symbol':<12}", end="")
    for r in ['RISK_ON', 'RISK_OFF', 'STAGFLATION', 'NORMAL']:
        print(f"  {r:>15}", end="")
    print()
    
    for sym in SYMBOLS:
        if sym not in results:
            continue
        print(f"{sym:<12}", end="")
        for r in ['RISK_ON', 'RISK_OFF', 'STAGFLATION', 'NORMAL']:
            rd = results[sym][r]
            if rd['ann_return'] is None:
                print(f"  {'N/A':>15}", end="")
            else:
                print(f"  {rd['ann_return']*100:>14.2f}%", end="")
        print()
    
    print("\n" + "="*60)
    print("SHARPE RATIO BY REGIME")
    print("="*60)
    print(f"{'Symbol':<12}", end="")
    for r in ['RISK_ON', 'RISK_OFF', 'STAGFLATION', 'NORMAL']:
        print(f"  {r:>15}", end="")
    print()
    
    for sym in SYMBOLS:
        if sym not in results:
            continue
        print(f"{sym:<12}", end="")
        for r in ['RISK_ON', 'RISK_OFF', 'STAGFLATION', 'NORMAL']:
            rd = results[sym][r]
            if rd['sharpe'] is None:
                print(f"  {'N/A':>15}", end="")
            else:
                print(f"  {rd['sharpe']:>15.3f}", end="")
        print()
    
    # Transition analysis
    regime_transition_analysis(regimes_df)
    
    # Hypothesis tests
    h2_res, h2b_res = test_hypotheses(results, regimes_df, data)
    
    # Regime-filtered backtest
    bt_results = regime_filter_backtest(data, regimes_df)
    
    # Save regime data for report generation
    regimes_df.to_csv("regime_data.csv")
    
    if bt_results:
        with open("backtest_results.json", "w") as f:
            json.dump(bt_results, f, indent=2)
    
    with open("regime_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\nResults saved to regime_results.json, regime_data.csv, backtest_results.json")
    
    mt5.shutdown()
