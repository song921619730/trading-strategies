#!/usr/bin/env python3
"""Create T1-T7 kanban tasks for post-market shortline screening pipeline."""

import sqlite3
import json
import uuid
import time
import os

DB_PATH = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/a-stock-shortline"

def make_id():
    return "t_" + uuid.uuid4().hex[:24]

def create_task(cur, task_id, title, assignee, body, parents=None):
    now = int(time.time())
    status = "todo" if parents else "ready"
    cur.execute("""
        INSERT OR REPLACE INTO tasks (id, title, body, assignee, status, created_at, tenant)
        VALUES (?, ?, ?, ?, ?, ?, 'default')
    """, (task_id, title, body, assignee, status, now))
    
    if parents:
        for p in parents:
            cur.execute("""
                INSERT OR REPLACE INTO task_links (parent_id, child_id)
                VALUES (?, ?)
            """, (p, task_id))
    print(f"  Created {task_id}: {title} [{status}] assignee={assignee} parents={parents}")
    return task_id

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Time context (2026-05-11 09:56 UTC+8)
    tc = """## \U0001f4c5 时间上下文（强制遵守）
- 系统执行时间：2026-05-11 09:56 UTC+8
- 今日日期：2026-05-11
- \u26a0\ufe0f 规则：
  1. 日志文件名中的日期必须使用"今日日期"20260511。
  2. 数据查询必须先运行 SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL 确认"数据基准日期"。
  3. 报告中的"基准日期"必须写实际查询到的 max_date（YYYY-MM-DD）。
  4. 报告中的"下一交易日"必须读取 ./logs/screen-20260511-01-trade_cal.md，引用准确结论。
  5. 禁止使用"今天/明天/周一/周五"等模糊词汇，统一使用 YYYY-MM-DD。"""

    researcher_soul = "你的核心工作原则请参考：`./skills/researcher-soul.md`。"
    analyst_soul = "你的核心工作原则请参考：`./skills/analyst-soul.md`。"
    writer_soul = "你的核心工作原则请参考：`./skills/writer-soul.md`。"

    print("Creating T1-T7 screening pipeline tasks...")

    # ===== T1: 交易日历确认 =====
    t1 = create_task(cur, make_id(), "T1 — 交易日历确认", "researcher", f"""
{tc}

你是数据研究员。确认 A 股最近交易日。
{researcher_soul}

使用 Tushare DB 查询:
  SELECT cal_date, is_open, pretrade_date FROM _meta.trade_cal FINAL
  WHERE exchange = 'SSE' AND cal_date <= 20260511
  ORDER BY cal_date DESC LIMIT 10

输出最近交易日（YYYYMMDD 格式）、是否为今日、下一交易日。

将查询结果写入日志：{STRATEGY_DIR}/logs/screen-20260511-01-trade_cal.md
""")

    # ===== T2: A股日线扫描 =====
    t2 = create_task(cur, make_id(), "T2 — A股日线扫描", "researcher", f"""
{tc}

你是数据研究员。获取 A 股市场最新数据快照。
{researcher_soul}

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
   WHERE trade_date >= '最近交易日-10' AND pe > 0 AND pe < 500 AND pb > 0
   GROUP BY trade_date ORDER BY trade_date DESC

将查询结果写入日志：{STRATEGY_DIR}/logs/screen-20260511-02-market_scan.md
""")

    # ===== T3: MT5全球行情 + global-futures =====
    t3 = create_task(cur, make_id(), "T3 — MT5全球行情 + 国际期货", "researcher", f"""
{tc}

你是数据研究员。获取全球市场最新行情并映射到 A 股对应板块。
{researcher_soul}

第一部分：MT5 全球行情
通过 WSL 调用 Windows Python: /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe
必须用 inline -c 方式，try/finally 包裹 mt5.shutdown()。
获取以下 symbol 的 tick + 5 根 D1 K线（Python API 中不带 m 后缀）:
XAUUSD, USOIL, UKOIL, US30, US500, USTEC, JP225, HK50, USDCNH, USDJPY, BTCUSD

第二部分：global-futures 国际期货
脚本路径: /mnt/f/AIcoding_space/skills/global-futures/scripts/global_futures.py
sys.path.insert(0, r"/mnt/f/AIcoding_space/skills/global-futures/scripts")
from global_futures import GlobalFutures
gf = GlobalFutures()
获取以下品种的价格和近 3 个月趋势:
谷物: Corn, Soybean, Wheat, SoybeanMeal
软商品: Sugar11, Cotton, Canola
能源: CrudeOil, BrentOil, NaturalGas
金属: Gold, Silver, Copper
利率: Treasury10Y, Treasury30Y

对每个品种输出: 最新价格、涨跌幅、近 3 个月趋势方向、对 A 股的映射判断。
将结果写入日志：{STRATEGY_DIR}/logs/screen-20260511-03-global_markets.md
""")

    # ===== T4: Tavily新闻搜索 =====
    t4 = create_task(cur, make_id(), "T4 — Tavily新闻搜索", "researcher", f"""
{tc}

你是数据研究员。搜索当日影响 A 股的重要新闻。
{researcher_soul}

使用 tavily_search 进行以下搜索（总轮次 <= 4，总搜索词 <= 16）:

1. 宏观政策: "中国 宏观经济 政策 央行 货币政策 财政 降准 降息 2026"
2. 行业催化: "A股 行业 利好 政策 板块 2026"
3. 地缘/国际事件: "中美贸易 关税 半导体 科技制裁 最新 2026"
4. 重要公告: "A股 重大公告 重组 减持 增持 业绩 2026"

权威新闻源优先：Reuters, Bloomberg, CNBC, 金十数据, 华尔街见闻, 东方财富, 新浪财经, AP News, BBC, WSJ, FT, 36氪, 虎嗅, 晚点 LatePost
数据新鲜度要求：财经 4h 内、政治 6h 内、科技 12h 内

每条新闻输出：标题、来源、日期、1-2 句摘要、影响方向（正面/负面/中性）、可信度。
绝对禁止用 tavily_search 查询价格/指数/汇率等数值行情。
将搜索结果写入日志：{STRATEGY_DIR}/logs/screen-20260511-04-news.md
""")

    # ===== T5: 财经专家全市场扫描 (depends on T1-T4) =====
    t5 = create_task(cur, make_id(), "T5 — 财经专家全市场扫描", "analyst", f"""
{tc}

你是财经专家。任务：基于研究员提供的全部数据，做全市场扫描，给出较宽的初始候选池。
{analyst_soul}

角色定义:
- 你是财经专家，负责从全市场角度识别活跃方向和资金偏好
- 你不是最终裁决者，你的输出将交由主控进行初筛压缩
- 你不得给出最终可执行名单或宣布"已收敛"

财经专家核心能力（必须覆盖）:
1. 全市场强弱与板块梯队判断
2. 龙头/次龙/补涨/套利票/伪强势票区分
3. 板块内部位置比较（龙头/次龙/补涨/低位预备突破）
4. 资金是否已充分定价与预期差识别
5. 双周期模型：中国经济周期 vs 美国经济周期
6. 资金联动模型：北向资金（配置盘vs交易盘）+ 南向资金
7. 全市场强度与位置模型：涨停家数、首板数量、炸板率、量价结构
8. 短线新开仓模型：竞价预期、盘中承接、股性、辨识度、题材强度、次日空间

你必须明确区分每只候选属于: 产业主线龙头 / 题材龙头 / 跟风补涨 / 套利票 / 伪强势票

输入数据: 读取 T1-T4 的日志文件。

操作步骤:
第一步：判断当前市场情绪周期（启动/发酵/高潮/退潮）
第二步：识别主线/次主线
第三步：生成宽候选池（不限数量）
第四步：为每只候选给出分项评分（板块强度分/资金认可分/位置分/预期差分/次日空间分/个股交易性分/资金结构风险等级）
第五步：输出格式（每只候选包含完整字段 + 最大失败路径 + 是否建议降级 + 降级触发条件）

搜索协议：总搜索轮次 <= 4，总搜索词 <= 16，权威新闻源优先。

将分析结果写入日志：{STRATEGY_DIR}/logs/screen-20260511-05-finance_scan.md
""", parents=[t1, t2, t3, t4])

    # ===== T6: 主控初筛压缩 (depends on T5) =====
    t6 = create_task(cur, make_id(), "T6 — 主控初筛压缩", "analyst", f"""
{tc}

你是主控分析师。任务：对财经专家的宽候选池进行初筛压缩到 12-20 只。
{analyst_soul}

角色定义:
- 你是主控，负责流程协调、评分裁决
- 你基于财经专家（T5）的输出来定义本轮分析主框架
- 你将输出交给四专家做专项加减分

核心原则:
- 先找待涨，再找可执行
- 待涨观察池占比 >= 50%
- 不得由当天已涨停/已走强票主导候选池
- 情绪周期权重切换：启动期重预期差分/位置分/次日空间分，发酵期重板块强度/资金认可/交易性，高潮期重接盘风险约束，退潮期默认降级

Reze 核心能力（短线六锚点）:
1. 情绪周期 2. 龙头梯队 3. 量价结构 4. 执行窗口 5. 关键价位 6. 待涨/接盘识别

逐票待涨/接盘判定：对每只候选显式判断"待涨票"或"接盘票"

每只候选必须包含：标的/所处分层/当前最新价/价格来源+retrievedAt/K线来源+retrievedAt/最小K线结构判断/位置分/预期差分/次日空间分/市场环境分/接盘风险等级/主线归属/核心逻辑/触发条件/失效条件/降级理由

将分析结果写入日志：{STRATEGY_DIR}/logs/screen-20260511-06-main_screen.md
""", parents=[t5])

    # ===== T7: 报告生成 (depends on T6) =====
    t7 = create_task(cur, make_id(), "T7 — 报告生成", "writer", f"""
{tc}

你是报告撰写人。任务：将主控初筛结果生成标准 markdown 报告。
{writer_soul}

文件命名：shortline-screen-202605110956.md
保存到：{STRATEGY_DIR}/reports/

\u26a0\ufe0f 强制要求：
在报告开头，你必须读取并引用 {STRATEGY_DIR}/logs/screen-20260511-01-trade_cal.md。
明确写出："分析基准: YYYY-MM-DD (周几)" 和 "下一交易日: YYYY-MM-DD (周几)"。
禁止自行推测日期。

报告结构:
1. 当前市场判断（情绪周期/主线/全球环境）
2. 三层候选池总览（待涨观察池/预备突破池/强确认跟踪池）
3. 候选明细（逐票完整字段）
4. 被降级/未纳入的高风险样本
5. 下一次复核点

将生成的报告同时写入日志：{STRATEGY_DIR}/logs/screen-20260511-07-report.md
""", parents=[t6])

    conn.commit()
    conn.close()
    print(f"\nDone! Created 7 tasks (T1-T7) for 2026-05-11 screening pipeline.")
    print(f"Task IDs: T1={t1}, T2={t2}, T3={t3}, T4={t4}, T5={t5}, T6={t6}, T7={t7}")

if __name__ == "__main__":
    main()
