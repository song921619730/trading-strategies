import clickhouse_connect
client = clickhouse_connect.get_client(host='192.168.0.30', port=18123, database='tushare')

r = client.query('SELECT max(trade_date) FROM tushare_stock_daily FINAL')
print(f'Latest trade_date: {r.result_rows[0][0]}')

# Check global index data
r2 = client.query('SELECT max(trade_date), count() FROM index_global FINAL')
print(f'index_global: latest={r2.result_rows[0][0]}, count={r2.result_rows[0][1]}')

# Check fx_daily
r3 = client.query('SELECT max(trade_date), count() FROM fx_daily FINAL')
print(f'fx_daily: latest={r3.result_rows[0][0]}, count={r3.result_rows[0][1]}')

# Check fut_daily
r4 = client.query('SELECT max(trade_date), count() FROM fut_daily FINAL')
print(f'fut_daily: latest={r4.result_rows[0][0]}, count={r4.result_rows[0][1]}')

# Check moneyflow
r5 = client.query('SELECT count(), max(trade_date) FROM moneyflow FINAL')
print(f'moneyflow: count={r5.result_rows[0][0]}, latest={r5.result_rows[0][1]}')

# Check global index codes
r6 = client.query("SELECT DISTINCT(ts_code) FROM index_global FINAL LIMIT 30")
print(f'Global index codes: {[r[0] for r in r6.result_rows]}')

# Check shibor
r7 = client.query('SELECT max(trade_date), count() FROM shibor FINAL')
print(f'shibor: latest={r7.result_rows[0][0]}, count={r7.result_rows[0][1]}')

# Check if hsgt_top10 (north bound) exists
r8 = client.query("SELECT max(trade_date), count() FROM hsgt_top10 FINAL")
print(f'hsgt_top10: latest={r8.result_rows[0][0]}, count={r8.result_rows[0][1]}')

# Check fut_daily for key commodities
r9 = client.query("SELECT DISTINCT(ts_code) FROM fut_daily FINAL LIMIT 30")
print(f'Futures codes: {[r[0] for r in r9.result_rows]}')

# Check cn_pmi
r10 = client.query('SELECT max(trade_date), count() FROM cn_pmi FINAL')
print(f'cn_pmi: latest={r10.result_rows[0][0]}, count={r10.result_rows[0][1]}')
