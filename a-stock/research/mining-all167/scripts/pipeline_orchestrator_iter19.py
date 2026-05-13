#!/usr/bin/env python3
"""Background poller for Iter19 mining pipeline.
Wait for T2-T8 analysts to complete, then sequentially manage T9-T11.

=== PID Safety ===
Checks for existing instances before running.

=== Usage ===
    python3 scripts/pipeline_orchestrator_iter19.py
"""

import os, sys, json, time, subprocess, sqlite3, datetime
from pathlib import Path

# ═══ Configuration ═══
ITER = 19
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
NOW = "2026-05-13 08:12"

# ── Task IDs ──
T1_ID = "t_a11e37ac"
ANALYST_IDS = [
    "t_f601d61e",  # T2: 动量趋势
    "t_3e48473b",  # T3: 反转低吸
    "t_2bbf689e",  # T4: 资金主力
    "t_f30a78e9",  # T5: 基本面估值
    "t_9f58ee06",  # T6: 板块轮动
    "t_e2eb92be",  # T7: 跨市场联动
    "t_f3aa9bfc",  # T8: 量价形态
]
T9_ID = "t_7719abe3"
T10_ID = "t_f094934d"
T11_ID = "t_950537e7"

ANALYST_NAMES = {
    "t_f601d61e": "T2_动量趋势",
    "t_3e48473b": "T3_反转低吸",
    "t_2bbf689e": "T4_资金主力",
    "t_f30a78e9": "T5_基本面估值",
    "t_9f58ee06": "T6_板块轮动",
    "t_e2eb92be": "T7_跨市场联动",
    "t_f3aa9bfc": "T8_量价形态",
}

SYSTEM_TIME = NOW

def ensure_single_instance():
    script_name = os.path.basename(__file__)
    count = 0
    try:
        result = subprocess.run(
            ["pgrep", "-f", script_name],
            capture_output=True, text=True, timeout=5
        )
        count = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
    except:
        pass
    if count > 1:
        log(f"WARN: {count} instances found (including this one). Continuing anyway.")
    log(f"PID check: {count} instance(s) of {script_name}")

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(f"{STRATEGY_DIR}/logs/poller_iter{ITER}.log", "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}")

def check_task_status(task_id):
    conn = sqlite3.connect(DB)
    try:
        row = conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()

def check_spawn_failures(task_id):
    conn = sqlite3.connect(DB)
    try:
        row = conn.execute("SELECT spawn_failures, last_spawn_error FROM tasks WHERE id=?", (task_id,)).fetchone()
        return row if row else (None, None)
    finally:
        conn.close()

def wait_for_tasks(tids, timeout=14400, poll_interval=60):
    start = time.time()
    while time.time() - start < timeout:
        conn = sqlite3.connect(DB)
        try:
            statuses = {}
            for tid in tids:
                row = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
                statuses[tid] = row[0] if row else "unknown"
        finally:
            conn.close()

        done = all(s == 'done' for s in statuses.values())
        if done:
            log(f"All {len(tids)} tasks done: {statuses}")
            return True

        for tid in tids:
            s = statuses[tid]
            fails, error = check_spawn_failures(tid)
            if s == 'done':
                continue
            if s == 'running':
                continue
            if fails and fails > 0:
                log(f"WARN: {tid} ({ANALYST_NAMES.get(tid, '?')}) has {fails} spawn failures: {error}")

        status_summary = "; ".join(f"{ANALYST_NAMES.get(tid, tid[:12])}={s}" for tid, s in statuses.items())
        elapsed = int(time.time() - start)
        log(f"Waiting... ({elapsed}s elapsed) {status_summary}")
        time.sleep(poll_interval)

    log(f"TIMEOUT: {timeout}s reached, tasks not all done")
    return False

def main():
    log(f"{'═' * 60}")
    log(f"Iter{ITER} Pipeline Orchestrator starting")
    log(f"Strategy dir: {STRATEGY_DIR}")
    log(f"Analyst IDs: {ANALYST_IDS}")

    ensure_single_instance()

    os.makedirs(f"{STRATEGY_DIR}/logs/iter_{ITER}", exist_ok=True)

    # ── Phase 1: Wait for T2-T8 analysts ──
    log(f"\n{'─'*60}")
    log(f"Phase 1: Waiting for T2-T8 analysts ({len(ANALYST_IDS)} tasks)...")
    t1_status = check_task_status(T1_ID)
    log(f"T1 status: {t1_status}")

    if not wait_for_tasks(ANALYST_IDS, timeout=14400, poll_interval=60):
        log("ERROR: T2-T8 did not complete within 4 hours. Exiting.")
        sys.exit(1)
    log("Phase 1 complete! All T2-T8 analysts done.")

    # ── Phase 2: Wait for T9 ──
    log(f"\n{'─'*60}")
    log(f"Phase 2: Waiting for T9 ({T9_ID})...")
    # T9 was already created; if it completed early, this returns immediately
    if not wait_for_tasks([T9_ID], timeout=10800, poll_interval=60):
        log("ERROR: T9 did not complete within 3 hours. Exiting.")
        sys.exit(1)
    log("Phase 2 complete! T9 done.")

    # ── Phase 3: Wait for T10 ──
    log(f"\n{'─'*60}")
    log(f"Phase 3: Waiting for T10 ({T10_ID})...")
    if not wait_for_tasks([T10_ID], timeout=7200, poll_interval=60):
        log("WARN: T10 did not complete within 2 hours.")
    else:
        log("Phase 3 complete! T10 done.")

    # ── Phase 4: Wait for T11 ──
    log(f"\n{'─'*60}")
    log(f"Phase 4: Waiting for T11 ({T11_ID})...")
    if not wait_for_tasks([T11_ID], timeout=1800, poll_interval=30):
        log("WARN: T11 did not complete within 30 minutes.")
    else:
        log("Phase 4 complete! T11 done.")

    # ── Final Summary ──
    log(f"\n{'═'*60}")
    log(f"Iter{ITER} Pipeline complete!")
    log(f"Task IDs:")
    log(f"  T1:  {T1_ID}")
    for tid in ANALYST_IDS:
        log(f"  {ANALYST_NAMES[tid]}: {tid}")
    log(f"  T9:  {T9_ID}")
    log(f"  T10: {T10_ID}")
    log(f"  T11: {T11_ID}")
    log(f"Logs: {STRATEGY_DIR}/logs/iter_{ITER}/")
    log(f"Report: {STRATEGY_DIR}/reports/")
    log(f"{'═'*60}")

if __name__ == "__main__":
    main()
