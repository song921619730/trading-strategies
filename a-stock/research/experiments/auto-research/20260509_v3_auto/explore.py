#!/usr/bin/env python3
"""
实验 20260509_v3_auto: 涨停股资金流向结构 vs 次日溢价
假设：涨停股的资金流向结构（大单/超大单占比）对次日溢价率和连板概率有显著预测能力
"""
import requests
import pandas as pd
import numpy as np
from io import StringIO

URL = 'http://172.24.224.1:8123/'
AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(query, fmt='TabSeparatedWithNames'):
    full = f"{query} FORMAT {fmt}"
    r = requests.get(URL, params={'query': full}, auth=AUTH, timeout=60)
    r.raise_for_status()
    return r.text

def ch_to_df(text):
    return pd.read_csv(StringIO(text), sep='\t')

# 1. 探索 limit_list_d 表结构
print("=== 1. limit_list_d 表结构 ===")
print(ch_query("DESCRIBE TABLE tushare.tushare_limit_list_d"))

print("\n=== 2. limit_list_d sample ===")
print(ch_query("SELECT * FROM tushare.tushare_limit_list_d FINAL LIMIT 3"))

# 3. moneyflow 表结构
print("\n=== 3. moneyflow 表结构 ===")
print(ch_query("DESCRIBE TABLE tushare.tushare_moneyflow"))

print("\n=== 4. moneyflow sample ===")
print(ch_query("SELECT * FROM tushare.tushare_moneyflow FINAL LIMIT 3"))

# 4. 检查数据范围
print("\n=== 5. limit_list_d 日期范围 ===")
print(ch_query("SELECT min(trade_date), max(trade_date), count() FROM tushare.tushare_limit_list_d FINAL"))

print("\n=== 6. moneyflow 日期范围 ===")
print(ch_query("SELECT min(trade_date), max(trade_date), count() FROM tushare.tushare_moneyflow FINAL"))

# 5. 检查 limit_list_d 中的关键字段
print("\n=== 7. limit_list_d 中的 limit_type 分布 ===")
print(ch_query("SELECT limit_type, count() FROM tushare.tushare_limit_list_d FINAL GROUP BY limit_type ORDER BY count() DESC LIMIT 10"))
