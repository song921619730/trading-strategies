#!/usr/bin/env python3
"""Update state.json with T8 combos."""
import json, hashlib

path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/state/state.json"
with open(path, "r", encoding="utf-8") as f:
    state = json.load(f)

# New combos from T8
new_combos = [
    "iter28_T8_C1: 长下影锤子线恐慌反转ELG确认 — 底20%(20日)+昨跌≤-5%+今涨≥1%+锤子线下影+振幅≥7%+VR≥1.3+buy_elg>sell_elg+CM≤30亿 N=297,WR=94.61%,R5=17.22%,Sharpe=10.966 ✅ PASS 🏆 T8本轮最佳",
    "iter28_T8_C2: 曙光初现SPX双涨散户割肉 — 底20%(20日)+昨跌≤-3%+今涨≥2%+曙光初现+振幅≥5%+VR≥1.0+SPX双涨+sell_sm>buy_sm+CM≤30亿 N=834,WR=83.51%,R5=12.77%,Sharpe=7.525 ✅ PASS",
    "iter28_T8_C3: 低开尾拉大单比例确认放量 — 底20%(20日)+低开+尾拉close/high≥0.95+涨2-10%+振幅≥5%+VR≥1.3+buy_lg_ratio≥50%+CM≤30亿 N=1101,WR=68.68%,R5=6.86%,Sharpe=3.460 ✅ PASS",
    "iter28_T8_C4: 双日恐慌不等幅振幅10%散户割肉 — 底20%(60日)+连2日跌(昨-4%+今-5%)+今涨≥1%+振幅≥10%+VR≥0.8+sell_sm>buy_sm+buy_lg>sell_lg+CM≤50亿 N=774,WR=91.95%,R5=15.62%,Sharpe=9.293 ✅ PASS 🏆 T8最佳容量",
    "iter28_T8_C5: 三连阴后放量反弹SPX散户割肉大单 — 底20%(20日)+三连阴+涨2-10%+振幅≥5%+VR≥1.3+SPX前日涨+sell_sm>buy_sm+buy_lg>sell_lg+CM≤30亿 N=1270,WR=61.87%,R5=6.30%,Sharpe=3.280 ✅ PASS",
]

# Add to recent_combos (keep last 50)
state["recent_combos"] = (new_combos + state["recent_combos"])[:50]

# Add to history
new_history = {
    "iteration": 28,
    "ret_5d": 17.22,
    "win_5d": 94.61,
    "signal_count": 297,
    "sharpe_5d": 10.966,
    "analyst": "T8_量价形态 (5/5全满贯!)",
    "params": "C1: 长下影锤子线恐慌反转ELG确认 — 底20%+昨跌≤-5%+锤子线+振幅≥7%+VR≥1.3+ELG+CM≤30亿 WR=94.61%,R5=17.22%,Sharpe=10.966",
    "note": "🏆🏆🏆 T8 量价形态(Iter28) — 5/5全满贯! C1(长下影锤子线恐慌反转)以WR=94.61%,R5=17.22%,Sharpe=10.966为本轮最佳。C4(不等幅双日恐慌振幅10%散户割肉, WR=91.95%,R5=15.62%,N=774)为最佳容量-质量平衡版。C2(曙光初现SPX双涨散户割肉, WR=83.51%,R5=12.77%,N=834)为优质发现。C3(低开尾拉大单比例, N=1101)和C5(三连阴放量SPX, N=1270)提供大容量信号。未破全局纪录(WR=99.55%,R5=25.23%)。fatigue_count=2→3。"
}
state["history"].insert(0, new_history)
state["history"] = state["history"][:50]
state["fatigue_count"] = 3  # No global record broken
state["updated_at"] = "2026-05-14 02:42"

with open(path, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("state.json updated!")
print(f"  fatigue_count: {state['fatigue_count']}")
print(f"  recent_combos: {len(state['recent_combos'])}")
print(f"  history: {len(state['history'])}")
