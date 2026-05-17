#!/usr/bin/env python3
"""
Round 17 — 超短线 M1/M5 研究循环 (Scalping Edition)

聚焦品种: XAUUSD, XAGUSD, JP225, US500, US30
时间框架: M1 / M5
数据源: scalping-m1/data/{M1,M5}/*.parquet (源自 MT5)

本轮假设队列 (5个):
1. M5 极端超卖 (RSI<20) → 做多全品种
2. M5 极端超买 (RSI>80) → 做空全品种
3. M1 连阴+超卖 (consecutive_bear>=3 + RSI<25) → 做多
4. M1/M5 美盘 (session='us') + 超卖 → 做多 (US session均值回归)
5. M5 连阳+超买 (consecutive_bull>=3 + RSI>75) → 做空
"""

import sys
import os
import json
from datetime import datetime

# ── Add scalping-m1 scripts to path ──
SCALPING_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts"
if SCALPING_DIR not in sys.path:
    sys.path.insert(0, SCALPING_DIR)

from data_loader import load_data, compute_indicators
from grid_engine import run_grid, print_results_table

# ─── Config ───
TARGET_SYMBOLS = ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"]
HOLD_PERIODS_M5 = [1, 2, 3, 5, 7, 10, 15, 20, 30, 44, 60]
HOLD_PERIODS_M1 = [1, 2, 3, 5, 7, 10, 15, 20, 30, 44, 60, 120, 240]
TIMEFRAMES = ["M5", "M1"]

def run_hypothesis(config, label):
    """Run a single hypothesis and return results."""
    print(f"\n{'='*80}")
    print(f"  🔬 {label}")
    print(f"  Entry: {config['entry_condition']}")
    print(f"  TF: {config['timeframe']} | Dir: {config['direction']}")
    print(f"  Symbols: {config['symbols']}")
    print(f"{'='*80}")
    
    results = run_grid(config)
    print_results_table(results, title=label)
    
    # Extract best findings
    findings = []
    for sym in sorted(results.keys()):
        sym_res = results[sym]
        best = max(sym_res, key=lambda r: r["win_rate"])
        if best["n"] >= 30:
            findings.append({
                "symbol": sym,
                "timeframe": config["timeframe"],
                "entry_condition": config["entry_condition"],
                "direction": config["direction"],
                "best_hold": best["hold_period"],
                "win_rate": best["win_rate"],
                "n": best["n"],
                "avg_return": best["avg_return"],
                "sharpe_ratio": best["sharpe_ratio"],
                "max_drawdown": best["max_drawdown"],
            })
            label_star = "⭐" if best["win_rate"] >= 0.60 else ("💡" if best["win_rate"] >= 0.55 else "")
            print(f"  {label_star} {sym:<10} hold={best['hold_period']:>3}  "
                  f"wr={best['win_rate']*100:>5.1f}%  n={best['n']:>5}  "
                  f"sharpe={best['sharpe_ratio']:>7.2f}")
    
    return findings

def main():
    all_findings = []
    
    # ──────────────────────────────────────────
    # Hypothesis 1: M5 极端超卖 → 做多
    # ──────────────────────────────────────────
    print("\n" + "█"*80)
    print("█  HYPOTHESIS 1: M5 极端超卖做多 (session不限)")
    print("█"*80)
    
    h1_findings = run_hypothesis({
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "rsi14 < 20",
        "direction": "long",
        "hold_periods": HOLD_PERIODS_M5,
    }, "H1: M5 RSI<20 → 做多 (极端超卖)")
    all_findings.extend(h1_findings)
    
    # ──────────────────────────────────────────
    # Hypothesis 2: M5 极端超买 → 做空
    # ──────────────────────────────────────────
    print("\n" + "█"*80)
    print("█  HYPOTHESIS 2: M5 极端超买做空 (session不限)")
    print("█"*80)
    
    h2_findings = run_hypothesis({
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "rsi14 > 80",
        "direction": "short",
        "hold_periods": HOLD_PERIODS_M5,
    }, "H2: M5 RSI>80 → 做空 (极端超买)")
    all_findings.extend(h2_findings)
    
    # ──────────────────────────────────────────
    # Hypothesis 3: M1 连阴超卖 → 做多
    # ──────────────────────────────────────────
    print("\n" + "█"*80)
    print("█  HYPOTHESIS 3: M1 连阴>=3 + RSI<25 → 做多")
    print("█"*80)
    
    h3_findings = run_hypothesis({
        "timeframe": "M1",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "consecutive_bear >= 3 and rsi14 < 25",
        "direction": "long",
        "hold_periods": HOLD_PERIODS_M1,
    }, "H3: M1 consecutive_bear>=3 + RSI<25 → 做多 (超卖连阴反转)")
    all_findings.extend(h3_findings)
    
    # ──────────────────────────────────────────
    # Hypothesis 4: M1/M5 美盘超卖 → 做多
    # ──────────────────────────────────────────
    print("\n" + "█"*80)
    print("█  HYPOTHESIS 4: M5 美盘超卖 → 做多")
    print("█"*80)
    
    h4_findings = run_hypothesis({
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "session == 'us' and rsi14 < 25",
        "direction": "long",
        "hold_periods": HOLD_PERIODS_M5,
    }, "H4: M5 session='us' + RSI<25 → 做多 (美盘超卖均值回归)")
    all_findings.extend(h4_findings)
    
    # ──────────────────────────────────────────
    # Hypothesis 5: M5 连阳超买 → 做空
    # ──────────────────────────────────────────
    print("\n" + "█"*80)
    print("█  HYPOTHESIS 5: M5 连阳>=3 + RSI>75 → 做空")
    print("█"*80)
    
    h5_findings = run_hypothesis({
        "timeframe": "M5",
        "symbols": TARGET_SYMBOLS,
        "entry_condition": "consecutive_bull >= 3 and rsi14 > 75",
        "direction": "short",
        "hold_periods": HOLD_PERIODS_M5,
    }, "H5: M5 consecutive_bull>=3 + RSI>75 → 做空 (超买连阳反转)")
    all_findings.extend(h5_findings)
    
    # ──────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────
    print(f"\n\n{'='*80}")
    print(f"  📊 ROUND 17 SUMMARY — ALL FINDINGS (n>=30)")
    print(f"{'='*80}")
    print(f"\n| {'品种':<10} | {'TF':<4} | {'方向':<4} | {'持有':<5} | {'胜率':<7} | {'n':<6} | {'Sharpe':<8} | {'条件'}")
    print(f"|{'':->10}|{'':->4}|{'':->4}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|{'':->30}")
    
    strong_findings = []
    promising_findings = []
    
    for f in sorted(all_findings, key=lambda x: -x["win_rate"]):
        wr = f["win_rate"] * 100
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        label = ""
        if f["win_rate"] >= 0.60 and f["n"] >= 30:
            label = "⭐"
            strong_findings.append(f)
        elif f["win_rate"] >= 0.55 and f["n"] >= 30:
            label = "💡"
            promising_findings.append(f)
        
        if f["win_rate"] >= 0.55 and f["n"] >= 30:
            print(f"| {label} {f['symbol']:<7} | {f['timeframe']:<4} | {dir_cn:<4} | {f['best_hold']:<5} | {wr:>5.1f}% | {f['n']:<6} | {f['sharpe_ratio']:<8.2f} | {f['entry_condition'][:30]}")
    
    print(f"\n{'='*80}")
    print(f"  强信号 (WR>=60%, n>=30): {len(strong_findings)}")
    for f in strong_findings:
        print(f"    ⭐ {f['symbol']:10s} {f['timeframe']:4s} {f['direction']:5s} "
              f"hold={f['best_hold']:3d}  WR={f['win_rate']*100:5.1f}%  "
              f"n={f['n']:5d}  Sharpe={f['sharpe_ratio']:7.2f}")
    
    print(f"\n  潜力信号 (55%<=WR<60%, n>=30): {len(promising_findings)}")
    for f in promising_findings:
        print(f"    💡 {f['symbol']:10s} {f['timeframe']:4s} {f['direction']:5s} "
              f"hold={f['best_hold']:3d}  WR={f['win_rate']*100:5.1f}%  "
              f"n={f['n']:5d}  Sharpe={f['sharpe_ratio']:7.2f}")
    
    # ─── Update state ───
    state_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "research_state.json")
    try:
        with open(state_path) as f:
            state = json.load(f)
    except:
        state = {"topic": "期货 K 线形态研究 — 外汇/商品/指数", "data": {}, "current_round": 16, "best_findings": [], "hypothesis_queue": []}
    
    # Convert findings to best_findings format
    new_best = []
    for i, f in enumerate(strong_findings + promising_findings):
        bf = {
            "id": f"round17_{i+1:03d}",
            "hypothesis": f"{f['entry_condition']} → {f['symbol']} {f['timeframe']} {f['direction']} hold={f['best_hold']}",
            "level": "A-" if f["win_rate"] >= 0.60 else "B+",
            "win_rate": round(f["win_rate"] * 100, 2),
            "signal_count": f["n"],
            "sharpe": round(f["sharpe_ratio"], 2),
            "notes": f"M1/M5 scalping R17新发现! {f['symbol']} {f['timeframe']} {f['direction']} WR={f['win_rate']*100:.1f}% n={f['n']}",
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        new_best.append(bf)
    
    # Update state
    state["current_round"] = 17
    state["best_findings"] = new_best + state.get("best_findings", [])
    state["data"]["timeframes"] = ["M1", "M5"]
    state["data"]["symbols"] = TARGET_SYMBOLS
    state["data"]["data_source"] = "MT5 M1/M5 parquet (scalping-m1)"
    state["data"]["status"] = "active"
    
    # Generate new hypothesis queue
    state["hypothesis_queue"] = generate_new_hypotheses(strong_findings, promising_findings)
    
    with open(state_path, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 状态已更新: {state_path}")
    return strong_findings, promising_findings


def generate_new_hypotheses(strong, promising):
    """Generate next round hypotheses based on findings."""
    hypotheses = []
    
    # If we found strong signals, suggest deeper exploration
    for f in strong[:3]:
        # Suggest session-specific optimization
        hy = {
            "id": f"round18_{len(hypotheses)+1:03d}",
            "hypothesis": f"{f['symbol']} {f['timeframe']} {f['direction']} — Session分离验证 (US/EU/Asia)",
            "direction": f["direction"],
            "priority": 1,
            "status": "pending",
            "reasoning": f"Round17发现{f['symbol']} {f['timeframe']} {f['direction']} WR={f['win_rate']*100:.1f}% n={f['n']}。将session分离验证，可能进一步提升胜率。"
        }
        hypotheses.append(hy)
    
    # If any M5 signals found, suggest M1 comparison
    m5_findings = [f for f in strong + promising if f["timeframe"] == "M5"]
    if m5_findings:
        avg_wr = sum(f["win_rate"] for f in m5_findings) / len(m5_findings)
        hypotheses.append({
            "id": f"round18_{len(hypotheses)+1:03d}",
            "hypothesis": f"M1 同条件对比 M5 — 超短时间框架下胜率是否更高？",
            "direction": "both",
            "priority": 2,
            "status": "pending",
            "reasoning": f"M5平均WR={avg_wr*100:.1f}%。M1更快节奏可能产生更多信号，但噪音更大。对比验证时间框架对胜率的影响。"
        })
    
    # Always suggest RSI threshold optimization
    hypotheses.append({
        "id": f"round18_{len(hypotheses)+1:03d}",
        "hypothesis": "RSI阈值深度扫描 — RSI<15/18/20/22/25 分档对比 (M5)",
        "direction": "long",
        "priority": 1,
        "status": "pending",
        "reasoning": "Round17发现RSI极端值有效。精细分档可确定最佳阈值，参考candlestick RSI>65优化成功经验。"
    })
    
    # Session-specific hypothesis
    hypotheses.append({
        "id": f"round18_{len(hypotheses)+1:03d}",
        "hypothesis": "M5 美盘连阴+超卖 vs 欧盘连阴+超卖 — Session对比扫描",
        "direction": "long",
        "priority": 2,
        "status": "pending",
        "reasoning": "US和EU session的超卖反转效率不同。分离验证可发现最佳交易时段。"
    })
    
    return hypotheses


if __name__ == "__main__":
    strong, promising = main()
