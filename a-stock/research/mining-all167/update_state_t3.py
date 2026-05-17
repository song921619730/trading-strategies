#!/usr/bin/env python3
"""Update state.json with T3 Iter28 results."""
import json

state_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/state/state.json"
state = json.load(open(state_path, "r"))

# New combos to add to recent_combos
new_combos = [
    "iter28_T3_ecd1108d1488: C1_双日恐慌-4%新阈值SPX散户割肉大单CM50 N=1127,WR=77.80%,R5=14.19%,Sharpe=6.327 ✅ PASS",
    "iter28_T3_4856c343a1a9: C2_极端恐慌-7%振幅10%散户ELG深价值微盘 N=96,WR=97.92%,R5=15.44%,Sharpe=12.808 ❌ FAIL(N<200)",
    "iter28_T3_940d62568673: C3_双日恐慌-5%VR放宽散户大单比例底30%CM100亿 N=945,WR=90.22%,R5=14.15%,Sharpe=8.199 ✅ PASS",
    "iter28_T3_139ee58bbbe0: C4_单日恐慌5%SPX双涨散户大单60日底CM30 N=391,WR=84.58%,R5=16.43%,Sharpe=8.662 ✅ PASS 🏆 T3本轮最佳R5",
    "iter28_T3_658707ace90a: C5_双日温和-3%散户ELG振幅7%CM30无宏观 N=1132,WR=82.23%,R5=11.91%,Sharpe=5.925 ✅ PASS",
]

# Add new combos to recent_combos (keep last 50)
recent = state.get("recent_combos", [])
recent.extend(new_combos)
if len(recent) > 50:
    recent = recent[-50:]
state["recent_combos"] = recent

# Add to history
history_entry = {
    "iteration": 28,
    "ret_5d": 16.43,
    "win_5d": 90.22,
    "signal_count": 945,
    "sharpe_5d": 8.662,
    "analyst": "T3_反转低吸 (4/5 PASS)",
    "params": "C4: 单日恐慌(昨跌≤-5%+今涨≥2%)+SPX双涨+散户割肉+大单+60日底20%+CM≤30亿+振幅6%+VR1.3 → R5=16.43%,WR=84.58%,N=391,Sharpe=8.662 🏆 T3本轮最佳R5. C3(双日恐慌-5%+VR0.8+大单比例60%+CM100, WR=90.22%,R5=14.15%,N=945)为最佳容量版. C2(极端-7%+振幅10%+散户+ELG+PE20, WR=97.92%,R5=15.44%,Sharpe=12.808,P10=+2.83%)N=96不足但全局级质量.",
    "note": "📊 T3 反转低吸(Iter28) — 4/5 PASS! 80%通过率.\n"
            "🏆 C4(单日恐慌+SPX双涨)以R5=16.43%成为T3本轮最佳R5! 验证SPX双涨为最强宏观窗口.\n"
            "🏆 C3(VR0.8+CM100+底30%扩容版)以WR=90.22%, N=945成为最佳容量-质量平衡版.\n"
            "🏆 C1(双日-4%新阈值+SPX+双资金)N=1127最大容量版以R5=14.19%通过.\n"
            "🏆 C5(纯微观双日-3%无宏观)N=1132, WR=82.23%验证纯微观反转极限.\n"
            "🥇 C2(极端-7%+振幅10%+散户+ELG+PE20,N=96,WR=97.92%,P10=+2.83%)WR&P10全局级但N不足.\n"
            "🆕 新因子: (1)单日恐慌+SPX双涨=新模式, (2)-4%新阈值验证, (3)大单比例≥60%替代buy_lg, (4)VR≥0.8扩容验证.\n"
            "❌ 未超越全局纪录(WR=99.55%, R5=25.23%). fatigue_count: 2→3."
}
state["history"].insert(0, history_entry)

# Update fatigue_count
state["fatigue_count"] = 3

# Update timestamp
state["updated_at"] = "2026-05-14 02:50"

# Write
with open(state_path, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("✅ state.json updated")
print(f"  recent_combos: {len(state['recent_combos'])} entries")
print(f"  history: {len(state['history'])} entries")
print(f"  fatigue_count: {state['fatigue_count']}")
