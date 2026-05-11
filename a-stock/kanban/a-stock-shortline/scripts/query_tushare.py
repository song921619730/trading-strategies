#!/usr/bin/env python3
"""Query Tushare ClickHouse for stock daily data."""
import requests

url = 'http://172.24.224.1:8123/'
auth = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

codes = [
    '688256.SH', '688521.SH', '688400.SH', '002805.SZ',
    '603119.SH', '000980.SZ', '600714.SH',
    '688699.SH', '603399.SH', '605123.SH', '605376.SH'
]

# Query 1: Latest 5 days
codes_str = "','".join(codes)
query1 = f"""
SELECT ts_code, trade_date, open, high, low, close, vol, pct_chg
FROM tushare.tushare_stock_daily FINAL
WHERE ts_code IN ('{codes_str}')
  AND trade_date >= '20260425'
ORDER BY ts_code, trade_date DESC
FORMAT TabSeparatedWithNames
"""

r = requests.get(url, params={'query': query1}, auth=auth, timeout=30)
print("=== LATEST 5 DAYS ===")
print(r.text)

# Query 2: Also check if 20260506 exists (May 6 trading)
query2 = f"""
SELECT DISTINCT trade_date
FROM tushare.tushare_stock_daily FINAL
WHERE trade_date >= '20260506' AND trade_date <= '20260507'
FORMAT TabSeparatedWithNames
"""
r2 = requests.get(url, params={'query': query2}, auth=auth, timeout=30)
print("\n=== TRADING DATES CHECK (May 6-7) ===")
print(r2.text)
