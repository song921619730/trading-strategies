#!/usr/bin/env python3
"""Pipeline orchestrator for iter 39 - waits for T2-T12, creates T13/T14."""
import sqlite3, time, subprocess, json, sys, os
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER = 39
OUT_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_39"
ANALYST_IDS = {"2": "t_d5dc756b", "3": "t_c7e884ef", "4": "t_42920599", "5": "t_43c70587", "6": "t_60a03369", "7": "t_c0322497", "8": "t_c5fac0eb", "9": "t_31dd6004", "10": "t_7bb2b38d", "11": "t_f15951df", "12": "t_0c779cfe"}
ALL_ANALYST_IDS = ["t_d5dc756b", "t_c7e884ef", "t_42920599", "t_43c70587", "t_60a03369", "t_c0322497", "t_c5fac0eb", "t_31dd6004", "t_7bb2b38d", "t_f15951df", "t_0c779cfe"]
LOG_FILE = os.path.join(OUT_DIR, "poller_iter39.log")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}")

def kanban_create(title, assignee, body, parents=None, max_runtime=600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR creating {title[:40]}: {result.stderr[:200]}")
        return None
    try:
        return json.loads(result.stdout)["id"]
    except:
        log(f"JSON parse error: {result.stdout[:200]}")
        return None

def wait_for_tasks(tids, timeout=43200, poll_interval=120):
    """Wait for all tasks to reach 'done' status."""
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            log(f"TIMEOUT after {int(elapsed)}s waiting for {len(tids)} tasks")
            return False
        try:
            conn = sqlite3.connect(DB)
            done = 0
            for tid in tids:
                row = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
                if row and row[0] == "done":
                    done += 1
            conn.close()
            log(f"Progress: {done}/{len(tids)} done | elapsed={int(elapsed)}s")
            if done == len(tids):
                return True
        except Exception as e:
            log(f"DB error: {e}")
        time.sleep(poll_interval)

def update_state_json(iter_num, best_combo, best_wr, best_r5, best_n, fatigue_comment):
    """Update state.json with iteration results."""
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state", "state.json")
    try:
        with open(state_path) as f:
            state = json.load(f)
    except:
        state = {"current_iteration": 0, "fatigue_count": 0, "history": [], "recent_combos": []}
    state["current_iteration"] = iter_num
    current_best_wr = state.get("best_metrics", {}).get("win_rate_5d", 0)
    if best_wr > current_best_wr and best_n >= 200:
        state["best_metrics"] = {
            "ret_5d": best_r5,
            "win_rate_5d": best_wr,
            "ret_10d": None,
            "ret_20d": None,
            "signal_count": best_n,
            "sharpe_5d": None,
            "strategy_desc": str(best_combo)[:80],
            "params": {},
            "discovered_at": datetime.now().strftime("%Y-%m-%d")
        }
        state["fatigue_count"] = 0
        log("NEW BEST! WR=" + str(best_wr) + "% - fatigue reset to 0")
    else:
        state["fatigue_count"] = state.get("fatigue_count", 0) + 1
        log("No new record. fatigue -> " + str(state["fatigue_count"]))
    history_entry = {
        "iteration": iter_num,
        "ret_5d": best_r5,
        "win_5d": best_wr,
        "signal_count": best_n,
        "sharpe_5d": None,
        "analyst": "T13_convergence",
        "params": str(best_combo)[:80],
        "note": str(fatigue_comment)[:200]
    }
    state["history"].insert(0, history_entry)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    log("state.json updated")

def main():
    log(f"=== Pipeline orchestrator for iter 39 started ===")
    log(f"Waiting for " + str(len(ALL_ANALYST_IDS)) + " analyst tasks (T2-T12)...")

    # Phase 1: Wait for T2-T12
    success = wait_for_tasks(ALL_ANALYST_IDS, timeout=43200, poll_interval=120)
    if not success:
        log("TIMEOUT - exiting")
        sys.exit(1)

    log("All analyst tasks done! Creating T13...")

    # Phase 2: Create T13 - convergence
    now = datetime.now()
    ts_now = now.strftime("%Y-%m-%d %H:%M")
    date_str = now.strftime("%Y%m%d")

    t13_body = (
        f"## T13: \u4e3b\u63a7\u6536\u655b (iter 39)\n"
        f"- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a{ts_now} UTC+8\n"
        f"- \u8fed\u4ee3\u7f16\u53f7\uff1aiter 39\n"
        "\n"
        "\u7efc\u5408\u8bc4\u4f30 T2~T12 \u5171 11 \u4efd\u5206\u6790\u62a5\u544a\uff0c\n"
        "\u8f93\u51fa\u6700\u4f73\u7ec4\u5408\u6392\u540d\u3001\u6d41\u6d3e\u8d28\u91cf\u6392\u5e8f\u3001\n"
        "\u4e0e best_metrics \u5bf9\u6bd4\u3001\u8fc7\u62df\u5408\u8bc4\u4f30\u3002\n"
        "\u8fd0\u884c\u540e\u66f4\u65b0 state.json\n"
        "\n"
        "\u6570\u636e\u89c4\u5219\uff1a\n"
        "- \u4e3b\u677f\u8fc7\u6ee4\uff1ats_code NOT LIKE '30%' AND NOT LIKE '688%'\n"
        "- net_mf \u4e0d\u5b58\u5728\uff0c\u7528 net_mf_amount\n"
        "\n"
        f"\u8f93\u51fa\u5230\uff1a{OUT_DIR}/T13_convergence.md\n"
    )

    t13_id = kanban_create(
        "T13: \u4e3b\u63a7\u6536\u655b (iter 39)",
        "analyst",
        t13_body,
        parents=ALL_ANALYST_IDS,
        max_runtime=7200
    )

    if not t13_id:
        log("Failed to create T13 - exiting")
        sys.exit(1)
    log("T13 created: " + str(t13_id))

    # Phase 3: Wait for T13
    log("Waiting for T13 to complete...")
    success = wait_for_tasks([t13_id], timeout=14400, poll_interval=120)
    if not success:
        log("TIMEOUT waiting for T13")
        sys.exit(1)

    log("T13 done! Creating T14...")

    # Phase 4: Create T14 - report
    t14_body = (
        f"## T14: \u62a5\u544a\u751f\u6210 (iter 39)\n"
        f"- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a{ts_now} UTC+8\n"
        "\n"
        "\u8bfb\u53d6 T13 \u8f93\u51fa\u6587\u4ef6\u751f\u6210\u683c\u5f0f\u5316\u62a5\u544a\u3002\n"
        "\u5fc5\u987b\u5305\u542b\uff1a\n"
        "1. \u6570\u636e\u57fa\u51c6\u65e5\u671f\n"
        "2. \u672c\u8f6e\u6700\u4f73\u7ec4\u5408 (WR/R5/N)\n"
        "3. \u4e0e best_metrics \u5bf9\u6bd4\n"
        "4. \u65b0\u53d1\u73b0\u548c\u5173\u95ed\u65b9\u5411\n"
        "5. \u4e0b\u4e00\u8f6e\u5efa\u8bae\n"
        "\n"
        f"\u8f93\u51fa\u5230\uff1a{STRATEGY_DIR}/reports/mining-iter{date_str}.md\n"
    )

    t14_id = kanban_create(
        "T14: \u62a5\u544a\u751f\u6210 (iter 39)",
        "writer",
        t14_body,
        parents=[t13_id],
        max_runtime=1200
    )

    if not t14_id:
        log("Failed to create T14")
        sys.exit(1)
    log("T14 created: " + str(t14_id))

    # Phase 5: Wait for T14
    log("Waiting for T14...")
    wait_for_tasks([t14_id], timeout=3600, poll_interval=60)

    log("=== Pipeline iter 39 complete ===")

if __name__ == "__main__":
    main()
