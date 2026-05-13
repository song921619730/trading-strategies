SELECT s.trade_date, s.ts_code, s.close, s.pct_chg,
       b.pe_ttm, b.pb, b.circ_mv, b.volume_ratio
FROM (
  SELECT * FROM tushare.tushare_stock_daily FINAL
) AS s
INNER JOIN (
  SELECT * FROM tushare.tushare_daily_basic FINAL
) AS b ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
WHERE s.trade_date >= '20200101'
  AND s.trade_date <= '20260511'
  AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' 
  AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
  AND s.close <= s.low + (s.high - s.low) * 0.20
  AND (s.high - s.low) / s.pre_close * 100 >= 5
  AND b.pe_ttm <= 15
  AND b.pb <= 2
  AND b.circ_mv >= 300000 AND b.circ_mv <= 1000000
  AND b.volume_ratio >= 1.0
LIMIT 10
