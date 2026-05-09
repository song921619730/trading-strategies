#!/usr/bin/env python3
"""
Reference Script: A-Stock Limit-Up Premium & Consecutive Board Analysis
Methodology:
1. Identify limit-up stocks daily (Close == Upper Limit Price)
2. Calculate consecutive limit-up streaks (连板高度)
3. Compute next-day premium rate (溢价率) = (Next_Day_High - Limit_Price) / Limit_Price
4. Analyze win rate by board count (1-board, 2-board, 3-board+)
5. Filter: Market Cap > 5B, Exclude ST/*ST, Volume > 1.5x 20-day avg
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

def load_data():
    # Placeholder: AI will load from Tushare/ClickHouse
    daily = pd.read_csv('../data/daily_quotes.csv', parse_dates=['trade_date'])
    limit_up = pd.read_csv('../data/limit_up_history.csv', parse_dates=['trade_date'])
    return daily, limit_up

def calculate_streaks(df):
    """Calculate consecutive limit-up streaks"""
    df = df.sort_values(['code', 'trade_date'])
    df['is_limit'] = (df['close'] >= df['upper_limit']).astype(int)
    
    # Group by stock and calculate streak
    df['streak'] = df.groupby('code')['is_limit'].apply(
        lambda x: x.groupby((x != x.shift()).cumsum()).cumsum()
    )
    df['prev_streak'] = df.groupby('code')['streak'].shift(1)
    return df

def calculate_premium(df):
    """Calculate next-day premium rate"""
    df['next_day_open'] = df.groupby('code')['open'].shift(-1)
    df['next_day_high'] = df.groupby('code')['high'].shift(-1)
    df['premium_rate'] = (df['next_day_high'] - df['close']) / df['close']
    df['next_day_return'] = (df['next_day_open'] - df['close']) / df['close']
    return df

def filter_quality(df):
    """Apply quality filters"""
    df = df[df['market_cap'] > 5_000_000_000]  # > 5B RMB
    df = df[~df['code'].str.contains('ST', na=False)]
    df = df[df['volume'] > (df['volume'].rolling(20).mean() * 1.5)]
    return df

def analyze_by_board(df):
    """Win rate analysis by consecutive boards"""
    results = []
    for board in [1, 2, 3, 4]:
        subset = df[df['prev_streak'] == board]
        if len(subset) == 0: continue
        
        win_rate = (subset['next_day_return'] > 0).mean()
        avg_premium = subset['premium_rate'].mean()
        max_drawdown = subset['next_day_return'].min()
        
        results.append({
            'board_count': board,
            'samples': len(subset),
            'win_rate': win_rate,
            'avg_premium': avg_premium,
            'max_dd': max_drawdown
        })
    return pd.DataFrame(results)

if __name__ == "__main__":
    print("=== A-Stock Limit-Up Premium Analysis ===")
    daily, limit_up = load_data()
    
    # Merge & Calculate
    df = daily.merge(limit_up, on=['code', 'trade_date'], how='inner')
    df = calculate_streaks(df)
    df = calculate_premium(df)
    df = filter_quality(df)
    
    # Analysis
    board_stats = analyze_by_board(df)
    print("\n📊 Win Rate by Board Count:")
    print(board_stats.to_string(index=False))
    
    # Key Insight Extraction
    best_board = board_stats.loc[board_stats['win_rate'].idxmax()]
    print(f"\n🏆 Best Setup: {int(best_board['board_count'])}-Board")
    print(f"   Win Rate: {best_board['win_rate']:.1%}")
    print(f"   Avg Premium: {best_board['avg_premium']:.2%}")
    print(f"   Sample Size: {int(best_board['samples'])}")
    
    # Risk Warning
    if best_board['max_dd'] < -0.08:
        print(f"⚠️ Risk: Max single-day DD = {best_board['max_dd']:.1%}. Tight SL required.")
    else:
        print("✅ Risk profile acceptable.")
