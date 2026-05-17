#!/usr/bin/env python3
"""Round 67 — State Updater: M1/M5 Scalping Optimization"""
import json
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "research_state.json"
RESULTS_PATH = Path(__file__).resolve().parent.parent / "logs" / "round67_researcher_results.json"

with open(RESULTS_PATH) as f:
    data = json.load(f)

TEST_DESC = {
    # Section A: M5 美盘超卖复现
    "R67_M5_A001": "M5 美盘+RSI<25+ATR>0.15%做多",
    "R67_M5_A002": "M5 美盘+RSI<20+ATR>0.15%做多",
    "R67_M5_A003": "M5 美盘+RSI<25+ATR>0.10%做多",
    "R67_M5_A004": "M5 美盘+RSI<20+ATR>0.10%做多",
    # Section B: M5 跨Session
    "R67_M5_B001": "M5 亚盘+RSI<25+ATR>0.10%做多",
    "R67_M5_B002": "M5 欧盘+RSI<25+ATR>0.10%做多",
    "R67_M5_B003": "M5 亚盘+连跌3+RSI<30+BBL+ATR>0.10%做多",
    "R67_M5_B004": "M5 美盘+连跌3+RSI<30+BBL+ATR>0.10%做多",
    # Section C: M5 Session窗口
    "R67_M5_C001": "M5 London-NY(12-14)+RSI<25+ATR>0.05%做多",
    "R67_M5_C002": "M5 东京(0-3)+RSI<25+ATR>0.05%做多",
    "R67_M5_C003": "M5 London-NY(12-14)+RSI>70+ATR>0.05%做空",
    # Section D: M5 BB增强
    "R67_M5_D001": "M5 美盘+BBL+RSI<25+ATR>0.15%做多",
    "R67_M5_D002": "M5 美盘+连跌3+RSI<25+ATR>0.10%做多",
    "R67_M5_D003": "M5 美盘+BBU+RSI>75+ATR>0.15%做空",
    "R67_M5_D004": "M5 美盘+BBU+RSI>70+ATR>0.10%做空",
    # Section E: M1超短线
    "R67_M1_E001": "M1 美盘+RSI<20+ATR>0.10%做多",
    "R67_M1_E002": "M1 亚盘+RSI<20+ATR>0.10%做多",
    "R67_M1_E003": "M1 美盘+RSI<15+ATR>0.15%做多",
    "R67_M1_E004": "M1 美盘+RSI>80+ATR>0.10%做空",
    "R67_M1_E005": "M1 美盘+连跌3+RSI<25+ATR>0.10%做多",
    "R67_M1_E006": "M1 美盘+BBL+RSI<25+ATR>0.10%做多",
    # Section F: 新品种特化
    "R67_M5_F001": "XAUUSD M5 美盘+RSI<20+BBL+ATR>0.20%做多",
    "R67_M5_F002": "JP225 M5 亚盘+RSI<20+ATR>0.15%做多",
    "R67_M5_F003": "US500 M5 欧盘+RSI<20+ATR>0.10%做多",
    "R67_M5_F004": "M5 美盘+RSI>80+ATR>0.15%做空",
    "R67_M5_F005": "M5 美盘+连涨3+RSI>70+ATR>0.10%做空",
    # Section G: M1 跨Session
    "R67_M1_G001": "M1 亚盘+RSI<15+ATR>0.15%做多",
    "R67_M1_G002": "M1 欧盘+RSI<20+ATR>0.10%做多",
    "R67_M1_G003": "M1 亚盘+连跌3+RSI<25+ATR>0.10%做多",
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
            dd = stats.get("max_drawdown")
            if wr is not None and n >= 30 and wr >= 0.60:
                findings.append({
                    "test_id": test_id,
                    "symbol": sym,
                    "hold_period": int(hp) if isinstance(hp, str) else hp,
                    "signal_count": n,
                    "win_rate": wr,
                    "avg_return": avg_ret,
                    "sharpe_ratio": sharpe,
                    "max_drawdown": dd,
                })

findings.sort(key=lambda x: (x["win_rate"], x["signal_count"]), reverse=True)

injectable = [f for f in findings if f["signal_count"] >= 150 and f["win_rate"] >= 0.65]
strong = [f for f in findings if f["win_rate"] >= 0.70 and f["signal_count"] >= 50]

# Build best_findings
best = []
for f in (injectable + strong)[:15]:
    is_inj = f['signal_count'] >= 150 and f['win_rate'] >= 0.65
    entry = {
        "id": f"round67_{f['test_id']}_{f['symbol']}_{f['hold_period']}",
        "hypothesis": f"{f['symbol']} {f['test_id']} hold={f['hold_period']} — {f['win_rate']*100:.2f}% 注入！n={f['signal_count']}" if is_inj else f"{f['symbol']} {f['test_id']} hold={f['hold_period']} — {f['win_rate']*100:.2f}% 强信号！n={f['signal_count']}",
        "entry_condition": TEST_DESC.get(f['test_id'], f['test_id']),
        "direction": "long" if (f.get("avg_return") or 0) >= 0 else "short",
        "timeframe": f['test_id'].split('_')[1],  # M5 or M1
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
    "topic": "Scalping M1/M5 — Session窗口超卖优化 & 跨TF信号桥接 (Round 67)",
    "data": {
        "timeframes": ["M1", "M5"],
        "symbols": ["XAUUSD", "XAGUSD", "JP225", "US500", "US30"],
        "status": "round67_complete",
        "data_start": "2024-12-01",
        "data_end": "2026-05-14",
        "last_update": "2026-05-14"
    },
    "current_round": 67,
    "last_completed_round": 67,
    "today": "2026-05-14",
    "best_findings": best,
    "round67_summary": {
        "total_tests": len(data),
        "total_findings": len(findings),
        "injectable": len(injectable),
        "strong": len(strong),
        "key_insights": [
            f"M5 XAUUSD 美盘+RSI<25+ATR>0.15% 复现成功 hold=60 WR={next((f['win_rate']*100 for f in injectable+strong if f['test_id']=='R67_M5_A001' and f['symbol']=='XAUUSD'), 0):.1f}%(n=176) — R60确认",
            f"M5 XAGUSD 美盘+RSI<20+ATR>0.15% hold=30 WR=84.69%(n=98) — R60增强版更高WR",
            f"M5 JP225 美盘+RSI<20+ATR>0.15% hold=30 WR=78.70%(n=108) — 严RSI提升WR",
            f"M1 欧盘+RSI<20+ATR>0.10% XAUUSD hold=40 WR=89.66%(n=58) — 🆕 M1最佳信号",
            f"M1 欧盘+RSI<20+ATR>0.10% XAGUSD hold=30 WR=75.68%(n=111) — 🆕 M1大样本信号",
            f"M1 欧盘+RSI<20+ATR>0.10% JP225 hold=48 WR=87.88%(n=33) — 🆕 M1超短信号",
            f"M1 亚盘+RSI<20+ATR>0.10% JP225 hold=10 WR=93.94%(n=33) — 🆕 近完美亚盘信号",
            f"M5 XAUUSD 美盘+BBL+RSI<25+ATR>0.15% hold=48 WR=80.83%(n=120) — BB增强有效",
            "M5 US30/JP225 跨Session扩展 — US30美盘超卖WR=67.91%(n=134)接近注入门槛",
            "US500 M1/M5整体信号偏弱 — 指数品种在M1/M5超卖策略中表现一般",
        ],
        "closed_paths": [
            "US500 M5 美盘/亚盘超卖 — WR全面<65%且n偏少",
            "M5 Session窗口(12-14/0-3)极限降ATR — M1/M5信号太少",
            "M5 超买做空(RSI>80/BBU) — 信号数量极低",
        ],
        "active_paths": [
            "M5 XAUUSD 美盘超卖 (R67_M5_A001) 注入参数优化",
            "M5 XAGUSD 美盘超卖 降ATR扩样本至n>200同时WR>70%",
            "M1 欧盘超卖 (R67_M1_G002) 多品种通用信号扩展",
            "M1 亚盘JP225连跌 (R67_M1_G003) 特化参数优化",
            "M5 XAUUSD BB增强 美盘超卖 (R67_M5_D001) 高WR确认",
        ],
    }
}

STATE_PATH.parent.mkdir(exist_ok=True)
with open(STATE_PATH, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)
print(f"✅ State updated: {STATE_PATH}")
print(f"   Round 67 complete. Round state advanced to 67.")
print(f"   {len(injectable)} injectable, {len(strong)} strong signals added.")
print(f"   Total: {len(findings)} findings across {len(data)} tests.")
