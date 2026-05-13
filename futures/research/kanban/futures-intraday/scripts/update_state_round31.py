#!/usr/bin/env python3
"""
Update research_state.json for Round 31 results.

This script modifies the JSON file in-place:
1. Marks init_005 as tested in hypothesis_queue
2. Adds round31 result to tested_hypotheses
3. Updates fatigue_count (4 → 5)
4. Updates current_round (31 → 32)
5. Adds new hypotheses to queue

Also prints summary of what was changed.
"""

import json
import sys
from pathlib import Path

STATE_PATH = Path("/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/state/research_state.json")

# Load
with open(STATE_PATH, "r") as f:
    state = json.load(f)

print("=" * 70)
print("  Updating research_state.json for Round 31")
print("=" * 70)

# ── 1. Mark init_005 as tested ──
for h in state["hypothesis_queue"]:
    if h["id"] == "init_005":
        h["status"] = "tested"
        h["tested_at"] = "2026-05-11"
        h["result"] = {
            "verdict": "no_signal",
            "description": "D1 MA20上下方对H1开盘方向影响测试——D1>MA20做多和D1<MA20做空均未发现>55%胜率信号。Long侧最佳：USDJPY hold=20 wr=54.90%(n=20,796), US500 hold=8 wr=54.53%(n=17,791), USTEC hold=20 wr=54.46%(n=17,195)。Short侧全部<51%，D1<MA20做空无效——市场在D1<MA20时实际倾向反弹(均值回归)。",
            "best_params": {
                "symbol": "USDJPY",
                "timeframe": "H1",
                "direction": "long",
                "entry_condition": "d1_close_above_ma20 == 1",
                "hold_period": 20,
                "win_rate": 0.5490,
                "signal_count": 20796,
                "avg_return": None,
                "sharpe_ratio": None,
                "summary": "Best signal in test: USDJPY D1>MA20做多hold=20 wr=54.90%(n=20,796)——接近55%阈值但未达标。D1>MA20方向性偏多但胜率不足以单独作为交易信号。"
            }
        }
        print(f"\n✅ Updated init_005 in hypothesis_queue: {h['status']}")
        break

# ── 2. Add round31 to tested_hypotheses ──
round31_entry = {
    "id": "round31",
    "hypothesis": "init_005: D1趋势方向过滤 — MA20上方/下方对H1开盘方向的影响",
    "status": "tested",
    "timeframe": "H1",
    "round": 31,
    "tested_at": "2026-05-11",
    "created_at": "2026-05-11",
    "result": {
        "verdict": "no_signal",
        "description": "全品种14个H1数据测试。Long(D1>MA20做多)：最佳USDJPY hold=20 wr=54.90%(n=20,796)。次优US500 hold=8 wr=54.53%(n=17,791)、USTEC hold=20 wr=54.46%(n=17,195)。Short(D1<MA20做空)：全部<51%，有效否定。核心结论：D1>MA20有微弱做多倾向(51-54.9%)但未达55%阈值，D1<MA20做空完全无效。趋势跟踪信号在H1上偏弱。",
        "best_params": {
            "symbol": "USDJPY",
            "timeframe": "H1",
            "direction": "long",
            "entry_condition": "d1_close_above_ma20 == 1",
            "hold_period": 20,
            "win_rate": 0.5490,
            "signal_count": 20796,
            "avg_return": None,
            "sharpe_ratio": None
        },
        "all_holds": {
            "long_best": "USDJPY hold=20 wr=54.90% n=20796",
            "long_top5": [
                "USDJPY hold=20 wr=54.90% n=20796",
                "USDJPY hold=15 wr=54.72% n=20796",
                "US500 hold=8 wr=54.53% n=17791",
                "US500 hold=10 wr=54.48% n=17789",
                "USTEC hold=20 wr=54.46% n=17195"
            ],
            "short_assessment": "全部<51%，D1<MA20做空无效——市场在D1<MA20时倾向反弹"
        },
        "key_insights": [
            "D1>MA20做多信号在USDJPY/US500/USTEC上最接近55%阈值，但均未达标",
            "D1>MA20做多在FX pairs(EURUSD/GBPUSD/AUDUSD/USDCHF)上完全无效(49-50%)",
            "D1<MA20做空全面无效——D1<MA20后市场实际倾向+0到+1%(均值回归)",
            "Long信号随持有期延长而增强(趋势跟踪特征)：hold=1~20 胜率从51-52%升至53-55%",
            "USDJPY D1>MA20做多hold=20(54.90%)为全测试最优——距离55%阈值仅差0.10pp",
            "US500/USTEC/JP225等美股指在D1>MA20后有微弱做多倾向(52-54%)",
            "D1趋势框架在H1上单独使用效果有限——建议结合RSI/ATR/时段等过滤器增强"
        ],
        "cross_symbol_summary": "USDJPY(54.90%)>US500(54.53%)>USTEC(54.46%)>XAUUSD(53.69%)>JP225(53.03%)。FX pairs(EURUSD/GBPUSD/AUDUSD/USDCHF/USDCHF)和HK50全部<50.5%。"
    },
    "new_hypotheses_generated": [
        "round31_a01: D1>MA20+RSI<40做多策略 — D1趋势过滤+超卖双条件，在USDJPY/US500上测试",
        "round31_a02: D1<MA20+收盘阳线做多(均值回归) — D1低于MA20时市场倾向反弹，加阳线确认增强",
        "round31_a03: D1趋势方向+时段过滤 — D1>MA20+美盘时段做多，在美股指上测试"
    ]
}

state["tested_hypotheses"].append(round31_entry)
print(f"✅ Added round31 to tested_hypotheses (now {len(state['tested_hypotheses'])} entries)")

# ── 3. Update fatigue_count ──
old_fatigue = state["fatigue_count"]
new_fatigue = old_fatigue + 1  # No finding found → fatigue += 1
state["fatigue_count"] = new_fatigue
print(f"✅ fatigue_count: {old_fatigue} → {new_fatigue}")

# ── 4. Update current_round ──
old_round = state["current_round"]
state["current_round"] = old_round + 1
print(f"✅ current_round: {old_round} → {state['current_round']}")

# ── 5. Check convergence ──
if new_fatigue >= 5:
    state["status"] = "converged"
    print(f"✅ status: in_progress → converged (fatigue={new_fatigue} >= 5)")
    print("⚠  TOPIC EXHAUSTED — Final report needed")

# ── 6. Add new hypotheses to queue ──
new_hypotheses = [
    {
        "id": "round31_a01",
        "hypothesis": "D1>MA20+RSI<40做多 — D1趋势过滤+超卖双条件，在USDJPY/US500上测试",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 2,
        "source": "round31: D1>MA20做多接近55%阈值(USDJPY 54.90%)，加RSI<40超卖过滤可能推至55%+。USDJPY和US500为最佳目标品种。"
    },
    {
        "id": "round31_a02",
        "hypothesis": "D1<MA20+阳线收盘做多(均值回归) — D1低于MA20时市场倾向反弹，加阳线确认增强入场信号",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 2,
        "source": "round31: D1<MA20做空全面无效(全部<51%)——反向做多(均值回归)可能有效。D1<MA20后市场倾向+0到+1%反弹，加阳线确认(close>open)可增强信号。"
    },
    {
        "id": "round31_a03",
        "hypothesis": "D1趋势方向+美盘时段做多 — D1>MA20+美盘时段做多，在美股指(US500/USTEC)上测试",
        "status": "pending",
        "created_at": "2026-05-11",
        "priority": 3,
        "source": "round31: D1>MA20在US500/USTEC上有53-54%胜率，叠加美盘时段(session=='us')可能推至55%+。"
    }
]

existing_ids = {h["id"] for h in state["hypothesis_queue"]}
added_count = 0
for nh in new_hypotheses:
    if nh["id"] not in existing_ids:
        state["hypothesis_queue"].append(nh)
        added_count += 1
        print(f"✅ Added new hypothesis to queue: {nh['id']} — {nh['hypothesis'][:60]}…")
    else:
        print(f"⏭ Skipped (already exists): {nh['id']}")

# ── 7. Write back ──
with open(STATE_PATH, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"\n{'='*70}")
print(f"  Update complete. {added_count} new hypotheses added to queue.")
print(f"  Queue now has {len(state['hypothesis_queue'])} entries.")
print(f"{'='*70}")
