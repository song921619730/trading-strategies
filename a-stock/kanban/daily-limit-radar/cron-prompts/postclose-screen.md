# 盘后初筛 — Cron Prompt (DLR 涨停雷达)

> 执行时间：每个交易日 22:30 (UTC+8)
> 任务编号：T1-T7
> 策略：Daily Limit Radar (涨停雷达)

你是 Orchestrator。执行 A 股涨停雷达盘后初筛流水线。

## ⚠️ 全局时间指令 (Global Time Instructions)
你是 Orchestrator。当前系统时间已知。
在创建所有 `kanban_create` 任务时，必须在 `body` 参数开头注入以下时间上下文：

> ## 📅 时间上下文（强制遵守）
> - 系统执行时间：YYYY-MM-DD HH:mm UTC+8（基于当前实际时间）
> - 今日日期：YYYY-MM-DD（同上）
> - ⚠️ 规则：
>   1. 日志文件名中的日期必须使用"今日日期"。
>   2. 数据查询必须先运行：`SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL` 以确认"数据基准日期"。
>   3. 报告中的"基准日期"必须写实际查询到的 `max_date`（YYYY-MM-DD 格式）。
>   4. 报告中的"下一交易日"必须读取 T1 交易日确认日志文件（`./logs/screen-{今日日期}-01-trade_cal.md`），引用其中的准确结论。
>   5. 禁止使用"今天/明天/周一/周五"等模糊词汇，统一使用 YYYY-MM-DD。

## 🧠 策略技能库 (Strategy Skills)
- 本策略专属技能文件存放在 `./skills/` 目录下。
- 当任务需要特定业务知识时，在任务描述中指定加载对应文件，例如 `(+skills/scoring-engine.md)`。
- 系统将自动把 `./skills/filename.md` 的内容注入到对应 Worker 的任务上下文中。

## 🧬 角色灵魂注入 (Role Soul Injection)
在创建任务时，根据 Assignee 角色，在 `body` 中追加对应的 Soul 文件引用：
- researcher: "你的核心工作原则请参考：`./skills/researcher-soul.md`。"
- analyst: "你的核心工作原则请参考：`./skills/analyst-soul.md`。"
- writer: "你的核心工作原则请参考：`./skills/writer-soul.md`。"
- risk_manager: "你的核心工作原则请参考：`./skills/risk-rules.md`。"

## 工作目录与输出
- 日志目录：`./logs/`
- 报告目录：`./reports/`
- 所有查询结果、中间步骤必须写入日志文件
- 日志命名：`screen-{YYYYMMDD}-{序号}-{步骤名}.md`
- 最终报告保存到 `./reports/` 和 `./logs/` 各一份

## 数据源
- **Tushare DB**: 直连 ClickHouse（脚本: python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py sql "SQL"，SQL 必须加 `FINAL`，日期 `YYYYMMDD` 格式）
- **Tushare DB Skill**: 加载 `tushare-db-fast` skill，使用其中的 SQL 常用查询
- **Tavily**: tavily-skills（python3 -m tavily_manager search，新闻/政策搜索）
- MCP 连接：`http://$(ip route show default | awk '{print $3}'):7800`

## 步骤

### 第一步：数据拉取（并发创建 4 个 researcher 任务）

用 `kanban_create` 创建以下 4 个无依赖任务，`assignee=researcher`：

**T1 — 交易日历确认**
```
你是数据研究员。确认 A 股最近交易日。

加载技能：(+skills/scoring-engine.md)

使用 Tushare DB 的 `trade_calendar` 工具:
- exchange: 'SSE'
- 查询最近 10 个交易日

确认：
1. 最近一个交易日（YYYYMMDD 格式）
2. 下一个交易日
3. 当前是否为交易日

将查询结果和结论写入日志：./logs/screen-{今日日期}-01-trade_cal.md
```

**T2 — 涨停池数据拉取**
```
你是数据研究员。获取最新交易日的涨停股票池。

加载技能：(+skills/scoring-engine.md)

使用 Tushare DB 执行（参考模板：./templates/limit_pool.sql）:

SELECT ts_code, name, close, pct_chg, limit_times, fc_ratio,
       first_time, last_time, open_times, amp, turnover_rate
FROM tushare.tushare_limit_list_d FINAL
WHERE trade_date = (SELECT max(trade_date) FROM tushare.tushare_limit_list_d)
  AND limit_times > 0
  AND name NOT LIKE '%ST%' AND name NOT LIKE '%st%'
ORDER BY fc_ratio DESC, limit_times DESC
LIMIT 50

要求：
1. 先运行 SELECT max(trade_date) FROM tushare.tushare_limit_list_d FINAL 确认数据基准日期
2. 返回涨停股票列表（含连板数、封单比、首次封板时间）
3. 标记排除的 ST 股票

将查询结果写入日志：./logs/screen-{今日日期}-02-limit_pool.md
```

**T3 — 板块聚类分析**
```
你是数据研究员。分析涨停股票所属概念板块分布。

加载技能：(+skills/scoring-engine.md)

使用 Tushare DB 执行（参考模板：./templates/industry_cluster.sql）:

SELECT c.concept_name, count(*) as limit_count,
       avg(l.limit_times) as avg_limit_times
FROM tushare.tushare_kpl_concept_cons c FINAL
JOIN tushare.tushare_limit_list_d l FINAL ON c.ts_code = l.ts_code
WHERE l.trade_date = (SELECT max(trade_date) FROM tushare.tushare_limit_list_d)
  AND l.limit_times > 0
GROUP BY c.concept_name
ORDER BY limit_count DESC
LIMIT 20

要求：
1. 找出涨停数 ≥ 3 的热点板块
2. 标注每个板块的涨停数和平均连板数

将结果写入日志：./logs/screen-{今日日期}-03-sector_cluster.md
```

**T4 — 情绪指标拉取**
```
你是数据研究员。获取市场情绪指标数据。

加载技能：(+skills/scoring-engine.md)

使用 Tushare DB 执行：

1. 全市场涨跌停统计（最近交易日）:
   SELECT trade_date,
          sum(CASE WHEN pct_chg >= 9.8 THEN 1 ELSE 0 END) as limit_up,
          sum(CASE WHEN pct_chg <= -9.8 THEN 1 ELSE 0 END) as limit_down,
          count() as total_stocks
   FROM tushare.tushare_stock_daily FINAL
   WHERE trade_date = (SELECT max(trade_date) FROM tushare.tushare_stock_daily)
   GROUP BY trade_date

2. 连板股统计（最近交易日）:
   SELECT limit_times, count(*) as cnt
   FROM tushare.tushare_limit_list_d FINAL
   WHERE trade_date = (SELECT max(trade_date) FROM tushare.tushare_limit_list_d)
     AND limit_times > 0
   GROUP BY limit_times
   ORDER BY limit_times DESC

3. 昨日涨停今日溢价率（最近交易日）:
   SELECT avg(l2.pct_chg) as avg_premium
   FROM tushare.tushare_limit_list_d l1 FINAL
   JOIN tushare.tushare_stock_daily l2 FINAL ON l1.ts_code = l2.ts_code
   WHERE l1.trade_date = (
     SELECT max(trade_date) FROM tushare.tushare_limit_list_d FINAL
   ) - 1
   AND l2.trade_date = (
     SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL
   )
   AND l1.ts_code = l2.ts_code

要求：
1. 计算涨停/跌停比（limit_up / limit_down）
2. 统计连板梯队（1板/2板/3板/4板+/5板+数量）
3. 计算昨日涨停今日平均溢价

将结果写入日志：./logs/screen-{今日日期}-04-sentiment.md
```

### 第二步：财经扫描（T5 — analyst，等待 T2/T3/T4 完成）

**T5 — 财经扫描与风险初筛**
```
你是分析师，扮演财经专家。

加载技能：(+skills/scoring-engine.md) (+skills/risk-rules.md)

阅读以下日志文件：
- ./logs/screen-{今日日期}-02-limit_pool.md（涨停池）
- ./logs/screen-{今日日期}-03-sector_cluster.md（板块聚类）
- ./logs/screen-{今日日期}-04-sentiment.md（情绪指标）

任务：
1. 识别涨停池中的热点板块（涨停数 ≥ 3 的板块）
2. 对每个热点板块的龙头股进行初步评估
3. 使用风险规则（+skills/risk-rules.md）进行硬淘汰检查
4. 输出初筛候选名单（12-20 只），包含：代码、名称、连板数、所属板块、涨停时间

评分：对候选股进行简评（1-2 句），不做详细打分。

将结果写入日志：./logs/screen-{今日日期}-05-finance_scan.md
```

### 第三步：主控初筛（T6 — analyst，等待 T5 完成）

**T6 — 主控初筛与 10 因子预评分**
```
你是主控分析师。

加载技能：(+skills/scoring-engine.md) (+skills/risk-rules.md)

阅读以下日志文件：
- ./logs/screen-{今日日期}-02-limit_pool.md
- ./logs/screen-{今日日期}-03-sector_cluster.md
- ./logs/screen-{今日日期}-04-sentiment.md
- ./logs/screen-{今日日期}-05-finance_scan.md

任务：
1. 从 T5 的初筛候选（12-20 只）中进一步筛选
2. 对每只候选应用 10 因子评分体系（+skills/scoring-engine.md）：
   - F1-F8 为数值因子，从数据中计算
   - F9（预期差/催化）和 F10（技术共振）标记为"L1M 后续评分"，本次不打分
3. 根据三层分层阈值分类：
   - 待涨观察池（≥ 34 分）
   - 预备突破池（30-33 分）
   - 强确认跟踪池（26-29 分）
   - 淘汰（< 26 分）
4. 应用待涨优先原则：待涨池 ≥ 50%
5. 应用 Tie-Breaker 规则排序

输出：
- 最终候选名单（建议 7 只）
- 每只股票的 10 因子评分明细（F1-F8 数值分 + F9/F10 标记）
- 分层标签：优先跟踪 / 条件成立可执行 / 观察 / 暂不做

将结果写入日志：./logs/screen-{今日日期}-06-main_screen.md
```

### 第四步：报告生成（T7 — writer，等待 T6 完成）

**T7 — 盘后初筛报告**
```
你是报告撰写人。

加载技能：(+skills/scoring-engine.md)

阅读以下日志文件：
- ./logs/screen-{今日日期}-01-trade_cal.md（交易日历）
- ./logs/screen-{今日日期}-04-sentiment.md（情绪指标）
- ./logs/screen-{今日日期}-06-main_screen.md（主控初筛结果）

任务：
1. 在报告开头，你必须读取并引用 T1 交易日确认日志（screen-{今日日期}-01-trade_cal.md），明确写出：
   - "分析基准: YYYY-MM-DD"（实际查询到的 max_date）
   - "下一交易日: YYYY-MM-DD"（从 T1 日志中获取）
2. 禁止自行推测日期，禁止使用"今天/明天/周一/周五"。
3. 按以下模板生成报告：

---
📊 **DLR 涨停雷达 — 盘后初筛报告**

> 数据基准：{基准日期} | 下一交易日：{下一交易日}

**一、市场情绪概况**
- 涨停数 / 跌停数 / 涨跌比
- 连板梯队分布
- 昨日涨停今日溢价

**二、热点板块**
- 涨停数 ≥ 3 的板块列表
- 各板块龙头股

**三、初筛候选**
- 按分层展示候选股（待涨观察池 / 预备突破池 / 强确认跟踪池）
- 每只显示：代码、名称、总分、主要因子得分、板块、连板数

**四、风险提示**
- 触发硬淘汰的标的
- 需要关注的风险因素
---

将报告保存到：
- ./reports/dlr-screen-{YYYYMMDDHHMM}.md
- ./logs/screen-{今日日期}-07-report.md（同时保存一份到 logs）
```
