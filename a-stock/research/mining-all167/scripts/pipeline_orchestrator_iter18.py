#!/usr/bin/env python3
"""Background poller for Iter18 mining pipeline.
Wait for T2-T8 analysts to complete, then create T9-T11 sequentially.

=== PID Safety ===
This script checks for existing instances before running.

=== Usage ===
    python3 scripts/pipeline_orchestrator_iter18.py
"""

import os, sys, json, time, subprocess, sqlite3, datetime
from pathlib import Path

# ═══ Configuration ═══
ITER = 18
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
NOW = "2026-05-13 07:15"

# ── Task IDs (from Phase 1 creation) ──
T1_ID = "t_3b25b59d"
ANALYST_IDS = [
    "t_319b88da",  # T2: 动量趋势
    "t_2a8b3693",  # T3: 反转低吸
    "t_72f0bb8b",  # T4: 资金主力
    "t_545909d0",  # T5: 基本面估值
    "t_b31587cd",  # T6: 板块轮动
    "t_7c18fa26",  # T7: 跨市场联动
    "t_1779c2b1",  # T8: 量价形态
]

ANALYST_NAMES = {
    "t_319b88da": "T2_动量趋势",
    "t_2a8b3693": "T3_反转低吸",
    "t_72f0bb8b": "T4_资金主力",
    "t_545909d0": "T5_基本面估值",
    "t_b31587cd": "T6_板块轮动",
    "t_7c18fa26": "T7_跨市场联动",
    "t_1779c2b1": "T8_量价形态",
}

SYSTEM_TIME = NOW

# ── PID safety ──
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

# ── Logging ──
def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(f"{STRATEGY_DIR}/logs/poller_iter{ITER}.log", "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}")

# ── Kanban DB helpers ──
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
    """Block until all task IDs have status='done'. Returns True on success, False on timeout."""
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

        # Check for failures
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

# ── Kanban create ──
def kanban_create(title, assignee, body, parents=None, max_runtime=600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        log(f"ERROR creating '{title}': {result.stderr[:300]}")
        return None
    try:
        data = json.loads(result.stdout)
        tid = data["id"]
        log(f"Created {tid}: {title} (assignee={assignee}, maxRT={max_runtime})")
        return tid
    except json.JSONDecodeError as e:
        log(f"ERROR parsing JSON for '{title}': {e}")
        log(f"stdout: {result.stdout[:300]}")
        return None


# ═══ MAIN ═══
def main():
    log(f"{'═' * 60}")
    log(f"Iter{ITER} Pipeline Orchestrator starting")
    log(f"Strategy dir: {STRATEGY_DIR}")
    log(f"Analyst IDs: {ANALYST_IDS}")

    ensure_single_instance()

    # Create logs/iter_18 directory
    os.makedirs(f"{STRATEGY_DIR}/logs/iter_{ITER}", exist_ok=True)

    # ============================================================
    # PHASE 1: Wait for T2-T8 analysts
    # ============================================================
    log(f"\n{'─'*60}")
    log(f"Phase 1: Waiting for T2-T8 analysts ({len(ANALYST_IDS)} tasks)...")
    
    # First check if T1 is done
    t1_status = check_task_status(T1_ID)
    log(f"T1 status: {t1_status}")
    
    if not wait_for_tasks(ANALYST_IDS, timeout=14400, poll_interval=60):
        log("ERROR: T2-T8 did not complete within 4 hours. Exiting.")
        sys.exit(1)
    
    log("Phase 1 complete! All analysts done.")

    # ============================================================
    # PHASE 2: Create T9 — Cross-validation
    # ============================================================
    log(f"\n{'─'*60}")
    log(f"Phase 2: Creating T9 — 组合交叉验证")

    t9_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{SYSTEM_TIME}
- 本轮迭代编号：{ITER}
- 所有 7 个 analyst 流派已完成挖掘

## 任务：组合交叉验证

### 你的角色
你扮演 组合交叉验证分析师。你的任务是读取 T2-T8 所有 analyst 的输出文件，从每个流派的最佳发现中提取因子做交叉组合。

### 文件引用
- 参数空间：`./skills/param-space.md`
- 循环规则：`./skills/mining-rules.md`
- 知识库：`./state/knowledge_base.md`
- 日志目录：`./logs/iter_{ITER}/`

### 执行步骤
1. 读取 T2-T8 所有分析输出文件（位于 `./logs/iter_{ITER}/`）
2. 从每个流派的最佳发现中提取最有效的因子
3. 至少测试 10 组交叉组合（不同流派的因子组合）
4. 每组用 SQL 回测
5. 记录结果到：`{STRATEGY_DIR}/logs/iter_{ITER}/analysis_T9_组合交叉.md`

### 数据查询规则
- 使用 FINAL, 日期 YYYYMMDD
- 先确定数据基准日期
- 主板过滤

### 已知数据问题
- basic_eps_yoy 为空，用 tr_yoy / netprofit_yoy 代替
- net_mf 不存在，用 net_mf_amount
- cyq_chips 可用但偶发 404（重试）
- 财报季频数据匹配困难

### 成功标准
WR >= 55% AND 5D收益 >= 5% AND 信号数 >= 200

### 输出
1. 所有 10+ 组交叉组合的完整结果
2. 最佳组合的详细分析
3. 写入日志文件
4. summary 中列出最佳交叉组合的指标
"""

    t9_id = kanban_create(f"Iter{ITER} T9: 组合交叉验证", "analyst", t9_body,
                          parents=ANALYST_IDS, max_runtime=10800)
    if not t9_id:
        log("FATAL: Failed to create T9. Exiting.")
        sys.exit(1)

    # ============================================================
    # PHASE 3: Wait for T9
    # ============================================================
    log(f"\n{'─'*60}")
    log(f"Phase 3: Waiting for T9 ({t9_id})...")
    
    if not wait_for_tasks([t9_id], timeout=10800, poll_interval=60):
        log("ERROR: T9 did not complete within 3 hours. Exiting.")
        sys.exit(1)
    
    log("Phase 3 complete! T9 done.")

    # ============================================================
    # PHASE 4: Create T10 — Convergence
    # ============================================================
    log(f"\n{'─'*60}")
    log(f"Phase 4: Creating T10 — 主控收敛+状态更新")

    t10_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{SYSTEM_TIME}
- 本轮迭代编号：{ITER}
- 所有 7 个 analyst + T9 交叉验证已完成

## 任务：主控收敛 + 状态更新

### 你的角色
你扮演 主控收敛分析师。你的任务是读取 T2-T9 所有输出，计算本轮最佳策略，更新 state.json 和 knowledge_base.md。

### 文件引用
- 循环规则：`./skills/mining-rules.md`
- 知识库：`./state/knowledge_base.md`
- 当前状态：`./state/state.json`
- 日志目录：`./logs/iter_{ITER}/`

### 执行步骤
1. 读取 T2-T9 所有输出（位于 `./logs/iter_{ITER}/`）
2. 汇总所有 analyst 的最佳发现
3. 对比历史最佳（state.json 中的 best_metrics）
4. 更新 state.json：
   - current_iteration = {ITER}
   - 如果本轮最佳超越历史最佳 → 更新 best_metrics, fatigue_count = 0
   - 否则 → fatigue_count += 1
   - 将本轮所有参数 hash 加入 recent_combos
   - 将本轮摘要加入 history（保持最多 50 条）
5. 更新 knowledge_base.md：追加有效发现
6. 写入收敛摘要到：`{STRATEGY_DIR}/logs/iter_{ITER}/analysis_T10_收敛.md`

### 更新逻辑
- 如果 fatigue_count >= 10 → 在报告中说"连续10轮未破纪录，建议调整方向"
- 如果 fatigue_count >= 20 → 建议暂停并审查

### 输出
1. 收敛摘要（含排名、对比历史最佳、疲劳计数）
2. 更新后的 state.json 内容
3. 写入日志文件
4. summary 中列出本轮最佳策略和历史最佳对比
"""

    t10_id = kanban_create(f"Iter{ITER} T10: 主控收敛+状态更新", "analyst", t10_body,
                           parents=[t9_id], max_runtime=3600)
    if not t10_id:
        log("FATAL: Failed to create T10. Exiting.")
        sys.exit(1)

    # ============================================================
    # PHASE 5: Wait for T10
    # ============================================================
    log(f"\n{'─'*60}")
    log(f"Phase 5: Waiting for T10 ({t10_id})...")
    
    if not wait_for_tasks([t10_id], timeout=7200, poll_interval=60):
        log("ERROR: T10 did not complete within 2 hours. Exiting.")
        sys.exit(1)
    
    log("Phase 5 complete! T10 done.")

    # ============================================================
    # PHASE 6: Create T11 — Report
    # ============================================================
    log(f"\n{'─'*60}")
    log(f"Phase 6: Creating T11 — 策略挖掘报告")

    t11_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{SYSTEM_TIME}
- 本轮迭代编号：{ITER}

## 任务：策略挖掘报告生成

### 你的角色
你扮演 报告生成 Writer。你的任务是读取 T10 收敛结果 + state.json + knowledge_base.md，生成格式化报告。

### 文件引用
- 当前状态：`./state/state.json`
- 知识库：`./state/knowledge_base.md`
- 收敛结果：`{STRATEGY_DIR}/logs/iter_{ITER}/analysis_T10_收敛.md`

### 执行步骤
1. 读取 state.json、knowledge_base.md、T10 收敛结果
2. 生成 Markdown 报告
3. 报告必须包含：
   - Top 5 策略排名（按综合 Score 排序）
   - 各流派表现对比
   - 关键发现和突破
   - 下轮建议
4. 保存到：`{STRATEGY_DIR}/reports/mining-all167-iter{ITER}-{datetime.datetime.now().strftime("%Y%m%d-%H%M")}.md`
5. 在 summary 中列出报告文件名和关键数据

### 报告格式要求
- 清晰的中文 Markdown
- 每个策略带完整指标（WR, R5, R10, R20, N, Sharpe）
- 包含 SQL 查询片段（可复现）
- 标注 🏆 最佳 / ✅ 达标 / ⚠️ 接近 / ❌ 无效
"""

    t11_id = kanban_create(f"Iter{ITER} T11: 策略挖掘报告", "writer", t11_body,
                           parents=[t10_id], max_runtime=600)
    if not t11_id:
        log("FATAL: Failed to create T11. Exiting.")
        sys.exit(1)

    # ============================================================
    # PHASE 7: Wait for T11 and finalize
    # ============================================================
    log(f"\n{'─'*60}")
    log(f"Phase 7: Waiting for T11 ({t11_id})...")
    
    if not wait_for_tasks([t11_id], timeout=1800, poll_interval=30):
        log("WARN: T11 did not complete within 30 minutes. Report may be missing.")
    else:
        log("Phase 7 complete! All tasks done.")

    # Final summary
    log(f"\n{'═'*60}")
    log(f"Iter{ITER} Pipeline complete!")
    log(f"All task IDs:")
    log(f"  T1:  {T1_ID}")
    for tid in ANALYST_IDS:
        log(f"  {ANALYST_NAMES[tid]}: {tid}")
    log(f"  T9:  {t9_id}")
    log(f"  T10: {t10_id}")
    log(f"  T11: {t11_id}")
    log(f"Logs: {STRATEGY_DIR}/logs/iter_{ITER}/")
    log(f"Report: {STRATEGY_DIR}/reports/")
    log(f"{'═'*60}")


if __name__ == "__main__":
    main()
