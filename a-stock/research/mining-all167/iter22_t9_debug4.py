#!/usr/bin/env python3
"""T9 debug: Try POST body approach for complex SQL"""
import json, urllib.request, sys

HOST = "172.24.224.1"
HTTP_PORT = "8123"
USER = "ai_reader"
PASSWORD = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

def ch_post(sql):
    """Send SQL as POST body"""
    url = f"http://{HOST}:{HTTP_PORT}/?user={USER}&password={PASSWORD}&database=tushare&default_format=JSONEachRow"
    data = sql.encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'text/plain'})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode('utf-8')
            if not body.strip():
                return []
            return [json.loads(line) for line in body.strip().split('\n') if line.strip()]
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8')
        print(f"HTTP {e.code}: {err[:300]}", file=sys.stderr)
        return None

# Test 1: Simple
print("=== POST: Simple count ===")
sql1 = """
SELECT count() AS n
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
WHERE s.trade_date >= '2020-01-01'
  AND s.pct_chg >= 4
  AND (s.high - s.low) / NULLIF(s.pre_close, 0) * 100 >= 7
  AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
  AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
  AND s.trade_date <= '2026-05-06'
"""
r = ch_post(sql1)
print(f"Result: {r}")

# Test 2: WITH + window function via POST
print("\n=== POST: WITH + lead window function ===")
sql2 = """
WITH stock_filter AS (
    SELECT ts_code, trade_date, close, pct_chg,
           (high - low) / NULLIF(pre_close, 0) * 100 AS ampl,
           lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    WHERE s.trade_date >= '2020-01-01'
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
      AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
SELECT count() AS n,
       round(avg(ret_5d) * 100, 2) AS r5,
       round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
FROM stock_filter
WHERE pct_chg >= 4
  AND ampl >= 7
  AND trade_date <= '2026-05-06'
  AND ret_5d IS NOT NULL
"""
r = ch_post(sql2)
print(f"Result: {r}")

# If test 2 works, continue to JOIN tests
if r is not None:
    # Test 3: JOIN with daily_basic
    print("\n=== POST: WITH + daily_basic JOIN ===")
    sql3 = """
    WITH
    stock_filter AS (
        SELECT ts_code, trade_date, close, pct_chg,
               (high - low) / NULLIF(pre_close, 0) * 100 AS ampl,
               lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
        WHERE s.trade_date >= '2020-01-01'
          AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
          AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
    ),
    basic AS (
        SELECT ts_code, trade_date, pe, pb, circ_mv, volume_ratio
        FROM (SELECT * FROM tushare.tushare_daily_basic FINAL) AS d
        WHERE d.trade_date >= '2020-01-01'
          AND d.pe > 0 AND d.pe <= 15 AND d.pb > 0 AND d.pb <= 2 AND d.circ_mv <= 300000
    )
    SELECT count() AS n,
           round(avg(ret_5d) * 100, 2) AS r5,
           round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
    FROM stock_filter s
    INNER JOIN basic b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
    WHERE s.pct_chg >= 4
      AND s.ampl >= 7
      AND s.trade_date <= '2026-05-06'
      AND s.ret_5d IS NOT NULL
    """
    r = ch_post(sql3)
    print(f"Result: {r}")

    # Test 4: SPX JOIN
    print("\n=== POST: SPX JOIN ===")
    sql4 = """
    WITH
    spx AS (
        SELECT trade_date, pct_chg
        FROM (SELECT * FROM tushare.tushare_index_global FINAL) AS g
        WHERE g.ts_code = 'SPX' AND g.trade_date >= '2019-12-01'
    ),
    spx_lag AS (
        SELECT trade_date, lagInFrame(pct_chg, 1) OVER (ORDER BY trade_date) AS spx_prev_pct
        FROM spx
    ),
    stock_filter AS (
        SELECT ts_code, trade_date, close, pct_chg,
               (high - low) / NULLIF(pre_close, 0) * 100 AS ampl,
               lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
        WHERE s.trade_date >= '2020-01-01'
          AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
          AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
    )
    SELECT count() AS n,
           round(avg(ret_5d) * 100, 2) AS r5,
           round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
    FROM stock_filter s
    INNER JOIN spx_lag sp ON s.trade_date = sp.trade_date
    WHERE sp.spx_prev_pct > 0
      AND s.pct_chg >= 4
      AND s.ampl >= 7
      AND s.trade_date <= '2026-05-06'
      AND s.ret_5d IS NOT NULL
    """
    r = ch_post(sql4)
    print(f"Result: {r}")

    # Test 5: Moneyflow JOIN
    print("\n=== POST: Moneyflow JOIN ===")
    sql5 = """
    WITH
    stock_filter AS (
        SELECT ts_code, trade_date, close, pct_chg,
               (high - low) / NULLIF(pre_close, 0) * 100 AS ampl,
               lead(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) / close - 1 AS ret_5d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
        WHERE s.trade_date >= '2020-01-01'
          AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
          AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
    ),
    mf AS (
        SELECT ts_code, trade_date
        FROM (SELECT * FROM tushare.tushare_moneyflow FINAL) AS m
        WHERE m.trade_date >= '2020-01-01'
          AND m.sell_sm_vol > m.buy_sm_vol
          AND m.buy_elg_vol > m.sell_elg_vol
    )
    SELECT count() AS n,
           round(avg(ret_5d) * 100, 2) AS r5,
           round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) AS wr
    FROM stock_filter s
    INNER JOIN mf ON s.ts_code = mf.ts_code AND s.trade_date = mf.trade_date
    WHERE s.pct_chg >= 4
      AND s.ampl >= 7
      AND s.trade_date <= '2026-05-06'
      AND s.ret_5d IS NOT NULL
    """
    r = ch_post(sql5)
    print(f"Result: {r}")
