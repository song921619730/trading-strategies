SELECT 
    'C1: 60日深底放量恐慌(底10%+恐慌≤-5%+VR≥1.0+振幅≥7%+CM≤50亿)' as combo_name,
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
    SELECT 
        ts_code, trade_date, close,
        (leadInFrame(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / close - 1) * 100 as ret_5d,
        (leadInFrame(close, 10) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / close - 1) * 100 as ret_10d,
        (leadInFrame(close, 20) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) / close - 1) * 100 as ret_20d
    FROM (
        SELECT 
            d.ts_code AS ts_code, d.trade_date AS trade_date, d.close AS close, 
            d.pct_chg AS pct_chg, d.high AS high, d.low AS low, d.pre_close AS pre_close,
            MIN(d.low) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min_low_60d,
            MAX(d.high) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max_high_60d,
            db.volume_ratio AS volume_ratio, db.circ_mv AS circ_mv
        FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS d
        JOIN (SELECT * FROM tushare.tushare_stock_basic FINAL) AS b ON d.ts_code = b.ts_code
        LEFT JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS db ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date
        WHERE b.ts_code NOT LIKE '30%' AND b.ts_code NOT LIKE '688%' AND b.ts_code NOT LIKE '920%' AND b.ts_code NOT LIKE '%ST%'
    ) AS s
    WHERE 1=1
        AND s.pct_chg <= -5
        AND s.volume_ratio >= 1.0
        AND s.close <= s.min_low_60d + (s.max_high_60d - s.min_low_60d) * 0.1
        AND (s.high - s.low) / s.pre_close * 100 >= 7
        AND s.circ_mv <= 500000
) AS sub
FORMAT JSON
