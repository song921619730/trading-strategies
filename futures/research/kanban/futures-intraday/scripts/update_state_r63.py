#!/usr/bin/env python3
"""Round 63 — State Updater"""
import json
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "research_state.json"
REPORTS_DIR = Path(__file__).resolve().parent.parent.parent

def update_state(findings, report_path):
    best = []
    # Convert top findings to best_findings format
    for s in findings[:10]:
        entry = {
            "id": f"round63_{s['test_id']}_{s['symbol']}_{s['hold_period']}",
            "hypothesis": f"{s['symbol']} {s['test_id']} hold={s['hold_period']} — {s['win_rate']*100:.2f}% (n={s['signal_count']})",
            "entry_condition": "See test definition",
            "direction": "long" if s.get("avg_return", 0) >= 0 else "short",
            "timeframe": "H1" if "H1" in s['test_id'] else "M30",
            "symbols": [s['symbol']],
            "best_hold": s['hold_period'],
            "metrics": {
                "win_rate": s['win_rate'],
                "avg_return": s['avg_return'],
                "sharpe_ratio": s['sharpe_ratio'],
                "signal_count": s['signal_count'],
            },
            "discovered_at": "2026-05-14",
            "status": "injectable" if s['signal_count'] >= 150 and s['win_rate'] >= 0.65 else "active",
            "summary": f"{s['symbol']} {s['test_id']} hold={s['hold_period']} 胜率{s['win_rate']*100:.2f}%(n={s['signal_count']})"
        }
        best.append(entry)
    
    state = {
        "topic": "Futures Intraday Pattern Mining — H1/M30 US Session & Candle Pattern Deep Dive (Round 63)",
        "data": {
            "timeframes": ["H1", "M30"],
            "symbols": ["XAUUSD", "XAGUSD", "USTEC", "US30", "US500", "JP225", "HK50",
                        "USOIL", "UKOIL", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
            "status": "round63_complete",
            "data_start": "2021-01-03",
            "data_end": "2026-05-14",
            "last_update": "2026-05-14"
        },
        "current_round": 63,
        "last_completed_round": 63,
        "today": "2026-05-14",
        "best_findings": best
    }
    
    STATE_PATH.parent.mkdir(exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print(f"State updated: {STATE_PATH}")

if __name__ == "__main__":
    # Test with dummy data if run standalone
    pass
