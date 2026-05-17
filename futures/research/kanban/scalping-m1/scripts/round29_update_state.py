#!/usr/bin/env python3
"""Update research state after round29"""
import json
from datetime import datetime

state = {
    "current_round": 29,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round29_001": "组合策略实盘调度模拟 — 方案A(共振优先+双枪补充) WR=88.1% n=67, 中点差成本后WR=85.1%；方案B(全组合) WR=88.2% n=119; 方案C(原双枪) WR=87.7% n=114. 三种方案在加中点差后WR均在84-85%, 实盘可行. 推荐继续方案A.",
        "round29_002": "双枪策略月度跟踪 — 近6月组合WR=88.4% n=43持续有效; 2026-05本月WR=88.9% n=9; 回撤记录:2025-12(55.6%),2025-09(66.7%),2026-03(50%); 平均回撤间隔7.6月(非3-4月假说,需更多数据); ✅策略持续有效",
        "round29_003": "XAG美盘RSI<16+CB>=3跨周期验证 — P1 WR=100%(n=8 hold=55), P2 WR=85.7%(n=7 hold=70), P3 WR=80%(n=5 hold=30); 全周期WR=90% n=20 hold=70; 跨周期基本稳定(每段WR≥80%), 超越旧基准87.1%✅",
        "round29_004": "XAG美盘极端阈值积累 — RSI<14+CB>=4(12/20), RSI<16+CB>=5(11/20), RSI<12+CB>=3(14/20), RSI<12+CB>=4(10/20) 均无增长vs round28; 宽时段13-17探索WR均<62%, 不推荐❌",
        "round29_005": "M1 EU仿双枪继续等待数据 — 当前104天(无增长), 距180天还差76天; hold=24 WR降至79.6%; 最佳hold=37 WR=81.5%; M1 US宽条件探索WR=61% ❌; 建议暂缓M1方向",
        "round29_006": "US30/US500/USOIL等探索 — USOIL美盘RSI<14+CB>=3 WR=82.6% n=23 hold=75 🆕✅值得关注! US30最高RSI<14+CB>=3 WR=69.4%(不足70%); USTEC全❌; FX中AUDUSD/USDCHF/USDJPY有60-70%潜力; 突破策略/成交量辅助未发现有效模式"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=88.5% n=52 [🏆核心策略, 近6月94.1% n=17, round29持续优异]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=87.1% n=62 [🏆核心策略, 近6月84.6% n=26, round29持续有效]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): hold=42+115 WR=87.7% n=114 [🏆核心策略, 9.4次/月, round29近6月88.4%持续有效]",
        "XAUUSD_resonance_us": "共振美盘→XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=91.7% n=36 [🏆最高胜率, 2.1/月, round29成本分析后仍最稳]",
        "XAUUSD_combo_optimized": "组合调度(共振优先+双枪补充): hold=115 WR=88.1% n=67 [🆕推荐! 3.9/月, 中点差后WR=85.1%, round29成本分析通过✅]",
        "XAGUSD_US_new": "XAG美盘RSI<16+CB>=3 hold=70 WR=90.0% n=20 [🆕超越旧基准! round29跨周期验证通过, P1=100% P2=85.7% P3=80%]",
        "XAGUSD_US": "XAG美盘RSI<18+CB>=3 hold=105 WR=87.1% n=31 [旧基准稳定, round29持续确认]",
        "XAGUSD_EU": "XAG欧盘RSI<14+CB>=3 hold=85 WR=86.5% n=37 [hold=85最优, round29持续确认 CI[75.7%,97.3%]]",
        "JP225_US": "JP225美盘RSI<14+CB>=2 hold=55 WR=85.4% n=41 [跨周期稳定✅ bootstrap CI[73.2%,95.1%]]",
        "USOIL_US_new": "USOIL美盘RSI<14+CB>=3 hold=75 WR=82.6% n=23 [🆕新发现! 信号少但胜率高, 需更多数据积累]"
    },
    "next_actions": [
        "round30_001: USOIL方向深入研究 — round29发现USOIL US RSI<14+CB>=3 WR=82.6% n=23, 需进行跨周期验证和最优参数微调",
        "round30_002: XAG RSI<16+CB>=3 继续积累 — 新发现n=20刚达标, 已达标的极端阈值继续积累至n≥30增强可信度",
        "round30_003: 双枪策略继续月度跟踪 — 持续监测近6月表现, 重点关注2026-06~07是否出现回撤",
        "round30_004: FX品种初步筛选 — AUDUSD US RSI<14+CB>=2 WR=77.8% n=27, USDJPY RSI<18+CB>=2 WR=69.5% n=59, 值得深入探索",
        "round30_005: XAG极端阈值继续积累 — RSI<14+CB>=4(12/20)等n无增长, 需检查数据更新机制",
        "round30_006: 组合策略回测细化 — 对方案A/B/C进行逐笔回测(含交易成本、最大回撤、收益曲线)"
    ]
}

with open('/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/scripts/state/research_state.json', 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("State updated successfully")
