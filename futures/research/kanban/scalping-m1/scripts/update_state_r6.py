#!/usr/bin/env python3
"""Update research state with Round 6 findings."""
import json
from pathlib import Path

state_path = Path("/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/state/research_state_h1_m30.json")

with open(state_path) as f:
    state = json.load(f)

# Round 6 best findings
r6_findings = [
    {
        "id": "h1r6_001",
        "description": "USTEC H1 欧盘RSI<28 hold=50 — WR=100% n=16 CI=[100%-100%] Sharpe=19.01 (税后净收益, 最高置信度)",
        "timeframe": "H1",
        "direction": "long",
        "best_hold": 50,
        "win_rate": 100.0,
        "n": 16,
        "avg_return_pct": 0,
        "sharpe": 19.01,
        "source": "round6_h1r6_001"
    },
    {
        "id": "h1r6_002",
        "description": "JP225 H1 欧盘RSI<25 hold=10 — WR=95% n=20 Sharpe=30.63 CI=[85%-100%] (税后高Sharpe信号)",
        "timeframe": "H1",
        "direction": "long",
        "best_hold": 10,
        "win_rate": 95.0,
        "n": 20,
        "avg_return_pct": 0,
        "sharpe": 30.63,
        "source": "round6_h1r6_001"
    },
    {
        "id": "h1r6_003",
        "description": "USOIL H1 欧盘RSI<22 hold=13 — WR=94.7% n=19 Sharpe=29.02 CI=[84%-100%] (税后，油类高胜率)",
        "timeframe": "H1",
        "direction": "long",
        "best_hold": 13,
        "win_rate": 94.7,
        "n": 19,
        "avg_return_pct": 0,
        "sharpe": 29.02,
        "source": "round6_h1r6_001"
    },
    {
        "id": "h1r6_004",
        "description": "UKOIL M30 亚盘RSI<20 hold=160 — WR=95.7% n=47 Sharpe=6.05 AvgRet=2.79% (超长周期持有)",
        "timeframe": "M30",
        "direction": "long",
        "best_hold": 160,
        "win_rate": 95.7,
        "n": 47,
        "avg_return_pct": 2.794,
        "sharpe": 6.05,
        "source": "round6_h1r6_004"
    },
    {
        "id": "h1r6_005",
        "description": "USTEC M30 亚盘RSI<22 hold=160 — WR=93.0% n=43 Sharpe=7.81 AvgRet=1.94% (科技指数超长持有)",
        "timeframe": "M30",
        "direction": "long",
        "best_hold": 160,
        "win_rate": 93.0,
        "n": 43,
        "avg_return_pct": 1.938,
        "sharpe": 7.81,
        "source": "round6_h1r6_004"
    },
    {
        "id": "h1r6_006",
        "description": "EURUSD H1 美盘连阳>=3+RSI>70做空 hold=2 — WR=88.0% n=25 Sharpe=52.18 (最优short squeeze)",
        "timeframe": "H1",
        "direction": "short",
        "best_hold": 2,
        "win_rate": 88.0,
        "n": 25,
        "avg_return_pct": 0.073,
        "sharpe": 52.18,
        "source": "round6_h1r6_005"
    },
    {
        "id": "h1r6_007",
        "description": "GBPUSD M30 美盘连阳>=5+RSI>68做空 hold=3 — WR=86.4% n=22 Sharpe=41.37 (高胜率short squeeze)",
        "timeframe": "M30",
        "direction": "short",
        "best_hold": 3,
        "win_rate": 86.4,
        "n": 22,
        "avg_return_pct": 0.062,
        "sharpe": 41.37,
        "source": "round6_h1r6_005"
    },
    {
        "id": "h1r6_008",
        "description": "USDCHF M30 美盘连阳>=4+RSI>72做空 hold=10 — WR=85.2% n=27 Sharpe=29.08 (瑞郎short squeeze)",
        "timeframe": "M30",
        "direction": "short",
        "best_hold": 10,
        "win_rate": 85.2,
        "n": 27,
        "avg_return_pct": 0.123,
        "sharpe": 29.08,
        "source": "round6_h1r6_005"
    },
    {
        "id": "h1r6_009",
        "description": "USOIL H1 美盘连阳>=5+RSI>68做空 hold=2 — WR=90.0% n=10 Sharpe=45.6 (油类极端short squeeze)",
        "timeframe": "H1",
        "direction": "short",
        "best_hold": 2,
        "win_rate": 90.0,
        "n": 10,
        "avg_return_pct": 0.216,
        "sharpe": 45.6,
        "source": "round6_h1r6_005"
    },
    {
        "id": "h1r6_010",
        "description": "UKOIL M30 ATR×2.0 hold=20 — Sharpe 1.41→4.80 (+239.4%改进) (ATR最佳参数配置)",
        "timeframe": "M30",
        "direction": "long",
        "best_hold": 20,
        "win_rate": 50.0,
        "n": 52,
        "avg_return_pct": 0,
        "sharpe": 4.80,
        "source": "round6_h1r6_002"
    },
    {
        "id": "h1r6_011",
        "description": "US500 H1 ATR×1.8 hold=50 — Sharpe 2.71→6.07 (+123.5%) n=14 (ATR最佳单项)",
        "timeframe": "H1",
        "direction": "long",
        "best_hold": 50,
        "win_rate": 50.0,
        "n": 14,
        "avg_return_pct": 0,
        "sharpe": 6.07,
        "source": "round6_h1r6_002"
    },
]

# Remove previous round6 findings if any
state["best_findings"] = [f for f in state["best_findings"] if not f["id"].startswith("h1r6_")]
state["best_findings"].extend(r6_findings)

# Update current_round
state["current_round"] = 6

# Update metadata
state["last_round6_run"] = "2026-05-14 09:57 UTC"
state["data_freshness"] = {
    "H1_last_bar": "2026-05-14 09:00 UTC",
    "M30_last_bar": "2026-05-14 09:30 UTC",
    "source": "MT5 Exness-MT5Trial5 (from parquet)"
}

state["round6_key_findings"] = {
    "h1r6_001_summary": "H1高置信度信号税后回测: 201个合格信号, 93%税后仍正期望, USTEC/JP225/USOIL最佳",
    "h1r6_002_summary": "ATR精细优化: 416配置, UKOIL M30 ATR×2.0 Sharpe+239%, US500 H1 ATR×1.8 Sharpe+123.5%",
    "h1r6_003_summary": "多时间框架协同: 仅5个有效模式, H1趋势无法显著提升M30胜率 — 假设被拒绝",
    "h1r6_004_summary": "亚盘大周期持有: UKOIL hold=160 WR=95.7%, USTEC hold=160 WR=93%, USOIL hold=120 WR=85.7%",
    "h1r6_005_summary": "美盘short squeeze: 96个有效信号, EURUSD/GBPUSD/USOIL最佳, 连阳>=5+RSI>68组合最强",
    "h1r6_006_summary": "波动率regime filter: USDCHF/UKOIL/USOIL在特定波动率下有显著改进(+50% WR)",
}

state["pending_hypotheses_r7"] = [
    "P1: 高置信度信号实盘模拟扩展 — 税后正期望信号完整回测(含滑点执行模型)",
    "P1: ATR动态止损实盘落地 — 最优参数(ATR×1.2-1.8)在JP225/US500/USOIL上验证",
    "P2: 亚盘大周期持有退出机制优化 — ATR trailing + 时间衰减",
    "P2: 美盘short squeeze信号整合为完整策略框架(EURUSD/GBPUSD/USOIL)",
    "P3: 短持仓hold<=3信号的滑点敏感度分析",
    "P3: 波动率filter+欧盘超卖组合策略在HK50/USDCHF上验证"
]

with open(state_path, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"✅ State updated with Round 6 findings.")
print(f"Total best findings: {len(state['best_findings'])}")
print(f"Current round: {state['current_round']}")
