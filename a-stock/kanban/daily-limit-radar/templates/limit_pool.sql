-- DLR 模板 01：涨停池初选
-- 用途：获取最近交易日的涨停股票池，用于初筛
-- 输入：无
-- 输出：涨停股票列表（含连板数、封单比、首次封板时间等）

SELECT
    ts_code,
    name,
    close,
    pct_chg,
    limit_times,
    fc_ratio,
    first_time,
    last_time,
    open_times,
    amp,
    turnover_rate
FROM tushare.tushare_limit_list_d FINAL
WHERE trade_date = (SELECT max(trade_date) FROM tushare.tushare_limit_list_d)
  AND limit_times > 0
  -- 排除 ST、*ST
  AND name NOT LIKE '%ST%'
  AND name NOT LIKE '%st%'
  -- 排除北交所（8 开头）
  AND ts_code NOT LIKE '8%'
  -- 排除科创板（688 开头）和创业板（300/301 开头），如果策略要求
  -- AND ts_code NOT LIKE '688%'
  -- AND ts_code NOT LIKE '300%'
  -- AND ts_code NOT LIKE '301%'
ORDER BY fc_ratio DESC, limit_times DESC
LIMIT 50
