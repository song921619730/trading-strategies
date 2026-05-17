#!/usr/bin/env python3
"""Update research state after round35"""
import json
from datetime import datetime

state = {
    "current_round": 35,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round35_001": "XAGUSD M30 做空策略深度验证 — CBull>=4+RSI>80 WR=78.6% n=28 hold=100 CI=[60.7%,92.9%]；CBull>=5+RSI>80 WR=82.4% n=17；时段细化发现US盘WR=85.7-90.0%(hold=35)显著优于欧洲盘；Hold敏感性扫描确认hold=100为最优(78.6%)。结论:✅ M30做空策略跨周期3/3通过，推荐纳入候补",
        "round35_002": "XAGUSD H1 做空策略方向修正 — H1框架下XAGUSD做空WR仅25-50%(n>10)，与Round32报告矛盾(Round32的WR=89.5%未能复现，因H1数据量少且hold参数不同)。结论:⚠️ H1 XAGUSD做空不可靠，建议放弃H1做空方向，专注M30",
        "round35_003": "EURUSD H1 CB>=3+RSI<20做多 — WR=100% n=11 hold=60 Bootstrap CI=[100%,100%] 跨周期3/3通过；CB>=3+RSI<25 WR=82.1% n=28 CI=[67.9%,96.4%] 跨周期3/3通过；M30版本CB>=3+RSI<20 WR=76.9% n=39 hold=70 CI=[64.1%,89.7%]; 结论:✅ EURUSD H1连续阴线+超卖做多是可靠信号，推荐纳入best_known",
        "round35_004": "USDJPY H1 做多月度跟踪 — CB>=5+RSI<25 WR=100% n=17 hold=190 跨周期3/3；月度跟踪2026-02~04 n=10 WR=100% avg=0.58%；M30版本WR=68.2% n=22(较弱)。结论:✅ H1版本持续有效，M30版本需积累更多数据",
        "round35_005": "H1/M30 全品种扫描 — 发现多个新信号：UKOIL CB>=4+RSI<25 M30 WR=96.9% n=32；JP225 CB>=5+RSI<25 H1 WR=100% n=16；US500 CB>=4+RSI<20 H1 WR=100% n=11；USOIL InsideBar+RSI<20 M30 WR=100% n=15。结论:🧪 指数和原油H1/M30有潜力，需进一步验证",
        "round35_006": "XAUUSD H1/M30 专项 — H1做多WR仅37-60%(不足)；M30做空CBull>=5+RSI>80 WR=72.2% n=18；Doji+RSI>75+us WR=100% n=12(30M) hold=35；XAUUSD H1 Doji+RSI>75+us WR=100% n=6。结论:🧪 XAUUSD在H1/M30上不如M5有效，仅Doji十字星做空策略值得关注",
        "round35_007": "跨框架一致性 — XAGUSD CBull>=4+RSI>80在M30上有效(WR=78.6%)但在H1上无效(WR=45%)，说明策略的时间框架特异性强，不能简单跨框架移植。结论:⚠️ 每个时间框架需独立验证",
        "round35_008": "H1/M30 跨品种信号排序 — 做多最强: JP225(77.8%)>US500(79.3%)>UKOIL(76%)>USOIL(75%)/H1；做空最强: XAGUSD(61.2%)>EURUSD(66.7%)>GBPUSD(62.1%)/H1。结论:📊 指数和原油在H1/M30做多信号显著优于外汇"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.3% n=122",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘→XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "🏆 XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [跨周期3/3通过]",
        "USDJPY_H1_long": "✅ USDJPY H1 CB>=5+RSI<25做多 WR=100% n=17 hold=190 [月度跟踪100%✅正式纳入]",
        "EURUSD_H1_long": "🆕 EURUSD H1 CB>=3+RSI<20做多 WR=100% n=11 hold=60 CI=[100%,100%] 跨周期3/3✅",
        "EURUSD_H1_long_safe": "🆕 EURUSD H1 CB>=3+RSI<25做多 WR=82.1% n=28 hold=60 CI=[67.9%,96.4%] 跨周期3/3✅",
        "EURUSD_M30_long": "🆕 EURUSD M30 CB>=3+RSI<20做多 WR=76.9% n=39 hold=70 CI=[64.1%,89.7%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT": "🆕 XAGUSD M30 SHORT CBull>=4+RSI>80 WR=78.6% n=28 hold=100 CI=[60.7%,92.9%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT_us": "🆕 XAGUSD M30 SHORT CBull>=4+RSI>80+us WR=85.7% n=14 hold=35",
        "XAGUSD_M30_SHORT_strong": "XAGUSD M30 SHORT CBull>=5+RSI>80 WR=82.4% n=17 hold=100",
        "JP225_H1_long": "🆕 JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40",
        "JP225_M30_long": "🆕 JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=140",
        "UKOIL_M30_long": "🆕 UKOIL M30 CB>=4+RSI<25做多 WR=96.9% n=32 hold=140",
        "US500_H1_long": "🆕 US500 H1 CB>=4+RSI<20做多 WR=100% n=11 hold=30",
        "USOIL_M30_inside_long": "🆕 USOIL M30 InsideBar+RSI<20做多 WR=100% n=15 hold=80",
        "XAUUSD_M30_Doji_short": "🆕 XAUUSD M30 Doji+RSI>75+us做空 WR=100% n=12 hold=35",
        "USOIL_M30_long": "USOIL M30 CB>=4+RSI<25做多 WR=79.5% n=39 hold=110",
        "AUDUSD_US": "AUDUSD美盘RSI<16+CB>=3 hold=125 WR=77.8% n=45",
        "JP225_US": "JP225美盘RSI<14+CB>=2 hold=55 WR=73.4% n=64",
        "XAGUSD_US": "XAG美盘RSI<18+CB>=3 hold=105 WR=75.0% n=60",
        "XAGUSD_EU": "XAG欧盘RSI<14+CB>=3 hold=85 WR=86.5% n=37"
    },
    "warnings": [
        "🔴 H1数据仅~1672行/M30仅~3344行(~3.5月)，统计稳定性不足，WR>90%的信号需谨慎",
        "🔴 H1/M30最新数据停于13:00/13:30 UTC，美盘后半段数据缺失(US18+=0)",
        "⚠️ XAGUSD做空策略在H1和M30上表现截然不同(45% vs 78.6%)，跨框架不可移植",
        "⚠️ UKOIL/USOIL的M30做多WR极高(96.9%)但n=32尚需积累",
        "⚠️ GBPUSD/us30/US500/USDTEC 做空信号均<60% WR，H1/M30做空整体弱于做多"
    ],
    "next_actions": [
        "round36_001: EURUSD H1 CB>=3+RSI<20/25继续积累并开启月度跟踪",
        "round36_002: XAGUSD M30 SHORT CBull>=4+RSI>80继续积累 n=28→目标50",
        "round36_003: JP225 H1/M30 做多策略深度验证 — WR>95% 跨周期检查",
        "round36_004: UKOIL/USOIL M30 做多策略验证 — WR>96% 需跨周期+Bootstrap确认",
        "round36_005: US500/US30 H1 做多策略验证 — WR>94% 需跨周期确认",
        "round36_006: XAUUSD M30 Doji+RSI>75+us做空 — WR=100% n=12 需更多数据",
        "round36_007: MT5数据下载时间调整 — 在18-20 UTC运行以覆盖完整美盘",
        "round36_008: H1/M30 信号频率统计 — 为每个最佳策略计算信号/月比率"
    ]
}

with open('/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/state/research_state.json', 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("State updated successfully (current_round=35)")
