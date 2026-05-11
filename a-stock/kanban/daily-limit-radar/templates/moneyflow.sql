-- DLR 模板 05：资金流向查询
-- 用途：获取候选股近 5 日资金流向数据
-- 输入：{ts_code_list} 候选股票代码列表
-- 输出：资金流向明细（大单/超大单净买入）

SELECT
    m.ts_code,
    b.name,
    m.trade_date,
    m.buy_sm_vol,
    m.sell_sm_vol,
    m.buy_md_vol,
    m.sell_md_vol,
    m.buy_lg_vol,
    m.sell_lg_vol,
    m.buy_elg_vol,
    m.sell_elg_vol,
    -- 超大单净流入（手）
    (m.buy_elg_vol - m.sell_elg_vol) as elg_net_vol,
    -- 大单净流入（手）
    (m.buy_lg_vol - m.sell_lg_vol) as lg_net_vol,
    -- 主力净流入 = 大单 + 超大单
    (m.buy_lg_vol + m.buy_elg_vol - m.sell_lg_vol - m.sell_elg_vol) as main_net_vol
FROM tushare.tushare_moneyflow m FINAL
INNER JOIN tushare.tushare_stock_basic b FINAL ON m.ts_code = b.ts_code
WHERE m.ts_code IN ({ts_code_list})
  AND m.trade_date >= (
    SELECT toString(dateSub(DAY, 5, toDateTime(max(trade_date))))
    FROM tushare.tushare_stock_daily FINAL
  )
ORDER BY m.ts_code, m.trade_date DESC
