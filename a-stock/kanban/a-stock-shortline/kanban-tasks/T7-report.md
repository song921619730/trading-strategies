# Kanban Task: T7 — 报告生成

| Field | Value |
|-------|-------|
| **Task ID** | T7 |
| **Name** | T7 — 报告生成 |
| **Status** | ✅ done |
| **Completed** | 2026-05-10 08:39 UTC+8 |
| **Assignee** | writer |
| **Parents** | [T6] |
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
你的核心工作原则请参考：`./skills/writer-soul.md`。

## Task Body
你是报告撰写人。任务：将主控初筛结果生成标准 markdown 报告。

文件命名：shortline-screen-202605102200.md
保存到：./reports/

⚠️ 强制要求：
在报告开头，你必须读取并引用 `./logs/screen-20260510-01-trade_cal.md`。
明确写出："分析基准: 2026-05-08 (周五)" 和 "下一交易日: 2026-05-11 (周一)"。
禁止自行推测日期。

报告结构:
1. 当前市场判断（情绪周期/主线/全球环境）
2. 三层候选池总览（待涨观察池/预备突破池/强确认跟踪池）
3. 候选明细（逐票完整字段）
4. 被降级/未纳入的高风险样本
5. 下一次复核点

输入数据: 读取 T6 日志文件:
  - ./logs/screen-20260510-06-main_screen.md

将生成的报告同时写入日志：./logs/screen-20260510-07-report.md
