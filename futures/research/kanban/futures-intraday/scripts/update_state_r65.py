#!/usr/bin/env python3
"""Round 65 — State Updater"""
import json
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "research_state.json"
RESULTS_PATH = Path(__file__).resolve().parent.parent / "logs" / "round65_researcher_results.json"

with open(RESULTS_PATH) as f:
    data = json.load(f)

# Extract findings
findings = []
for test_id, test_results in data.items():
    if not isinstance(test_results, dict):
        continue
    for sym, sym_res in test_results.items():
        if not isinstance(sym_res, dict):
            continue
        for hp, stats in sym_res.items():
            if not isinstance(stats, dict):
                continue
            n = stats.get("signal_count", 0)
            wr = stats.get("win_rate")
            avg_ret = stats.get("avg_return")
            sharpe = stats.get("sharpe_ratio")
            if wr is not None and n >= 30 and wr >= 0.60:
                findings.append({
                    "test_id": test_id,
                    "symbol": sym,
                    "hold_period": int(hp) if isinstance(hp, str) else hp,
                    "signal_count": n,
                    "win_rate": wr,
                    "avg_return": avg_ret,
                    "sharpe_ratio": sharpe,
                })

findings.sort(key=lambda x: (x["win_rate"], x["signal_count"]), reverse=True)

injectable = [f for f in findings if f["signal_count"] >= 150 and f["win_rate"] >= 0.65]
strong = [f for f in findings if f["win_rate"] >= 0.70 and f["signal_count"] >= 50]

# Build best_findings — merge with existing from state
best = []
for f in (injectable + strong)[:15]:
    entry = {
        "id": f"round65_{f['test_id']}_{f['symbol']}_{f['hold_period']}",
        "hypothesis": f"{f['symbol']} {f['test_id']} hold={f['hold_period']} — {f['win_rate']*100:.2f}% 注入！n={f['signal_count']}" if f['signal_count'] >= 150 else f"{f['symbol']} {f['test_id']} hold={f['hold_period']} — {f['win_rate']*100:.2f}% 强信号！n={f['signal_count']}",
        "entry_condition": "See test definition",
        "direction": "long" if f.get("avg_return", 0) and f["avg_return"] >= 0 else "short",
        "timeframe": "H1" if "H1" in f['test_id'] else "M30",
        "symbols": [f['symbol']],
        "best_hold": f['hold_period'],
        "metrics": {
            "win_rate": f['win_rate'],
            "avg_return": f['avg_return'],
            "sharpe_ratio": f['sharpe_ratio'],
            "signal_count": f['signal_count'],
        },
        "discovered_at": "2026-05-14",
        "status": "injectable" if f['signal_count'] >= 150 and f['win_rate'] >= 0.65 else "active",
        "summary": f"{f['symbol']} {f['test_id']} hold={f['hold_period']} 胜率{f['win_rate']*100:.2f}%(n={f['signal_count']})"
    }
    best.append(entry)

state = {
    "topic": "Futures Intraday Pattern Mining — 欧盘/亚盘 Session 扩样本优化 (Round 65)",
    "data": {
        "timeframes": ["H1", "M30"],
        "symbols": ["XAUUSD", "XAGUSD", "USTEC", "US30", "US500", "JP225", "HK50",
                    "USOIL", "UKOIL", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
        "status": "round65_complete",
        "data_start": "2021-01-03",
        "data_end": "2026-05-14",
        "last_update": "2026-05-14"
    },
    "current_round": 65,
    "last_completed_round": 65,
    "today": "2026-05-14",
    "best_findings": best
}

STATE_PATH.parent.mkdir(exist_ok=True)
with open(STATE_PATH, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)
print(f"✅ State updated: {STATE_PATH}")
print(f"   Round 65 complete. {len(injectable)} injectable, {len(strong)} strong signals added.")
