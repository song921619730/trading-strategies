#!/usr/bin/env python3
"""Round 66 — State Updater"""
import json
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "research_state.json"
RESULTS_PATH = Path(__file__).resolve().parent.parent / "logs" / "round66_researcher_results.json"

with open(RESULTS_PATH) as f:
    data = json.load(f)

TEST_DESC = {
    "R66_H1_A001": "H1 亚盘+连跌3+RSI<30+BBL+ATR>0.10%做多",
    "R66_H1_A002": "H1 亚盘+连跌3+RSI<30+BBL+ATR>0.07%做多",
    "R66_M30_A003": "M30 亚盘+连跌4+RSI<25+ATR>0.10%做多",
    "R66_M30_A004": "M30 亚盘+连跌4+RSI<25+ATR>0.07%做多",
    "R66_M30_A005": "M30 亚盘+RSI<20+ATR>0.08%做多",
    "R66_H1_B001": "H1 欧盘+RSI>70+ATR>0.10%做空",
    "R66_H1_B002": "H1 欧盘+RSI>65+ATR>0.10%做空",
    "R66_M30_B003": "M30 欧盘+RSI>70+ATR>0.10%做空",
    "R66_H1_B004": "H1 欧盘+RSI>70+ATR>0.07%做空",
    "R66_M30_C001": "M30 亚盘+RSI<20+ATR>0.15%做多(长持有72-96)",
    "R66_M30_C002": "M30 亚盘+RSI<25+ATR>0.10%做多(长持有72-96)",
    "R66_M30_C003": "M30 亚盘+RSI<22+ATR>0.15%做多(长持有72-96)",
    "R66_M30_C004": "M30 亚盘+RSI<20+ATR>0.10%做多(长持有72-96)",
    "R66_M30_D001": "M30 亚盘+RSI<25+ATR>0.15%做多",
    "R66_M30_D002": "M30 亚盘+RSI<25+ATR>0.10%做多",
    "R66_M30_D003": "M30 亚盘+RSI<28+ATR>0.10%做多",
    "R66_H1_E001": "H1 亚盘+RSI<25+ATR>0.15%+bb_pos<0.3做多",
    "R66_H1_E002": "H1 亚盘+RSI<25+ATR>0.12%+bb_pos<0.35做多",
    "R66_H1_E003": "H1 亚盘+RSI<25+ATR>0.15%+低于MA50做多",
    "R66_H1_F001": "H1 伦敦开盘(8-10)+RSI<30+ATR>0.10%做多",
    "R66_H1_F002": "H1 亚→欧转换(7-9)+RSI<25+ATR>0.07%做多",
    "R66_M30_G001": "M30 London-NY(12-14)+RSI<25+ATR>0.05%做多",
    "R66_M30_G002": "M30 London-NY(12-14)+RSI>70+ATR>0.05%做空",
    "R66_M30_G003": "M30 东京开盘(0-3)+RSI<25+ATR>0.05%做多",
    "R66_M30_G004": "M30 东京开盘(0-3)+RSI>70+ATR>0.05%做空",
    "R66_H1_H001": "H1 欧盘+RSI>70+ATR>0.10%做空(跨品种)",
    "R66_M30_H002": "M30 亚盘+RSI<20+ATR>0.10%做多(跨品种)",
}

# Extract findings
findings = []
for test_id, test_results in data.items():
    if not isinstance(test_results, dict):
        continue
    for sym, sym_res in test_results.items():
        if not isinstance(sym_res, dict):
            continue
        for hp, stats in sym_res.items():
            if not isinstance(stats, dict):
                continue
            n = stats.get("signal_count", 0)
            wr = stats.get("win_rate")
            avg_ret = stats.get("avg_return")
            sharpe = stats.get("sharpe_ratio")
            if wr is not None and n >= 30 and wr >= 0.60:
                findings.append({
                    "test_id": test_id,
                    "symbol": sym,
                    "hold_period": int(hp) if isinstance(hp, str) else hp,
                    "signal_count": n,
                    "win_rate": wr,
                    "avg_return": avg_ret,
                    "sharpe_ratio": sharpe,
                })

findings.sort(key=lambda x: (x["win_rate"], x["signal_count"]), reverse=True)

injectable = [f for f in findings if f["signal_count"] >= 150 and f["win_rate"] >= 0.65]
strong = [f for f in findings if f["win_rate"] >= 0.70 and f["signal_count"] >= 50]

# Build best_findings
best = []
for f in (injectable + strong)[:15]:
    is_inj = f['signal_count'] >= 150 and f['win_rate'] >= 0.65
    direction = "long" if f.get("avg_return", 0) is None or f["avg_return"] >= 0 else "short"
    entry = {
        "id": f"round66_{f['test_id']}_{f['symbol']}_{f['hold_period']}",
        "hypothesis": f"{f['symbol']} {f['test_id']} hold={f['hold_period']} — {f['win_rate']*100:.2f}% 注入！n={f['signal_count']}" if is_inj else f"{f['symbol']} {f['test_id']} hold={f['hold_period']} — {f['win_rate']*100:.2f}% 强信号！n={f['signal_count']}",
        "entry_condition": TEST_DESC.get(f['test_id'], f['test_id']),
        "direction": direction,
        "timeframe": "H1" if "H1" in f['test_id'] else "M30",
        "symbols": [f['symbol']],
        "best_hold": f['hold_period'],
        "metrics": {
            "win_rate": f['win_rate'],
            "avg_return": f['avg_return'],
            "sharpe_ratio": f['sharpe_ratio'],
            "signal_count": f['signal_count'],
        },
        "discovered_at": "2026-05-14",
        "status": "injectable" if is_inj else "active",
        "summary": f"{f['symbol']} {f['test_id']} hold={f['hold_period']} 胜率{f['win_rate']*100:.2f}%(n={f['signal_count']})"
    }
    best.append(entry)

state = {
    "topic": "Futures Intraday Pattern Mining — P0/P1 优先级定向优化 (Round 66)",
    "data": {
        "timeframes": ["H1", "M30"],
        "symbols": ["XAUUSD", "XAGUSD", "USTEC", "US30", "US500", "JP225", "HK50",
                    "USOIL", "UKOIL", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
        "status": "round66_complete",
        "data_start": "2021-01-03",
        "data_end": "2026-05-14",
        "last_update": "2026-05-14"
    },
    "current_round": 66,
    "last_completed_round": 66,
    "today": "2026-05-14",
    "best_findings": best,
    "round66_summary": {
        "total_tests": len(data),
        "total_findings": len(findings),
        "injectable": len(injectable),
        "strong": len(strong),
        "key_insights": [
            "JP225 H1连跌+RSI<30+BBL触碰信号天花板(n=178)，非ATR限制因子",
            "USDJPY欧盘做空降ATR扩样本失败(WR从72%降至55%)，此路径关闭",
            "UKOIL长持有期72-96无增强效应，最佳持有期45-60确认",
            "US500 M30 亚盘RSI<25+ATR>0.10% → n=182, WR=65.38% 新弱可注入信号",
            "USOIL M30 Session窗口(12-14/0-3)超卖→ n=263, WR=65.02% 新发现",
            "AUDUSD H1 bb_pos降ATR后WR全面<45%，低ATR信号不可靠",
        ],
        "closed_paths": ["USDJPY欧盘做空扩样本", "UKOIL长持有期>60", "JP225极限降ATR>0.15%"],
        "active_paths": ["US500 M30 RSI<25", "USOIL Session窗口超卖", "JP225 H1连跌注入参数优化"],
    }
}

STATE_PATH.parent.mkdir(exist_ok=True)
with open(STATE_PATH, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)
print(f"✅ State updated: {STATE_PATH}")
print(f"   Round 66 complete. Round state advanced to 66.")
print(f"   {len(injectable)} injectable, {len(strong)} strong signals added.")
print(f"   Key: {len(findings)} total findings across {len(data)} tests.")
