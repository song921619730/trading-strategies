#!/usr/bin/env python3
"""
update_state_round19.py — Update research_state.json with Round 19 results
"""

import json
import sys
from pathlib import Path

state_path = Path("/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/state/research_state.json")
state = json.loads(state_path.read_text())

# ------------------------------------------------------------------
# Update current_round
# ------------------------------------------------------------------
state["current_round"] = 19

# ------------------------------------------------------------------
# Add best_findings (win_rate > 60%)
# ------------------------------------------------------------------
new_findings = [
    {
        "id": "round19_001",
        "hypothesis": "XAUUSD H1 美盘+高ATR+RSI<35做多 hold=15 跨品种验证发现63.77%",
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "direction": "long",
        "entry_condition": "session == 'us' and atr14 / close > 0.0025 and rsi14 < 35",
        "hold_period": 15,
        "metrics": {
            "win_rate": 0.6377,
            "avg_return": 0.00054,
            "sharpe_ratio": 1.26,
            "signal_count": 933,
            "max_drawdown": 0.3547
        },
        "discovered_at": "2026-05-11",
        "status": "active",
        "summary": "XAUUSD H1美盘+高ATR(>0.25%)+RSI<35做多hold=15胜率63.77%(n=933, Sharpe=1.26)。跨品种验证发现XAUUSD在此配置下表现最强——hold=7也达61.52%(STRONG)。所有持有期(3-15)均保持>58%胜率。"
    },
    {
        "id": "round19_002",
        "hypothesis": "XAUUSD H1 美盘+高ATR+RSI<35做多 hold=7 短持有期强信号",
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "direction": "long",
        "entry_condition": "session == 'us' and atr14 / close > 0.0025 and rsi14 < 35",
        "hold_period": 7,
        "metrics": {
            "win_rate": 0.6152,
            "avg_return": 0.00055,
            "sharpe_ratio": 2.53,
            "signal_count": 933,
            "max_drawdown": 0.1778
        },
        "discovered_at": "2026-05-11",
        "status": "active",
        "summary": "XAUUSD H1美盘+高ATR(>0.25%)+RSI<35做多hold=7胜率61.52%(n=933, Sharpe=2.53)。短持有期具有更好的风险调整回报，MaxDD仅0.1778。跨品种验证中XAUUSD在所有测试品种中表现最优。"
    }
]

state["best_findings"].extend(new_findings)

# ------------------------------------------------------------------
# Add round19_summary
# ------------------------------------------------------------------
state["round19_summary"] = {
    "timeframe": "H1",
    "hypothesis": "round17_a01: EURUSD H1 美盘+高ATR+RSI<35做多 hold=7 尝试推至68%+",
    "verdict": "promising",
    "core_findings": [
        {
            "test": "A_main_hypothesis",
            "description": "EURUSD H1 session=='us' + atr14/close>0.0025 + rsi14<35 做多 持有期扫描(hold=3/5/7/10/12/15)",
            "results": {
                "hold_3": {"win_rate": 0.6179, "n": 123, "sharpe": 3.71, "label": "STRONG"},
                "hold_5": {"win_rate": 0.6667, "n": 123, "sharpe": 5.94, "label": "STRONG"},
                "hold_7": {"win_rate": 0.6748, "n": 123, "sharpe": 7.31, "label": "STRONG (67.48%)"},
                "hold_10": {"win_rate": 0.6585, "n": 123, "sharpe": 7.24, "label": "STRONG"},
                "hold_12": {"win_rate": 0.6179, "n": 123, "sharpe": 5.97, "label": "STRONG"},
                "hold_15": {"win_rate": 0.6179, "n": 123, "sharpe": 3.22, "label": "STRONG"}
            },
            "verdict": "RSI<35: 67.48%略高于RSI<40基线(67.36%)，但信号数从193降至123(-36%)，Sharpe从8.24降至7.31"
        },
        {
            "test": "B_rsi_threshold_scan",
            "description": "EURUSD H1 RSI阈值梯度扫描 hold=7固定 (RSI<33/35/37/38/39/40)",
            "results": {
                "RSI_33": {"win_rate": 0.6136, "n": 88, "sharpe": 2.40, "label": "STRONG"},
                "RSI_35": {"win_rate": 0.6748, "n": 123, "sharpe": 7.31, "label": "STRONG"},
                "RSI_37": {"win_rate": 0.6714, "n": 140, "sharpe": 6.81, "label": "STRONG"},
                "RSI_38": {"win_rate": 0.6554, "n": 148, "sharpe": 6.30, "label": "STRONG"},
                "RSI_39": {"win_rate": 0.6786, "n": 168, "sharpe": 7.92, "label": "STRONG (最高胜率)"},
                "RSI_40": {"win_rate": 0.6736, "n": 193, "sharpe": 8.24, "label": "BASELINE (最优composite)"}
            },
            "optimal_by_composite": "RSI<40 (composite=9.36, wr=67.36%, n=193, Sharpe=8.24)",
            "verdict": "RSI<40仍为最优阈值。RSI<39有最高胜率(67.86%)但Sharpe略低。RSI<35提升微不足道(+0.12%)"
        },
        {
            "test": "C_cross_symbol",
            "description": "跨品种验证 美盘+高ATR+RSI<35做多 (XAUUSD/US500/GBPUSD/US30/XAGUSD/USTEC)",
            "results_hold7": {
                "XAUUSD": {"win_rate": 0.6152, "n": 933, "sharpe": 2.53, "label": "STRONG"},
                "US30": {"win_rate": 0.5832, "n": 679, "sharpe": 1.61, "label": "PROMISING"},
                "US500": {"win_rate": 0.5792, "n": 758, "sharpe": 1.54, "label": "PROMISING"},
                "XAGUSD": {"win_rate": 0.5660, "n": 993, "sharpe": 0.44, "label": "PROMISING"},
                "GBPUSD": {"win_rate": 0.5625, "n": 192, "sharpe": -2.21, "label": "PROMISING (负Sharpe)"},
                "USTEC": {"win_rate": 0.5488, "n": 1086, "sharpe": 0.23, "label": "WEAK"}
            },
            "best_hold15": {
                "XAUUSD": {"win_rate": 0.6377, "n": 933, "sharpe": 1.26, "label": "★★ STRONG (63.77%)"}
            },
            "verdict": "XAUUSD为跨品种验证最大发现——所有持有期均>58.8%，hold=15达63.77%。US30/US500稳健~58%。USTEC最弱<55%。"
        }
    ],
    "key_insights": [
        "EURUSD H1 美盘+高ATR+RSI<35做多hold=7胜率67.48%(n=123, Sharpe=7.31)略高于RSI<40基线(67.36%)，但提升仅+0.12个百分点——在统计误差范围内",
        "信号数从193降至123(-36%)——以大幅减少信号量为代价换取了微不足道的胜率提升",
        "RSI阈值梯度扫描显示RSI<40(composite=9.36)仍为最优阈值，RSI<39有最高胜率(67.86%)但综合评分低于RSI<40",
        "跨品种验证的最大发现是XAUUSD——美盘+高ATR+RSI<35做多hold=15达63.77%(n=933, Sharpe=1.26)，hold=7达61.52%",
        "XAUUSD所有测试持有期(3-15)均保持>58%胜率，在6个跨品种中表现最优",
        "US30(58.32%)和US500(57.92%)在hold=7表现稳健，USTEC最弱(54.88%)",
        "GBPUSD虽然胜率56.25%但Sharpe为负(-2.21)——高胜率但负收益的异常模式"
    ],
    "negative_findings": [
        "EURUSD RSI<35相比RSI<40仅提升0.12%——不足以证明更严格RSI阈值有效",
        "信号数从193降至123(-36%)但胜率几乎不变——RSI<35过滤掉了大量有效信号",
        "68%目标未达成——最高67.86%(RSI<39)仍低于68%",
        "GBPUSD高胜率但负avg_return(avg=-0.00046, Sharpe=-2.21)——高胜率低收益陷阱",
        "USTEC全持有期<55%——科技股在此策略下无效"
    ],
    "new_hypotheses_generated": [
        "round19_a01: XAUUSD H1 美盘+高ATR+RSI<35做多 hold=15 正式验证63.77%并尝试推至65%+",
        "round19_a02: XAUUSD H1 美盘+高ATR+RSI<35做多 vs RSI<40 阈值对比(63.77% vs baseline?) 确认最优RSI值",
        "round19_a03: EURUSD H1 美盘+高ATR+RSI<39做多 hold=7 验证67.86%是否可复现（RSI梯度中最高胜率）",
        "round19_a04: XAUUSD H1 美盘+高ATR+RSI<40做多 验证跨品种强信号一致性（从XAUUSD扩展到EURUSD模式）"
    ],
    "summary": "Round 19 H1完成round17_a01假设测试：EURUSD H1美盘+高ATR+RSI<35做多尝试推至68%+。完成3组测试：主假设(A)、RSI阈值梯度扫描(B)、跨品种验证(C)。核心结论：(1)主假设通过但提升微弱——RSI<35 hold=7胜率67.48%(n=123, Sharpe=7.31)仅比RSI<40基线(67.36%)高0.12pp，68%目标未达成。(2)RSI阈值梯度扫描确认RSI<40仍为最优阈值(composite=9.36) ——RSI<39有最高胜率(67.86%)但综合评分低于RSI<40。(3)跨品种验证最大发现：XAUUSD美盘+高ATR+RSI<35做多hold=15达63.77%(n=933, Sharpe=1.26)为STRONG信号！hold=7也达61.52%(Sharpe=2.53)。(4)US30(58.32%)和US500(57.92%)稳健达到PROMISING。USTEC最弱(54.88%)。(5)新增2个best_findings(round19_001~002: XAUUSD RSI<35 hold=15 63.77%和hold=7 61.52%)。疲劳度从1/5维持1/5(有发现但主要假设未达目标，以跨品种发现作为补偿)。生成4个新假设(round19_a01~a04)。"
}

# ------------------------------------------------------------------
# Fatigue check
# ------------------------------------------------------------------
# Round 18 fatigue was 1/5. Round 19 has findings (cross-symbol XAUUSD)
# so consecutive counter resets, fatigue stays at 1.
# Let me check if fatigue_count exists
if "fatigue_count" not in state:
    state["fatigue_count"] = 1  # inherited from round18 summary
# With new findings, fatigue stays at 1 (consecutive counter resets)

# ------------------------------------------------------------------
# Write back
# ------------------------------------------------------------------
state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
print(f"✅ State updated: current_round={state['current_round']}, fatigue_count={state.get('fatigue_count', 'N/A')}")
print(f"   New findings: {len(new_findings)}")
print(f"   Total best_findings: {len(state['best_findings'])}")
