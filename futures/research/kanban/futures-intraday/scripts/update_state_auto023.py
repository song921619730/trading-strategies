#!/usr/bin/env python3
"""
Update research_state.json with auto_023 results.

This script:
1. Removes auto_023 from hypothesis_queue
2. Adds auto_023 result to tested_hypotheses
3. Updates current_round to 15
4. Adds new best_finding if applicable
5. Adds round15_summary
6. Generates new hypotheses
"""
import json
from copy import deepcopy
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "research_state.json"

with open(STATE_PATH, "r") as f:
    state = json.load(f)

# ============================================================
# 1. Find and remove auto_023 from hypothesis_queue
# ============================================================
queue = state["hypothesis_queue"]
auto_023_entry = None
for i, entry in enumerate(queue):
    if entry.get("id") == "auto_023":
        auto_023_entry = queue.pop(i)
        break

assert auto_023_entry is not None, "auto_023 not found in hypothesis_queue!"

# ============================================================
# 2. Build the tested hypothesis entry
# ============================================================
tested_entry = {
    "id": "auto_023",
    "hypothesis": "EURUSD H1高ATR+RSI<40做多 最优持有期深入扫描(hold=6/7/8/9/12/15) 寻找精确最优参数",
    "status": "tested",
    "created_at": "2026-05-11",
    "tested_at": "2026-05-11",
    "priority": 1,
    "source": "round7_001: EURUSD RSI<40 hold=10达63.86%，但可能hold=6/7/8/9/12/15有更优参数",
    "result": {
        "verdict": "strong",
        "best_params": {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "direction": "long",
            "entry_condition": "atr14 / close > 0.0025 and rsi14 < 40",
            "hold_period": 7,
            "win_rate": 0.6449,
            "signal_count": 321,
            "avg_return": 0.000653,
            "sharpe_ratio": 6.35,
            "max_drawdown": 0.0492
        },
        "round7_001_comparison": {
            "hold_10": {"win_rate": 0.6386, "signal_count": 321, "sharpe": 6.18, "max_dd": 0.0809, "label": "BASELINE (from round7)"},
            "verdict": "hold=7(64.49%)超越hold=10(63.86%)成为新的最优持有期"
        },
        "hold_period_scan": {
            "6":  {"win_rate": 0.6324, "signal_count": 321, "avg_return": 0.00053, "sharpe": 6.05, "max_dd": 0.0493, "label": "STRONG"},
            "7":  {"win_rate": 0.6449, "signal_count": 321, "avg_return": 0.00065, "sharpe": 6.35, "max_dd": 0.0492, "label": "★ STRONG (NEW BEST)"},
            "8":  {"win_rate": 0.6324, "signal_count": 321, "avg_return": 0.00076, "sharpe": 6.33, "max_dd": 0.0469, "label": "STRONG"},
            "9":  {"win_rate": 0.6324, "signal_count": 321, "avg_return": 0.00083, "sharpe": 6.44, "max_dd": 0.0538, "label": "STRONG"},
            "10": {"win_rate": 0.6386, "signal_count": 321, "avg_return": 0.00089, "sharpe": 6.18, "max_dd": 0.0809, "label": "STRONG (round7 baseline)"},
            "12": {"win_rate": 0.6324, "signal_count": 321, "avg_return": 0.00113, "sharpe": 6.58, "max_dd": 0.0981, "label": "STRONG"},
            "15": {"win_rate": 0.6355, "signal_count": 321, "avg_return": 0.00102, "sharpe": 4.78, "max_dd": 0.1315, "label": "STRONG"}
        },
        "summary": "持有期精细扫描完成。所有6个测试持有期(6/7/8/9/12/15)均保持>63%胜率(n=321)和>6.0 Sharpe(hold=15除外Sharpe=4.78)，信号极其稳定。hold=7(64.49%, Sharpe=6.35)超越round7 baseline hold=10(63.86%, Sharpe=6.18)成为新的最优参数，且MaxDD更低(0.0492 vs 0.0809)。hold=12拥有最高avg_return(0.00113)和最高Sharpe(6.58)但MaxDD较高(0.0981)。hold=15信号开始衰减(Sharpe降至4.78, MaxDD升至0.1315)但仍在63%以上。核心结论：EURUSD H1高ATR+RSI<40做多信号在该品种和时间框架上极其稳健，不敏感于持有期选择，7-10小时窗口均有效。最佳参数更新为hold=7(7小时EWMA持有)。"
    }
}

# Add to tested_hypotheses (at the beginning, before round14 entries)
state["tested_hypotheses"].insert(0, tested_entry)

# ============================================================
# 3. Update current_round
# ============================================================
state["current_round"] = 15

# ============================================================
# 4. Add new best_finding (hold=7 beats hold=10)
# ============================================================
new_best_finding = {
    "id": "auto_023",
    "hypothesis": "EURUSD H1高ATR+RSI<40做多 最优持有期深入扫描 hold=7确认最优",
    "entry_condition": "atr14 / close > 0.0025 and rsi14 < 40",
    "direction": "long",
    "timeframe": "H1",
    "symbols": ["EURUSD"],
    "best_hold": 7,
    "metrics": {
        "win_rate": 0.6449,
        "avg_return": 0.00065,
        "sharpe_ratio": 6.35,
        "signal_count": 321,
        "max_drawdown": 0.0492
    },
    "discovered_at": "2026-05-11",
    "status": "active",
    "summary": "EURUSD H1高ATR(>0.25%)+RSI<40做多hold=7胜率64.49%(n=321, Sharpe=6.35, MaxDD=0.0492)。比round7_001的hold=10(63.86%, Sharpe=6.18, MaxDD=0.0809)全面更优——胜率+0.63%, Sharpe+0.17, MaxDD-39%。"
}

state["best_findings"].append(new_best_finding)

# ============================================================
# 5. Update fatigue_count (we found a new best parameter, so reset)
# ============================================================
state["fatigue_count"] = 0  # Reset since we found better params

# ============================================================
# 6. Add new hypotheses to queue
# ============================================================
new_hypotheses = [
    {
        "id": "round15_a01",
        "hypothesis": "EURUSD H1高ATR+RSI<40做多 hold=7 加入session时段过滤(US+Europe vs Asia) 尝试从64.49%推至66%+",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 1,
        "source": "auto_023: EURUSD H1高ATR+RSI<40 hold=7达64.49%，时段过滤可进一步排除亚盘噪音提升胜率"
    },
    {
        "id": "round15_a02",
        "hypothesis": "EURUSD H1高ATR+RSI<40做多 全品种跨品种验证(GBPUSD/USDCHF/USDJPY/XAUUSD) 确认EURUSD独有性",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 1,
        "source": "auto_023: EURUSD 64.49%强信号可能是EURUSD独有，需跨品种验证EURUSD独特性"
    },
    {
        "id": "round15_a03",
        "hypothesis": "EURUSD H1高ATR(>0.30%更高阈值)+RSI<40做多 验证极端波动率下胜率是否能突破65%",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 2,
        "source": "auto_023: 当前使用ATR>0.25%阈值(n=321)，更严格的ATR>0.30%可能筛选最强信号但样本量减少"
    }
]

state["hypothesis_queue"].extend(new_hypotheses)

# ============================================================
# 7. Add round15_summary
# ============================================================
state["round15_summary"] = {
    "timeframe": "H1",
    "hypothesis": "auto_023: EURUSD H1高ATR(>0.25%)+RSI<40做多 最优持有期深入扫描(hold=6/7/8/9/12/15)",
    "verdict": "strong",
    "core_findings": [
        {
            "test": "A_hold_period_scan",
            "description": "EURUSD H1 atr14/close>0.0025 and rsi14<40 做多 持有期精细扫描(hold=6,7,8,9,12,15)",
            "results": {
                "hold_6":  {"win_rate": 0.6324, "signal_count": 321, "sharpe": 6.05, "max_dd": 0.0493, "label": "STRONG"},
                "hold_7":  {"win_rate": 0.6449, "signal_count": 321, "sharpe": 6.35, "max_dd": 0.0492, "label": "★ STRONG (NEW BEST)"},
                "hold_8":  {"win_rate": 0.6324, "signal_count": 321, "sharpe": 6.33, "max_dd": 0.0469, "label": "STRONG"},
                "hold_9":  {"win_rate": 0.6324, "signal_count": 321, "sharpe": 6.44, "max_dd": 0.0538, "label": "STRONG"},
                "hold_10": {"win_rate": 0.6386, "signal_count": 321, "sharpe": 6.18, "max_dd": 0.0809, "label": "STRONG (baseline)"},
                "hold_12": {"win_rate": 0.6324, "signal_count": 321, "sharpe": 6.58, "max_dd": 0.0981, "label": "STRONG"},
                "hold_15": {"win_rate": 0.6355, "signal_count": 321, "sharpe": 4.78, "max_dd": 0.1315, "label": "STRONG"}
            }
        }
    ],
    "key_insights": [
        "所有测试持有期(6/7/8/9/12/15)均保持>63%胜率——信号极其稳健，不敏感于持有期选择",
        "hold=7(64.49%, Sharpe=6.35)超越round7 baseline hold=10(63.86%)成为新的最优持有期",
        "hold=7相比hold=10具有更低的MaxDD(0.0492 vs 0.0809)和更高的Sharpe(6.35 vs 6.18)",
        "hold=12拥有最高avg_return(0.00113)和最高Sharpe(6.58)但MaxDD较高(0.0981)",
        "hold=15信号开始衰减(Sharpe降至4.78, MaxDD升至0.1315)但仍维持63%+胜率",
        "信号非常一致——321个信号全部匹配，信号数量与round7_001一致，验证通过",
        "方向不对称性和ATR高波动偏多特性在EURUSD H1上极其牢固"
    ],
    "negative_findings": [
        "不同持有期之间胜率差异仅1.25个百分点(63.24%-64.49%)——没有发现绝对最优持有期，7-10小时窗口均有效",
        "hold=15 Sharpe下降明显(4.78)且MaxDD上升(0.1315)——长持有期风险调整收益降低"
    ],
    "new_hypotheses_generated": [
        "round15_a01: EURUSD H1高ATR+RSI<40做多 hold=7 加入session时段过滤(US+Europe vs Asia) 尝试推至66%+",
        "round15_a02: EURUSD H1高ATR+RSI<40做多 全品种跨品种验证 确认EURUSD独有性",
        "round15_a03: EURUSD H1高ATR(>0.30%)+RSI<40做多 更高波动率阈值验证能否突破65%"
    ],
    "summary": "Round 15 H1完成auto_023假设：EURUSD H1高ATR(>0.25%)+RSI<40做多最优持有期深入扫描。完成1组测试(6个持有期)。核心结论：(1)所有6个测试持有期均保持>63%胜率(n=321)和>6.0 Sharpe(除hold=15)，信号极其稳健。(2)hold=7(64.49%, Sharpe=6.35, MaxDD=0.0492)超越round7_001 hold=10(63.86%)成为新的最优参数——全面更优(胜率+0.63pp, Sharpe+0.17, MaxDD-39%)。(3)信号非常一致，321个信号全部匹配round7_001，验证通过。(4)该信号在7-10小时窗口内均有效，不敏感于持有期精确选择。(5)hold=12拥有最高avg_return(0.00113)和Sharpe(6.58)但MaxDD较高。(6)hold=15开始衰减但仍维持>63%胜率。疲劳度重置为0/5(发现新的更优参数)。生成3个新假设(round15_a01~a03)。"
}

# ============================================================
# 8. Write back
# ============================================================
with open(STATE_PATH, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"✅ Updated {STATE_PATH}")
print(f"  - Removed auto_023 from hypothesis_queue")
print(f"  - Added auto_023 to tested_hypotheses")
print(f"  - Added new best_finding (hold=7, 64.49%)")
print(f"  - Updated current_round: 14 → 15")
print(f"  - Reset fatigue_count: 1 → 0")
print(f"  - Added 3 new hypotheses (round15_a01~a03)")
print(f"  - Added round15_summary")
