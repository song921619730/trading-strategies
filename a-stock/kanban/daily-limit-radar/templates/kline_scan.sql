-- DLR 模板 03：K 线形态扫描（候选股）
-- 用途：获取候选股近 20 日日线数据，用于技术面分析
-- 输入：{ts_code_list} 逗号分隔的股票代码
-- 输出：近 20 日 OHLCV 数据

WITH target_codes AS (
    -- 在此填入候选股票代码
    SELECT arrayJoin(['{ts_code_list}']) as ts_code
)
SELECT
    d.ts_code,
    b.name,
    d.trade_date,
    d.open,
    d.high,
    d.low,
    d.close,
    d.vol,
    d.amount,
    d.pct_chg,
    db.turnover_rate,
    db.pe,
    db.pb,
    db.total_mv,
    db.circ_mv
FROM tushare.tushare_stock_daily d FINAL
INNER JOIN tushare.tushare_stock_basic b FINAL ON d.ts_code = b.ts_code
LEFT JOIN tushare.tushare_daily_basic db FINAL
  ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date
WHERE d.ts_code IN (SELECT ts_code FROM target_codes)
  AND d.trade_date >= (
    SELECT toString(min(trade_date))
    FROM (
      SELECT trade_date
      FROM tushare.tushare_stock_daily FINAL
      WHERE ts_code IN (SELECT ts_code FROM target_codes)
      ORDER BY trade_date DESC
      LIMIT 20
    )
  )
ORDER BY d.ts_code, d.trade_date DESC
