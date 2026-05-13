#!/usr/bin/env python3
"""
迭代14 后台轮询脚本

等待 Iter14 T2-T8 全部完成,然后依次创建 T9→T10→T11。
Dispatcher 会继续运行这些任务。
"""

import sqlite3
import time
import subprocess
import json
import sys
import os

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
LOG = os.path.join(STRATEGY_DIR, "logs/poller_iter14.log")

def log_msg(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    line = f"[{ts}] {msg}"
    print(line)
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

        # Log current status
        status_line = ", ".join([f"{tid[:12]}={s}" for tid, s in statuses.items()])
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
        log_msg(f"ERROR creating task '{title}': {result.stderr}")
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

def main():
    log_msg("=== Iter14 Poller started ===")
    
    # Analyst task IDs for Iter14
    analyst_tids = ['t_b303e821','t_ff21631d','t_b400626b','t_2a59d29d','t_62d40717','t_a79dded6','t_a31614c7']

    # Step 1: Wait for T2-T8
    log_msg("Phase 1: Waiting for T2-T8 analysts to complete...")
    if not wait_for_tasks(analyst_tids):
        log_msg("FAILED: T2-T8 did not complete within timeout")
        sys.exit(1)
    
    # Step 2: Create T9 - 组合交叉验证
    log_msg("Phase 2: Creating T9 - 组合交叉验证")
    t9_body = """## 📅 时间上下文（强制遵守）
- 系统执行时间：{sys_time} UTC+8
- 数据基准日期：20260511
- 本轮迭代编号：14
- 历史最佳：WR=91.86%, R5=19.70%, Sharpe=1.73, N=307 (T2-B1: SPX上涨+T2-C2动量)

## 任务：T9 组合交叉验证
读取 T2-T8 所有输出（位于 ./logs/iter_14/）→ 从每个流派最佳发现中提取因子做交叉组合（至少 10 组）
→ 输出到 ./logs/iter_14/analysis_T9_组合交叉.md

### 数据规则
- ClickHouse 查询必须加 FINAL
- 日期格式 YYYYMMDD
- 主板过滤：ts_code NOT LIKE '30%%' AND NOT LIKE '688%%' AND NOT LIKE '920%%' AND NOT LIKE '%%ST%%'
- net_mf_amount 不是 net_mf
- tr_yoy / netprofit_yoy 代替 basic_eps_yoy
- cyq_chips 可用但偶发 404，需重试

### 输出要求
- 至少 10 组交叉组合回测
- 每组记录：因子组合、WR、R5、Sharpe、信号数、P10
- 成功标准：WR ≥ 52%% AND 5D 收益 ≥ 3%% AND 信号数 ≥ 200""".replace("{sys_time}", time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 8*3600)))
    
    t9_id = kanban_create("Iter14 T9: 组合交叉验证", "analyst", t9_body, parents=analyst_tids, max_runtime=10800)
    if not t9_id:
        log_msg("FAILED to create T9")
        sys.exit(1)
    
    # Step 3: Wait for T9
    log_msg("Phase 3: Waiting for T9...")
    if not wait_for_tasks([t9_id]):
        log_msg("FAILED: T9 did not complete within timeout")
        sys.exit(1)
    
    # Step 4: Create T10 - 主控收敛+状态更新
    log_msg("Phase 4: Creating T10 - 主控收敛+状态更新")
    t10_body = """## 📅 时间上下文（强制遵守）
- 系统执行时间：{sys_time} UTC+8
- 数据基准日期：20260511
- 本轮迭代编号：14

## 任务：T10 主控收敛+状态更新
读取 T2-T9 所有输出 → 更新 state.json 和 knowledge_base.md

### 要求
1. 用 Python 更新 ./state/state.json：
   - current_iteration: 14（当前为13）
   - best_metrics: 如果新发现优于当前最佳则更新
   - fatigue_count: 如果没有新最佳则+1
   - history: 追加本轮最佳发现
   - recent_combos: 追加本轮新组合（保留最近 50 个）
2. 更新 ./state/knowledge_base.md（追加有效发现）
3. 输出收敛摘要到 ./logs/iter_14/analysis_T10_收敛.md

### 成功标准
WR ≥ 52%% AND 5D 收益 ≥ 3%% AND 信号数 ≥ 200""".replace("{sys_time}", time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 8*3600)))
    
    t10_id = kanban_create("Iter14 T10: 主控收敛+状态更新", "analyst", t10_body, parents=[t9_id], max_runtime=7200)
    if not t10_id:
        log_msg("FAILED to create T10")
        sys.exit(1)
    
    # Step 5: Wait for T10
    log_msg("Phase 5: Waiting for T10...")
    if not wait_for_tasks([t10_id]):
        log_msg("FAILED: T10 did not complete within timeout")
        sys.exit(1)
    
    # Step 6: Create T11 - 报告生成
    log_msg("Phase 6: Creating T11 - 策略挖掘报告")
    t11_body = """## 📅 时间上下文（强制遵守）
- 系统执行时间：{sys_time} UTC+8
- 数据基准日期：20260511
- 本轮迭代编号：14

## 任务：T11 策略挖掘报告
读取 T10 收敛结果 + state.json + knowledge_base

### 要求
1. 生成格式化报告，保存到 ./reports/mining-all167-iter14-{date_str}.md
2. 报告包含：
   - Top 5 策略排名
   - 各流派表现对比
   - 关键发现
   - 下轮建议""".replace("{sys_time}", time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 8*3600))).replace("{date_str}", time.strftime("%Y%m%d", time.localtime(time.time() + 8*3600)))
    
    t11_id = kanban_create("Iter14 T11: 策略挖掘报告", "writer", t11_body, parents=[t10_id], max_runtime=600)
    if not t11_id:
        log_msg("FAILED to create T11")
        sys.exit(1)
    
    # Step 7: Wait for T11
    log_msg("Phase 7: Waiting for T11 report...")
    if not wait_for_tasks([t11_id]):
        log_msg("FAILED: T11 did not complete within timeout")
        sys.exit(1)
    
    # Step 8: Done!
    # Update state.json current_iteration if poller script didn't do it
    log_msg("=== Iter14 Pipeline Complete! ===")
    sys.exit(0)

if __name__ == "__main__":
    main()
