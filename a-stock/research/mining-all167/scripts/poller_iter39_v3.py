#!/usr/bin/env python3
"""
Pipeline orchestrator for iter 39 — monitors T13->T14 completion and updates state.json.
"""
import sqlite3, time, json, os, sys, subprocess
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
STATE_PATH = STRATEGY_DIR + "/state/state.json"
LOG_DIR = STRATEGY_DIR + "/logs/iter_39"

T13_ID = "t_2d6e27ee"
T14_ID = "t_33229960"
ITER = 39

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_DIR + "/poller_v3.log", "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}")

def wait_for_task(tid, timeout=14400):
    """Wait for a kanban task to reach 'done' status."""
    start = time.time()
    while time.time() - start < timeout:
        conn = sqlite3.connect(DB)
        status = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
        conn.close()
        if status is None:
            log(f"Task {tid} not found in DB!")
            return False
        if status[0] == "done":
            log(f"Task {tid} is DONE")
            return True
        elapsed = int(time.time() - start)
        log(f"Waiting for {tid}: status={status[0]}, elapsed={elapsed}s")
        time.sleep(60)
    log(f"Task {tid} TIMEOUT after {timeout}s")
    return False

def read_file_safe(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception as e:
        log(f"Error reading {path}: {e}")
        return None

log(f"=== Pipeline orchestrator for iter {ITER} v3 started ===")
log(f"T13={T13_ID}, T14={T14_ID}")

# Phase 1: Wait for T13 to complete
log("Phase 1: Waiting for T13 (convergence)...")
t13_ok = wait_for_task(T13_ID, timeout=14400)
if not t13_ok:
    log("T13 FAILED or TIMEOUT — exiting")
    sys.exit(1)

# Phase 2: Read T13 output
log("Phase 2: Reading T13 convergence report...")
t13_report = read_file_safe(LOG_DIR + "/T13_主控收敛.md")
t13_state = read_file_safe(LOG_DIR + "/T13_state_update.json")

if t13_state:
    try:
        state_update = json.loads(t13_state)
        log("T13 state_update.json loaded successfully")
        beat_best = state_update.get("beat_best_metrics", False)
        beat_global = state_update.get("beat_global_record", False)
        fatigue_inc = state_update.get("fatigue_increment", False)
        best_combo = state_update.get("best_combo", {})
        new_factors = state_update.get("new_factors", [])
        closed_dirs = state_update.get("closed_directions", [])
        log(f"beat_best_metrics={beat_best}, beat_global={beat_global}, fatigue_inc={fatigue_inc}")
    except json.JSONDecodeError as e:
        log(f"Failed to parse T13_state_update.json: {e}")
        state_update = None
else:
    log("T13_state_update.json not found — will NOT update state.json")
    state_update = None

# Phase 3: Wait for T14 (report) to complete  
log("Phase 3: Waiting for T14 (report)...")
t14_ok = wait_for_task(T14_ID, timeout=3600)
if not t14_ok:
    log("T14 FAILED or TIMEOUT — exiting")
    sys.exit(1)

# Phase 4: Update state.json
log("Phase 4: Updating state.json...")
if state_update:
    with open(STATE_PATH) as f:
        state = json.load(f)
    
    # Update current_iteration
    state["current_iteration"] = ITER
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Update best_metrics if beaten
    if beat_best and best_combo.get("win_rate_5d"):
        state["best_metrics"] = {
            "ret_5d": best_combo.get("ret_5d"),
            "win_rate_5d": best_combo.get("win_rate_5d"),
            "ret_10d": best_combo.get("ret_10d"),
            "ret_20d": best_combo.get("ret_20d"),
            "signal_count": best_combo.get("signal_count"),
            "sharpe_5d": best_combo.get("sharpe_5d"),
            "strategy_desc": best_combo.get("strategy_desc", ""),
            "params": best_combo.get("params", {}),
            "discovered_at": datetime.now().strftime("%Y-%m-%d")
        }
        state["fatigue_count"] = 0
        log("New best_metrics recorded! fatigue_count reset to 0")
    elif fatigue_inc:
        state["fatigue_count"] = state.get("fatigue_count", 0) + 1
        log(f"fatigue_count incremented to {state['fatigue_count']}")
    else:
        log("fatigue_count unchanged")
    
    # Update global record if beaten
    if beat_global and best_combo.get("win_rate_5d"):
        state["best_metrics_global_record"] = {
            "ret_5d": best_combo.get("ret_5d"),
            "win_rate_5d": best_combo.get("win_rate_5d"),
            "signal_count": best_combo.get("signal_count"),
            "strategy_desc": best_combo.get("strategy_desc", ""),
            "params": best_combo.get("params", {}),
            "discovered_at": datetime.now().strftime("%Y-%m-%d")
        }
        log("New global record set!")
    
    # Add history entry
    history_entry = {
        "iteration": ITER,
        "ret_5d": best_combo.get("ret_5d") if best_combo else None,
        "win_5d": best_combo.get("win_rate_5d") if best_combo else None,
        "signal_count": best_combo.get("signal_count") if best_combo else None,
        "sharpe_5d": best_combo.get("sharpe_5d"),
        "analyst": "T13_主控收敛",
        "params": best_combo.get("strategy_desc", "No best combo found") if best_combo else "No best combo found",
        "note": "Completed via background poller v3. fatigue_count: " + str(state["fatigue_count"])
    }
    state["history"].insert(0, history_entry)
    
    # Keep history at 12 entries
    if len(state["history"]) > 12:
        state["history"] = state["history"][:12]
    
    # Update recent_combos if new combos from this iteration
    if best_combo and best_combo.get("strategy_desc"):
        combo_entry = f"iter{ITER}_" + best_combo.get("strategy_desc", "")
        if combo_entry not in state.get("recent_combos", []):
            combos = state.get("recent_combos", [])
            combos.insert(0, combo_entry)
            if len(combos) > 50:
                combos = combos[:50]
            state["recent_combos"] = combos
    
    # Write updated state
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    log("state.json updated successfully!")
    
    # Update knowledge_base.md if new factors
    if new_factors:
        kb_path = STRATEGY_DIR + "/state/knowledge_base.md"
        kb_entry = "\n\n## " + datetime.now().strftime("%Y-%m-%d") + " (iter " + str(ITER) + ")"
        for factor in new_factors:
            kb_entry += "\n- " + str(factor)
        with open(kb_path, "a") as f:
            f.write(kb_entry)
        log("knowledge_base.md updated with new factors")

log("=== Pipeline orchestator for iter 39 completed! ===")
