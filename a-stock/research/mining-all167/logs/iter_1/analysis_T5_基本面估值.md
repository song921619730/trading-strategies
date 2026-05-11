# T5 基本面估值 视角 — Iter 1

> 数据基准日: 2026-05-08 | 回测范围: 全量历史(2020-2026) | 主板过滤: 排除30%/688%/920%/ST
> 成功标准: WR >= 52% AND 5D收益 >= 3% AND 信号数 >= 200

## 测试参数组合（5 组）

### 组合 1: 低PE+高ROE价值策略
- **参数**: pe_max=15, roe_min=0.1, gross_margin_min=0.2, market_cap_bucket=中大盘(100-500亿), dv_ratio_min=0.01
- **Hash**: `eb3061a8`
- **结果**: 信号数=213678, WR_1d=49.57%, ret_1d=0.0441%, WR_3d=48.65%, ret_3d=0.1109%, WR_5d=47.8%, ret_5d=0.1767%, WR_10d=47.29%, ret_10d=0.2786%, WR_20d=48.14%, ret_20d=0.4286%, Sharpe_5d=0.26
- **达标**: ❌ 未达标

### 组合 2: 高分红+低PB防御策略
- **参数**: pe_max=20, pb_max=2, dv_ratio_min=0.02, market_cap_bucket=中大盘(100-500亿), roe_min=0.05, pledge_ratio_max=0.3
- **Hash**: `e2ecb754`
- **结果**: 信号数=269345, WR_1d=49.65%, ret_1d=0.0465%, WR_3d=48.83%, ret_3d=0.1216%, WR_5d=48.19%, ret_5d=0.2061%, WR_10d=47.61%, ret_10d=0.3148%, WR_20d=48.52%, ret_20d=0.4683%, Sharpe_5d=0.31
- **达标**: ❌ 未达标

### 组合 3: 成长+估值GARP策略(fix)
- **参数**: pe_max=30, tr_yoy_growth=>10%, turnover_rate_min=0.01
- **Hash**: `899444e1`
- **结果**: 信号数=1066863, WR_1d=48.23%, ret_1d=0.0795%, WR_3d=49.29%, ret_3d=0.2477%, WR_5d=49.8%, ret_5d=0.4062%, WR_10d=50.75%, ret_10d=0.761%, WR_20d=50.7%, ret_20d=1.4266%, Sharpe_5d=0.49
- **达标**: ❌ 未达标

### 组合 4: 小盘低估值+筹码集中
- **参数**: pe_max=25, pb_max=3, market_cap_bucket=中小盘(30-100亿), cyq_concentration=集中(50-70%), holder_num_chg_3q=减少>5%, turnover_rate_min=0.005, roe_min=0.05
- **Hash**: `57052c10`
- **结果**: 信号数=526141, WR_1d=50.53%, ret_1d=0.1171%, WR_3d=49.83%, ret_3d=0.2528%, WR_5d=49.34%, ret_5d=0.3876%, WR_10d=48.41%, ret_10d=0.5738%, WR_20d=48.84%, ret_20d=0.8162%, Sharpe_5d=0.49
- **达标**: ❌ 未达标

### 组合 5: 低估值+技术突破+资金认可(fix)
- **参数**: pe_max=30, pb_max=5, volume_ratio_min=1.5, net_mf_min=0, turnover_rate_min=0.02
- **Hash**: `958b9d2c`
- **结果**: 信号数=10501, WR_1d=45.94%, ret_1d=0.1439%, WR_3d=46.9%, ret_3d=0.3362%, WR_5d=46.8%, ret_5d=0.4461%, WR_10d=48.15%, ret_10d=0.6143%, WR_20d=48.36%, ret_20d=1.3447%, Sharpe_5d=0.46
- **达标**: ❌ 未达标

## 最佳发现

- **参数组合**: 成长+估值GARP策略(fix)
- **参数**: pe_max=30, tr_yoy_growth=>10%, turnover_rate_min=0.01
- **指标**: WR_5d=49.8%, ret_5d=0.4062%, ret_10d=0.761%, ret_20d=1.4266%, Sharpe_5d=0.49, 信号数=1066863
- **Hash**: `899444e1`
- **详细分析**: 本次测试所有组合均未达到成功标准(WR>=52% AND ret_5d>=3%)。最佳表现为小盘低估值+筹码集中组合(WR_5d=49.34%, ret_5d=0.39%)，胜率接近52%但5日收益偏低。价值类策略(WR_5d约48%)表现略弱于小盘策略。

## 数据质量问题发现

1. **basic_eps_yoy完全为空**: tushare_fina_indicator中basic_eps_yoy字段118565条记录全为NULL，无法用于EPS增长筛选。建议改用tr_yoy(营收增长)或netprofit_yoy(净利润增长)。
2. **net_mf字段不存在**: tushare_moneyflow表中实际列名为net_mf_amount，非net_mf。
3. **季频数据覆盖有限**: fina_indicator仅118565条记录，覆盖约4000股票×30报告期，导致使用财报指标的信号受限于财报日期匹配。

## 所有组合 Hash（用于去重）

eb3061a8, e2ecb754, 899444e1, 57052c10, 958b9d2c

## 关键SQL示例

```sql
-- 组合1: 低PE+高ROE价值策略
SELECT ts_code, trade_date, close, pe, pb, dv_ratio, turnover_rate, volume_ratio, circ_mv
FROM tushare.tushare_daily_basic FINAL
WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
  AND pe IS NOT NULL AND pe <= 15
  AND dv_ratio IS NOT NULL AND dv_ratio >= 0.01
  AND circ_mv > 1000000 AND circ_mv <= 5000000;

-- 营收增长过滤(替代basic_eps_yoy)
SELECT ts_code, end_date, tr_yoy FROM tushare.tushare_fina_indicator FINAL WHERE tr_yoy IS NOT NULL;

-- 主力资金流过滤(使用net_mf_amount)
SELECT ts_code, trade_date, net_mf_amount FROM tushare.tushare_moneyflow FINAL WHERE net_mf_amount >= 0;
```

## 备注

- circ_mv单位: 万元 (Tushare daily_basic标准)
- FINAL+JOIN语法限制: 采用分步查询+Python侧合并
- fina_indicator为季频数据，信号受财报日期匹配影响
- 前向收益基于实际交易日计算，None值已过滤
