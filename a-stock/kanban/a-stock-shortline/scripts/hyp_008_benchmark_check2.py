#!/usr/bin/env python3
"""Quick benchmark comparison - various gap-up conditions."""
import requests

def q(sql):
    r = requests.get('http://172.24.224.1:8123/', auth=('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ'),
                     params={'query': sql, 'database': 'tushare'}, timeout=300)
    if r.status_code != 200:
        print(f'ERROR: {r.text[:500]}')
        return []
    lines = r.text.strip().split('\n')
    return [line.split('\t') for line in lines if line]

# Test 1: Simple gap-up >2%, all stocks, buy T close, sell T+20
print("=== Test 1: Simple gap-up >2%, all A-shares, T->T+20 ===")
sql = """
SELECT count(), 
       countIf(closes[21] > close),
       avg((closes[21] - close) / close * 100)
FROM (
    SELECT ts_code, trade_date, close, 
           groupArray(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 21 FOLLOWING) as closes
    FROM tushare_stock_daily
    WHERE trade_date >= '2020-01-01' AND trade_date <= '2026-04-15'
      AND open >= pre_close * 1.02
)
WHERE length(closes) >= 21
"""
rows = q(sql)
for r in rows:
    t, w, a = float(r[0]), float(r[1]), float(r[2])
    print(f"  Total={t:.0f} WR={w/t*100:.2f}% AvgRet={a:.2f}%")

# Test 2: Main board only
print("\n=== Test 2: Gap-up >2%, main board only, T->T+20 ===")
sql = """
SELECT count(), 
       countIf(closes[21] > close),
       avg((closes[21] - close) / close * 100)
FROM (
    SELECT d.ts_code, d.trade_date, d.close, 
           groupArray(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 1 FOLLOWING AND 21 FOLLOWING) as closes
    FROM tushare_stock_daily d
    JOIN tushare_stock_basic b ON d.ts_code = b.ts_code
    WHERE d.trade_date >= '2020-01-01' AND d.trade_date <= '2026-04-15'
      AND d.open >= d.pre_close * 1.02
      AND b.market = '主板'
)
WHERE length(closes) >= 21
"""
rows = q(sql)
for r in rows:
    t, w, a = float(r[0]), float(r[1]), float(r[2])
    print(f"  Total={t:.0f} WR={w/t*100:.2f}% AvgRet={a:.2f}%")

# Test 3: Gap-up >2% + check low doesn't go below gap_low in T+1..T+3
print("\n=== Test 3: Gap-up >2%, low>=gap_low in T+1..T+3, main board ===")
sql = """
SELECT count(), 
       countIf(closes[21] > close),
       avg((closes[21] - close) / close * 100)
FROM (
    SELECT d.ts_code, d.trade_date, d.close, d.low as gap_low,
           groupArray(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 1 FOLLOWING AND 21 FOLLOWING) as closes,
           groupArray(d.low) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 1 FOLLOWING AND 3 FOLLOWING) as future_lows
    FROM tushare_stock_daily d
    JOIN tushare_stock_basic b ON d.ts_code = b.ts_code
    WHERE d.trade_date >= '2020-01-01' AND d.trade_date <= '2026-04-15'
      AND d.open >= d.pre_close * 1.02
      AND b.market = '主板'
)
WHERE length(closes) >= 21
  AND length(future_lows) >= 3
  AND arrayMin(future_lows) >= gap_low
"""
rows = q(sql)
for r in rows:
    t, w, a = float(r[0]), float(r[1]), float(r[2])
    print(f"  Total={t:.0f} WR={w/t*100:.2f}% AvgRet={a:.2f}%")

# Test 4: Same but buy at T+3 close (after pullback), sell at T+23
print("\n=== Test 4: Gap-up >2%, low>=gap_low in T+1..T+3, buy T+3 exit T+23 ===")
sql = """
SELECT count(), 
       countIf(closes[24] > closes[4]),
       avg((closes[24] - closes[4]) / closes[4] * 100)
FROM (
    SELECT d.ts_code, d.trade_date, d.close, d.low as gap_low,
           groupArray(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 1 FOLLOWING AND 24 FOLLOWING) as closes,
           groupArray(d.low) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 1 FOLLOWING AND 3 FOLLOWING) as future_lows
    FROM tushare_stock_daily d
    JOIN tushare_stock_basic b ON d.ts_code = b.ts_code
    WHERE d.trade_date >= '2020-01-01' AND d.trade_date <= '2026-04-15'
      AND d.open >= d.pre_close * 1.02
      AND b.market = '主板'
)
WHERE length(closes) >= 24
  AND length(future_lows) >= 3
  AND arrayMin(future_lows) >= gap_low
"""
rows = q(sql)
for r in rows:
    t, w, a = float(r[0]), float(r[1]), float(r[2])
    print(f"  Total={t:.0f} WR={w/t*100:.2f}% AvgRet={a:.2f}%")

# Test 5: Same as 3 but with volume shrink condition
print("\n=== Test 5: + volume shrink, buy T close, exit T+20 ===")
sql = """
SELECT count(), 
       countIf(closes[21] > close),
       avg((closes[21] - close) / close * 100)
FROM (
    SELECT d.ts_code, d.trade_date, d.close, d.low as gap_low, d.vol as gap_vol,
           groupArray(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 1 FOLLOWING AND 21 FOLLOWING) as closes,
           groupArray(d.low) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 1 FOLLOWING AND 3 FOLLOWING) as future_lows,
           groupArray(d.vol) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 1 FOLLOWING AND 3 FOLLOWING) as future_vols
    FROM tushare_stock_daily d
    JOIN tushare_stock_basic b ON d.ts_code = b.ts_code
    WHERE d.trade_date >= '2020-01-01' AND d.trade_date <= '2026-04-15'
      AND d.open >= d.pre_close * 1.02
      AND b.market = '主板'
)
WHERE length(closes) >= 21
  AND length(future_lows) >= 3
  AND arrayMin(future_lows) >= gap_low
  AND arrayExists(x -> x < gap_vol * 0.95, future_vols)
"""
rows = q(sql)
for r in rows:
    t, w, a = float(r[0]), float(r[1]), float(r[2])
    print(f"  Total={t:.0f} WR={w/t*100:.2f}% AvgRet={a:.2f}%")
