# Kanban Task: T2 — A股日线扫描

| Field | Value |
|-------|-------|
| **Task ID** | T2 |
| **Name** | T2 — A股日线扫描 |
| **Status** | ✅ done |
| **Completed** | 2026-05-10 08:39 UTC+8 |
| **Assignee** | researcher |
| **Parents** | [] (无依赖) |
| **Created** | 2026-05-10 08:39 UTC+8 |
| **Priority** | high |

## 📅 时间上下文（强制遵守）
- 系统执行时间：2026-05-10 08:39 UTC+8
- 今日日期：2026-05-10
- 数据基准日期：2026-05-08（最近实际交易日）
- ⚠️ 规则：
  1. 日志文件名中的日期必须使用"今日日期"。
  2. 数据查询必须先运行：`SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL` 以确认"数据基准日期"。
  3. 报告中的"基准日期"必须写实际查询到的 `max_date`（YYYY-MM-DD）。
  4. 报告中的"下一交易日"必须读取 `./logs/screen-20260510-01-trade-cal.md`，引用其中的准确结论。
  5. 禁止使用"今天/明天/周一/周五"等模糊词汇，统一使用 YYYY-MM-DD。

## Skill/Soul 注入
你的核心工作原则请参考：`./skills/researcher-soul.md`。

## Task Body
你是数据研究员。获取 A 股市场最新数据快照。
使用 Tushare DB 执行以下查询（SQL 必须加 FINAL，日期 YYYYMMDD）:

1. 五大指数最新收盘:
   SELECT ts_code, trade_date, close, pct_chg, vol, amount
   FROM tushare.tushare_index_daily FINAL
   WHERE ts_code IN ('000001.SH','399001.SZ','000300.SH','000688.SH','399006.SZ')
   ORDER BY ts_code, trade_date DESC LIMIT 5 BY ts_code

2. 涨停池（最近交易日）:
   SELECT ts_code, name, close, pct_chg, limit_times, fc_ratio, first_time, last_time, open_times
   FROM tushare.tushare_limit_list_d FINAL
   WHERE trade_date = (SELECT max(trade_date) FROM tushare.tushare_limit_list_d)
     AND limit_times > 0
   ORDER BY fc_ratio DESC, limit_times DESC LIMIT 50

3. 北向资金（最近 10 个交易日）:
   SELECT trade_date, north_money, south_money, gg_buy, gg_sell
   FROM tushare.tushare_moneyflow_hsgt FINAL
   ORDER BY trade_date DESC LIMIT 10

4. 概念板块涨停分布:
   SELECT c.concept_name, count(*) as limit_count
   FROM tushare.tushare_concept_detail c FINAL
   JOIN tushare.tushare_limit_list_d l FINAL ON c.ts_code = l.ts_code
   WHERE l.trade_date = (SELECT max(trade_date) FROM tushare.tushare_limit_list_d)
     AND l.limit_times > 0
   GROUP BY c.concept_name ORDER BY limit_count DESC LIMIT 20

5. 全市场 PE/PB 中位数（近 10 个交易日）:
   SELECT trade_date, median(pe) AS median_pe, median(pb) AS median_pb, count() AS cnt
   FROM tushare.tushare_daily_basic FINAL
   WHERE trade_date >= '2026-04-28' AND pe > 0 AND pe < 500 AND pb > 0
   GROUP BY trade_date ORDER BY trade_date DESC

将查询结果写入日志：./logs/screen-20260510-02-market_scan.md
