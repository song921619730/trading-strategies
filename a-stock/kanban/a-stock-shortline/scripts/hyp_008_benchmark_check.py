#!/usr/bin/env python3
"""
Quick check: test simpler gap-up conditions to understand the 78.25% benchmark.
"""
import requests, json

CLICKHOUSE_URL = 'http://172.24.224.1:8123/'
CLICKHOUSE_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def query(sql):
    r = requests.get(CLICKHOUSE_URL, auth=CLICKHOUSE_AUTH,
                     params={'query': sql, 'database': 'tushare'}, timeout=600)
    if r.status_code != 200:
        print(f"ERROR: {r.text[:300]}")
        return []
    lines = r.text.strip().split('\n')
    if len(lines) == 1 and lines[0] == '':
        return []
    return [line.split('\t') for line in lines]

# Check: What if we just look at gap-up >2% and see if after 20 days it's positive?
# No pullback condition, no volume condition.
# Use all main-board stocks.
print("=== Simple gap-up >2%, buy at T close, sell at T+20 close ===")
sql = """
SELECT 
    count() as total,
    countIf(close_20d > close) as wins,
    avg((close_20d - close) / close * 100) as avg_ret
FROM (
    SELECT 
        a.ts_code, a.trade_date, a.close,
        b.close as close_20d
    FROM (
        SELECT ts_code, trade_date, close, 
               row_number() OVER (PARTITION BY ts_code ORDER BY trade_date) as rn
        FROM tushare_stock_daily
        WHERE trade_date >= '2020-01-01' AND trade_date <= '2026-04-15'
          AND open >= pre_close * 1.02
    ) a
    JOIN (
        SELECT ts_code, trade_date, close,
               row_number() OVER (PARTITION BY ts_code ORDER BY trade_date) as rn
        FROM tushare_stock_daily
    ) b ON a.ts_code = b.ts_code AND a.rn + 20 = b.rn
)
"""
rows = query(sql)
for r in rows:
    total = float(r[0]); wins = float(r[1]); avg_ret = float(r[2])
    wr = wins/total*100 if total > 0 else 0
    print(f"Total: {total:.0f}, Wins: {wins:.0f}, WinRate: {wr:.2f}%, AvgRet: {avg_ret:.2f}%")

print()
print("=== Same but only main board (exclude 30%/688/920/ST) ===")
sql = """
SELECT 
    count() as total,
    countIf(close_20d > close) as wins,
    avg((close_20d - close) / close * 100) as avg_ret
FROM (
    SELECT 
        a.ts_code, a.trade_date, a.close,
        b.close as close_20d
    FROM (
        SELECT d.ts_code, d.trade_date, d.close, 
               row_number() OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) as rn
        FROM tushare_stock_daily d
        JOIN tushare_stock_basic b ON d.ts_code = b.ts_code
        WHERE d.trade_date >= '2020-01-01' AND d.trade_date <= '2026-04-15'
          AND d.open >= d.pre_close * 1.02
          AND b.market = '主板'
    ) a
    JOIN (
        SELECT ts_code, trade_date, close,
               row_number() OVER (PARTITION BY ts_code ORDER BY trade_date) as rn
        FROM tushare_stock_daily
    ) b ON a.ts_code = b.ts_code AND a.rn + 20 = b.rn
)
"""
rows = query(sql)
for r in rows:
    total = float(r[0]); wins = float(r[1]); avg_ret = float(r[2])
    wr = wins/total*100 if total > 0 else 0
    print(f"Total: {total:.0f}, Wins: {wins:.0f}, WinRate: {wr:.2f}%, AvgRet: {avg_ret:.2f}%")

print()
print("=== Gap-up + pullback (low >= prev_close) + volume shrink, buy at T close ===")
# The pullback condition is: T+1 to T+3, all lows >= prev_close (gap not filled)
sql = """
SELECT 
    count() as total,
    countIf(close_20d > close) as wins,
    avg((close_20d - close) / close * 100) as avg_ret
FROM (
    SELECT 
        a.ts_code, a.trade_date, a.close,
        b.close as close_20d
    FROM (
        SELECT d.ts_code, d.trade_date, d.close, d.pre_close, d.low as gap_low, d.vol as gap_vol,
               row_number() OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) as rn
        FROM tushare_stock_daily d
        JOIN tushare_stock_basic s ON d.ts_code = s.ts_code
        WHERE d.trade_date >= '2020-01-01' AND d.trade_date <= '2026-04-15'
          AND d.open >= d.pre_close * 1.02
          AND s.market = '主板'
    ) a
    JOIN (
        SELECT ts_code, trade_date, close,
               row_number() OVER (PARTITION BY ts_code ORDER BY trade_date) as rn
        FROM tushare_stock_daily
    ) b ON a.ts_code = b.ts_code AND a.rn + 20 = b.rn
    WHERE (
        SELECT count() 
        FROM (
            SELECT low, vol
            FROM tushare_stock_daily d2
            WHERE d2.ts_code = a.ts_code AND d2.trade_date > a.trade_date
            ORDER BY d2.trade_date
            LIMIT 3
        ) t
        WHERE t.low >= a.pre_close AND t.vol < a.gap_vol * 0.95
    ) > 0
)
"""
rows = query(sql)
for r in rows:
    total = float(r[0]); wins = float(r[1]); avg_ret = float(r[2])
    wr = wins/total*100 if total > 0 else 0
    print(f"Total: {total:.0f}, Wins: {wins:.0f}, WinRate: {wr:.2f}%, AvgRet: {avg_ret:.2f}%")
