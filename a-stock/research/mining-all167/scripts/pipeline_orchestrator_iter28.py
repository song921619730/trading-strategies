#!/usr/bin/env python3
"""Background poller for Iter28 mining pipeline.
Waits for T2-T8 analysts to complete, then creates T9->T10->T11 sequentially.
"""
import sqlite3, time, subprocess, json, sys, os
from datetime import datetime

# === CONFIG ===
DB_PATH = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER = 28
TS = "2026-05-14 02:01"

ANALYST_TIDS = ["t_3d33a31e", "t_c32413ab", "t_141ab1b5", "t_08c26905", "t_f6623845", "t_96761ebe", "t_a5cf5421"]

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\
"
    with open(f"{STRATEGY_DIR}/logs/poller_iter{ITER}.log", "a") as f:
        f.write(line)
    print(line, end="")

def wait_for_tasks(tids, timeout_seconds=14400, poll_interval=60):
    """Poll kanban.db until all tasks are 'done' or timeout."""
    start = time.time()
    log(f"Waiting for {len(tids)} tasks to complete: {tids}")
    while True:
        elapsed = time.time() - start
        if elapsed > timeout_seconds:
            raise TimeoutError(f"Waited {elapsed:.0f}s for tasks but timeout reached")
        try:
            conn = sqlite3.connect(DB_PATH)
            statuses = {}
            for tid in tids:
                r = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
                statuses[tid] = r[0] if r else "NOT_FOUND"
            conn.close()
            done = all(s == "done" for s in statuses.values())
            if done:
                log(f"All {len(tids)} tasks done!")
                return True
            log(f"Status: {json.dumps(statuses, ensure_ascii=False)}  (elapsed={elapsed:.0f}s)")
            time.sleep(poll_interval)
        except Exception as e:
            log(f"Poll error: {e}, retrying in {poll_interval}s")
            time.sleep(poll_interval)

def kanban_create(title, assignee, body, parents=None, max_runtime=600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR creating task: {result.stderr}")
        return None
    return json.loads(result.stdout)["id"]

# ===== Phase 1: Wait for T2-T8 =====
log("Phase 1: Waiting for T2-T8 analysts to complete...")
try:
    wait_for_tasks(ANALYST_TIDS, timeout_seconds=14400, poll_interval=60)
except TimeoutError as e:
    log(f"TIMEOUT: {e}")
    sys.exit(1)

# ===== Phase 2: Create T9 =====
log("Phase 2: Creating T9 组合交叉验证...")
t9_body = (
    "## Task: 组合派交叉验证\
"
    f"- 系统执行时间：{TS} UTC+8\
"
    f"- 迭代编号：{ITER}\
"
    "\
"
    "## 任务要求\
"
    "1. 读取 T2-T8 所有输出文件\
"
    "2. 从每个流派最佳发现中提取因子做交叉组合\
"
    "3. 至少 10 组交叉组合\
"
    "4. 输出交叉验证结果\
"
    "\
"
    "## 输出\
"
    f"- {STRATEGY_DIR}/logs/iter_{ITER}/analysis_T9_cross.md\
"
    "\
"
    "## 数据规则\
"
    "- 使用 query_sql MCP 工具\
"
    "- 所有查询 FINAL\
"
    "- 主板过滤\
"
    "- 成功标准：WR >= 52%, R5 >= 3%, N >= 200\
"
    "- 关注：是否存在叠加增强效应而非价值毁灭\
"
)

t9_id = kanban_create(
    title=f"Iter{ITER} T9: 组合交叉验证",
    assignee="analyst",
    body=t9_body,
    parents=ANALYST_TIDS,
    max_runtime=10800
)
if not t9_id:
    log("FAILED to create T9. Exiting.")
    sys.exit(1)
log(f"T9 created: {t9_id}")

# ===== Phase 3: Wait for T9 =====
log("Phase 3: Waiting for T9 to complete...")
try:
    wait_for_tasks([t9_id], timeout_seconds=14400, poll_interval=60)
except TimeoutError as e:
    log(f"TIMEOUT: {e}")
    sys.exit(1)

# ===== Phase 4: Create T10 =====
log("Phase 4: Creating T10 主控收敛...")
t10_body = (
    "## Task: 主控收敛\
"
    f"- 系统执行时间：{TS} UTC+8\
"
    f"- 迭代编号：{ITER}\
"
    "\
"
    "## 任务要求\
"
    "1. 读取 T2-T9 所有输出文件\
"
    "2. 更新 state.json（best_metrics, fatigue_count, history, recent_combos）\
"
    "3. 更新 knowledge_base.md（追加有效发现）\
"
    "4. 输出收敛摘要\
"
    "\
"
    "## 输出\
"
    f"- {STRATEGY_DIR}/logs/iter_{ITER}/analysis_T10_convergence.md\
"
    f"- {STRATEGY_DIR}/state/state.json（更新）\
"
    f"- {STRATEGY_DIR}/state/knowledge_base.md（更新）\
"
    "\
"
    "## 更新逻辑\
"
    "- 如果本轮超越历史最佳 → best_metrics更新, fatigue_count=0\
"
    "- 否则 → fatigue_count += 1\
"
    "- 所有新组合hash加入recent_combos（保持最多50条）\
"
    "- 本轮摘要加入history（保持最多50条）\
"
    "- 有效发现追加到knowledge_base.md\
"
)

t10_id = kanban_create(
    title=f"Iter{ITER} T10: 主控收敛",
    assignee="analyst",
    body=t10_body,
    parents=[t9_id],
    max_runtime=3600
)
if not t10_id:
    log("FAILED to create T10. Exiting.")
    sys.exit(1)
log(f"T10 created: {t10_id}")

# ===== Phase 5: Wait for T10 =====
log("Phase 5: Waiting for T10 to complete...")
try:
    wait_for_tasks([t10_id], timeout_seconds=7200, poll_interval=60)
except TimeoutError as e:
    log(f"TIMEOUT: {e}")
    sys.exit(1)

# ===== Phase 6: Create T11 =====
log("Phase 6: Creating T11 报告生成...")
t11_body = (
    "## Task: 报告生成\
"
    f"- 系统执行时间：{TS} UTC+8\
"
    f"- 迭代编号：{ITER}\
"
    "\
"
    "## 任务要求\
"
    "1. 读取 T10 收敛结果\
"
    "2. 读取 state.json 和 knowledge_base.md\
"
    "3. 生成格式化报告\
"
    "\
"
    "## 报告内容\
"
    "- Top 5 策略排名\
"
    "- 各流派表现对比\
"
    "- 关键发现\
"
    "- 下轮建议\
"
    "\
"
    "## 输出\
"
    f"- {STRATEGY_DIR}/reports/mining-all167-iter{ITER}-20260514-HHMM.md\
"
)

t11_id = kanban_create(
    title=f"Iter{ITER} T11: 报告生成",
    assignee="writer",
    body=t11_body,
    parents=[t10_id],
    max_runtime=600
)
if not t11_id:
    log("FAILED to create T11. Exiting.")
    sys.exit(1)
log(f"T11 created: {t11_id}")

log(f"PIPELINE COMPLETE! T9={t9_id}, T10={t10_id}, T11={t11_id}")
log("All tasks created successfully. Dispatcher will handle execution.")
