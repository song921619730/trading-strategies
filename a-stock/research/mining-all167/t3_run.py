#!/usr/bin/env python3
"""
iter8-T3: 反转低吸全量回测
5 combos → signal count → full metrics
"""
import json
from urllib.request import Request, urlopen
from collections import defaultdict

CH_URL = "http://172.24.224.1:8123"
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_DB = "tushare"

def ch_query(sql):
    url = f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&database={CH_DB}&default_format=JSON"
    req = Request(url, data=sql.encode('utf-8'))
    req.add_header('Content-Type', 'text/plain')
    with urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode('utf-8'))

def ch_query_rows(sql):
    """Return list of dicts"""
    return ch_query(sql).get('data', [])

MAX_DATE = '20260511'
EXCLUDE = "AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'"

# ── Step 1: Load all stock_daily data for future return computation ──
print("Loading all stock daily data for forward return computation...")
all_daily = ch_query_rows(f"""
SELECT ts_code, trade_date, close
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
WHERE trade_date >= '20200101' AND trade_date <= '{MAX_DATE}'
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
  AND close > 0
ORDER BY ts_code, trade_date
""")
print(f"Loaded {len(all_daily):,} daily rows")

# Build per-stock price arrays
print("Building price index...")
stock_prices = defaultdict(list)
for row in all_daily:
    stock_prices[row['ts_code']].append((row['trade_date'], row['close']))
print(f"Indexed {len(stock_prices)} stocks")

# ── Helper: compute forward returns ──
def compute_forward_returns(signals):
    """
    signals: list of (trade_date, ts_code)
    Returns dict with 5d, 10d, 20d return lists
    """
    results = {'5d': [], '10d': [], '20d': []}
    for td, tc in signals:
        prices = stock_prices.get(tc, [])
        if not prices:
            continue
        # Find index of signal date
        idx = None
        for i, (d, _) in enumerate(prices):
            if d == td:
                idx = i
                break
        if idx is None:
            continue
        
        c0 = prices[idx][1]
        if c0 <= 0:
            continue
        
        if idx + 5 < len(prices):
            r5 = (prices[idx + 5][1] / c0 - 1) * 100
            results['5d'].append(r5)
        if idx + 10 < len(prices):
            r10 = (prices[idx + 10][1] / c0 - 1) * 100
            results['10d'].append(r10)
        if idx + 20 < len(prices):
            r20 = (prices[idx + 20][1] / c0 - 1) * 100
            results['20d'].append(r20)
    return results

def compute_stats(returns_5d, returns_10d, returns_20d):
    """Compute WR, avg_return, Sharpe"""
    def _stats(r_list, label):
        if not r_list:
            return {'label': label, 'n': 0, 'avg_return': 0, 'win_rate': 0, 'sharpe': 0}
        avg = sum(r_list) / len(r_list)
        wins = sum(1 for r in r_list if r > 0)
        wr = wins / len(r_list) * 100
        if len(r_list) > 1:
            variance = sum((r - avg) ** 2 for r in r_list) / (len(r_list) - 1)
            std = variance ** 0.5
        else:
            std = 0
        sharpe = (avg / std * (252/5)**0.5) if std > 0.001 else 0
        # Percentiles for distribution analysis
        s_ret = sorted(r_list)
        p10 = s_ret[int(len(s_ret)*0.1)]
        p50 = s_ret[int(len(s_ret)*0.5)]
        p90 = s_ret[int(len(s_ret)*0.9)]
        return {
            'label': label, 'n': len(r_list), 'avg_return': round(avg, 2),
            'win_rate': round(wr, 2), 'sharpe': round(sharpe, 2),
            'p10': round(p10, 2), 'p50': round(p50, 2), 'p90': round(p90, 2)
        }
    return {
        '5d': _stats(returns_5d, '5D'),
        '10d': _stats(returns_10d, '10D'),
        '20d': _stats(returns_20d, '20D'),
    }

# ── Define 5 combos ──
combos_defs = []

# C1: Quality bottom fishing
# 底20% + PE≤15 + PB≤2 + 振幅≥5% + VR≥1.0 + CM 30-100亿
combos_defs.append({
    'name': 'C1: 优质底吸 — 底20%+PE≤15+PB≤2+振幅≥5%+VR≥1.0+中小盘30-100亿',
    'params_str': 'close_position=底20%, pe_max=15, pb_max=2, amplitude_min=5, volume_ratio_min=1.0, circ_mv=30-100亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s.close <= s.low + (s.high - s.low) * 0.20
      AND (s.high - s.low) / s.pre_close * 100 >= 5
      AND b.volume_ratio >= 1.0
      AND b.pe_ttm <= 15
      AND b.pb <= 2
      AND b.circ_mv >= 300000 AND b.circ_mv <= 1000000
    """
})

# C2: Low-vol exhaustion + reversal
# 底20% + pct_chg≥0 + VR≥1.5 + TR≤10 + CM≤30亿
combos_defs.append({
    'name': 'C2: 低波衰竭放量反转 — 底20%+今日涨+VR≥1.5+换手≤10%+小盘≤30亿',
    'params_str': 'close_position=底20%, pct_chg_min=0, volume_ratio_min=1.5, turnover_rate_max=10, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s.close <= s.low + (s.high - s.low) * 0.20
      AND s.pct_chg >= 0
      AND b.volume_ratio >= 1.5
      AND b.turnover_rate <= 10
      AND b.circ_mv <= 300000
    """
})

# C3: Shrink before surge — 缩量衰竭后放量起跳
# 底20% + 今日涨≥0 + 振幅≥5% + 今日量>前日量 + CM≤30亿
combos_defs.append({
    'name': 'C3: 缩量衰竭起跳 — 底20%+今日涨+振幅≥5%+量递增+小盘≤30亿',
    'params_str': 'close_position=底20%, pct_chg_min=0, amplitude_min=5, vol_today>vol_yesterday, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s1.ts_code, s1.trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s1
    INNER JOIN (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s0
      ON s1.ts_code = s0.ts_code AND s0.trade_date < s1.trade_date
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s1.ts_code = b.ts_code AND s1.trade_date = b.trade_date
    WHERE s1.trade_date >= '20200101' AND s1.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s1.close <= s1.low + (s1.high - s1.low) * 0.20
      AND s1.pct_chg >= 0
      AND (s1.high - s1.low) / s1.pre_close * 100 >= 5
      AND s1.vol > s0.vol
      AND b.circ_mv <= 300000
      AND s0.trade_date = (
        SELECT max(s2.trade_date) FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s2
        WHERE s2.ts_code = s1.ts_code AND s2.trade_date < s1.trade_date
      )
    """
})

# C4: Panic + quality + small cap
# 底20% + pct_chg≤-5 + 振幅≥6% + VR≥1.2 + CM≤30亿
combos_defs.append({
    'name': 'C4: 恐慌深底反弹 — 底20%+跌≥5%+振幅≥6%+VR≥1.2+小盘≤30亿',
    'params_str': 'close_position=底20%, pct_chg_max=-5, amplitude_min=6, volume_ratio_min=1.2, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s.close <= s.low + (s.high - s.low) * 0.20
      AND s.pct_chg <= -5
      AND (s.high - s.low) / s.pre_close * 100 >= 6
      AND b.volume_ratio >= 1.2
      AND b.circ_mv <= 300000
    """
})

# C5: 60-day new low + big amplitude + micro cap (极端底部反转)
combos_defs.append({
    'name': 'C5: 60日新低+大振幅 — 60日最低+振幅≥5%+CM≤30亿',
    'params_str': 'n_day_low=60, amplitude_min=5, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND (s.high - s.low) / s.pre_close * 100 >= 5
      AND b.circ_mv <= 300000
      AND s.close = (
        SELECT min(s2.close) FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s2
        WHERE s2.ts_code = s.ts_code
          AND s2.trade_date >= toYYYYMMDD(toDate(s.trade_date) - 90)
          AND s2.trade_date <= s.trade_date
      )
    """
})

# ── Run all combos ──
all_results = []

for idx, combo in enumerate(combos_defs):
    print(f"\n{'='*70}")
    print(f"Combo {idx+1}: {combo['name']}")
    print(f"Params: {combo['params_str']}")
    print(f"{'='*70}")
    
    try:
        # Get signals
        signals_raw = ch_query_rows(combo['sql'])
        n_raw = len(signals_raw)
        print(f"Raw signals: {n_raw:,}")
        
        if n_raw < 50:
            print(f"⚠️ Too few signals ({n_raw}), skipping")
            all_results.append({
                'name': combo['name'],
                'params': combo['params_str'],
                'n_raw': n_raw,
                'status': 'too_few'
            })
            continue
        
        # Deduplicate and format
        signals = list(set((r['trade_date'], r['ts_code']) for r in signals_raw))
        print(f"Unique signals: {len(signals):,}")
        
        if len(signals) < 100:
            print(f"⚠️ Only {len(signals)} unique signals, skipping")
            all_results.append({
                'name': combo['name'],
                'params': combo['params_str'],
                'n_raw': n_raw,
                'n_unique': len(signals),
                'status': 'too_few'
            })
            continue
        
        # Compute forward returns
        fwd = compute_forward_returns(signals)
        stats = compute_stats(fwd['5d'], fwd['10d'], fwd['20d'])
        
        print(f"  N_5d={stats['5d']['n']:,}, R5={stats['5d']['avg_return']:.2f}%, WR={stats['5d']['win_rate']:.2f}%, Sharpe={stats['5d']['sharpe']:.2f}")
        print(f"  N_10d={stats['10d']['n']:,}, R10={stats['10d']['avg_return']:.2f}%, WR={stats['10d']['win_rate']:.2f}%")
        print(f"  N_20d={stats['20d']['n']:,}, R20={stats['20d']['avg_return']:.2f}%, WR={stats['20d']['win_rate']:.2f}%")
        print(f"  5D_dist: P10={stats['5d']['p10']:.1f}% P50={stats['5d']['p50']:.1f}% P90={stats['5d']['p90']:.1f}%")
        
        # Check if passed
        passed = stats['5d']['win_rate'] >= 52 and stats['5d']['avg_return'] >= 3.0 and stats['5d']['n'] >= 200
        print(f"  {'✅ PASS' if passed else '❌ FAIL'}: WR≥52%={stats['5d']['win_rate']>=52}, R5≥3%={stats['5d']['avg_return']>=3.0}, N≥200={stats['5d']['n']>=200}")
        
        all_results.append({
            'name': combo['name'],
            'params': combo['params_str'],
            'n_raw': n_raw,
            'n_unique': len(signals),
            'stats': stats,
            'passed': passed
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        all_results.append({
            'name': combo['name'],
            'params': combo['params_str'],
            'n_raw': 0,
            'status': 'error',
            'error': str(e)
        })

# ── Summary ──
print(f"\n\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
for r in all_results:
    status = '✅' if r.get('passed') else '❌'
    if r.get('status') == 'too_few':
        status = '⚠️ Too few'
    elif r.get('status') == 'error':
        status = '❌ Error'
    
    if 'stats' in r:
        print(f"{status} {r['name']}")
        print(f"   N={r['stats']['5d']['n']:,} | R5={r['stats']['5d']['avg_return']:.2f}% | WR={r['stats']['5d']['win_rate']:.1f}% | Sharpe={r['stats']['5d']['sharpe']:.2f}")
        print(f"   R10={r['stats']['10d']['avg_return']:.2f}% | R20={r['stats']['20d']['avg_return']:.2f}%")
    elif 'n_raw' in r:
        print(f"{status} {r['name']} — raw={r.get('n_raw', 0)} unique={r.get('n_unique', 'N/A')}")
