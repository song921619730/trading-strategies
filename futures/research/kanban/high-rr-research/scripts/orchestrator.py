#!/usr/bin/env python3
"""orchestrator.py — High-RR 研究主循环

每轮:
  1. 读 research_state.json
  2. 对 14 个品种随机采样参数
  3. 回测 → 更新 best_findings
  4. 写回 state
  5. 输出最终报告
"""

import json
import logging
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保能导入同级模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from research_engine import run_research_round, backtest_strategy, random_params, SYMBOLS

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("high_rr_orchestrator")

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR.parent / "state"
REPORT_DIR = SCRIPT_DIR.parent / "reports"
STATE_PATH = STATE_DIR / "research_state.json"
LOG_DIR = SCRIPT_DIR.parent / "logs"

os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ─── 注入门槛（研究阶段用，auto_inject 会再用严格版过滤） ───
MIN_SHARPE = 1.0
MIN_PROFIT_FACTOR = 1.2
MIN_TRADES = 30


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {
        "topic": "High-RR 低胜率高盈亏比策略挖掘",
        "data": {
            "timeframes": ["H1", "M5", "M15"],
            "data_range": "H1: ~2年 | M5: ~1.5年",
            "symbols": SYMBOLS,
        },
        "current_round": 0,
        "best_findings": [],
        "hypothesis_queue": [],
        "tested_hypotheses": [],
        "fatigue": 0.0,
        "consecutive_no_finding": 0,
    }


def save_state(state: dict):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def make_finding(result) -> dict:
    """将 BacktestResult 转为 state 中的 finding 记录"""
    return {
        "id": f"hrr_{state['current_round']:03d}_{result.symbol}_{result.params.get('pattern_type','?')}_{result.params.get('direction','?')[:1]}",
        "description": (
            f"{result.symbol} {result.params.get('timeframe_entry','M5')} "
            f"{result.params.get('pattern_type','?').replace('_',' ')} "
            f"{result.params.get('direction','long')} "
            f"— h1_trend={result.params.get('h1_trend','any')} "
            f"session={result.params.get('session','any')} "
            f"sl={result.params.get('sl_multiple',1.0)}x "
            f"tp={result.params.get('tp_multiple',5.0)}x"
        ),
        "timeframe": result.params.get("timeframe_entry", "M5"),
        "direction": result.params.get("direction", "long"),
        "best_hold": result.params.get("max_hold_bars", 48),
        "win_rate": round(result.win_rate, 1),
        "n": result.total_trades,
        "avg_return_pct": round(result.avg_return_pct, 4),
        "sharpe": round(result.sharpe, 2),
        "profit_factor": round(result.profit_factor, 2),
        "max_dd_pct": round(result.max_drawdown_pct, 2),
        "source": f"round{state['current_round']}",
        # 原始参数存档
        "_params": result.params,
        "_discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def write_report(state: dict, new_findings: list):
    """写出文本报告"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"research_round_{state['current_round']}_{ts}.md"

    lines = [f"# High-RR Research Round {state['current_round']}\n"]
    lines.append(f"**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    if new_findings:
        lines.append(f"\n## 本轮新发现 ({len(new_findings)})\n")
        lines.append(f"{'Symbol':<8}|{'Pattern':<18}|{'Dir':<5}|{'TF':<4}|{'n':<5}|{'WR':<6}|{'Sharpe':<7}|{'PF':<6}|{'DD%':<6}|{'AvgR%':<7}")
        lines.append('-' * 80)
        for f in new_findings:
            lines.append(
                f"{f.get('description','')[:8]:<8}|"
                f"{f.get('description','').split(' ')[2] if len(f.get('description','').split(' '))>2 else '?':<18}|"
                f"{f['direction']:<5}|{f['timeframe']:<4}|"
                f"{f['n']:<5}|{f['win_rate']:<6.1f}|{f['sharpe']:<7.2f}|"
                f"{f['profit_factor']:<6.2f}|{f['max_dd_pct']:<6.2f}|{f['avg_return_pct']:<7.4f}"
            )

    # 总排行榜
    all_findings = state["best_findings"]
    if all_findings:
        top = sorted(all_findings, key=lambda f: f.get("sharpe", 0), reverse=True)[:10]
        lines.append(f"\n## 历史 Top 10 (by Sharpe)\n")
        for i, f in enumerate(top, 1):
            lines.append(
                f"{i:2d}. {f.get('description','')[:60]} | "
                f"WR={f['win_rate']:.1f}% n={f['n']} "
                f"S={f['sharpe']:.2f} PF={f.get('profit_factor',0):.2f}"
            )

    with open(path, "w") as f:
        f.write("\n".join(lines))

    return path


def main():
    global state
    state = load_state()
    state["current_round"] += 1
    round_num = state["current_round"]

    log.info("═" * 60)
    log.info("High-RR Research Round %d", round_num)
    log.info("═" * 60)

    # ── 运行研究 ──
    samples = max(2, int(10 / (1 + state["fatigue"] * 2)))
    log.info("Sampling %d per symbol (fatigue=%.2f)", samples, state["fatigue"])

    results = run_research_round(samples_per_symbol=samples)

    if not results:
        log.warning("No results from research round")
        state["consecutive_no_finding"] += 1
        save_state(state)
        return

    # ── 筛选合格发现 ──
    new_findings = []
    for r in results:
        if r.sharpe < MIN_SHARPE:
            continue
        if r.profit_factor < MIN_PROFIT_FACTOR:
            continue
        if r.total_trades < MIN_TRADES:
            continue
        # 避免重复注入: 检查是否已存在相似描述
        desc = (
            f"{r.symbol} {r.params.get('timeframe_entry','M5')} "
            f"{r.params.get('pattern_type','?')} "
            f"{r.params.get('direction','long')}"
        )
        existing = any(desc in f.get("description", "") for f in state["best_findings"])
        if existing:
            log.info("  ⏭ Duplicate: %s", desc)
            continue

        finding = make_finding(r)
        new_findings.append(finding)

    # ── 更新 state ──
    if new_findings:
        log.info("✅ %d new findings this round", len(new_findings))
        state["best_findings"].extend(new_findings)
        # 按 Sharpe 排序保留 Top 100
        state["best_findings"].sort(key=lambda f: f.get("sharpe", 0), reverse=True)
        state["best_findings"] = state["best_findings"][:100]
        state["consecutive_no_finding"] = 0
        state["fatigue"] = max(0, state["fatigue"] - 0.1)
    else:
        log.info("No qualified findings this round")
        state["consecutive_no_finding"] += 1
        state["fatigue"] = min(1.0, state["fatigue"] + 0.15)

    # ── 写报告 ──
    report_path = write_report(state, new_findings)
    log.info("Report: %s", report_path)

    # ── 保存 ──
    save_state(state)
    log.info("State saved (%d total findings)", len(state["best_findings"]))

    # 输出最终结果（给 Cron 抓取）
    print(f"\n{'='*60}")
    print(f"High-RR Research Round {round_num} Complete")
    print(f"New findings: {len(new_findings)}")
    print(f"Total findings: {len(state['best_findings'])}")
    print(f"Fatigue: {state['fatigue']:.2f}")
    print(f"Report: {report_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    state = None
    main()
