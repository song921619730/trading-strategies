#!/usr/bin/env python3
"""Update research state to round 60 after round 59 execution."""
import json

with open("state/research_state.json", "r") as f:
    state = json.load(f)

state["current_round"] = 60
state["data"]["last_update"] = "2026-05-14"
state["fatigue"] = 0
state["consecutive_no_finding"] = 0

today = "2026-05-14"

new_findings = [
    {
        "id": "round59_best_001",
        "hypothesis": "XAUUSD H1 \u7f8e\u76d8+RSI<30+ATR>0.35%\u505a\u591a hold=7 \u2014 71.49% INJECTABLE! \u9ec4\u91d1\u9996\u500b\u53ef\u6ce8\u5165\u4fe1\u53f7",
        "entry_condition": "session == 'us' and rsi14 < 30 and atr14 / close > 0.0035",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "best_hold": 7,
        "metrics": {
            "win_rate": 0.7149,
            "avg_return": 0.0013,
            "sharpe_ratio": 3.99,
            "signal_count": 235,
            "max_drawdown": 0.1757
        },
        "discovered_at": today,
        "status": "injectable",
        "summary": "XAUUSD H1\u7f8e\u76d8+RSI<30+ATR>0.35%\u505a\u591ahold=7\u80dc\u738771.49%(n=235, Sharpe=3.99, MaxDD=17.57%)\uff01\u964dATR\u4ece0.40%\u81f30.35%\u540en\u4ece143\u6269\u81f3235(+64%)\uff0cWR\u4ec5\u4ece72.73%\u5fae\u964d\u81f371.49%(-1.24pp)\u3002n>=150\u4e14WR>=65%\u53cc\u91cd\u76ee\u6807\u901a\u8fc7\uff0c\u6b63\u5f0f\u6210\u4e3a\u9ec4\u91d1\u9996\u500b\u53ef\u6ce8\u5165\u4fe1\u53f7\uff01"
    },
    {
        "id": "round59_best_002",
        "hypothesis": "XAUUSD H1 \u4e9a\u76d8+RSI<25+ATR>0.35%\u505a\u591a hold=40 \u2014 85.29% \u6781\u81f4\u8d85\u5356\u786e\u8ba4",
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr14 / close > 0.0035",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "best_hold": 40,
        "metrics": {
            "win_rate": 0.8529,
            "avg_return": 0.0113,
            "sharpe_ratio": 3.84,
            "signal_count": 34,
            "max_drawdown": 0.1518
        },
        "discovered_at": today,
        "status": "active",
        "summary": "XAUUSD H1\u4e9a\u76d8+RSI<25+ATR>0.35%\u505a\u591ahold=40\u80dc\u738785.29%(n=34, Sharpe=3.84)\u3002\u4e9a\u76d8RSI<25\u8d85\u5356\u4fe1\u53f7n=34\u867d\u5c0f\u4f46WR=85.29%\u786e\u8ba4\u9ec4\u91d1\u4e9a\u76d8\u786e\u5b9e\u5b58\u5728\u6781\u81f4\u8d85\u5356\u53cd\u5f39\u6a21\u5f0f\u3002hold=20(73.53%)/hold=30(82.35%)/hold=40(85.29%)/hold=48(85.29%)\u957f\u6301\u6709\u671f\u6301\u7eed80%+\u3002"
    },
    {
        "id": "round59_best_003",
        "hypothesis": "XAUUSD H1 \u7f8e\u76d8+RSI<25+ATR>0.35%\u505a\u591a hold=7 \u2014 77.65% \u4e25\u683cRSI\u589e\u5f3a\u786e\u8ba4",
        "entry_condition": "session == 'us' and rsi14 < 25 and atr14 / close > 0.0035",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "best_hold": 7,
        "metrics": {
            "win_rate": 0.7765,
            "avg_return": 0.0029,
            "sharpe_ratio": 13.89,
            "signal_count": 85,
            "max_drawdown": 0.0276
        },
        "discovered_at": today,
        "status": "active",
        "summary": "XAUUSD H1\u7f8e\u76d8+RSI<25+ATR>0.35%\u505a\u591ahold=7\u80dc\u738777.65%(n=85, Sharpe=13.89, MaxDD=2.76%)\uff01\u4e25\u683cRSI<25\u76f8\u6bd4RSI<30(71.49%)\u63d0\u5347+6.16pp\uff0cSharpe=13.89\u4e3a\u9ec4\u91d1\u4fe1\u53f7\u6700\u9ad8\u3002\u77ed\u671f1-8h\u5168\u90e8\u8d8562%\u4e14\u6ce2\u52a8\u6781\u5c0f\u3002"
    }
]

state["best_findings"].extend(new_findings)

# Update hypothesis queue
queue_updates = {
    "round59_new_01": "completed",
    "round59_new_02": "completed",
    "round59_new_03": "completed",
    "round59_new_04": "completed",
    "round59_new_05": "completed",
    "round59_new_06": "completed",
    "round59_bonus_01": "completed",
    "round59_bonus_02": "completed",
    "round59_hibernate_01": "completed",
    "round59_hibernate_02": "completed"
}

for h in state["hypothesis_queue"]:
    if h["id"] in queue_updates:
        h["status"] = queue_updates[h["id"]]

# Add new hypotheses for round 60
new_hypotheses = [
    {
        "id": "round60_new_01",
        "priority": 1,
        "status": "pending",
        "hypothesis": "XAUUSD H1 \u7f8e\u76d8+RSI<22+ATR>0.35%\u505a\u591a \u2014 RSI<22\u6781\u81f4\u7248\u6d4b\u8bd5\u662f\u5426\u80fd\u8fbe80%+",
        "entry_condition": "session == 'us' and rsi14 < 22 and atr14 / close > 0.0035",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "description": "\u5728RSI<25(77.65%)\u57fa\u7840\u4e0a\u66f4\u4e25\u683c\u81f3RSI<22\uff0c\u9884\u671fn~40-50\uff0cWR\u7ea680-85%"
    },
    {
        "id": "round60_new_02",
        "priority": 1,
        "status": "pending",
        "hypothesis": "XAUUSD H1 \u7f8e\u76d8+RSI<30+ATR>0.35%+close<bb_lower\u505a\u591a \u2014 BB\u589e\u5f3agold\u9996\u865f\u6ce8\u5165\u4fe1\u53f7",
        "entry_condition": "session == 'us' and rsi14 < 30 and atr14 / close > 0.0035 and close < bb_lower",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "description": "\u5728\u53ef\u6ce8\u5165\u4fe1\u53f7(71.49%)\u57fa\u7840\u4e0a\u52a0\u5165BB\u4e0b\u8f68\u589e\u5f3a\uff0c\u9884\u671fWR~75-78%\u4f46n~80-120"
    },
    {
        "id": "round60_new_03",
        "priority": 1,
        "status": "pending",
        "hypothesis": "XAUUSD H1 \u4e9a\u76d8+RSI<25+ATR>0.30%\u505a\u591a \u2014 \u964dATR\u6269\u4e9a\u76d8\u6781\u81f4\u4fe1\u53f7\u6837\u672c",
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr14 / close > 0.0030",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "description": "\u4e9a\u76d8RSI<25\u76ee\u524dn=34(WR=85.29%)\uff0c\u964dATR\u81f30.30%\u9884\u671fn~60-80\uff0cWR\u7ea675-80%"
    },
    {
        "id": "round60_new_04",
        "priority": 2,
        "status": "pending",
        "hypothesis": "XAUUSD H1 \u7f8e\u76d8+RSI<30+ATR>0.35%\u505a\u591a hold=5 \u2014 \u6ce8\u5165\u4fe1\u53f7\u7684\u6700\u4f73\u6301\u6709\u671f\u63a2\u7d22",
        "entry_condition": "session == 'us' and rsi14 < 30 and atr14 / close > 0.0035",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "description": "\u57fa\u7ebfhold=7(71.49%)\uff0chold=5(66.38%)\u7565\u4f4e\u4f46MaxDD\u66f4\u5c0f\uff0c\u63a2\u7d22\u6700\u4f73\u76c8\u4e8f\u70b9"
    },
    {
        "id": "round60_new_05",
        "priority": 3,
        "status": "pending",
        "hypothesis": "XAGUSD H1 \u6b27\u76d8+RSI<25+ATR>0.50%\u505a\u591a hold=5 \u2014 XAG\u786e\u8ba4\u77ed\u671f\u8fb9\u9645",
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr14 / close > 0.0050",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAGUSD"],
        "description": "XAG\u6b27\u76d8\u964dATR\u81f30.40%\u540eWR\u65e0\u6539\u5584(63.22% vs 65.00%)\uff0c\u56de\u52300.50%\u786e\u8ba4\u8fb9\u9645\u4fe1\u53f7"
    },
    {
        "id": "round60_hibernate_01",
        "priority": 9,
        "status": "pending",
        "hypothesis": "XAUUSD\u7f8e\u76d8\u505a\u7a7a\u5168\u90e8\u5173\u95ed \u2014 \u6240\u6709\u7a7a\u5934\u6d4b\u8bd5FAILED",
        "direction": "short",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "description": "XAUUSD\u7f8e\u76d8RSI>65(WR<51%)\u3001RSI>70(61.48%\u4f46n=135\u4e0d\u8db3)\u5168\u90e8\u4e0d\u8fbe\u6807\uff0c\u505a\u7a7a\u65b9\u5411\u4f11\u7720"
    },
    {
        "id": "round60_hibernate_02",
        "priority": 9,
        "status": "pending",
        "hypothesis": "XAGUSD\u6b27\u76d8\u77ed\u671f\u4fe1\u53f7\u5173\u95ed \u2014 \u786e\u8ba4\u8fb9\u9645\u4ec5hold=5\u6709\u6548\u4e14\u4e0d\u53ef\u9760",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAGUSD"],
        "description": "XAGUSD\u6b27\u76d8\u6240\u6709\u53d8\u4f53\u6d4b\u8bd5\u5b8c\u6210\uff0c\u6700\u4f73\u4ec563.22%\u4e14\u9000\u5316\u8fc5\u901f\uff0c\u8c31\u7cfb\u5173\u95ed"
    }
]

state["hypothesis_queue"].extend(new_hypotheses)

with open("state/research_state.json", "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"Updated to round {state['current_round']}")
print(f"Total best_findings: {len(state['best_findings'])}")
print(f"Total hypothesis_queue: {len(state['hypothesis_queue'])}")
