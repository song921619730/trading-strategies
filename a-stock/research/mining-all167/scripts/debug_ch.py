#!/usr/bin/env python3
"""Debug - check response format from ch_query"""
import json, sys, os
from urllib.request import Request, urlopen

CH_URL = "http://172.24.224.1:8123"
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

def ch_query(sql):
    url = f"{CH_URL}/?default_format=JSONCompact"
    req = Request(url, data=sql.encode('utf-8'))
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    import base64
    auth = base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode()
    req.add_header('Authorization', f'Basic {auth}')
    resp = urlopen(req, timeout=120)
    raw = resp.read().decode('utf-8')
    print(f"Raw response type: {type(raw)}")
    print(f"Raw response length: {len(raw)}")
    print(f"First 500 chars: {raw[:500]}")
    data = json.loads(raw)
    print(f"Parsed type: {type(data)}")
    if isinstance(data, list):
        print(f"List length: {len(data)}")
        print(f"First item type: {type(data[0])}")
        print(f"First item: {json.dumps(data[0], indent=2)[:500]}")
    elif isinstance(data, dict):
        print(f"Dict keys: {list(data.keys())}")
    return data

# Test with a simple query
sql = """
SELECT count() AS signal_count 
FROM tushare.tushare_stock_daily FINAL 
WHERE trade_date = toDate('2026-05-06') 
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' 
  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
"""
r = ch_query(sql)
print(f"\nResult: {r}")
