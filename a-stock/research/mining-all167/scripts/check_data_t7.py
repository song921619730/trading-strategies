#!/usr/bin/env python3
"""Check data availability for T7 cross-market linkage"""
from clickhouse_driver import Client
import json

client = Client(host='10.0.0.40', port=9000, user='default', password='gjtmux811', database='tushare')

# Check max trade_date
for tbl in ['tushare_stock_daily', 'tushare_moneyflow', 'tushare_daily_basic', 'tushare_index_global', 'tushare_limit_list_d', 'tushare_stk_limit']:
    r = client.execute(f'SELECT max(trade_date) FROM tushare.{tbl} FINAL')
    print(f'{tbl} max_date: {r[0][0]}')

# Check index codes
r = client.execute('SELECT DISTINCT ts_code FROM tushare.tushare_index_global FINAL ORDER BY ts_code LIMIT 30')
print(f'index codes: {[x[0] for x in r]}')

# SPX recent data
r = client.execute('SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code = \'SPX\' ORDER BY trade_date DESC LIMIT 5')
print(f'SPX: {r}')

# Check for VOLX/VIX
r = client.execute('SELECT DISTINCT ts_code FROM tushare.tushare_index_global FINAL WHERE ts_code LIKE \'%VOL%\' OR ts_code LIKE \'%VIX%\'')
print(f'VOL/VIX codes: {r}')

# Check HSI
r = client.execute('SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code = \'HSI\' ORDER BY trade_date DESC LIMIT 3')
print(f'HSI: {r}')

# Check hs300
r = client.execute('SELECT DISTINCT ts_code FROM tushare.tushare_index_global FINAL WHERE ts_code LIKE \'%300%\' OR ts_code LIKE \'%SH%\'')
print(f'CN index codes: {r}')

# Check amount stats
r = client.execute('SELECT min(amount), max(amount), min(circ_mv), max(circ_mv) FROM tushare.tushare_daily_basic FINAL WHERE trade_date = 20260513')
print(f'daily_basic 20260513 stats: {r}')

# Check moneyflow column names
r = client.execute('SELECT count() FROM tushare.tushare_moneyflow FINAL WHERE trade_date = 20260513 AND sell_sm > buy_sm')
print(f'moneyflow 20260513 sell_sm>buy_sm: {r[0][0]}')

r = client.execute('SELECT count() FROM tushare.tushare_moneyflow FINAL WHERE trade_date = 20260513 AND buy_lg > sell_lg')
print(f'moneyflow 20260513 buy_lg>sell_lg: {r[0][0]}')

# Stock count 
r = client.execute("SELECT count() FROM tushare.tushare_stock_daily FINAL WHERE trade_date = 20260513 AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'")
print(f'mainboard stocks 20260513: {r[0][0]}')

# Test a simple T7 query
r = client.execute("""
SELECT count()
FROM tushare.tushare_stock_daily FINAL d
WHERE d.trade_date = 20260513
  AND d.ts_code NOT LIKE '30%'
  AND d.ts_code NOT LIKE '688%'
  AND d.ts_code NOT LIKE '920%'
  AND d.ts_code NOT LIKE '%ST%'
  AND d.pct_chg <= -5
""")
print(f'恐慌>=5% on 20260513: {r[0][0]}')
