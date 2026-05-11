# Kanban Task: T4 — Tavily 新闻搜索

| Field | Value |
|-------|-------|
| **Task ID** | T4 |
| **Name** | T4 — Tavily 新闻搜索 |
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
你是数据研究员。搜索当日影响 A 股的重要新闻。
使用 tavily_search 进行以下搜索（总轮次 <= 4，总搜索词 <= 16）:

1. 宏观政策: "中国 宏观经济 政策 央行 货币政策 财政 降准 降息 2026"
2. 行业催化: "A股 行业 利好 政策 板块 2026"
3. 地缘/国际事件: "中美贸易 关税 半导体 科技制裁 最新 2026"
4. 重要公告: "A股 重大公告 重组 减持 增持 业绩 2026"

权威新闻源优先：Reuters, Bloomberg, CNBC, 金十数据, 华尔街见闻, 东方财富, 新浪财经, AP News, BBC, WSJ, FT, 36氪, 虎嗅, 晚点 LatePost
数据新鲜度要求：财经 4h 内、政治 6h 内、科技 12h 内

每条新闻输出：标题、来源、日期、1-2 句摘要、影响方向（正面/负面/中性）、可信度。
绝对禁止用 tavily_search 查询价格/指数/汇率等数值行情。
将搜索结果写入日志：./logs/screen-20260510-04-news.md
