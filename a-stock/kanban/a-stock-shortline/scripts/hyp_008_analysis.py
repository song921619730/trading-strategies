#!/usr/bin/env python3
"""
hyp_008 Analysis Script
Test sector/industry co-occurrence condition on top of gap-up + pullback pattern.
"""

import requests
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict
import csv
import math

CLICKHOUSE_URL = 'http://172.24.224.1:8123/'
CLICKHOUSE_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')
CLICKHOUSE_DB = 'tushare'

def query(sql, params=None):
    """Execute a ClickHouse query and return results as list of lists."""
    if params is None:
        params = {}
    params['database'] = CLICKHOUSE_DB
    try:
        r = requests.get(CLICKHOUSE_URL, auth=CLICKHOUSE_AUTH, params={'query': sql, 'database': CLICKHOUSE_DB}, timeout=300)
        if r.status_code != 200:
            print(f"ERROR: {r.status_code} - {r.text[:500]}")
            return []
        lines = r.text.strip().split('\n')
        if len(lines) == 1 and lines[0] == '':
            return []
        return [line.split('\t') for line in lines]
    except Exception as e:
        print(f"Exception: {e}")
        return []

def query_csv(sql):
    """Execute query with TSV output and parse."""
    rows = query(sql)
    return rows

def get_trade_cal(start_date='2020-01-01', end_date='2026-05-12'):
    """Get all trading days."""
    sql = f"""
    SELECT DISTINCT trade_date 
    FROM tushare_stock_daily 
    WHERE trade_date >= '{start_date}' AND trade_date <= '{end_date}'
    ORDER BY trade_date
    """
    rows = query(sql)
    return [r[0] for r in rows]

def get_main_board_stocks():
    """Get main board stock codes."""
    sql = """
    SELECT ts_code, industry 
    FROM tushare_stock_basic 
    WHERE market = '主板'
    """
    rows = query(sql)
    return rows  # [[ts_code, industry], ...]

def get_concept_mapping():
    """Get concept membership for all stocks.
    Returns: dict: concept_name -> set of ts_codes (stock codes)
    And: dict: ts_code -> list of concept names
    """
    sql = """
    SELECT DISTINCT con_code, name 
    FROM tushare_kpl_concept_cons
    """
    rows = query(sql)
    concept_to_stocks = defaultdict(set)
    stock_to_concepts = defaultdict(list)
    for r in rows:
        stock_code = r[0]
        concept_name = r[1]
        concept_to_stocks[concept_name].add(stock_code)
        stock_to_concepts[stock_code].append(concept_name)
    return concept_to_stocks, stock_to_concepts

def get_industry_mapping(main_board_stocks):
    """Build industry mapping from main board stocks.
    Returns: dict: industry -> list of ts_codes
    And: dict: ts_code -> industry
    """
    industry_to_stocks = defaultdict(set)
    stock_to_industry = {}
    for r in main_board_stocks:
        code = r[0]
        industry = r[1] if r[1] else ''
        if industry:
            industry_to_stocks[industry].add(code)
            stock_to_industry[code] = industry
    return industry_to_stocks, stock_to_industry

def get_gap_up_stocks(trade_date):
    """Get stocks with gap-up >2% on a given date."""
    sql = f"""
    SELECT ts_code, open, pre_close, low, high, close, vol, amount
    FROM tushare_stock_daily 
    WHERE trade_date = '{trade_date}'
      AND open >= pre_close * 1.02
      AND open IS NOT NULL AND pre_close IS NOT NULL
      AND low IS NOT NULL AND high IS NOT NULL
    """
    rows = query(sql)
    results = {}
    for r in rows:
        code = r[0]
        results[code] = {
            'open': float(r[1]),
            'pre_close': float(r[2]),
            'low': float(r[3]),
            'high': float(r[4]),
            'close': float(r[5]),
            'vol': float(r[6]),
            'amount': float(r[7]),
            'gap_pct': (float(r[1]) / float(r[2]) - 1) * 100
        }
    return results

def get_future_data(ts_code, trade_date, forward_days):
    """Get stock data for future dates up to forward_days after trade_date."""
    sql = f"""
    SELECT trade_date, open, high, low, close, vol
    FROM tushare_stock_daily 
    WHERE ts_code = '{ts_code}'
      AND trade_date > '{trade_date}'
    ORDER BY trade_date
    LIMIT {forward_days + 5}
    """
    rows = query(sql)
    return rows

def check_pullback_condition(gap_day_data, future_rows):
    """
    Check if the pullback condition is met:
    - In the next 1-3 trading days, all lows >= gap_day low
    - Volume is shrinking (non-increasing compared to gap day)
    Returns: (is_valid, exit_idx) where exit_idx is the last day of pullback (0-indexed in future_rows)
    """
    gap_low = gap_day_data['low']
    gap_vol = gap_day_data['vol']
    
    if len(future_rows) < 3:
        return False, -1
    
    # Check T+1, T+2, T+3
    for i in range(min(3, len(future_rows))):
        row_low = float(future_rows[i][3])
        row_vol = float(future_rows[i][5])
        row_close = float(future_rows[i][4])
        
        # Must not break the gap (low >= gap low)
        if row_low < gap_low * 0.995:  # Allow 0.5% tolerance
            return False, -1
    
    # Volume condition: at least one of the 3 days has lower volume than gap day
    # (缩量回调 - volume shrinking pullback)
    vol_condition = False
    for i in range(min(3, len(future_rows))):
        row_vol = float(future_rows[i][5])
        if row_vol < gap_vol * 0.95:  # At least 5% lower volume
            vol_condition = True
            break
    
    if not vol_condition:
        return False, -1
    
    # Return the exit index (last day of the 3-day window, or the last available)
    exit_idx = min(2, len(future_rows) - 1)
    return True, exit_idx

def compute_forward_returns(future_rows, start_idx, horizons):
    """
    Compute forward returns from start_idx.
    horizons: list of (name, days_from_start) e.g. [('5d', 5), ('10d', 10), ('20d', 20)]
    Returns dict of horizon_name -> return_pct
    """
    results = {}
    for h_name, h_days in horizons:
        target_idx = start_idx + h_days
        if target_idx < len(future_rows):
            entry_close = float(future_rows[start_idx][4])
            exit_close = float(future_rows[target_idx][4])
            ret = (exit_close / entry_close - 1) * 100
            results[h_name] = ret
        else:
            # Use last available close
            entry_close = float(future_rows[start_idx][4])
            exit_close = float(future_rows[-1][4])
            ret = (exit_close / entry_close - 1) * 100
            results[h_name] = ret
    return results

def compute_statistics(returns_list):
    """Compute win_rate, avg_return, profit_factor, total_trades, max_drawdown."""
    if not returns_list:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_return': 0,
            'profit_factor': 0,
            'max_drawdown': 0
        }
    
    total = len(returns_list)
    wins = [r for r in returns_list if r > 0]
    losses = [r for r in returns_list if r <= 0]
    
    win_rate = len(wins) / total * 100 if total > 0 else 0
    avg_return = sum(returns_list) / total if total > 0 else 0
    
    total_profit = sum(wins) if wins else 0
    total_loss = abs(sum(losses)) if losses else 1
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    
    # Max drawdown calculation
    cumulative = 0
    peak = 0
    max_dd = 0
    for r in returns_list:
        cumulative += r
        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / (peak if peak > 0 else 1) * 100
        if dd > max_dd:
            max_dd = dd
    
    return {
        'total_trades': total,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'profit_factor': profit_factor,
        'max_drawdown': max_dd
    }

def main():
    print("=" * 60)
    print("hyp_008 Analysis: Sector/Industry Co-occurrence Test")
    print("=" * 60)
    
    start_date = '2020-01-01'
    end_date = '2026-05-12'
    
    print(f"\n[Step 1] Getting main board stocks...")
    main_board = get_main_board_stocks()
    main_board_codes = set(r[0] for r in main_board)
    print(f"  Found {len(main_board_codes)} main board stocks")
    
    print(f"\n[Step 2] Getting concept mapping...")
    concept_to_stocks, stock_to_concepts = get_concept_mapping()
    print(f"  Found {len(concept_to_stocks)} concepts, {sum(len(v) for v in concept_to_stocks.values())} total memberships")
    
    print(f"\n[Step 3] Getting industry mapping...")
    industry_to_stocks, stock_to_industry = get_industry_mapping(main_board)
    print(f"  Found {len(industry_to_stocks)} industries")
    
    print(f"\n[Step 4] Getting trading days...")
    trade_dates = get_trade_cal(start_date, end_date)
    print(f"  Found {len(trade_dates)} trading days")
    
    # Statistics accumulators
    # Base model (no sector check)
    base_returns_all = []
    
    # Test A: Concept co-occurrence
    concept_returns_all = []
    
    # Test B: Industry co-occurrence
    industry_returns_all = []
    
    # Track which concept/industries had co-occurrence on each date
    concept_cooccurrence_dates = defaultdict(int)
    industry_cooccurrence_dates = defaultdict(int)
    
    total_processed = 0
    total_gap_signals = 0
    total_valid = 0
    
    horizons = [('5d', 5), ('10d', 10), ('20d', 20)]
    
    # For each trading day, check gap-ups and track
    print(f"\n[Step 5] Processing gap-up signals...")
    
    # Build a date-indexed look-ahead for faster processing
    # We'll process day by day and cache future data
    
    date_set = set(trade_dates)
    date_to_idx = {d: i for i, d in enumerate(trade_dates)}
    
    for day_idx, trade_date in enumerate(trade_dates):
        if day_idx % 50 == 0:
            print(f"  Processing date {day_idx}/{len(trade_dates)}: {trade_date}...")
        
        # Get gap-up stocks for this day
        gap_stocks = get_gap_up_stocks(trade_date)
        
        if not gap_stocks:
            continue
        
        # Filter to main board only
        gap_main = {code: data for code, data in gap_stocks.items() if code in main_board_codes}
        
        if not gap_main:
            continue
        
        total_gap_signals += len(gap_main)
        
        # Check which stocks have valid pullback
        valid_stocks = {}  # code -> future data
        for code, data in gap_main.items():
            # Get next 30 trading days of data
            future = get_future_data(code, trade_date, 25)
            if len(future) < 4:  # Need at least T+3 + 5 forward days
                continue
            
            is_valid, exit_idx = check_pullback_condition(data, future[:8])  # Check first 8 days for pullback
            if is_valid:
                valid_stocks[code] = {
                    'data': data,
                    'future': future,
                    'exit_idx': exit_idx
                }
        
        if not valid_stocks:
            continue
        
        total_valid += len(valid_stocks)
        
        # Base: just compute returns for all valid gap-up signals
        for code, info in valid_stocks.items():
            future = info['future']
            returns = compute_forward_returns(future, info['exit_idx'] + 1, horizons)
            base_returns_all.append(returns)
        
        # Test A: Check concept co-occurrence
        concept_gapups = defaultdict(list)  # concept_name -> list of stock codes
        for code in valid_stocks:
            if code in stock_to_concepts:
                for concept in stock_to_concepts[code]:
                    concept_gapups[concept].append(code)
        
        concept_cooccur_codes = set()
        for concept, codes in concept_gapups.items():
            if len(codes) >= 2:
                concept_cooccurrence_dates[concept] += 1
                concept_cooccur_codes.update(codes)
        
        # Compute returns for concept co-occurrence stocks
        for code in concept_cooccur_codes:
            if code in valid_stocks:
                info = valid_stocks[code]
                returns = compute_forward_returns(info['future'], info['exit_idx'] + 1, horizons)
                concept_returns_all.append(returns)
        
        # Test B: Check industry co-occurrence
        industry_gapups = defaultdict(list)  # industry -> list of stock codes
        for code in valid_stocks:
            if code in stock_to_industry:
                industry = stock_to_industry[code]
                industry_gapups[industry].append(code)
        
        industry_cooccur_codes = set()
        for industry, codes in industry_gapups.items():
            if len(codes) >= 2:
                industry_cooccurrence_dates[industry] += 1
                industry_cooccur_codes.update(codes)
        
        # Compute returns for industry co-occurrence stocks
        for code in industry_cooccur_codes:
            if code in valid_stocks:
                info = valid_stocks[code]
                returns = compute_forward_returns(info['future'], info['exit_idx'] + 1, horizons)
                industry_returns_all.append(returns)
    
    print(f"\n[Summary]")
    print(f"  Total gap-up signals (main board): {total_gap_signals}")
    print(f"  Valid pullback signals: {total_valid}")
    print(f"  Base trades: {len(base_returns_all)}")
    print(f"  Concept co-occurrence trades: {len(concept_returns_all)}")
    print(f"  Industry co-occurrence trades: {len(industry_returns_all)}")
    
    # Compute statistics for each horizon
    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    
    for h_name, h_days in horizons:
        print(f"\n--- Horizon: {h_name} ---")
        
        base_rets = [r[h_name] for r in base_returns_all]
        concept_rets = [r[h_name] for r in concept_returns_all]
        industry_rets = [r[h_name] for r in industry_returns_all]
        
        base_stats = compute_statistics(base_rets)
        concept_stats = compute_statistics(concept_rets)
        industry_stats = compute_statistics(industry_rets)
        
        print(f"  Base (no sector): WR={base_stats['win_rate']:.2f}% avg_ret={base_stats['avg_return']:.2f}% PF={base_stats['profit_factor']:.2f} trades={base_stats['total_trades']} maxDD={base_stats['max_drawdown']:.2f}%")
        print(f"  Concept co-occur: WR={concept_stats['win_rate']:.2f}% avg_ret={concept_stats['avg_return']:.2f}% PF={concept_stats['profit_factor']:.2f} trades={concept_stats['total_trades']} maxDD={concept_stats['max_drawdown']:.2f}%")
        print(f"  Industry co-occur: WR={industry_stats['win_rate']:.2f}% avg_ret={industry_stats['avg_return']:.2f}% PF={industry_stats['profit_factor']:.2f} trades={industry_stats['total_trades']} maxDD={industry_stats['max_drawdown']:.2f}%")
        
        # vs benchmark
        if concept_stats['total_trades'] > 0:
            wr_diff = concept_stats['win_rate'] - base_stats['win_rate']
            print(f"  Concept vs Base WR: {wr_diff:+.2f}%")
        if industry_stats['total_trades'] > 0:
            wr_diff = industry_stats['win_rate'] - base_stats['win_rate']
            print(f"  Industry vs Base WR: {wr_diff:+.2f}%")
    
    # Save results to JSON for report generation
    results = {
        'latest_trade_date': max(trade_dates),
        'data_range': f'{start_date} to {end_date}',
        'total_gap_signals': total_gap_signals,
        'total_valid_signals': total_valid,
        'horizons': {},
        'base': compute_statistics([r['20d'] for r in base_returns_all]) if base_returns_all else {},
        'concept_cooccurrence_counts': dict(concept_cooccurrence_dates),
        'industry_cooccurrence_counts': dict(industry_cooccurrence_dates),
    }
    
    for h_name, h_days in horizons:
        base_rets = [r[h_name] for r in base_returns_all]
        concept_rets = [r[h_name] for r in concept_returns_all]
        industry_rets = [r[h_name] for r in industry_returns_all]
        
        results['horizons'][h_name] = {
            'base': compute_statistics(base_rets),
            'concept': compute_statistics(concept_rets),
            'industry': compute_statistics(industry_rets),
        }
    
    with open('/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/a-stock-shortline/logs/hyp_008_raw_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nRaw results saved to hyp_008_raw_results.json")
    print("Done!")

if __name__ == '__main__':
    main()
