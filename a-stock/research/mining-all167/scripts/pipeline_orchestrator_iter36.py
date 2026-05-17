#!/usr/bin/env python3
"""
Background poller for iter 36 (mining-all167).
Waits for T2-T12 analyst tasks to complete, then creates T13 (convergence) and T14 (report).
"""

import sqlite3, time, subprocess, json, sys, os
from datetime import datetime

DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
ANALYST_IDS = ["t_0b659c15", "t_72cd53c6", "t_6d5d727c", "t_bdcbefe2", "t_57c8743f", "t_295f1c8c", "t_53d2daad", "t_b9acef3b", "t_4c404321", "t_016fc906", "t_3a61c970"]
ITER = 36
BEST_METRICS_REF = {"win_rate_5d": 87.81, "ret_5d": 38.81, "signal_count": 812}
LOG_BASE = f"{STRATEGY_DIR}/logs/iter_{ITER}"

ts_start = "2026-05-14 23:04"
best_wr = 87.81
best_r5 = 38.81
fatigue_start = 4

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(f"{STRATEGY_DIR}/logs/poller.log", "a") as f:
        f.write(line + "\n")

def wait_for_tasks(tids, timeout_seconds=14400, poll_interval=30):
    """Wait until all specified tasks reach 'done' status."""
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout_seconds:
            log(f"TIMEOUT after {elapsed:.0f}s waiting for {len(tids)} tasks")
            return False
        
        conn = sqlite3.connect(DB)
        done_count = 0
        for tid in tids:
            row = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
            if row and row[0] == 'done':
                done_count += 1
        conn.close()
        
        log(f"Progress: {done_count}/{len(tids)} done | elapsed={elapsed:.0f}s")
        
        if done_count == len(tids):
            log(f"All {len(tids)} tasks complete!")
            return True
        
        time.sleep(poll_interval)

def kanban_create(title, assignee, body, parents=None, max_runtime=10800):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR creating task: {result.stderr[:200]}")
        return None
    try:
        data = json.loads(result.stdout)
        log(f"Created task: {data.get('id','?')} - {title[:50]}")
        return data.get('id')
    except:
        log(f"Parse error: {result.stdout[:150]}")
        return None

def update_state_json(data):
    """Update state.json with convergence results."""
    path = f"{STRATEGY_DIR}/state/state.json"
    with open(path) as f:
        state = json.load(f)
    
    state['current_iteration'] = ITER
    state['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M")
    state['fatigue_count'] = data.get('fatigue_count', state['fatigue_count'])
    
    if data.get('best_updated'):
        state['best_metrics'] = {
            'win_rate_5d': data['best_metrics'].get('win_rate_5d', state['best_metrics']['win_rate_5d']),
            'ret_5d': data['best_metrics'].get('ret_5d', state['best_metrics']['ret_5d']),
            'signal_count': data['best_metrics'].get('signal_count', state['best_metrics']['signal_count']),
            'strategy_desc': data['best_metrics'].get('strategy_desc', ''),
            'params': data['best_metrics'].get('params', {}),
            'discovered_at': datetime.now().strftime("%Y-%m-%d")
        }
    
    # Add history entry
    history_entry = {
        'iteration': ITER,
        'ret_5d': data.get('ret_5d'),
        'win_5d': data.get('win_5d'),
        'signal_count': data.get('signal_count'),
        'sharpe_5d': data.get('sharpe_5d'),
        'analyst': 'T13_主控收敛 (poller)',
        'params': data.get('strategy_desc', '各流派最佳汇总'),
        'note': data.get('summary', '')
    }
    state['history'].insert(0, history_entry)
    
    # Update recent_combos
    new_combos = data.get('recent_combos', [])
    if new_combos:
        state['recent_combos'] = (new_combos + state['recent_combos'])[:50]
    
    with open(path, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    log("state.json updated")

# ======================================
# Phase 1: Wait for T2-T12 to complete
# ======================================
log(f"Starting iter {ITER} background poller")
log(f"Waiting for {len(ANALYST_IDS)} analyst tasks (T2-T12)...")
log(f"Best metrics ref: WR={best_wr}%, R5={best_r5}%, fatigue={fatigue_start}")

if not wait_for_tasks(ANALYST_IDS):
    log("ERROR: Analyst tasks did not complete within timeout")
    sys.exit(1)

# ======================================
# Phase 2: Read analyst outputs
# ======================================
log("Reading analyst output files to extract best strategies...")
output_files = []
import glob
for f in sorted(glob.glob(f"{LOG_BASE}/analysis_*.md")):
    output_files.append(f)
    log(f"  Found output: {os.path.basename(f)}")

# Also check for JSON outputs
for f in sorted(glob.glob(f"{LOG_BASE}/analysis_*.json")):
    output_files.append(f)
    log(f"  Found JSON: {os.path.basename(f)}")

log(f"Total {len(output_files)} analysis outputs found")

# ======================================
# Phase 3: Create T13 convergence task
# ======================================
log("Creating T13 (convergence)...")

t13_body = (
    f"## 时间上下文\n"
    f"- 系统执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n"
    f"- 迭代：iter {ITER}\n"
    f"- 全局最佳（IS）：WR={best_wr}%, R5={best_r5}%\n"
    f"- 疲劳计数：{fatigue_start}/10\n"
    "\n"
    "## 任务：主控收敛\n"
    "读取 T2-T12 所有分析师的输出文件，进行：\n"
    "1. 汇总各流派的最佳发现（只保留 OOS 优先指标）\n"
    "2. 交叉对比各流派发现，寻找跨流派协同信号\n"
    "3. 对每个发现进行 Walk-Forward 验证评估\n"
    "4. 与全局最佳对比：\n"
    f"   - 是否 WR > {best_wr}% (IS) 且信号数 >= 200？\n"
    f"   - 是否 R5 > {best_r5}% (IS) 且信号数 >= 200？\n"
    "5. 判断是否超越全局纪录，决定疲劳计数\n"
    "\n"
    "## 输出要求\n"
    f"- 汇总报告到：{LOG_BASE}/convergence.md\n"
    "- 明确列出每个发现的 OOS 指标\n"
    "- 标注过拟合风险等级\n"
    "- 给出下一轮探索建议\n"
    "\n"
    "## 数据规则\n"
    "- 所有输出文件在以下目录：\n"
)

for f_name in ['analysis_T2_动量趋势', 'analysis_T3_反转低吸', 'analysis_T4_资金主力',
               'analysis_T5_基本面估值', 'analysis_T6_板块轮动', 'analysis_T7_跨市场联动',
               'analysis_T8_量价形态', 'analysis_T9_交叉验证', 'analysis_T10_VWAP流动性',
               'analysis_T11_DeepTrades', 'analysis_T12_资金预判']:
    t13_body += f"  - {LOG_BASE}/{f_name}.md (or .json if absent)\n"

t13_body += (
    "\n"
    "## ⚠️ Walk-Forward 验证规则\n"
    "所有结论必须基于 OOS（2025-至今）数据。IS 数据仅供参考。\n"
    "双重 PASS：OOS WR>=48%, R5>=2%, N>=20\n"
    "过拟合过滤：IS→OOS 降幅 >15pp 直接废弃\n"
)

t13_id = kanban_create(
    f"T13: 主控收敛 (iter {ITER})",
    "analyst",
    t13_body,
    parents=ANALYST_IDS,
    max_runtime=10800
)

if not t13_id:
    log("FATAL: Could not create T13 convergence task")
    sys.exit(1)

# ======================================
# Phase 4: Wait for T13 to complete
# ======================================
log("Waiting for T13 convergence...")
if not wait_for_tasks([t13_id], timeout_seconds=14400):
    log("ERROR: T13 convergence did not complete")
    sys.exit(1)

# ======================================
# Phase 5: Read convergence output
# ======================================
log("Reading convergence output...")
convergence_text = ""
convergence_path = f"{LOG_BASE}/convergence.md"
if os.path.exists(convergence_path):
    with open(convergence_path) as f:
        convergence_text = f.read()
    log(f"Convergence file size: {len(convergence_text)} bytes")

# Extract key metrics from convergence (simplified - T14 will do detailed parsing)
# For now, we assume convergence succeeded and pass results forward

# ======================================
# Phase 6: Create T14 report
# ======================================
log("Creating T14 (report generation)...")

t14_body = (
    f"## 时间上下文\n"
    f"- 系统执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC+8\n"
    f"- 迭代：iter {ITER}\n"
    "\n"
    "## 任务：报告生成\n"
    f"1. 读取 T13 收敛结果：{LOG_BASE}/convergence.md\n"
    f"2. 读取各流派分析文件：{LOG_BASE}/\n"
    "3. 生成格式化报告，必须包含：\n"
    "   - 本轮测试概要（流派数、总组合数、PASS数、通过率）\n"
    "   - 各流派最佳发现（OOS 指标：WR/R5/N/Sharpe/P10）\n"
    "   - 跨流派协同发现\n"
    "   - 新因子发现\n"
    "   - 是否超越全局纪录 + 疲劳计数\n"
    "   - 下一轮探索建议\n"
    "\n"
    f"- 输出到：{STRATEGY_DIR}/reports/mining-all167-iter{ITER}-{datetime.now().strftime('%Y%m%d-%H%M')}.md\n"
    "- 代码和名称一起显示（如 600984.SH 建设机械）\n"
    "\n"
    "## ⚠️ 强制规则\n"
    "1. 报告开头必须引用 T13 收敛结果中的基准日期和结论\n"
    "2. 禁止使用'周一/周五'等推测日期词\n"
    "3. 所有指标必须标注 IS/OOS 及通过了/未通过\n"
    "4. 保持报告简洁（<50KB）\n"
)

t14_id = kanban_create(
    f"T14: 报告生成 (iter {ITER})",
    "writer",
    t14_body,
    parents=[t13_id],
    max_runtime=3600
)

if not t14_id:
    log("FATAL: Could not create T14 report task")
    sys.exit(1)

# ======================================
# Phase 7: Wait for T14 to complete
# ======================================
log("Waiting for T14 report generation...")
if not wait_for_tasks([t14_id], timeout_seconds=7200):
    log("ERROR: T14 report did not complete")
    sys.exit(1)

# ======================================
# Phase 8: Update state.json
# ======================================
log("All tasks complete. Updating state.json...")

# Check fatigue: did we beat best_metrics?
# (This simplified logic assumes the convergence task recorded results)
# T13/T14 will have done the actual analysis; we just update state
# For robustness, read convergence for fatigue determination
found_record = False
if convergence_text and len(convergence_text) > 100:
    # Simple heuristics for fatigue tracking
    # Look for signal_count and WR/R5 values in the text
    import re
    wr_match = re.search(r'(?:WR|win_rate|胜率)[:=]\s*([\d.]+)%', convergence_text)
    r5_match = re.search(r'(?:R5|ret_5d|回报)[:=]\s*([\d.]+)%', convergence_text)
    n_match = re.search(r'(?:N|signal_count|信号)[:=]\s*([\d,]+)', convergence_text)
    
    new_wr = float(wr_match.group(1)) if wr_match else 0
    new_r5 = float(r5_match.group(1)) if r5_match else 0
    new_n = int(n_match.group(1).replace(',','')) if n_match else 0
    
    if (new_wr > best_wr or new_r5 > best_r5) and new_n >= 200:
        found_record = True
        log(f"🏆 New record! WR={new_wr}% > {best_wr}% or R5={new_r5}% > {best_r5}%")

new_fatigue = 0 if found_record else fatigue_start + 1
log(f"Record broken: {found_record}, fatigue: {fatigue_start} -> {new_fatigue}")

# Write state update
update_state_json({
    'ret_5d': new_r5 if 'new_r5' in dir() else None,
    'win_5d': new_wr if 'new_wr' in dir() else None,
    'signal_count': new_n if 'new_n' in dir() else None,
    'fatigue_count': new_fatigue,
    'best_updated': found_record,
    'best_metrics': {'win_rate_5d': new_wr, 'ret_5d': new_r5, 'signal_count': new_n} if found_record else {},
    'strategy_desc': f"Iter{ITER}完整汇总",
    'summary': f"✅ Iter{ITER} completed via background poller. Fatigue: {fatigue_start}->{new_fatigue}. {'🏆 New record!' if found_record else 'No new record.'}",
})

log("=" * 50)
log(f"✅ Iter {ITER} pipeline complete!")
log(f"   Last run: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
log("=" * 50)
