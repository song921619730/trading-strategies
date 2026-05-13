from clickhouse_driver import Client
client = Client(host='172.24.224.1', port=9000, user='ai_reader', password='OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

# 1. 检查 limit_list_d 表整体情况
print("=" * 70)
print("1. limit_list_d 总体数据量 & 时间范围")
print("=" * 70)
rows = client.execute("""
SELECT count() AS total,
       count(open_times) AS c_open_times,
       count(fd_amount) AS c_fd_amount,
       count(first_time) AS c_first_time,
       count(last_time) AS c_last_time,
       min(trade_date) AS min_dt,
       max(trade_date) AS max_dt
FROM tushare.tushare_limit_list_d FINAL
""")
print(f"total={rows[0][0]}, open_times有={rows[0][1]}, fd_amount有={rows[0][2]}, first_time有={rows[0][3]}, last_time有={rows[0][4]}")
print(f"min_date={rows[0][5]}, max_date={rows[0][6]}")

# 2. 按年份分组查看字段覆盖率
print("\n" + "=" * 70)
print("2. 按年份字段覆盖率")
print("=" * 70)
rows = client.execute("""
SELECT toYear(trade_date) AS yr,
       count() AS total,
       count(open_times) AS c_ot,
       count(fd_amount) AS c_fd,
       count(first_time) AS c_ft,
       count(last_time) AS c_lt,
       min(open_times) AS min_ot,
       max(open_times) AS max_ot,
       min(fd_amount) AS min_fd,
       max(fd_amount) AS max_fd
FROM tushare.tushare_limit_list_d FINAL
GROUP BY yr
ORDER BY yr
""")
for r in rows:
    yr, total, c_ot, c_fd, c_ft, c_lt, min_ot, max_ot, min_fd, max_fd = r
    print(f"{yr}: total={total:>8d}, open_times={c_ot:>8d}({c_ot/total*100:5.1f}%), fd_amount={c_fd:>8d}({c_fd/total*100:5.1f}%), "
          f"first_time={c_ft:>8d}({c_ft/total*100:5.1f}%), last_time={c_lt:>8d}({c_lt/total*100:5.1f}%) "
          f"| open_times range=[{min_ot},{max_ot}], fd_amount range=[{min_fd},{max_fd}]")

# 3. 检查非一字首板数据量（first_time != last_time）
print("\n" + "=" * 70)
print("3. 非一字首板（first_time != last_time）的数据量")
print("=" * 70)
rows = client.execute("""
SELECT toYear(trade_date) AS yr,
       count() AS total_limit,
       countIf(first_time != '' AND last_time != '' AND first_time != last_time) AS non_yizi
FROM tushare.tushare_limit_list_d FINAL
GROUP BY yr
ORDER BY yr
""")
for r in rows:
    print(f"{r[0]}: 总涨停={r[1]:>8d}, 非一字首板={r[2]:>8d}")

# 4. 检查 open_times=0 的比例
print("\n" + "=" * 70)
print("4. 未开板(open_times=0)占比")
print("=" * 70)
rows = client.execute("""
SELECT toYear(trade_date) AS yr,
       count() AS total,
       countIf(open_times = 0) AS no_open,
       countIf(open_times > 0) AS has_open,
       countIf(open_times IS NULL) AS null_ot
FROM tushare.tushare_limit_list_d FINAL
GROUP BY yr
ORDER BY yr
""")
for r in rows:
    print(f"{r[0]}: total={r[1]:>8d}, open_times=0={r[2]:>8d}({r[2]/max(r[1],1)*100:5.1f}%), open_times>0={r[3]:>8d}, null={r[4]:>8d}")

# 5. 检查 data_date 和 limit_times
print("\n" + "=" * 70)
print("5. limit_times 和 data_date 数据量检查")
print("=" * 70)
rows = client.execute("""
SELECT toYear(trade_date) AS yr,
       count(limit_times) AS c_lt2,
       count(data_date) AS c_dd
FROM tushare.tushare_limit_list_d FINAL
GROUP BY yr
ORDER BY yr
""")
for r in rows:
    print(f"{r[0]}: limit_times有={r[1]:>8d}, data_date有={r[2]:>8d}")

# 6. 查看最佳变体的可行信号数量
print("\n" + "=" * 70)
print("6. 各变体信号数量估算")
print("=" * 70)
rows = client.execute("""
SELECT toYear(trade_date) AS yr,
       countIf(first_time != '' AND last_time != '' AND first_time != last_time) AS base_non_yizi,
       countIf(first_time != '' AND last_time != '' AND first_time != last_time AND open_times = 0) AS v1_no_open,
       countIf(first_time != '' AND last_time != '' AND first_time != last_time AND first_time < '10:00') AS v2_early,
       countIf(first_time != '' AND last_time != '' AND first_time != last_time AND first_time < '11:30') AS v3_morning,
       countIf(first_time != '' AND last_time != '' AND first_time != last_time AND open_times = 0 AND first_time < '10:00') AS v6_strict
FROM tushare.tushare_limit_list_d FINAL
GROUP BY yr
ORDER BY yr
""")
for r in rows:
    print(f"{r[0]}: 非一字首板={r[1]:>8d}, v1(未开板)={r[2]:>8d}, v2(早封<10点)={r[3]:>8d}, v3(午前<11:30)={r[4]:>8d}, v6(未开+早封)={r[5]:>8d}")
