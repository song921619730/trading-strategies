#!/usr/bin/env python3
"""Update research_state.json after Round 20 completion."""
import json
from pathlib import Path
from copy import deepcopy

state_path = Path(__file__).resolve().parent.parent / "state" / "research_state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))

# 1. Increment round
state["current_round"] = 20

# 2. Mark round18_a01 as tested
for h in state.get("hypothesis_queue", []):
    if h["id"] == "round18_a01":
        h["status"] = "tested"
        h["tested_at"] = "2026-05-11"
        h["result"] = {
            "verdict": "strong",
            "entry_condition": "(session == 'us') and (rsi14 < 40) and (atr14 / close > 0.0030)",
            "direction": "long",
            "timeframe": "M30",
            "best_params": {
                "symbol": "XAUUSD",
                "hold_period": 15,
                "win_rate": 0.6329,
                "signal_count": 1087,
                "avg_return": 0.001043,
                "sharpe_ratio": 3.07,
                "max_drawdown": 0.4737
            },
            "atr_gradient_findings": {
                "atr_0.25pct": {"win_rate": 0.6270, "n": 1697, "sharpe": 3.01},
                "atr_0.30pct": {"win_rate": 0.6329, "n": 1087, "sharpe": 3.07, "label": "VERIFIED"},
                "atr_0.35pct": {"win_rate": 0.6551, "n": 664, "sharpe": 2.90, "label": "NEW BEST"},
            },
            "cross_symbol": {
                "XAGUSD": {"win_rate": 0.5732, "n": 2924, "sharpe": 2.00, "label": "PROMISING"},
                "US30": {"win_rate": 0.5784, "n": 989, "sharpe": 0.14, "label": "PROMISING"},
                "US500": {"win_rate": 0.5609, "n": 1314, "sharpe": 0.02, "label": "PROMISING"},
            },
            "summary": "Round 20正式验证通过。XAUUSD M30美盘+RSI<40+ATR>0.30%做多hold=15精确复现63.29%(n=1,087, Sharpe=3.07)。声称值全部匹配。ATR梯度扫描发现>0.35%阈值胜率65.51%(n=664)为当前最高。跨品种验证通过：XAGUSD 57.32%(n=2,924), US30 57.84%(n=989)。"
        }
        break

# 3. Add best findings
new_findings = [
    {
        "id": "round20_001",
        "hypothesis": "XAUUSD M30 session=='us' + rsi14<40 + atr14/close>0.0030做多 hold=15 正式验证通过",
        "entry_condition": "(session == 'us') and (rsi14 < 40) and (atr14 / close > 0.0030)",
        "direction": "long",
        "timeframe": "M30",
        "symbols": ["XAUUSD"],
        "best_hold": 15,
        "metrics": {
            "win_rate": 0.6329,
            "avg_return": 0.001043,
            "sharpe_ratio": 3.07,
            "signal_count": 1087,
            "max_drawdown": 0.4737
        },
        "discovered_at": "2026-05-11",
        "status": "active",
        "summary": "XAUUSD M30美盘+RSI<40+ATR>0.30%做多hold=15精确复现63.29%(n=1,087, Sharpe=3.07)。相比无ATR过滤基线(60.35%)提升2.94pp，AvgRet翻倍(+96.4%)，Sharpe提升21.3%。称为本轮验证通过的基准策略。"
    },
    {
        "id": "round20_002",
        "hypothesis": "XAUUSD M30 session=='us' + rsi14<40 + atr14/close>0.0035做多 hold=15 胜率65.51%(待进一步验证)",
        "entry_condition": "(session == 'us') and (rsi14 < 40) and (atr14 / close > 0.0035)",
        "direction": "long",
        "timeframe": "M30",
        "symbols": ["XAUUSD"],
        "best_hold": 15,
        "metrics": {
            "win_rate": 0.6551,
            "avg_return": 0.001183,
            "sharpe_ratio": 2.90,
            "signal_count": 664,
            "max_drawdown": 0.4952
        },
        "discovered_at": "2026-05-11",
        "status": "active",
        "summary": "XAUUSD M30美盘+RSI<40+ATR>0.35%做多hold=15胜率65.51%(n=664, Sharpe=2.90)。ATR梯度扫描发现的最优胜率阈值，比ATR>0.30%版本高2.22pp，但信号量减少39%且Sharpe略低。需进一步验证稳定性。"
    },
]
state["best_findings"].extend(new_findings)

# 4. Add new hypotheses to queue
new_hypotheses = [
    {
        "id": "round20_a01",
        "hypothesis": "XAUUSD M30 美盘+RSI<40+ATR>0.35%做多 hold=10 验证65.51%胜率并寻找最优持有期",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 1,
        "source": "round20 B组测试：ATR>0.35% hold=15达65.51%(n=664)，但hold=10在ATR>0.30%时表现最优(63.11%, Sharpe=4.64)，需在ATR>0.35%下测试hold=10是否同样高效"
    },
    {
        "id": "round20_a02",
        "hypothesis": "XAUUSD M30 美盘+RSI<35+ATR>0.30%做多 极端超卖测试尝试推至65%+",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 1,
        "source": "round20 A组测试：当前RSI<40已达63.29%，收紧RSI阈值至35可能进一步筛选出更强反转信号"
    },
    {
        "id": "round20_a03",
        "hypothesis": "XAGUSD M30 美盘+RSI<40+ATR>0.30%做多 hold扫描(3-20) 贵金属扩展验证",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 1,
        "source": "round20 C组跨品种验证：XAGUSD在相同条件下达57.32%(n=2,924, Sharpe=2.00)，信号量充裕，需独立优化持有期和ATR阈值"
    },
    {
        "id": "round20_a04",
        "hypothesis": "US30 M30 美盘+RSI<40+ATR>0.30%做多 hold扫描(3-20) 美股指扩展验证",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 2,
        "source": "round20 C组跨品种验证：US30在相同条件下达57.84%(n=989)，但AvgRet极低(0.004%)，需确认是否为数据问题或信号噪音"
    },
]
state["hypothesis_queue"].extend(new_hypotheses)

# 5. Write back
state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"✅ State updated: current_round={state['current_round']}, fatigue={state.get('fatigue_count', 0)}, "
      f"queue_size={len([h for h in state.get('hypothesis_queue', []) if h.get('status')=='pending'])}")
print(f"   best_findings: {len(state['best_findings'])} total, +2 new (round20_001, round20_002)")
print(f"   new hypotheses added: round20_a01~a04")
