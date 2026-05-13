#!/usr/bin/env python3
"""
iter8-T3: 反转低吸 — 第二轮，更强激活信号
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

# ── 5 Strong combos ──
# C1: Deep panic + extreme amplitude + deep value + micro cap  (strongest reversal)
# 底20% + 跌≥7% + 振幅≥7% + PE≤15 + PB≤2 + CM≤30亿
combos = []

combos.append({
    'name': 'C1: 深恐慌+深价值+微盘 — 底20%+跌≥7%+振幅≥7%+PE≤15+PB≤2+CM≤30亿',
    'params': 'close_position=底20%, pct_chg<=-7, amplitude_min=7, pe_max=15, pb_max=2, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s.close <= s.low + (s.high - s.low) * 0.20
      AND s.pct_chg <= -7
      AND (s.high - s.low) / s.pre_close * 100 >= 7
      AND b.pe_ttm <= 15 AND b.pe_ttm > 0
      AND b.pb <= 2 AND b.pb > 0
      AND b.circ_mv <= 300000
    """
})

# C2: Two-day consecutive panic + extreme amplitude + micro cap
# 前日跌≥3% + 今日跌≥3% + 底20% + 振幅≥6% + CM≤30亿
combos.append({
    'name': 'C2: 连续恐慌+微盘 — 连续2日跌≥3%+底20%+振幅≥6%+CM≤30亿',
    'params': '连续2日恐慌≤-3%, close_position=底20%, amplitude_min=6, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s1.ts_code, s1.trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s1
    INNER JOIN (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s0
      ON s1.ts_code = s0.ts_code
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s1.ts_code = b.ts_code AND s1.trade_date = b.trade_date
    WHERE s1.trade_date >= '20200101' AND s1.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s1.close <= s1.low + (s1.high - s1.low) * 0.20
      AND s1.pct_chg <= -3
      AND (s1.high - s1.low) / s1.pre_close * 100 >= 6
      AND s0.pct_chg <= -3
      AND b.circ_mv <= 300000
      AND s0.trade_date = toYYYYMMDD(toDate(s1.trade_date) - (
        SELECT min(diff)
        FROM (
          SELECT toDate(s2.trade_date) AS td2,
                 dateDiff('day', toDate(s2.trade_date), toDate(s1.trade_date)) AS diff
          FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s2
          WHERE s2.ts_code = s1.ts_code AND s2.trade_date < s1.trade_date
          ORDER BY s2.trade_date DESC LIMIT 1
        )
      ))
    """
})

# C3: Capital flow bottom fishing — net_mf + buy_lg + micro cap
# 底20% + 振幅≥5% + VR≥1.2 + 净流入≥100万 + 大单买入比≥10% + CM≤30亿
combos.append({
    'name': 'C3: 主力底吸 — 底20%+振幅≥5%+VR≥1.2+净流入≥100万+大单比≥10%+CM≤30亿',
    'params': 'close_position=底20%, amplitude_min=5, vr>=1.2, net_mf>=100万, buy_lg>=10%, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date
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
      AND m.net_mf_amount >= 100
      AND m.buy_lg_amount > m.sell_lg_amount
    """
})

# C4: Two-day reversal + extreme wick (hammer) + micro cap
# 前日跌 ≥3% + 今日涨 ≥2% + 振幅≥7% + VR≥1.3 + CM≤30亿  (双日反转增强版)
combos.append({
    'name': 'C4: 双日反转+强振幅+微盘 — 前日跌≥3%+今日涨≥2%+振幅≥7%+VR≥1.3+CM≤30亿',
    'params': '前日跌≥3%, 今日涨≥2%, amplitude_min=7, vr>=1.3, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s1.ts_code, s1.trade_date
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s1
    INNER JOIN (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s0
      ON s1.ts_code = s0.ts_code
    INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
      ON s1.ts_code = b.ts_code AND s1.trade_date = b.trade_date
    WHERE s1.trade_date >= '20200101' AND s1.trade_date <= '{MAX_DATE}'
      {EXCLUDE}
      AND s1.pct_chg >= 2
      AND (s1.high - s1.low) / s1.pre_close * 100 >= 7
      AND b.volume_ratio >= 1.3
      AND b.circ_mv <= 300000
      AND s0.pct_chg <= -3
      AND s0.trade_date = toYYYYMMDD(toDate(s1.trade_date) - (
        SELECT min(diff) FROM (
          SELECT dateDiff('day', toDate(s2.trade_date), toDate(s1.trade_date)) AS diff
          FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s2
          WHERE s2.ts_code = s1.ts_code AND s2.trade_date < s1.trade_date
          ORDER BY s2.trade_date DESC LIMIT 1
        )
      ))
    """
})

# C5: Panic super-large order buying + micro cap (恐慌日主力逆势吸筹)
# 跌≥7% + 振幅≥7% + 净流入≥0 + 超大单买入>卖出 + CM≤30亿
combos.append({
    'name': 'C5: 恐慌日主力逆势 — 跌≥7%+振幅≥7%+净流入≥0+超大单买>卖+CM≤30亿',
    'params': 'pct_chg<=-7, amplitude_min=7, net_mf>=0, buy_elg>sell_elg, circ_mv≤30亿',
    'sql': f"""
    SELECT DISTINCT s.ts_code, s.trade_date
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
        signals = list(set((r['trade_date'], r['ts_code']) for r in signals_raw))
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
print("SUMMARY")
print(f"{'='*70}")
for r in all_results:
    if 'stats' in r:
        s = r['stats']['5d']
        print(f"{'✅' if r['passed'] else '❌'} {r['name']}")
        print(f"   N={s['n']:,} | R5={s['avg']:.2f}% | WR={s['wr']:.1f}% | Sharpe={s['shp']:.2f} | R10={r['stats']['10d']['avg']:.2f}% | R20={r['stats']['20d']['avg']:.2f}%")
    elif r.get('status') == 'error':
        print(f"❌ Error: {r['name']} — {r.get('error','')}")
    else:
        print(f"⚠️ {r['name']} — raw={r.get('n_raw',0)} unique={r.get('n_unique','?')}")
