#!/usr/bin/env python3
"""Update research state with Round 5 findings."""
import json
from pathlib import Path

state_path = Path("/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/state/research_state_h1_m30.json")

with open(state_path) as f:
    state = json.load(f)

# Add Round 5 best findings
r5_findings = [
    {
        "id": "h1r5_001",
        "description": "USTEC H1 欧盘RSI<28 hold=50 — WR=100.0% n=16 CI=[100%-100%] Sharpe=19.2 (最高置信度信号)",
        "timeframe": "H1",
        "direction": "long",
        "best_hold": 50,
        "win_rate": 100.0,
        "n": 16,
        "avg_return_pct": 0.0,
        "sharpe": 19.2,
        "source": "round5_h1r5_001"
    },
    {
        "id": "h1r5_002",
        "description": "JP225 M30 欧盘CB>=4+RSI<20 hold=25 — WR=100.0% n=9 Sharpe=45.98 (最佳持仓期优化)",
        "timeframe": "M30",
        "direction": "long",
        "best_hold": 25,
        "win_rate": 100.0,
        "n": 9,
        "avg_return_pct": 0.994,
        "sharpe": 45.98,
        "source": "round5_h1r5_002"
    },
    {
        "id": "h1r5_003",
        "description": "UKOIL M30 亚盘RSI<20 hold=60 — WR=91.5% n=47 Sharpe=10.47 AvgRet=2.811% (油类大周期持有表现优秀)",
        "timeframe": "M30",
        "direction": "long",
        "best_hold": 60,
        "win_rate": 91.5,
        "n": 47,
        "avg_return_pct": 2.811,
        "sharpe": 10.47,
        "source": "round5_h1r5_002"
    },
    {
        "id": "h1r5_004",
        "description": "US500 M30 亚盘RSI<22 hold=80 — WR=90.5% n=42 Sharpe=9.9 AvgRet=1.172% (亚盘指数大周期持有)",
        "timeframe": "M30",
        "direction": "long",
        "best_hold": 80,
        "win_rate": 90.5,
        "n": 42,
        "avg_return_pct": 1.172,
        "sharpe": 9.9,
        "source": "round5_h1r5_002"
    },
    {
        "id": "h1r5_005",
        "description": "GBPUSD M30 欧盘RSI<20 hold=5 — WR=84.8% n=33 Sharpe=34.38 (欧盘→美盘延续性最佳)",
        "timeframe": "M30",
        "direction": "long",
        "best_hold": 5,
        "win_rate": 84.8,
        "n": 33,
        "avg_return_pct": 0.109,
        "sharpe": 34.38,
        "source": "round5_h1r5_004"
    },
    {
        "id": "h1r5_006",
        "description": "USOIL M30 亚盘RSI<22 hold=60 — WR=84.2% n=57 Sharpe=8.84 AvgRet=2.733% (油类信号频率高)",
        "timeframe": "M30",
        "direction": "long",
        "best_hold": 60,
        "win_rate": 84.2,
        "n": 57,
        "avg_return_pct": 2.733,
        "sharpe": 8.84,
        "source": "round5_h1r5_002"
    },
]

# Remove previous round5 findings if any
state["best_findings"] = [f for f in state["best_findings"] if not f["id"].startswith("h1r5_")]
state["best_findings"].extend(r5_findings)

# Update metadata
state["last_round5_run"] = "2026-05-14 09:51 UTC"
state["data_freshness"] = {
    "M1_last_bar": "2026-05-14 09:50 UTC",
    "H1_last_bar": "2026-05-14 09:00 UTC",
    "M30_last_bar": "2026-05-14 09:30 UTC",
    "source": "MT5 Exness-MT5Trial5 (fresh fetch)"
}

state["round5_key_findings"] = {
    "h1r5_001_summary": "H1欧盘超卖bootstrap CI分层: 163个合格信号, USTEC最高(100% WR n=16 CI窄幅)",
    "h1r5_002_summary": "M30跨品种hold扩展: JP225 CB4+RSI<20 hold=25 WR=100%, UKOIL亚洲RSI<20 hold=60 WR=91.5%",
    "h1r5_003_summary": "ATR动态止损: US500 H1 ATRx2.0 Sharpe改进+115.7%, 但多数品种ATR止损无优势",
    "h1r5_004_summary": "M30欧盘→美盘延续: GBPUSD RSI<20 hold=5 WR=84.8%, USOIL/UKOIL最佳持有60期",
    "data_update": "✅ 成功从MT5获取新鲜M1数据(+336 bars/品种), H1/M30重采样完成"
}

state["pending_hypotheses_r6"] = [
    "P1: H1高置信度信号(CI<15%)实盘模拟回测(含佣金滑点)",
    "P1: ATR参数优化扫描(ATR×1.2/1.5/1.8/2.0)",
    "P2: H1/M30多时间框架协同入场出场策略",
    "P2: US500/USOIL/UKOIL亚盘大周期持有策略深度优化",
    "P3: 欧盘→美盘波动率 regime filter",
    "P3: 做空信号深化(超买+CBull美盘short squeeze)"
]

with open(state_path, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print("✅ State updated with Round 5 findings.")
print(f"Total best findings: {len(state['best_findings'])}")
