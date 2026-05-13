#!/usr/bin/env python3
"""
iter8-T3: 反转低吸 — 第三轮，修复moneyflow和连续日期查询
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
    with urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode('utf-8'))

def ch_query_rows(sql):
    return ch_query(sql).get('data', [])

MAX_DATE = '20260511'
EXCLUDE = "AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'"

# ── Step 1: Load all stock_daily ──
print("Loading stock daily data...")
all_daily = ch_query_rows(f"""
SELECT ts_code, trade_date, close
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
WHERE trade_date >= '20200101' AND trade_date <= '{MAX_DATE}'
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
  AND close > 0
ORDER BY ts_code, trade_date
""")
print(f"Loaded {len(all_daily):,} rows")

stock_prices = defaultdict(list)
for row in all_daily:
    stock_prices[row['ts_code']].append((row['trade_date'], row['close']))
print(f"Indexed {len(stock_prices)} stocks")

def compute_forward_returns(signals):
    results = {'5d': [], '10d': [], '20d': []}
    for td, tc in signals:
        prices = stock_prices.get(tc, [])
        if not prices: continue
        idx = None
        for i, (d, _) in enumerate(prices):
            if d == td: idx = i; break
        if idx is None: continue
        c0 = prices[idx][1]
        if c0 <= 0: continue
        if idx + 5 < len(prices):
            results['5d'].append((prices[idx+5][1]/c0 - 1)*100)
        if idx + 10 < len(prices):
            results['10d'].append((prices[idx+10][1]/c0 - 1)*100)
        if idx + 20 < len(prices):
            results['20d'].append((prices[idx+20][1]/c0 - 1)*100)
    return results

def compute_stats(r5, r10, r20):
    def _stats(r_list, label):
        if not r_list: return {'l': label, 'n': 0, 'avg': 0, 'wr': 0, 'shp': 0}
        avg = sum(r_list)/len(r_list); wins = sum(1 for r in r_list if r>0)
        wr = wins/len(r_list)*100
        std = (sum((r-avg)**2 for r in r_list)/(len(r_list)-1))**0.5 if len(r_list)>1 else 0
        shp = avg/std*(252/5)**0.5 if std>0.001 else 0
        sr = sorted(r_list)
        return {'l': label, 'n': len(r_list), 'avg': round(avg,2), 'wr': round(wr,2),
                'shp': round(shp,2), 'p10': round(sr[int(len(sr)*0.1)],2),
                'p50': round(sr[int(len(sr)*0.5)],2), 'p90': round(sr[int(len(sr)*0.9)],2)}
    return {'5d': _stats(r5,'5D'), '10d': _stats(r10,'10D'), '20d': _stats(r20,'20D')}

# ── 5 combos (fixed queries) ──
combos = []

# C1 already passed. Let me include it for completeness but try to beat it.

# C2: Two consecutive panic days (using self-join with date difference=1 trading day)
# Approach: JOIN prev_day where prev day is the most recent trading day before today
# Use a simpler approach: require prev_day exists with pct_chg <= -3 within last 7 calendar days
combos.append({
    'name': 'C2: 连续恐慌+微盘 — 前5日内有跌≥5%且今日跌≥3%+底20%+振幅≥6%+CM≤30亿',
    'params': '前5日内有恐慌≥5%, 今日也跌≥3%, 底20%, 振幅≥6%, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date AS td, s.close AS c
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s.close <= s.low + (s.high - s.low) * 0.20
      AND s.pct_chg <= -3
      AND (s.high - s.low) / s.pre_close * 100 >= 6
      AND b.circ_mv <= 300000
      AND s.ts_code IN (
        SELECT s2.ts_code FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s2
        WHERE s2.trade_date >= toYYYYMMDD(toDate(s.trade_date) - 7)
          AND s2.trade_date < s.trade_date
          AND s2.pct_chg <= -5
      )
    """
})

# C3: Capital flow bottom fishing — with proper aliases
combos.append({
    'name': 'C3: 主力底吸+微盘 — 底20%+振幅≥5%+VR≥1.2+净流入≥0+CM≤30亿',
    'params': 'close_position=底20%, amplitude_min=5, vr>=1.2, net_mf>=0, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date AS td, s.close AS c
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    INNER JOIN (SELECT * FROM tushare.tushare_moneyflow FINAL) AS m
      ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s.close <= s.low + (s.high - s.low) * 0.20
      AND (s.high - s.low) / s.pre_close * 100 >= 5
      AND b.volume_ratio >= 1.2
      AND b.circ_mv <= 300000
      AND m.net_mf_amount >= 0
      AND m.buy_lg_amount > m.sell_lg_amount
    """
})

# C4: Two-day reversal (today >= 2%, prev day <= -3%) + micro cap
combos.append({
    'name': 'C4: 双日反转+微盘 — 今日涨≥2%+前7日有跌≥3%+振幅≥7%+VR≥1.3+CM≤30亿',
    'params': 'pct_chg>=2, 前7日有跌≥3%, amplitude_min=7, vr>=1.3, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date AS td, s.close AS c
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s.pct_chg >= 2
      AND (s.high - s.low) / s.pre_close * 100 >= 7
      AND b.volume_ratio >= 1.3
      AND b.circ_mv <= 300000
      AND s.ts_code IN (
        SELECT s2.ts_code FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s2
        WHERE s2.trade_date >= toYYYYMMDD(toDate(s.trade_date) - 7)
          AND s2.trade_date < s.trade_date
          AND s2.pct_chg <= -3
      )
    """
})

# C5: Panic + super-large order + micro cap
combos.append({
    'name': 'C5: 恐慌日主力逆势吸筹 — 跌≥7%+振幅≥7%+净流入≥0+超大单买>卖+CM≤30亿',
    'params': 'pct_chg<=-7, amplitude_min=7, net_mf>=0, buy_elg>sell_elg, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date AS td, s.close AS c
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    INNER JOIN (SELECT * FROM tushare.tushare_moneyflow FINAL) AS m
      ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s.pct_chg <= -7
      AND (s.high - s.low) / s.pre_close * 100 >= 7
      AND m.net_mf_amount >= 0
      AND m.buy_elg_amount > m.sell_elg_amount
      AND b.circ_mv <= 300000
    """
})

# C6 (NEW): Panic + capital outflow (retail panic + value + small cap) → contrarian
# 跌≥7% + 净流出(散户大量卖出) + 振幅≥7% + PE≤20 + CM≤30亿
combos.append({
    'name': 'C6: 散户恐慌割肉+价值+微盘 — 跌≥7%+散户净卖出+振幅≥7%+PE≤20+CM≤30亿',
    'params': 'pct_chg<=-7, sm_net_sell, amplitude_min=7, pe<=20, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date AS td, s.close AS c
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    INNER JOIN (SELECT * FROM tushare.tushare_moneyflow FINAL) AS m
      ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s.pct_chg <= -7
      AND (s.high - s.low) / s.pre_close * 100 >= 7
      AND b.pe_ttm <= 20 AND b.pe_ttm > 0
      AND b.circ_mv <= 300000
      AND m.sell_sm_amount > m.buy_sm_amount
      AND m.net_mf_amount < 0
    """
})

# ── Run ──
all_results = []
for idx, combo in enumerate(combos):
    print(f"\n{'='*70}")
    print(f"Combo {idx+1}: {combo['name']}")
    print(f"{'='*70}")
    try:
        signals_raw = ch_query_rows(combo['sql'])
        n_raw = len(signals_raw)
        print(f"Raw signals: {n_raw:,}")
        if n_raw < 50:
            print(f"⚠️ Too few")
            all_results.append({'name': combo['name'], 'params': combo['params'], 'n_raw': n_raw, 'status': 'too_few'})
            continue
        # keys: td, ts_code
        try:
            signals = list(set((r['td'], r['ts_code']) for r in signals_raw))
        except KeyError:
            print(f"Keys in result: {list(signals_raw[0].keys()) if signals_raw else 'empty'}")
            signals = list(set((r.get('td') or r.get('trade_date'), r['ts_code']) for r in signals_raw))
        print(f"Unique: {len(signals):,}")
        if len(signals) < 100:
            all_results.append({'name': combo['name'], 'params': combo['params'], 'n_raw': n_raw, 'n_unique': len(signals), 'status': 'too_few'})
            continue
        fwd = compute_forward_returns(signals)
        stats = compute_stats(fwd['5d'], fwd['10d'], fwd['20d'])
        print(f"  N={stats['5d']['n']:,} | R5={stats['5d']['avg']:.2f}% | WR={stats['5d']['wr']:.1f}% | Sharpe={stats['5d']['shp']:.2f}")
        print(f"  R10={stats['10d']['avg']:.2f}% | R20={stats['20d']['avg']:.2f}%")
        print(f"  Dist: P10={stats['5d']['p10']:.1f}% P50={stats['5d']['p50']:.1f}% P90={stats['5d']['p90']:.1f}%")
        passed = stats['5d']['wr'] >= 52 and stats['5d']['avg'] >= 3.0 and stats['5d']['n'] >= 200
        print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
        all_results.append({'name': combo['name'], 'params': combo['params'], 'stats': stats, 'passed': passed})
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback; traceback.print_exc()
        all_results.append({'name': combo['name'], 'params': combo['params'], 'status': 'error', 'error': str(e)})

# ── Summary ──
print(f"\n\n{'='*70}")
print("FINAL SUMMARY")
print(f"{'='*70}")
pass_count = 0
for r in all_results:
    if 'stats' in r:
        s = r['stats']['5d']
        tag = '✅' if r['passed'] else '❌'
        if r['passed']: pass_count += 1
        print(f"{tag} {r['name']}")
        print(f"   N={s['n']:,} | R5={s['avg']:.2f}% | WR={s['wr']:.1f}% | Sharpe={s['shp']:.2f} | R10={r['stats']['10d']['avg']:.2f}% | R20={r['stats']['20d']['avg']:.2f}%")
    elif r.get('status') == 'error':
        print(f"❌ Error: {r['name']} — {r.get('error','')}")
    else:
        print(f"⚠️ {r['name']} — raw={r.get('n_raw',0)}")

print(f"\nPassed: {pass_count}/{len(combos)}")
