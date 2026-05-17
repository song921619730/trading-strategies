#!/usr/bin/env python3
"""
Iter 35 poller — waits for T2-T12 analysts, creates T13 convergence and T14 report.
Spawning: subprocess.Popen + nohup + preexec_fn=os.setpgrp
"""
import sqlite3, time, subprocess, json, sys, os
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER = 35

# Analyst task IDs (T2-T12)
ANALYST_IDS = ["t_037502f1", "t_886a8f10", "t_05c0f3d8", "t_34be10df", "t_58596afd", "t_7d2ca4e3", "t_65cd4b8c", "t_8c26ee85", "t_27f78125", "t_c640a562", "t_40914575"]

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(f"{STRATEGY_DIR}/logs/poller_iter{ITER}.log", "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}", flush=True)

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
    return json.loads(result.stdout)["id"]

def kanban_complete(task_id, summary):
    result = subprocess.run(
        ["hermes", "kanban", "complete", task_id, "--summary", summary],
        capture_output=True, text=True
    )
    return result.returncode == 0

def wait_tasks(tids, timeout=43200, check_interval=60):
    """Wait for all tasks to reach 'done' status."""
    start = time.time()
    while True:
        if time.time() - start > timeout:
            log(f"TIMEOUT after {timeout}s waiting for {len(tids)} tasks")
            return False
        
        try:
            conn = sqlite3.connect(DB)
            done_count = 0
            for tid in tids:
                row = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
                if row and row[0] == "done":
                    done_count += 1
                elif row and row[0] == "failed":
                    log(f"WARNING: Task {tid} has status 'failed' — continuing anyway")
                    done_count += 1
            conn.close()
            
            elapsed = int(time.time() - start)
            elapsed_m = elapsed // 60
            log(f"Progress: {done_count}/{len(tids)} done | elapsed={elapsed_m}m")
            
            if done_count >= len(tids):
                return True
        except Exception as e:
            log(f"DB error: {e}")
        
        time.sleep(check_interval)

log(f"=== Iter {ITER} Background Poller Started ===")
log(f"Watching {len(ANALYST_IDS)} analyst tasks")

# Phase 1: Wait for all analysts (T2-T12)
log("Phase 1: Waiting for T2-T12 analysts to complete...")
if not wait_tasks(ANALYST_IDS, timeout=43200):
    log("FATAL: Timeout waiting for analysts. Exiting.")
    sys.exit(1)

log("All analysts done! Creating T13 convergence...")

# Phase 2: Create T13 convergence
ts_now = datetime.now().strftime("%Y-%m-%d %H:%M")
t13_body = (
    "## \u23f0 \u65f6\u95f4\u4e0a\u4e0b\u6587\uff08\u5f3a\u5236\u9075\u5b88\uff09\n"
    f"- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a{ts_now} UTC+8\n"
    f"- \u8fed\u4ee3\u7f16\u53f7\uff1aiter {ITER}\n"
    "\n"
    "## \u4efb\u52a1\uff1a\u4e3b\u63a7\u6536\u655b\uff08\u8de8\u6d41\u6d3e\u8bc4\u4f30\uff09\n"
    "\u4f60\u662f\u4e3b\u63a7\u5206\u6790\u5e08\uff0c\u8d1f\u8d23\u6536\u96c6\u6240\u6709\u6d41\u6d3e\u5206\u6790\u5e08\uff08T2-T12\uff09\u7684\u8f93\u51fa\uff0c\u5e76\u505a\u51fa\u7efc\u5408\u8bc4\u4f30\u3002\n"
    "\n"
    "### \u6b65\u9aa4\n"
    "1. \u8bfb\u53d6\u6240\u6709\u6d41\u6d3e\u5206\u6790\u6587\u4ef6\uff08\u4ece {STRATEGY_DIR}/logs/iter_{ITER}/ \u76ee\u5f55\uff09\n"
    "2. \u5bf9\u6bcf\u4e2a\u6d41\u6d3e\u7684 PASS \u7ec4\u5408\u8fdb\u884c\u8de8\u6d41\u6d3e\u5bf9\u6bd4\n"
    "3. \u8bc4\u4f30\u662f\u5426\u6709\u65b0\u7684\u5168\u5c40\u7eaa\u5f55\u7a81\u7834\uff08WR>=99.59% \u6216 R5>=25.23%\uff09\n"
    "4. \u8bc4\u4f30 fatigue_count\uff1a\u5982\u679c\u6709\u65b0\u7eaa\u5f55\u2192reset=0\uff0c\u5426\u5219+=1\n"
    "5. \u66f4\u65b0 state.json\uff08\u5305\u62ec history \u6570\u7ec4\uff09\n"
    f"6. \u8f93\u51fa\u5230\uff1a{STRATEGY_DIR}/logs/iter_{ITER}/13-convergence.md\n"
    f"7. \u540c\u6b65\u66f4\u65b0 state.json \u81f3 {STRATEGY_DIR}/state/state.json\n"
    "\n"
    "### \u6570\u636e\u89c4\u5219\n"
    "- \u6240\u6709\u5206\u6790\u6587\u4ef6\u90fd\u5728 {STRATEGY_DIR}/logs/iter_{ITER}/ \u4e0b\n"
    "- \u6587\u4ef6\u547d\u540d\u683c\u5f0f\uff1aanalysis_T{N}_{\u6d41\u6d3e\u540d}.md\n"
    "- \u5982\u679c\u67d0\u4e2a\u6587\u4ef6\u4e0d\u5b58\u5728\uff0c\u7b49\u5f8530\u79d2\u91cd\u8bd5\uff0c\u6700\u591a3\u6b21\n"
    "\n"
    "### \u8bc4\u4f30\u6807\u51c6\n"
    "- WR>=99.59% (\u5f53\u524d\u5168\u5c40WR\u7eaa\u5f55)\n"
    "- R5>=25.23% (\u5f53\u524d\u5168\u5c40R5\u7eaa\u5f55)\n"
    "- \u4fe1\u53f7\u6570>=200\n"
    "- Walk-Forward \u53cc\u91cd\u9a8c\u8bc1\u901a\u8fc7\n"
)

t13_id = kanban_create(
    f"T13: \u4e3b\u63a7\u6536\u655b (iter {ITER})",
    "analyst",
    t13_body,
    parents=ANALYST_IDS,
    max_runtime=10800
)

if not t13_id:
    log("FATAL: Failed to create T13")
    sys.exit(1)

log(f"T13 created: {t13_id}")

# Phase 3: Wait for T13
log("Phase 3: Waiting for T13 convergence...")
if not wait_tasks([t13_id], timeout=21600):
    log("FATAL: Timeout waiting for T13")
    sys.exit(1)

log("T13 done! Creating T14 report...")

# Phase 4: Create T14 report
ts_now2 = datetime.now().strftime("%Y-%m-%d %H:%M")
t14_body = (
    "## \u23f0 \u65f6\u95f4\u4e0a\u4e0b\u6587\uff08\u5f3a\u5236\u9075\u5b88\uff09\n"
    f"- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a{ts_now2} UTC+8\n"
    f"- \u8fed\u4ee3\u7f16\u53f7\uff1aiter {ITER}\n"
    "\n"
    "## \u4efb\u52a1\uff1a\u62a5\u544a\u751f\u6210\n"
    "\u4f60\u662f\u62a5\u544a\u4e13\u5bb6\uff0c\u8d1f\u8d23\u5c06\u4e3b\u63a7\u6536\u655b\uff08T13\uff09\u7684\u7ed3\u8bba\u8f6c\u5316\u4e3a\u53cb\u597d\u7684\u62a5\u544a\u683c\u5f0f\u3002\n"
    "\n"
    "### \u6b65\u9aa4\n"
    f"1. \u8bfb\u53d6 T13 \u6536\u655b\u6587\u4ef6\uff1a{STRATEGY_DIR}/logs/iter_{ITER}/13-convergence.md\n"
    "2. \u8bfb\u53d6 state.json \u786e\u8ba4\u5f53\u524d\u72b6\u6001\n"
    "3. \u751f\u6210\u62a5\u544a\uff1a\u5305\u62ec\u7efc\u8ff0\u3001\u5404\u6d41\u6d3e\u8868\u73b0\u3001\u6700\u4f73\u7b56\u7565\u6392\u540d\u3001\u65b0\u56e0\u5b50\u53d1\u73b0\u3001fatigue_count\u72b6\u6001\n"
    f"4. \u8f93\u51fa\u5230\uff1a{STRATEGY_DIR}/reports/iter{ITER}_report_{ts_now2[:10].replace('-','')}.md\n"
    "\n"
    "### \u683c\u5f0f\u8981\u6c42\n"
    "- \u62a5\u544a\u5f00\u5934\u5fc5\u987b\u660e\u786e\u5199\u51fa\u201c\u5206\u6790\u57fa\u51c6\u65e5\u671f\u201d\u548c\u201c\u4e0b\u4e00\u4ea4\u6613\u65e5\u201d\uff0c\u5f15\u7528\u6765\u81ea T13 \u8f93\u51fa\n"
    "- \u5728\u62a5\u544a\u672b\u5c3e\u9644\u4e0a\u201c\u4e0b\u8f6e\u5efa\u8bae\u201d\n"
)

t14_id = kanban_create(
    f"T14: \u62a5\u544a\u751f\u6210 (iter {ITER})",
    "writer",
    t14_body,
    parents=[t13_id],
    max_runtime=1200
)

if not t14_id:
    log("FATAL: Failed to create T14")
    sys.exit(1)

log(f"T14 created: {t14_id}")

# Phase 5: Wait for T14
log("Phase 5: Waiting for T14 report...")
if not wait_tasks([t14_id], timeout=7200):
    log("WARNING: Timeout waiting for T14")

log(f"=== Iter {ITER} Pipeline Complete ===")
