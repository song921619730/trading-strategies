# T4 资金主力 视角 — Iter 1

> 数据基准: 2026-05-08 | 执行时间: 2026-05-11 15:02 UTC+8
> 角色: 策略挖掘分析师 (资金主力视角)
> 回测范围: 2023-01-01 ~ 2026-05-08 (全量历史)

## ⚠️ 技术限制
ClickHouse LEFT JOIN + 窗口函数存在列作用域问题，外查询无法直接引用被JOIN表的列。
因此每个查询只对一个JOIN表操作（moneyflow 或 daily_basic），跨表条件需嵌套处理。
组合6仅含 daily_basic。

## 测试参数组合 (6 组)

### 组合 1: 主力净流入+大单买入占比高
- **域**: 资金流
- **参数**: net_mf_min(万元)=2000, buy_lg_ratio_min=0.15, pct_chg_min=0
- **逻辑**: 主力净流入>=2000万, 大单买入占比>=15%, 当日不跌
- **结果**: 信号数=266470
  - 1D: WR=60.04%, ret=0.4408%, sharpe=0.891
  - 3D: WR=53.53%, ret=1.1831%, sharpe=0.838
  - 5D: WR=50.73%, ret=1.8399%, sharpe=0.802
  - 10D: WR=46.84%, ret=3.3011%, sharpe=0.756
  - 20D: WR=42.54%, ret=5.4722%, sharpe=0.698
- **判定**: ⚠️接近

### 组合 2: 超大单净买入+大单卖出少
- **域**: 资金流
- **参数**: buy_elg_ratio_min=0.05, sell_lg_ratio_max=0.1, pct_chg_min=0
- **逻辑**: 超大单买入占比>=5%, 大单卖出占比<=10%, 当日不跌
- **结果**: 信号数=416
  - 1D: WR=9.62%, ret=0.8143%, sharpe=0.804
  - 3D: WR=0.96%, ret=0.5127%, sharpe=0.771
  - 5D: WR=0.0%, ret=-0.0262%, sharpe=-0.349
  - 10D: WR=0.0%, ret=0.0%, sharpe=0
  - 20D: WR=0.0%, ret=0.0%, sharpe=0
- **判定**: ❌不佳

### 组合 3: 底部放量+主力吸筹
- **域**: 资金流+价格位置
- **参数**: pos_20d_max=0.2, net_mf_min(万元)=500, pct_chg_min=-3
- **逻辑**: 价格位于20日底部20%, 主力净流入>=500万, 跌幅不超3% (位置在外部query计算)
- **结果**: 信号数=114762
  - 1D: WR=0.0%, ret=0.0%, sharpe=0.0
  - 3D: WR=0.0%, ret=0.0%, sharpe=0.0
  - 5D: WR=57.02%, ret=2.1041%, sharpe=1.149
  - 10D: WR=0.0%, ret=0.0%, sharpe=0.0
  - 20D: WR=0.0%, ret=0.0%, sharpe=0.0
- **判定**: ⚠️接近

### 组合 4: 主力净流入+涨幅>2%
- **域**: 资金流
- **参数**: net_mf_min(万元)=1000, pct_chg_min=2
- **逻辑**: 主力净流入>=1000万, 涨幅>=2%
- **结果**: 信号数=224087
  - 1D: WR=59.53%, ret=0.5801%, sharpe=1.003
  - 3D: WR=52.95%, ret=1.5891%, sharpe=0.935
  - 5D: WR=50.26%, ret=2.5521%, sharpe=0.916
  - 10D: WR=46.73%, ret=4.9029%, sharpe=0.92
  - 20D: WR=41.95%, ret=8.7567%, sharpe=0.876
- **判定**: ⚠️接近

### 组合 5: 散户恐慌+主力买
- **域**: 资金流+散户行为
- **参数**: sell_sm_gt_buy_sm=True, buy_lg_ratio_min=0.12
- **逻辑**: 散户卖出>买入(恐慌), 大单买入占比>=12%
- **结果**: 信号数=999820
  - 1D: WR=48.82%, ret=0.1393%, sharpe=0.49
  - 3D: WR=48.78%, ret=0.4111%, sharpe=0.469
  - 5D: WR=48.21%, ret=0.661%, sharpe=0.451
  - 10D: WR=46.51%, ret=1.1959%, sharpe=0.408
  - 20D: WR=44.98%, ret=2.2509%, sharpe=0.392
- **判定**: ⚠️接近

### 组合 6: 量价健康+低估值
- **域**: 量能+市值+估值
- **参数**: volume_ratio_min=1.5, turnover_rate_min(%)=1, total_mv_max(亿)=100, pe_max=30, pct_chg_min=2
- **逻辑**: 量比>=1.5, 换手率>=1%, 总市值<=100亿, PE<=20, 涨幅>=2%
- **结果**: 信号数=26626
  - 1D: WR=58.99%, ret=0.425%, sharpe=0.714
  - 3D: WR=46.83%, ret=0.8909%, sharpe=0.576
  - 5D: WR=41.38%, ret=1.2951%, sharpe=0.566
  - 10D: WR=31.61%, ret=2.1295%, sharpe=0.581
  - 20D: WR=16.28%, ret=2.3157%, sharpe=0.475
- **判定**: ❌不佳

## 最佳发现

### 按夏普: 底部放量+主力吸筹
- **核心**: N=114762, WR_5d=57.02%, ret_5d=2.1041%, sharpe_5d=1.149
- **10D**: WR=0.0%, ret=0.0%, sharpe=0.0
- **20D**: WR=0.0%, ret=0.0%, sharpe=0.0
- **参数**: pos_20d_max=0.2, net_mf_min(万元)=500, pct_chg_min=-3

### 按5D收益: 主力净流入+涨幅>2%
- **WR_5d**: 50.26%, **Ret_5d**: 2.5521%, **Sharpe**: 0.916
- **信号数**: 224087

## 汇总表
| # | 组合 | N | WR_5d | Ret_5d | Sharpe |
|---|------|---|-------|--------|--------|
| 1 | 主力净流入+大单买入占比高 | 266470 | 50.73% | 1.8399% | 0.802 |
| 2 | 超大单净买入+大单卖出少 | 416 | 0.0% | -0.0262% | -0.349 |
| 3 | 底部放量+主力吸筹 | 114762 | 57.02% | 2.1041% | 1.149 |
| 4 | 主力净流入+涨幅>2% | 224087 | 50.26% | 2.5521% | 0.916 |
| 5 | 散户恐慌+主力买 | 999820 | 48.21% | 0.661% | 0.451 |
| 6 | 量价健康+低估值 | 26626 | 41.38% | 1.2951% | 0.566 |

## 所有组合 Hash
- `53f80c4401` — 主力净流入+大单买入占比高
- `4ab4bfc94d` — 超大单净买入+大单卖出少
- `613115c3c7` — 底部放量+主力吸筹
- `f671f9a5a7` — 主力净流入+涨幅>2%
- `efd797a6ff` — 散户恐慌+主力买
- `9f22ef9ee2` — 量价健康+低估值

Hash列表: 53f80c4401, 4ab4bfc94d, 613115c3c7, f671f9a5a7, efd797a6ff, 9f22ef9ee2

## 完整 SQL (最佳组合)
```sql

SELECT count() AS signal_count,
  round(avg(if(fwd_5>0,if(fwd_5>close,1,0),0))*100,2) AS wr_5d,
  round(avg(if(fwd_5>0,(fwd_5/close-1)*100,0)),4) AS ret_5d,
  round(stddevPop(if(fwd_5>0,(fwd_5/close-1),0)),6) AS std_5d
FROM (
  SELECT close, fwd_5,
    (close - low_20d) / NULLIF(high_20d - low_20d, 0) AS pos_20d
  FROM (
    SELECT d.close,
      min(d.low) OVER w19 AS low_20d,
      max(d.high) OVER w19 AS high_20d,
      leadInFrame(d.close,5) OVER w AS fwd_5
    FROM tushare.tushare_stock_daily d FINAL
    LEFT JOIN tushare.tushare_moneyflow m FINAL ON d.ts_code=m.ts_code AND d.trade_date=m.trade_date
    WHERE d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%' AND d.ts_code NOT LIKE '920%' AND d.ts_code NOT LIKE '%ST%'
      AND d.trade_date>='2023-01-01' AND d.trade_date<='2026-05-08' AND d.amount>0
      AND m.net_mf_amount>=500
      AND d.pct_chg>=-3
    WINDOW w19 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
           w AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING)
  )
  WHERE pos_20d <= 0.20
)
WHERE fwd_5 > 0

```
