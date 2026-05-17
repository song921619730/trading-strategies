#!/usr/bin/env python3
"""Pipeline orchestrator for iteration 33 - Background poller"""
import sqlite3, time, subprocess, json, os, sys
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER = 33
ITSDIR = f"{STRATEGY_DIR}/logs/iter_{ITER}"

# Task IDs
ANALYST_IDS = {"T2": "t_ea8b4b05", "T3": "t_9a23a6d6", "T4": "t_6c13f566", "T5": "t_db2357a8", "T6": "t_c03d8406", "T7": "t_024dbba8", "T8": "t_8234c99a", "T9": "t_1471c786", "T10": "t_786173bf", "T11": "t_411d13ad", "T12": "t_f0e52daa"}
ANALYST_ID_LIST = sorted(ANALYST_IDS.values())

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    os.makedirs(f"{STRATEGY_DIR}/logs", exist_ok=True)
    with open(f"{STRATEGY_DIR}/logs/poller.log", "a") as f:
        f.write(line + "\n")

def kanban_create(title, assignee, body, parents=None, max_runtime=600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR creating task: {result.stderr[:200]}")
        return None
    try:
        return json.loads(result.stdout)["id"]
    except:
        return None

def wait_for_tasks(task_ids, label="tasks", poll_interval=60, timeout=43200):
    """Wait until all tasks are done. Returns True if all done, False if timeout."""
    start = time.time()
    while time.time() - start < timeout:
        conn = sqlite3.connect(DB)
        pending = []
        for tid in task_ids:
            row = conn.execute("SELECT id, status FROM tasks WHERE id=?", (tid,)).fetchone()
            if row and row[1] != "done":
                pending.append(row)
        conn.close()

        if not pending:
            log(f"  All {label} completed!")
            return True

        elapsed = int(time.time() - start)
        done_count = len(task_ids) - len(pending)
        log(f"  {done_count}/{len(task_ids)} done | elapsed={elapsed}s | pending: {[(p[0][:10], p[1]) for p in pending]}")
        time.sleep(poll_interval)

    log(f"  TIMEOUT waiting for {label} after {timeout}s")
    return False

log(f"=== Poller Iteration {ITER} started ===")
log(f"Analyst IDs: {ANALYST_ID_LIST}")

# === Phase 2: Wait for T2-T12 analysts ===
log("Phase 2: Waiting for T2-T12 analysts to complete...")
os.makedirs(ITSDIR, exist_ok=True)
wait_for_tasks(ANALYST_ID_LIST, label=f"T2-T12 analysts (iter {ITER})")
log("All analysts completed!")

# === Phase 3: Create T13 convergence ===
log("Phase 3: Creating T13 convergence...")
# Read state for context
with open(f"{STRATEGY_DIR}/state/state.json") as f:
    s = json.load(f)

ts_now = datetime.now().strftime("%Y-%m-%d %H:%M")
best_wr_local = s['best_metrics']['win_rate_5d']
best_r5_local = s['best_metrics']['ret_5d']

t13_body = (
    "## \u23f0 \u65f6\u95f4\u4e0a\u4e0b\u6587\uff08\u5f3a\u5236\u9075\u5b88\uff09\n"
    f"- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a{ts_now} UTC+8\n"
    f"- \u8fed\u4ee3\u7f16\u53f7\uff1aiter {ITER}\n"
    f"- \u5386\u53f2\u6700\u4f73WR\uff1a{best_wr_local}%\n"
    f"- \u5386\u53f2\u6700\u4f73R5\uff1a{best_r5_local}%\n"
    "\n"
    f"# T13: \u4e3b\u63a7\u6536\u655b (Iter{ITER})\n\n"
    "## \u4efb\u52a1\n"
    "1. \u8bfb\u53d6 T2-T12 \u6240\u6709\u5206\u6790\u5e08\u8f93\u51fa\u6587\u4ef6\n"
    "2. \u6458\u53d6\u5404\u6d41\u6d3e\u6700\u4f73\u53c2\u6570\u7ec4\u5408\uff08\u6309 WR/R5/Sharpe/P10 \u7efc\u5408\u8bc4\u5206\uff09\n"
    "3. \u8de8\u6d41\u6d3e comparison: \u54ea\u4e2a\u6d41\u6d3e\u672c\u8f6e\u8868\u73b0\u6700\u597d\uff1f\n"
    "4. \u786e\u8ba4\u662f\u5426\u6709\u65b0\u5168\u5c40\u7eaa\u5f55\u7a81\u7834\uff08WR > {best_wr_local}% \u6216 R5 > {best_r5_local}%\uff09\n"
    "5. \u66f4\u65b0 state.json \u7684 best_metrics\u3001fatigue_count\u3001current_iteration\u3001history\n"
    f"6. \u5199\u5165 {STRATEGY_DIR}/logs/iter_{ITER}/13-convergence.md\n"
    "\n"
    "## \u8f93\u51fa\u683c\u5f0f\n"
    "- \u5404\u6d41\u6d3e\u6700\u4f73\u7ec4\u5408\u4e00\u89c8\n"
    "- \u672c\u8f6e\u65b0\u53d1\u73b0\u7684\u56e0\u5b50\n"
    "- \u65b0\u5168\u5c40\u7eaa\u5f55\u6307\u6807\uff08\u5982\u6709\uff09\n"
    "- \u75b2\u52b3\u503c\u53d8\u5316\n"
    f"- \u5199\u5165\uff1a{STRATEGY_DIR}/logs/iter_{ITER}/13-convergence.md\n"
    "\n"
    "## \u6570\u636e\u89c4\u5219\n"
    "- \u4e3b\u677f\u8fc7\u6ee4\uff1ats_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'\n"
    "- \u65e5\u671f\u683c\u5f0f\uff1aYYYYMMDD\n"
)

t13_id = kanban_create(
    f"T13: \u4e3b\u63a7\u6536\u655b (iter {ITER})",
    "analyst",
    t13_body,
    parents=ANALYST_ID_LIST,
    max_runtime=10800
)

if t13_id:
    log(f"Created T13 convergence -> {t13_id}")
else:
    log("FAILED to create T13!")
    sys.exit(1)

# === Phase 4: Wait for T13 ===
log("Phase 4: Waiting for T13 convergence...")
wait_for_tasks([t13_id], label="T13 convergence", poll_interval=120)

# === Phase 5: Create T14 report ===
log("Phase 5: Creating T14 report...")

date_str = datetime.now().strftime("%Y%m%d")

t14_body = (
    "## \u23f0 \u65f6\u95f4\u4e0a\u4e0b\u6587\uff08\u5f3a\u5236\u9075\u5b88\uff09\n"
    f"- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n"
    f"- \u8fed\u4ee3\u7f16\u53f7\uff1aiter {ITER}\n"
    "\n"
    f"# T14: \u62a5\u544a\u751f\u6210 (Iter{ITER})\n\n"
    "## \u4efb\u52a1\n"
    "1. \u8bfb\u53d6 T13 \u6536\u655b\u62a5\u544a\n"
    "2. \u751f\u6210\u683c\u5f0f\u5316\u62a5\u544a\n"
    "3. \u5305\u542b\uff1a\u672c\u8f6e\u6982\u89c8\u3001\u5404\u6d41\u6d3e\u6700\u4f73\u3001\u65b0\u53d1\u73b0\u3001\u75b2\u52b3\u72b6\u6001\n"
    f"4. \u8f93\u51fa\u5230\uff1a{STRATEGY_DIR}/reports/mining-iter{ITER}-{date_str}.md\n"
    "\n"
    "## \u89c4\u5219\n"
    "- \u4fdd\u7559\u6240\u6709\u5206\u6790\u5e08\u5224\u65ad\uff0c\u4e0d\u8981\u6539\u53d8\u7ed3\u8bba\n"
    "- \u4e0d\u8981\u65b0\u589e\u5206\u6790\uff0c\u53ea\u505a\u683c\u5f0f\u5316\u6574\u7406\n"
)

t14_id = kanban_create(
    f"T14: \u62a5\u544a\u751f\u6210 (iter {ITER})",
    "writer",
    t14_body,
    parents=[t13_id],
    max_runtime=1200
)

if t14_id:
    log(f"Created T14 report -> {t14_id}")
else:
    log("FAILED to create T14!")
    sys.exit(1)

log(f"=== Poller Iteration {ITER} COMPLETE ===")
log(f"Pipeline complete: T13={t13_id}, T14={t14_id}")
