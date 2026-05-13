#!/usr/bin/env python3
"""
Iter15 后台轮询脚本

等待 Iter15 T2-T8 全部完成,然后依次创建 T9→T10→T11。
Dispatcher 会继续运行这些任务。

启动方式：nohup python3 scripts/mining_orchestrator_poller_iter15.py &
"""

import sqlite3
import time
import subprocess
import json
import sys
import os
import hashlib

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
LOG = os.path.join(STRATEGY_DIR, "logs/poller_iter15.log")

ITER = 15
LOG_DIR = os.path.join(STRATEGY_DIR, f"logs/iter_{ITER}")

# ── Task IDs for Iter15 ──
T1_ID = "t_e3cb601c"  # researcher: data freshness

ANALYST_IDS = [
    "t_8c028d2e",  # T2: 动量趋势
    "t_4805b4b1",  # T3: 反转低吸
    "t_9b4f8a3a",  # T4: 资金主力
    "t_64c34bc1",  # T5: 基本面估值
    "t_2dc0eb98",  # T6: 板块轮动
    "t_3b14a08b",  # T7: 跨市场联动
    "t_c3c29e65",  # T8: 量价形态
]

ANALYST_NAMES = {
    "t_8c028d2e": "T2-动量趋势",
    "t_4805b4b1": "T3-反转低吸",
    "t_9b4f8a3a": "T4-资金主力",
    "t_64c34bc1": "T5-基本面估值",
    "t_2dc0eb98": "T6-板块轮动",
    "t_3b14a08b": "T7-跨市场联动",
    "t_c3c29e65": "T8-量价形态",
}


def log_msg(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def wait_for_tasks(tids, poll_interval=60, max_wait_secs=72000):
    """Wait until all task IDs have status='done' or max_wait_secs."""
    waited = 0
    while waited < max_wait_secs:
        conn = sqlite3.connect(DB)
        statuses = {}
        for tid in tids:
            row = conn.execute('SELECT status FROM tasks WHERE id=?', (tid,)).fetchone()
            statuses[tid] = row[0] if row else "unknown"
        conn.close()

        done = all(s == "done" for s in statuses.values())
        if done:
            log_msg(f"All {len(tids)} tasks are done!")
            return True

        # Log every 5 minutes only to avoid log spam
        if waited % 300 == 0:
            status_line = ", ".join([f"{ANALYST_NAMES.get(tid, tid[:12])}={s}" for tid, s in statuses.items()])
            log_msg(f"Waiting... ({waited}s) {status_line}")
        time.sleep(poll_interval)
        waited += poll_interval

    log_msg(f"TIMEOUT after {max_wait_secs}s - tasks not all done")
    return False


def kanban_create(title, assignee, body, parents=None, max_runtime=10800):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log_msg(f"ERROR creating task '{title}': {result.stderr[:300]}")
        log_msg(f"stdout: {result.stdout[:300]}")
        return None
    try:
        data = json.loads(result.stdout)
        tid = data.get("id") or data.get("task_id")
        log_msg(f"Created task {tid}: {title}")
        return tid
    except json.JSONDecodeError as e:
        log_msg(f"JSON parse error for '{title}': {e}")
        log_msg(f"stdout: {result.stdout[:500]}")
        return None


def read_existing_analyst_logs():
    """Read all existing analyst logs from iter_15 directory to summarize findings."""
    log_dir = LOG_DIR
    if not os.path.exists(log_dir):
        log_msg(f"Warning: {log_dir} does not exist yet")
        return []
    
    findings = []
    for fname in sorted(os.listdir(log_dir)):
        if fname.startswith("analysis_T") and fname.endswith(".md"):
            fpath = os.path.join(log_dir, fname)
            try:
                with open(fpath, "r") as f:
                    content = f.read()
                # Extract best discovery summary (first 500 chars)
                findings.append({"file": fname, "content": content[:500], "size": len(content)})
                log_msg(f"Read {fname} ({len(content)} bytes)")
            except Exception as e:
                log_msg(f"Error reading {fname}: {e}")
    return findings


def build_t9_body():
    """Build T9 task body based on current state."""
    sys_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 8*3600)) + " UTC+8"
    
    return f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{sys_time}
- 本轮迭代编号：{ITER}
- 历史最佳：WR=91.86%, R5=19.70%, Sharpe=1.73, N=307 (T2-B1: SPX上涨+T2-C2动量)
- 全局纪录：R5=25.76% (T9-X17: 锤子线×SPX上涨)
- 连续未破纪录轮数：3

## 任务：T9 组合交叉验证

当前目录：{STRATEGY_DIR}

### 步骤

1. 读取 T2-T8 所有输出（位于 {LOG_DIR}/）
2. 从每个流派最佳发现中提取因子做交叉组合（至少 10 组）
3. 每组做 SQL 回测（全量历史数据）

### 交叉规则
- 从不同流派的最佳参数中取不同维度交叉，避免同一流派的冗余维度
- 重点测试：动量因子 × 资金流因子、价量因子 × 基本面因子、板块因子 × 宏观因子
- 结合 SPX 前日上涨过滤（Iter13 发现这一过滤质变量变）
- 每组写入完整 SQL 查询语句

### 输出要求
写入 {LOG_DIR}/analysis_T9_组合交叉.md
每组记录：因子组合、WR_5d、ret_5d、ret_10d、ret_20d、Sharpe、信号数、P10

### 成功标准
WR ≥ 52% AND 5D 收益 ≥ 3% AND 信号数 ≥ 200

### 数据规则
- ClickHouse 查询必须加 FINAL
- 日期格式 YYYYMMDD
- 主板过滤：ts_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'
- net_mf 字段不存在，用 net_mf_amount
- basic_eps_yoy 全空，用 tr_yoy / netprofit_yoy
- 所有 None 值用 0 或 N/A 处理"""


def build_t10_body():
    """Build T10 task body."""
    sys_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 8*3600)) + " UTC+8"
    
    return f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{sys_time}
- 本轮迭代编号：{ITER}
- 历史最佳：WR=91.86%, R5=19.70%, Sharpe=1.73, N=307

## 任务：T10 主控收敛+状态更新

当前目录：{STRATEGY_DIR}

### 要求

1. 读取 T2-T9 所有输出（位于 {LOG_DIR}/）
2. 用 Python 更新 {STRATEGY_DIR}/state/state.json：
   - current_iteration: {ITER}
   - best_metrics: 如果新发现优于当前最佳则更新（WR=91.86%, R5=19.70%, Sharpe=1.73, N=307）
   - fatigue_count: 如果没有新最佳则+1（当前为3）
   - history: 追加本轮最佳发现（保留最近 50 条）
   - recent_combos: 追加本轮新组合（保留最近 50 个）
3. 更新 {STRATEGY_DIR}/state/knowledge_base.md（追加有效发现）
4. 输出收敛摘要到 {LOG_DIR}/analysis_T10_收敛.md

### 更新逻辑
- 如果本轮有超过历史最佳的策略 → 更新 best_metrics，fatigue_count = 0
- 否则 → fatigue_count += 1
- 将本轮所有参数组合的 hash 加入 recent_combos
- 如果 fatigue_count >= 10 → 在报告中建议用户检查方向

### 成功标准
WR ≥ 52% AND 5D 收益 ≥ 3% AND 信号数 ≥ 200"""


def build_t11_body():
    """Build T11 writer body."""
    sys_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 8*3600)) + " UTC+8"
    date_str = time.strftime("%Y%m%d", time.localtime(time.time() + 8*3600))
    
    return f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{sys_time}
- 本轮迭代编号：{ITER}

## 任务：T11 策略挖掘报告

当前目录：{STRATEGY_DIR}

### 要求
读取 {LOG_DIR}/analysis_T10_收敛.md + state/state.json + state/knowledge_base.md

1. 生成格式化报告，保存到 {STRATEGY_DIR}/reports/mining-all167-iter{ITER}-{date_str}.md
2. 报告包含：
   - Top 5 策略排名（按综合评分排序）
   - 各流派表现对比（表格）
   - 本轮回测参数组合汇总
   - 关键发现和 Alpha 逻辑
   - 历史最佳演变趋势
   - 下轮建议（方向、参数优化建议）

### 格式规范
- 使用中文
- 数据表格清晰可读
- 每个策略列出：参数、WR、R5、Sharpe、信号数
- 标注新发现 vs 已有知识库里已有类似策略"""


def main():
    log_msg(f"=== Iter{ITER} Poller started ===")
    log_msg(f"Strategy: {STRATEGY_DIR}")
    
    # Ensure log directory exists
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Create T9 body using the file-based approach: read analyst logs through body
    log_msg("Phase 1: Waiting for T2-T8 analysts to complete...")
    if not wait_for_tasks(ANALYST_IDS):
        log_msg(f"FAILED: T2-T8 did not complete within timeout")
        sys.exit(1)
    
    # Phase 2: Create T9 - 组合交叉验证
    log_msg("Phase 2: Creating T9 - 组合交叉验证")
    t9_body = build_t9_body()
    t9_id = kanban_create(
        f"Iter{ITER} T9: 组合交叉验证",
        "analyst",
        t9_body,
        parents=ANALYST_IDS,
        max_runtime=10800  # 3 hours for complex SQL
    )
    if not t9_id:
        log_msg("FAILED to create T9")
        sys.exit(1)
    
    # Phase 3: Wait for T9
    log_msg("Phase 3: Waiting for T9...")
    if not wait_for_tasks([t9_id]):
        log_msg("FAILED: T9 did not complete within timeout")
        sys.exit(1)
    
    # Phase 4: Create T10 - 主控收敛+状态更新
    log_msg("Phase 4: Creating T10 - 主控收敛+状态更新")
    t10_body = build_t10_body()
    t10_id = kanban_create(
        f"Iter{ITER} T10: 主控收敛+状态更新",
        "analyst",
        t10_body,
        parents=[t9_id],
        max_runtime=10800  # 3 hours for state updates
    )
    if not t10_id:
        log_msg("FAILED to create T10")
        sys.exit(1)
    
    # Phase 5: Wait for T10
    log_msg("Phase 5: Waiting for T10...")
    if not wait_for_tasks([t10_id]):
        log_msg("FAILED: T10 did not complete within timeout")
        sys.exit(1)
    
    # Phase 6: Create T11 - 策略挖掘报告
    log_msg("Phase 6: Creating T11 - 策略挖掘报告")
    t11_body = build_t11_body()
    t11_id = kanban_create(
        f"Iter{ITER} T11: 策略挖掘报告",
        "writer",
        t11_body,
        parents=[t10_id],
        max_runtime=600  # 10 min for text formatting
    )
    if not t11_id:
        log_msg("FAILED to create T11")
        sys.exit(1)
    
    # Phase 7: Wait for T11
    log_msg("Phase 7: Waiting for T11 report...")
    if not wait_for_tasks([t11_id]):
        log_msg("FAILED: T11 did not complete within timeout")
        sys.exit(1)
    
    # Phase 8: Done!
    log_msg(f"=== Iter{ITER} Pipeline Complete! ===")
    log_msg(f"T1={T1_ID}, T2-T8={ANALYST_IDS}, T9={t9_id}, T10={t10_id}, T11={t11_id}")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_msg(f"FATAL: {e}")
        import traceback
        log_msg(traceback.format_exc())
        sys.exit(1)
