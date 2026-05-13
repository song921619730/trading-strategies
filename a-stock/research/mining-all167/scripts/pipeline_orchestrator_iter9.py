#!/usr/bin/env python3
"""
Kanban Pipeline Orchestrator for iter 9 mining-all167.
Monitors T2-T8 completion, then creates T9→T10→T11 sequentially.
Designed to run as a long-lived background process.
"""
import subprocess, json, time, os, sys, sqlite3

ITER = 9
WORKDIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
SYSTEM_TIME = "2026-05-12 09:59 UTC+8"
DB_PATH = "/home/gjtmux/.hermes/profiles/reze/kanban.db"

# Reusable kanban_create function
def kanban_create(title, assignee, body, parents=None, max_runtime=600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr[:300]}")
        return None
    try:
        data = json.loads(result.stdout)
        tid = data.get("id")
        print(f"  ✅ {tid} | {title} | {assignee}")
        return tid
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Raw: {result.stdout[:200]}")
        return None

# Load task IDs
with open(f"{WORKDIR}/state/task_ids_iter{ITER}.json") as f:
    tids = json.load(f)["task_ids"]

analyst_ids = [tids[f"T{n}"] for n in range(2, 9)]

def wait_for_tasks(task_ids, timeout=7200, poll_interval=60, label="tasks"):
    """Wait until all task_ids have status='done'."""
    start = time.time()
    while time.time() - start < timeout:
        conn = sqlite3.connect(DB_PATH)
        statuses = {}
        for tid in task_ids:
            row = conn.execute('SELECT status, spawn_failures FROM tasks WHERE id=?', (tid,)).fetchone()
            statuses[tid] = (row[0], row[1]) if row else ("unknown", 0)
        conn.close()

        done = all(v[0] == "done" for v in statuses.values())
        failed = any(v[1] > 3 for v in statuses.values())

        elapsed = time.time() - start
        running = sum(1 for v in statuses.values() if v[0] == "running")
        todo = sum(1 for v in statuses.values() if v[0] == "todo")
        ready = sum(1 for v in statuses.values() if v[0] == "ready")

        if done:
            print(f"[{elapsed:.0f}s] ✅ All {label} done!")
            return True
        if failed:
            print(f"[{elapsed:.0f}s] ❌ Some {label} have failures!")
            # Don't abort, keep waiting
        if elapsed % 300 < poll_interval:  # Every ~5 min
            print(f"[{elapsed:.0f}s] {label}: done={sum(1 for v in statuses.values() if v[0]=='done')}, "
                  f"running={running}, ready={ready}, todo={todo}")

        time.sleep(poll_interval)

    print(f"❌ Timeout after {timeout}s waiting for {label}")
    return False

def get_task_id(name):
    return tids.get(name)

print("=" * 60)
print(f"Kanban Pipeline Orchestrator — iter {ITER}")
print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# ================================================================
# PHASE 2: Wait for T2-T8, then create T9
# ================================================================
print(f"\n[Phase 2] T1 ID: {tids['T1']}")
print(f"[Phase 2] T2-T8 IDs: {analyst_ids}")
print(f"[Phase 2] Waiting for T1 to complete (so T2-T8 can start)...")

# First wait for T1
wait_for_tasks([tids["T1"]], timeout=600, poll_interval=30, label="T1 data check")
print("T1 done! T2-T8 should auto-promote to ready.")

# Wait for all analysts (T2-T8)
print("\n[Phase 2] Waiting for T2-T8 to all complete...")
if not wait_for_tasks(analyst_ids, timeout=7200, poll_interval=120, label="T2-T8 analysts"):
    print("T2-T8 not all done within timeout. Creating T9 anyway with whatever is available.")
    # Still attempt T9 with partial data

# ================================================================
# PHASE 3: Create T9 (Cross-validation)
# ================================================================
print("\n" + "=" * 60)
print("PHASE 3: Creating T9 — 组合交叉验证")
print("=" * 60)

T9_BODY = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{SYSTEM_TIME}
- 本轮迭代编号：{ITER}
- 历史最佳：R5=25.76%(T9-X17 锤子线×SPX上涨), WR=74.9%, Sharpe=0.68
- 疲劳计数：{FATIGUE_COUNT}

## 任务：T9 组合派交叉验证

你的核心工作原则请参考：./skills/analyst-soul.md（如果存在）。
如果父级输出文件不存在，等待30秒后重试，最多3次，不要报错退出。

参考文件：
- ./skills/param-space.md
- ./skills/mining-rules.md
- ./state/knowledge_base.md

### 步骤
1. 读取 T2-T8 所有输出文件：{WORKDIR}/logs/iter_{ITER}/analysis_T2_*.md, T3_*, ..., T8_*
2. 从每个流派的最佳发现中提取关键因子
3. 做跨流派交叉组合测试（至少 10 组）
4. 使用 query_sql MCP 工具回测每组组合
5. 对比历史最佳（R5=25.76%, WR=74.9%）

### 关键数据规则
- cyq_chips 偶发404 → 重试
- basic_eps_yoy 不可用 → 用 tr_yoy/netprofit_yoy
- net_mf 不存在 → 用 net_mf_amount
- 所有查询加 FINAL, 日期格式 YYYYMMDD
- 主板过滤

### 输出
写入绝对路径：{WORKDIR}/logs/iter_{ITER}/analysis_T9_组合交叉.md
包含：每组交叉组合的参数、SQL、指标、是否突破历史最佳

### 成功标准
WR ≥ 52% AND 5D收益 ≥ 3% AND 信号数 ≥ 200
"""

t9 = kanban_create(
    title=f"T9: 组合交叉验证 (iter {ITER})",
    assignee="analyst",
    body=T9_BODY,
    max_runtime=3600,
)

if t9:
    tids["T9"] = t9
    print(f"\nT9 created: {t9}")
else:
    print("❌ Failed to create T9")
    sys.exit(1)

# ================================================================
# PHASE 4: Wait for T9, then create T10
# ================================================================
print(f"\n[Phase 4] Waiting for T9 to complete...")
if not wait_for_tasks([t9], timeout=7200, poll_interval=120, label="T9 cross-validation"):
    print("T9 timeout. Creating T10 anyway.")

print("\n" + "=" * 60)
print("PHASE 4: Creating T10 — 主控收敛")
print("=" * 60)

T10_BODY = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{SYSTEM_TIME}
- 本轮迭代编号：{ITER}

## 任务：T10 主控收敛

你的核心工作原则请参考：./skills/analyst-soul.md（如果存在）。
如果父级输出文件不存在，等待30秒后重试，最多3次，不要报错退出。

### 步骤
1. 读取 T2-T9 所有输出（{WORKDIR}/logs/iter_{ITER}/）
2. 读取当前 state.json: {WORKDIR}/state/state.json
3. 读取 knowledge_base.md: {WORKDIR}/state/knowledge_base.md
4. 使用 Python 更新 state.json：
   - 如果本轮有超过历史最佳的策略 → 更新 best_metrics, fatigue_count=0
   - 否则 fatigue_count+=1（当前={FATIGUE_COUNT}）
   - 添加本轮所有组合 hash 到 recent_combos
   - 添加本轮摘要到 history（保持最多50条）
5. 追加有效发现到 knowledge_base.md
   - 格式：## YYYY-MM-DD (iter N) - 流派名
   - 参数 / 指标 / SQL / 结论 / 状态

### 输出
写入：{WORKDIR}/logs/iter_{ITER}/analysis_T10_收敛.md
更新：{WORKDIR}/state/state.json（请写入完整JSON，不要只写部分字段）
更新：{WORKDIR}/state/knowledge_base.md
"""

t10 = kanban_create(
    title=f"T10: 主控收敛 (iter {ITER})",
    assignee="analyst",
    body=T10_BODY,
    max_runtime=1800,
)

if t10:
    tids["T10"] = t10
    print(f"\nT10 created: {t10}")
else:
    print("❌ Failed to create T10")
    sys.exit(1)

# ================================================================
# PHASE 5: Wait for T10, then create T11
# ================================================================
print(f"\n[Phase 5] Waiting for T10 to complete...")
if not wait_for_tasks([t10], timeout=3600, poll_interval=120, label="T10 convergence"):
    print("T10 timeout. Creating T11 anyway.")

print("\n" + "=" * 60)
print("PHASE 5: Creating T11 — 报告生成")
print("=" * 60)

import datetime
now = datetime.datetime.now()
report_time = now.strftime("%Y%m%d-%H%M")

T11_BODY = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{SYSTEM_TIME}
- 本轮迭代编号：{ITER}

## 任务：T11 报告生成

你的核心工作原则请参考：./skills/writer-soul.md（如果存在）。
如果父级输出文件不存在，等待30秒后重试，最多3次，不要报错退出。

### 步骤
1. 读取 T10 收敛结果：{WORKDIR}/logs/iter_{ITER}/analysis_T10_收敛.md
2. 读取最终 state.json：{WORKDIR}/state/state.json
3. 读取 knowledge_base.md 最新发现：{WORKDIR}/state/knowledge_base.md
4. 生成格式化报告

### 报告大纲
1. 本轮挖掘概要（iteration, 时间, 流派数）
2. Top 5 策略排名（R5降序，含WR/R5/R10/R20/Sharpe/信号数）
3. 各流派表现对比（表格）
4. 本轮关键发现（3-5个要点）
5. 与历史最佳对比（R5=25.76%, WR=74.9%, Sharpe=0.68）
6. 疲劳状态分析（当前={FATIGUE_COUNT}轮）
7. 下轮建议

### 格式要求
- 使用 Markdown 表格
- 所有指标包含单位和方向
- 代码和名称一起给出
- 报告日期使用 YYYY-MM-DD 格式

### 输出
写入绝对路径：{WORKDIR}/reports/mining-all167-iter{ITER}-{report_time}.md
"""

t11 = kanban_create(
    title=f"T11: 报告生成 (iter {ITER})",
    assignee="writer",
    body=T11_BODY,
    max_runtime=600,
)

if t11:
    tids["T11"] = t11
    print(f"\nT11 created: {t11}")

# Save final task IDs
tids["completed_at"] = time.strftime('%Y-%m-%d %H:%M:%S')
with open(f"{WORKDIR}/state/task_ids_iter{ITER}.json", "w") as f:
    json.dump({"iteration": ITER, "task_ids": tids, "updated_at": tids["completed_at"]}, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 60)
print(f"PIPELINE COMPLETE! All tasks created.")
print(f"Task chain: T1→[T2-T8]→T9→T10→T11")
done_tasks = [k for k, v in tids.items() if k.startswith("T") and v]
print(f"Tasks: {', '.join(done_tasks)}")
print("=" * 60)
