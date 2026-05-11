# T1: 全量数据新鲜度检查 (iter 1)

> 系统执行时间：2026-05-11 15:02 UTC+8
> 查询工具：ClickHouse 直连 (ch_query.py) @ tushare-clickhouse-direct
> 查询时间：2026-05-11 15:04 UTC+8

---

## 1. 最新交易日

| 指标 | 值 |
|------|-----|
| max(trade_date) | **2026-05-08** |

→ 2026-05-11（周一）为**当日**，数据基准日为上一个交易日 **2026-05-08（周五）**

---

## 2. 主板股票总数（排除 30%/688%/920%/ST）

| 指标 | 值 |
|------|-----|
| 股票数量 | **3,197** |

过滤条件：`ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'`

### 按市场分类

| 市场 | 数量 |
|------|------|
| 主板 | 3,196 |
| 科创板 | 1 |

> 注：科创板（688 前缀）已被排除，但 market 字段标记为「科创板」的股票中仍有 1 只未被 ts_code 前缀过滤掉（可能为非 688 开头的科创板股票）。

---

## 3. 日线数据全量日期范围 (`tushare_stock_daily`)

| 指标 | 值 |
|------|-----|
| min(trade_date) | 2019-12-30 |
| max(trade_date) | 2026-05-08 |
| 总行数 | 7,539,250 |

---

## 4. 核心表数据量一览

### 行情 & 指标（batch A）

| 表名 | 行数 | max(trade_date) | 新鲜度 |
|------|------|----------------|--------|
| `tushare_stock_daily` | 7,539,250 | 2026-05-08 | ✅ 当日 |
| `tushare_daily_basic` | 7,484,257 | 2026-05-08 | ✅ 当日 |
| `tushare_moneyflow` | 7,175,785 | 2026-05-08 | ✅ 当日 |

### 涨停 & 龙虎榜

| 表名 | 行数 | max(trade_date) | 新鲜度 |
|------|------|----------------|--------|
| `tushare_limit_list_d` | 153,858 | 2026-05-08 | ✅ 当日 |
| `tushare_top_list` | 97,289 | 2026-05-08 | ✅ 当日 |

### 融资融券

| 表名 | 行数 | max(trade_date) | 新鲜度 |
|------|------|----------------|--------|
| `tushare_margin` | 3,835 | 2026-04-27 | ⚠️ **滞后 11 天** |

### 北向资金

| 表名 | 行数 | max(trade_date) | 新鲜度 |
|------|------|----------------|--------|
| `tushare_moneyflow_hsgt` | 351 | 2026-05-08 | ✅ 当日 |

### 财报（batch C，季频）

| 表名 | 行数 | max(end_date) | 新鲜度 |
|------|------|---------------|--------|
| `tushare_income` | 123,800 | 2026-03-31 | ✅ 最新一季（Q1 2026） |
| `tushare_balancesheet` | 122,180 | 2026-03-31 | ✅ 最新一季（Q1 2026） |
| `tushare_fina_indicator` | 118,565 | 2026-03-31 | ✅ 最新一季（Q1 2026） |

### 概念 & 板块

| 表名 | 行数 | max(trade_date) | 新鲜度 |
|------|------|----------------|--------|
| `tushare_kpl_concept_cons` | 8,291 | 2026-05-08 | ✅ 当日 |
| `tushare_ths_daily` | 236,484 | 2026-05-08 | ✅ 当日 |
| `tushare_sw_daily` | 743,134 | 2026-05-07 | ⚠️ **滞后 1 天** |

### 期货

| 表名 | 行数 | max(trade_date) | 新鲜度 |
|------|------|----------------|--------|
| `tushare_fut_daily` | 1,371,170 | 2026-05-07 | ⚠️ **滞后 1 天** |

### 宏观

| 表名 | 行数 | 最新日期 | 新鲜度 |
|------|------|---------|--------|
| `tushare_cn_pmi` | 255 | 202603（3 月） | ✅ 月频，最新 |
| `tushare_cn_cpi` | 507 | 202603（3 月） | ✅ 月频，最新 |
| `tushare_shibor` | 2,008 | 2026-05-08 | ✅ 当日 |

### 外汇

| 表名 | 行数 | max(trade_date) | 新鲜度 |
|------|------|----------------|--------|
| `tushare_fx_daily` | 349,163 | 2026-05-07 | ⚠️ **滞后 1 天** |

### 指数

| 表名 | 行数 | max(trade_date) | 新鲜度 |
|------|------|----------------|--------|
| `tushare_index_daily` | 3,422,753 | 2026-05-08 | ✅ 当日 |

### 持仓分析

| 表名 | 行数 | max(end_date) | 新鲜度 |
|------|------|---------------|--------|
| `tushare_stk_holdernumber` | 426,488 | 2026-04-28 | ⚠️ **滞后约 10 天** |

### 筹码分布

| 表名 | 行数 | max(trade_date) | 新鲜度 |
|------|------|----------------|--------|
| `tushare_cyq_perf` | 9,138,766 | 2026-05-08 | ✅ 当日 |
| `tushare_cyq_chips` | 2,069,705 | 2026-05-08 | ✅ 当日 |

---

## 5. 新鲜度总结

### ✅ 与基准日 2026-05-08 同步（14 张表）

| 表 | 特殊说明 |
|----|---------|
| tushare_stock_daily | 基准 |
| tushare_daily_basic | ✅ |
| tushare_moneyflow | ✅ |
| tushare_limit_list_d | ✅ |
| tushare_top_list | ✅ |
| tushare_moneyflow_hsgt | ✅ |
| tushare_kpl_concept_cons | ✅ |
| tushare_ths_daily | ✅ |
| tushare_shibor | ✅ |
| tushare_index_daily | ✅ |
| tushare_cyq_perf | ✅ |
| tushare_cyq_chips | ✅ |
| tushare_income | 季频，最新 2026-03-31 ✅ |
| tushare_balancesheet | 季频，最新 2026-03-31 ✅ |
| tushare_fina_indicator | 季频，最新 2026-03-31 ✅ |

### ⚠️ 滞后（5 张表）

| 表 | 最新日期 | 滞后天数 | 说明 |
|----|---------|---------|------|
| tushare_margin | 2026-04-27 | **11 天** | 融资融券数据长期滞后 |
| tushare_stk_holdernumber | 2026-04-28 | **~10 天** | 持仓人数数据更新延迟 |
| tushare_sw_daily | 2026-05-07 | **1 天** | 申万行业指数滞后 |
| tushare_fut_daily | 2026-05-07 | **1 天** | 期货日线滞后 |
| tushare_fx_daily | 2026-05-07 | **1 天** | 外汇日线滞后 |

### ✅ 宏观（月频正常）

| 表 | 最新 |
|----|------|
| tushare_cn_pmi | 2026-03（3 月） |
| tushare_cn_cpi | 2026-03（3 月） |

---

## 6. 原始查询 SQL 记录

```sql
-- Q1: 最新交易日
SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL

-- Q2: 主板股票总数
SELECT count() FROM tushare.tushare_stock_basic FINAL
WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'

-- Q3: 全量日期范围
SELECT min(trade_date), max(trade_date), count()
FROM tushare.tushare_stock_daily FINAL

-- Q4: 主板按市场分类
SELECT market, count() AS cnt
FROM tushare.tushare_stock_basic FINAL
WHERE ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
GROUP BY market ORDER BY cnt DESC

-- Q5: 各表数据量（模式：count + max date）
-- 见第 4 节各表查询
```
