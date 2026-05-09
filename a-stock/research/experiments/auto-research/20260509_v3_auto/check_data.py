#!/usr/bin/env python3
"""快速检查涨停数据"""
import requests
import pandas as pd
from io import StringIO

URL = 'http://172.24.224.1:8123/'
AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(query, fmt='TabSeparatedWithNames'):
    full = f"{query} FORMAT {fmt}"
    r = requests.get(URL, params={'query': full}, auth=AUTH, timeout=120)
    r.raise_for_status()
    return r.text

def ch_to_df(text):
    return pd.read_csv(StringIO(text), sep='\t')

# 检查 name 字段中 ST 的格式
print("=== ST 名称样例 ===")
print(ch_query("SELECT name FROM tushare.tushare_limit_list_d FINAL WHERE name LIKE '%ST%' LIMIT 10"))

print("\n=== 包含 ST 的总数 ===")
print(ch_query("SELECT count() FROM tushare.tushare_limit_list_d FINAL WHERE limit='U' AND name LIKE '%ST%'"))

print("\n=== 总涨停数（不限日期） ===")
print(ch_query("SELECT count() FROM tushare.tushare_limit_list_d FINAL WHERE limit='U'"))

print("\n=== 2024年涨停数 ===")
print(ch_query("SELECT count() FROM tushare.tushare_limit_list_d FINAL WHERE limit='U' AND trade_date >= '20240101' AND trade_date < '20250101'"))

print("\n=== 2025年涨停数 ===")
print(ch_query("SELECT count() FROM tushare.tushare_limit_list_d FINAL WHERE limit='U' AND trade_date >= '20250101' AND trade_date < '20260101'"))

print("\n=== 2026年涨停数 ===")
print(ch_query("SELECT count() FROM tushare.tushare_limit_list_d FINAL WHERE limit='U' AND trade_date >= '20260101' AND name NOT LIKE '%ST%' AND NOT (ts_code LIKE '8%' OR ts_code LIKE '4%')"))
