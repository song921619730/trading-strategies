#!/usr/bin/env python3
"""
Pipeline orchestrator for iter 38 — Waits for T2-T12 to complete,
then creates T13 (convergence).
Spawned as a background process by the orchestrator.
"""
import sqlite3, time, subprocess, json, sys, os
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER = 38
LOG = os.path.join(STRATEGY_DIR, "logs", "poller.log")

ANALYST_IDS = ["t_1efc1af0", "t_6c0b2453", "t_0b4af415", "t_5b4d2ce6",
               "t_8bab777f", "t_a5ff43ac", "t_33c78ef8", "t_c581f25f",
               "t_6700a763", "t_aaa3aec4", "t_dc93fa28"]


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def wait_for_tasks(tids, timeout=43200):
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            log("TIMEOUT after %ds" % int(elapsed))
            return False
        done_count = 0
        for tid in tids:
            try:
                conn = sqlite3.connect(DB)
                row = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
                conn.close()
                if row and row[0] == 'done':
                    done_count += 1
            except Exception as e:
                log("DB error %s: %s" % (tid, e))
        log("Poll: %d/%d done | elapsed=%ds" % (done_count, len(tids), int(elapsed)))
        if done_count == len(tids):
            return True
        time.sleep(120)


def kanban_create(title, assignee, body, parents=None, max_runtime=10800):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        log("ERROR creating '%s': %s" % (title[:40], result.stderr[:200]))
        return None
    try:
        return json.loads(result.stdout)["id"]
    except Exception as e:
        log("PARSE ERROR: %s - %s" % (e, result.stdout[:200]))
        return None


def main():
    log("=== Pipeline Orchestrator for iter %d STARTED ===" % ITER)
    analyst_list = ANALYST_IDS
    log("Waiting for %d analyst tasks (T2-T12)..." % len(analyst_list))

    ts_start = time.time()
    success = wait_for_tasks(analyst_list, timeout=43200)
    elapsed = time.time() - ts_start
    log("All analysts done after %ds. Creating T13..." % int(elapsed))

    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    t13_body = (
        "## \u23f0 \u65f6\u95f4\u4e0a\u4e0b\u6587\uff08\u5f3a\u5236\u9075\u5b88\uff09\n"
        "- \u7cfb\u7edf\u6267\u884c\u65f6\u95f4\uff1a" + ts_now + " UTC+8\n"
        "- \u8fed\u4ee3\u7f16\u53f7\uff1aiter 38\n"
        "\n"
        "## T13: \u4e3b\u63a7\u6536\u655b (iter 38)\n"
        "\n"
        "### \u4efb\u52a1\n"
        "1. \u8bfb\u53d6 T2\uff5eT12 \u5168\u90e811\u4efd\u5206\u6790\u62a5\u544a\uff0c\u9010\u4e00\u8bc4\u4f30\u6bcf\u7ec4\u53c2\u6570\u7ec4\u5408\u7684IS/OOS\u8868\u73b0\n"
        "2. \u7efc\u5408\u8bc4\u5206\u6240\u6709\u53d1\u73b0\uff0c\u6309R5/WR/N/Sharpe\u6392\u5e8f\n"
        "3. \u5224\u65ad\u662f\u5426\u6709\u7b56\u7565\u8d85\u8d8a best_metrics (WR=87.81%, R5=38.81%) \u6216\u5168\u5c40\u7eaa\u5f55 (WR=99.55%, R5=25.23%)\n"
        "4. \u66f4\u65b0 state.json: current_iteration, fatigue_count, best_metrics, history\n"
        "5. \u66f4\u65b0 recent_combos\n"
        "6. \u8f93\u51fa\u5230\uff1a" + STRATEGY_DIR + "/logs/iter_38/T13_convergence.md\n"
        "\n"
        "## \u8bc4\u4f30\u89c4\u5219\n"
        "- \u82e5\u6709\u7b56\u7565 WR > best_metrics.win_rate_5d(87.81%) \u6216 R5 > best_metrics.ret_5d(38.81%) \uff08\u4fe1\u53f7\u6570 >= 200\uff09\u2192 \u66f4\u65b0 best_metrics\uff0cfatigue_count = 0\n"
        "- \u5426\u5219\u2192 fatigue_count += 1\n"
        "- fatigue_count >= 10 \u65f6\u63d0\u9192\u7528\u6237\n"
        "- T11/T12 \u4fe1\u53f7\u9608\u503c\u53ef\u964d\u4f4e\u81f3 >= 100\n"
    )

    t13_id = kanban_create(
        "T13: \u4e3b\u63a7\u6536\u655b (iter 38)",
        "analyst",
        t13_body,
        parents=analyst_list,
        max_runtime=10800
    )

    if not t13_id:
        log("FATAL: Failed to create T13. Exiting.")
        sys.exit(1)

    log("T13 created: %s" % t13_id)
    log("=== Pipeline Orchestrator for iter %d DONE (T13 launched) ===" % ITER)


if __name__ == "__main__":
    main()
