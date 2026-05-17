#!/usr/bin/env python3
"""Background poller for Iter30 — waits for T2-T8, creates T9, waits, creates T10, waits, creates T11."""

import sqlite3
import time
import subprocess
import json
import os
from datetime import datetime

STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
KANBAN_DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
ITER = 30

# Task IDs from Phase 1
T1 = "t_23a0b294"
ANALYST_IDS = [
    "t_b2dfd608",  # T2 动量趋势
    "t_d8ccb593",  # T3 反转低吸
    "t_bcb9dd25",  # T4 资金主力
    "t_a5042aba",  # T5 基本面估值
    "t_e80f81c1",  # T6 板块轮动
    "t_bc55b762",  # T7 跨市场联动
    "t_c4b0a14d",  # T8 量价形态
]

ANALYST_NAMES = {
    "t_b2dfd608": "T2_动量趋势",
    "t_d8ccb593": "T3_反转低吸",
    "t_bcb9dd25": "T4_资金主力",
    "t_a5042aba": "T5_基本面估值",
    "t_e80f81c1": "T6_板块轮动",
    "t_bc55b762": "T7_跨市场联动",
    "t_c4b0a14d": "T8_量价形态",
}

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}\n"
    print(line, end="", flush=True)
    with open(f"{STRATEGY_DIR}/logs/poller_iter{ITER}.log", "a") as f:
        f.write(line)

def kanban_create(title, assignee, body, parents=None, max_runtime=600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR creating '{title}': {result.stderr[:200]}")
        return None
    try:
        data = json.loads(result.stdout)
        tid = data.get("id")
        log(f"Created {title}: {tid}")
        return tid
    except json.JSONDecodeError as e:
        log(f"JSON parse error '{title}': {str(e)[:100]}")
        return None

def wait_for_tasks(tids, poll_interval=60, timeout=14400):
    """Poll kanban.db until all task IDs have status='done'."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            conn = sqlite3.connect(KANBAN_DB)
            done = True
            statuses = {}
            for tid in tids:
                row = conn.execute('SELECT status FROM tasks WHERE id=?', (tid,)).fetchone()
                if row is None:
                    statuses[tid] = "NOT_FOUND"
                    done = False
                else:
                    statuses[tid] = row[0]
                    if row[0] != 'done':
                        done = False
            conn.close()
            
            # Show progress
            done_count = sum(1 for s in statuses.values() if s == 'done')
            total = len(tids)
            running = [tid for tid, s in statuses.items() if s == 'running']
            ready = [tid for tid, s in statuses.items() if s == 'ready']
            todo = [tid for tid, s in statuses.items() if s == 'todo']
            
            if done:
                log(f"All {total} tasks done!")
                return True
            else:
                running_names = [ANALYST_NAMES.get(t, t[:20]) for t in running]
                ready_names = [ANALYST_NAMES.get(t, t[:20]) for t in ready]
                todo_names = [ANALYST_NAMES.get(t, t[:20]) for t in todo]
                progress = f"{done_count}/{total} done"
                if running_names:
                    progress += f", running: {running_names}"
                if ready_names:
                    progress += f", ready: {ready_names}"
                if todo_names:
                    progress += f", todo: {todo_names}"
                log(progress)
                
        except Exception as e:
            log(f"Poll error: {str(e)[:100]}")
        
        time.sleep(poll_interval)
    
    log(f"TIMEOUT after {timeout}s — not all tasks completed")
    return False

def read_state():
    with open(f"{STRATEGY_DIR}/state/state.json") as f:
        return json.load(f)

def save_state(state):
    with open(f"{STRATEGY_DIR}/state/state.json", "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

# ============================================================
# Phase 2: Wait for T2-T8, then create T9
# ============================================================

log(f"=== Iter{ITER} Poller started ===")
log(f"Monitoring T2-T8 analyst tasks: {ANALYST_IDS}")

if not wait_for_tasks(ANALYST_IDS):
    log("FATAL: T2-T8 did not complete within timeout")
    log("=== Poller exiting (TIMEOUT) ===")
    exit(1)

log("All T2-T8 complete! Creating T9: 组合交叉验证")

state = read_state()
best_metrics = state.get("best_metrics", {})
recent_combos = state.get("recent_combos", [])

t9_body = (
    "## 📅 时间上下文（强制遵守）\n"
    f"- 系统执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n"
    f"- 本轮迭代编号：{ITER}\n"
    f"- 全局纪录：WR={best_metrics.get('win_rate_5d', 'N/A')}%, R5={best_metrics.get('ret_5d', 'N/A')}%\n\n"
    "---\n"
    f"## T9: 组合交叉验证 (Iter {ITER})\n\n"
    "### 任务\n"
    "1. 读取 T2-T8 所有输出文件\n"
    f"2. 文件位置：{STRATEGY_DIR}/logs/iter_{ITER}/ 目录下的 analysis_T*.md\n"
    "3. 从每个流派的最佳发现中提取关键因子做交叉组合\n"
    "4. 测试至少 12 组跨流派组合\n"
    "5. 输出每组结果：信号数、WR(5D)、R5、R10、R20、夏普比率\n\n"
    "### 数据规则\n"
    "- ClickHouse 查询必须加 FINAL\n"
    "- 日期格式 YYYYMMDD\n"
    "- 主板过滤：ts_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'\n"
    "- 使用 query_sql MCP 工具\n"
    "- net_mf 字段不存在，正确字段是 net_mf_amount\n"
    "- basic_eps_yoy 不可用，改用 netprofit_yoy 或 tr_yoy\n\n"
    "### 成功标准\n"
    "- 至少 3 组通过筛选（WR >= 52% AND R5 >= 3% AND 信号数 >= 200）\n"
    "- 最佳组合应达到 WR >= 85% AND R5 >= 10%\n\n"
    "### 输出要求\n"
    f"- 写入 {STRATEGY_DIR}/logs/iter_{ITER}/analysis_T9_cross.md\n"
    "- 包含所有测试组合的参数、SQL、结果\n"
    "- 标记通过/未通过\n"
    "- 列出最佳组合的完整参数\n"
    "---\n"
    "⚠️ 日志路径为绝对路径，请写入到指定位置。如果某个流派输出文件不存在，跳过该流派。"
)

t9 = kanban_create(
    title=f"T9: 组合交叉验证 (iter {ITER})",
    assignee="analyst",
    body=t9_body,
    parents=ANALYST_IDS,
    max_runtime=10800
)

if not t9:
    log("FATAL: Failed to create T9, aborting")
    exit(1)

# ============================================================
# Phase 3: Wait for T9, then create T10
# ============================================================

log("Waiting for T9 to complete...")
if not wait_for_tasks([t9]):
    log("FATAL: T9 did not complete within timeout")
    exit(1)

log("T9 complete! Creating T10: 主控收敛")

state = read_state()
best_metrics = state.get("best_metrics", {})
recent_combos = state.get("recent_combos", [])

t10_body = (
    "## 📅 时间上下文（强制遵守）\n"
    f"- 系统执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n"
    f"- 本轮迭代编号：{ITER}\n"
    f"- 全局纪录：WR={best_metrics.get('win_rate_5d', 'N/A')}%, R5={best_metrics.get('ret_5d', 'N/A')}%\n"
    f"- 当前疲劳计数：{state.get('fatigue_count', 0)}\n\n"
    "---\n"
    f"## T10: 主控收敛 (Iter {ITER})\n\n"
    "### 任务\n"
    "1. 读取 T2-T9 所有输出文件\n"
    f"2. 文件位置：{STRATEGY_DIR}/logs/iter_{ITER}/ 目录下\n"
    "3. 汇总各流派和交叉验证的通过组合\n"
    "4. 判断是否有策略超越全局纪录（WR >= 99.55% AND R5 >= 25.23%）\n"
    "5. 更新 state.json\n"
    "6. 更新 knowledge_base.md\n\n"
    "### state.json 更新规则\n"
    "- 如果本轮有策略的 WR > 99.55% 或 R5 > 25.23%（同时 信号数 >= 200）→ 更新 best_metrics，fatigue_count = 0\n"
    "- 否则 → fatigue_count += 1\n"
    "- 将本轮所有参数组合的 hash 加入 recent_combos（最近50个）\n"
    "- 将本轮摘要加入 history\n"
    "- 保留 history 最近 50 条\n\n"
    f"### 写入 state.json\n"
    f"使用 Python json 库直接写入 {STRATEGY_DIR}/state/state.json\n\n"
    f"### 更新 knowledge_base.md\n"
    f"- 追加到 {STRATEGY_DIR}/state/knowledge_base.md\n"
    "- 格式：YYYY-MM-DD (iter N) - 流派名 + 参数 + 指标 + SQL片段 + 结论 + 状态\n\n"
    "### 输出要求\n"
    f"- 写入 {STRATEGY_DIR}/logs/iter_{ITER}/analysis_T10_convergence.md\n"
    "- 包含跨流派总成绩单、各流派最佳对比、突破发现汇总、下轮建议\n\n"
    "### 数据规则\n"
    "- 日期格式 YYYYMMDD\n"
    "- 主板过滤：ts_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'\n"
    "---\n"
    "⚠️ 此任务完成后，迭代 30 的数据和发现将持久化到 state.json。"
)

t10 = kanban_create(
    title=f"T10: 主控收敛 (iter {ITER})",
    assignee="analyst",
    body=t10_body,
    parents=[t9],
    max_runtime=7200
)

if not t10:
    log("FATAL: Failed to create T10, aborting")
    exit(1)

# ============================================================
# Phase 4: Wait for T10, then create T11
# ============================================================

log("Waiting for T10 to complete...")
if not wait_for_tasks([t10]):
    log("FATAL: T10 did not complete within timeout")
    exit(1)

log("T10 complete! Creating T11: 报告生成")

state = read_state()
best_metrics = state.get("best_metrics", {})
latest_history = state.get("history", [{}])[0] if state.get("history") else {}

t11_body = (
    "## 📅 时间上下文（强制遵守）\n"
    f"- 系统执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n"
    f"- 本轮迭代编号：{ITER}\n\n"
    "---\n"
    f"## T11: 报告生成 (Iter {ITER})\n\n"
    "### 任务\n"
    "1. 读取 T10 收敛结果\n"
    f"2. 文件：{STRATEGY_DIR}/logs/iter_{ITER}/analysis_T10_convergence.md\n"
    f"3. 读取 state.json: {STRATEGY_DIR}/state/state.json\n"
    f"4. 读取 knowledge_base: {STRATEGY_DIR}/state/knowledge_base.md\n\n"
    "### 报告内容\n"
    "- 迭代编号和时间\n"
    "- Top 5 策略排名（按综合评分：WR*R5*信号数）\n"
    "- 各流派表现对比表格\n"
    "- 关键发现总结\n"
    "- 与全局纪录对比\n"
    "- 下轮建议（最多 8 条）\n"
    "- 疲劳状态提醒\n\n"
    "### 格式要求\n"
    f"- 保存到 {STRATEGY_DIR}/reports/mining-all167-iter{ITER}-{datetime.now().strftime('%Y%m%d-%H%M')}.md\n"
    "- Markdown 格式，清晰易读\n"
    "- 必须从 T10 收敛报告中读取准确的数据，不得自行推测\n"
    "- 股票代码必须同时包含代码和名称（如 600984.SH 建设机械）\n\n"
    "### 报告中的日期必须遵守以下规则\n"
    "- 报告开头的 基准日期 和 下一交易日 必须从 T1 trade calendar 数据读取\n"
    "- 禁止使用'周一/周五'等推测词\n"
    "- 如无 T1 trade calendar 数据，使用系统执行日期\n"
)

t11 = kanban_create(
    title=f"T11: 报告生成 (iter {ITER})",
    assignee="writer",
    body=t11_body,
    parents=[t10],
    max_runtime=600
)

if not t11:
    log("FATAL: Failed to create T11")
    exit(1)

log(f"=== Iter{ITER} pipeline fully deployed ===")
log(f"Task graph: T1->[T2..T8]->T9->T10->T11")
log(f"T1={T1}")
log(f"Analysts: {ANALYST_IDS}")
log(f"T9={t9}")
log(f"T10={t10}")
log(f"T11={t11}")
log("Poller exiting — dispatcher handles the rest")
log(f"=== Iter{ITER} Poller END ===")
