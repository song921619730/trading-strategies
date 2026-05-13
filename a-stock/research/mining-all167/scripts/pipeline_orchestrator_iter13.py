#!/usr/bin/env python3
"""
Pipeline orchestrator for iteration 13 of all-167 mining.
Waits for T2-T8 analysts → creates T9 cross-validation → waits → creates T10 convergence → waits → creates T11 report.
Run as background process from the cron orchestrator session.
"""
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER_NUM = 13
CREATED_AT = "2026-05-12 18:19"

def kanban_create(title, assignee, body, parents=None, max_runtime=600):
    """Create a kanban task via CLI. Returns task ID."""
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR creating task '{title}': {result.stderr}")
        return None
    try:
        data = json.loads(result.stdout)
        tid = data.get("id") or data.get("task_id")
        print(f"Created: {tid} - {title} (assignee={assignee}, parents={parents})")
        return tid
    except json.JSONDecodeError as e:
        print(f"JSON parse error for '{title}': {e}")
        print(f"stdout: {result.stdout[:500]}")
        return None

def wait_for_tasks(tids, timeout=7200, poll_interval=30):
    """Poll kanban.db until all tasks in tids are 'done'. Returns True/False."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = sqlite3.connect(DB)
            statuses = {}
            for t in tids:
                row = conn.execute('SELECT status FROM tasks WHERE id=?', (t,)).fetchone()
                statuses[t] = row[0] if row else 'unknown'
            conn.close()
            done = all(s == 'done' for s in statuses.values())
            running = sum(1 for s in statuses.values() if s == 'running')
            remaining = [t for t, s in statuses.items() if s not in ('done',)]
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Status: done={sum(1 for s in statuses.values() if s=='done')}/{len(tids)}, running={running}, remaining={remaining}")
            if done:
                return True
            time.sleep(poll_interval)
        except Exception as e:
            print(f"Poll error: {e}")
            time.sleep(poll_interval)
    print(f"TIMEOUT after {timeout}s waiting for tasks: {tids}")
    return False

def log(msg):
    """Write to a log file in the strategy dir."""
    log_path = f"{STRATEGY_DIR}/logs/iter_{ITER_NUM}/orchestrator_poller.log"
    with open(log_path, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg)

def read_trade_date(conn):
    """Query the latest trade date from ClickHouse."""
    import requests
    try:
        url = "http://172.24.224.1:8123/"
        q = "SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL"
        r = requests.get(url, params={"query": q, "user": "ai_reader", "password": "ai_reader_2026", "format": "TabSeparated"}, timeout=10)
        if r.status_code == 200:
            return r.text.strip()
        return "unknown"
    except Exception as e:
        log(f"Warning: cannot query trade_date: {e}")
        return "unknown"

def main():
    log("=== Iteration 13 Pipeline Orchestrator started ===")
    
    # Read command-line args for T1-T8 task IDs
    if len(sys.argv) < 9:
        print("ERROR: Expected 8 task IDs (t1 t2 t3 t4 t5 t6 t7 t8)")
        sys.exit(1)
    
    t1, t2, t3, t4, t5, t6, t7, t8 = sys.argv[1:9]
    analyst_ids = [t2, t3, t4, t5, t6, t7, t8]
    
    # Get the latest trade date
    conn = sqlite3.connect(DB)
    trade_date = read_trade_date(conn)
    conn.close()
    
    log(f"Data baseline trade date: {trade_date}")
    
    # ======== Phase 2: Wait for T2-T8 analysts ========
    log("Phase 2: Waiting for T2-T8 analysts to complete...")
    if not wait_for_tasks(analyst_ids, timeout=7200):
        log("ERROR: T2-T8 timeout - aborting")
        sys.exit(1)
    log("All T2-T8 analysts completed!")
    
    # ======== Phase 3: Create T9 - Cross-validation ========
    log("Phase 3: Creating T9 - cross-validation...")
    t9_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{CREATED_AT} UTC+8
- 数据基准日期：{trade_date}
- 本轮迭代编号：13
- 历史最佳(R5)：{trade_date} — T9-X17: R5=25.76%, WR=74.9%, Sharpe=0.68, N=1546
- 历史最佳(稳健)：T9-X04: R5=7.33%, WR=82.29%, Sharpe=6.021, N=271

## 任务：T9 组合交叉验证

工作目录：{STRATEGY_DIR}

### 步骤
1. 读取 T2-T8 所有输出（位于 ./logs/iter_13/）
2. 从每个流派最佳发现中提取因子，做交叉组合（至少 10 组）
3. 每组交叉组合用 SQL 回测验证（使用全量历史数据）
4. 优先尝试跨流派协同（如 T2 动量因子 × T4 资金流因子、T3 恐慌因子 × T7 宏观因子）

### 输出
- 写入 ./logs/iter_13/analysis_T9_组合交叉.md
- 包含：至少 10 组交叉组合的完整回测结果
- 标注每组成功/失败（成功标准：WR≥52% AND 5D收益≥3% AND 信号数≥200）
- 列出 Top 5 交叉策略

### 数据规则
- 使用 query_sql MCP 工具
- ClickHouse 查询必须加 FINAL
- 日期格式 YYYYMMDD
- 主板过滤：ts_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'
- net_mf_amount 替代 net_mf
- tr_yoy / netprofit_yoy 替代 basic_eps_yoy
- cyq_chips 可用但偶发 404，重试即可
- None 值用 0 或 N/A 处理

### 成功标准
- WR ≥ 52% AND 5D 收益 ≥ 3% AND 信号数 ≥ 200
"""
    t9 = kanban_create(
        "T9: 组合交叉验证 (iter 13)",
        "analyst",
        t9_body,
        parents=analyst_ids,
        max_runtime=3600
    )
    if not t9:
        log("ERROR: Failed to create T9")
        sys.exit(1)
    log(f"T9 created: {t9}")
    
    # ======== Phase 4: Wait for T9 ========
    log("Phase 4: Waiting for T9 to complete...")
    if not wait_for_tasks([t9], timeout=7200):
        log("ERROR: T9 timeout - aborting")
        sys.exit(1)
    log("T9 completed!")
    
    # ======== Phase 5: Create T10 - Convergence ========
    log("Phase 5: Creating T10 - convergence...")
    t10_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{CREATED_AT} UTC+8
- 数据基准日期：{trade_date}
- 本轮迭代编号：13

## 任务：T10 主控收敛

工作目录：{STRATEGY_DIR}

### 步骤
1. 读取 T2-T9 所有输出（位于 ./logs/iter_13/）
2. 汇总所有流派的发现
3. 更新 ./state/state.json：
   - current_iteration: 13
   - 如果有新 best_metrics：更新并设置 fatigue_count=0
   - 否则：fatigue_count += 1
   - 追加本轮组合 hash 到 recent_combos
   - 追加本轮摘要到 history
4. 更新 ./state/knowledge_base.md：
   - 每个有效发现单独一个条目
   - 包含参数、指标、SQL、结论
5. 输出收敛摘要到 ./logs/iter_13/analysis_T10_收敛.md
6. 如果 fatigue_count ≥ 10：在报告中提醒调整方向

### 更新逻辑
- 新全局纪录（超越 R5=25.76% 或 同时 WR≥74.9%+Sharpe≥0.68）：fatigue_count=0
- 新稳健纪录（超越 R5=7.33% 且 WR≥82.29% 且 Sharpe≥6.021）：fatigue_count=0
- 否则：fatigue_count += 1
- 如果 fatigue_count ≥ 20：建议暂停审查

### 输出
- ./logs/iter_13/analysis_T10_收敛.md
- 更新 ./state/state.json
- 更新 ./state/knowledge_base.md
"""
    t10 = kanban_create(
        "T10: 主控收敛 (iter 13)",
        "analyst",
        t10_body,
        parents=[t9],
        max_runtime=3600
    )
    if not t10:
        log("ERROR: Failed to create T10")
        sys.exit(1)
    log(f"T10 created: {t10}")
    
    # ======== Phase 6: Wait for T10 ========
    log("Phase 6: Waiting for T10 to complete...")
    if not wait_for_tasks([t10], timeout=7200):
        log("ERROR: T10 timeout - aborting")
        sys.exit(1)
    log("T10 completed!")
    
    # ======== Phase 7: Create T11 - Report ========
    log("Phase 7: Creating T11 - report generation...")
    t11_body = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{CREATED_AT} UTC+8
- 数据基准日期：{trade_date}
- 本轮迭代编号：13

## 任务：T11 报告生成

工作目录：{STRATEGY_DIR}

### 步骤
1. 读取 T10 收敛结果（./logs/iter_13/analysis_T10_收敛.md）
2. 读取 ./state/state.json（确认最新 best_metrics）
3. 读取 ./state/knowledge_base.md（获取历史背景）
4. 生成格式化报告

### 报告模板（中文）
# 全表 167 挖掘 — Iter 13 报告

## 📅 分析基准
- 执行时间：{CREATED_AT}
- 数据基准日期：{trade_date}
- 疲劳计数：{trade_date}（超过 10 需调整方向）

## 本轮发现 Top 5
（列表：排名、流派、参数、R5、WR、N、Sharpe）

## 各流派表现
（T2-T8 每个流派的最佳参数和指标）

## 交叉组合发现
（T9 最佳交叉策略）

## 历史最佳跟踪
（当前 best_metrics 及其历史趋势）

## 下轮建议
（参数空间调整建议、新的探索方向、需放弃的无效方向）

### 输出
- 保存到 ./reports/mining-all167-iter13-20260512-1819.md
"""
    t11 = kanban_create(
        "T11: 报告生成 (iter 13)",
        "writer",
        t11_body,
        parents=[t10],
        max_runtime=600
    )
    if not t11:
        log("ERROR: Failed to create T11")
        sys.exit(1)
    log(f"T11 created: {t11}")
    
    # ======== Phase 8: Wait for T11 ========
    log("Phase 8: Waiting for T11 to complete...")
    if not wait_for_tasks([t11], timeout=3600):
        log("WARNING: T11 timeout - report may be incomplete")
    else:
        log("T11 completed! Pipeline iteration 13 fully done.")
    
    log("=== Iteration 13 Pipeline Orchestrator completed ===")


if __name__ == "__main__":
    main()
