#!/usr/bin/env python3
"""Background poller for Iteration 23 -- waits for T2-T8, then creates T9-T11."""
import sqlite3, time, subprocess, json, os, sys
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER = 23
T1_ID = "t_9d2fb32a"
ANALYST_IDS = {2: "t_20ee60b0", 3: "t_9b41bceb", 4: "t_756e3ee9", 5: "t_adebe10c", 6: "t_5f942a4e", 7: "t_da19b90a", 8: "t_782d100f"}

LOG_FILE = f"{STRATEGY_DIR}/logs/poller_iter{ITER}.log"
PIPELINE_STATE = f"{STRATEGY_DIR}/logs/poller_iter{ITER}_state.json"
TIME_STR = "2026-05-13 15:36 UTC+8"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def save_state(data):
    with open(PIPELINE_STATE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def kanban_create(title, assignee, body, parents=None, max_runtime=10800):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"kanban_create failed: {result.stderr[:500]}")
    return json.loads(result.stdout)["id"]

def wait_for_tasks(tids, timeout=14400, poll_interval=120, label=""):
    log(f"Waiting for {label} tasks: {tids}")
    elapsed = 0
    while elapsed < timeout:
        conn = sqlite3.connect(DB)
        statuses = []
        for t in tids:
            r = conn.execute("SELECT status FROM tasks WHERE id=?", (t,)).fetchone()
            statuses.append(r[0] if r else "unknown")
        conn.close()
        done_count = sum(1 for s in statuses if s == "done")
        log(f"  [{label}] {done_count}/{len(tids)} done - {statuses}")
        if all(s == "done" for s in statuses):
            log(f"  [{label}] ALL DONE!")
            return statuses
        time.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError(f"Timeout waiting for {label} after {timeout}s")

state = {"phase": "init", "tasks": {"t1": T1_ID, "t2_t8": ANALYST_IDS}}
save_state(state)

log("=" * 60)
log(f"Background Poller Started for Iteration {ITER}")
log(f"Strategy: {STRATEGY_DIR}")
log(f"T1: {T1_ID}")
log(f"Analysts: {ANALYST_IDS}")
log("=" * 60)

try:
    # Phase 1: Wait for T2-T8 analysts
    analyst_tids = list(ANALYST_IDS.values())
    wait_for_tasks(analyst_tids, timeout=14400, poll_interval=120, label="T2-T8 analysts")
    state["phase"] = "T2T8_done"
    save_state(state)

    # Phase 2: Create T9 Cross-validation
    log("\n--- Phase 2: Creating T9: Cross-validation ---")

    t9_body = (
        "## \U0001f4c5 \u65f6\u95f4\u4e0a\u4e0b\u6587\uff08\u5f3a\u5236\u9075\u5b88\uff09\n"
        f"- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a{TIME_STR}\n"
        f"- \u672c\u8f6e\u8fed\u4ee3\u7f16\u53f7\uff1a{ITER}\n"
        "\n"
        "## \u4efb\u52a1\uff1a\u7ec4\u5408\u4ea4\u53c9\u9a8c\u8bc1\n"
        "\n"
        "### \u524d\u7f6e\u6b65\u9aa4\n"
        f"1. \u8bfb\u53d6 T2-T8 \u6240\u6709\u8f93\u51fa\uff08{STRATEGY_DIR}/logs/iter_{ITER}/\uff09\n"
        "2. \u4ece\u6bcf\u4e2a\u6d41\u6d3e\u6700\u4f73\u53d1\u73b0\u4e2d\u63d0\u53d6\u5173\u952e\u56e0\u5b50\n"
        "3. \u8bbe\u8ba1\u81f3\u5c11 10 \u7ec4\u8de8\u6d41\u6d3e\u7ec4\u5408\n"
        "4. \u56de\u6d4b\u6bcf\u7ec4\u7ec4\u5408\n"
        "\n"
        "### \u8de8\u6d41\u6d3e\u7ec4\u5408\u89c4\u5219\n"
        "- \u81f3\u5c11 3 \u7ec4\u6765\u81ea\u4e0d\u540c\u6d41\u6d3e\u5bf9\n"
        "- \u81f3\u5c11 3 \u7ec4\u5305\u542b SPX\u00d7\u67d0\u6d41\u6d3e\n"
        "- \u5305\u542b 2 \u7ec4\u6781\u7aef\u53d8\u4f53\n"
        "\n"
        "### \u6570\u636e\u89c4\u5219\n"
        "- \u6240\u6709\u67e5\u8be2\u5fc5\u987b\u52a0 FINAL\n"
        "- \u65e5\u671f\u683c\u5f0f YYYYMMDD\n"
        "- \u4e3b\u677f\u8fc7\u6ee4: ts_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'\n"
        "- \u4e0d\u7528 basic_eps_yoy(\u5168NULL)\n"
        "- \u4e0d\u7528 net_mf\uff0c\u7528 net_mf_amount\n"
        "\n"
        "### \u6210\u529f\u6807\u51c6\n"
        "- WR >= 52% AND 5D\u6536\u76ca >= 3% AND \u4fe1\u53f7\u6570 >= 200\n"
        "\n"
        "### \u8f93\u51fa\n"
        f"\u6587\u4ef6\uff1a{STRATEGY_DIR}/logs/iter_{ITER}/analysis_T9_\u7ec4\u5408\u4ea4\u53c9.md\n"
        "- \u6bcf\u7ec4\u7ec4\u5408\u7684\u53c2\u6570\u3001SQL\u3001\u7ed3\u679c\u3001\u5206\u6790\n"
        "- \u5982\u679c\u67d0\u4e9b\u6d41\u6d3e\u8f93\u51fa\u4e0d\u5b58\u5728\uff0c\u7b49\u5f8530\u79d2\u91cd\u8bd5\uff0c\u6700\u591a3\u6b21\n"
    )

    t9_id = kanban_create("T9: \u7ec4\u5408\u4ea4\u53c9\u9a8c\u8bc1","analyst",t9_body,parents=analyst_tids,max_runtime=10800)
    log(f"T9 created: {t9_id}")
    state["t9_id"] = t9_id
    state["phase"] = "T9_created"
    save_state(state)

    # Phase 3: Wait for T9
    wait_for_tasks([t9_id], timeout=14400, poll_interval=120, label="T9")
    state["phase"] = "T9_done"
    save_state(state)

    # Phase 4: Create T10 Convergence
    log("\n--- Phase 4: Creating T10: Convergence ---")

    t10_body = (
        "## \U0001f4c5 \u65f6\u95f4\u4e0a\u4e0b\u6587\uff08\u5f3a\u5236\u9075\u5b88\uff09\n"
        f"- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a{TIME_STR}\n"
        f"- \u672c\u8f6e\u8fed\u4ee3\u7f16\u53f7\uff1a{ITER}\n"
        "\n"
        "## \u4efb\u52a1\uff1a\u4e3b\u63a7\u6536\u655b\n"
        f"1. \u8bfb\u53d6 T2-T9 \u8f93\u51fa ({STRATEGY_DIR}/logs/iter_{ITER}/)\n"
        "2. \u8bfb\u53d6 \u5f53\u524d state.json\n"
        "3. \u6bd4\u8f83\u672c\u8f6e\u6700\u4f73 vs \u5c40\u7ecf\u7eaa\u7eaa\u5f55 (SPX-NEG: WR=94.93%, R5=21.32%)\n"
        "4. \u5982\u679c\u8d85\u8d8a -> update best_metrics, fatigue_count=0\n"
        "5. \u5426\u5219 -> fatigue_count += 1\n"
        "6. \u66f4\u65b0 state.json + knowledge_base.md\n"
        "\n"
        "### \u5982\u679c fatigue_count >= 10\n"
        "- \u5f3a\u8c03\uff1a\u8fde\u7eed10\u8f6e\u672a\u7834\u7eaa\u5f55\uff0c\u5efa\u8bae\u8c03\u6574\u65b9\u5411\n"
        "\n"
        "### \u8f93\u51fa\n"
        f"1. \u66f4\u65b0 {STRATEGY_DIR}/state/state.json\n"
        f"2. \u66f4\u65b0 {STRATEGY_DIR}/state/knowledge_base.md\n"
        f"3. \u8f93\u51fa {STRATEGY_DIR}/logs/iter_{ITER}/analysis_T10_\u6536\u655b.md\n"
    )

    t10_id = kanban_create("T10: \u4e3b\u63a7\u6536\u655b","analyst",t10_body,parents=[t9_id],max_runtime=10800)
    log(f"T10 created: {t10_id}")
    state["t10_id"] = t10_id
    state["phase"] = "T10_created"
    save_state(state)

    # Phase 5: Wait for T10
    wait_for_tasks([t10_id], timeout=7200, poll_interval=120, label="T10")
    state["phase"] = "T10_done"
    save_state(state)

    # Phase 6: Create T11 Report
    log("\n--- Phase 6: Creating T11: Report ---")

    t11_body = (
        "## \U0001f4c5 \u65f6\u95f4\u4e0a\u4e0b\u6587\n"
        f"- \u6267\u884c\u65f6\u95f4\uff1a{TIME_STR}\n"
        f"- \u8fed\u4ee3\u7f16\u53f7\uff1a{ITER}\n"
        "\n"
        "## \u4efb\u52a1\uff1a\u751f\u6210\u62a5\u544a\n"
        f"1. \u8bfb\u53d6 state.json\n"
        f"2. \u8bfb\u53d6 knowledge_base.md\n"
        f"3. \u8bfb\u53d6 T10: {STRATEGY_DIR}/logs/iter_{ITER}/analysis_T10_\u6536\u655b.md\n"
        "\n"
        "### \u62a5\u544a\u5185\u5bb9\n"
        "- Top 5 \u7b56\u7565\u6392\u540d\n"
        "- \u5404\u6d41\u6d3e\u8868\u73b0\u5bf9\u6bd4\n"
        "- T9 \u8de8\u6d41\u6d3e\u7ec4\u5408\u7ed3\u679c\n"
        "- \u5173\u952e\u53d1\u73b0\n"
        "- \u4e0b\u8f6e\u5efa\u8bae\n"
        "\n"
        "### \u8f93\u51fa\n"
        f"\u6587\u4ef6\uff1a{STRATEGY_DIR}/reports/mining-all167-iter{ITER}-20260513-HHMM.md\n"
    )

    t11_id = kanban_create("T11: \u62a5\u544a\u751f\u6210","writer",t11_body,parents=[t10_id],max_runtime=600)
    log(f"T11 created: {t11_id}")
    state["t11_id"] = t11_id
    state["phase"] = "all_created"
    save_state(state)

    # Phase 7: Wait for T11
    wait_for_tasks([t11_id], timeout=3600, poll_interval=60, label="T11")
    state["phase"] = "completed"
    save_state(state)

    log("\n" + "=" * 60)
    log("FULL PIPELINE COMPLETE!")
    log(f"T1: {T1_ID}")
    log(f"T2-T8: {list(ANALYST_IDS.values())}")
    log(f"T9: {t9_id}")
    log(f"T10: {t10_id}")
    log(f"T11: {t11_id}")
    log("=" * 60)

except Exception as e:
    log(f"\nERROR: {e}")
    import traceback
    log(traceback.format_exc())
    state["phase"] = "error"
    state["error"] = str(e)
    save_state(state)
    sys.exit(1)
