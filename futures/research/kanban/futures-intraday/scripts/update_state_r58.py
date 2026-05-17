#!/usr/bin/env python3
"""Update research state to round 58."""
import json

with open("state/research_state.json", "r") as f:
    state = json.load(f)

state["current_round"] = 58
state["data"]["last_update"] = "2026-05-14"

new_findings = [
    {
        "id": "round58_best_001",
        "hypothesis": "XAUUSD H1 US session+RSI<30+ATR>0.40% long hold=7 — 72.73% n=143 near injection threshold",
        "entry_condition": "session == 'us' and rsi14 < 30 and atr14 / close > 0.0040",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "best_hold": 7,
        "metrics": {
            "win_rate": 0.7273,
            "avg_return": 0.0017,
            "sharpe_ratio": 6.01,
            "signal_count": 143,
            "max_drawdown": 0.1757
        },
        "discovered_at": "2026-05-14",
        "status": "active",
        "summary": "XAUUSD H1 US session+RSI<30+ATR>0.40% long hold=7 WR=72.73% (n=143, Sharpe=6.01, MaxDD=17.57%). Only 7 samples shy of n=150 injection threshold. 12/16 hold periods WR>60%. ATR reduced to 0.35% expected to pass injection."
    },
    {
        "id": "round58_best_002",
        "hypothesis": "XAUUSD H1 Asia session+RSI<30+ATR>0.40% long hold=30 — 83.87% among highest WR in research",
        "entry_condition": "session == 'asia' and rsi14 < 30 and atr14 / close > 0.0040",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "best_hold": 30,
        "metrics": {
            "win_rate": 0.8387,
            "avg_return": 0.0096,
            "sharpe_ratio": 8.76,
            "signal_count": 62,
            "max_drawdown": 0.1187
        },
        "discovered_at": "2026-05-14",
        "status": "active",
        "summary": "XAUUSD H1 Asia session+RSI<30+ATR>0.40% long hold=30 WR=83.87% (n=62, Sharpe=8.76, MaxDD=11.87%). One of the highest WR signals in research history. Hold periods 10-48 all above 64%. n=62 <150 threshold."
    },
    {
        "id": "round58_best_003",
        "hypothesis": "JP225 M30 US session+RSI<30+ATR>0.30%+close<bb_lower long hold=15 — 73.64% BB series complete",
        "entry_condition": "session == 'us' and rsi14 < 30 and atr14 / close > 0.0030 and close < bb_lower",
        "direction": "long",
        "timeframe": "M30",
        "symbols": ["JP225"],
        "best_hold": 15,
        "metrics": {
            "win_rate": 0.7364,
            "avg_return": 0.0048,
            "sharpe_ratio": 13.92,
            "signal_count": 110,
            "max_drawdown": 0.0687
        },
        "discovered_at": "2026-05-14",
        "status": "hibernate",
        "summary": "JP225 M30 US session+RSI<30+ATR>0.30%+close<bb_lower long hold=15 WR=73.64% (n=110, Sharpe=13.92). BB series fully complete. n still <150, JP225 BB spectrum closed."
    }
]

state["best_findings"] = state["best_findings"] + new_findings

with open("state/research_state.json", "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"Updated to round {state['current_round']}")
print(f"Total best_findings: {len(state['best_findings'])}")
