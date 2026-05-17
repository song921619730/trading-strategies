#!/usr/bin/env python3
"""Pipeline orchestrator for Iter24 — handles T9/T10/T11 sequential creation.
Spawning command: nohup python3 scripts/pipeline_orchestrator_iter24.py >> logs/poller_iter24.log 2>&1 &
"""
import json, sqlite3, subprocess, time, os, sys
from datetime import datetime

ITER = 24
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
LOGS_DIR = STRATEGY_DIR + "/logs/iter_" + str(ITER)
DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
ANALYST_IDS_FILE = STRATEGY_DIR + "/state/task_ids_iter" + str(ITER) + ".json"

def log(msg):
    line = "[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "] " + msg
    print(line, flush=True)

def kanban_create(title, assignee, body, parents=None, max_runtime=3600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log("ERROR creating " + title + ": " + result.stderr)
        return None
    return json.loads(result.stdout)["id"]

def wait_for_tasks(tids, timeout=7200, poll_interval=60):
    """Poll kanban.db until all tasks are done, or timeout."""
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            log("TIMEOUT after " + str(int(elapsed)) + "s waiting for tasks")
            return False
        
        conn = sqlite3.connect(DB)
        statuses = {}
        for t in tids:
            row = conn.execute("SELECT id, status FROM tasks WHERE id=?", (t,)).fetchone()
            if row:
                statuses[row[0]] = row[1]
            else:
                statuses[t] = "NOT_FOUND"
        conn.close()
        
        done = all(s == "done" for s in statuses.values())
        pending = [(t, s) for t, s in statuses.items() if s != "done"]
        
        log("Poll: " + str(len([s for s in statuses.values() if s == 'done'])) + "/" + str(len(tids)) + " done" + 
            (" | pending: " + str(pending[:3]) if pending else " | ALL DONE"))
        
        if done:
            return True
        
        # Report file status periodically
        if int(elapsed) % 300 < poll_interval:  # every ~5 min
            if os.path.isdir(LOGS_DIR):
                files = [f for f in os.listdir(LOGS_DIR) if f.startswith("analysis_T")]
                log("Files in logs dir: " + str(len(files)) + " - " + str(files))
        
        time.sleep(poll_interval)

def read_latest_logs(tids, prefix="analysis_T"):
    """Read all analysis files from the logs directory."""
    if not os.path.isdir(LOGS_DIR):
        return []
    files = sorted([f for f in os.listdir(LOGS_DIR) if f.startswith(prefix)])
    summaries = []
    for f in files:
        path = LOGS_DIR + "/" + f
        try:
            with open(path) as fh:
                content = fh.read()
            summaries.append({"filename": f, "size": len(content), "path": path})
        except Exception as e:
            log("Error reading " + path + ": " + str(e))
    return summaries

# ========== MAIN ==========
log("=" * 60)
log("Pipeline Orchestrator Iter24 started")
log("Strategy dir: " + STRATEGY_DIR)
log("Logs dir: " + LOGS_DIR)

# Load task IDs
with open(ANALYST_IDS_FILE) as f:
    task_ids = json.load(f)

analyst_ids = [task_ids["T%d" % i] for i in range(2, 9)]
log("Analyst task IDs: " + str(analyst_ids))
log("T1 ID: " + task_ids.get("T1", "N/A"))

# Load state for best metrics
with open(STRATEGY_DIR + "/state/state.json") as f:
    state = json.load(f)
best = state["best_metrics"]
fatigue = state["fatigue_count"]

# === Phase 1: Wait for T2-T8 ===
log("Phase 1: Waiting for T2-T8 to complete (7 analyst tasks)...")
if not wait_for_tasks(analyst_ids):
    log("FAILED: T2-T8 did not complete within timeout")
    sys.exit(1)

log("All T2-T8 completed! Proceeding to T9 creation.")

# === Phase 2: Verify T1 output exists ===
t1_log = LOGS_DIR + "/analysis_T1_数据检查.md"
if os.path.exists(t1_log):
    with open(t1_log) as f:
        t1_content = f.read()
    log("T1 log found: " + str(len(t1_content)) + " bytes")
    # Extract data baseline date from T1
    for line in t1_content.split("\n"):
        if "数据基准" in line or "基准日期" in line or "基准日" in line:
            log("T1 baseline: " + line.strip())
else:
    log("WARNING: T1 log not found at " + t1_log)

# === Phase 3: Check analyst output files ===
analyst_files = read_latest_logs(analyst_ids)
log("Analyst output files found: " + str(len(analyst_files)))
for af in analyst_files:
    log("  " + af["filename"] + " (" + str(af["size"]) + " bytes)")

# === Phase 4: Create T9 - 组合交叉验证 ===
log("Creating T9: 组合交叉验证...")

t9_lines = []
t9_lines.append("## 时间上下文（强制遵守）")
t9_lines.append("- 系统执行时间：" + datetime.now().strftime("%Y-%m-%d %H:%M") + " UTC+8")
t9_lines.append("- 本轮迭代编号：24")
t9_lines.append("- 历史最佳：WR=%.2f%%, R5=%.2f%%, Sharpe=%.2f" % (best['win_rate_5d'], best['ret_5d'], best['sharpe_5d']))
t9_lines.append("- fatigue_count: %d" % fatigue)
t9_lines.append("")
t9_lines.append("### 职责：跨流派组合交叉验证")
t9_lines.append("读取 T2-T8 所有输出文件（位于 " + LOGS_DIR + "/），从每个流派最佳发现中提取关键因子做交叉组合。")
t9_lines.append("")
t9_lines.append("### 执行步骤")
t9_lines.append("1. 读取 T1 数据检查结果：%s/analysis_T1_数据检查.md" % LOGS_DIR)
t9_lines.append("2. 读取 T2-T8 所有分析文件：")
for af in analyst_files:
    t9_lines.append("   - %s/analysis_T%d_*.md" % (LOGS_DIR, 2 + analyst_files.index(af)))
t9_lines.append("3. 从每个流派的最佳策略中提取 1-2 个关键因子")
t9_lines.append("4. 做至少 10 组因子交叉组合")
t9_lines.append("5. 每组用 query_sql MCP 执行 ClickHouse 回测")
t9_lines.append("")
t9_lines.append("### 回测要求")
t9_lines.append("- 使用 query_sql MCP 工具，所有查询加 FINAL")
t9_lines.append("- 主板过滤：ts_code NOT LIKE '30%%' AND NOT LIKE '688%%' AND NOT LIKE '920%%' AND NOT LIKE '%%ST%%'")
t9_lines.append("- 已知数据修复：net_mf->net_mf_amount, basic_eps_yoy->tr_yoy/netprofit_yoy")
t9_lines.append("- 成功标准：WR >= 52%% AND 5D收益 >= 3%% AND 信号数 >= 200")
t9_lines.append("")
t9_lines.append("### 输出要求")
t9_lines.append("写入绝对路径：%s/analysis_T9_组合交叉.md" % LOGS_DIR)
t9_lines.append("包含：")
t9_lines.append("- 每个交叉组合的描述和逻辑")
t9_lines.append("- 完整的 SQL 查询语句（可复现）")
t9_lines.append("- 回测结果：信号数、WR、5D收益、10D收益、20D收益、夏普")
t9_lines.append("- 最佳 3 个组合的详细分析")
t9_lines.append("")
t9_lines.append("### 完成时")
t9_lines.append("用 kanban_complete 标记完成，summary 中包含最佳交叉组合的参数和指标")

t9_body = "\n".join(t9_lines)
t9_id = kanban_create("Iter24 T9: 组合交叉验证", "analyst", t9_body, parents=analyst_ids, max_runtime=10800)
if not t9_id:
    log("FATAL: Could not create T9")
    sys.exit(1)
log("T9 created: " + t9_id)

# === Phase 5: Wait for T9 ===
log("Phase 2: Waiting for T9 to complete...")
if not wait_for_tasks([t9_id], timeout=10800):
    log("FAILED: T9 did not complete within timeout")
    sys.exit(1)
log("T9 completed! Proceeding to T10 creation.")

# === Phase 6: Check T9 output ===
t9_log = LOGS_DIR + "/analysis_T9_组合交叉.md"
if os.path.exists(t9_log):
    with open(t9_log) as f:
        t9_content = f.read()
    log("T9 log found: " + str(len(t9_content)) + " bytes")
else:
    log("WARNING: T9 log not found")

# === Phase 7: Create T10 - 主控收敛 ===
log("Creating T10: 主控收敛...")

# Read all analysis files
all_logs = read_latest_logs(None, prefix="analysis_T")

t10_lines = []
t10_lines.append("## 时间上下文（强制遵守）")
t10_lines.append("- 系统执行时间：" + datetime.now().strftime("%Y-%m-%d %H:%M") + " UTC+8")
t10_lines.append("- 本轮迭代编号：24")
t10_lines.append("- 历史最佳：WR=%.2f%%, R5=%.2f%%, Sharpe=%.2f" % (best['win_rate_5d'], best['ret_5d'], best['sharpe_5d']))
t10_lines.append("- fatigue_count: %d" % fatigue)
t10_lines.append("")
t10_lines.append("### 职责：主控收敛 + 状态更新")
t10_lines.append("读取 T2-T9 所有输出文件（位于 " + LOGS_DIR + "/），执行收敛分析并更新 state.json 和 knowledge_base.md。")
t10_lines.append("")
t10_lines.append("### 执行步骤")
t10_lines.append("1. 读取 T1 ~ T9 所有分析文件：")
for lf in all_logs:
    t10_lines.append("   - " + lf["path"])
t10_lines.append("2. 提取每轮最佳策略指标")
t10_lines.append("3. 与本轮历史最佳做对比")
t10_lines.append("4. 更新 ./state/state.json（用 Python 或 vim）")
t10_lines.append("5. 追加有效发现到 ./state/knowledge_base.md")
t10_lines.append("")
t10_lines.append("### state.json 更新逻辑")
t10_lines.append("- 如果本轮有超过历史最佳的策略 -> 更新 best_metrics，fatigue_count = 0")
t10_lines.append("- 否则 -> fatigue_count += 1")
t10_lines.append("- 将本轮所有参数组合 hash 加入 recent_combos")
t10_lines.append("- 将本轮摘要加入 history（保持最多50条）")

# Load current state for guidelines
t10_lines.append("")
t10_lines.append("当前 state.json 关键字段：")
t10_lines.append("- current_iteration: 24")
t10_lines.append("- best_metrics: WR=%.2f (T8-C3e), R5=%.2f, Sharpe=%.2f" % (best['win_rate_5d'], best['ret_5d'], best['sharpe_5d']))
t10_lines.append("- best_metrics_global_record: R5=%.2f (T9-X17, Iter22)" % state['best_metrics_global_record']['ret_5d'])
t10_lines.append("- fatigue_count: %d" % fatigue)
t10_lines.append("")
t10_lines.append("### knowledge_base 更新规则")
t10_lines.append("有效发现（PASS 或以上的策略）必须追加到 knowledge_base.md")
t10_lines.append("格式：YYYY-MM-DD (iter N) - 流派名 + 参数 + 指标 + 结论")
t10_lines.append("")
t10_lines.append("### 输出要求")
t10_lines.append("写入绝对路径：%s/analysis_T10_收敛.md" % LOGS_DIR)
t10_lines.append("包含：本轮最佳策略、流派对比、疲劳计数判断、下轮建议")

t10_body = "\n".join(t10_lines)
t10_id = kanban_create("Iter24 T10: 主控收敛", "analyst", t10_body, parents=[t9_id], max_runtime=3600)
if not t10_id:
    log("FATAL: Could not create T10")
    sys.exit(1)
log("T10 created: " + t10_id)

# === Phase 8: Wait for T10 ===
log("Phase 3: Waiting for T10 to complete...")
if not wait_for_tasks([t10_id], timeout=7200):
    log("FAILED: T10 did not complete within timeout")
    sys.exit(1)
log("T10 completed! Proceeding to T11 creation.")

# === Phase 9: Check T10 output ===
t10_log = LOGS_DIR + "/analysis_T10_收敛.md"
if os.path.exists(t10_log):
    with open(t10_log) as f:
        t10_content = f.read()
    log("T10 log found: " + str(len(t10_content)) + " bytes")
else:
    log("WARNING: T10 log not found")

# Load updated state after T10
with open(STRATEGY_DIR + "/state/state.json") as f:
    new_state = json.load(f)
new_best = new_state["best_metrics"]
new_fatigue = new_state["fatigue_count"]
log("Updated state: WR=%.2f, R5=%.2f, fatigue=%d" % (new_best['win_rate_5d'], new_best['ret_5d'], new_fatigue))

# === Phase 10: Create T11 - 报告生成 ===
log("Creating T11: 报告生成...")

t11_lines = []
t11_lines.append("## 时间上下文（强制遵守）")
t11_lines.append("- 系统执行时间：" + datetime.now().strftime("%Y-%m-%d %H:%M") + " UTC+8")
t11_lines.append("- 本轮迭代编号：24")
t11_lines.append("")
t11_lines.append("### 职责：生成格式化报告")
t11_lines.append("读取 T10 收敛结果 + state.json + knowledge_base.md，生成完整的研究报告。")
t11_lines.append("")
t11_lines.append("### 输入文件")
t11_lines.append("1. T10 收敛结果：%s/analysis_T10_收敛.md" % LOGS_DIR)
t11_lines.append("2. state.json：" + STRATEGY_DIR + "/state/state.json")
t11_lines.append("3. knowledge_base.md：" + STRATEGY_DIR + "/state/knowledge_base.md")
t11_lines.append("4. T2-T9 所有日志（如需引用具体数据）：" + LOGS_DIR + "/")
t11_lines.append("")
t11_lines.append("### 报告内容要求")
t11_lines.append("1. Top 5 策略排名（按综合评分：WR * R5 * sqrt(N)）")
t11_lines.append("2. 各流派表现对比")
t11_lines.append("3. 本轮关键发现（重点突出超越历史最佳的发现）")
t11_lines.append("4. 疲劳计数状态和趋势判断")
t11_lines.append("5. 下轮策略挖掘建议（方向性指导）")
t11_lines.append("6. 参考数据基准日期（从 T1 读取）")
t11_lines.append("")
t11_lines.append("### 报告路径")
t11_lines.append("保存到：" + STRATEGY_DIR + "/reports/mining-all167-iter24-" + datetime.now().strftime("%Y%m%d") + "-" + datetime.now().strftime("%H%M") + ".md")
t11_lines.append("")
t11_lines.append("### 格式要求")
t11_lines.append("- 使用 Markdown 格式")
t11_lines.append("- 所有日期使用 YYYY-MM-DD 格式")
t11_lines.append("- 包含数据表格（如适用）")
t11_lines.append("- 禁止推测日期")
t11_lines.append("")
t11_lines.append("### 完成时")
t11_lines.append("用 kanban_complete 标记完成，summary 中包含报告路径和核心发现")

t11_body = "\n".join(t11_lines)
t11_id = kanban_create("Iter24 T11: 报告生成", "writer", t11_body, parents=[t10_id], max_runtime=600)
if not t11_id:
    log("FATAL: Could not create T11")
    sys.exit(1)
log("T11 created: " + t11_id)

# === Phase 11: Wait for T11 ===
log("Phase 4: Waiting for T11 to complete...")
if not wait_for_tasks([t11_id], timeout=1800):
    log("FAILED: T11 did not complete within timeout")
    sys.exit(1)
log("T11 completed!")

# === Final summary ===
log("=" * 60)
log("Iter24 Pipeline COMPLETE!")
log("T1-T8: All done")
log("T9: " + t9_id + " - done")
log("T10: " + t10_id + " - done")
log("T11: " + t11_id + " - done")
log("Logs: " + LOGS_DIR)
log("State: " + STRATEGY_DIR + "/state/state.json")
log("Report: " + STRATEGY_DIR + "/reports/")

# Final state check
with open(STRATEGY_DIR + "/state/state.json") as f:
    final_state = json.load(f)
final_best = final_state["best_metrics"]
log("=== Final State ===")
log("iteration: " + str(final_state["current_iteration"]))
log("best: WR=%.2f, R5=%.2f, Sharpe=%.2f" % (final_best['win_rate_5d'], final_best['ret_5d'], final_best['sharpe_5d']))
log("fatigue: " + str(final_state["fatigue_count"]))
log("history entries: " + str(len(final_state["history"])))
log("recent combos: " + str(len(final_state["recent_combos"])))
log("=" * 60)
log("Pipeline orchestrator Iter24 exiting normally.")
