#!/usr/bin/env python3
"""
Poll T2-T8 task completion, then create T9, T10, T11 sequentially.
This script runs inside the orchestrator's session.
"""
import subprocess, json, time, os, sys, datetime

ITER = 9
WORKDIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
SYSTEM_TIME = "2026-05-12 09:59 UTC+8"
BEST_METRICS = "R5=25.76%(T9-X17 锤子线×SPX上涨), WR=74.9%, Sharpe=0.68(偏低), 稳健最佳=T7-C6(R5=4.54%,WR=78.79%,Sharpe=4.587)"
FATIGUE_COUNT = 2

# Task IDs from the first phase
TASK_IDS_FILE = f"{WORKDIR}/state/task_ids_iter{ITER}.json"
with open(TASK_IDS_FILE) as f:
    data = json.load(f)

tids = data["task_ids"]
analyst_ids = [tids[f"T{n}"] for n in range(2, 9)]  # T2-T8
print(f"Polling for T2-T8 completion...")
print(f"Task IDs: {analyst_ids}")

DB_PATH = "/home/gjtmux/.hermes/profiles/reze/kanban.db"

# ============================================================
# Phase 1: Poll T2-T8 until all done
# ============================================================
def poll_tasks(task_ids, poll_interval=60, max_wait=7200):
    """Poll kanban.db until all tasks are done."""
    import sqlite3
    start = time.time()
    while time.time() - start < max_wait:
        conn = sqlite3.connect(DB_PATH)
        statuses = {}
        for tid in task_ids:
            row = conn.execute('SELECT status, spawn_failures FROM tasks WHERE id=?', (tid,)).fetchone()
            statuses[tid] = row if row else ("unknown", 0)
        conn.close()

        all_done = True
        for tid, (status, fails) in statuses.items():
            if status == "unknown":
                print(f"  {tid}: not found in DB")
                all_done = False
            elif status == "done":
                pass  # good
            elif status == "running":
                print(f"  {tid}: running")
                all_done = False
            elif fails and fails > 3:
                print(f"  {tid}: FAILED ({status}, {fails} spawn failures)")
                all_done = False
            else:
                print(f"  {tid}: {status} (fails={fails})")
                all_done = False

        if all_done:
            elapsed = time.time() - start
            print(f"\n✅ All {len(task_ids)} tasks done! Elapsed: {elapsed:.0f}s")
            return True

        elapsed = time.time() - start
        print(f"[{elapsed:.0f}s elapsed] Waiting {poll_interval}s...")
        time.sleep(poll_interval)

    print(f"\n❌ Timeout after {max_wait}s - not all tasks completed")
    return False

# Poll for T2-T8
print("\n" + "=" * 60)
print("POLLING T2-T8 (background polling started)")
print("=" * 60)

# Since we can't poll forever in a cron session, let's check current status
# and report back. The dispatcher will re-invoke us later.
def get_task_status(task_ids):
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    results = {}
    for tid in task_ids:
        row = conn.execute('SELECT id, title, status, spawn_failures, started_at FROM tasks WHERE id=?', (tid,)).fetchone()
        if row:
            results[tid] = {"status": row[2], "spawn_failures": row[3], "started_at": row[4], "title": row[1][:50]}
    conn.close()
    return results

status = get_task_status(analyst_ids)
all_analysts_done = all(v["status"] == "done" for v in status.values())
running_analysts = [k for k, v in status.items() if v["status"] == "running"]
pending_analysts = [k for k, v in status.items() if v["status"] in ("todo", "ready")]

print(f"\nT2-T8 Status:")
for tid, info in status.items():
    print(f"  {tid[:8]}... | {info['status']:8s} | {info['title']}")

if all_analysts_done:
    print("\n✅ All analysts done! Proceeding to create T9...")
    # Continue below to create T9
elif running_analysts:
    print(f"\n⏳ {len(running_analysts)} still running, {len(pending_analysts)} pending")
    print("Will check back later when woken up by dispatcher.")
    sys.exit(0)  # Exit gracefully - dispatcher will wake orchestrator again
else:
    print(f"\n⏳ {len(pending_analysts)} pending, no one running yet")
    print("Dispatcher hasn't started them yet. Will check back.")
    sys.exit(0)
