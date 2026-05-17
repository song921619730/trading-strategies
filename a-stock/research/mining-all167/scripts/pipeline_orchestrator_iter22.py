#!/usr/bin/env python3
"""
Iter22 Background Poller — Waits for T2-T8 analysts to complete,
then creates T9→T10→T11 sequentially.
Usage: nohup python3 scripts/pipeline_orchestrator_iter22.py &
PID safety: checks pgrep before running.
"""

import sqlite3, time, subprocess, json, datetime, os, sys, hashlib, re

# ── Configuration ──
DB_PATH = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
LOG_DIR = f"{STRATEGY_DIR}/logs/iter_22"
REPORT_DIR = f"{STRATEGY_DIR}/reports"
STATE_PATH = f"{STRATEGY_DIR}/state/state.json"
KNOWLEDGE_BASE = f"{STRATEGY_DIR}/state/knowledge_base.md"
SKILL_PARAM = f"{STRATEGY_DIR}/skills/param-space.md"
SKILL_RULES = f"{STRATEGY_DIR}/skills/mining-rules.md"

# T2-T8 task IDs for Iter22 (created by dispatcher)
ANALYST_IDS = {
    "T2": "t_84d77228",  # 动量趋势
    "T3": "t_5320e7b9",  # 反转低吸
    "T4": "t_4ce3f368",  # 资金流
    "T5": "t_10968c3d",  # 基本面估值
    "T6": "t_4dede86c",  # 板块轮动
    "T7": "t_5c61d028",  # 跨市场联动
    "T8": "t_409a3b4f",  # 量价形态
}
ALL_ANALYST_IDS = list(ANALYST_IDS.values())

ITER_N = 22
NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(f"{STRATEGY_DIR}/logs/poller_iter22.log", "a") as f:
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
    """Poll kanban.db until all tasks are done."""
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
            if running:
                log(f"Waiting: {len(running)} tasks remaining (elapsed={elapsed:.0f}s)")
            if done:
                return True
        finally:
            conn.close()
        
        time.sleep(poll_interval)

def check_iter22_logs():
    """Check which analyst output files exist."""
    if not os.path.isdir(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)
        return set()
    files = set(os.listdir(LOG_DIR))
    analysis = [f for f in files if f.startswith("analysis_T")]
    log(f"Iter22 log files (analysis_*): {sorted(analysis)}")
    return files

def load_state():
    with open(STATE_PATH) as f:
        return json.loads(f.read())

# ── PID Safety ──
script_name = os.path.basename(__file__)
result = subprocess.run(["pgrep", "-f", script_name], capture_output=True, text=True)
pids = [p for p in result.stdout.strip().split('\n') if p and p != str(os.getpid())]
if len(pids) > 1:
    log(f"WARNING: Found {len(pids)} other instances: {pids}. Exiting.")
    sys.exit(0)

result = subprocess.run(["pgrep", "-f", "pipeline_orchestrator_iter22"], capture_output=True, text=True)
pids = [p for p in result.stdout.strip().split('\n') if p and p != str(os.getpid())]
if pids:
    log(f"WARNING: Found other iter22 poller instances: {pids}. Exiting.")
    sys.exit(0)

log(f"=== Iter22 Background Poller Started ===")
log(f"Strategy: {STRATEGY_DIR}")
log(f"Analyst tasks: {ANALYST_IDS}")
log(f"System time: {NOW} UTC+8")

# ── Phase 1: Wait for T2-T8 (all analysts) ──
log("\n=== Phase 1: Waiting for all analysts (T2-T8) ===")
if not wait_for_tasks(ALL_ANALYST_IDS, timeout=28800, poll_interval=60):
    log("Analyst tasks did not complete. Exiting.")
    sys.exit(1)
log("All analysts completed!")

# Wait for output files to be flushed
time.sleep(30)

# ── Phase 2: Create T9 (Cross-validation) ──
log("\n=== Phase 2: Creating T9 (组合交叉验证) ===")

existing_logs = check_iter22_logs()
analyst_files = [f for f in existing_logs if f.startswith("analysis_T")]
log(f"Found {len(analyst_files)} analyst output files: {analyst_files}")

state = load_state()
best_r5 = state.get("best_metrics", {}).get("ret_5d", "N/A")
best_wr = state.get("best_metrics", {}).get("win_rate_5d", "N/A")
best_sharpe = state.get("best_metrics", {}).get("sharpe_5d", "N/A")
best_sig = state.get("best_metrics", {}).get("signal_count", "N/A")
fatigue = state.get("fatigue_count", 0)

recent_combos = state.get("recent_combos", [])[:10]
combos_str = "\n".join([f"- {c}" for c in recent_combos])

now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

t9_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{now_ts} UTC+8
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
- 每组使用 ch_query.py sql 做全历史回测
- 记录 hash 避免与 recent_combos 中已有组合重复

#### 第4步：输出
写入到：
{STRATEGY_DIR}/logs/iter_{ITER_N}/analysis_T9_组合交叉.md

格式要求：
| 编号 | 组合来源 | 参数 | 信号数 | 5D收益 | WR | 夏普 |
|------|----------|------|--------|--------|-----|------|
| X01 | T2×T4 | ... | ... | ... | ... | ... |

| 是否超越历史最佳 |
- 当前最佳：WR={best_wr}%, R5={best_r5}%, Sharpe={best_sharpe}
- 本轮最优跨流派：WR=XX%, R5=XX%, Sharpe=XX
- 结论：是/否

#### 数据规则
- 使用 ch_query.py sql 查询，加 FINAL
- 日期格式 YYYYMMDD
- 主板过滤
- 成功标准：WR ≥ 55% AND 5D ≥ 5% AND 信号数 ≥ 200"""

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

# ── Phase 3: Wait for T9 ──
log("\n=== Phase 3: Waiting for T9 (cross-validation) ===")
if not wait_for_tasks([t9_id], timeout=14400, poll_interval=60):
    log("T9 did not complete. Exiting.")
    sys.exit(1)
log("T9 completed!")
time.sleep(30)

# ── Phase 4: Create T10 (Convergence) ──
log("\n=== Phase 4: Creating T10 (主控收敛+状态更新) ===")

now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

t10_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{now_ts} UTC+8
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
6. 设置 current_iteration = {ITER_N}

#### 第3步：更新 knowledge_base.md
将有效发现追加到 {KNOWLEDGE_BASE}

#### 第4步：输出收敛摘要
写入到：
{STRATEGY_DIR}/logs/iter_{ITER_N}/analysis_T10_收敛.md

包含：
- 本轮最佳策略
- 是否超越历史最佳
- 各流派表现排名
- fatigue_count 状态
- 下轮建议（如果 fatigue ≥ 10 则建议调整方向）"""

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

# ── Phase 5: Wait for T10 ──
log("\n=== Phase 5: Waiting for T10 (convergence) ===")
if not wait_for_tasks([t10_id], timeout=7200, poll_interval=60):
    log("T10 did not complete. Exiting.")
    sys.exit(1)
log("T10 completed!")
time.sleep(30)

# ── Phase 6: Create T11 (Report) ──
log("\n=== Phase 6: Creating T11 (策略挖掘报告) ===")

now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
date_str = datetime.datetime.now().strftime("%Y%m%d-%H%M")

t11_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{now_ts} UTC+8
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
{STRATEGY_DIR}/reports/mining-all167-iter{ITER_N}-{date_str}.md

报告大纲：
# 策略挖掘报告 — Iter {ITER_N} ({now_ts} UTC+8)

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

## 3. 各流派表现对比
| 流派 | 最佳组合 | WR | 5D收益 | 信号数 |

## 4. 跨流派组合表现
| 组合 | 来源 | WR | 5D收益 | 信号数 |

## 5. 关键发现

## 6. 下轮建议
- fatigue_count = X/10
- 如果 fatigue ≥ 10 建议调整方向"""

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
log(f"  T1: (already done)")
for label, tid in ANALYST_IDS.items():
    log(f"  {label}: {tid}")
log(f"  T9: {t9_id}")
log(f"  T10: {t10_id}")
log(f"  T11: {t11_id}")
log(f"Dependencies: T1→T2-T8→T9→T10→T11")
log(f"=== End Iter{ITER_N} Poller ===")
sys.exit(0)
