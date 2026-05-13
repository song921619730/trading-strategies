#!/usr/bin/env python3
"""Update research_state.json after testing round20_a01."""
import json
from pathlib import Path
from copy import deepcopy

state_path = Path(__file__).resolve().parent.parent / "state" / "research_state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))

# Results from backtest
# Best: hold=10 → 65.81% win rate, n=664, Sharpe=5.47, avg_return=0.00128
results = {
    3:  {"wr": 0.5783, "n": 664, "avg": 0.00022, "sharpe": 2.52, "dd": 0.1737},
    5:  {"wr": 0.5994, "n": 664, "avg": 0.00059, "sharpe": 4.73, "dd": 0.1831},
    7:  {"wr": 0.6205, "n": 664, "avg": 0.00083, "sharpe": 4.85, "dd": 0.2421},
    10: {"wr": 0.6581, "n": 664, "avg": 0.00128, "sharpe": 5.47, "dd": 0.2977},
    12: {"wr": 0.6476, "n": 664, "avg": 0.00147, "sharpe": 4.88, "dd": 0.3586},
    15: {"wr": 0.6551, "n": 664, "avg": 0.00118, "sharpe": 2.90, "dd": 0.4737},
    20: {"wr": 0.6130, "n": 664, "avg": 0.00051, "sharpe": 0.92, "dd": 0.6350},
}

# 1. Update current_round to 22
state["current_round"] = 22

# 2. Move round20_a01 from hypothesis_queue to tested_hypotheses
queue = state.get("hypothesis_queue", [])
round20_a01_entry = None
for i, h in enumerate(queue):
    if h["id"] == "round20_a01":
        round20_a01_entry = queue.pop(i)
        break

assert round20_a01_entry is not None, "round20_a01 not found in hypothesis_queue!"

# Mark as tested and add results
round20_a01_entry["status"] = "tested"
round20_a01_entry["tested_at"] = "2026-05-11"
round20_a01_entry["round"] = 22
round20_a01_entry["result"] = {
    "verdict": "strong",
    "description": "XAUUSD M30 session=='us' + rsi14<40 + atr14/close>0.0035 做多 hold扫描(3-20)完成。所有7个持有期均>57.8%，最佳为hold=10达65.81%(n=664, Sharpe=5.47)。",
    "best_params": {
        "symbol": "XAUUSD",
        "timeframe": "M30",
        "direction": "long",
        "entry_condition": "(session == 'us') and (rsi14 < 40) and (atr14 / close > 0.0035)",
        "hold_period": 10,
        "win_rate": 0.6581,
        "signal_count": 664,
        "avg_return": 0.00128,
        "sharpe_ratio": 5.47,
        "max_drawdown": 0.2977,
        "summary": "ATR>0.35%持有期扫描完成。hold=10以65.81%胜率(Sharpe=5.47)为最优，hold=15精确复现65.51%，hold=12为64.76%(AvgRet最高=0.147%)。所有持有期胜率超57.8%，远超基线。"
    },
    "all_holds": {str(k): {"wr": round(v["wr"], 4), "n": v["n"], "avg": round(v["avg"], 6), "sharpe": round(v["sharpe"], 2)} for k, v in sorted(results.items())},
    "summary": "Round 22 hold扫描完成。XAUUSD M30 session=='us' + rsi14<40 + atr14/close>0.0035做多，7个持有期(3/5/7/10/12/15/20)全部>57.8%。hold=10胜率65.81%(n=664, Sharpe=5.47)为全局最优——这是XAUUSD在M30上至今发现的最高胜率配置。相比Round 20基线(ATR>0.30%, hold=15, wr=63.29%, n=1,087)，提高ATR阈值至0.35%虽然信号量减少39%但胜率提升2.52pp，且hold=10的Sharpe(5.47)远优于基线(3.07)。原假设(hold=15验证65.51%)精确复现。最大发现：hold=10(65.81%)超过hold=15(65.51%)，持有期越短风险调整收益越高。"
}

# Add to tested_hypotheses at the beginning (most recent first)
state["tested_hypotheses"].insert(0, round20_a01_entry)

# 3. Add new best_finding (win_rate 65.81% >> 60%)
new_finding = {
    "id": "round22_001",
    "hypothesis": "XAUUSD M30 美盘+RSI<40+ATR>0.35%做多 hold=10 达65.81%——当前XAUUSD最优配置",
    "symbol": "XAUUSD",
    "timeframe": "M30",
    "direction": "long",
    "entry_condition": "(session == 'us') and (rsi14 < 40) and (atr14 / close > 0.0035)",
    "hold_period": 10,
    "win_rate": 0.6581,
    "signal_count": 664,
    "avg_return": 0.00128,
    "sharpe_ratio": 5.47,
    "max_drawdown": 0.2977,
    "discovered_at": "2026-05-11",
    "status": "active",
    "summary": "XAUUSD M30 session=='us'+RSI<40+ATR>0.35%做多hold=10胜率65.81%(n=664, Sharpe=5.47)——为XAUUSD在M30上至今发现的最高胜率配置。相比Round 20基线(ATR>0.30%, hold=15, 63.29%)提升2.52pp。所有7个持有期均>57.8%，信号稳健。"
}
state["best_findings"].append(new_finding)

# 4. Generate 1-2 follow-up hypotheses
new_hypotheses = [
    {
        "id": "round22_a01",
        "hypothesis": "XAUUSD M30 美盘+RSI<40+ATR>0.35%做多 hold=10 跨时间框架验证——H1上同样条件是否也能达65%+",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 1,
        "source": "round22: XAUUSD M30 ATR>0.35%做多hold=10达65.81%。H1上类似条件(round21_a01: session+ATR>0.25%+RSI<40, hold=15)达62.55%。提高H1的ATR阈值至0.35%是否也能推至65%+？同时验证M30和H1的跨框架一致性。"
    },
    {
        "id": "round22_a02",
        "hypothesis": "XAUUSD M30 美盘+RSI<40+ATR梯度(0.30%/0.35%/0.40%)做多 更极端ATR阈值测试能否突破66%",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 2,
        "source": "round22: ATR>0.35%达65.81%，推测更高ATR阈值(0.40%)可能进一步筛选极端行情，但信号量将减少。测试是否能在牺牲信号量下突破66%。"
    },
    {
        "id": "round22_a03",
        "hypothesis": "XAUUSD M30 美盘+RSI<40+ATR>0.35%做多 精细持有期扫描(8-11) 优化hold=10附近粒度",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 1,
        "source": "round22: hold=10(65.81%)>hold=12(64.76%)>hold=7(62.05%)，最优在10附近。hold=8/9/11的精细扫描可定位精确最优持有期。"
    }
]
state["hypothesis_queue"].extend(new_hypotheses)

# 5. Fatigue: no change (major discovery this round)
# state["fatigue_count"] stays at 1

# 6. Update the summary at the end
round_summary = {
    "timeframe": "M30",
    "hypothesis": "round20_a01: XAUUSD M30 美盘+RSI<40+ATR>0.35%做多 hold扫描寻找最优持有期",
    "verdict": "strong",
    "core_findings": [
        {
            "test": "hold_scan_3_20",
            "symbol": "XAUUSD",
            "entry_condition": "(session == 'us') and (rsi14 < 40) and (atr14 / close > 0.0035)",
            "direction": "long",
            "best_hold": 10,
            "win_rate": 0.6581,
            "signal_count": 664,
            "avg_return": 0.00128,
            "sharpe_ratio": 5.47,
            "max_drawdown": 0.2977
        }
    ],
    "all_holds": {
        str(k): {
            "win_rate": round(v["wr"], 4),
            "n": v["n"],
            "avg_return": round(v["avg"], 6),
            "sharpe": round(v["sharpe"], 2),
            "max_drawdown": round(v["dd"], 4)
        } for k, v in sorted(results.items())
    },
    "comparison_to_baseline": {
        "baseline": "Round 20: ATR>0.30%, hold=15, wr=63.29%, n=1087, Sharpe=3.07",
        "current_best": "Round 22: ATR>0.35%, hold=10, wr=65.81%, n=664, Sharpe=5.47",
        "delta_wr": "+2.52pp",
        "delta_sharpe": "+2.40",
        "signal_reduction": "-38.9%",
        "assessment": "更高ATR阈值+更短持有期带来显著改善。胜率提升2.52pp的同时Sharpe几乎翻倍，风险调整收益大幅提升。信号量减少但仍在合理范围(n=664)。"
    },
    "key_insights": [
        "XAUUSD M30 ATR>0.35%做多hold=10达65.81%(n=664, Sharpe=5.47)——为XAUUSD在M30上至今发现的最高胜率配置",
        "原假设hold=15验证65.51%精确复现——Round 20的ATR梯度扫描结果完全一致",
        "hold=10(65.81%)>hold=12(64.76%)>hold=15(65.51%)——最优持有期移至10，更短持有期Sharpe更高",
        "所有7个持有期全部>57.8%——hold=3最低57.83%也远超55%阈值，信号极其稳健",
        "hold=5达59.94%(Sharpe=4.73)接近60%强信号——短持有期选项同样优秀",
        "AvgReturn最高为hold=12(0.147%)——hold=10(0.128%)次之，均具有经济显著性",
        "MaxDD随持有期递增：hold=3(17.4%)→hold=10(29.8%)→hold=20(63.5%)——hold=10提供了最佳收益/风险平衡"
    ],
    "negative_findings": [
        "信号量从ATR>0.30%(n=1087)降至ATR>0.35%(n=664)，减少约39%——更严格阈值筛选掉了近四成信号",
        "hold=20最长持有期MaxDD达63.5%——过长持有期不适合该策略",
        "仅测试了XAUUSD单一品种，跨品种扩展尚未验证",
        "hold=10的AvgReturn(0.128%)虽经济显著但低于hold=12(0.147%)——最佳胜率并非最佳收益"
    ],
    "new_hypotheses_generated": [
        "round22_a01: XAUUSD H1 美盘+RSI<40+ATR>0.35%做多 hold=10 跨框架验证",
        "round22_a02: XAUUSD M30 美盘+RSI<40+ATR>0.40%做多 hold=10 更高ATR阈值测试",
        "round22_a03: XAUUSD M30 美盘+RSI<40+ATR>0.35%做多 hold=8/9/11精细扫描"
    ]
}

# Find the "summary" field at the end of state to update it
# The summary is at the very end of the file. Let me look at the structure.
# Actually, looking at the end of the file, it seems each round adds to a round-specific section.
# Let me just update the last "summary" field.

# Since the JSON has many nested round summaries, let me add a round22_summary
state["round22_summary"] = round_summary

# Also update the overall summary string
state["summary"] = "Round 22 M30完成round20_a01假设：XAUUSD M30美盘+RSI<40+ATR>0.35%做多持有期扫描(hold=3/5/7/10/12/15/20)。核心结论：(1)hold=10最优——65.81%(n=664, Sharpe=5.47)，为XAUUSD M30至今最高胜率配置。(2)原假设hold=15验证65.51%精确复现。(3)所有7个持有期全部>57.8%，信号极其稳健。(4)相比Round 20基线(ATR>0.30%, hold=15, 63.29%, Sharpe=3.07)，新配置胜率+2.52pp，Sharpe+2.40。(5)最佳配置：XAUUSD M30 session=='us' + rsi14<40 + atr14/close>0.0035 long hold=10 wr=65.81%。疲劳度维持1/5(有重大发现——65.81%为XAUUSD最高)。生成3个新假设(round22_a01~a03)。"

# 7. Write back
state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"✅ State updated: current_round={state['current_round']}, fatigue={state.get('fatigue_count', 0)}, "
      f"queue_size={len([h for h in state.get('hypothesis_queue', []) if h.get('status')=='pending'])}")
print(f"   best_findings: {len(state['best_findings'])} total, +1 new (round22_001)")
print(f"   new hypotheses added: round22_a01~a03")
