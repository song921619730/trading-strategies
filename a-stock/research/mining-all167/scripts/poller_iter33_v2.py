#!/usr/bin/env python3
"""Background poller for iter 33 — waits for T13/T14, then updates state.json"""
import sqlite3, time, subprocess, json, os, sys
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER = 33
T13 = "t_c5782744"
T14 = "t_4e05d933"
ITSDIR = f"{STRATEGY_DIR}/logs/iter_{ITER}"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(f"{STRATEGY_DIR}/logs/poller.log", "a") as f:
        f.write(line + "\n")

def wait_for_task(tid, label, poll=60, timeout=43200):
    start = time.time()
    while time.time() - start < timeout:
        conn = sqlite3.connect(DB)
        row = conn.execute("SELECT id, status FROM tasks WHERE id=?", (tid,)).fetchone()
        conn.close()
        if row and row[1] == "done":
            log(f"  {label} DONE!")
            return True
        elapsed = int(time.time() - start)
        status = row[1] if row else "unknown"
        log(f"  {label}: {status} (elapsed={elapsed}s)")
        time.sleep(poll)
    log(f"  TIMEOUT waiting for {label}")
    return False

def update_state():
    with open(f"{STRATEGY_DIR}/state/state.json") as f:
        s = json.load(f)
    
    # Read convergence report to find best metrics
    conv_path = f"{ITSDIR}/13-convergence.md"
    best_new_wr = None
    best_new_r5 = None
    best_new_n = None
    best_sharpe = None
    best_desc = "Iter33汇总"
    
    if os.path.exists(conv_path):
        with open(conv_path) as f:
            conv = f.read()
        
        # Extract best metrics from convergence report
        import re
        wr_match = re.search(r'WR[=:]\s*([\d.]+)%', conv)
        r5_match = re.search(r'R5[=:]\s*([\d.]+)%', conv)
        n_match = re.search(r'N[=:]\s*(\d+)', conv)
        sharpe_match = re.search(r'Sharpe[=:]\s*([\d.]+)', conv)
        
        if wr_match:
            best_new_wr = float(wr_match.group(1))
        if r5_match:
            best_new_r5 = float(r5_match.group(1))
        if n_match:
            best_new_n = int(n_match.group(1))
        if sharpe_match:
            best_sharpe = float(sharpe_match.group(1))
    else:
        log(f"WARNING: Convergence report not found at {conv_path}")
    
    # Determine if new record
    old_best_wr = s['best_metrics']['win_rate_5d']
    old_best_r5 = s['best_metrics']['ret_5d']
    new_record = False
    
    if best_new_wr and best_new_r5 and best_new_n:
        if (best_new_wr > old_best_wr or best_new_r5 > old_best_r5) and best_new_n >= 200:
            new_record = True
            log(f"  NEW RECORD! WR={best_new_wr}%, R5={best_new_r5}%, N={best_new_n}")
    
    if new_record:
        s['fatigue_count'] = 0
        s['best_metrics'] = {
            'ret_5d': best_new_r5,
            'win_rate_5d': best_new_wr,
            'ret_10d': None,
            'ret_20d': None,
            'signal_count': best_new_n,
            'sharpe_5d': best_sharpe,
            'strategy_desc': best_desc,
            'params': {},
            'discovered_at': datetime.now().strftime("%Y-%m-%d")
        }
        s['best_metrics_global_record']['ret_5d'] = best_new_r5
        s['best_metrics_global_record']['win_rate_5d'] = best_new_wr
        s['best_metrics_global_record']['signal_count'] = best_new_n
        s['best_metrics_wr_record']['win_rate_5d'] = best_new_wr
        log("  fatigue_count reset to 0!")
    else:
        s['fatigue_count'] = s.get('fatigue_count', 0) + 1
        log(f"  No new record. Fatigue: {s['fatigue_count']}")
    
    # Add history entry
    history_entry = {
        "iteration": ITER,
        "ret_5d": best_new_r5,
        "win_5d": best_new_wr,
        "signal_count": best_new_n,
        "sharpe_5d": best_sharpe,
        "analyst": "T13_主控收敛 (poller)",
        "params": best_desc,
        "note": f"Finish iter {ITER} via background poller"
    }
    s.setdefault('history', []).insert(0, history_entry)
    s['current_iteration'] = ITER
    
    with open(f"{STRATEGY_DIR}/state/state.json", "w") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    log(f"  state.json updated. current_iteration={ITER}, fatigue={s['fatigue_count']}")

log(f"=== Iter {ITER} poller started ===")

# Phase 1: Wait for T13 convergence
log("Phase 1: Waiting for T13 convergence...")
if not wait_for_task(T13, "T13 convergence"):
    log("T13 timed out — exiting")
    sys.exit(1)

# Phase 2: Wait for T14 report
log("Phase 2: Waiting for T14 report...")
if not wait_for_task(T14, "T14 report"):
    log("T14 timed out — exiting")
    sys.exit(1)

# Phase 3: Update state.json
log("Phase 3: Updating state.json...")
update_state()

log(f"=== Iter {ITER} pipeline COMPLETE! ===")
