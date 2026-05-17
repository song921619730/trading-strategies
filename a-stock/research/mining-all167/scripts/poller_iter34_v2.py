#!/usr/bin/env python3
import sqlite3, time, json, subprocess, os, re, sys
from datetime import datetime

# Injected variables
VARS = {"T13_ID": "t_39729d48", "T14_ID": "t_1d3ce224", "ITER": 34, "STRATEGY_DIR": "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167", "DB": "/home/gjtmux/.hermes/profiles/reze/kanban.db", "TS": "2026-05-14 18:40", "BEST_WR": 87.81, "BEST_R5": 38.81, "FATIGUE_COUNT": 1}

DB = VARS["DB"]
STRATEGY_DIR = VARS["STRATEGY_DIR"]
T13_ID = VARS["T13_ID"]
T14_ID = VARS["T14_ID"]
ITER = VARS["ITER"]
TS = VARS["TS"]
LOGS_DIR = f"{STRATEGY_DIR}/logs"
POLLER_LOG = f"{LOGS_DIR}/poller_iter{ITER}_v2.log"

def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(POLLER_LOG, "a") as f:
        f.write(line + "\n")

def get_task_status(tid):
    conn = sqlite3.connect(DB)
    try:
        r = conn.execute("SELECT status, spawn_failures FROM tasks WHERE id=?", (tid,)).fetchone()
        return r[0] if r else "not_found"
    finally:
        conn.close()

def wait_for_task(tid, timeout=14400, label="task"):
    start = time.time()
    while True:
        elapsed = int(time.time() - start)
        status = get_task_status(tid)
        log(f"  {label} [{tid[:12]}]: {status} (elapsed={elapsed}s)")
        
        if status == "done":
            log(f"  {label} DONE!")
            return True
        if elapsed > timeout:
            log(f"  {label} TIMEOUT after {timeout}s!")
            return False
        
        time.sleep(30)

def update_state_json():
    state_path = f"{STRATEGY_DIR}/state/state.json"
    with open(state_path) as f:
        state = json.load(f)
    
    best_wr = state["best_metrics"]["win_rate_5d"]
    best_r5 = state["best_metrics"]["ret_5d"]
    fatigue = state["fatigue_count"]
    
    # Try to read convergence report for metrics
    conv_path = f"{LOGS_DIR}/iter_{ITER}/convergence.md"
    metrics = {"ret_5d": None, "win_rate_5d": None, "signal_count": None, "sharpe_5d": None,
               "strategy_desc": "Iter34汇总", "params": {}}
    
    if os.path.exists(conv_path):
        with open(conv_path) as f:
            content = f.read()
        
        # Try to extract best metrics from the report
        wr_match = re.search(r'WR[OOS_]*\s*[:=]\s*([\d.]+)%', content)
        if wr_match:
            metrics["win_rate_5d"] = float(wr_match.group(1))
        
        r5_match = re.search(r'R5[OOS_]*\s*[:=]\s*([\d.]+)%', content)
        if r5_match:
            metrics["ret_5d"] = float(r5_match.group(1))
        
        n_match = re.search(r'N[OOS_]*\s*[:=]\s*(\d+)', content)
        if n_match:
            metrics["signal_count"] = int(n_match.group(1))
    
    new_record = False
    fatigue_changed = False
    
    wr = metrics["win_rate_5d"]
    r5 = metrics["ret_5d"]
    n = metrics["signal_count"]
    
    # Check if record was broken
    record_broken = False
    if wr and r5 and n:
        if (wr > best_wr or r5 > best_r5) and n >= 200:
            record_broken = True
    
    if record_broken:
        fatigue = 0
        fatigue_changed = True
        state["best_metrics"] = {
            "ret_5d": r5,
            "win_rate_5d": wr,
            "ret_10d": None,
            "ret_20d": None,
            "signal_count": n,
            "sharpe_5d": metrics["sharpe_5d"],
            "strategy_desc": metrics["strategy_desc"],
            "params": metrics["params"],
            "discovered_at": "2026-05-14"
        }
        new_record = True
        log(f"  NEW RECORD! WR={wr}%, R5={r5}%, N={n}")
    else:
        fatigue += 1
        fatigue_changed = True
        log(f"  No record broken. fatigue_count: {fatigue}")
    
    # Update state.json
    state["current_iteration"] = ITER
    state["fatigue_count"] = fatigue
    
    # Add history entry
    from copy import deepcopy
    history_entry = {
        "iteration": ITER,
        "ret_5d": r5,
        "win_5d": wr,
        "signal_count": n,
        "sharpe_5d": metrics["sharpe_5d"],
        "analyst": "T13_主控收敛 (poller v2)",
        "params": metrics["strategy_desc"],
        "note": f"✅ Iter{ITER} completed via background poller v2."
    }
    if new_record:
        history_entry["note"] += f" NEW RECORD! WR={wr}%, R5={r5}%"
    else:
        history_entry["note"] += f" No new record. fatigue_count: {fatigue}"
    
    if "history" not in state:
        state["history"] = []
    state["history"].insert(0, history_entry)
    
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    
    log(f"  state.json updated. current_iteration={ITER}, fatigue={fatigue}")
    return new_record

def main():
    log(f"=== Poller Iteration {ITER} v2 started ===")
    
    # Phase 1: Wait for T13 convergence
    log("Phase 1: Waiting for T13 convergence...")
    if not wait_for_task(T13_ID, timeout=14400, label="T13 convergence"):
        log("T13 TIMEOUT! Exiting.")
        sys.exit(1)
    
    # Phase 2: Wait for T14 report
    log("Phase 2: Waiting for T14 report...")
    if not wait_for_task(T14_ID, timeout=3600, label="T14 report"):
        log("T14 TIMEOUT! Exiting.")
        sys.exit(1)
    
    # Phase 3: Update state.json
    log("Phase 3: Updating state.json...")
    new_record = update_state_json()
    
    log(f"=== Iter {ITER} pipeline COMPLETE! ===")
    if new_record:
        log("NEW RECORD ACHIEVED!")

if __name__ == "__main__":
    main()
