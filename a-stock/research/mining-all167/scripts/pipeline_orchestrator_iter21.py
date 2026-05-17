#!/usr/bin/env python3
"""
Iter21 Background Poller — Fix C pattern for Cron orchestrators.
Waits for T2-T8 (analysts) to complete, then creates T9→T10→T11 sequentially.

Usage: nohup python3 scripts/pipeline_orchestrator_iter21.py &
PID safety: This script checks pgrep before running; only one instance.
"""

import sqlite3, time, subprocess, json, datetime, os, sys, hashlib, re

# ── Configuration ──
DB_PATH = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
LOG_DIR = f"{STRATEGY_DIR}/logs/iter_21"
REPORT_DIR = f"{STRATEGY_DIR}/reports"
STATE_PATH = f"{STRATEGY_DIR}/state/state.json"
KNOWLEDGE_BASE = f"{STRATEGY_DIR}/state/knowledge_base.md"
SKILL_PARAM = f"{STRATEGY_DIR}/skills/param-space.md"
SKILL_RULES = f"{STRATEGY_DIR}/skills/mining-rules.md"

# The orchestrator just created these in the main session
T1_ID = "t_e1c0237e"
ANALYST_IDS = {
    "T2": "t_fc14be12",  # 动量趋势
    "T3": "t_cd490d36",  # 反转低吸
    "T4": "t_c9c7b179",  # 资金流
    "T5": "t_2188aa3a",  # 基本面估值
    "T6": "t_d81e1288",  # 板块轮动
    "T7": "t_e06def2e",  # 跨市场联动
    "T8": "t_8143bac9",  # 量价形态
}
ALL_ANALYST_IDS = list(ANALYST_IDS.values())

ITER_N = 21
NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(f"{STRATEGY_DIR}/logs/poller_iter21.log", "a") as f:
        f.write(line + "\n")

def kanban_create(title, assignee, body, parents=None, max_runtime=600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            log(f"ERROR kanban_create: {result.stderr[:300]}")
            return None
        data = json.loads(result.stdout)
        tid = data.get("id")
        if tid:
            log(f"✅ Created {title[:50]} -> {tid}")
        return tid
    except Exception as e:
        log(f"EXCEPTION kanban_create: {e}")
        return None

def wait_for_tasks(tids, timeout=14400, poll_interval=60):
    """Poll kanban.db until all tasks are done, with timeout."""
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            log(f"TIMEOUT after {elapsed:.0f}s waiting for tasks: {tids}")
            return False
        
        conn = sqlite3.connect(DB_PATH)
        try:
            statuses = {}
            for t in tids:
                row = conn.execute("SELECT status FROM tasks WHERE id=?", (t,)).fetchone()
                statuses[t] = row[0] if row else "UNKNOWN"
            done = all(s == 'done' for s in statuses.values())
            running = [f"{tid}={s}" for tid, s in statuses.items() if s not in ['done']]
            log(f"Waiting: {len(running)} tasks remaining (elapsed={elapsed:.0f}s)")
            if done:
                return True
        finally:
            conn.close()
        
        time.sleep(poll_interval)

def get_task_body(task_id):
    """Get task body from DB for diagnostic purposes."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT title, status FROM tasks WHERE id=?", (task_id,)).fetchone()
        return f"{row[0]} ({row[1]})" if row else "UNKNOWN"
    finally:
        conn.close()

def check_iter21_logs():
    """Check which analyst output files exist."""
    if not os.path.isdir(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)
        return set()
    files = set(os.listdir(LOG_DIR))
    # Filter out non-analysis files
    analysis = [f for f in files if f.startswith("analysis_T")]
    log(f"Iter21 log files (analysis_*): {sorted(analysis)}")
    return files

def load_state():
    with open(STATE_PATH) as f:
        return json.loads(f.read())

# ── PID Safety ──
script_name = os.path.basename(__file__)
result = subprocess.run(["pgrep", "-f", script_name], capture_output=True, text=True)
pids = [p for p in result.stdout.strip().split('\n') if p and p != str(os.getpid())]
if len(pids) > 1:
    log(f"WARNING: Found {len(pids)} other instances of {script_name}: {pids}")
    log("Exiting to avoid duplicate.")
    sys.exit(0)

# Also check for any pipeline_orchestrator script with iter21
result = subprocess.run(["pgrep", "-f", "pipeline_orchestrator_iter21"], capture_output=True, text=True)
pids = [p for p in result.stdout.strip().split('\n') if p and p != str(os.getpid())]
if pids:
    log(f"WARNING: Found {len(pids)} other iter21 poller instances: {pids}")
    log("Exiting to avoid duplicate.")
    sys.exit(0)

log(f"=== Iter21 Background Poller Started ===")
log(f"Strategy: {STRATEGY_DIR}")
log(f"Analyst tasks: {ANALYST_IDS}")
log(f"System time: {NOW} UTC+8")

# ── Phase 1: Wait for T1 (data check) ──
log("Phase 0: Waiting for T1 (data check)...")
if not wait_for_tasks([T1_ID], timeout=1800, poll_interval=30):
    log("T1 did not complete in time. Exiting.")
    sys.exit(1)
log("T1 completed!")

# Wait a bit for T1's output file to be written
time.sleep(30)

# ── Phase 2: Wait for T2-T8 (all analysts) ──
log("\n=== Phase 1: Waiting for all analysts (T2-T8) ===")
if not wait_for_tasks(ALL_ANALYST_IDS, timeout=28800, poll_interval=60):
    log("Analyst tasks did not complete in time. Exiting.")
    sys.exit(1)
log("All analysts completed!")

# Wait for output files to be flushed
time.sleep(30)

# ── Phase 3: Create T9 (Cross-validation) ──
log("\n=== Phase 2: Creating T9 (组合交叉验证) ===")

# Check what analysis files exist
existing_logs = check_iter21_logs()
analyst_files = [f for f in existing_logs if f.startswith("analysis_T")]
log(f"Found {len(analyst_files)} analyst output files: {analyst_files}")

state = load_state()
best_r5 = state.get("best_metrics", {}).get("ret_5d", "N/A")
best_wr = state.get("best_metrics", {}).get("win_rate_5d", "N/A")
best_sharpe = state.get("best_metrics", {}).get("sharpe_5d", "N/A")
best_sig = state.get("best_metrics", {}).get("signal_count", "N/A")
fatigue = state.get("fatigue_count", 0)

# Recent combos top 10 for reference
recent_combos = state.get("recent_combos", [])[:10]
combos_str = "\n".join([f"- {c}" for c in recent_combos])

t9_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{NOW} UTC+8
- 本轮迭代编号：{ITER_N}
- 历史最佳：WR={best_wr}%, R5={best_r5}%, Sharpe={best_sharpe}, N={best_sig}
- 疲劳计数：{fatigue}/10
- 工作目录：{STRATEGY_DIR}

### 已知已验证的 combos（前10个，去重参考）
{combos_str}

## 任务：组合交叉验证（Iter {ITER_N}）

### 目标
读取 T2-T8 全部 7 个流派的输出文件（位于 logs/iter_{ITER_N}/），提取每个流派的最佳发现，做跨流派的 5D*5D 因子交叉组合测试。

### 执行步骤

#### 第1步：读取所有 analyst 输出
读取以下文件（在 logs/iter_{ITER_N}/ 目录中）：
- analysis_T2_动量趋势.md
- analysis_T3_反转低吸.md
- analysis_T4_资金流.md
- analysis_T5_基本面估值.md
- analysis_T6_板块轮动.md
- analysis_T7_跨市场联动.md
- analysis_T8_量价形态.md

如果某个文件不存在，等待 30 秒后重试，最多 3 次。

#### 第2步：提取每个流派的最佳因子
从每个流派中提取胜率 > 52% 且 5D收益 > 3% 的因子对。

#### 第3步：跨流派组合
从至少 2 个不同流派的最佳因子中各取一个，组合为新的策略条件：
- 至少测试 10 组跨流派组合
- 每组使用 query_sql MCP 做全历史回测
- 记录 hash 避免与 recent_combos 中已有组合重复
- 示例：T2(持续放量) × T4(超大单资金流入)

#### 第4步：输出
写入到：
{STRATEGY_DIR}/logs/iter_{ITER_N}/analysis_T9_组合交叉.md

格式要求：
```markdown
# 组合交叉验证 (Iter {ITER_N})

## 流派最佳发现汇总
| 流派 | 最佳组合 | WR | 5D收益 | 信号数 | 
|------|----------|-----|--------|--------|
| T2 | ... | ... | ... | ... |
| ... (7 rows) |

## 跨流派组合结果 (10+组)
| 编号 | 组合来源 | 参数 | 信号数 | 5D收益 | WR | 夏普 | 
|------|----------|------|--------|--------|-----|------|
| X01 | T2×T4 | ... | ... | ... | ... | ... |
| ... (10+ rows) |

## 是否超越历史最佳
- 当前最佳：WR={best_wr}%, R5={best_r5}%, Sharpe={best_sharpe}
- 本轮最优跨流派：WR=XX%, R5=XX%, Sharpe=XX
- 结论：是/否

## 推荐策略 (Top 3)
1. ...
2. ...
3. ...
```

#### 数据规则
- 主板过滤
- FINAL 去重
- YYYYMMDD 格式
- 成功标准：WR ≥ 55% AND 5D ≥ 5% AND 信号数 ≥ 200
- 使用 query_sql MCP 工具，不要直连 ClickHouse HTTP
- 先查 SELECT max(trade_date) 确认数据基准"""

t9_id = kanban_create(
    f"Iter{ITER_N} T9: 组合交叉验证",
    "analyst",
    t9_body,
    parents=ALL_ANALYST_IDS,
    max_runtime=10800
)

if not t9_id:
    log("FATAL: Failed to create T9")
    sys.exit(1)

# ── Phase 4: Wait for T9 ──
log("\n=== Phase 3: Waiting for T9 (cross-validation) ===")
if not wait_for_tasks([t9_id], timeout=14400, poll_interval=60):
    log("T9 did not complete in time. Exiting.")
    sys.exit(1)
log("T9 completed!")
time.sleep(30)

# ── Phase 5: Create T10 (Convergence) ──
log("\n=== Phase 4: Creating T10 (主控收敛+状态更新) ===")

t10_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{NOW} UTC+8
- 本轮迭代编号：{ITER_N}
- 历史最佳：WR={best_wr}%, R5={best_r5}%, Sharpe={best_sharpe}, N={best_sig}
- 疲劳计数：{fatigue}/10
- 工作目录：{STRATEGY_DIR}

## 任务：主控收敛 + 状态更新（Iter {ITER_N}）

### 目标
读取 T2-T9 所有输出，更新 state.json、knowledge_base.md，输出收敛摘要。

### 执行步骤

#### 第1步：读取所有输出
读取 logs/iter_{ITER_N}/ 目录下的所有 analysis_*.md 文件：
- T2-T8: 各流派最佳发现
- T9: 跨流派组合最佳

#### 第2步：更新 state.json
使用 Python 更新 {STATE_PATH}：

更新逻辑：
1. 比较本轮所有发现 vs state.json 中的 best_metrics
2. 如果本轮有 R5 > {best_r5}% 且 WR ≥ 55% 且 信号数 ≥ 200 的策略 → 更新 best_metrics，fatigue_count = 0
3. 否则 → fatigue_count = {fatigue} + 1
4. 将本轮所有参数组合的 hash 加入 recent_combos（去重，保留最近 50 个）
5. 将本轮摘要加入 history（保留最多 50 条）

#### 第3步：更新 knowledge_base.md
将有效发现追加到 {KNOWLEDGE_BASE}：
```markdown
## {NOW.split(' ')[0]} (iter {ITER_N}) - [流派名]
- **参数**: key1=value1, key2=value2, ...
- **指标**: 5D收益=X%%, WR=X%%, 信号数=XXX, 夏普=X.XX
- **SQL**: （关键查询片段）
- **结论**: 一句话总结
- **状态**: ✅ 有效 / ❌ 无效
```

#### 第4步：输出收敛摘要
写入到：
{STRATEGY_DIR}/logs/iter_{ITER_N}/analysis_T10_收敛.md

包含：
- 本轮最佳策略
- 是否超越历史最佳
- 各流派表现排名
- fatigue_count 状态
- 下轮建议（如果 fatigue ≥ 10 则建议调整方向）

### 数据规则
- None 值用 0 或 N/A 处理
- 禁止使用推测日期
- T10 更新 state.json 后，T11 Writer 才能生成最终报告"""

t10_id = kanban_create(
    f"Iter{ITER_N} T10: 主控收敛+状态更新",
    "analyst",
    t10_body,
    parents=[t9_id],
    max_runtime=3600
)

if not t10_id:
    log("FATAL: Failed to create T10")
    sys.exit(1)

# ── Phase 6: Wait for T10 ──
log("\n=== Phase 5: Waiting for T10 (convergence) ===")
if not wait_for_tasks([t10_id], timeout=7200, poll_interval=60):
    log("T10 did not complete in time. Exiting.")
    sys.exit(1)
log("T10 completed!")
time.sleep(30)

# ── Phase 7: Create T11 (Report) ──
log("\n=== Phase 6: Creating T11 (策略挖掘报告) ===")

t11_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8
- 本轮迭代编号：{ITER_N}
- 工作目录：{STRATEGY_DIR}

## 任务：策略挖掘报告（Iter {ITER_N}）

### 目标
读取 T10 收敛结果 + state.json + knowledge_base.md，生成格式化报告。

### 执行步骤

#### 第1步：读取源文件
1. 读取 {STATE_PATH} — 获取最新状态
2. 读取 {KNOWLEDGE_BASE} — 获取历史有效发现
3. 读取 {STRATEGY_DIR}/logs/iter_{ITER_N}/analysis_T10_收敛.md — 本轮收敛结果

#### 第2步：生成报告
写入到：
{STRATEGY_DIR}/reports/mining-all167-iter{ITER_N}-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}.md

报告大纲：
```markdown
# 策略挖掘报告 — Iter {ITER_N} ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8)

## 1. 本轮概况
- 迭代编号：{ITER_N}
- 测试流派：7个（动量趋势/反转低吸/资金流/基本面估值/板块轮动/跨市场联动/量价形态）
- 疲劳计数：X/10
- 历史最佳 R5：X%
- 历史最佳 WR：X%

## 2. Top 5 策略排名
| 排名 | 来源 | 参数 | 信号数 | 5D收益 | WR | 夏普 |
|------|------|------|--------|--------|-----|------|
| 1 | ... | ... | ... | ... | ... | ... |
| ... (5 rows) |

## 3. 各流派表现对比
| 流派 | 最佳组合 | WR | 5D收益 | 信号数 |
|------|----------|-----|--------|--------|

## 4. 跨流派组合表现
| 组合 | 来源 | WR | 5D收益 | 信号数 |

## 5. 关键发现
- ...
- ...

## 6. 下轮建议
- fatigue_count = X/10
- 建议：...
```

#### 第3步：报告要求
- 报告日期必须从 T10 收敛结果中读取，禁止自行推测
- 保持简洁，突出重点
- 成功标准：WR ≥ 55% AND 5D ≥ 5% AND 信号数 ≥ 200

### 建议
如果 fatigue_count ≥ 10，在报告中强烈建议调整挖掘方向。"""

t11_id = kanban_create(
    f"Iter{ITER_N} T11: 策略挖掘报告",
    "writer",
    t11_body,
    parents=[t10_id],
    max_runtime=600
)

if not t11_id:
    log("FATAL: Failed to create T11")
    sys.exit(1)

log(f"\n=== Iter{ITER_N} Pipeline Complete ===")
log(f"All 11 tasks created with proper dependency chains:")
log(f"  T1: {T1_ID}")
for label, tid in ANALYST_IDS.items():
    log(f"  {label}: {tid}")
log(f"  T9: {t9_id}")
log(f"  T10: {t10_id}")
log(f"  T11: {t11_id}")
log(f"Dependencies: T1→T2-T8→T9→T10→T11")
log(f"The dispatcher will automatically promote tasks as dependencies complete.")
log(f"Poller will now exit. T9-T11 creation was already done above.")
log(f"=== End Iter{ITER_N} Poller ===")
