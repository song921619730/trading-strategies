#!/usr/bin/env python3
"""
Background poller for mining-all167 Iteration 29.
Waits for T2-T8 analyst tasks to complete, then creates T9/T10/T11 sequentially.
"""
import sqlite3, time, subprocess, json, os, sys
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
LOG_DIR = f"{STRATEGY_DIR}/logs/iter_29"
POLLER_LOG = f"{STRATEGY_DIR}/logs/poller_iter29.log"

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(POLLER_LOG, 'a') as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}", flush=True)

def kanban_create(title, assignee, body, parents=None, max_runtime=10800):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"FAILED kanban_create: {result.stderr[:300]}")
        return None
    try:
        data = json.loads(result.stdout)
        return data.get('id')
    except json.JSONDecodeError:
        log(f"JSON decode error: {result.stdout[:200]}")
        return None

def wait_for_tasks(tids, poll_interval=60, timeout=14400):
    """Poll kanban.db until all tasks are status='done'."""
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            log(f"TIMEOUT after {timeout}s waiting for {tids}")
            return False
        
        done, total = 0, len(tids)
        statuses = []
        try:
            conn = sqlite3.connect(DB)
            cur = conn.cursor()
            for tid in tids:
                cur.execute('SELECT status FROM tasks WHERE id=?', (tid,))
                row = cur.fetchone()
                s = row[0] if row else 'unknown'
                statuses.append(s)
                if s == 'done':
                    done += 1
            conn.close()
        except Exception as e:
            log(f"DB error: {e}")
            time.sleep(poll_interval)
            continue
        
        if done == total:
            log(f"All {total} tasks done!")
            return True
        
        running = sum(1 for s in statuses if s == 'running')
        todo = sum(1 for s in statuses if s in ('todo', 'ready'))
        failed = sum(1 for s in statuses if s not in ('done', 'running', 'todo', 'ready'))
        
        log(f"Progress: {done}/{total} done, {running} running, {todo} waiting, {failed} other")
        time.sleep(poll_interval)

# ─── Phase 1: Wait for T2-T8 analysts to complete ───
analyst_ids = [
    "t_ed0bf104",  # T2 动量趋势
    "t_b3f3510d",  # T3 反转低吸
    "t_18717b0d",  # T4 资金主力
    "t_abc92436",  # T5 基本面估值
    "t_204eaadb",  # T6 板块轮动
    "t_f6e09539",  # T7 跨市场联动
    "t_e7ecc1e3",  # T8 量价形态
]

log("=== Iteration 29 Poller Started ===")
log(f"Waiting for {len(analyst_ids)} analyst tasks T2-T8...")

# Verify tasks were created
try:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    for tid in analyst_ids:
        cur.execute('SELECT id, title, status FROM tasks WHERE id=?', (tid,))
        row = cur.fetchone()
        if row:
            log(f"  Task {row[0]}: {row[1][:50]} status={row[2]}")
        else:
            log(f"  WARNING: Task {tid} not found in DB!")
    conn.close()
except Exception as e:
    log(f"Initial DB check error: {e}")

if not wait_for_tasks(analyst_ids):
    log("Phase 1 FAILED: timeout waiting for analysts")
    sys.exit(1)

# ─── Phase 2: Create T9 (Cross-validation) ───
log("=== Phase 2: Creating T9 (组合交叉验证) ===")

TS = datetime.now().strftime('%Y-%m-%d %H:%M')

t9_body = (
    "## \u23f1\ufe0f 时间上下文（强制遵守）\n"
    f"- 系统执行时间：{TS} UTC+8\n"
    f"- 本轮迭代编号：29\n"
    "\n"
    "## \u4efb\u52a1\uff1a\u7ec4\u5408\u4ea4\u53c9\u9a8c\u8bc1\n"
    "\u4f60\u9700\u8981\u8bfb\u53d6 T2-T8 \u6240\u6709\u8f93\u51fa\uff0c\u4ece\u6bcf\u4e2a\u6d41\u6d3e\u6700\u4f73\u53d1\u73b0\u4e2d\u63d0\u53d6\u56e0\u5b50\u505a\u4ea4\u53c9\u7ec4\u5408\u3002\n\n"
    "## \u6267\u884c\u6b65\u9aa4\n"
    "1. \u8bfb\u53d6\u4ee5\u4e0b\u6587\u4ef6\uff1a\n"
    f"  - {LOG_DIR}/analysis_T2_\u52a8\u91cf\u8d8b\u52bf.md\n"
    f"  - {LOG_DIR}/analysis_T3_\u53cd\u8f6c\u4f4e\u5438.md\n"
    f"  - {LOG_DIR}/analysis_T4_\u8d44\u91d1\u4e3b\u529b.md\n"
    f"  - {LOG_DIR}/analysis_T5_\u57fa\u672c\u9762\u4f30\u503c.md\n"
    f"  - {LOG_DIR}/analysis_T6_\u677f\u5757\u8f6e\u52a8.md\n"
    f"  - {LOG_DIR}/analysis_T7_\u8de8\u5e02\u573a\u8054\u52a8.md\n"
    f"  - {LOG_DIR}/analysis_T8_\u91cf\u4ef7\u5f62\u6001.md\n"
    "2. \u4ece\u6bcf\u4e2a\u6d41\u6d3e\u6700\u4f73\u53d1\u73b0\u4e2d\u63d0\u53d6\u6838\u5fc3\u56e0\u5b50\n"
    "3. \u751f\u6210\u81f3\u5c1110\u7ec4\u8de8\u6d41\u6d3e\u4ea4\u53c9\u7ec4\u5408\n"
    "4. \u5bf9\u6bcf\u7ec4\u7ec4\u5408\u6267\u884cClickHouse SQL\u56de\u6d4b\n"
    "5. \u8bb0\u5f55\u7ed3\u679c\n\n"
    "## \u6570\u636e\u89c4\u5219\n"
    "- \u4f7f\u7528 query_sql MCP \u5de5\u5177\n"
    "- \u5fc5\u987b\u52a0 FINAL\n"
    "- \u65e5\u671f\u683c\u5f0f YYYYMMDD\n"
    "- \u4e3b\u677f\u8fc7\u6ee4\uff1ats_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'\n"
    "- net_mf_amount \u4e0d\u662f net_mf\n"
    "- tr_yoy / netprofit_yoy \u4ee3\u66ff basic_eps_yoy\n\n"
    "## \u8f93\u51fa\n"
    f"\u4fdd\u5b58\u5230\uff1a{LOG_DIR}/analysis_T9_cross.md\n"
    "\u5305\u542b\uff1a\u6bcf\u7ec4\u7ec4\u5408\u7684\u53c2\u6570\u3001SQL\u3001\u6307\u6807\u3001\u6700\u4f73\u53d1\u73b0\u7684\u8be6\u7ec6\u63cf\u8ff0"
)

t9_id = kanban_create(
    f"T9: \u7ec4\u5408\u4ea4\u53c9\u9a8c\u8bc1 (iter 29)",
    "analyst",
    t9_body,
    parents=analyst_ids,
    max_runtime=10800
)

if not t9_id:
    log("FAILED to create T9!")
    sys.exit(1)

log(f"T9 created: {t9_id}")

# ─── Phase 3: Wait for T9 ───
log("Waiting for T9...")
if not wait_for_tasks([t9_id]):
    log("Phase 3 FAILED: timeout waiting for T9")
    sys.exit(1)

# ─── Phase 4: Create T10 (Convergence) ───
log("=== Phase 4: Creating T10 (主控收敛) ===")

TS2 = datetime.now().strftime('%Y-%m-%d %H:%M')

t10_body = (
    "## \u23f1\ufe0f 时间上下文（强制遵守）\n"
    f"- 系统执行时间：{TS2} UTC+8\n"
    f"- 本轮迭代编号：29\n"
    "\n"
    "## 任务：主控收敛\n"
    "读取 T2-T9 所有输出，更新 state.json 和 knowledge_base.md\n\n"
    "## 执行步骤\n"
    "1. 读取以下文件：\n"
    f"  - {LOG_DIR}/analysis_T2_动量趋势.md\n"
    f"  - {LOG_DIR}/analysis_T3_反转低吸.md\n"
    f"  - {LOG_DIR}/analysis_T4_资金主力.md\n"
    f"  - {LOG_DIR}/analysis_T5_基本面估值.md\n"
    f"  - {LOG_DIR}/analysis_T6_板块轮动.md\n"
    f"  - {LOG_DIR}/analysis_T7_跨市场联动.md\n"
    f"  - {LOG_DIR}/analysis_T8_量价形态.md\n"
    f"  - {LOG_DIR}/analysis_T9_cross.md\n"
    "2. 汇总所有流派的 PASS/FAIL 情况\n"
    "3. 找出本轮最佳策略（最高 R5 且 WR >= 52% 且 N >= 200）\n"
    "4. 对比全局纪录（WR=99.55%, R5=25.23%, Sharpe=20.227, Iter25 CROSS-6）\n"
    "5. 更新 state/state.json：\n"
    "   - current_iteration = 29\n"
    "   - 如果本轮有超历史最佳的策略，更新 best_metrics 并设 fatigue_count=0\n"
    "   - 否则 fatigue_count += 1\n"
    "   - 追加本轮摘要到 history\n"
    "   - 追加参数 hash 到 recent_combos\n"
    "6. 更新 state/knowledge_base.md：追加有效发现\n\n"
    "## state.json 更新方式\n"
    "使用 Python 读写 JSON 文件：\n"
    "```python\n"
    "import json\n"
    "with open('state/state.json', 'r') as f:\n"
    "    state = json.load(f)\n"
    "# modify\n"
    "with open('state/state.json', 'w') as f:\n"
    "    json.dump(state, f, indent=2, ensure_ascii=False)\n"
    "```\n\n"
    "## 输出\n"
    f"保存收敛摘要到：{LOG_DIR}/analysis_T10_convergence.md\n"
    "- 包含本轮汇总、流派排名、关键发现、下轮建议"
)

t10_id = kanban_create(
    "T10: 主控收敛 (iter 29)",
    "analyst",
    t10_body,
    parents=[t9_id],
    max_runtime=10800
)

if not t10_id:
    log("FAILED to create T10!")
    sys.exit(1)

log(f"T10 created: {t10_id}")

# ─── Phase 5: Wait for T10 ───
log("Waiting for T10...")
if not wait_for_tasks([t10_id]):
    log("Phase 5 FAILED: timeout waiting for T10")
    sys.exit(1)

# ─── Phase 6: Create T11 (Report) ───
log("=== Phase 6: Creating T11 (报告生成) ===")

TS3 = datetime.now().strftime('%Y-%m-%d %H:%M')
report_filename = f"mining-all167-iter29-{datetime.now().strftime('%Y%m%d-%H%M')}.md"

t11_body = (
    "## \u23f1\ufe0f 时间上下文（强制遵守）\n"
    f"- 系统执行时间：{TS3} UTC+8\n"
    f"- 本轮迭代编号：29\n"
    "\n"
    "## 任务：生成迭代报告\n"
    "读取 T10 收敛结果 + state.json + knowledge_base.md，生成格式化报告。\n\n"
    "## 执行步骤\n"
    "1. 读取 state/state.json 获取本轮汇总\n"
    "2. 读取 state/knowledge_base.md 获取完整知识库\n"
    f"3. 读取 {LOG_DIR}/analysis_T10_convergence.md 获取收敛摘要\n"
    "4. 生成报告，包含：\n"
    "   - Top 5 策略排名（R5 排序）\n"
    "   - 各流派表现对比（PASS 数、平均 R5、最佳 WR）\n"
    "   - 关键发现总结\n"
    "   - 新因子/新模式\n"
    "   - 未超越全局纪录的分析\n"
    "   - 下轮建议方向\n\n"
    "## 报告格式\n"
    "使用 Markdown 格式，包含表格对比各策略。\n\n"
    "## 输出\n"
    f"保存到：{STRATEGY_DIR}/reports/{report_filename}"
)

t11_id = kanban_create(
    "T11: 报告生成 (iter 29)",
    "writer",
    t11_body,
    parents=[t10_id],
    max_runtime=600
)

if not t11_id:
    log("FAILED to create T11!")
    sys.exit(1)

log(f"T11 created: {t11_id}")

# ─── Phase 7: Wait for T11 ───
log("Waiting for T11...")
if not wait_for_tasks([t11_id]):
    log("Phase 7 FAILED: timeout waiting for T11 report")
    sys.exit(1)

log("=== Iteration 29 Pipeline Complete! ===")
log(f"All tasks: T1 -> T2-T8 -> T9 -> T10 -> T11 completed successfully.")
log(f"Report: {STRATEGY_DIR}/reports/{report_filename}")
log("Poller exiting normally.")
