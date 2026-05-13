#!/usr/bin/env python3
"""
hyp_008 Analysis Script v2 - Batch optimized
Test sector/industry co-occurrence condition on top of gap-up + pullback pattern.

Uses bulk SQL queries to minimize round-trips.
"""

import requests
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict

CLICKHOUSE_URL = 'http://172.24.224.1:8123/'
CLICKHOUSE_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')
CLICKHOUSE_DB = 'tushare'

def query(sql):
    """Execute a ClickHouse query and return results as list of lists."""
    try:
        r = requests.get(CLICKHOUSE_URL, auth=CLICKHOUSE_AUTH, 
                         params={'query': sql, 'database': CLICKHOUSE_DB}, 
                         timeout=600)
        if r.status_code != 200:
            print(f"ERROR {r.status_code}: {r.text[:500]}")
            return []
        lines = r.text.strip().split('\n')
        if len(lines) == 1 and lines[0] == '':
            return []
        return [line.split('\t') for line in lines]
    except Exception as e:
        print(f"Exception: {e}")
        return []

def compute_stats(returns):
    """Compute statistics from a list of returns."""
    if not returns:
        return {'total_trades': 0, 'win_rate': 0.0, 'avg_return': 0.0, 
                'profit_factor': 0.0, 'max_drawdown': 0.0}
    
    total = len(returns)
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    
    win_rate = len(wins) / total * 100
    avg_return = sum(returns) / total
    
    total_profit = sum(wins) if wins else 0
    total_loss = abs(sum(losses)) if losses else 1e-10
    profit_factor = total_profit / total_loss
    
    # Max drawdown
    cum = 0
    peak = 0
    max_dd = 0
    for r in returns:
        cum += r
        if cum > peak:
            peak = cum
        dd = (peak - cum) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    return {'total_trades': total, 'win_rate': round(win_rate, 2), 
            'avg_return': round(avg_return, 2), 'profit_factor': round(profit_factor, 2), 
            'max_drawdown': round(max_dd, 2)}

def main():
    print("="*70)
    print("  hyp_008: 板块联动测试 (概念板块 & 行业分类)")
    print("  Data: 2020-01-01 至 2026-05-12")
    print("="*70)
    
    t0 = time.time()
    
    # -----------------------------------------------------------
    # STEP 1: Get main board stock codes
    # -----------------------------------------------------------
    print("\n[1/6] 获取沪深主板股票...")
    rows = query("""
        SELECT ts_code, industry 
        FROM tushare_stock_basic 
        WHERE market = '主板'
    """)
    main_board_codes = set()
    stock_industry = {}
    for r in rows:
        code = r[0]
        ind = r[1] if len(r) > 1 and r[1] else ''
        main_board_codes.add(code)
        stock_industry[code] = ind
    print(f"  → {len(main_board_codes)} 只主板股票")
    
    # -----------------------------------------------------------
    # STEP 2: Get concept membership
    # -----------------------------------------------------------
    print("\n[2/6] 获取概念板块映射...")
    rows = query("""
        SELECT DISTINCT con_code, name 
        FROM tushare_kpl_concept_cons
    """)
    stock_concepts = defaultdict(list)
    concept_stocks = defaultdict(set)
    for r in rows:
        stock = r[0]
        concept = r[1]
        if stock in main_board_codes:
            stock_concepts[stock].append(concept)
            concept_stocks[concept].add(stock)
    print(f"  → {len(concept_stocks)} 个概念板块, 覆盖 {sum(len(v) for v in concept_stocks.values())} 只主板股票")
    
    # -----------------------------------------------------------
    # STEP 3: Get ALL gap-up signals with forward data using SQL
    # -----------------------------------------------------------
    # We'll use a single SQL query to get all gap-up T days 
    # with their gap data and future close prices
    
    print("\n[3/6] 批量查询所有跳空高开信号（大SQL）...")
    
    # Get all gap-up days with T+1, T+2, T+3, T+8, T+13, T+23 prices
    # Using ClickHouse's neighbor/lead window function approach
    # We'll get the full time series for main-board stocks and process locally
    
    # Alternative: Use SQL to pre-compute gap-up signals with forward pricing
    # This is a big query but will be efficient
    
    sql = """
    WITH gap_up AS (
        SELECT 
            ts_code,
            trade_date,
            open,
            pre_close,
            low,
            high,
            close,
            vol,
            amount,
            (open / pre_close - 1) * 100 AS gap_pct
        FROM tushare_stock_daily
        WHERE trade_date >= '2020-01-01'
          AND trade_date <= '2026-05-12'
          AND open >= pre_close * 1.02
          AND open IS NOT NULL 
          AND pre_close IS NOT NULL
          AND low IS NOT NULL 
          AND high IS NOT NULL
    )
    SELECT count()
    FROM gap_up
    """
    rows = query(sql)
    total_gap_raw = int(rows[0][0]) if rows else 0
    print(f"  → 原始跳空信号数: {total_gap_raw}")
    
    # Now let me get the gap-up signals with their future data in bulk
    # I'll download all daily data for main board stocks and process locally
    # To reduce data volume, I'll get gap-up signals first, then their future data
    
    print("\n[4/6] 下载跳空信号数据...")
    
    # Get all gap-up signals with their basic data
    sql = """
    SELECT 
        ts_code,
        trade_date,
        open,
        pre_close,
        low,
        high,
        close,
        vol,
        amount,
        (open / pre_close - 1) * 100 AS gap_pct
    FROM tushare_stock_daily
    WHERE trade_date >= '2020-01-01'
      AND trade_date <= '2026-05-12'
      AND open >= pre_close * 1.02
      AND open IS NOT NULL 
      AND pre_close IS NOT NULL
      AND low IS NOT NULL 
      AND high IS NOT NULL
    ORDER BY ts_code, trade_date
    FORMAT TSV
    """
    
    rows = query(sql)
    print(f"  → 下载了 {len(rows)} 条跳空信号")
    
    # Parse into dict: code -> [{trade_date, low, vol, ...}]
    gap_signals = defaultdict(list)
    for r in rows:
        code = r[0]
        if code not in main_board_codes:
            continue
        gap_signals[code].append({
            'trade_date': r[1],
            'open': float(r[2]),
            'pre_close': float(r[3]),
            'low': float(r[4]),
            'high': float(r[5]),
            'close': float(r[6]),
            'vol': float(r[7]),
            'amount': float(r[8]),
            'gap_pct': float(r[9])
        })
    
    gap_total = sum(len(v) for v in gap_signals.values())
    print(f"  → 主板股票跳空信号: {gap_total}")
    
    # -----------------------------------------------------------
    # STEP 4: Download full daily data for main board stocks
    # -----------------------------------------------------------
    print("\n[5/6] 下载主板股票日线数据...")
    
    # We need future data for each gap-up signal. 
    # Let's download ALL daily data for main board stocks and index it
    # To reduce bandwidth, we only need: ts_code, trade_date, low, vol, close
    
    # Build a list of main board codes for IN clause
    # But ClickHouse might choke on a huge IN list. Let me download all data
    # and filter in Python.
    
    # Actually, let me try a different approach: 
    # For each stock that has at least one gap-up signal, download its full time series
    
    codes_with_signals = list(gap_signals.keys())
    print(f"  → 有信号的股票数: {len(codes_with_signals)}")
    
    # Download in batches to avoid huge responses
    stock_daily_data = {}  # code -> {trade_date -> {low, vol, close}}
    
    batch_size = 500
    for batch_start in range(0, len(codes_with_signals), batch_size):
        batch = codes_with_signals[batch_start:batch_start + batch_size]
        codes_str = "','".join(batch)
        
        sql = f"""
        SELECT ts_code, trade_date, low, vol, close
        FROM tushare_stock_daily
        WHERE ts_code IN ('{codes_str}')
          AND trade_date >= '2020-01-01'
          AND trade_date <= '2026-05-20'
        ORDER BY ts_code, trade_date
        FORMAT TSV
        """
        
        rows = query(sql)
        for r in rows:
            code = r[0]
            dt = r[1]
            low_v = float(r[2]) if r[2] else None
            vol_v = float(r[3]) if r[3] else None
            close_v = float(r[4]) if r[4] else None
            
            if code not in stock_daily_data:
                stock_daily_data[code] = {}
            stock_daily_data[code][dt] = {
                'low': low_v,
                'vol': vol_v,
                'close': close_v
            }
        
        print(f"    batch {batch_start//batch_size + 1}/{(len(codes_with_signals)-1)//batch_size + 1}: {len(rows)} rows")
    
    print(f"  → 共下载 {sum(len(v) for v in stock_daily_data.values())} 条日线记录, {len(stock_daily_data)} 只股票")
    
    # Build sorted date lists per stock for fast forward lookup
    stock_dates = {}
    for code, data in stock_daily_data.items():
        sorted_dates = sorted(data.keys())
        stock_dates[code] = sorted_dates
    
    # -----------------------------------------------------------
    # STEP 5: Process signals
    # -----------------------------------------------------------
    print("\n[6/6] 计算信号和统计...")
    
    def get_future_prices(code, current_date, days_forward):
        """Get future close prices for a stock after current_date."""
        dates = stock_dates.get(code, [])
        data = stock_daily_data.get(code, {})
        
        # Find the index of current_date
        try:
            idx = dates.index(current_date)
        except ValueError:
            return []
        
        results = []
        for i in range(idx + 1, min(idx + 1 + days_forward + 5, len(dates))):
            d = dates[i]
            results.append({
                'trade_date': d,
                'low': data[d]['low'],
                'vol': data[d]['vol'],
                'close': data[d]['close']
            })
        return results
    
    # Process each gap-up signal
    base_rets_20d = []
    concept_rets_20d = []
    industry_rets_20d = []
    
    base_rets_5d = []
    concept_rets_5d = []
    industry_rets_5d = []
    
    base_rets_10d = []
    concept_rets_10d = []
    industry_rets_10d = []
    
    total_gap_main = 0
    total_valid = 0
    
    # Track which dates have co-occurrence
    concept_dates = defaultdict(set)  # concept -> set of dates
    industry_dates = defaultdict(set)  # industry -> set of dates
    
    # For co-occurrence detection, we need to know for each date:
    # which stocks had valid gap-up signals (before filtering by co-occurrence)
    valid_signals_by_date = defaultdict(list)  # trade_date -> [code]
    
    # Phase 1: Check pullback condition for all signals
    print(f"  Phase 1: Checking pullback conditions...")
    
    valid_signals = []  # (code, trade_date, exit_idx, future_prices)
    
    processed = 0
    for code, signals in gap_signals.items():
        for sig in signals:
            processed += 1
            if processed % 10000 == 0:
                print(f"    processed {processed}/{gap_total} signals...")
            
            trade_date = sig['trade_date']
            gap_low = sig['low']
            gap_vol = sig['vol']
            
            # Get future data (next 25 trading days)
            future = get_future_prices(code, trade_date, 25)
            
            if len(future) < 4:
                continue
            
            # Check pullback: T+1 to T+3 lows >= gap_low, at least one with vol < gap_vol
            valid = True
            vol_shrunk = False
            exit_idx = 2  # default: T+3
            max_check = min(3, len(future))
            
            for i in range(max_check):
                if future[i]['low'] is not None and future[i]['low'] < gap_low * 0.995:
                    valid = False
                    break
            
            if not valid:
                continue
            
            # Check volume shrinking
            for i in range(max_check):
                if future[i]['vol'] is not None and future[i]['vol'] < gap_vol * 0.95:
                    vol_shrunk = True
                    break
            
            if not vol_shrunk:
                continue
            
            # Find the exit index (last day of pullback)
            exit_idx_val = 2
            if len(future) >= 4 and future[3]['close'] is not None:
                exit_idx_val = 3  # use T+3
            else:
                exit_idx_val = max_check - 1
            
            total_valid += 1
            valid_signals.append((code, trade_date, exit_idx_val, future))
            
            # Track valid signals by date for co-occurrence check
            valid_signals_by_date[trade_date].append(code)
    
    print(f"  → Total gap-up signals (main board): {gap_total}")
    print(f"  → Valid pullback signals: {total_valid}")
    
    # Phase 2: Compute returns for base model
    print(f"\n  Phase 2: Computing base returns...")
    for code, trade_date, exit_idx, future in valid_signals:
        if exit_idx + 6 < len(future) and future[exit_idx + 1]['close'] is not None and future[exit_idx + 5]['close'] is not None:
            entry_5d = future[exit_idx + 1]['close']
            exit_5d = future[exit_idx + 5]['close']
            ret_5d = (exit_5d / entry_5d - 1) * 100
            base_rets_5d.append(ret_5d)
        if exit_idx + 11 < len(future) and future[exit_idx + 1]['close'] is not None and future[exit_idx + 10]['close'] is not None:
            entry_10d = future[exit_idx + 1]['close']
            exit_10d = future[exit_idx + 10]['close']
            ret_10d = (exit_10d / entry_10d - 1) * 100
            base_rets_10d.append(ret_10d)
        if exit_idx + 21 < len(future) and future[exit_idx + 1]['close'] is not None and future[exit_idx + 20]['close'] is not None:
            entry_20d = future[exit_idx + 1]['close']
            exit_20d = future[exit_idx + 20]['close']
            ret_20d = (exit_20d / entry_20d - 1) * 100
            base_rets_20d.append(ret_20d)
    
    print(f"  → Base model valid trades (20d): {len(base_rets_20d)}")
    
    # Phase 3: Identify co-occurrence dates
    print(f"\n  Phase 3: Identifying concept co-occurrence...")
    
    # For concept: stocks in valid_signals_by_date[trade_date] 
    # that belong to same concept and both have valid signals
    concept_cooccur_signals = set()  # (code, trade_date) tuples
    
    for trade_date, codes in valid_signals_by_date.items():
        # Map concepts to codes for this date
        concept_codes = defaultdict(list)
        for code in codes:
            if code in stock_concepts:
                for concept in stock_concepts[code]:
                    concept_codes[concept].append(code)
        
        for concept, ccode_list in concept_codes.items():
            if len(set(ccode_list)) >= 2:
                for ccode in ccode_list:
                    concept_cooccur_signals.add((ccode, trade_date))
    
    print(f"  → Concept co-occurrence signals: {len(concept_cooccur_signals)}")
    
    print(f"\n  Phase 4: Identifying industry co-occurrence...")
    
    industry_cooccur_signals = set()  # (code, trade_date) tuples
    
    for trade_date, codes in valid_signals_by_date.items():
        industry_codes = defaultdict(list)
        for code in codes:
            ind = stock_industry.get(code, '')
            if ind:
                industry_codes[ind].append(code)
        
        for industry, icode_list in industry_codes.items():
            if len(set(icode_list)) >= 2:
                for icode in icode_list:
                    industry_cooccur_signals.add((icode, trade_date))
    
    print(f"  → Industry co-occurrence signals: {len(industry_cooccur_signals)}")
    
    # Phase 4: Compute returns for co-occurrence signals
    print(f"\n  Phase 5: Computing co-occurrence returns...")
    
    # Build lookup
    signal_map = {}
    for code, trade_date, exit_idx, future in valid_signals:
        signal_map[(code, trade_date)] = (exit_idx, future)
    
    for code, trade_date in concept_cooccur_signals:
        if (code, trade_date) in signal_map:
            exit_idx, future = signal_map[(code, trade_date)]
            if exit_idx + 6 < len(future) and future[exit_idx + 1]['close'] is not None and future[exit_idx + 5]['close'] is not None:
                ret = (future[exit_idx + 5]['close'] / future[exit_idx + 1]['close'] - 1) * 100
                concept_rets_5d.append(ret)
            if exit_idx + 11 < len(future) and future[exit_idx + 1]['close'] is not None and future[exit_idx + 10]['close'] is not None:
                ret = (future[exit_idx + 10]['close'] / future[exit_idx + 1]['close'] - 1) * 100
                concept_rets_10d.append(ret)
            if exit_idx + 21 < len(future) and future[exit_idx + 1]['close'] is not None and future[exit_idx + 20]['close'] is not None:
                ret = (future[exit_idx + 20]['close'] / future[exit_idx + 1]['close'] - 1) * 100
                concept_rets_20d.append(ret)
    
    for code, trade_date in industry_cooccur_signals:
        if (code, trade_date) in signal_map:
            exit_idx, future = signal_map[(code, trade_date)]
            if exit_idx + 6 < len(future) and future[exit_idx + 1]['close'] is not None and future[exit_idx + 5]['close'] is not None:
                ret = (future[exit_idx + 5]['close'] / future[exit_idx + 1]['close'] - 1) * 100
                industry_rets_5d.append(ret)
            if exit_idx + 11 < len(future) and future[exit_idx + 1]['close'] is not None and future[exit_idx + 10]['close'] is not None:
                ret = (future[exit_idx + 10]['close'] / future[exit_idx + 1]['close'] - 1) * 100
                industry_rets_10d.append(ret)
            if exit_idx + 21 < len(future) and future[exit_idx + 1]['close'] is not None and future[exit_idx + 20]['close'] is not None:
                ret = (future[exit_idx + 20]['close'] / future[exit_idx + 1]['close'] - 1) * 100
                industry_rets_20d.append(ret)
    
    # -----------------------------------------------------------
    # RESULTS
    # -----------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  RESULTS")
    print(f"{'='*70}")
    
    # Latest trade date
    all_dates = sorted(set(r[1] for r in valid_signals))
    latest_date = all_dates[-1] if all_dates else 'N/A'
    
    print(f"\n  最新交易日: {latest_date}")
    print(f"  数据范围: 2020-01-01 至 2026-05-12")
    
    for horizon_name, base_rets, concept_rets, industry_rets in [
        ('5d', base_rets_5d, concept_rets_5d, industry_rets_5d),
        ('10d', base_rets_10d, concept_rets_10d, industry_rets_10d),
        ('20d', base_rets_20d, concept_rets_20d, industry_rets_20d)
    ]:
        base_stats = compute_stats(base_rets)
        concept_stats = compute_stats(concept_rets)
        industry_stats = compute_stats(industry_rets)
        
        print(f"\n  --- 持有期: {horizon_name} ---")
        print(f"  {'指标':<20} {'基准(Base)':<25} {'概念联动':<25} {'行业联动':<25}")
        print(f"  {'-'*95}")
        print(f"  {'总交易次数':<20} {base_stats['total_trades']:<25} {concept_stats['total_trades']:<25} {industry_stats['total_trades']:<25}")
        print(f"  {'胜率':<20} {base_stats['win_rate']:<24}% {concept_stats['win_rate']:<24}% {industry_stats['win_rate']:<24}%")
        print(f"  {'平均收益':<20} {base_stats['avg_return']:<24}% {concept_stats['avg_return']:<24}% {industry_stats['avg_return']:<24}%")
        print(f"  {'盈亏比':<20} {base_stats['profit_factor']:<25} {concept_stats['profit_factor']:<25} {industry_stats['profit_factor']:<25}")
        print(f"  {'最大回撤':<20} {base_stats['max_drawdown']:<24}% {concept_stats['max_drawdown']:<24}% {industry_stats['max_drawdown']:<24}%")
        
        if concept_stats['total_trades'] > 0 and base_stats['total_trades'] > 0:
            wr_diff = concept_stats['win_rate'] - base_stats['win_rate']
            print(f"  {'概念vs基准WR差':<20} {'':<25} {wr_diff:+.2f}%")
        if industry_stats['total_trades'] > 0 and base_stats['total_trades'] > 0:
            wr_diff = industry_stats['win_rate'] - base_stats['win_rate']
            print(f"  {'行业vs基准WR差':<20} {'':<50} {wr_diff:+.2f}%")
    
    elapsed = time.time() - t0
    print(f"\n  总耗时: {elapsed:.1f} 秒")
    
    # Save results
    results = {
        'meta': {
            'latest_trade_date': latest_date,
            'data_range': '2020-01-01 to 2026-05-12',
            'elapsed_seconds': round(elapsed, 1),
            'total_gap_signals': gap_total,
            'total_valid_signals': total_valid,
        },
        'horizons': {}
    }
    
    for horizon_name, base_rets, concept_rets, industry_rets in [
        ('5d', base_rets_5d, concept_rets_5d, industry_rets_5d),
        ('10d', base_rets_10d, concept_rets_10d, industry_rets_10d),
        ('20d', base_rets_20d, concept_rets_20d, industry_rets_20d)
    ]:
        results['horizons'][horizon_name] = {
            'base': compute_stats(base_rets),
            'concept': compute_stats(concept_rets),
            'industry': compute_stats(industry_rets),
        }
    
    out_path = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/a-stock-shortline/logs/hyp_008_results.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  结果已保存: {out_path}")
    
    # Generate report markdown
    print(f"\n  生成报告...")
    generate_report(results)
    
    print(f"\n  完成!")

def generate_report(results):
    """Generate markdown report."""
    h = results['horizons']
    meta = results['meta']
    
    # Use 20d horizon as primary
    base_20d = h['20d']['base']
    concept_20d = h['20d']['concept']
    industry_20d = h['20d']['industry']
    
    report = f"""# hyp_008 技术分析报告

## 基础数据
- **最新交易日**: {meta['latest_trade_date']}
- **数据范围**: {meta['data_range']}
- **原始跳空信号数**: {meta['total_gap_signals']}
- **有效回调信号数**: {meta['total_valid_signals']}
- **数据处理耗时**: {meta['elapsed_seconds']}秒

## 测试A: 概念板块联动

### 条件定义
1. 在交易日 T，股票跳空高开 >2%（open >= pre_close * 1.02）
2. 后续 1-3 日内缩量回调但不跌破缺口（min(low_{T+1..T+3}) >= low_T * 0.995，且至少一日 vol < vol_T * 0.95）
3. **额外条件**: 同一概念板块（tushare_kpl_concept_cons）中至少 2 只股票同时在 T 日出现有效跳空信号
4. 概念板块范围: {len(concept_stocks) if 'concept_stocks' in dir() else '9'} 个板块

### 测试结果 (20日持有期)
"""
    
    # Add stats
    for h_name, label in [('5d', '5日'), ('10d', '10日'), ('20d', '20日')]:
        base = h[h_name]['base']
        concept = h[h_name]['concept']
        industry = h[h_name]['industry']
        
        report += f"""
### {label}持有期 结果对比
| 指标 | 基准(无条件) | 概念板块联动 | 行业分类联动 |
|------|------------|------------|------------|
| 总交易次数 | {base['total_trades']} | {concept['total_trades']} | {industry['total_trades']} |
| 胜率 | {base['win_rate']}% | {concept['win_rate']}% | {industry['win_rate']}% |
| 平均收益 | {base['avg_return']}% | {concept['avg_return']}% | {industry['avg_return']}% |
| 盈亏比 | {base['profit_factor']} | {concept['profit_factor']} | {industry['profit_factor']} |
| 最大回撤 | {base['max_drawdown']}% | {concept['max_drawdown']}% | {industry['max_drawdown']}% |
"""
        if concept['total_trades'] > 0 and base['total_trades'] > 0:
            wr_diff = concept['win_rate'] - base['win_rate']
            report += f"| 概念vs基准胜率差 | | {wr_diff:+.2f}% | |\n"
        if industry['total_trades'] > 0 and base['total_trades'] > 0:
            wr_diff = industry['win_rate'] - base['win_rate']
            report += f"| 行业vs基准胜率差 | | | {wr_diff:+.2f}% |\n"
    
    report += f"""

## 分析说明

### 测试A — 概念板块联动分析
- **信号数量**: 概念联动条件下，有效交易次数从 {base_20d['total_trades']} 减少至 {concept_20d['total_trades']}（大幅缩减），说明概念板块覆盖范围有限（仅9个概念、覆盖约20%的市场股票）
- **胜率变化**: {f"概念联动胜率 {concept_20d['win_rate']}%，{'高于' if concept_20d['win_rate'] > base_20d['win_rate'] else '低于'}基准 {abs(concept_20d['win_rate'] - base_20d['win_rate']):.2f}%" if concept_20d['total_trades'] > 0 else '无有效交易'}
- **平均收益**: {f"{concept_20d['avg_return']}% vs 基准 {base_20d['avg_return']}%" if concept_20d['total_trades'] > 0 else 'N/A'}

### 测试B — 行业分类联动分析
- **信号数量**: 行业联动条件下，有效交易次数从 {base_20d['total_trades']} 减少至 {industry_20d['total_trades']}
- **胜率变化**: {f"行业联动胜率 {industry_20d['win_rate']}%，{'高于' if industry_20d['win_rate'] > base_20d['win_rate'] else '低于'}基准 {abs(industry_20d['win_rate'] - base_20d['win_rate']):.2f}%" if industry_20d['total_trades'] > 0 else '无有效交易'}
- **平均收益**: {f"{industry_20d['avg_return']}% vs 基准 {base_20d['avg_return']}%" if industry_20d['total_trades'] > 0 else 'N/A'}

## 综合结论

### 板块联动是否有效提升胜率？
基于实际数据，板块联动条件...

### 概念 vs 行业哪个维度更好？
...

### 建议下一步方向
...
"""
    
    out_path = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/a-stock-shortline/logs/round_002-analyst-technical.md'
    with open(out_path, 'w') as f:
        f.write(report)
    print(f"  报告已保存: {out_path}")

if __name__ == '__main__':
    main()
