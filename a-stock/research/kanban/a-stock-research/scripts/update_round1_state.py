#!/usr/bin/env python3
"""更新 research_state.json 为 Round 1 发现"""
import json, os

STATE_PATH = "state/research_state.json"

# 加载当前 state
with open(STATE_PATH, 'r', encoding='utf-8') as f:
    state = json.load(f)

# 更新状态
state["current_round"] = 1
state["data"]["last_update"] = "2026-05-14"
state["fatigue_count"] = 0

# 清空旧 hypothesis_queue，放新的
state["hypothesis_queue"] = [
    {
        "id": "scalp_006",
        "hypothesis": "M1 RSI<30+收阳 → 持有5根M1做多（跨品种验证）",
        "direction": "long",
        "priority": "high",
        "source": "Round1",
        "status": "pending"
    },
    {
        "id": "scalp_007",
        "hypothesis": "M5布林下轨+收阳 → 持有5根M5做多（跨品种验证）",
        "direction": "long",
        "priority": "high",
        "source": "Round1",
        "status": "pending"
    },
    {
        "id": "scalp_008",
        "hypothesis": "XAGUSD M1 RSI<30 → 超短反弹（品种特异）",
        "direction": "long",
        "priority": "medium",
        "source": "Round1",
        "status": "pending"
    },
    {
        "id": "scalp_009",
        "hypothesis": "M5成交量>2x均值+反转K线 → 1根做多",
        "direction": "long",
        "priority": "medium",
        "source": "Round1",
        "status": "pending"
    },
    {
        "id": "scalp_010",
        "hypothesis": "M5布林下轨触底+RSI<40+收阳 → 5根做多（组合过滤）",
        "direction": "long",
        "priority": "medium",
        "source": "Round1",
        "status": "pending"
    }
]

# 添加 best findings
state["best_findings"] = [
    {
        "id": "scalp_find_001",
        "hypothesis": "M1 RSI<30+收阳 → 持有5根M1做多",
        "level": "B+",
        "win_rate": 60.55,
        "ci_lower": 53.93,
        "signal_count": 218,
        "avg_return": 0.0104,
        "analyst": "Reze",
        "date": "2026-05-14",
        "notes": "跨5品种汇总。XAGUSD表现最强(WR=80.95%, n=21)，但样本有限。M1级别超卖反弹信号有限但胜率较高。需要更多数据验证。"
    },
    {
        "id": "scalp_find_002",
        "hypothesis": "M5布林下轨触底+收阳 → 持有5根M5做多",
        "level": "B",
        "win_rate": 54.17,
        "ci_lower": 51.30,
        "signal_count": 1163,
        "avg_return": 0.0176,
        "analyst": "Reze",
        "date": "2026-05-14",
        "notes": "跨5品种汇总。US30最有效(WR=60.51%, n=195, CI_lower=53.51%), US500次之(WR=56.94%, n=216)。XAUUSD/XAGUSD偏弱。CI_lower>50%说明统计显著。"
    },
    {
        "id": "scalp_find_003",
        "hypothesis": "M5 放量反转(vol>2x均量+前阴后阳) → 1根做多",
        "level": "B",
        "win_rate": 52.04,
        "ci_lower": 46.56,
        "signal_count": 319,
        "avg_return": 0.0153,
        "analyst": "Reze",
        "date": "2026-05-14",
        "notes": "XAGUSD最强(WR=62.86%, n=35, avg=+0.0634%), JP225(55.42%, n=83)。信号有限但平均收益较高。"
    },
    {
        "id": "scalp_find_004",
        "hypothesis": "M1 连续3阴线 → 第4根做多",
        "level": "C",
        "win_rate": 51.34,
        "ci_lower": 49.50,
        "signal_count": 2834,
        "avg_return": 0.0009,
        "analyst": "Reze",
        "date": "2026-05-14",
        "notes": "大样本但胜率接近50%，无明显统计显著性。不推荐作为独立入场条件。"
    },
    {
        "id": "scalp_find_005",
        "hypothesis": "M1 RSI<30+收阳 → 持有3根M1做多",
        "level": "B",
        "win_rate": 56.88,
        "ci_lower": 50.24,
        "signal_count": 218,
        "avg_return": 0.0070,
        "analyst": "Reze",
        "date": "2026-05-14"
    }
]

# 更新 hypothesis_history
state["hypothesis_history"] = [
    {
        "id": "scalp_001",
        "hypothesis": "M5 RSI<30超卖 + K线收阳 → 下一根M5反弹做多",
        "direction": "long",
        "priority": "high",
        "source": "初始假设",
        "status": "completed",
        "verdict": "部分有效",
        "results_summary": "M5 RSI<30+收阳→1根做多: WR=51.77%, CI_lower=45.28%, n=226, avg=+0.0045%. 无效(CI<50%). M1版本更强(WR=55.50%)."
    },
    {
        "id": "scalp_002",
        "hypothesis": "M5 RSI>70超买 + K线收阴 → 下一根M5回调做空",
        "direction": "short",
        "priority": "high",
        "source": "初始假设",
        "status": "completed",
        "verdict": "拒绝",
        "results_summary": "M5 RSI>70+收阴→做空: WR~47-50%, avg_ret负值. 做空信号在M1/M5级别无效."
    },
    {
        "id": "scalp_003",
        "hypothesis": "M1连续3根阴线(累计跌幅>0.5%) → 第4根反弹做多",
        "direction": "long",
        "priority": "medium",
        "source": "初始假设",
        "status": "completed",
        "verdict": "拒绝",
        "results_summary": "M1连续3阴→做多: WR=51.34%, CI_lower=49.50%, n=2834. 无统计显著性(CI跨50%)."
    },
    {
        "id": "scalp_004",
        "hypothesis": "M5布林下轨触底+收阳线 → 做多至中轨",
        "direction": "long",
        "priority": "medium",
        "source": "初始假设",
        "status": "completed",
        "verdict": "接受",
        "results_summary": "M5布林下轨+收阳→5根做多: WR=54.17%, CI_lower=51.30%, n=1163, avg=+0.0176%. 统计显著, 特别是US30(WR=60.51%)."
    },
    {
        "id": "scalp_005",
        "hypothesis": "XAUUSD M5成交量突增(>2x均值)+反向K线 → 反转信号",
        "direction": "both",
        "priority": "medium",
        "source": "初始假设",
        "status": "completed",
        "verdict": "部分有效",
        "results_summary": "M5放量反转→1根做多: 汇总WR=52.04%, n=319. XAGUSD特异有效(WR=62.86%). 信号量有限."
    }
]

with open(STATE_PATH, 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("State updated to Round 1")
