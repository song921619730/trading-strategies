#!/usr/bin/env python3
"""Iter17 T9: Cross-stream combination validation — v3.
Uses POST-based queries. All combos share one base CTE.
"""
import json, sys, math, urllib.request, urllib.parse, hashlib, time

HOST, PORT, USER, PWD = '172.24.224.1', '8123', 'ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ'
START, END = "2020-01-01", "2026-05-12"

def ch_q(sql, timeout=600):
    """GET-based ClickHouse query. Handles URL encoding."""
    params = {"user": USER, "password": PWD, "database": "tushare",
              "query": sql, "default_format": "JSONEachRow"}
    url = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        if not body.strip():
            return []
        return [json.loads(line) for line in body.strip().split("\n") if line.strip()]

def safe_float(v, default=None):
    if v is None: return default
    try: return float(v)
    except: return default

def get_spx_prev_up_dates():
    """Get set of trade_dates where SPX was up previous day."""
    sql = """
    SELECT trade_date, pct_chg,
           lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS prev_pct_chg
    FROM (SELECT * FROM tushare.tushare_index_global FINAL)
    WHERE ts_code = 'SPX' AND trade_date >= '2020-01-01' AND trade_date <= '2026-05-12'
    ORDER BY trade_date
    """
    rows = ch_q(sql)
    up_dates = set()
    for r in rows:
        prev = safe_float(r.get('prev_pct_chg'), 0)
        if prev > 0:
            up_dates.add(r['trade_date'])
    return up_dates


def build_base_cte():
    """Build the inner CTE body (the part after AS). All window functions use inline OVER."""
    return """
SELECT
    s.ts_code, s.trade_date,
    s.close, round(s.pct_chg, 2) AS pct_chg,
    s.open, s.high, s.low, s.pre_close,
    round((s.high - s.low) / NULLIF(s.pre_close, 0) * 100, 2) AS amp,
    round((s.close - s.low_20d) / NULLIF(s.range_20d, 0.0001), 4) AS close_pos,
    round((leadInFrame(s.close, 5) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / s.close - 1) * 100, 2) AS ret_5d,
    round((leadInFrame(s.close, 10) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / s.close - 1) * 100, 2) AS ret_10d,
    round((leadInFrame(s.close, 20) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / s.close - 1) * 100, 2) AS ret_20d,
    COALESCE(cc.concept_count, 0) AS concept_cnt
FROM (
    SELECT *,
        MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
        MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d,
        MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
        - MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS range_20d
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
    WHERE trade_date >= '{start}' AND trade_date <= '{end}'
      AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%' AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
) s
LEFT JOIN (
    SELECT con_code, count(*) AS concept_count
    FROM (SELECT * FROM tushare.tushare_ths_member FINAL)
    WHERE con_code NOT LIKE '700001.TI' AND con_code NOT LIKE '700002.TI'
    GROUP BY con_code
) cc ON cc.con_code = s.ts_code
"""


def run_sql_combo(name, sql, signal_threshold=10):
    """Run a SQL query and compute metrics."""
    t0 = time.time()
    try:
        rows = ch_q(sql)
    except Exception as e:
        return {'combo': name, 'signals': 0, 'win_rate_5d': 0, 'avg_ret_5d': 0,
                'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0,
                'time_sec': round(time.time() - t0, 1), 'passed': False, 'error': str(e)}
    
    n = len(rows)
    if n < signal_threshold:
        return {'combo': name, 'signals': n, 'win_rate_5d': 0, 'avg_ret_5d': 0,
                'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0,
                'time_sec': round(time.time() - t0, 1), 'passed': False}
    
    rets_5d = [safe_float(r.get('ret_5d'), -999) for r in rows]
    rets_5d = [r for r in rets_5d if r > -998]
    rets_10d = [safe_float(r.get('ret_10d'), -999) for r in rows]
    rets_10d = [r for r in rets_10d if r > -998]
    rets_20d = [safe_float(r.get('ret_20d'), -999) for r in rows]
    rets_20d = [r for r in rets_20d if r > -998]
    
    n5 = len(rets_5d)
    if n5 < signal_threshold:
        return {'combo': name, 'signals': n5, 'win_rate_5d': 0, 'avg_ret_5d': 0,
                'avg_ret_10d': 0, 'avg_ret_20d': 0, 'sharpe_5d': 0, 'p10_5d': 0,
                'time_sec': round(time.time() - t0, 1), 'passed': False}
    
    wins_5d = sum(1 for r in rets_5d if r > 0)
    wr_5d = wins_5d / n5 * 100
    avg_5d = sum(rets_5d) / n5
    avg_10d = sum(rets_10d) / n5 if rets_10d else 0
    avg_20d = sum(rets_20d) / n5 if rets_20d else 0
    
    if n5 > 1:
        mean_r = sum(rets_5d) / n5
        var_r = sum((r - mean_r) ** 2 for r in rets_5d) / (n5 - 1)
        std_r = math.sqrt(var_r) if var_r > 0 else 0.0001
        sharpe = (mean_r / std_r) * math.sqrt(252 / 5) if std_r > 0 else 0
    else:
        sharpe = 0
    
    sorted_rets = sorted(rets_5d)
    p10_idx = max(0, int(n5 * 0.1) - 1)
    p10_5d = sorted_rets[p10_idx] if sorted_rets else 0
    
    passed = (wr_5d >= 52 and avg_5d >= 3.0 and n5 >= 200)
    
    return {
        'combo': name, 'signals': n5, 'win_rate_5d': round(wr_5d, 2),
        'avg_ret_5d': round(avg_5d, 2), 'avg_ret_10d': round(avg_10d, 2),
        'avg_ret_20d': round(avg_20d, 2), 'sharpe_5d': round(sharpe, 3),
        'p10_5d': round(p10_5d, 2), 'time_sec': round(time.time() - t0, 2),
        'passed': passed
    }


def make_sql(template, base_cte, spx_up_str, fina_sub):
    """Fill template placeholders. Replace {start}/{end} in base_cte first."""
    # Replace start/end in base_cte
    cte = base_cte.replace('{start}', START).replace('{end}', END)
    # Replace all placeholders in template
    return template.replace('{base_cte}', cte)\
                   .replace('{spx_prev_up}', spx_up_str)\
                   .replace('{fina_sub}', fina_sub)\
                   .replace('{start}', START)\
                   .replace('{end}', END)


def main():
    t_start = time.time()
    print("=" * 60)
    print("Iter17 T9: Cross-Stream Combination Backtest")
    print("=" * 60)
    
    # Phase 1: SPX data
    print("\n[Phase 1] SPX prev-up dates...")
    spx_up_dates = get_spx_prev_up_dates()
    spx_up_str = "','".join(sorted(spx_up_dates))
    spx_up_str = f"'{spx_up_str}'"
    print(f"  {len(spx_up_dates)} dates")
    
    # Phase 2: Build base CTE
    print("\n[Phase 2] Building base CTE...")
    base_cte = build_base_cte()
    print(f"  Base CTE ready ({len(base_cte)} chars)")
    
    # Phase 3: Build fina_indicator subquery
    print("\n[Phase 3] Building fina subquery...")
    fina_sub = """
(
    SELECT ts_code FROM (
        SELECT ts_code,
               argMax(end_date, end_date) AS max_end,
               argMax(netprofit_yoy, end_date) AS np_yoy
        FROM (SELECT * FROM tushare.tushare_fina_indicator FINAL)
        WHERE end_date >= '2024-01-01'
        GROUP BY ts_code
        HAVING np_yoy >= 10
    )
)
"""
    
    # ===== Define all 14 combos with their SQL =====
    print("\n[Phase 4] Running cross-stream combos...")
    
    combos = [
        {
            'name': 'X01_T3恐慌×T4资金',
            'desc': '恐慌(-5%) × 超大单净买入 × 底20% × 振幅≥6% × VR≥1.2 × CM≤30亿 × PE≤20',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}'), mf AS (SELECT * FROM tushare.tushare_moneyflow FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv, d.pe FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date JOIN mf ON b.ts_code=mf.ts_code AND b.trade_date=mf.trade_date WHERE b.pct_chg<=-5 AND b.close_pos<=0.20 AND b.amp>=6.0 AND d.volume_ratio>=1.2 AND d.circ_mv>0 AND d.circ_mv<=300000 AND d.pe>0 AND d.pe<=20 AND mf.buy_elg_amount>mf.sell_elg_amount"""
        },
        {
            'name': 'X02_T3恐慌×SPX',
            'desc': 'SPX前日涨 × 恐慌(-5%) × 底20% × VR≥1.2 × 振幅≥5% × CM≤30亿',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date WHERE b.pct_chg<=-5 AND b.close_pos<=0.20 AND b.amp>=5.0 AND d.volume_ratio>=1.2 AND d.circ_mv>0 AND d.circ_mv<=300000 AND (d.turnover_rate IS NULL OR d.turnover_rate<=10.0) AND b.trade_date IN ({spx_prev_up})"""
        },
        {
            'name': 'X03_T6板块动量×T4资金',
            'desc': '涨幅≥3% × 超大单净买入 × 底20% × 振幅≥6% × VR≥1.3 × CM≤30亿',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}'), mf AS (SELECT * FROM tushare.tushare_moneyflow FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date JOIN mf ON b.ts_code=mf.ts_code AND b.trade_date=mf.trade_date WHERE b.pct_chg>=3 AND b.close_pos<=0.20 AND b.amp>=6.0 AND d.volume_ratio>=1.3 AND d.circ_mv>0 AND d.circ_mv<=300000 AND mf.buy_elg_amount>mf.sell_elg_amount"""
        },
        {
            'name': 'X04_T8微盘大阳×T4资金',
            'desc': '微盘(≤15亿)大阳(≥3%) × 超大单净买入 × 底20% × VR≥1.3 × 振幅≥6%',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}'), mf AS (SELECT * FROM tushare.tushare_moneyflow FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date JOIN mf ON b.ts_code=mf.ts_code AND b.trade_date=mf.trade_date WHERE b.pct_chg>=3 AND b.close_pos<=0.20 AND b.amp>=6.0 AND d.volume_ratio>=1.3 AND d.circ_mv>0 AND d.circ_mv<=150000 AND d.turnover_rate>=0.003 AND mf.buy_elg_amount>mf.sell_elg_amount"""
        },
        {
            'name': 'X05_T8低开尾拉×T4资金',
            'desc': '低开尾拉 × 超大单净买入 × 底20% × VR≥1.3 × CM≤50亿',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}'), mf AS (SELECT * FROM tushare.tushare_moneyflow FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date JOIN mf ON b.ts_code=mf.ts_code AND b.trade_date=mf.trade_date WHERE b.pct_chg>=2 AND b.close_pos<=0.20 AND b.amp>=5.0 AND d.volume_ratio>=1.3 AND d.circ_mv>0 AND d.circ_mv<=500000 AND b.open<b.pre_close AND b.close>=b.high*0.95 AND b.close>b.open AND mf.buy_elg_amount>mf.sell_elg_amount"""
        },
        {
            'name': 'X06_T5基本面×T6动量',
            'desc': '净利增长≥10% × PE≤15 × PB≤2 × 底20% × 涨幅≥3% × VR≥1.2 × CM≤30亿',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv, d.pe, d.pb FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date WHERE b.pct_chg>=3 AND b.close_pos<=0.20 AND b.amp>=5.0 AND d.volume_ratio>=1.2 AND d.circ_mv>0 AND d.circ_mv<=300000 AND d.pe>0 AND d.pe<=15 AND d.pb>0 AND d.pb<=2 AND b.ts_code IN {fina_sub}"""
        },
        {
            'name': 'X07_T3筹码锁定×T6动量',
            'desc': '恐慌(-5%)+筹码锁定(TR 0.3-3%) × 底20% × VR≥1.3 × CM≤30亿 × PE≤20',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv, d.pe FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date WHERE b.pct_chg<=-5 AND b.close_pos<=0.20 AND b.amp>=5.0 AND d.volume_ratio>=1.3 AND d.circ_mv>0 AND d.circ_mv<=300000 AND d.pe>0 AND d.pe<=20 AND d.turnover_rate>=0.003 AND d.turnover_rate<=3.0"""
        },
        {
            'name': 'X08_SPX×T8低开尾拉',
            'desc': 'SPX前日涨 × 低开尾拉 × 底20% × VR≥1.3 × CM≤50亿 × TR 0.5-15%',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date WHERE b.pct_chg>=2 AND b.close_pos<=0.20 AND b.amp>=5.0 AND d.volume_ratio>=1.3 AND d.circ_mv>0 AND d.circ_mv<=500000 AND d.turnover_rate>=0.005 AND d.turnover_rate<=15.0 AND b.open<b.pre_close AND b.close>=b.high*0.95 AND b.close>b.open AND b.trade_date IN ({spx_prev_up})"""
        },
        {
            'name': 'X09_T4资金×T5基本面',
            'desc': '超大单净买入 × 净利增长≥10% × PE≤15 × PB≤2 × 底20% × VR≥1.2 × CM≤30亿',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}'), mf AS (SELECT * FROM tushare.tushare_moneyflow FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv, d.pe, d.pb FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date JOIN mf ON b.ts_code=mf.ts_code AND b.trade_date=mf.trade_date WHERE b.close_pos<=0.20 AND b.amp>=5.0 AND d.volume_ratio>=1.2 AND d.circ_mv>0 AND d.circ_mv<=300000 AND d.pe>0 AND d.pe<=15 AND d.pb>0 AND d.pb<=2 AND mf.buy_elg_amount>mf.sell_elg_amount AND b.ts_code IN {fina_sub}"""
        },
        {
            'name': 'X10_SPX×T6概念',
            'desc': 'SPX前日涨 × 多概念(≥2个) × 底20% × 涨幅≥2% × VR≥1.2 × CM≤30亿',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date WHERE b.pct_chg>=2 AND b.close_pos<=0.20 AND b.amp>=5.0 AND d.volume_ratio>=1.2 AND d.circ_mv>0 AND d.circ_mv<=300000 AND b.concept_cnt>=2 AND b.trade_date IN ({spx_prev_up})"""
        },
        {
            'name': 'X11_T3恐慌×T4资金×T8微盘',
            'desc': '恐慌(-5%) × 超大单净买入 × 微盘(≤15亿) × 底20% × VR≥1.3 × 振幅≥6% × PE≤20',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}'), mf AS (SELECT * FROM tushare.tushare_moneyflow FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv, d.pe FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date JOIN mf ON b.ts_code=mf.ts_code AND b.trade_date=mf.trade_date WHERE b.pct_chg<=-5 AND b.close_pos<=0.20 AND b.amp>=6.0 AND d.volume_ratio>=1.3 AND d.circ_mv>0 AND d.circ_mv<=150000 AND d.pe>0 AND d.pe<=20 AND mf.buy_elg_amount>mf.sell_elg_amount"""
        },
        {
            'name': 'X12_T8极致微盘×T6概念',
            'desc': '微盘(≤15亿)大阳(≥3%) × 多概念(≥2个) × 底20% × VR≥1.3 × 振幅≥6%',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date WHERE b.pct_chg>=3 AND b.close_pos<=0.20 AND b.amp>=6.0 AND d.volume_ratio>=1.3 AND d.circ_mv>0 AND d.circ_mv<=150000 AND d.turnover_rate>=0.003 AND b.concept_cnt>=2"""
        },
        {
            'name': 'X13_T4资金×T8大阳',
            'desc': '超大单净买入 × 底20%大阳(≥3%) × 振幅≥6% × VR≥1.5 × CM≤50亿 × 收阳',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}'), mf AS (SELECT * FROM tushare.tushare_moneyflow FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date JOIN mf ON b.ts_code=mf.ts_code AND b.trade_date=mf.trade_date WHERE b.pct_chg>=3 AND b.close_pos<=0.20 AND b.amp>=6.0 AND d.volume_ratio>=1.5 AND d.circ_mv>0 AND d.circ_mv<=500000 AND b.close>b.open AND mf.buy_elg_amount>mf.sell_elg_amount"""
        },
        {
            'name': 'X14_T3恐慌×T5价值',
            'desc': '深恐慌(-7%) × 深度价值(PE≤15,PB≤2) × 底20% × VR≥1.3 × CM≤30亿',
            'sql': """WITH base AS ({base_cte}), basic AS (SELECT * FROM tushare.tushare_daily_basic FINAL WHERE trade_date>='{start}')
SELECT b.*, d.volume_ratio, d.turnover_rate, d.circ_mv, d.pe, d.pb FROM base b JOIN basic d ON b.ts_code=d.ts_code AND b.trade_date=d.trade_date WHERE b.pct_chg<=-7 AND b.close_pos<=0.20 AND b.amp>=6.0 AND d.volume_ratio>=1.3 AND d.circ_mv>0 AND d.circ_mv<=300000 AND d.pe>0 AND d.pe<=15 AND d.pb>0 AND d.pb<=2"""
        },
    ]
    
    results = []
    for i, combo in enumerate(combos):
        name = combo['name']
        print(f"\n  [{i+1}/{len(combos)}] {name}")
        print(f"    {combo['desc']}")
        
        sql = make_sql(combo['sql'], base_cte, spx_up_str, fina_sub)
        result = run_sql_combo(name, sql)
        
        if 'error' in result:
            print(f"    ⚠️ Error: {result['error']}")
        else:
            status = "✅" if result['passed'] else "❌"
            print(f"    N={result['signals']}, WR={result['win_rate_5d']}%, R5={result['avg_ret_5d']}%, "
                  f"R10={result['avg_ret_10d']}%, R20={result['avg_ret_20d']}%, "
                  f"Sharpe={result['sharpe_5d']} {status}")
        
        result['desc'] = combo['desc']
        results.append(result)
    
    # Summary
    print("\n" + "=" * 90)
    print("ITER17 T9 RESULTS")
    print("=" * 90)
    print(f"{'Combo':30s} | {'N':>6s} | {'WR_5d':>7s} | {'R5':>6s} | {'R10':>6s} | {'R20':>6s} | {'Sharpe':>7s} | {'P10':>6s} |")
    print("-" * 90)
    
    passed_count = 0
    best = None
    best_score = -1
    
    for r in results:
        status = "✅" if r['passed'] else "❌"
        if r['passed']:
            passed_count += 1
            score = r['win_rate_5d'] * r['avg_ret_5d'] * min(r['signals'] / 500, 1.0)
            if score > best_score:
                best_score = score
                best = r
        print(f"{r['combo']:30s} | {r['signals']:>6d} | {r['win_rate_5d']:>6.2f}% | {r['avg_ret_5d']:>5.2f}% | {r['avg_ret_10d']:>5.2f}% | {r['avg_ret_20d']:>5.2f}% | {r['sharpe_5d']:>7.3f} | {r['p10_5d']:>5.2f}% | {status}")
    
    print(f"\nTotal: {len(results)} combos, {passed_count} passed ({passed_count/len(results)*100:.0f}%)")
    if best:
        print(f"\n🏆 BEST: {best['combo']} (score={best_score:.1f})")
    print(f"\nTotal time: {time.time() - t_start:.1f}s")
    
    # Save results
    out = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_17/t9_raw.json'
    with open(out, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nRaw results: {out}")
    
    # Generate report
    report = gen_report(results, best, best_score, passed_count)
    report_path = '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_17/analysis_T9_组合交叉.md'
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"Report: {report_path}")


def gen_report(results, best, best_score, passed_count):
    lines = []
    lines.append("# Iter17 T9: 组合交叉验证报告")
    lines.append("")
    lines.append(f"> 2026-05-13 | 数据: 2026-05-12 | 成功标准: WR≥52% AND R5≥3% AND N≥200")
    lines.append("")
    lines.append("## 组合结果总览")
    lines.append("")
    lines.append("| 组合 | N | WR_5d | R5 | R10 | R20 | Sharpe | P10 | 状态 |")
    lines.append("|------|----|-------|-----|-----|------|--------|-----|------|")
    
    for r in results:
        status = "✅" if r['passed'] else "❌"
        lines.append(f"| {r['combo']:30s} | {r['signals']:>6d} | {r['win_rate_5d']:>5.2f}% | {r['avg_ret_5d']:>5.2f}% | {r['avg_ret_10d']:>5.2f}% | {r['avg_ret_20d']:>5.2f}% | {r['sharpe_5d']:>6.3f} | {r['p10_5d']:>6.2f}% | {status} |")
    
    lines.append(f"\n**{len(results)}组, {passed_count}通过 ({passed_count/len(results)*100:.0f}%)**\n")
    
    if best and best.get('passed'):
        lines.append(f"## 🏆 最佳组合: {best['combo']}")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 描述 | {best.get('desc', '')} |")
        lines.append(f"| 信号数 (N) | {best['signals']} |")
        lines.append(f"| 5日胜率 (WR) | {best['win_rate_5d']}% |")
        lines.append(f"| 5日平均收益 (R5) | {best['avg_ret_5d']}% |")
        lines.append(f"| 10日平均收益 (R10) | {best['avg_ret_10d']}% |")
        lines.append(f"| 20日平均收益 (R20) | {best['avg_ret_20d']}% |")
        lines.append(f"| 夏普比率 | {best['sharpe_5d']} |")
        lines.append(f"| P10 (最差10%) | {best['p10_5d']}% |")
    
    lines.append("\n## 各组合参数详情\n")
    lines.append("| 组合 | 因子来源 | 参数 |")
    lines.append("|------|---------|------|")
    for r in results:
        lines.append(f"| {r['combo']:30s} | {r.get('desc', '')} |")
    
    # Stream analysis
    stream_combos = {
        'T3恐慌反转': ['X01', 'X02', 'X07', 'X11', 'X14'],
        'T4资金主力': ['X01', 'X03', 'X04', 'X05', 'X09', 'X11', 'X13'],
        'T5基本面估值': ['X06', 'X09', 'X14'],
        'T6板块轮动': ['X03', 'X06', 'X07', 'X10', 'X12'],
        'T7跨市场联动': ['X02', 'X08', 'X10'],
        'T8量价形态': ['X04', 'X05', 'X08', 'X11', 'X12', 'X13'],
    }
    
    lines.append("\n## 流源交叉分析\n")
    lines.append("| 流源 | 参与组合数 | 通过数 | 通过率 | 核心因子贡献 |")
    lines.append("|------|-----------|--------|--------|-------------|")
    
    for stream, prefixes in stream_combos.items():
        total = len(prefixes)
        actual_passed = sum(1 for p in prefixes for r in results if r['combo'].startswith(p) and r['passed'])
        core = {
            'T3恐慌反转': '恐慌跌幅(-5%~-7%), 筹码锁定(TR 0.3-3%)',
            'T4资金主力': '超大单净买入(buy_elg>sell_elg)',
            'T5基本面估值': '净利增长(≥10%), PE≤15, PB≤2',
            'T6板块轮动': '涨幅≥3%, 多概念(≥2), 振幅≥6%',
            'T7跨市场联动': 'SPX前日上涨',
            'T8量价形态': '低开尾拉, 大阳线, 极致微盘(≤15亿)',
        }.get(stream, '')
        rate = f"{actual_passed}/{total} ({actual_passed/total*100:.0f}%)"
        lines.append(f"| {stream} | {total} | {actual_passed} | {rate} | {core} |")
    
    lines.append("\n## 结论与建议\n")
    if best and best.get('passed'):
        lines.append(f"### 最佳交叉组合")
        lines.append(f"{best['combo']} 以综合评分 {best_score:.1f} 成为本轮最佳交叉组合。")
    
    lines.append("\n### 流源交叉有效性排序")
    
    stream_pass_rates = {}
    for stream, prefixes in stream_combos.items():
        total = len(prefixes)
        actual_passed = sum(1 for p in prefixes for r in results if r['combo'].startswith(p) and r['passed'])
        stream_pass_rates[stream] = (actual_passed, total)
    
    for stream, (ap, tot) in sorted(stream_pass_rates.items(), key=lambda x: -x[1][0]/max(x[1][1],1)):
        lines.append(f"- **{stream}**: {ap}/{tot} ({ap/tot*100:.0f}%)")
    
    lines.append("\n### 未达标组合分析\n")
    for r in results:
        if not r['passed']:
            lines.append(f"- **{r['combo']}**: N={r['signals']}, WR={r['win_rate_5d']}%, R5={r['avg_ret_5d']}% — {r.get('desc', '')}")
    
    return "\n".join(lines)


if __name__ == '__main__':
    main()
