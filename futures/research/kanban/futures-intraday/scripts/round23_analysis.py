#!/usr/bin/env python3
"""Round 23 analysis: update research_state.json with findings."""
import json
from pathlib import Path

state_path = Path("../state/research_state.json")
state = json.loads(state_path.read_text())

# =====================================================================
# Test (a) results
# =====================================================================
core_holds = {
    "3":  {"win_rate": 0.5943, "n": 705, "avg_return": 0.00044, "sharpe": 3.60, "max_drawdown": 0.1219},
    "5":  {"win_rate": 0.6184, "n": 705, "avg_return": 0.00086, "sharpe": 4.39, "max_drawdown": 0.1802},
    "7":  {"win_rate": 0.6298, "n": 705, "avg_return": 0.00099, "sharpe": 3.25, "max_drawdown": 0.2757},
    "10": {"win_rate": 0.5957, "n": 705, "avg_return": 0.00056, "sharpe": 1.26, "max_drawdown": 0.3945},
    "12": {"win_rate": 0.6028, "n": 705, "avg_return": 0.00043, "sharpe": 0.84, "max_drawdown": 0.4565},
    "15": {"win_rate": 0.6085, "n": 705, "avg_return": 0.00036, "sharpe": 0.63, "max_drawdown": 0.4313},
    "20": {"win_rate": 0.5546, "n": 705, "avg_return": -0.00066,"sharpe": -0.84,"max_drawdown": 0.5907},
}

cross_results = {
    "XAUUSD": {"n": 705,  "win_rate": 0.5957, "avg_return": 0.00056, "sharpe": 1.26, "max_drawdown": 0.3945},
    "XAGUSD": {"n": 1847, "win_rate": 0.5463, "avg_return": 0.00060, "sharpe": 1.08, "max_drawdown": 0.5884},
    "EURUSD": {"n": 14,   "win_rate": 0.9286, "avg_return": 0.00358, "sharpe": 33.38,"max_drawdown": 0.0000},
    "GBPUSD": {"n": 53,   "win_rate": 0.6226, "avg_return": -0.00162,"sharpe": -4.13,"max_drawdown": 0.1664},
    "USDJPY": {"n": 118,  "win_rate": 0.5169, "avg_return": -0.00040,"sharpe": -1.20,"max_drawdown": 0.2176},
    "AUDUSD": {"n": 94,   "win_rate": 0.6064, "avg_return": 0.00144, "sharpe": 6.75, "max_drawdown": 0.0399},
    "USDCHF": {"n": 54,   "win_rate": 0.4074, "avg_return": -0.00087,"sharpe": -4.18,"max_drawdown": 0.1029},
    "USOIL":  {"n": 2028, "win_rate": 0.5256, "avg_return": 0.00071, "sharpe": 1.36, "max_drawdown": 0.7048},
    "UKOIL":  {"n": 1477, "win_rate": 0.5471, "avg_return": 0.00104, "sharpe": 1.81, "max_drawdown": 0.4973},
    "USTEC":  {"n": 1301, "win_rate": 0.5673, "avg_return": 0.00020, "sharpe": 0.52, "max_drawdown": 0.4489},
    "US30":   {"n": 517,  "win_rate": 0.5938, "avg_return": 0.00035, "sharpe": 1.03, "max_drawdown": 0.2469},
    "US500":  {"n": 691,  "win_rate": 0.5485, "avg_return": 0.00016, "sharpe": 0.44, "max_drawdown": 0.3120},
    "JP225":  {"n": 671,  "win_rate": 0.5633, "avg_return": 0.00044, "sharpe": 0.78, "max_drawdown": 0.6096},
    "HK50":   {"n": 735,  "win_rate": 0.5279, "avg_return": 0.00065, "sharpe": 1.16, "max_drawdown": 0.5851},
}

# =====================================================================
# Identify best findings (>60% with n>=30)
# =====================================================================
new_findings = []

# XAUUSD hold=7 is the best: 62.98%, n=705, Sharpe=3.25
new_findings.append({
    "id": "round23_001",
    "hypothesis": "XAUUSD H1 session=='us' + rsi14<40 + atr14/close>0.0035做多 hold=7 达62.98% 跨框架验证强信号",
    "symbol": "XAUUSD",
    "timeframe": "H1",
    "direction": "long",
    "entry_condition": "session == 'us' and rsi14 < 40 and atr14 / close > 0.0035",
    "hold_period": 7,
    "win_rate": 0.6298,
    "signal_count": 705,
    "avg_return": 0.00099,
    "sharpe_ratio": 3.25,
    "max_drawdown": 0.2757,
    "discovered_at": "2026-05-11",
    "status": "active",
    "summary": "XAUUSD H1美盘+RSI<40+ATR>0.35%做多hold=7胜率62.98%(n=705, Sharpe=3.25)——跨框架验证M30 65.81%强信号成功。H1上最佳持有期从ATR>0.25%的hold=15(62.55%)提前至hold=7(62.98%)，更高ATR阈值+更短持有期带来更优风险调整。所有持有期(3-15)均>59%——信号极其稳健。"
})

# AUDUSD hold=10: 60.64%, n=94, Sharpe=6.75
new_findings.append({
    "id": "round23_002",
    "hypothesis": "AUDUSD H1 美盘+RSI<40+ATR>0.35%做多 hold=10 达60.64% 跨品种新发现",
    "symbol": "AUDUSD",
    "timeframe": "H1",
    "direction": "long",
    "entry_condition": "session == 'us' and rsi14 < 40 and atr14 / close > 0.0035",
    "hold_period": 10,
    "win_rate": 0.6064,
    "signal_count": 94,
    "avg_return": 0.00144,
    "sharpe_ratio": 6.75,
    "max_drawdown": 0.0399,
    "discovered_at": "2026-05-11",
    "status": "active",
    "summary": "AUDUSD H1美盘+RSI<40+ATR>0.35%做多hold=10胜率60.64%(n=94, Sharpe=6.75, MaxDD=0.0399)——跨品种验证中意外发现AUDUSD达到60%+强信号阈值。Sharpe=6.75及超低MaxDD(0.0399)表明信号质量极高，但样本量仅94偏低，需扩大验证。"
})

# =====================================================================
# Comparison with Round 21 baseline
# =====================================================================
baseline_comparison = {
    "Round21_baseline": "XAUUSD H1 session=='us' + ATR>0.25% + RSI<40 long hold=15 wr=62.55% n=1,530 Sharpe=1.49",
    "Round23_current_best": "XAUUSD H1 session=='us' + ATR>0.35% + RSI<40 long hold=7 wr=62.98% n=705 Sharpe=3.25",
    "delta_wr": "+0.43pp (hold=7 vs baseline hold=15)",
    "delta_sharpe": "+1.76 (3.25 vs 1.49)",
    "signal_reduction": "-53.9% (705 vs 1,530)",
    "assessment": "ATR>0.35%在H1上并未在相同持有期(hold=15)超越ATR>0.25%基线(60.85% vs 62.55%)。但更高ATR阈值将最优持有期从15前移至5-7，hold=7的62.98%略高于基线62.55%且Sharpe翻倍(3.25 vs 1.49)。核心价值在于持有期缩短+风险调整改善。与M30上ATR>0.35%的效果类似但幅度温和——M30从ATR>0.30%(63.29%)提至ATR>0.35% hold=10(65.81%)提升2.52pp，H1从ATR>0.25%(62.55%)提至ATR>0.35% hold=7(62.98%)仅提升0.43pp。"
}

# =====================================================================
# New hypotheses to add to queue
# =====================================================================
new_hypotheses = [
    {
        "id": "round23_a01",
        "hypothesis": "AUDUSD H1 美盘+RSI<40+ATR>0.35%做多 hold=10 扩大样本验证60.64%强信号",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 1,
        "source": "round23: AUDUSD意外达60.64%但n=94仅，需确认稳定性。M30上同样条件是否更强？"
    },
    {
        "id": "round23_a02",
        "hypothesis": "XAUUSD H1 美盘+RSI<40+ATR>0.35%做多 hold=5/7精细扫描(hold=4/6/8) 寻找62.98%以上参数",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 1,
        "source": "round23: XAUUSD H1 hold=7达62.98%为峰值，但附近持有期(5/10)可能更优。精细扫描hold=4/6/8确认最优。"
    },
    {
        "id": "round23_a03",
        "hypothesis": "US30 H1 美盘+RSI<40+ATR>0.35%做多 hold=10 59.38%——加ATR阈值扫描尝试突破60%",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 2,
        "source": "round23: US30达59.38%(n=517)距60%仅0.62pp。降低/提高ATR阈值或缩短持有期可能推至60%+"
    },
    {
        "id": "round23_a04",
        "hypothesis": "AUDUSD H1 美盘+RSI<40+ATR>0.35%做多 M30跨框架验证60.64%是否更强",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 2,
        "source": "round23: AUDUSD在H1上达60.64%——与XAUUSD类似模式，M30上可能更强"
    },
]

# =====================================================================
# Update state
# =====================================================================

# 1. Add round23_summary
state["round23_summary"] = {
    "timeframe": "H1",
    "hypothesis": "round22_a01: XAUUSD H1 美盘+RSI<40+ATR>0.35%做多 hold扫描+跨品种验证 跨框架验证",
    "verdict": "strong",
    "core_findings": [
        {
            "test": "hold_scan_3_20",
            "symbol": "XAUUSD",
            "entry_condition": "session == 'us' and rsi14 < 40 and atr14 / close > 0.0035",
            "direction": "long",
            "best_hold": 7,
            "win_rate": 0.6298,
            "signal_count": 705,
            "avg_return": 0.00099,
            "sharpe_ratio": 3.25,
            "max_drawdown": 0.2757
        }
    ],
    "all_holds": core_holds,
    "cross_symbol_hold10": cross_results,
    "comparison_to_baseline": baseline_comparison,
    "key_insights": [
        "XAUUSD H1 ATR>0.35%做多hold=7达62.98%(n=705, Sharpe=3.25)——跨框架验证M30 65.81%强信号在H1上同样有效",
        "最优持有期从ATR>0.25%的hold=15前移至hold=7——更高ATR阈值+更短持有期改善风险调整",
        "所有7个持有期(3-20)均>55%——hold=20(55.46%)唯一低于59%但仍高于55%阈值",
        "hold=5(61.84%, Sharpe=4.39)和hold=7(62.98%, Sharpe=3.25)为最优双持有期——均>60%",
        "相比Round21基线(ATR>0.25%, hold=15, 62.55%)——相同条件hold=15降至60.85%，但hold=7的62.98%+Sharpe3.25全面超越",
        "跨品种验证发现AUDUSD达60.64%(n=94, Sharpe=6.75)——风险资产在美盘+高ATR的超卖信号集群再次得到验证",
        "GBPUSD达62.26%(n=53)但avg_return为负(-0.16%)——高胜率低收益陷阱持续存在",
        "EURUSD仅14个信号(高ATR条件在EURUSD上极罕见)——EURUSD不适合高ATR>0.35%条件",
        "USDCHF(40.74%)和USDJPY(51.69%)继续表现最差——避险货币在美盘+高ATR的超卖信号方向矛盾",
        "US30(59.38%)接近60%——美股指在ATR>0.35%条件下信号强度中等(59%左右)"
    ],
    "negative_findings": [
        "信号量从ATR>0.25%(n=1,530)降至ATR>0.35%(n=705)，减少约54%——更严格阈值筛掉了超半数信号",
        "hold=20最长持有期avg_return为负(-0.07%)——过长持有期不适合该策略",
        "相比M30上ATR>0.35%的65.81%大幅优于ATR>0.30%的63.29%(+2.52pp)，H1上ATR>0.35%最佳仅62.98%略高于ATR>0.25%的62.55%(+0.43pp)——H1上ATR阈值提升效果远不如M30显著",
        "AUDUSD(60.64%)和GBPUSD(62.26%)样本量均<100——需至少n>300才能确认强信号可靠性"
    ],
    "new_hypotheses_generated": [
        "round23_a01: AUDUSD H1 美盘+RSI<40+ATR>0.35%做多 hold=10 扩大样本验证60.64%强信号",
        "round23_a02: XAUUSD H1 美盘+RSI<40+ATR>0.35%做多 hold=5/7精细扫描",
        "round23_a03: US30 H1 美盘+RSI<40+ATR>0.35%做多 hold=10 加ATR阈值扫描尝试突破60%",
        "round23_a04: AUDUSD H1 美盘+RSI<40+ATR>0.35%做多 M30跨框架验证"
    ]
}

# 2. Add best findings (only >60% with n>=30)
existing_ids = {f["id"] for f in state["best_findings"]}
for nf in new_findings:
    if nf["id"] not in existing_ids:
        state["best_findings"].append(nf)
        existing_ids.add(nf["id"])

# 3. Update current round
state["current_round"] = 23

# 4. Add new hypotheses to queue
existing_hyp_ids = {h["id"] for h in state["hypothesis_queue"]}
for nh in new_hypotheses:
    if nh["id"] not in existing_hyp_ids:
        state["hypothesis_queue"].append(nh)
        existing_hyp_ids.add(nh["id"])

# 5. Update fatigue (Round 22 had a finding, this round also has findings → no fatigue increase)
# Fatigue stays at its current level. There's no fatigue_count field explicitly, 
# but the Round 22 summary says "疲劳度维持1/5(有重大发现)"
# Since we also made findings this round, fatigue remains low.
# But there's no explicit fatigue_count key - let me check and add one if needed.
state["fatigue_count"] = state.get("fatigue_count", 0)  # stays same since we have findings
state["consecutive_empty_rounds"] = 0  # reset since we have findings

# Also update summary
state["summary"] = (
    "Round 23 H1完成round22_a01假设：XAUUSD H1美盘+RSI<40+ATR>0.35%做多持有期扫描(hold=3/5/7/10/12/15/20)+跨品种验证(14 symbols, hold=10)。"
    "核心结论：(1)跨框架验证M30 65.81%强信号在H1上成功——hold=7达62.98%(n=705, Sharpe=3.25)为STRONG信号。"
    "(2)ATR>0.35%在H1上最优持有期从ATR>0.25%的hold=15前移至hold=7——更短持有期+更好风险调整。"
    "(3)但ATR阈值提升效果远不如M30显著——H1上62.98% vs M30上65.81%。"
    "(4)跨品种验证发现AUDUSD达60.64%(n=94, Sharpe=6.75)——为新品种额外发现。"
    "(5)GBPUSD(62.26%, n=53)高胜率但avg_return为负——验证收益陷阱。"
    "(6)USDCHF(40.74%)和USDJPY(51.69%)继续失败——避险货币做多完全无效。"
    "(7)US30达59.38%(n=517)接近60%——美股指方向性偏多信号一致。"
    "新增2个best_findings(round23_001~002: XAUUSD 62.98% + AUDUSD 60.64%)。"
    "疲劳度维持低水平(有重大发现)。生成4个新假设(round23_a01~a04)。"
)

state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
print("✅ research_state.json updated successfully")
print(f"   Current round: {state['current_round']}")
print(f"   Best findings: {len(state['best_findings'])}")
print(f"   Hypothesis queue: {len(state['hypothesis_queue'])}")
print(f"   Fatigue: {state['fatigue_count']}/5")
