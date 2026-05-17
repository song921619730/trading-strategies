#!/usr/bin/env python3
"""Background poller for Iter32 — waits for T2-T12, creates T13, waits, creates T14."""

import sqlite3
import time
import subprocess
import json
import os
from datetime import datetime

STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
KANBAN_DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
ITER = 32

# Task IDs from Phase 1 (orchestrator created these)
T1 = "t_d61ff167"
ANALYST_IDS = ["t_6c78aa95", "t_bbd86acd", "t_86cc20a1", "t_34bc98c3", "t_f801c32c", "t_e62fb421", "t_c9e37d06", "t_62caceca", "t_ff5704bd", "t_b91cc5ca", "t_c370ae15"]

ANALYST_NAMES = {"t_6c78aa95": "T2_动量趋势", "t_bbd86acd": "T3_反转低吸", "t_86cc20a1": "T4_资金主力", "t_34bc98c3": "T5_基本面估值", "t_f801c32c": "T6_板块轮动", "t_e62fb421": "T7_跨市场联动", "t_c9e37d06": "T8_量价形态", "t_62caceca": "T9_交叉验证(流派融合)", "t_ff5704bd": "T10_VWAP流动性", "t_b91cc5ca": "T11_DeepTrades", "t_c370ae15": "T12_资金预判"}


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

            done_count = sum(1 for s in statuses.values() if s == 'done')
            total = len(tids)
            running = [tid for tid, s in statuses.items() if s == 'running']
            ready = [tid for tid, s in statuses.items() if s == 'ready']
            todo_tasks = [tid for tid, s in statuses.items() if s == 'todo']

            if done:
                log(f"All {total} tasks done!")
                return True
            else:
                running_names = [ANALYST_NAMES.get(t, t[:20]) for t in running]
                ready_names = [ANALYST_NAMES.get(t, t[:20]) for t in ready]
                todo_names = [ANALYST_NAMES.get(t, t[:20]) for t in todo_tasks]
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

    log(f"TIMEOUT after {timeout}s - not all tasks completed")
    return False


def read_state():
    with open(f"{STRATEGY_DIR}/state/state.json") as f:
        return json.load(f)


def save_state(state):
    with open(f"{STRATEGY_DIR}/state/state.json", "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ============================================================
# Phase 2: Wait for T2-T12, then create T13
# ============================================================

log(f"=== Iter{ITER} Poller started ===")
log(f"Monitoring T2-T12 analyst tasks: {len(ANALYST_IDS)} tasks")

if not wait_for_tasks(ANALYST_IDS):
    log("FATAL: T2-T12 did not complete within timeout")
    log("=== Poller exiting (TIMEOUT) ===")
    exit(1)

log("All T2-T12 complete! Creating T13: 交叉验证收敛")

state = read_state()
best_metrics = state.get("best_metrics", {})
recent_combos = state.get("recent_combos", [])

t13_body = (
    "## \u23f3 \u6642\u9593\u4e0a\u4e0b\u6587\uff08\u5f37\u5236\u9075\u5b88\uff09\n"
    f"- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n"
    f"- \u672c\u8f6e\u8fed\u4ee3\u7f16\u53f7\uff1a{ITER}\n"
    f"- \u5168\u5c40\u7eaa\u9304\uff1aWR={best_metrics.get('win_rate_5d', 'N/A')}%, R5={best_metrics.get('ret_5d', 'N/A')}%\n\n"
    "---\n"
    f"## T13: \u4e3b\u63a7\u6536\u655b (Iter {ITER})\n\n"
    "### \u4efb\u52a1\n"
    "1. \u8bfb\u53d6 T2-T12 \u6240\u6709\u8f93\u51fa\u6587\u4ef6\n"
    f"2. \u6587\u4ef6\u4f4d\u7f6e\uff1a{STRATEGY_DIR}/logs/iter_{ITER}/ \u76ee\u5f55\u4e0b\n"
    "3. \u6c47\u603b\u5404\u6d41\u6d3e\u548c\u4ea4\u53c9\u9a8c\u8bc1\u7684\u901a\u8fc7\u7ec4\u5408\n"
    "4. \u5224\u65ad\u662f\u5426\u6709\u7b56\u7565\u8d85\u8d8a\u5168\u5c40\u7eaa\u5f55\uff08WR >= 99.55% AND R5 >= 25.23%\uff09\n"
    "5. \u66f4\u65b0 state.json\n"
    "6. \u66f4\u65b0 knowledge_base.md\n\n"
    "### state.json \u66f4\u65b0\u89c4\u5219\n"
    "- \u5982\u679c\u672c\u8f6e\u6709\u7b56\u7565\u7684 WR > 99.55% \u6216 R5 > 25.23%\uff08\u540c\u65f6 \u4fe1\u53f7\u6570 >= 200\uff09\u2192 \u66f4\u65b0 best_metrics\uff0cfatigue_count = 0\n"
    "- \u5426\u5219 \u2192 fatigue_count += 1\n"
    "- \u5c06\u672c\u8f6e\u6240\u6709\u53c2\u6570\u7ec4\u5408\u7684 hash \u52a0\u5165 recent_combos\uff08\u6700\u8fd150\u4e2a\uff09\n"
    "- \u5c06\u672c\u8f6e\u6458\u8981\u52a0\u5165 history\n"
    "- \u4fdd\u7559 history \u6700\u8fd1 50 \u6761\n\n"
    "### \u91cd\u8981\uff1a\u66f4\u65b0 state.json \u65f6\u5fc5\u987b\u9a8c\u8bc1\u5199\u5165\u5b8c\u6574\u6027\n"
    "- \u5199\u5165 state.json \u540e\uff0c\u7acb\u5373\u8bfb\u53d6\u9a8c\u8bc1\uff1ahistory \u6761\u76ee\u662f\u5426\u5df2\u8ffd\u52a0\uff1fcurrent_iteration \u662f\u5426\u6b63\u786e\uff1f\n"
    "- \u5982\u679c history \u6761\u76ee\u672a\u88ab\u8ffd\u52a0\uff0c\u8bf4\u660e\u5199\u5165\u5931\u8d25\uff0c\u5fc5\u987b\u91cd\u8bd5\n\n"
    f"### \u5199\u5165 state.json\n"
    f"\u4f7f\u7528 Python json \u5e93\u76f4\u63a5\u5199\u5165 {STRATEGY_DIR}/state/state.json\n\n"
    f"### \u66f4\u65b0 knowledge_base.md\n"
    f"- \u8ffd\u52a0\u5230 {STRATEGY_DIR}/state/knowledge_base.md\n"
    "- \u683c\u5f0f\uff1aYYYY-MM-DD (iter N) - \u6d41\u6d3e\u540d + \u53c2\u6570 + \u6307\u6807 + SQL\u7247\u6bb5 + \u7ed3\u8bba + \u72b6\u6001\n\n"
    "### \u8f93\u51fa\u8981\u6c42\n"
    f"- \u5199\u5165 {STRATEGY_DIR}/logs/iter_{ITER}/analysis_T13_convergence.md\n"
    "- \u5305\u542b\u8de8\u6d41\u6d3e\u603b\u6210\u7ee9\u5355\u3001\u5404\u6d41\u6d3e\u6700\u4f73\u5bf9\u6bd4\u3001\u7a81\u7834\u53d1\u73b0\u6c47\u603b\u3001\u4e0b\u8f6e\u5efa\u8bae\n\n"
    "### \u6570\u636e\u89c4\u5219\n"
    "- \u65e5\u671f\u683c\u5f0f YYYYMMDD\n"
    "- \u4e3b\u677f\u8fc7\u6ee4\uff1ats_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'\n"
    "---\n"
    "\u26a0\ufe0f \u6b64\u4efb\u52a1\u5b8c\u6210\u540e\uff0c\u8fed\u4ee3 32 \u7684\u6570\u636e\u548c\u53d1\u73b0\u5c06\u6301\u4e45\u5316\u5230 state.json\u3002"
)

t13 = kanban_create(
    title=f"T13: \u4e3b\u63a7\u6536\u655b (iter {ITER})",
    assignee="analyst",
    body=t13_body,
    parents=ANALYST_IDS,
    max_runtime=10800
)

if not t13:
    log("FATAL: Failed to create T13, aborting")
    exit(1)

# ============================================================
# Phase 3: Wait for T13, then create T14
# ============================================================

log("Waiting for T13 to complete...")
if not wait_for_tasks([t13]):
    log("FATAL: T13 did not complete within timeout")
    exit(1)

log("T13 complete! Creating T14: \u62a5\u544a\u751f\u6210")

state = read_state()
best_metrics = state.get("best_metrics", {})

t14_body = (
    "## \u23f3 \u6642\u9593\u4e0a\u4e0b\u6587\uff08\u5f37\u5236\u9075\u5b88\uff09\n"
    f"- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n"
    f"- \u672c\u8f6e\u8fed\u4ee3\u7f16\u53f7\uff1a{ITER}\n\n"
    "---\n"
    f"## T14: \u62a5\u544a\u751f\u6210 (Iter {ITER})\n\n"
    "### \u4efb\u52a1\n"
    "1. \u8bfb\u53d6 T13 \u6536\u655b\u7ed3\u679c\n"
    f"2. \u6587\u4ef6\uff1a{STRATEGY_DIR}/logs/iter_{ITER}/analysis_T13_convergence.md\n"
    f"3. \u8bfb\u53d6 state.json: {STRATEGY_DIR}/state/state.json\n"
    f"4. \u8bfb\u53d6 knowledge_base: {STRATEGY_DIR}/state/knowledge_base.md\n\n"
    "### \u62a5\u544a\u5185\u5bb9\n"
    "- \u8fed\u4ee3\u7f16\u53f7\u548c\u65f6\u95f4\n"
    "- Top 5 \u7b56\u7565\u6392\u540d\uff08\u6309\u7efc\u5408\u8bc4\u5206\uff1aWR*R5*\u4fe1\u53f7\u6570\uff09\n"
    "- \u5404\u6d41\u6d3e\u8868\u73b0\u5bf9\u6bd4\u8868\u683c\n"
    "- \u5173\u952e\u53d1\u73b0\u603b\u7ed3\n"
    "- \u4e0e\u5168\u5c40\u7eaa\u5f55\u5bf9\u6bd4\n"
    "- \u4e0b\u8f6e\u5efa\u8bae\uff08\u6700\u591a 8 \u6761\uff09\n"
    "- \u75b2\u52b3\u72b6\u6001\u63d0\u9192\n\n"
    "### \u683c\u5f0f\u8981\u6c42\n"
    f"- \u4fdd\u5b58\u5230 {STRATEGY_DIR}/reports/mining-all167-iter{ITER}-{datetime.now().strftime('%Y%m%d-%H%M')}.md\n"
    "- Markdown \u683c\u5f0f\uff0c\u6e05\u6670\u6613\u8bfb\n"
    "- \u5fc5\u987b\u4ece T13 \u6536\u655b\u62a5\u544a\u4e2d\u8bfb\u53d6\u51c6\u786e\u7684\u6570\u636e\uff0c\u4e0d\u5f97\u81ea\u884c\u63a8\u6d4b\n"
    "- \u80a1\u7968\u4ee3\u7801\u5fc5\u987b\u540c\u65f6\u5305\u542b\u4ee3\u7801\u548c\u540d\u79f0\uff08\u5982 600984.SH \u5efa\u8bbe\u673a\u68b0\uff09\n\n"
    "### \u62a5\u544a\u4e2d\u7684\u65e5\u671f\u5fc5\u987b\u9075\u5b88\u4ee5\u4e0b\u89c4\u5219\n"
    "- \u62a5\u544a\u5f00\u5934\u7684 \u57fa\u51c6\u65e5\u671f \u548c \u4e0b\u4e00\u4ea4\u6613\u65e5 \u5fc5\u987b\u4ece T1 data check \u6587\u4ef6\u8bfb\u53d6\n"
    "- \u7981\u6b62\u4f7f\u7528'\u5468\u4e00/\u5468\u4e94'\u7b49\u63a8\u6d4b\u8bcd\n"
    "- \u5982\u65e0 T1 data check \u6587\u4ef6\uff0c\u4f7f\u7528\u7cfb\u7edf\u6267\u884c\u65e5\u671f\n"
)

t14 = kanban_create(
    title=f"T14: \u62a5\u544a\u751f\u6210 (iter {ITER})",
    assignee="writer",
    body=t14_body,
    parents=[t13],
    max_runtime=1200
)

if not t14:
    log("FATAL: Failed to create T14")
    exit(1)

log(f"=== Iter{ITER} pipeline fully deployed ===")
log(f"Task graph: T1->[T2..T12]->T13->T14")
log(f"T1={T1}")
analyst_ids_str = ", ".join(ANALYST_IDS)
log(f"Analysts ({len(ANALYST_IDS)}): [{analyst_ids_str}]")
log(f"T13={t13}")
log(f"T14={t14}")
log("Poller exiting - dispatcher handles the rest")
log(f"=== Iter{ITER} Poller END ===")
