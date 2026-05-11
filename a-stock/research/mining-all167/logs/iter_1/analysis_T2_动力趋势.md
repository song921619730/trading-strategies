# T2 动力趋势视角 — Iter 1

- 执行时间: 2026-05-11 15:38 UTC+8
- 数据基准: 20260508
- 回测区间: 20190101 ~ 20260508

---

## 测试参数组合（5 组）

### 组合 1: 中大盘趋势+放量突破
- 描述: 中大盘趋势票放量突破，日涨幅2-10%确认动能的延续
- 参数: amplitude_min=3, close_position=顶40%, ma_arrangement=多头排列, market_cap_bucket=中大盘(100-500亿), pct_chg_1d_max=10, pct_chg_1d_min=2, turnover_rate_min=0.01, volume_ratio_min=1.2
- Hash: `c36b4199bfda`

#### 结果
| 周期 | 信号数 | 胜率(WR) | 平均收益 | 夏普比率 |
|------|--------|----------|----------|----------|
| T+1d | 0 | 0.00% | 0.00% | 0.000 |
| T+3d | 0 | 0.00% | 0.00% | 0.000 |
| T+5d | 0 | 0.00% | 0.00% | 0.000 |
| T+10d | 0 | 0.00% | 0.00% | 0.000 |
| T+20d | 0 | 0.00% | 0.00% | 0.000 |

#### SQL 查询骨架
```sql
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, d.open, d.pre_close
FROM tushare_stock_daily FINAL d
LEFT JOIN tushare_daily_basic FINAL b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE d.trade_date >= '20190101' AND d.trade_date <= '20260508'
  AND d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%' AND d.ts_code NOT LIKE '920%'
  -- amplitude_min=3
  -- close_position=顶40%
  -- ma_arrangement=多头排列
  -- market_cap_bucket=中大盘(100-500亿)
  -- pct_chg_1d_max=10
  -- pct_chg_1d_min=2
  -- turnover_rate_min=0.01
  -- volume_ratio_min=1.2
```

### 组合 2: 小盘强势+放量上攻
- 描述: 小盘动量强势股，放量上攻，高换手确认活跃度
- 参数: amplitude_min=3, close_position=顶40%, market_cap_bucket=小盘(<30亿), pct_chg_1d_max=10, pct_chg_1d_min=3, turnover_rate_max=0.3, turnover_rate_min=0.02, volume_ratio_min=1.5
- Hash: `c5af00358922`

#### 结果
| 周期 | 信号数 | 胜率(WR) | 平均收益 | 夏普比率 |
|------|--------|----------|----------|----------|
| T+1d | 324 | 51.54% | 0.39% | 2.433 |
| T+3d | 324 | 49.07% | 0.65% | 1.264 |
| T+5d | 324 | 50.00% | 1.05% | 1.068 |
| T+10d | 324 | 52.16% | 0.94% | 0.625 |
| T+20d | 324 | 48.77% | 0.98% | 0.311 |

#### SQL 查询骨架
```sql
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, d.open, d.pre_close
FROM tushare_stock_daily FINAL d
LEFT JOIN tushare_daily_basic FINAL b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE d.trade_date >= '20190101' AND d.trade_date <= '20260508'
  AND d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%' AND d.ts_code NOT LIKE '920%'
  -- amplitude_min=3
  -- close_position=顶40%
  -- market_cap_bucket=小盘(<30亿)
  -- pct_chg_1d_max=10
  -- pct_chg_1d_min=3
  -- turnover_rate_max=0.3
  -- turnover_rate_min=0.02
  -- volume_ratio_min=1.5
```

### 组合 3: 多头趋势+放量加速
- 描述: 均线多头排列中放量加速的纯趋势信号，无市值限制
- 参数: amplitude_min=3, ma_arrangement=多头排列, ma_support=MA10, pct_chg_1d_max=10, pct_chg_1d_min=2, turnover_rate_min=0.01, volume_ratio_min=1.5
- Hash: `47910210ac6e`

#### 结果
| 周期 | 信号数 | 胜率(WR) | 平均收益 | 夏普比率 |
|------|--------|----------|----------|----------|
| T+1d | 66100 | 41.99% | -0.17% | -0.595 |
| T+3d | 66100 | 41.45% | -0.38% | -0.440 |
| T+5d | 66100 | 40.03% | -0.57% | -0.410 |
| T+10d | 66100 | 40.00% | -0.64% | -0.245 |
| T+20d | 66100 | 40.26% | -0.51% | -0.103 |

#### SQL 查询骨架
```sql
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, d.open, d.pre_close
FROM tushare_stock_daily FINAL d
LEFT JOIN tushare_daily_basic FINAL b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE d.trade_date >= '20190101' AND d.trade_date <= '20260508'
  AND d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%' AND d.ts_code NOT LIKE '920%'
  -- amplitude_min=3
  -- ma_arrangement=多头排列
  -- ma_support=MA10
  -- pct_chg_1d_max=10
  -- pct_chg_1d_min=2
  -- turnover_rate_min=0.01
  -- volume_ratio_min=1.5
```

### 组合 4: 低位首阳放量反弹
- 描述: 低位放量首阳，超跌反弹的动量反转模式
- 参数: amplitude_min=4, close_position=底40%, pct_chg_1d_max=10, pct_chg_1d_min=3, turnover_rate_min=0.01, volume_ratio_min=2.0
- Hash: `44d1abcfd92a`

#### 结果
| 周期 | 信号数 | 胜率(WR) | 平均收益 | 夏普比率 |
|------|--------|----------|----------|----------|
| T+1d | 7377 | 42.86% | -0.11% | -0.430 |
| T+3d | 7377 | 45.05% | 0.19% | 0.253 |
| T+5d | 7377 | 45.52% | 0.43% | 0.334 |
| T+10d | 7377 | 47.40% | 0.70% | 0.282 |
| T+20d | 7377 | 48.18% | 1.63% | 0.335 |

#### SQL 查询骨架
```sql
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, d.open, d.pre_close
FROM tushare_stock_daily FINAL d
LEFT JOIN tushare_daily_basic FINAL b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE d.trade_date >= '20190101' AND d.trade_date <= '20260508'
  AND d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%' AND d.ts_code NOT LIKE '920%'
  -- amplitude_min=4
  -- close_position=底40%
  -- pct_chg_1d_max=10
  -- pct_chg_1d_min=3
  -- turnover_rate_min=0.01
  -- volume_ratio_min=2.0
```

### 组合 5: 涨停后高开+换手接力
- 描述: 涨停后接力（简化：高换手+高振幅+多头+跳空确认）
- 参数: amplitude_min=5, gap_direction=向上跳空, ma_arrangement=多头排列, pct_chg_1d_max=6, pct_chg_1d_min=0, turnover_rate_max=0.4, turnover_rate_min=0.05, volume_ratio_min=1.0
- Hash: `075428600d21`

#### 结果
| 周期 | 信号数 | 胜率(WR) | 平均收益 | 夏普比率 |
|------|--------|----------|----------|----------|
| T+1d | 32 | 59.38% | 1.33% | 6.299 |
| T+3d | 32 | 50.00% | 1.04% | 2.154 |
| T+5d | 32 | 53.12% | 0.76% | 1.051 |
| T+10d | 32 | 53.12% | 1.05% | 0.955 |
| T+20d | 32 | 53.12% | 1.87% | 0.624 |

#### SQL 查询骨架
```sql
SELECT d.ts_code, d.trade_date, d.close, d.pct_chg, d.open, d.pre_close
FROM tushare_stock_daily FINAL d
LEFT JOIN tushare_daily_basic FINAL b ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE d.trade_date >= '20190101' AND d.trade_date <= '20260508'
  AND d.ts_code NOT LIKE '30%' AND d.ts_code NOT LIKE '688%' AND d.ts_code NOT LIKE '920%'
  -- amplitude_min=5
  -- gap_direction=向上跳空
  -- ma_arrangement=多头排列
  -- pct_chg_1d_max=6
  -- pct_chg_1d_min=0
  -- turnover_rate_max=0.4
  -- turnover_rate_min=0.05
  -- volume_ratio_min=1.0
```

---

## 最佳发现

- 参数组合: 小盘强势+放量上攻
- 指标:
  - 信号数: 324
  - WR_5d: 50.00%
  - Ret_5d: 1.05%
  - Ret_10d: 0.94%
  - Ret_20d: 0.98%
  - Sharpe_5d: 1.068
  - Sharpe_10d: 0.625
  - Sharpe_20d: 0.311
- 描述: 小盘动量强势股，放量上攻，高换手确认活跃度
- Hash: `c5af00358922`

- 成功标准(WR>=52% AND Ret5d>=3% AND N>=200): FAIL
- 未达标原因: WR_5d=50.00%<52%, Ret_5d=1.05%<3%

---

## 所有组合 Hash（用于去重）

`c36b4199bfda`, `c5af00358922`, `47910210ac6e`, `44d1abcfd92a`, `075428600d21`
