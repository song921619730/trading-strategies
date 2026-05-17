#!/usr/bin/env python3
"""
Iter24 T7: Cross-market linkage backtest.
Tests 5 parameter combinations for cross-market strategy mining.
"""
import json
import urllib.request
import urllib.parse
import sys
from datetime import datetime, date

CLICKHOUSE_URL = "http://172.24.224.1:8123"
CLICKHOUSE_USER = "ai_reader"
CLICKHOUSE_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
BASE_DATE = "2026-05-12"

def ch_query(sql):
    """Execute SQL against ClickHouse via HTTP API."""
    url = f"{CLICKHOUSE_URL}/?query={urllib.parse.quote(sql)}&default_format=JSON"
    req = urllib.request.Request(url)
    import base64
    creds = base64.b64encode(f"{CLICKHOUSE_USER}:{CLICKHOUSE_PASS}".encode()).decode()
    req.add_header("Authorization", f"Basic {creds}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data.get('data', [])
    except Exception as e:
        print(f"  [ERROR] Query failed: {e}", file=sys.stderr)
        print(f"  SQL: {sql[:200]}...", file=sys.stderr)
        return None

def build_signal_query(combo):
    """
    Build the signal detection query.
    Returns: list of {ts_code, trade_date, close, ...}
    """
    where_clauses = [
        "s.ts_code NOT LIKE '30%'",
        "s.ts_code NOT LIKE '688%'",
        "s.ts_code NOT LIKE '920%'",
        "s.ts_code NOT LIKE '%ST%'",
    ]
    joins = []
    
    # Base table: stock_daily
    from_clause = "(SELECT * FROM tushare.tushare_stock_daily FINAL) AS s"
    
    # Price/volume filters
    if 'pct_chg_min' in combo:
        where_clauses.append(f"s.pct_chg >= {combo['pct_chg_min']}")
    if 'pct_chg_max' in combo:
        where_clauses.append(f"s.pct_chg <= {combo['pct_chg_max']}")
    
    # Yesterday's conditions
    if 'prev_pct_chg_max' in combo:
        # Join yesterday's data
        joins.append("""
        LEFT JOIN (SELECT ts_code, trade_date, pct_chg 
                   FROM (SELECT *, row_number() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn 
                         FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)) 
                   WHERE rn = 2) AS py 
          ON s.ts_code = py.ts_code AND s.trade_date > py.trade_date
        """)
        # Actually this needs a proper approach. Let me use a LAG approach.
    
    # For simplicity, use subquery approach for previous day conditions
    # Let me rewrite this properly
    
    return from_clause, joins, where_clauses

def backtest_combo(combo, combo_name):
    """Run complete backtest for one parameter combination."""
    print(f"\n{'='*60}")
    print(f"Testing: {combo_name}")
    print(f"Params: {json.dumps(combo, ensure_ascii=False)}")
    print('='*60)
    
    # Build the signal query step by step
    # Step 1: Get stock_daily with index_global cross-market data
    
    # Because SPX data may lag by 1 day, we use trade_date join carefully
    # SPX max date is 2026-05-11, so for signal date 2026-05-12 we use SPX data from 2026-05-11 (previous trading day)
    
    # Also need to handle the fact that SPX trades on different calendar (US market dates)
    # Join by finding the most recent index data <= stock trade_date
    
    # Let me use a simpler approach: pre-compute SPX changes in Python from index_global, 
    # then combine with stock data in a query
    
    # Actually, let me use ClickHouse's ANY LEFT JOIN for this
    # Or use a subquery approach
    
    # For each combo, I'll write a tailored SQL
    
    # Common stock filters
    stock_filter = "s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'"
    
    # Base fields we need
    select_base = """
        s.ts_code, s.trade_date, s.close AS close_0, 
        s.pct_chg AS pct_chg_0, s.volume_ratio AS vr_0,
        s.amplitude AS amp_0, s.turnover_rate AS tr_0
    """
    
    # Build combo-specific SQL
    clauses = []
    
    # Price/volume conditions
    # Yesterday's panic (need yesterday's pct_chg)
    if 'prev_pct_chg' in combo:
        clauses.append(f"py.pct_chg <= {combo['prev_pct_chg']}")
    
    # Today's conditions
    if 'cur_pct_chg_min' in combo:
        clauses.append(f"s.pct_chg >= {combo['cur_pct_chg_min']}")
    if 'cur_pct_chg_max' in combo:
        clauses.append(f"s.pct_chg <= {combo['cur_pct_chg_max']}")
    if 'amplitude_min' in combo:
        clauses.append(f"s.amplitude >= {combo['amplitude_min']}")
    if 'vr_min' in combo:
        clauses.append(f"s.volume_ratio >= {combo['vr_min']}")
    if 'vr_max' in combo:
        clauses.append(f"s.volume_ratio <= {combo['vr_max']}")
    if 'tr_min' in combo:
        clauses.append(f"s.turnover_rate >= {combo['tr_min']}")
    if 'tr_max' in combo:
        clauses.append(f"s.turnover_rate <= {combo['tr_max']}")
    
    # Position condition (bottom 20% of 60-day range)
    if 'bottom_60d' in combo:
        pct = combo['bottom_60d']  # e.g., 0.20 for bottom 20%
        clauses.append(f"(s.close <= s.low + (s.high - s.low) * {pct})")
        # Actually this is wrong - we need 60-day min/max, not daily
        # Let me fix this: close_position needs window function
        # Use a different approach
    
    # Market cap
    if 'circ_mv_max' in combo:
        cm_val = combo['circ_mv_max']  # in 亿
        clauses.append(f"db.circ_mv <= {cm_val * 10000}")  # circ_mv is in 万元
    
    # Cross-market conditions
    spx_cross_join = ""
    if 'spx_prev_pct_chg_min' in combo:
        spx_cross_join = f"""
        CROSS JOIN (
            SELECT ig.trade_date AS spx_date, ig.pct_chg AS spx_pct_chg
            FROM (SELECT * FROM tushare.tushare_index_global FINAL) ig
            WHERE ig.ts_code = 'SPX'
        ) spx
        """
        # This won't work properly without date alignment
        # Need proper approach
    
    # Let me redesign this completely...
    # The proper approach: 
    # 1. First get the raw signal data from stock_daily + index_global
    # 2. Then compute forward returns in a separate step
    
    return None


# Redesigned simpler approach: use two-stage query
# Stage 1: Get candidate dates + stocks with cross-market conditions
# Stage 2: Compute forward returns

def run_combo_2stage(combo, combo_name):
    """
    Two-stage backtest:
    Stage 1: Find signal stocks with index filtered conditions
    Stage 2: Compute forward returns for those signals
    """
    print(f"\n{'='*60}")
    print(f"Testing: {combo_name}")
    print(f"Params: {json.dumps(combo, ensure_ascii=False)}")
    print('='*60)
    
    # Stage 1: Get all stock_daily + cross-market data
    # Strategy: Load index_global data once, then use it for filtering
    
    # First, get all SPX/HSI/N225/KS11 data
    index_codes = ['SPX', 'HSI', 'N225', 'KS11']
    index_data = {}
    
    for ic in index_codes:
        sql = f"""
        SELECT trade_date, pct_chg, close 
        FROM (SELECT * FROM tushare.tushare_index_global FINAL) 
        WHERE ts_code = '{ic}' 
          AND trade_date >= toDate('2020-01-01')
        ORDER BY trade_date
        """
        rows = ch_query(sql)
        if rows:
            index_data[ic] = rows
            print(f"  Loaded {len(rows)} rows for {ic}, range: {rows[0]['trade_date']} to {rows[-1]['trade_date']}")
        else:
            print(f"  WARNING: No data for {ic}")
            return None
    
    # Also get northbound flow data if needed
    if 'north_flow' in combo:
        sql = """
        SELECT trade_date, north_money 
        FROM (SELECT * FROM tushare.tushare_moneyflow_hsgt FINAL)
        WHERE trade_date >= toDate('2020-01-01')
        ORDER BY trade_date
        """
        nb = ch_query(sql)
        if nb:
            print(f"  Loaded {len(nb)} northbound flow rows")
            index_data['NORTH'] = nb
    
    # Build index lookup: for each stock trade_date, find the most recent index date <= stock date
    # SPX trades on US calendar, so stock trade_date D matches SPX trade_date D-1 most of the time
    # For simplicity, we'll join on trade_date directly
    
    # Build a dict for fast index lookup: {trade_date: pct_chg}
    def build_date_pct_dict(rows):
        return {r['trade_date']: r['pct_chg'] for r in rows}
    
    spx_dict = build_date_pct_dict(index_data.get('SPX', []))
    hsi_dict = build_date_pct_dict(index_data.get('HSI', []))
    n225_dict = build_date_pct_dict(index_data.get('N225', []))
    ks11_dict = build_date_pct_dict(index_data.get('KS11', []))
    
    # For multi-day SPX, precompute rolling sums
    spx_rolling_3d = {}
    if 'spx_3d_sum' in combo:
        spx_rows = index_data.get('SPX', [])
        for i, r in enumerate(spx_rows):
            if i >= 2:
                total = r['pct_chg'] + spx_rows[i-1]['pct_chg'] + spx_rows[i-2]['pct_chg']
                spx_rolling_3d[r['trade_date']] = total
            else:
                spx_rolling_3d[r['trade_date']] = None
    
    # For KS11 big move detection, precompute
    ks11_prev_dict = {}
    ks11_rows = index_data.get('KS11', [])
    for i, r in enumerate(ks11_rows):
        if i > 0:
            ks11_prev_dict[r['trade_date']] = r['pct_chg']
        else:
            ks11_prev_dict[r['trade_date']] = None
    
    # Stage 2: Scan stock_daily for signals
    # Process in chunks by date to manage memory
    # First get all trading dates we need
    date_sql = """
    SELECT DISTINCT trade_date 
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) 
    WHERE trade_date >= toDate('2020-01-01')
      AND trade_date <= toDate('2026-05-12')
    ORDER BY trade_date
    """
    all_dates = ch_query(date_sql)
    if not all_dates:
        print("  ERROR: Cannot get trading dates")
        return None
    
    trade_dates = [d['trade_date'] for d in all_dates]
    print(f"  Scanning {len(trade_dates)} trading dates...")
    
    # Build a date index for future return lookup
    date_index = {d: i for i, d in enumerate(trade_dates)}
    
    all_signals = []
    
    # Process dates in batches (every 100 dates) to manage API calls
    batch_size = 100
    for batch_start in range(0, len(trade_dates), batch_size):
        batch_end = min(batch_start + batch_size, len(trade_dates))
        batch_dates = trade_dates[batch_start:batch_end]
        
        # Build SQL for this batch
        stock_filter = "s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'"
        conditions = [stock_filter]
        
        # Get stocks for all dates in batch
        # We need: ts_code, trade_date, close, pct_chg, volume_ratio, amplitude
        # Also join with daily_basic for circ_mv
        
        join_daily_basic = ""
        if 'circ_mv_max' in combo:
            join_daily_basic = """
            INNER JOIN (SELECT ts_code, trade_date, circ_mv 
                       FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)) db
              ON s.ts_code = db.ts_code AND s.trade_date = db.trade_date
            """
            conditions.append(f"db.circ_mv <= {combo['circ_mv_max'] * 10000}")
        
        # Previous day condition - use self-join with lag
        prev_join = ""
        if 'prev_pct_chg_max' in combo:
            # Use window function to get previous day
            prev_join = """
            INNER JOIN (
                SELECT ts_code, trade_date, pct_chg 
                FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
            ) py ON s.ts_code = py.ts_code
            """
            # This still needs date matching - let me use a different approach
        
        date_strs = ', '.join([f"toDate('{d}')" for d in batch_dates])
        conditions.append(f"s.trade_date IN ({date_strs})")
        
        where_clause = ' AND '.join(conditions)
        
        # For previous day condition, use LAG approach in subquery
        if 'prev_pct_chg_max' in combo:
            # Use a CTE or subquery with window function
            sql = f"""
            WITH stock_with_prev AS (
                SELECT 
                    ts_code, trade_date, close, pct_chg, volume_ratio, amplitude, turnover_rate,
                    LAG(pct_chg) OVER (PARTITION BY ts_code ORDER BY trade_date) AS prev_pct_chg
                FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
            )
            SELECT s.ts_code, s.trade_date, s.close AS close_0, s.pct_chg AS pct_chg_0,
                   s.volume_ratio AS vr_0, s.amplitude AS amp_0, s.turnover_rate AS tr_0,
                   s.prev_pct_chg
            FROM stock_with_prev s
            {join_daily_basic}
            WHERE {where_clause}
              AND s.prev_pct_chg <= {combo['prev_pct_chg_max']}
            """
        else:
            sql = f"""
            SELECT s.ts_code, s.trade_date, s.close AS close_0, s.pct_chg AS pct_chg_0,
                   s.volume_ratio AS vr_0, s.amplitude AS amp_0, s.turnover_rate AS tr_0
            FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) s
            {join_daily_basic}
            WHERE {where_clause}
            """
        
        rows = ch_query(sql)
        if rows is None:
            print(f"  ERROR on batch {batch_start}-{batch_end}")
            continue
        if rows:
            all_signals.extend(rows)
            print(f"  Batch {batch_start}-{batch_end}: found {len(rows)} signals")
    
    print(f"\n  Total raw signals: {len(all_signals)}")
    
    if len(all_signals) < 50:
        print("  WARNING: Too few signals, try relaxing conditions")
        return {
            'name': combo_name,
            'N': len(all_signals),
            'WR_5d': 0,
            'WR_10d': 0,
            'WR_20d': 0,
            'ret_5d': 0,
            'ret_10d': 0,
            'ret_20d': 0,
            'sharpe_5d': 0,
            'sharpe_10d': 0,
            'sharpe_20d': 0,
            'params': combo,
            'status': 'INSUFFICIENT_SIGNALS'
        }
    
    # Stage 3: Compute forward returns
    # For each signal, find the close N days later
    # Use LAG approach but forward-looking
    
    # Get all needed stock data for future dates
    signal_keys = {(s['ts_code'], s['trade_date']) for s in all_signals}
    
    # Build forward return queries in batch
    # For efficiency, load future prices for all signal stocks
    signal_codes = list(set(s[0] for s in signal_keys))
    
    # Process forward returns by date batch
    forward_returns = {s['ts_code']: {} for s in all_signals}  # dict of dict: {ts_code: {trade_date: {ret_5d, ret_10d, ret_20d}}}
    
    # For each signal date, find close at +5, +10, +20 trading days
    signal_dates_deduplicated = sorted(set(s['trade_date'] for s in all_signals))
    
    # Build an efficient lookup: for each stock, preload all price data
    # This will be large but manageable
    for si, signal in enumerate(all_signals):
        code = signal['ts_code']
        dt = signal['trade_date']
        close_0 = signal['close_0']
        
        # Find the index of this trade_date
        if dt not in date_index:
            continue
        
        dt_idx = date_index[dt]
        
        # Look up close at +5, +10, +20 trading days
        for fwd_days, label in [(5, 'ret_5d'), (10, 'ret_10d'), (20, 'ret_20d')]:
            target_idx = dt_idx + fwd_days
            if target_idx < len(trade_dates):
                target_date = trade_dates[target_idx]
                # Query: get close for this stock on target_date
                sql = f"""
                SELECT close 
                FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
                WHERE ts_code = '{code}' AND trade_date = toDate('{target_date}')
                """
                rows = ch_query(sql)
                if rows and rows[0]['close'] and close_0 and close_0 > 0:
                    ret = (rows[0]['close'] / close_0 - 1) * 100
                    if code not in forward_returns:
                        forward_returns[code] = {}
                    if dt not in forward_returns[code]:
                        forward_returns[code][dt] = {}
                    forward_returns[code][dt][label] = ret
        
        if (si + 1) % 50 == 0:
            print(f"  Processed {si+1}/{len(all_signals)} signals for forward returns...")
    
    # Compute stats
    rets_5d, rets_10d, rets_20d = [], [], []
    
    for s in all_signals:
        code = s['ts_code']
        dt = s['trade_date']
        if code in forward_returns and dt in forward_returns[code]:
            fd = forward_returns[code][dt]
            if 'ret_5d' in fd and fd['ret_5d'] is not None:
                rets_5d.append(fd['ret_5d'])
            if 'ret_10d' in fd and fd['ret_10d'] is not None:
                rets_10d.append(fd['ret_10d'])
            if 'ret_20d' in fd and fd['ret_20d'] is not None:
                rets_20d.append(fd['ret_20d'])
    
    import statistics
    
    def compute_stats(rets):
        if not rets or len(rets) < 10:
            return {'N': len(rets) if rets else 0, 'WR': 0, 'avg_ret': 0, 'sharpe': 0}
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        avg_ret = statistics.mean(rets)
        if len(rets) > 1:
            std = statistics.stdev(rets)
            sharpe = avg_ret / std * (252 / 5) ** 0.5 if std > 0 else 0
        else:
            sharpe = 0
        return {'N': len(rets), 'WR': round(wr, 2), 'avg_ret': round(avg_ret, 2), 'sharpe': round(sharpe, 2)}
    
    stats_5d = compute_stats(rets_5d)
    stats_10d = compute_stats(rets_10d)
    stats_20d = compute_stats(rets_20d)
    
    result = {
        'name': combo_name,
        'N': len(all_signals),
        'N_5d': stats_5d['N'],
        'WR_5d': stats_5d['WR'],
        'WR_10d': stats_10d['WR'],
        'WR_20d': stats_20d['WR'],
        'ret_5d': stats_5d['avg_ret'],
        'ret_10d': stats_10d['avg_ret'],
        'ret_20d': stats_20d['avg_ret'],
        'sharpe_5d': stats_5d['sharpe'],
        'sharpe_10d': stats_10d['sharpe'],
        'sharpe_20d': stats_20d['sharpe'],
        'params': combo,
        'status': 'PASS' if (stats_5d['WR'] >= 52 and stats_5d['avg_ret'] >= 3 and stats_5d['N'] >= 200) else 'FAIL'
    }
    
    print(f"\n  Results:")
    print(f"    Signals: {result['N']} (5D complete: {result['N_5d']})")
    print(f"    5D: WR={result['WR_5d']}%, avg_ret={result['ret_5d']}%, Sharpe={result['sharpe_5d']}")
    print(f"    10D: WR={result['WR_10d']}%, avg_ret={result['ret_10d']}%, Sharpe={result['sharpe_10d']}")
    print(f"    20D: WR={result['WR_20d']}%, avg_ret={result['ret_20d']}%, Sharpe={result['sharpe_20d']}")
    print(f"    Status: {result['status']}")
    
    return result


if __name__ == '__main__':
    # Redesign: This per-stock-per-date query approach is too slow.
    # I need to batch by stock code and forward return periods.
    print("Testing ClickHouse connectivity...")
    test = ch_query("SELECT 1 AS test")
    print(f"Connection OK: {test}")
    
    # The per-stock approach is too slow for thousands of signals.
    # Let me redesign for batch processing.
    print("\nNeed to redesign for batch processing...")
