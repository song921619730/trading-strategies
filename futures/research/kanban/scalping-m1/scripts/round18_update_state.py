#!/usr/bin/env python3
"""Update research state for Round 18"""
import json

with open('/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/state/research_state.json', 'r') as f:
    state = json.load(f)

# Add new best_findings
new_findings = [
    {
        "id": "bf_051",
        "description": "XAUUSD M5 欧盘9-11 RSI<18+CB>=4 做多 — hold=42 WR=88.5% n=52 Sharpe=25.2 — RSI收紧至<18+CB>=4组合，n>=50中WR最好的欧盘模式之一",
        "timeframe": "M5",
        "direction": "long",
        "best_hold": 42,
        "win_rate": 88.5,
        "n": 52,
        "avg_return_pct": 0.252,
        "sharpe": 25.21,
        "source": "round18_eu9to11_rsi18_cb4"
    },
    {
        "id": "bf_052",
        "description": "XAUUSD M5 欧盘8-11 RSI<18+CB>=4 做多 — hold=42 WR=83.3% n=78 Sharpe=13.5 — 宽窗口版bf_051，以更多信号(n=78)换取稍低WR",
        "timeframe": "M5",
        "direction": "long",
        "best_hold": 42,
        "win_rate": 83.3,
        "n": 78,
        "avg_return_pct": 0.167,
        "sharpe": 13.53,
        "source": "round18_eu8to11_rsi18_cb4"
    },
]

for f in new_findings:
    # Check if already exists
    ids = [bf['id'] for bf in state['best_findings']]
    if f['id'] not in ids:
        state['best_findings'].append(f)

# Update hypothesis statuses
# round17_001 (bf_050 stability) → completed, inconclusive (n too small)
for h in state['hypothesis_queue']:
    if h['id'] == 'round17_001':
        h['status'] = 'completed'
        h['result'] = 'inconclusive'
        h['notes'] = 'n=14 total (P1=8, P2=5, P3=1)，样本严重不足无法判断稳定性。正确CB定义下该模式极稀有，原bf_050的n=53不可复现。'
    elif h['id'] == 'round17_002':
        h['status'] = 'completed'
        h['result'] = 'promising_insufficient'
        h['notes'] = 'XAU+JP同bar共振n=5-7，3-bar窗口n=14-20，WR=75-100%但n<30仍不足。JP条件放宽至RSI<20+CB>=2后n从5升至20(接近30)但WR下降至80%。需要更大数据集。'
    elif h['id'] == 'round17_003':
        h['status'] = 'completed'
        h['result'] = 'moderate'
        h['notes'] = 'ATR>0.08/0.10过滤对bf_046有轻微改善(WR从86.7%→87.7%/89.8%)但n从60降至57/49。无质变。'
    elif h['id'] == 'round17_004':
        h['status'] = 'completed'
        h['result'] = 'negative'
        h['notes'] = 'bf_050仅n=14无法跨品种扩展。'

# Add new hypotheses
new_hypotheses = [
    {
        "id": "round18_001",
        "description": "XAUUSD M5 欧盘9-11 RSI<18+CB>=4 (bf_051) 跨数据周期稳定性验证 — WR=88.5% n=52需分P1/P2/P3验证稳定性，与bf_035(RSI<22+CB>=4 WR=84.3% n=83)和bf_028(RSI<20+CB>=4 WR=81.8% n=66)对比",
        "direction": "long",
        "timeframe": "M5",
        "priority": 1,
        "status": "pending",
        "source": "round18_eu9to11_rsi18_cb4"
    },
    {
        "id": "round18_002",
        "description": "XAUUSD M5 US 15-16 RSI<22 CB>=2 (放宽版bf_046) — n=76 WR=84.2% hold=115 vs bf_046(RSI<20 CB>=2 WR=86.7% n=60)。放宽RSI至<22增加信号量(60→76)但WR略降，评估性价比",
        "direction": "long",
        "timeframe": "M5",
        "priority": 1,
        "status": "pending",
        "source": "round18_us_15to16_rsi22"
    },
    {
        "id": "round18_003",
        "description": "XAUUSD M5 + JP225 M5 美盘中段共振扩大样本 — XAU US 15-18 RSI<20 CB>=2 (bf_018 base n=174) + JP US 15-18 RSI<20 CB>=2 (n=198) 共振n=20 WR=80% hold=110。放宽至RSI<22+CB>=1获取n>=30，验证共振是否保持WR>75%",
        "direction": "long",
        "timeframe": "M5",
        "priority": 2,
        "status": "pending",
        "source": "round18_resonance_loose"
    },
    {
        "id": "round18_004",
        "description": "XAUUSD M5 欧盘8-11 RSI<18+CB>=4 (bf_052) 窗口子分段 — 对比8-9/9-10/10-11三个子窗口，验证9-11是否最优(类似bf_047对bf_034的改进)",
        "direction": "long",
        "timeframe": "M5",
        "priority": 2,
        "status": "pending",
        "source": "round18_eu8to11_subwindow"
    },
]

for h in new_hypotheses:
    state['hypothesis_queue'].append(h)

# Update round counter
state['current_round'] = 18
state['fatigue'] = 0
state['consecutive_no_finding'] = 0

# Write back
with open('/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/state/research_state.json', 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("State updated to round 18")
print(f"Best findings: {len(state['best_findings'])}")
print(f"Pending hypotheses: {sum(1 for h in state['hypothesis_queue'] if h['status'] == 'pending')}")
