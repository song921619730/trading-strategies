#!/usr/bin/env python3
"""Update research state after round58 execution."""
import json
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "research_state.json"

with open(STATE_PATH, 'r') as f:
    state = json.load(f)

# === 1. Mark completed hypotheses from round58 ===
completion_data = {
    "round57_new_01": {
        "verdict": "strong_insufficient_sample",
        "notes": "JP225 M30美盘+RSI<30+ATR>0.30%+BB_lower做多hold=15: n=110(扩+49%), WR=73.64%(-4.74pp)。n仍<150无法注入。所有持有期5-50均超65%。BB下轨增强因子确认(+4.52pp)。JP225美盘BB系列全部完成——谱系关闭(休眠)。"
    },
    "round57_new_02": {
        "verdict": "strong_insufficient_sample",
        "notes": "XAUUSD H1亚盘+RSI<30+ATR>0.40%做多hold=30: n=62, WR=83.87%！研究历史最高WR之一！12/16持有期超64%。n=62<150门槛需降ATR扩样本。黄金亚盘新品种最大突破！"
    },
    "round57_new_03": {
        "verdict": "marginal",
        "notes": "XAGUSD H1欧盘+RSI<25+ATR>0.50%做多hold=5: n=120, WR=65.00%。短期(5-12h)WR在60-65%但长持有(16+)退化至50%以下。不建议深入。"
    },
    "round57_new_04": {
        "verdict": "negative",
        "notes": "USOIL M30欧盘+RSI<25+ATR>0.50%做多: n=334, WR=44-51%完全NOISE。bonus_04(RSI<30,n=889)也全部<52%。USOIL欧盘不存在方向性超卖模式。休眠。"
    }
}

for item in state['hypothesis_queue']:
    if item['id'] in completion_data and item['status'] == 'pending':
        cd = completion_data[item['id']]
        item['status'] = 'completed'
        item['verdict'] = cd['verdict']
        item['notes'] = cd['notes']
        item['completed_at'] = 'round58'

# === 2. Add new best findings at top ===
new_findings = [
    {
        "id": "round58_best_001",
        "hypothesis": "XAUUSD H1 美盘+RSI<30+ATR>0.40%做多 hold=7 — 72.73% 仅差7样本达注入门槛！最高优先级信号",
        "entry_condition": "session == 'us' and rsi14 < 30 and atr14 / close > 0.0040",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "best_hold": 7,
        "metrics": {
            "win_rate": 0.7273,
            "avg_return": 0.0017,
            "sharpe_ratio": 6.01,
            "signal_count": 143,
            "max_drawdown": 0.1757
        },
        "discovered_at": "2026-05-14",
        "status": "active",
        "summary": "XAUUSD H1美盘+RSI<30+ATR>0.40%做多hold=7胜率72.73%(n=143, Sharpe=6.01, MaxDD=17.57%)！n=143仅差7个样本即达150注入门槛。12/16持有期WR>60%，信号异常一致。短期(1-8h)avg_ret稳定+0.0005~+0.0018。hold=7(72.73%)和hold=48(72.73%)双峰。降ATR至0.35%几乎必然通过注入门槛。"
    },
    {
        "id": "round58_best_002",
        "hypothesis": "XAUUSD H1 亚盘+RSI<30+ATR>0.40%做多 hold=30 — 83.87% 研究历史最高WR之一！",
        "entry_condition": "session == 'asia' and rsi14 < 30 and atr14 / close > 0.0040",
        "direction": "long",
        "timeframe": "H1",
        "symbols": ["XAUUSD"],
        "best_hold": 30,
        "metrics": {
            "win_rate": 0.8387,
            "avg_return": 0.0096,
            "sharpe_ratio": 8.76,
            "signal_count": 62,
            "max_drawdown": 0.1187
        },
        "discovered_at": "2026-05-14",
        "status": "active",
        "summary": "XAUUSD H1亚盘+RSI<30+ATR>0.40%做多hold=30胜率83.87%(n=62, Sharpe=8.76, MaxDD=11.87%)！研究历史最高WR之一(仅次于JP225亚盘RSI<20的82.46%)。持有期10-48均超64%，长期持有(20-48h)极其稳定在72-84%。n=62<150门槛但WR=83.87%潜力巨大。降ATR扩样本为第一优先级。"
    },
    {
        "id": "round58_best_003",
        "hypothesis": "JP225 M30 美盘+RSI<30+ATR>0.30%+close<bb_lower做多 hold=15 — 73.64% BB增强确认但样本不足",
        "entry_condition": "session == 'us' and rsi14 < 30 and atr14 / close > 0.0030 and close < bb_lower",
        "direction": "long",
        "timeframe": "M30",
        "symbols": ["JP225"],
        "best_hold": 15,
        "metrics": {
            "win_rate": 0.7364,
            "avg_return": 0.0048,
            "sharpe_ratio": 13.92,
            "signal_count": 110,
            "max_drawdown": 0.0687
        },
        "discovered_at": "2026-05-14",
        "status": "active",
        "summary": "JP225 M30美盘+RSI<30+ATR>0.30%+close<bb_lower做多hold=15胜率73.64%(n=110, Sharpe=13.92, MaxDD=6.87%)！降低ATR至0.30%后n从74扩至110(+49%)，WR从78.38%降至73.64%(-4.74pp)。n仍<150门槛。BB下轨增强因子确认(+4.52pp)。JP225美盘BB系列全部完成——谱系关闭。"
    }
]

state['best_findings'] = new_findings + state['best_findings']

# === 3. Generate new hypotheses for round59 ===
new_round59 = [
    {
        "id": "round59_new_01",
        "family": "gold_silver",
        "session": "us",
        "hypothesis": "XAUUSD H1 美盘+RSI<30+ATR>0.35%做多 hold=7 — 降ATR从0.40%至0.35%扩样本至180+，目标注入",
        "direction": "long",
        "timeframe": "H1",
        "symbol": "XAUUSD",
        "priority": 1,
        "status": "pending",
        "notes": "基线美盘+RSI<30+ATR>0.40%: n=143, WR=72.73%@hold=7。降低ATR至0.35%预期n扩至~180-220。目标:n>=150且WR>=68%——将黄金美盘从'接近门槛'升级为'可注入信号'。本轮最大优先级！"
    },
    {
        "id": "round59_new_02",
        "family": "gold_silver",
        "session": "asia",
        "hypothesis": "XAUUSD H1 亚盘+RSI<30+ATR>0.25%做多 hold=30 — 大幅降低ATR扩样本验证83.87%稳定性",
        "direction": "long",
        "timeframe": "H1",
        "symbol": "XAUUSD",
        "priority": 1,
        "status": "pending",
        "notes": "基线亚盘+RSI<30+ATR>0.40%: n=62, WR=83.87%@hold=30。降低ATR至0.25%预期n扩至~150-200。目标:n>=120且WR>=70%——确认83.87%超高WR是否稳定。黄金H1平均ATR约0.5-0.8%，0.25%为超低阈值。"
    },
    {
        "id": "round59_new_03",
        "family": "gold_silver",
        "session": "asia",
        "hypothesis": "XAUUSD H1 亚盘+RSI<25+ATR>0.35%做多 hold=30 — 严格RSI测试黄金亚盘极限超卖",
        "direction": "long",
        "timeframe": "H1",
        "symbol": "XAUUSD",
        "priority": 1,
        "status": "pending",
        "notes": "RSI<25严格版预期n~30-40(相比RSI<30的62), 但WR有望冲85-90%。目标:n>=30且WR>=80%。若成功将确认黄金亚盘极致超卖信号。可能n过小(R<30)而无法统计显著。"
    },
    {
        "id": "round59_new_04",
        "family": "gold_silver",
        "session": "us",
        "hypothesis": "XAUUSD H1 美盘+RSI<25+ATR>0.35%做多 hold=7 — 严格RSI+低ATR扩样本测试美盘极限",
        "direction": "long",
        "timeframe": "H1",
        "symbol": "XAUUSD",
        "priority": 2,
        "status": "pending",
        "notes": "基线美盘+RSI<30+ATR>0.40%: n=143, WR=72.73%。严格RSI<25+降低ATR至0.35%预期n~60-90。目标:n>=60且WR>=75%。评估黄金美盘极限超卖的WR增益。"
    },
    {
        "id": "round59_new_05",
        "family": "gold_silver",
        "session": "us",
        "hypothesis": "XAUUSD H1 美盘+RSI>65+ATR>0.35%做空 — 黄金美盘超买做空宽松版测试",
        "direction": "short",
        "timeframe": "H1",
        "symbol": "XAUUSD",
        "priority": 2,
        "status": "pending",
        "notes": "基线美盘+RSI>70+ATR>0.40%做空: n=135, WR=61.48%@hold=20仅marginal。测试RSI>65+ATR>0.35%宽松版看能否扩样本并稳定60%+。黄金做空方向优先级低于做多。"
    },
    {
        "id": "round59_new_06",
        "family": "gold_silver",
        "session": "europe",
        "hypothesis": "XAGUSD H1 欧盘+RSI<25+ATR>0.40%做多 hold=5 — 降ATR扩XAG样本至200+看短期稳定性",
        "direction": "long",
        "timeframe": "H1",
        "symbol": "XAGUSD",
        "priority": 2,
        "status": "pending",
        "notes": "基线欧盘+RSI<25+ATR>0.50%: n=120, WR=65.00%@hold=5。降低ATR至0.40%预期n扩至~200-250。目标:hold=5 WR>=60%。若成功则XAGUSD短期信号可辅助参考。"
    },
    {
        "id": "round59_bonus_01",
        "family": "gold_silver",
        "session": "asia",
        "hypothesis": "XAUUSD H1 亚盘+RSI<25+ATR>0.40%+close<bb_lower做多 — BB下轨增强黄金亚盘测试(n估30-45)",
        "direction": "long",
        "timeframe": "H1",
        "symbol": "XAUUSD",
        "priority": 3,
        "status": "pending",
        "notes": "测试BB_lower过滤能否在黄金亚盘超卖上进一步提升WR。基线亚盘+RSI<30+ATR>0.40%: n=62, WR=83.87%。叠加BB_lower预期n~25-40但WR可能>90%。"
    },
    {
        "id": "round59_bonus_02",
        "family": "us_equity",
        "session": "asia",
        "hypothesis": "US500 M30 亚盘+RSI<25+ATR>0.20%+close<bb_lower做多 — US500亚盘BB增强最后确认",
        "direction": "long",
        "timeframe": "M30",
        "symbol": "US500",
        "priority": 3,
        "status": "pending",
        "notes": "US500亚盘+RSI<25+ATR>0.20%基线: n=189, WR=65.61%@hold=10。叠加BB_lower预期WR冲80%+但n降至~50。确认BB_lower跨品种增强通用性。"
    },
    {
        "id": "round59_hibernate_01",
        "family": "hibernate",
        "session": "all",
        "hypothesis": "JP225 全部session+BB系列谱系完整完成——正式休眠",
        "direction": "long",
        "timeframe": "M30",
        "symbol": "JP225",
        "priority": 9,
        "status": "pending",
        "notes": "JP225三session全部完成、BB系列全部完成、ATR阈值全部完成。亚盘(RSI<25+ATR>0.35%: 74.33%/n=187)、美盘(RSI<30+ATR>0.35%: 69.12%/n=204)、美盘BB(RSI<30+ATR>0.30%+BB: 73.64%/n=110)。不再继续JP225新测试。"
    },
    {
        "id": "round59_hibernate_02",
        "family": "hibernate",
        "session": "all",
        "hypothesis": "USOIL 欧盘+亚盘全部测试完成——确认NOISE休眠",
        "direction": "long",
        "timeframe": "M30",
        "symbol": "USOIL",
        "priority": 9,
        "status": "pending",
        "notes": "USOIL欧盘RSI<25+ATR>0.50%(n=334,~50%)、RSI<30+ATR>0.40%(n=889,~50%)、亚盘RSI<25+ATR>0.50%(n=64,~50%短期)全部无方向性。USOIL正式休眠。"
    }
]

# Append new hypotheses to queue (completed items stay; we add new pending items)
for h in new_round59:
    state['hypothesis_queue'].append(h)

# === 4. Advance round ===
state['current_round'] = 59
state['last_updated'] = '2026-05-14'
state['consecutive_no_finding'] = 0  # Reset since we found gold signals

with open(STATE_PATH, 'w') as f:
    json.dump(state, f, indent=2, default=str)

pending_count = sum(1 for h in state['hypothesis_queue'] if h.get('status') == 'pending')
completed_count = sum(1 for h in state['hypothesis_queue'] if h.get('status') == 'completed')
print(f"✅ State updated to round {state['current_round']}")
print(f"   hypothesis_queue: {len(state['hypothesis_queue'])} total ({pending_count} pending, {completed_count} completed)")
print(f"   best_findings: {len(state['best_findings'])} entries")
print(f"   last_updated: {state['last_updated']}")
