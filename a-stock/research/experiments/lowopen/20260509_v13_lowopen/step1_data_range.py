#!/usr/bin/env python3
"""查询tushare_stock_daily表的实际日期范围和基本统计"""
import requests

url = 'http://172.24.224.1:8123/'
auth = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

# 1. 查询日期范围
query = """
SELECT 
    min(trade_date) as min_date,
    max(trade_date) as max_date,
    count(DISTINCT trade_date) as unique_dates,
    count(DISTINCT ts_code) as unique_stocks,
    count() as total_rows
FROM tushare.tushare_stock_daily FINAL
"""
r = requests.get(url, params={'query': query}, auth=auth, timeout=30)
print("=== 数据范围 ===")
print(r.text)

# 2. 查询moneyflow表日期范围
query2 = """
SELECT 
    min(trade_date) as min_date,
    max(trade_date) as max_date,
    count() as total_rows
FROM tushare.tushare_moneyflow FINAL
"""
r2 = requests.get(url, params={'query': query2}, auth=auth, timeout=30)
print("=== 资金流数据范围 ===")
print(r2.text)

# 3. 查询limit_list_d日期范围
query3 = """
SELECT 
    min(trade_date) as min_date,
    max(trade_date) as max_date,
    count() as total_rows
FROM tushare.tushare_limit_list_d FINAL
"""
r3 = requests.get(url, params={'query': query3}, auth=auth, timeout=30)
print("=== 涨停数据范围 ===")
print(r3.text)

# 4. 查询daily_basic日期范围
query4 = """
SELECT 
    min(trade_date) as min_date,
    max(trade_date) as max_date,
    count() as total_rows
FROM tushare.tushare_daily_basic FINAL
"""
r4 = requests.get(url, params={'query': query4}, auth=auth, timeout=30)
print("=== daily_basic数据范围 ===")
print(r4.text)

# 5. 查询ths_daily日期范围
query5 = """
SELECT 
    min(trade_date) as min_date,
    max(trade_date) as max_date,
    count() as total_rows
FROM tushare.tushare_ths_daily FINAL
"""
r5 = requests.get(url, params={'query': query5}, auth=auth, timeout=30)
print("=== ths_daily数据范围 ===")
print(r5.text)
