-- DLR 模板 04：10 因子数据预计算（简化版 — 直接拉原始数据）
-- 用途：从 Tushare DB 拉取候选股的完整原始数据，供 LLM 分析
-- 优势：167 张表、5 年历史数据，全在库里，不用在 SQL 层计算

-- ============================================================
-- ① 日线数据：近 120 日（约半年）
--    直接拉 OHLCV，LLM 从原始数据看趋势/均线/形态
-- ============================================================
SELECT
    d.ts_code,
    d.trade_date,
    d.open,
    d.high,
    d.low,
    d.close,
    d.vol,
    d.amount,
    d.pct_chg,
    d.turnover_rate
FROM tushare.tushare_stock_daily d FINAL
WHERE d.ts_code IN ({ts_code_list})
  AND d.trade_date >= (
      SELECT toString(dateSub(DAY, 150, toDateTime(max(trade_date))))
      FROM tushare.tushare_stock_daily FINAL
      WHERE ts_code IN ({ts_code_list})
  )
ORDER BY d.ts_code, d.trade_date ASC;


-- ============================================================
-- ② 估值数据：近 120 日（PE/PB/市值/换手率/量比）
--    daily_basic 表有现成的所有估值指标
-- ============================================================
SELECT
    ts_code,
    trade_date,
    pe,
    pb,
    total_mv,
    circ_mv,
    turnover_rate,
    turnover_rate_f,
    volume_ratio,
    ps
FROM tushare.tushare_daily_basic FINAL
WHERE ts_code IN ({ts_code_list})
  AND trade_date >= (
      SELECT toString(dateSub(DAY, 150, toDateTime(max(trade_date))))
      FROM tushare.tushare_daily_basic FINAL
      WHERE ts_code IN ({ts_code_list})
  )
ORDER BY ts_code, trade_date ASC;


-- ============================================================
-- ③ 资金流向：近 60 日（主力/超大单/大单/中单/小单）
--    moneyflow 表有现成的分类资金流向
-- ============================================================
SELECT
    ts_code,
    trade_date,
    buy_sm_vol, sell_sm_vol,
    buy_md_vol, sell_md_vol,
    buy_lg_vol, sell_lg_vol,
    buy_elg_vol, sell_elg_vol,
    -- 主力净流入（大单 + 超大单）
    (buy_lg_vol + buy_elg_vol - sell_lg_vol - sell_elg_vol) as main_net_vol,
    -- 超大单净流入
    (buy_elg_vol - sell_elg_vol) as elg_net_vol,
    -- 散户净流入
    (buy_sm_vol + buy_md_vol - sell_sm_vol - sell_md_vol) as retail_net_vol
FROM tushare.tushare_moneyflow FINAL
WHERE ts_code IN ({ts_code_list})
  AND trade_date >= (
      SELECT toString(dateSub(DAY, 65, toDateTime(max(trade_date))))
      FROM tushare.tushare_moneyflow FINAL
      WHERE ts_code IN ({ts_code_list})
  )
ORDER BY ts_code, trade_date ASC;


-- ============================================================
-- ④ 涨停历史：近 60 日（连板数/封单比/首次封板时间）
-- ============================================================
SELECT
    ts_code,
    trade_date,
    limit_times,
    fc_ratio,
    first_time,
    last_time,
    open_times,
    amp
FROM tushare.tushare_limit_list_d FINAL
WHERE ts_code IN ({ts_code_list})
  AND trade_date >= (
      SELECT toString(dateSub(DAY, 65, toDateTime(max(trade_date))))
      FROM tushare.tushare_limit_list_d FINAL
      WHERE ts_code IN ({ts_code_list})
  )
ORDER BY ts_code, trade_date ASC;


-- ============================================================
-- ⑤ 板块趋势：候选股所属板块近 60 日涨停数变化
-- ============================================================
SELECT
    c.concept_name,
    l.trade_date,
    count(*) as limit_count,
    avg(l.limit_times) as avg_limit_times,
    groupArray(l.ts_code) as limit_stocks
FROM tushare.tushare_concept_detail c FINAL
JOIN tushare.tushare_limit_list_d l FINAL ON c.ts_code = l.ts_code
WHERE l.trade_date >= (
    SELECT toString(dateSub(DAY, 65, toDateTime(max(trade_date))))
    FROM tushare.tushare_limit_list_d FINAL
)
  AND c.concept_name IS NOT NULL AND c.concept_name != ''
  AND c.ts_code IN ({ts_code_list})
GROUP BY c.concept_name, l.trade_date
ORDER BY c.concept_name, l.trade_date ASC;


-- ============================================================
-- ⑥ 北向资金：近 30 日（市场情绪参考）
-- ============================================================
SELECT
    trade_date,
    north_money,
    south_money,
    gg_buy,
    gg_sell,
    north_money - lagInFrame(north_money, 1) OVER (ORDER BY trade_date) as north_net_change
FROM tushare.tushare_moneyflow_hsgt FINAL
WHERE trade_date >= (
    SELECT toString(dateSub(DAY, 35, toDateTime(max(trade_date))))
    FROM tushare.tushare_moneyflow_hsgt FINAL
)
ORDER BY trade_date ASC;


-- ============================================================
-- ⑦ 基本面：最新财报（PE/PB/ROE/净利润/营收）
-- ============================================================
SELECT
    b.ts_code,
    b.name,
    b.industry,
    b.area,
    b.market,
    db_latest.pe,
    db_latest.pb,
    db_latest.total_mv,
    db_latest.circ_mv,
    fi_latest.roe,
    fi_latest.roa,
    fi_latest.grossprofit_margin,
    fi_latest.netprofit_margin,
    inc_latest.revenue,
    inc_latest.n_income,
    inc_latest.basic_eps
FROM tushare.tushare_stock_basic b FINAL
LEFT JOIN (
    SELECT ts_code, pe, pb, total_mv, circ_mv
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date = (SELECT max(trade_date) FROM tushare.tushare_daily_basic)
) db_latest ON b.ts_code = db_latest.ts_code
LEFT JOIN (
    SELECT ts_code, roe, roa, grossprofit_margin, netprofit_margin
    FROM tushare.tushare_fina_indicator FINAL
    WHERE end_date = (SELECT max(end_date) FROM tushare.tushare_fina_indicator WHERE ts_code IN ({ts_code_list}))
) fi_latest ON b.ts_code = fi_latest.ts_code
LEFT JOIN (
    SELECT ts_code, revenue, n_income, basic_eps
    FROM tushare.tushare_income FINAL
    WHERE end_date = (SELECT max(end_date) FROM tushare.tushare_income WHERE ts_code IN ({ts_code_list}))
) inc_latest ON b.ts_code = inc_latest.ts_code
WHERE b.ts_code IN ({ts_code_list})
ORDER BY b.ts_code;
