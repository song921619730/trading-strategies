SELECT 
    'C8: 缩量企稳反弹(前日跌≥-3%+今日止跌0~3%+缩量VR0.3~0.8+底20%+PE≤30+CM≤50亿)' as combo_name,
    count(DISTINCT ts_code) as unique_stocks,
    count(*) as signal_count,
    round(avg(ret_5d), 2) as avg_ret_5d,
    round(avg(ret_10d), 2) as avg_ret_10d,
    round(avg(ret_20d), 2) as avg_ret_20d,
    round(count(CASE WHEN ret_5d > 0 THEN 1 END) * 100.0 / count(*), 2) as win_rate_5d,
    round(avg(ret_5d) / (stddevSamp(ret_5d) + 0.0001) * sqrt(252.0/5.0), 3) as sharpe_5d,
    round(quantile(0.1)(ret_5d), 2) as p10_ret_5d,
    round(quantile(0.9)(ret_5d), 2) as p90_ret_5d
FROM (
    SELECT ts_code, trade_date, close,
        (leadInFrame(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / close - 1) * 100 as ret_5d,
        (leadInFrame(close, 10) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / close - 1) * 100 as ret_10d,
        (leadInFrame(close, 20) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / close - 1) * 100 as ret_20d
    FROM (
        SELECT d.ts_code AS ts_code, d.trade_date AS trade_date, d.close AS close,
            d.pct_chg AS pct_chg, d.pre_close AS pre_close, (d.high - d.low) / d.pre_close * 100 AS amp,
            lagInFrame(d.pct_chg, 1) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS prev_pct_chg,
            db.volume_ratio AS volume_ratio, db.circ_mv AS circ_mv, db.pe AS pe, db.pb AS pb,
            MIN(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min_close_60d,
            MAX(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max_close_60d
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS d
        JOIN (SELECT * FROM tushare.tushare_stock_basic FINAL) AS b ON d.ts_code = b.ts_code
        LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date
        WHERE b.ts_code NOT LIKE '30%' AND b.ts_code NOT LIKE '688%' AND b.ts_code NOT LIKE '920%' AND b.ts_code NOT LIKE '%ST%'
    ) AS s
    WHERE 1=1
        AND s.prev_pct_chg <= -3
        AND s.pct_chg BETWEEN 0 AND 3
        AND s.volume_ratio BETWEEN 0.3 AND 0.8
        AND s.amp >= 3
        AND s.close <= s.min_close_60d + (s.max_close_60d - s.min_close_60d) * 0.2
        AND s.pe <= 30
        AND s.circ_mv <= 500000
) AS sub
FORMAT JSON
