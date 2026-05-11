#!/usr/bin/env python3
"""Create T15, T16, T17 tasks for pre-open confirmation pipeline."""
import sqlite3
import time
import hashlib

conn = sqlite3.connect("/home/gjtmux/.hermes/profiles/reze/kanban.db")
cur = conn.cursor()

now = int(time.time())
strategy_dir = "/mnt/f/AIcoding_space/Hermes/A_stock/kanban/strategy/a-stock-shortline"


def make_id(title):
    return "t_" + hashlib.md5((title + str(now)).encode()).hexdigest()[:8]


# --- T15 ---
t15_id = make_id("T15")
t15_body = """你是数据研究员。任务：对上一轮收敛结果中的每只候选进行盘前价格校验。

读取最新收敛报告：./reports/
找到文件名以 shortline-screen- 或 shortline-candidates- 开头的最新报告，从中提取候选股票代码列表（6-10 只）。

对每只票执行（使用 Tushare DB，SQL 必须加 FINAL，日期 YYYYMMDD）:

1. 最新价校验:
   SELECT ts_code, trade_date, open, high, low, close, vol, pct_chg
   FROM tushare.tushare_stock_daily FINAL
   WHERE ts_code = '{code}' AND trade_date >= '{最近交易日-3}'
   ORDER BY trade_date DESC LIMIT 5

2. 隔夜外盘影响（MT5）:
   通过 WSL 调用 Windows Python: /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe
   获取 US30/US500/USTEC 的隔夜收盘表现、HK50/JP225 的最新表现。
   必须用 inline -c 方式，try/finally 包裹 mt5.shutdown()。
   symbol 不带 m 后缀。

3. 隔夜新闻催化（Tavily）:
   tavily_search("{股票名称/板块} 隔夜 最新 2026", max_results=3)
   总搜索轮次 <= 3，绝对禁止查询数值行情。

输出：
- 每只票的最新价 + 与前一日收盘价对比
- 是否有跳空高开/低开
- 是否有隔夜重大新闻影响
- MT5 相关 symbol 隔夜表现

将校验结果写入日志：./logs/preopen-20260508-15-price_check.md"""

cur.execute(
    """INSERT INTO tasks (id, title, body, assignee, status, priority, created_at, workspace_kind, workspace_path)
       VALUES (?, ?, ?, ?, 'todo', 0, ?, 'dir', ?)""",
    (t15_id, "T15 盘前价格校验 + 隔夜表现 (2026-05-08)", t15_body, "researcher", now, strategy_dir),
)
print(f"T15 created: {t15_id}")

# --- T16 ---
t16_id = make_id("T16")
t16_body = """你是主控分析师。任务：对上一轮候选进行盘前校验，判断保留/降级/放弃和分层迁移。

角色定义:
- 你是主控
- 你不是重新大范围选股，而是基于上一轮候选池做"盘前校验 + 分层迁移 + 降级/保留"
- 核心是"校验和降级"，不是重新讲故事

Reze 核心能力（短线六锚点）:
1. 情绪周期 2. 龙头梯队 3. 量价结构 4. 执行窗口 5. 关键价位 6. 待涨/接盘识别

输入数据: 读取 T15 日志（./logs/preopen-20260508-15-price_check.md）+ 最新收敛报告（./reports/shortline-screen-202605080700.md 或 ./reports/shortline-candidates-202605071357.md）。

操作步骤:
第一步：逐票校验
对每只候选重新校验:
- 当前最新价 + 价格来源 + retrievedAt
- 是否触发原执行条件
- 是否触发原失效条件
- 所处分层是否需要迁移
- 位置分、预期差分、次日空间分是否仍成立
- 接盘风险等级是否抬升

第二步：分层迁移
对每只票判断:
- 继续可执行: 条件仍然成立
- 条件成立后可执行: 需满足额外条件
- 降级为观察: 条件部分不成立
- 放弃: 条件完全不成立或出现新风险

禁止:
- 禁止重新大规模扩池
- 禁止不校验价格就沿用前一晚结论
- 禁止把盘后候选直接当成盘前必买名单
- 若高位一致性风险显著上升 → 必须优先降级

输出格式:
每只票包含: 标的/上一轮状态 vs 本轮状态/最新价校验结果/分层迁移结论及原因/重点观察项

将分析结果写入日志：./logs/preopen-20260508-16-migration.md"""

cur.execute(
    """INSERT INTO tasks (id, title, body, assignee, status, priority, created_at, workspace_kind, workspace_path)
       VALUES (?, ?, ?, ?, 'todo', 0, ?, 'dir', ?)""",
    (t16_id, "T16 主控分层迁移判断 (2026-05-08)", t16_body, "analyst", now + 1, strategy_dir),
)
print(f"T16 created: {t16_id}")

# --- T17 ---
t17_id = make_id("T17")
t17_body = """你是报告撰写人。任务：将盘前确认结果生成标准 markdown 报告。

文件命名：preopen-check-20260508{HHMM}.md
保存到：./reports/

报告结构:
1. 上一轮候选回顾
2. 当前最新价校验
3. 三层候选池迁移结果
4. 继续可执行名单
5. 被降级名单
6. 被放弃名单
7. 竞价/开盘前30分钟重点观察项

输入数据: 读取 T16 日志（./logs/preopen-20260508-16-migration.md）+ T15 日志（./logs/preopen-20260508-15-price_check.md）。

将生成的报告同时写入日志：./logs/preopen-20260508-17-report.md"""

cur.execute(
    """INSERT INTO tasks (id, title, body, assignee, status, priority, created_at, workspace_kind, workspace_path)
       VALUES (?, ?, ?, ?, 'todo', 0, ?, 'dir', ?)""",
    (t17_id, "T17 盘前确认报告生成 (2026-05-08)", t17_body, "writer", now + 2, strategy_dir),
)
print(f"T17 created: {t17_id}")

# --- Task Links ---
cur.execute("INSERT INTO task_links (parent_id, child_id) VALUES (?, ?)", (t15_id, t16_id))
print(f"Link: {t15_id} -> {t16_id}")

cur.execute("INSERT INTO task_links (parent_id, child_id) VALUES (?, ?)", (t16_id, t17_id))
print(f"Link: {t16_id} -> {t17_id}")

conn.commit()

# Verify
print("\n=== VERIFICATION ===")
for row in cur.execute(
    "SELECT id, title, status, assignee FROM tasks WHERE id IN (?, ?, ?)",
    (t15_id, t16_id, t17_id),
):
    print(row)

print("\n=== LINKS ===")
for row in cur.execute(
    "SELECT parent_id, child_id FROM task_links WHERE parent_id IN (?, ?, ?) OR child_id IN (?, ?, ?)",
    (t15_id, t16_id, t17_id, t15_id, t16_id, t17_id),
):
    print(row)

conn.close()
print("\nDone!")
