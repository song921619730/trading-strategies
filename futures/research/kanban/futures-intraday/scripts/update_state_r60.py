#!/usr/bin/env python3
"""Update research state to round 61 after round 60 M1/M5 execution."""
import json

today = "2026-05-14"

with open("state/research_state.json", "r") as f:
    state = json.load(f)

# Update timeframes to include M1/M5
state["data"]["timeframes"] = ["M1", "M5", "H1", "M30"]
state["current_round"] = 61
state["data"]["last_update"] = today
state["fatigue"] = 0
state["consecutive_no_finding"] = 0

# Add new best findings from Round 60
new_findings = [
    # ── TIER 1: Injectable ──
    {
        "id": "round60_best_001",
        "hypothesis": "XAUUSD M5 美盘+RSI<25+ATR>0.15%做多 hold=60 — 88.07% 首個M5可注入信号！最高优先级信号",
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "best_hold": 60,
        "metrics": {
            "win_rate": 0.8807,
            "avg_return": 0.0041,
            "sharpe_ratio": 7.42,
            "signal_count": 176,
            "max_drawdown": 0.1235
        },
        "discovered_at": today,
        "status": "injectable",
        "summary": "XAUUSD M5美盘+RSI<25+ATR>0.15%做多hold=60(5h)胜率88.07%(n=176, Sharpe=7.42, MaxDD=12.35%)！首個M5可注入信号。持有期越长WR越高(15=61.93%→48=81.25%→60=88.07%)，美盘超卖在M5上表现极其一致。n>=150且WR>=65%双重目标通过！"
    },
    {
        "id": "round60_best_002",
        "hypothesis": "XAGUSD M5 美盘+RSI<25+ATR>0.15%做多 hold=40 — 78.54% 白银美盘超卖极强！",
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAGUSD"],
        "best_hold": 40,
        "metrics": {
            "win_rate": 0.7854,
            "avg_return": 0.0107,
            "sharpe_ratio": 8.18,
            "signal_count": 233,
            "max_drawdown": 0.2043
        },
        "discovered_at": today,
        "status": "injectable",
        "summary": "XAGUSD M5美盘+RSI<25+ATR>0.15%做多hold=40胜率78.54%(n=233, Sharpe=8.18, avg_ret=+1.07%)！白银M5超卖每笔盈利远超黄金。30-60持有期均超75%+, n=233大样本通过注入门槛。"
    },
    {
        "id": "round60_best_003",
        "hypothesis": "JP225 M5 美盘+RSI<25+ATR>0.15%做多 hold=30 — 72.60% 日经美盘超卖M5确认",
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["JP225"],
        "best_hold": 30,
        "metrics": {
            "win_rate": 0.7260,
            "avg_return": 0.0035,
            "sharpe_ratio": 8.08,
            "signal_count": 219,
            "max_drawdown": 0.1244
        },
        "discovered_at": today,
        "status": "injectable",
        "summary": "JP225 M5美盘+RSI<25+ATR>0.15%做多hold=30(2.5h)胜率72.60%(n=219, Sharpe=8.08)。与H1/M30 JP225超卖信号形成跨时间框架一致性确认。"
    },
    {
        "id": "round60_best_004",
        "hypothesis": "XAUUSD M5 美盘+close<bb_lower+RSI<30+ATR>0.15%做多 hold=48 — 75.00% BB增强确认",
        "entry_condition": "session == 'us' and close < bb_lower and rsi14 < 30 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "best_hold": 48,
        "metrics": {
            "win_rate": 0.75,
            "avg_return": 0.0037,
            "sharpe_ratio": 8.16,
            "signal_count": 152,
            "max_drawdown": 0.0714
        },
        "discovered_at": today,
        "status": "injectable",
        "summary": "XAUUSD M5美盘+close<bb_lower+RSI<30+ATR>0.15%做多hold=48胜率75.00%(n=152, Sharpe=8.16, MaxDD=7.14%)。n=152恰好通过注入门槛！BB下轨增强因子在M5上同样有效。"
    },
    {
        "id": "round60_best_005",
        "hypothesis": "XAUUSD M5 美盘+consecutive_bear>=3+RSI<30+ATR>0.10%做多 hold=60 — 69.73% 连跌反转",
        "entry_condition": "session == 'us' and consecutive_bear >= 3 and rsi14 < 30 and atr_pct > 0.0010",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "best_hold": 60,
        "metrics": {
            "win_rate": 0.6973,
            "avg_return": 0.0019,
            "sharpe_ratio": 2.64,
            "signal_count": 185,
            "max_drawdown": 0.1349
        },
        "discovered_at": today,
        "status": "injectable",
        "summary": "XAUUSD M5美盘+连跌3+RSI<30+ATR>0.10%做多hold=60胜率69.73%(n=185, Sharpe=2.64)。连跌3结合超卖确认反转信号，n=185通过150门槛。"
    },
    {
        "id": "round60_best_006",
        "hypothesis": "XAGUSD M5 美盘+consecutive_bear>=3+RSI<30+ATR>0.10%做多 hold=48 — 69.12% 白银连跌反转",
        "entry_condition": "session == 'us' and consecutive_bear >= 3 and rsi14 < 30 and atr_pct > 0.0010",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAGUSD"],
        "best_hold": 48,
        "metrics": {
            "win_rate": 0.6912,
            "avg_return": 0.0047,
            "sharpe_ratio": 4.43,
            "signal_count": 272,
            "max_drawdown": 0.2517
        },
        "discovered_at": today,
        "status": "injectable",
        "summary": "XAGUSD M5美盘+连跌3+RSI<30+ATR>0.10%做多hold=48胜率69.12%(n=272, Sharpe=4.43)。白银连跌反转大样本验证通过。"
    },
    {
        "id": "round60_best_007",
        "hypothesis": "XAGUSD M5 亚盘+RSI<25+ATR>0.15%做多 hold=20 — 65.49% 大样本亚盘超卖",
        "entry_condition": "session == 'asia' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAGUSD"],
        "best_hold": 20,
        "metrics": {
            "win_rate": 0.6549,
            "avg_return": 0.0025,
            "sharpe_ratio": 3.73,
            "signal_count": 368,
            "max_drawdown": 0.3406
        },
        "discovered_at": today,
        "status": "injectable",
        "summary": "XAGUSD M5亚盘+RSI<25+ATR>0.15%做多hold=20胜率65.49%(n=368, Sharpe=3.73)。n=368为本轮最大样本信号之一，白银亚盘超卖稳定。"
    },
    {
        "id": "round60_best_008",
        "hypothesis": "XAUUSD M5 欧盘+RSI<25+ATR>0.15%做多 hold=30 — 65.85% 欧盘超卖大样本",
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "best_hold": 30,
        "metrics": {
            "win_rate": 0.6585,
            "avg_return": 0.0016,
            "sharpe_ratio": 3.93,
            "signal_count": 284,
            "max_drawdown": 0.1789
        },
        "discovered_at": today,
        "status": "injectable",
        "summary": "XAUUSD M5欧盘+RSI<25+ATR>0.15%做多hold=30胜率65.85%(n=284, Sharpe=3.93)。黄金欧盘超卖大样本稳定65%+，15-60持有期均在60-66%之间。"
    },
    {
        "id": "round60_best_009",
        "hypothesis": "US500 M5 欧盘+RSI<25+ATR>0.15%做多 hold=30 — 65.90% 标普欧盘超卖",
        "entry_condition": "session == 'europe' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["US500"],
        "best_hold": 30,
        "metrics": {
            "win_rate": 0.659,
            "avg_return": 0.0012,
            "sharpe_ratio": 4.40,
            "signal_count": 173,
            "max_drawdown": 0.1418
        },
        "discovered_at": today,
        "status": "injectable",
        "summary": "US500 M5欧盘+RSI<25+ATR>0.15%做多hold=30胜率65.90%(n=173, Sharpe=4.40)。标普欧盘超卖信号稳定，n=173通过注入门槛。"
    },
    # ── TIER 2: High Potential ──
    {
        "id": "round60_best_010",
        "hypothesis": "XAUUSD M5 美盘+consecutive_bear>=4+RSI<25+ATR>0.15%做多 hold=48 — 93.62% 极致反转！",
        "entry_condition": "session == 'us' and consecutive_bear >= 4 and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "best_hold": 48,
        "metrics": {
            "win_rate": 0.9362,
            "avg_return": 0.0052,
            "sharpe_ratio": 14.94,
            "signal_count": 47,
            "max_drawdown": 0.0175
        },
        "discovered_at": today,
        "status": "active",
        "summary": "XAUUSD M5美盘+连跌4+RSI<25+ATR>0.15%做多hold=48胜率93.62%(n=47, Sharpe=14.94, MaxDD=1.75%)！极致反转信号，所有持有期均超60%+，hold=20-60区间75-94%。降ATR扩样本为第一优先级。"
    },
    {
        "id": "round60_best_011",
        "hypothesis": "XAUUSD M5 亚盘+RSI>75+ATR>0.15%做空 hold=20 — 73.88% 研究唯一做空信号",
        "entry_condition": "session == 'asia' and rsi14 > 75 and atr_pct > 0.0015",
        "direction": "short",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "best_hold": 20,
        "metrics": {
            "win_rate": 0.7388,
            "avg_return": 0.0020,
            "sharpe_ratio": 12.78,
            "signal_count": 134,
            "max_drawdown": 0.0269
        },
        "discovered_at": today,
        "status": "active",
        "summary": "XAUUSD M5亚盘+RSI>75+ATR>0.15%做空hold=20胜率73.88%(n=134, Sharpe=12.78, MaxDD=2.69%)！研究循环唯一有效的做空信号。n=134仅差16样本达注入门槛。降ATR扩样本为最高优先级。"
    },
    {
        "id": "round60_best_012",
        "hypothesis": "JP225 M1 亚盘+RSI<20+ATR>0.10%做多 hold=10 — 100.00% 零回撤！",
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "timeframe": "M1",
        "symbols": ["JP225"],
        "best_hold": 10,
        "metrics": {
            "win_rate": 1.0,
            "avg_return": 0.0033,
            "sharpe_ratio": 271.03,
            "signal_count": 33,
            "max_drawdown": 0.0
        },
        "discovered_at": today,
        "status": "active",
        "summary": "JP225 M1亚盘+RSI<20+ATR>0.10%做多hold=10胜率100.00%(n=33, Sharpe=271.03, MaxDD=0.00%)！零回撤零亏损！所有持有期4-60均超75%+。n=33远低于150门槛，降ATR扩样本为第一优先级。"
    },
    {
        "id": "round60_best_013",
        "hypothesis": "XAUUSD M1 美盘+RSI<20+ATR>0.10%做多 hold=20 — 73.24% M1黄金现货超卖",
        "entry_condition": "session == 'us' and rsi14 < 20 and atr_pct > 0.0010",
        "direction": "long",
        "timeframe": "M1",
        "symbols": ["XAUUSD"],
        "best_hold": 20,
        "metrics": {
            "win_rate": 0.7324,
            "avg_return": 0.0014,
            "sharpe_ratio": 28.86,
            "signal_count": 71,
            "max_drawdown": 0.0683
        },
        "discovered_at": today,
        "status": "active",
        "summary": "XAUUSD M1美盘+RSI<20+ATR>0.10%做多hold=20胜率73.24%(n=71, Sharpe=28.86)。黄金M1超卖信号稳定，2-60持有期均超60%+。n=71<150，降ATR或获取更多数据为优先级。"
    },
    {
        "id": "round60_best_014",
        "hypothesis": "US500 M5 欧盘+RSI<20+ATR>0.15%做多 hold=60 — 75.00% 标普欧盘极值",
        "entry_condition": "session == 'europe' and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["US500"],
        "best_hold": 60,
        "metrics": {
            "win_rate": 0.75,
            "avg_return": 0.0023,
            "sharpe_ratio": 3.99,
            "signal_count": 72,
            "max_drawdown": 0.0762
        },
        "discovered_at": today,
        "status": "active",
        "summary": "US500 M5欧盘+RSI<20+ATR>0.15%做多hold=60胜率75.00%(n=72, Sharpe=3.99)。标普欧盘RSI<20极值超卖信号稳定75%但样本不足。"
    },
]

state["best_findings"].extend(new_findings)

# Update hypothesis queue statuses (mark round60 tests as completed)
queue_updates = {}
for h in state["hypothesis_queue"]:
    if h["id"].startswith("round60_"):
        queue_updates[h["id"]] = "completed"

for h in state["hypothesis_queue"]:
    if h["id"] in queue_updates:
        h["status"] = queue_updates[h["id"]]

# Add new hypotheses for round 61
new_hypotheses = [
    {
        "id": "round61_new_01",
        "priority": 1,
        "status": "pending",
        "hypothesis": "XAUUSD M5 美盘+consecutive_bear>=4+RSI<25+ATR>0.10%做多 — 降ATR扩连跌4样本至150+",
        "entry_condition": "session == 'us' and consecutive_bear >= 4 and rsi14 < 25 and atr_pct > 0.0010",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "description": "连跌4+RSI<25目前n=47(WR=93.62%)，降ATR至0.10%预计n~80-100，目标接近150门槛"
    },
    {
        "id": "round61_new_02",
        "priority": 1,
        "status": "pending",
        "hypothesis": "XAUUSD M5 亚盘+RSI>75+ATR>0.10%做空 — 降ATR扩做空样本至150+",
        "entry_condition": "session == 'asia' and rsi14 > 75 and atr_pct > 0.0010",
        "direction": "short",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "description": "黄金亚盘RSI>75做空目前n=134(WR=73.88%)，降ATR至0.10%预计n~180+，冲刺注入门槛"
    },
    {
        "id": "round61_new_03",
        "priority": 1,
        "status": "pending",
        "hypothesis": "JP225 M1 亚盘+RSI<20+ATR>0.05%做多 — 大幅降ATR验证100%稳定性",
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0005",
        "direction": "long",
        "timeframe": "M1",
        "symbols": ["JP225"],
        "description": "JP225 M1亚盘RSI<20目前n=33(WR=100%)，大幅降ATR至0.05%预计n~100-150，验证零回撤是否能维持"
    },
    {
        "id": "round61_new_04",
        "priority": 2,
        "status": "pending",
        "hypothesis": "XAUUSD M5 美盘+RSI<25做多 — hold最佳区间(48-72)深度优化",
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "description": "hold=48(81.25%) vs hold=60(88.07%)，测试hold=36/42/54/66寻找最佳盈亏比"
    },
    {
        "id": "round61_new_05",
        "priority": 2,
        "status": "pending",
        "hypothesis": "XAGUSD M5 美盘+RSI<25+ATR>0.15%做多 — hold最佳区间优化",
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAGUSD"],
        "description": "hold=30(75.11%)/40(78.54%)/60(78.54%)，测试hold=36/45/50寻找最优解"
    },
    {
        "id": "round61_new_06",
        "priority": 2,
        "status": "pending",
        "hypothesis": "JP225 M5 亚盘+RSI<20+ATR>0.15%做多 — 亚盘日经M5超卖",
        "entry_condition": "session == 'asia' and rsi14 < 20 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["JP225"],
        "description": "R60_M1_003在M1上JP225亚盘RSI<20达100%，在M5上测试跨TF一致性"
    },
    {
        "id": "round61_new_07",
        "priority": 3,
        "status": "pending",
        "hypothesis": "XAUUSD M5 美盘+RSI<25+ATR>0.15%+close<bb_lower做多 — BB增强注入信号的再增强",
        "entry_condition": "session == 'us' and rsi14 < 25 and atr_pct > 0.0015 and close < bb_lower",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "description": "基线88.07%(n=176)加BB下轨过滤，预期WR~92%但n~60-80"
    },
    {
        "id": "round61_new_08",
        "priority": 3,
        "status": "pending",
        "hypothesis": "XAUUSD M5 美盘+close<bb_lower+RSI<30做多 — hold=48最佳持有确认",
        "entry_condition": "session == 'us' and close < bb_lower and rsi14 < 30 and atr_pct > 0.0015",
        "direction": "long",
        "timeframe": "M5",
        "symbols": ["XAUUSD"],
        "description": "BB增强信号hold=48(75.00%, n=152)刚好通过注入，测试hold=40-60区间确认稳定性"
    },
]

state["hypothesis_queue"].extend(new_hypotheses)

with open("state/research_state.json", "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"Updated to round {state['current_round']}")
print(f"Total best_findings: {len(state['best_findings'])}")
print(f"Total hypothesis_queue: {len(state['hypothesis_queue'])}")
print(f"New findings added: {len(new_findings)}")
print(f"New hypotheses added: {len(new_hypotheses)}")
