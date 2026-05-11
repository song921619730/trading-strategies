# T3 反转低吸 视角 — Iter 1

**数据基准日**: 2026-05-08  
**系统执行时间**: 2026-05-11 15:02 UTC+8  
**角色**: 策略挖掘分析师（反转低吸视角）

**回测方法**: 信号触发日买入，计算T+1/T+3/T+5/T+10/T+20交易日收益  

**成功标准**: WR >= 52% AND 5D收益 >= 3% AND 信号数 >= 200

## 测试参数组合（5 组）

### 组合 1: 超跌空头排列放量反转
- **参数**: close_position=底20%, volume_ratio_min=1.5, ma_arrangement=空头排列, pct_chg_1d_min=-5, turnover_rate_min=0.01
- **描述**: close在20日区间底20% + 量比>=1.5 + MA5<MA10<MA20 + 当日跌幅>=-5% + 换手>=1%
- **Hash**: 611d0402f916
- **信号数**: 17941
- **T+1d**: WR=52.98%, ret=0.27%, sharpe=0.9
- **T+3d**: WR=58.76%, ret=1.71%, sharpe=1.97
- **T+5d**: WR=59.92%, ret=2.67%, sharpe=1.96
- **T+10d**: WR=62.34%, ret=4.76%, sharpe=1.75
- **T+20d**: WR=62.88%, ret=6.03%, sharpe=1.36
- **SQL**:
```sql
WITH daily AS (
    SELECT ts_code, trade_date, close, pct_chg, vol,
        AVG(close) OVER w5 AS ma5,
        AVG(close) OVER w10 AS ma10,
        AVG(close) OVER w20 AS ma20,
        MIN(low) OVER w20 AS min20,
        MAX(high) OVER w20 AS max20
    FROM tushare_stock_daily FINAL
    WHERE ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%' AND ts_code NOT LIKE '920%%'
      AND trade_date <= '2026-05-08'
    WINDOW
        w5 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
        w10 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),
        w20 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
)
SELECT ts_code, trade_date, close, pct_chg, vol
FROM daily
WHERE pct_chg <= -5.0
  AND ma5 < ma10 AND ma10 < ma20
  AND (max20 - min20) > 0
  AND (close - min20) / (max20 - min20) <= 0.20
```

### 组合 2: 资金净流入+近期跌停+中小盘
- **参数**: net_mf_min=5000000, was_limit_down_recent=True, market_cap_bucket=中小盘(30-100亿), pct_chg_1d_max=5, turnover_rate_max=0.2
- **描述**: 主力净流入>=500万 + 近期跌停过 + 流通市值30-100亿 + 当日涨幅<=5% + 换手<=20%
- **Hash**: ca89ba9c1cbb
- **信号数**: 0
- **错误**: no daily_basic data

### 组合 3: 筹码集中+向下跳空+低换手
- **参数**: cyq_concentration=高度集中(>70%), gap_direction=向下跳空, turnover_rate_min=0.005, turnover_rate_max=0.1, holder_num_chg_3q=减少>10%, amplitude_min=3
- **描述**: 筹码集中度>70%(winner_rate) + 向下跳空缺口 + 换手0.5%-10% + 振幅>=3%
- **Hash**: 6e6fd2719c40
- **信号数**: 0
- **错误**: HTTP Error 404: Not Found

### 组合 4: 低PE+低PB+MA20支撑+缩量
- **参数**: pe_max=15, pb_max=2, ma_support=MA20, volume_ratio_max=1.5, roe_min=0.1, pct_chg_1d_min=-3
- **描述**: PE_TTM<=15 + PB<=2 + 回踩MA20(2%内) + 量比<=1.5 + 当日跌幅>=-3%
- **Hash**: 6b9737d51dc2
- **信号数**: 4460
- **T+1d**: WR=58.54%, ret=0.52%, sharpe=2.5
- **T+3d**: WR=53.7%, ret=1.07%, sharpe=1.88
- **T+5d**: WR=49.31%, ret=0.77%, sharpe=0.81
- **T+10d**: WR=53.76%, ret=1.36%, sharpe=0.76
- **T+20d**: WR=49.85%, ret=1.5%, sharpe=0.42
- **SQL**:
```sql
WITH daily AS (
    SELECT ts_code, trade_date, close, pct_chg,
        AVG(close) OVER w20 AS ma20
    FROM tushare_stock_daily FINAL
    WHERE ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%' AND ts_code NOT LIKE '920%%'
      AND trade_date <= '2026-05-08'
    WINDOW w20 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
)
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, d.ma20
FROM daily d
WHERE d.ma20 > 0 AND ABS(d.close - d.ma20) / d.ma20 <= 0.02 AND d.pct_chg <= -3.0
```

### 组合 5: 振幅大+金叉+北向+涨停
- **参数**: fc_ratio_min=0.3, amplitude_min=7, north_net_inflow=净流入>0, concept_count_max=2, pct_chg_1d_min=-2, pct_chg_1d_max=3, ma_arrangement=金叉
- **描述**: 振幅>=7% + 涨幅-2%~3% + MA5金叉MA10 + 北向净流入>0
- **Hash**: 19f1d1da98a2
- **信号数**: 0
- **错误**: HTTP Error 404: Not Found

## 最佳发现

- **参数组合**: close_position=底20%, volume_ratio_min=1.5, ma_arrangement=空头排列, pct_chg_1d_min=-5, turnover_rate_min=0.01
- **策略**: 超跌空头排列放量反转
- **信号数**: 17941
- **T+1d**: WR=52.98%, ret=0.27%, sharpe=0.9
- **T+3d**: WR=58.76%, ret=1.71%, sharpe=1.97
- **T+5d**: WR=59.92%, ret=2.67%, sharpe=1.96
- **T+10d**: WR=62.34%, ret=4.76%, sharpe=1.75
- **T+20d**: WR=62.88%, ret=6.03%, sharpe=1.36
- **描述**: close在20日区间底20% + 量比>=1.5 + MA5<MA10<MA20 + 当日跌幅>=-5% + 换手>=1%
- **达标状态**: FAIL
- **未达标原因**: ret_5d=2.67%<3%

## 所有组合 Hash（用于去重）

611d0402f916, ca89ba9c1cbb, 6e6fd2719c40, 6b9737d51dc2, 19f1d1da98a2