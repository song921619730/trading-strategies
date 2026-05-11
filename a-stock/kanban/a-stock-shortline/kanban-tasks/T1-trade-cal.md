# Kanban Task: T1 — 交易日历确认

| Field | Value |
|-------|-------|
| **Task ID** | T1 |
| **Name** | T1 — 交易日历确认 |
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
  4. 报告中的"下一交易日"必须读取 `./logs/screen-20260510-01-trade_cal.md`，引用其中的准确结论。
  5. 禁止使用"今天/明天/周一/周五"等模糊词汇，统一使用 YYYY-MM-DD。

## Skill/Soul 注入
你的核心工作原则请参考：`./skills/researcher-soul.md`。

## Task Body
你是数据研究员。确认 A 股最近交易日。
使用 Tushare DB 查询:
  SELECT cal_date, is_open, pretrade_date FROM _meta.trade_cal FINAL
  WHERE exchange = 'SSE' AND cal_date <= today()
  ORDER BY cal_date DESC LIMIT 10
输出最近交易日（YYYYMMDD 格式）、是否为今日、下一交易日。
将查询结果写入日志：./logs/screen-20260510-01-trade_cal.md
