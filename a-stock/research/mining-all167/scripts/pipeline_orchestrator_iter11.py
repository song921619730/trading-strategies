#!/usr/bin/env python3
"""
Background poller for Iteration 11 mining pipeline.
Waits for T2-T8 → creates T9 → waits T9 → creates T10 → waits T10 → creates T11.
Survives as independent process after orchestrator session ends.
"""
import sqlite3
import time
import subprocess
import json
import os
from datetime import datetime, timezone, timedelta

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ITER_N = 11

now_utc8 = datetime.now(timezone(timedelta(hours=8)))
time_str = now_utc8.strftime("%Y-%m-%d %H:%M")
date_str = now_utc8.strftime("%Y%m%d")

# Task IDs created by orchestrator
T1_ID = "t_fd146c16"
T2_IDS = {
    "t_132e1afb": "T2_动量趋势",
    "t_58858238": "T3_反转低吸",
    "t_0467d946": "T4_资金主力",
    "t_e131508b": "T5_基本面估值",
    "t_1a03759f": "T6_板块轮动",
    "t_cfa1300d": "T7_跨市场联动",
    "t_0b9e16a5": "T8_量价形态",
}
T2_ID_LIST = list(T2_IDS.keys())

def kanban_create(title, assignee, body, parents=None, max_runtime=600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    print(f"Creating: {title}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"  FAIL: {result.stderr[:200]}")
        return None
    data = json.loads(result.stdout)
    tid = data.get("id") or data.get("task_id")
    print(f"  OK: {tid}")
    return tid

def wait_for_done(tids, timeout=7200, poll_interval=60):
    """Wait until all tasks are status='done'."""
    start = time.time()
    while time.time() - start < timeout:
        conn = sqlite3.connect(DB)
        statuses = {}
        for t in tids:
            row = conn.execute('SELECT status FROM tasks WHERE id=?', (t,)).fetchone()
            statuses[t] = row[0] if row else 'missing'
        conn.close()
        all_done = all(s == 'done' for s in statuses.values())
        running_count = sum(1 for s in statuses.values() if s == 'running')
        todo_count = sum(1 for s in statuses.values() if s == 'todo')
        done_count = sum(1 for s in statuses.values() if s == 'done')
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] done={done_count}/{len(tids)}, running={running_count}, todo={todo_count}")
        if all_done:
            print("  All done!")
            return True
        time.sleep(poll_interval)
    print("  TIMEOUT waiting for tasks")
    return False

def wait_t1_ready():
    """Wait for T1 to be done."""
    print(f"\n=== Waiting for T1 ({T1_ID}) ===")
    wait_for_done([T1_ID], timeout=1200, poll_interval=30)

def main():
    log_lines = []
    def log(msg):
        print(msg)
        log_lines.append(msg)

    # Phase 1: Wait T1 done
    wait_t1_ready()

    # Phase 2: Wait T2-T8 all done
    log(f"\n=== Waiting for T2-T8 (7 analyst tasks) ===")
    ok = wait_for_done(T2_ID_LIST, timeout=7200, poll_interval=60)
    if not ok:
        log("WARNING: Not all T2-T8 completed within timeout. Proceeding anyway with available results.")

    # Phase 3: Create T9 - Cross-validation
    time_context = f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{time_str} UTC+8
- 本轮迭代编号：{ITER_N}
- 规则：日志文件名日期使用 {date_str}，日期查询读取 T1 输出。
"""

    t9_body = f"""{time_context}
## 任务：跨流派组合交叉验证 (Iter {ITER_N})

你是 analyst（主控收敛角色），负责跨流派组合发现。

工作目录：{STRATEGY_DIR}

你的任务：
1. 读取 T2-T8 所有输出文件（位于 {STRATEGY_DIR}/logs/iter_{ITER_N}/）
   - 文件名模式：analysis_T[2-8]_*.md
   - 如果父级输出文件不存在，等待30秒后重试，最多3次，不要报错退出
2. 从每个流派的最佳发现中提取因子，做交叉组合验证（至少 10 组组合）
3. 组合逻辑示例：T3恐慌×T4资金流、T8K线×T7宏观、T5估值×T2动量等
4. 对每组组合编写 ClickHouse SQL 回测查询
5. 评估指标：5D收益率、5D胜率、Sharpe、10D/20D收益、信号数量
6. 输出到：{STRATEGY_DIR}/logs/iter_{ITER_N}/analysis_T9_组合交叉_{date_str}.md

历史最佳参考：
- 稳健最佳：T8-C4 底部长下影伞形线 (R5=7.28%, WR=77.82%, Sharpe=4.965)
- R5最高：T9-X17 锤子线×SPX上涨 (R5=25.76%, WR=74.9%, Sharpe=0.68)
- 高Sharpe：T3-C5 恐慌筹码全亏 (R5=4.88%, WR=79.7%, N=2290, Sharpe=5.025)

重要规则：
- ClickHouse 查询必须加 FINAL
- 日期格式 YYYYMMDD
- 主板过滤：ts_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'
- net_mf 字段不存在，用 net_mf_amount
- basic_eps_yoy 不可用，用 tr_yoy 或 netprofit_yoy
- 成功标准：WR ≥ 52% AND 5D收益 ≥ 3% AND 信号数 ≥ 200
- 日志文件必须简洁（<20KB）
"""

    t9 = kanban_create(
        title=f"T9: 跨流派组合交叉验证 (Iter {ITER_N})",
        assignee="analyst",
        body=t9_body,
        parents=T2_ID_LIST,
        max_runtime=3600
    )

    if not t9:
        log("FATAL: T9 creation failed")
        return

    # Phase 4: Wait T9 done
    log(f"\n=== Waiting for T9 ({t9}) ===")
    ok = wait_for_done([t9], timeout=7200, poll_interval=60)
    if not ok:
        log("WARNING: T9 not completed within timeout. Proceeding anyway.")

    # Phase 5: Create T10 - Convergence
    t10_body = f"""{time_context}
## 任务：主控收敛 — 更新状态 + 知识库 (Iter {ITER_N})

你是 analyst（主控收敛角色），负责汇总本轮发现并更新全局状态。

工作目录：{STRATEGY_DIR}

你的任务：
1. 读取 T2-T9 所有输出文件（位于 {STRATEGY_DIR}/logs/iter_{ITER_N}/）
   - 如果父级输出文件不存在，等待30秒后重试，最多3次
2. 读取当前 {STRATEGY_DIR}/state/state.json
3. 用 Python 更新 state.json：
   - current_iteration: {ITER_N}
   - best_metrics: 如果本轮有超过历史最佳（WR≥52% AND R5≥3% AND N≥200）的策略，更新
   - best_metrics_robust: 更新稳健最佳（高Sharpe+高WR+合理N）
   - fatigue_count: 如果本轮无新最佳纪录，+1；否则归0
   - recent_combos: 追加本轮所有组合描述（保留最近50个）
   - history: 追加本轮 Top 策略记录
4. 更新 {STRATEGY_DIR}/state/knowledge_base.md：追加本轮有效发现（避免未来重复）
5. 输出收敛摘要到：{STRATEGY_DIR}/logs/iter_{ITER_N}/analysis_T10_收敛_{date_str}.md

当前 state.json 位于 {STRATEGY_DIR}/state/state.json，用 Python 读写。
更新时必须保持 JSON 格式完整。
"""

    t10 = kanban_create(
        title=f"T10: 主控收敛更新状态 (Iter {ITER_N})",
        assignee="analyst",
        body=t10_body,
        parents=[t9],
        max_runtime=1800
    )

    if not t10:
        log("FATAL: T10 creation failed")
        return

    # Phase 6: Wait T10 done
    log(f"\n=== Waiting for T10 ({t10}) ===")
    ok = wait_for_done([t10], timeout=3600, poll_interval=60)
    if not ok:
        log("WARNING: T10 not completed within timeout. Proceeding anyway.")

    # Phase 7: Create T11 - Report
    t11_body = f"""{time_context}
## 任务：生成策略挖掘报告 (Iter {ITER_N})

你是 writer，负责格式化本轮策略挖掘报告。

工作目录：{STRATEGY_DIR}

你的任务：
1. 读取 T10 收敛结果：{STRATEGY_DIR}/logs/iter_{ITER_N}/analysis_T10_收敛_{date_str}.md
   - 如果文件不存在，等待30秒后重试，最多3次
2. 读取 state.json：{STRATEGY_DIR}/state/state.json
3. 读取知识库：{STRATEGY_DIR}/state/knowledge_base.md
4. 生成格式化报告，保存到：{STRATEGY_DIR}/reports/mining-all167-iter{ITER_N}-{date_str}.md

报告必须包含：
- 分析基准日期（读取 T1 数据检查日志 {STRATEGY_DIR}/logs/iter_{ITER_N}/T1_data_check_{date_str}.md）
- 本轮 Top 5 策略排名（含代码、名称、指标）
- 各流派表现对比表
- 关键发现与创新点
- 与历史最佳对比
- 下轮探索建议

重要：报告中的股票必须同时包含代码和名称（如 600984.SH 建设机械），不要只给代码。
日期必须使用 YYYY-MM-DD 格式，禁止推测。
"""

    t11 = kanban_create(
        title=f"T11: 生成策略挖掘报告 (Iter {ITER_N})",
        assignee="writer",
        body=t11_body,
        parents=[t10],
        max_runtime=600
    )

    if not t11:
        log("FATAL: T11 creation failed")
        return

    log(f"\n=== Pipeline complete! ===")
    log(f"T9: {t9}")
    log(f"T10: {t10}")
    log(f"T11: {t11}")

    # Write completion log
    with open(f"{STRATEGY_DIR}/logs/iter_{ITER_N}/poller_completion_{date_str}.md", "w") as f:
        f.write("# Pipeline Orchestrator Completion Log\n\n")
        f.write(f"执行时间：{time_str} UTC+8\n\n")
        f.write("## 任务图\n")
        f.write(f"- T1: {T1_ID} (researcher, 数据检查)\n")
        f.write(f"- T2-T8: {', '.join(T2_ID_LIST)} (analyst, 7流派并行)\n")
        f.write(f"- T9: {t9} (analyst, 组合交叉验证)\n")
        f.write(f"- T10: {t10} (analyst, 收敛更新)\n")
        f.write(f"- T11: {t11} (writer, 报告生成)\n\n")
        f.write("## 日志\n")
        for line in log_lines:
            f.write(line + "\n")

if __name__ == "__main__":
    # Ensure logs directory exists
    os.makedirs(f"{STRATEGY_DIR}/logs/iter_{ITER_N}", exist_ok=True)
    os.makedirs(f"{STRATEGY_DIR}/reports", exist_ok=True)
    main()
