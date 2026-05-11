# T8 量价形态 视角 — Iter 1

> 数据基准: 2026-05-08 | 执行时间: 2026-05-11 15:02 UTC+8
> 角色: 策略挖掘分析师 (量价形态视角)
> 回测范围: 2023-01-01 ~ 2026-05-08 (近3年, 采样20万条)
> 基础过滤: 排除30/688/920/ST, amount>=1亿
> 成功标准: WR>=52% AND 5D收益>=3% AND 信号数>=200

## 测试参数组合 (5 组)

### 组合 1: 放量突破20日新高
- **域**: 价格行为+量能
- **参数**: n_day_high=20, volume_ratio_min=2.0, close_position=顶20%, pct_chg_1d_min=2
- **逻辑**: 股价位于20日区间顶部80%+, 量比>=2, 当日涨幅>=2%
- **条件**: `pos_20d>=0.80 AND vol_ratio>=2.0 AND pct_chg>=2.0`
- **结果**: 信号数=9499
  - 1D: WR=44.46%, ret=0.09%, sharpe=0.293
  - 3D: WR=43.34%, ret=-0.09%, sharpe=-0.092
  - 5D: WR=40.99%, ret=-0.38%, sharpe=-0.239
  - 10D: WR=39.76%, ret=-0.69%, sharpe=-0.237
  - 20D: WR=39.96%, ret=-0.54%, sharpe=-0.1
- **判定**: 未达标准 — WR_5d=40.99%<52%, ret_5d=-0.38%<3%

### 组合 2: 均线多头排列+温和放量
- **域**: 均线系统+量能
- **参数**: ma_arrangement=多头排列, volume_ratio_min=1.5, pct_chg_1d_min=0
- **逻辑**: MA5>MA10>MA20多头排列, 量比>=1.5温和放量, 非下跌日
- **条件**: `ma5>ma10>ma20 AND vol_ratio>=1.5 AND pct_chg>=0`
- **结果**: 信号数=31158
  - 1D: WR=43.37%, ret=-0.03%, sharpe=-0.082
  - 3D: WR=42.44%, ret=-0.23%, sharpe=-0.251
  - 5D: WR=40.79%, ret=-0.43%, sharpe=-0.285
  - 10D: WR=41.45%, ret=-0.38%, sharpe=-0.14
  - 20D: WR=42.52%, ret=-0.01%, sharpe=-0.003
- **判定**: 未达标准 — WR_5d=40.79%<52%, ret_5d=-0.43%<3%

### 组合 3: 大阳线放量(涨停附近)
- **域**: 价格行为+量能+涨停
- **参数**: pct_chg_1d_min=7, volume_ratio_min=1.0, amplitude_min=5
- **逻辑**: 当日涨幅>=7%, 振幅>=5%, 量比>=1 — 大阳线强势形态
- **条件**: `pct_chg>=7.0 AND vol_ratio>=1.0 AND amplitude>=5%`
- **结果**: 信号数=38137
  - 1D: WR=52.64%, ret=1.04%, sharpe=2.629
  - 3D: WR=46.82%, ret=0.67%, sharpe=0.553
  - 5D: WR=45.63%, ret=0.53%, sharpe=0.276
  - 10D: WR=46.25%, ret=0.98%, sharpe=0.28
  - 20D: WR=47.32%, ret=2.09%, sharpe=0.32
- **判定**: 未达标准 — WR_5d=45.63%<52%, ret_5d=0.53%<3%

### 组合 4: 向上跳空+中小幅上涨
- **域**: 价格行为+量能
- **参数**: gap_direction=向上跳空, pct_chg_1d_min=1, pct_chg_1d_max=5, volume_ratio_min=1.2
- **逻辑**: 跳空高开>=1%, 涨幅1-5%温和, 量比>=1.2
- **条件**: `gap_pct>=0.01 AND 1.0<=pct_chg<=5.0 AND vol_ratio>=1.2`
- **结果**: 信号数=22146
  - 1D: WR=44.66%, ret=-0.23%, sharpe=-0.846
  - 3D: WR=45.89%, ret=0.05%, sharpe=0.058
  - 5D: WR=46.3%, ret=0.19%, sharpe=0.141
  - 10D: WR=47.7%, ret=0.81%, sharpe=0.31
  - 20D: WR=47.84%, ret=1.76%, sharpe=0.331
- **判定**: 未达标准 — WR_5d=46.3%<52%, ret_5d=0.19%<3%

### 组合 5: 底部放量(超跌反弹)
- **域**: 价格位置+量能
- **参数**: close_position=底20%, volume_ratio_min=1.5, pct_chg_1d_min=0
- **逻辑**: 股价位于20日底部20%以内, 量比>=1.5放量, 当日不跌
- **条件**: `pos_20d<=0.20 AND vol_ratio>=1.5 AND pct_chg>=0`
- **结果**: 信号数=3002
  - 1D: WR=42.63%, ret=-0.14%, sharpe=-0.456
  - 3D: WR=47.75%, ret=0.58%, sharpe=0.578
  - 5D: WR=49.95%, ret=1.28%, sharpe=0.778
  - 10D: WR=53.86%, ret=2.77%, sharpe=0.844
  - 20D: WR=55.65%, ret=5.17%, sharpe=0.791
- **判定**: 未达标准 — WR_5d=49.95%<52%, ret_5d=1.28%<3%

## 最佳发现

- **最佳参数**: 底部放量(超跌反弹)
- **参数组合**: close_position=底20%, volume_ratio_min=1.5, pct_chg_1d_min=0
- **核心指标**: 信号数=3002, WR_5d=49.95%, ret_5d=1.28%, ret_10d=2.77%, sharpe_5d=0.778
- **详细分析**: 价格位置+量能域, 股价位于20日底部20%以内, 量比>=1.5放量, 当日不跌。3002个信号中, 5日胜率49.95%, 5日收益1.28%, 10日收益2.77%, 20日收益5.17%。5日夏普0.778, 10日夏普0.844。
- **结论**: 未完全达标, 作首轮参考基线

## 所有组合 Hash (用于去重)

- `56bca2d129` — 放量突破20日新高
- `db460fc350` — 均线多头排列+温和放量
- `14875ed716` — 大阳线放量(涨停附近)
- `12094a5c49` — 向上跳空+中小幅上涨
- `f655c7de3c` — 底部放量(超跌反弹)

Hash列表: 56bca2d129, db460fc350, 14875ed716, 12094a5c49, f655c7de3c

## 完整 SQL 查询
```sql

SELECT
    ts_code, trade_date, close, open, high, low, pre_close, pct_chg, vol, amount,
    avg(close) OVER w5 AS ma5,
    avg(close) OVER w10 AS ma10,
    avg(close) OVER w20 AS ma20,
    vol / NULLIF(avg(vol) OVER w5, 0) AS vol_ratio,
    max(high) OVER w20r AS high_20d,
    min(low) OVER w20r AS low_20d,
    (close - min(low) OVER w20r) / NULLIF(max(high) OVER w20r - min(low) OVER w20r, 0) AS pos_20d,
    open / NULLIF(pre_close, 0) - 1 AS gap_pct,
    (high - low) / NULLIF(pre_close, 0) AS amplitude,
    leadInFrame(close, 1) OVER wfwd AS fwd_1,
    leadInFrame(close, 3) OVER wfwd AS fwd_3,
    leadInFrame(close, 5) OVER wfwd AS fwd_5,
    leadInFrame(close, 10) OVER wfwd AS fwd_10,
    leadInFrame(close, 20) OVER wfwd AS fwd_20
FROM tushare.tushare_stock_daily FINAL
WHERE ts_code NOT LIKE '30%'
  AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%'
  AND ts_code NOT LIKE '%ST%'
  AND amount >= 1e5
  AND trade_date >= '2023-01-01'
WINDOW
    w5 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
    w10 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),
    w20 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
    w20r AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
    wfwd AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING)
ORDER BY trade_date DESC
LIMIT 1500000

```