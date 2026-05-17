#!/usr/bin/env python3
"""Background poller for iter 37 — waits for analysts, creates T13/T14."""
import sqlite3
import time
import subprocess
import json
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER = 37
ANALYST_IDS = ["t_fe1940af", "t_c1a76e75", "t_11c198e8", "t_a87f14b2", "t_b39f81d4", "t_adc98cfc", "t_c386fada", "t_c683e15d", "t_57a660c2", "t_9286629b", "t_2b4738ff"]

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(f"{STRATEGY_DIR}/logs/poller.log", "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}")

def kanban_create(title, assignee, body, parents=None, max_runtime=3600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR creating {title}: {result.stderr[:300]}")
        return None
    return json.loads(result.stdout)["id"]

def wait_for_tasks(tids, timeout=14400):
    """Wait until all specified tasks are 'done'."""
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            log(f"TIMEOUT after {elapsed:.0f}s waiting for {len(tids)} tasks!")
            return False
        conn = sqlite3.connect(DB)
        done_count = 0
        total = len(tids)
        for tid in tids:
            row = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
            if row and row[0] == "done":
                done_count += 1
        conn.close()
        if done_count == total:
            log(f"All {total} tasks done! ({elapsed:.0f}s)")
            return True
        log(f"Progress: {done_count}/{total} done | elapsed={elapsed:.0f}s")
        time.sleep(60)

def update_state_json():
    """Read state.json, add iter 37 history entry."""
    state_path = f"{STRATEGY_DIR}/state/state.json"
    with open(state_path) as f:
        state = json.load(f)
    
    # Add history entry
    entry = {
        "iteration": ITER,
        "ret_5d": None,
        "win_5d": None,
        "signal_count": None,
        "sharpe_5d": None,
        "analyst": "T13_主控收敛 (poller auto)",
        "params": "Iter37完整汇总 (详见poller输出)",
        "note": f"🔄 Iter37自动创建 — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    }
    
    if "history" not in state:
        state["history"] = []
    state["history"].insert(0, entry)
    
    # Update current iteration
    state["current_iteration"] = ITER
    
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    log("state.json updated with iter 37 entry")

def main():
    log(f"=== Iter {ITER} Background Poller Started ===")
    
    # Phase 1: Wait for T2-T12 analyst tasks
    log("Phase 1: Waiting for T2-T12 analysts...")
    if not wait_for_tasks(ANALYST_IDS):
        log("Phase 1 FAILED — timeout")
        return
    
    # Check log files exist
    import os
    iter_dir = f"{STRATEGY_DIR}/logs/iter_{ITER}"
    analysis_files = [f for f in os.listdir(iter_dir) if f.startswith("analysis_")]
    log(f"Found {len(analysis_files)} analysis files in {iter_dir}")
    
    # Phase 2: Create T13 convergence task
    log("Phase 2: Creating T13 convergence...")
    t13_body = (
        "## 📅 时间上下文\n"
        f"- 系统执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n"
        f"- 迭代编号：iter {ITER}\n"
        "\n"
        "## T13: 主控收敛\n"
        "读取 T2-T12 各流派分析报告，进行多流派融合和最终决策:\n"
        "1. 逐一读取所有 analysts 输出文件\n"
        "2. 筛选 DUAL-PASS 策略（训练集+测试集均通过）\n"
        "3. 按 R5/wR/Sharpe/P10 综合评分排序\n"
        "4. 生成标记: 过拟合风险等级(低/中/高)\n"
        "5. 判断是否超越全局纪录 WR=99.55%, R5=25.23%\n"
        "\n"
        "输出到：" + STRATEGY_DIR + f"/logs/iter_{ITER}/T13_convergence.md\n"
        "\n"
        "格式要求：策略排名表(流派|组合|N|WR_train|WR_test|R5_train|R5_test|Sharpe|P10|过拟合风险|状态)\n"
    )
    
    t13_id = kanban_create(
        f"T13: 主控收敛 (iter {ITER})",
        "analyst",
        t13_body,
        parents=ANALYST_IDS,
        max_runtime=10800
    )
    if not t13_id:
        log("FAILED to create T13!")
        return
    log(f"T13 ID: {t13_id}")
    
    # Phase 3: Wait for T13
    log("Phase 3: Waiting for T13 convergence...")
    if not wait_for_tasks([t13_id]):
        log("Phase 3 FAILED — timeout")
        return
    
    # Phase 4: Create T14 report
    log("Phase 4: Creating T14 report...")
    t14_body = (
        "## 📅 时间上下文\n"
        f"- 系统执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n"
        f"- 迭代编号：iter {ITER}\n"
        "\n"
        "## T14: 报告生成\n"
        "读取 T13 收敛结果，生成可投递报告。\n"
        "报告必须包含：\n"
        "1. 本轮整体表现（PASS率/测试组合数/流派表现）\n"
        "2. 最佳策略排名表（Top 10）\n"
        "3. 是否超越全局纪录\n"
        "4. 关键新因子/模式发现\n"
        "5. 下轮建议\n"
        "\n"
        "输出到：" + STRATEGY_DIR + "/reports/mining-all167-iter" + str(ITER) + "-" + TS_NOW[:10] + ".md\n"
    )
    
    t14_id = kanban_create(
        f"T14: 报告生成 (iter {ITER})",
        "writer",
        t14_body,
        parents=[t13_id],
        max_runtime=1200
    )
    if not t14_id:
        log("FAILED to create T14!")
        return
    log(f"T14 ID: {t14_id}")
    
    # Phase 5: Wait for T14
    log("Phase 5: Waiting for T14 report...")
    if not wait_for_tasks([t14_id]):
        log("Phase 5 FAILED — timeout")
        return
    
    # Phase 6: Update state.json
    log("Phase 6: Updating state.json...")
    update_state_json()
    
    log(f"=== Iter {ITER} Pipeline COMPLETE! ===")

if __name__ == "__main__":
    main()
