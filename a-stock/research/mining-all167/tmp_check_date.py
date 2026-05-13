#!/usr/bin/env python3
"""Check latest trade date from ClickHouse"""
from clickhouse_driver import Client
c = Client(host='localhost')
rows = c.execute('SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL')
print('max trade_date:', rows[0][0])

# Also check available moneyflow and daily_basic dates
rows2 = c.execute('SELECT max(trade_date) FROM tushare.tushare_moneyflow FINAL')
print('max moneyflow date:', rows2[0][0])

rows3 = c.execute('SELECT max(trade_date) FROM tushare.tushare_daily_basic FINAL')
print('max daily_basic date:', rows3[0][0])

# Check fina_indicator for PE/PB
rows4 = c.execute('SELECT max(trade_date) FROM tushare.tushare_fina_indicator FINAL')
print('max fina_indicator date:', rows4[0][0])

# Check index_global for SPX
rows5 = c.execute("SELECT max(trade_date) FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX'")
print('max SPX date:', rows5[0][0])
