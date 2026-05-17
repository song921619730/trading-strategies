#!/usr/bin/env python3
"""
Background poller for Iteration 26 (mining-all167).
Waits for T2-T8 -> creates T9 -> waits -> T10 -> waits -> T11.

Spawning time: 2026-05-13 21:50 UTC+8

Phase timing expectations:
- T1 completes in seconds (data freshness check)
- T2-T8 run in parallel after T1 done (~30-90 min for ClickHouse queries)
  Set max_runtime=10800 for each
- T9 cross-validation (~30-60 min)
- T10 convergence (~15-30 min)
- T11 report (~5-10 min)

Total estimated wall time: ~2-3 hours
"""
import sqlite3, time, subprocess, json, sys, os

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER = 26

ANALYST_IDS = [
    "t_073b864d",  # T2 动量趋势
    "t_3c14685b",  # T3 反转低吸
    "t_6e2c7853",  # T4 资金主力
    "t_d46fe12c",  # T5 基本面估值
    "t_fed4aaf8",  # T6 板块轮动
    "t_809e1b66",  # T7 跨市场联动
    "t_048cf754",  # T8 量价形态
]


def log(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{t}] {msg}"
    print(line)
    with open(f"{STRATEGY}/logs/poller.log", "a") as f:
        f.write(line + "\n")


def wait_for(tids, label, poll_sec=120, timeout=14400):
    """Wait until all task IDs have status='done', with timeout."""
    log(f"Waiting for {label} ({len(tids)} tasks)...")
    elapsed = 0
    while elapsed < timeout:
        conn = sqlite3.connect(DB)
        statuses = {}
        for tid in tids:
            row = conn.execute(
                "SELECT id, status FROM tasks WHERE id=?", (tid,)
            ).fetchone()
            statuses[tid] = row[1] if row else "MISSING"
        conn.close()

        done = [t for t, s in statuses.items() if s == "done"]
        other = [(t, s) for t, s in statuses.items() if s != "done"]
        log(f"  {len(done)}/{len(tids)} done | pending: {other[:5]}")

        if len(done) == len(tids):
            log(f"  All {label} completed!")
            return True

        time.sleep(poll_sec)
        elapsed += poll_sec

    log(f"TIMEOUT after {timeout}s waiting for {label}")
    return False


def read_body(filepath):
    with open(filepath, "r") as f:
        return f.read()


def kanban_create(title, assignee, body, parents=None, max_runtime=3600):
    cmd = [
        "hermes", "kanban", "create", title,
        "--assignee", assignee,
        "--body", body,
        "--max-runtime", str(max_runtime),
        "--json",
    ]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR creating '{title}': {result.stderr[:200]}")
        return None
    try:
        data = json.loads(result.stdout)
        log(f"Created: {title} -> {data['id']}")
        return data["id"]
    except Exception as e:
        log(f"PARSE FAIL: {result.stdout[:200]} | err={e}")
        return None


def main():
    log(f"=== Poller Iteration {ITER} STARTED ===")
    log("Monitoring T2-T8 analysts (7 parallel tasks)...")

    # Phase 1: Wait for T2-T8
    if not wait_for(ANALYST_IDS, "T2-T8 analyst tasks", poll_sec=120, timeout=14400):
        log("T2-T8 TIMEOUT - exiting without creating T9")
        sys.exit(1)

    # Phase 2: Create T9 cross-validation
    log("Phase 2: Creating T9 cross-validation...")
    t9_body = read_body(f"{STRATEGY}/scripts/t9_body_iter{ITER}.md")
    t9_id = kanban_create(
        f"T9: 组合交叉验证 (Iter{ITER})",
        "analyst",
        t9_body,
        max_runtime=10800,
    )
    if not t9_id:
        log("FATAL: T9 creation failed")
        sys.exit(1)

    # Phase 3: Wait for T9
    if not wait_for([t9_id], "T9 cross-validation", poll_sec=120, timeout=14400):
        log("T9 TIMEOUT - exiting without creating T10")
        sys.exit(1)

    # Phase 4: Create T10 convergence
    log("Phase 4: Creating T10 convergence...")
    t10_body = read_body(f"{STRATEGY}/scripts/t10_body_iter{ITER}.md")
    t10_id = kanban_create(
        f"T10: 主控收敛 (Iter{ITER})",
        "analyst",
        t10_body,
        max_runtime=3600,
    )
    if not t10_id:
        log("FATAL: T10 creation failed")
        sys.exit(1)

    # Phase 5: Wait for T10
    if not wait_for([t10_id], "T10 convergence", poll_sec=60, timeout=7200):
        log("T10 TIMEOUT - exiting without creating T11")
        sys.exit(1)

    # Phase 6: Create T11 report
    log("Phase 6: Creating T11 report...")
    t11_body = read_body(f"{STRATEGY}/scripts/t11_body_iter{ITER}.md")
    t11_id = kanban_create(
        f"T11: 报告生成 (Iter{ITER})",
        "writer",
        t11_body,
        max_runtime=600,
    )
    if not t11_id:
        log("FATAL: T11 creation failed")

    log(f"=== Poller Iteration {ITER} COMPLETE ===")
    log(f"Pipeline complete: T9={t9_id}, T10={t10_id}, T11={t11_id}")


if __name__ == "__main__":
    main()
