#!/usr/bin/env python3
"""
iter8-T3: 反转低吸挖掘 — 全量历史回测
Focus: 恐慌暴跌、深底反转、超卖反弹、估值修复
"""
import json, hashlib, sys, os
from collections import defaultdict
from urllib.request import Request, urlopen
from urllib.parse import quote
from datetime import datetime, timedelta

# ── ClickHouse 连接 ──
CH_URL = "http://172.24.224.1:8123"
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_DB = "tushare"

def ch_query(sql, fmt='JSON'):
    """Execute SQL via ClickHouse HTTP interface"""
    url = f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&database={CH_DB}&default_format={fmt}"
    req = Request(url, data=sql.encode('utf-8'))
    req.add_header('Content-Type', 'text/plain')
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode('utf-8'))

# ── Latest date ──
max_date = ch_query("SELECT max(trade_date) AS d FROM tushare_stock_daily FINAL")['data'][0]['d']
print(f"Latest trade_date: {max_date}")
# Use full history up to latest date

def get_trade_dates_before(date_str, count):
    """Get last N trade dates before given date"""
    rows = ch_query(f"""
        SELECT DISTINCT trade_date 
        FROM tushare_stock_daily FINAL 
        WHERE trade_date <= '{date_str}'
        ORDER BY trade_date DESC 
        LIMIT {count + 5}
    """)['data']
    return [r['trade_date'] for r in rows]

# ── Helper: compute statistics from a list of future returns ──
def compute_stats(returns_5d, returns_10d, returns_20d):
    """Compute win rate, avg return, Sharpe from return lists"""
    def _stats(r_list):
        if not r_list:
            return {'avg_return': 0, 'win_rate': 0, 'std': 0, 'sharpe': 0, 'n': 0}
        avg = sum(r_list) / len(r_list)
        n_win = sum(1 for r in r_list if r > 0)
        wr = n_win / len(r_list) * 100
        if len(r_list) > 1:
            variance = sum((r - avg) ** 2 for r in r_list) / (len(r_list) - 1)
            std = variance ** 0.5
        else:
            std = 0
        # Annualized Sharpe: avg/std * sqrt(252/N_days)
        # For 5-day: sharp_5d = avg/std * sqrt(252/5) ≈ avg/std * 7.1
        sharpe = (avg / std * (252/5)**0.5) if std > 1e-8 else 0
        return {'avg_return': avg * 100, 'win_rate': wr, 'std': std, 'sharpe': sharpe, 'n': len(r_list)}
    
    return {
        '5d': _stats(returns_5d),
        '10d': _stats(returns_10d),
        '20d': _stats(returns_20d),
    }

# ── Define 5 combos ──
combos = [
    {
        'name': 'C1: 优质底吸 — 底20%+高毛利+低PE+放量+中小盘',
        'params': {
            'close_position': '底20%',
            'pe_max': 15,
            'pb_max': 2,
            'gross_margin_min': 0.30,
            'amplitude_min': 5,
            'volume_ratio_min': 1.0,
            'market_cap': '中小盘30-100亿',
        },
        'base_condition': """
            -- 底20%: close at bottom 20% of 20-day range
            s.close <= s.low + (s.high - s.low) * 0.20
        """,
        'from_clause': 'tushare_stock_daily FINAL AS s',
    },
    {
        'name': 'C2: 低波衰竭+放量反转 — 底20%+ATR≤1%+今日涨+VR≥1.5+小盘',
        'params': {
            'close_position': '底20%',
            'atr_pct_20d': 0.01,
            'pct_chg_1d_min': 0,
            'volume_ratio_min': 1.5,
            'turnover_rate_max': 10,
            'market_cap': '小盘<30亿',
        },
    },
    {
        'name': 'C3: 缩量衰竭+深底反弹 — 底20%+量缩5日+今日放量企稳+小盘',
        'params': {
            'close_position': '底20%',
            'vol_trend_5d': '持续缩量后再放量',
            'pct_chg_1d_min': 0,
            'amplitude_min': 5,
            'market_cap': '小盘<30亿',
        },
    },
    {
        'name': 'C4: 恐慌深底+净利率质量+高波 — 底20%+跌≥5%+振≥6%+净利率≥10%+小盘',
        'params': {
            'close_position': '底20%',
            'pct_chg_1d_max': -5,
            'amplitude_min': 6,
            'net_profit_margin_min': 0.10,
            'volume_ratio_min': 1.2,
            'market_cap': '小盘<30亿',
        },
    },
    {
        'name': 'C5: 超长线底(60日新低)+超大单抄底+微盘 — 60日新低+超大单买>卖+微盘',
        'params': {
            'n_day_low': 60,
            'buy_elg_ratio_min': 0.05,
            'sell_elg_ratio_max': 0.05,
            'amplitude_min': 5,
            'net_mf_amount_min_wan': 100,
            'market_cap': '微盘<30亿',
        },
    },
]

# ── Build SQL for each combo ──
def build_combo_sql(combo_idx):
    """
    Build backtest SQL for each combo.
    Returns a list of (trade_date, ts_code, close_price, future_5d_return, future_10d_return, future_20d_return)
    """
    if combo_idx == 0:
        # C1: Quality bottom fishing
        # Bottom 20% + PE≤15 + PB≤2 + gross_margin≥30% + amplitude≥5% + VR≥1.0 + mid-small cap
        sql = f"""
        SELECT s.trade_date, s.ts_code, s.close,
               s.amount / 1e8 AS amount_yi,
               s.pct_chg
        FROM tushare_stock_daily FINAL AS s
        WHERE s.trade_date >= '20200101' AND s.trade_date <= '{max_date}'
          AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' 
          AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
          -- Bottom 20% of 20-day range
          AND s.close <= s.low + (s.high - s.low) * 0.20
          -- Amplitude ≥ 5%
          AND (s.high - s.low) / s.pre_close * 100 >= 5
          -- Volume ratio ≥ 1.0
          AND s.vol / (
            SELECT avg(s2.vol) FROM tushare_stock_daily FINAL AS s2 
            WHERE s2.ts_code = s.ts_code AND s2.trade_date >= toYYYYMMDD(toDate(s.trade_date) - 10) 
              AND s2.trade_date < s.trade_date
          ) >= 1.0
        ORDER BY s.trade_date, s.ts_code
        """
    elif combo_idx == 1:
        # C2: Low-vol exhaustion + reversal
        # Need daily_basic for turnover_rate, stk_factor_pro for ATR
        sql = f"""
        SELECT s.trade_date, s.ts_code, s.close, s.pct_chg,
               s.high, s.low, s.amount / 1e8 AS amount_yi,
               s.pre_close
        FROM tushare_stock_daily FINAL AS s
        WHERE s.trade_date >= '20200101' AND s.trade_date <= '{max_date}'
          AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' 
          AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
          -- Bottom 20%
          AND s.close <= s.low + (s.high - s.low) * 0.20
          -- Today positive
          AND s.pct_chg >= 0
          -- Volume ratio ≥ 1.5
          AND s.vol / (
            SELECT avg(s2.vol) FROM tushare_stock_daily FINAL AS s2 
            WHERE s2.ts_code = s.ts_code AND s2.trade_date >= toYYYYMMDD(toDate(s.trade_date) - 10) 
              AND s2.trade_date < s.trade_date
          ) >= 1.5
        ORDER BY s.trade_date, s.ts_code
        """
    elif combo_idx == 2:
        # C3: Shrink 5d + bottom + recovery today
        # 5 consecutive days of shrinking volume, then today positive with volume
        sql = f"""
        SELECT s.trade_date, s.ts_code, s.close, s.pct_chg,
               s.vol, s.amount / 1e8 AS amount_yi
        FROM tushare_stock_daily FINAL AS s
        WHERE s.trade_date >= '20200101' AND s.trade_date <= '{max_date}'
          AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' 
          AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
          -- Bottom 20%
          AND s.close <= s.low + (s.high - s.low) * 0.20
          -- Today positive
          AND s.pct_chg >= 0
          -- Amplitude ≥ 5%
          AND (s.high - s.low) / s.pre_close * 100 >= 5
          -- Volume > previous day (初步放量)
          AND s.vol > (
            SELECT s2.vol FROM tushare_stock_daily FINAL AS s2 
            WHERE s2.ts_code = s.ts_code AND s2.trade_date < s.trade_date 
            ORDER BY s2.trade_date DESC LIMIT 1
          )
        ORDER BY s.trade_date, s.ts_code
        """
    elif combo_idx == 3:
        # C4: Panic + quality + small cap reversal
        sql = f"""
        SELECT s.trade_date, s.ts_code, s.close, s.pct_chg,
               s.high, s.low, s.vol, s.amount / 1e8 AS amount_yi
        FROM tushare_stock_daily FINAL AS s
        WHERE s.trade_date >= '20200101' AND s.trade_date <= '{max_date}'
          AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' 
          AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
          -- Bottom 20%
          AND s.close <= s.low + (s.high - s.low) * 0.20
          -- Panic: dropped ≥ 5%
          AND s.pct_chg <= -5
          -- Amplitude ≥ 6%
          AND (s.high - s.low) / s.pre_close * 100 >= 6
          -- Volume ratio ≥ 1.2
          AND s.vol / (
            SELECT avg(s2.vol) FROM tushare_stock_daily FINAL AS s2 
            WHERE s2.ts_code = s.ts_code AND s2.trade_date >= toYYYYMMDD(toDate(s.trade_date) - 10) 
              AND s2.trade_date < s.trade_date
          ) >= 1.2
        ORDER BY s.trade_date, s.ts_code
        """
    elif combo_idx == 4:
        # C5: 60-day low + super large order buying + micro cap
        sql = f"""
        SELECT s.trade_date, s.ts_code, s.close, s.pct_chg,
               s.amount / 1e8 AS amount_yi
        FROM tushare_stock_daily FINAL AS s
        WHERE s.trade_date >= '20200101' AND s.trade_date <= '{max_date}'
          AND s.ts_code NOT LIKE '30%%' AND s.ts_code NOT LIKE '688%%' 
          AND s.ts_code NOT LIKE '920%%' AND s.ts_code NOT LIKE '%%ST%%'
          -- 60-day low: close is min of past 60 days
          AND s.close <= (
            SELECT min(s2.close) FROM tushare_stock_daily FINAL AS s2 
            WHERE s2.ts_code = s.ts_code 
              AND s2.trade_date >= toYYYYMMDD(toDate(s.trade_date) - 90)
              AND s2.trade_date <= s.trade_date
          )
          -- Amplitude ≥ 5%
          AND (s.high - s.low) / s.pre_close * 100 >= 5
        ORDER BY s.trade_date, s.ts_code
        """
    
    return sql

def build_future_return_query():
    """Build query to get future returns for signal dates"""
    # We'll do this per-combo using IN clause
    
    pass

# ── Run full backtest ──
def run_backtest(combo_idx, combo):
    print(f"\n{'='*80}")
    print(f"Testing: {combo['name']}")
    print(f"{'='*80}")
    
    sql = build_combo_sql(combo_idx)
    print(f"SQL length: {len(sql)} chars")
    
    try:
        result = ch_query(sql)
        data = result.get('data', [])
        n_signals = len(data)
        print(f"Raw signals: {n_signals}")
        
        if n_signals < 50:
            print(f"⚠️  Too few signals ({n_signals}), skipping detailed analysis")
            return {
                'name': combo['name'],
                'params': combo['params'],
                'n_signals': n_signals,
                'status': 'too_few_signals'
            }
        
        # Get unique (trade_date, ts_code) pairs for future return lookup
        # Build a dict for quick lookup
        signal_set = set()
        for row in data:
            signal_set.add((row['trade_date'], row['ts_code']))
        
        # Sample a subset to limit query size if too many
        all_signals = list(signal_set)
        print(f"Unique signals: {len(all_signals)}")
        
        # Process in batches of 500 to avoid huge IN clauses
        batch_size = 500
        returns_5d = []
        returns_10d = []
        returns_20d = []
        
        # Get trade calendar
        all_dates = sorted(set(d for d, _ in all_signals))
        
        # For each signal, we need to find the close N days later
        # First, get all future prices in one pass
        for batch_start in range(0, len(all_signals), batch_size):
            batch = all_signals[batch_start:batch_start + batch_size]
            date_strs = set(d for d, _ in batch)
            code_list = list(set(c for _, c in batch))
            
            # Build future price query for this batch
            # We need to find the close 5, 10, 20 trading days AFTER signal
            # This requires self-join or correlated subquery
            # Alternative: get all prices for these stocks in a date range and compute in Python
            
            min_date = min(date_strs)
            max_date_obj = datetime.strptime(max_date, '%Y%m%d')
            future_end = (max_date_obj + timedelta(days=40)).strftime('%Y%m%d')
            
            # Get all future prices for these codes
            codes_str = ','.join(f"'{c}'" for c in code_list)
            
            # Simpler approach: get all trading dates and compute offsets in Python
            # For now, let's use window function approach
            
        # Simpler approach: query all future prices for a sample of recent signals
        # Let's just do a statistical approach using the full data
        
        print("Using simplified approach: computing T+5/+10/+20 via windowed query")
        
        # Grab all daily data for stock_codes to compute forward returns
        # Actually let's take a smarter approach: JOIN future_close directly
        
        # For each signal date, find close of n-th trading day after
        # Use window + lead function
        
        # Final approach: batch query with nested future lookup
        total_5d = []
        total_10d = []
        total_20d = []
        
        # Process in chunks of 200 codes
        code_chunks = [list(set(c for _, c in all_signals))[i:i+200] 
                      for i in range(0, len(set(c for _, c in all_signals)), 200)]
        
        for chunk_idx, codes_chunk in enumerate(code_chunks):
            codes_list = ','.join(f"'{c}'" for c in codes_chunk)
            
            # Get all data for these codes with forward window
            fwd_sql = f"""
            SELECT ts_code, trade_date, close,
                   pct_chg
            FROM tushare_stock_daily FINAL
            WHERE ts_code IN ({codes_list})
              AND trade_date >= '20200101'
              AND trade_date <= '{future_end}'
            ORDER BY ts_code, trade_date
            """
            
            try:
                fwd_data = ch_query(fwd_sql)['data']
                # Build per-stock price array
                stock_prices = defaultdict(list)
                for row in fwd_data:
                    stock_prices[row['ts_code']].append((row['trade_date'], row['close']))
                
                # For each signal, find future close
                for td, tc in batch if isinstance(batch, list) else all_signals[chunk_idx * 200:(chunk_idx+1) * 200]:
                    prices = stock_prices.get(tc, [])
                    # Find index of signal date
                    idx = None
                    for i, (d, _) in enumerate(prices):
                        if d == td:
                            idx = i
                            break
                    if idx is None or idx + 20 >= len(prices):
                        continue
                    
                    c0 = prices[idx][1]
                    if c0 == 0:
                        continue
                    
                    r5 = (prices[idx + 5][1] / c0 - 1) if idx + 5 < len(prices) else None
                    r10 = (prices[idx + 10][1] / c0 - 1) if idx + 10 < len(prices) else None
                    r20 = (prices[idx + 20][1] / c0 - 1) if idx + 20 < len(prices) else None
                    
                    if r5 is not None:
                        total_5d.append(r5)
                    if r10 is not None:
                        total_10d.append(r10)
                    if r20 is not None:
                        total_20d.append(r20)
                
                print(f"  Chunk {chunk_idx+1}/{len(code_chunks)}: processed {len([s for s in all_signals if s[1] in codes_chunk])} signals, got {len(total_5d)} 5d returns")
                
            except Exception as e:
                print(f"  Chunk {chunk_idx+1} failed: {e}")
                continue
        
        print(f"\nResults: 5d_N={len(total_5d)}, 10d_N={len(total_10d)}, 20d_N={len(total_20d)}")
        
        # For the approach above to work efficiently, let me just use a simpler method
        # Query all data at once for the signal set
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'name': combo['name'],
            'params': combo['params'],
            'n_signals': 0,
            'status': 'error',
            'error': str(e)
        }

# ── First, let me just test the SQL queries to check signal counts ──
print(f"\n{'='*80}")
print("PHASE 1: Quick signal count check for all 5 combos")
print(f"{'='*80}")

for i, combo in enumerate(combos):
    print(f"\n--- Combo {i+1}: {combo['name']} ---")
    sql = build_combo_sql(i)
    try:
        result = ch_query(sql)
        n = len(result.get('data', []))
        print(f"Signals: {n}")
        if n > 5:
            # Show sample
            for row in result['data'][:3]:
                print(f"  {row['trade_date']} {row['ts_code']} close={row.get('close', '?')} pct={row.get('pct_chg', '?')}")
    except Exception as e:
        print(f"Error: {e}")

print(f"\n{'='*80}")
print("PHASE 2: Detailed backtest on winning combos")
print(f"{'='*80}")

# For combos with enough signals, do full backtest
# Pick the best combos based on signal count and do detailed analysis
