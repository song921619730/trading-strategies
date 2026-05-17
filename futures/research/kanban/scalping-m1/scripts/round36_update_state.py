#!/usr/bin/env python3
"""Update research state after round36"""
import json
from datetime import datetime

state = {
    "current_round": 36,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round36_001": "EURUSD H1 CB>=3+RSI<20/25月度跟踪 — CB>=3+RSI<20 WR=100% n=11 hold=60 跨周期3/3通过；CB>=3+RSI<25 WR=82.1% n=28 月度连4月稳定(83.3%)。结论:✅ EURUSD H1做多持续有效，确认保留best_known",
        "round36_002": "XAGUSD M30 SHORT积累 — CBull>=4+RSI>80 WR=78.6% n=28 hold=100 CI=[64.3%,92.9%]跨周期3/3通过；CBull>=5+RSI>80 WR=82.4% n=17；US盘WR=85.7% hold=35。结论:✅ n从28继续积累，跨周期3/3全通",
        "round36_003": "JP225 H1/M30做多深度验证 — H1 CB>=4+RSI<20 WR=94.7% n=19 跨周期3/3✅; CB>=4+RSI<25 WR=92.3% n=26 跨周期3/3✅; M30 CB>=4+RSI<20 WR=95.5% n=22 跨周期3/3✅。结论:✅ JP225 H1/M30做多极强，推荐纳入best_known",
        "round36_004": "UKOIL/USOIL M30做多验证 — UKOIL CB>=4+RSI<20 WR=100% n=23 跨周期3/3✅; CB>=4+RSI<25 WR=96.9% n=32 跨周期3/3✅; USOIL CB>=4+RSI<25 WR=79.5% n=39 跨周期3/3✅。结论:✅ UKOIL极强(推荐候补)，USOIL稳健但<80%",
        "round36_005": "US500/US30 H1做多验证 — US500 CB>=4+RSI<20 WR=100% n=11 hold=30 跨周期2/3(P3无数据)；US30 CB>=4+RSI<20 WR=92.9% n=14 跨周期3/3✅。结论:🧪 指数H1做多可行，但US500 P3缺数据需补全美盘",
        "round36_006": "XAUUSD M30 Doji+RSI>75+us做空 — WR=100% n=12 hold=35 CI=[100%,100%] 跨周期2/3。结论:🧪 n=12无增长，需要更多数据",
        "round36_007": "M1/M5目标品种扫描 — XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55(冠军级)；XAGUSD M5 EU CB>=3+RSI<10 WR=76.2% n=42；US500 M5 EU CB>=4+RSI<14 WR=78.1% n=73。结论:🧪 M1/M5多个潜力信号待验证",
        "round36_008": "H1/M30信号频率统计 — H1月均10-15次/品种，M30月均18-26次/品种。UKOIL SHORT和GBPUSD LONG是M30最高频信号(25.6次/月)。结论:📊 信号频率充足，适合实盘交易"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.3% n=122",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘→XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "🏆 XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [跨周期3/3通过]",
        "USDJPY_H1_long": "✅ USDJPY H1 CB>=5+RSI<25做多 WR=100% n=17 hold=190 [月度跟踪100%✅正式纳入]",
        "EURUSD_H1_long": "✅ EURUSD H1 CB>=3+RSI<20做多 WR=100% n=11 hold=60 CI=[100%,100%] 跨周期3/3✅",
        "EURUSD_H1_long_safe": "✅ EURUSD H1 CB>=3+RSI<25做多 WR=82.1% n=28 hold=60 CI=[67.9%,96.4%] 跨周期3/3✅ 月度跟踪4月稳定83.3%",
        "EURUSD_M30_long": "🆕 EURUSD M30 CB>=3+RSI<20做多 WR=76.9% n=39 hold=70 CI=[64.1%,89.7%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT": "✅ XAGUSD M30 SHORT CBull>=4+RSI>80 WR=78.6% n=28 hold=100 CI=[64.3%,92.9%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT_us": "XAGUSD M30 SHORT CBull>=4+RSI>80+us WR=85.7% n=14 hold=35",
        "XAGUSD_M30_SHORT_strong": "XAGUSD M30 SHORT CBull>=5+RSI>80 WR=82.4% n=17 hold=100",
        "JP225_H1_long": "🆕 JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 跨周期3/3✅ [推荐正式纳入]",
        "JP225_H1_long_safe": "🆕 JP225 H1 CB>=4+RSI<25做多 WR=92.3% n=26 hold=40 跨周期3/3✅",
        "JP225_M30_long": "🆕 JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 跨周期3/3✅",
        "JP225_M30_long_safe": "🆕 JP225 M30 CB>=3+RSI<20做多 WR=94.3% n=35 hold=135 跨周期3/3✅",
        "UKOIL_M30_long": "🆕 UKOIL M30 CB>=4+RSI<25做多 WR=96.9% n=32 hold=140 跨周期3/3✅ [推荐候补]",
        "UKOIL_M30_long_strong": "🆕 UKOIL M30 CB>=4+RSI<20做多 WR=100% n=23 hold=60 跨周期3/3✅",
        "USOIL_M30_inside_long": "🆕 USOIL M30 InsideBar+RSI<20做多 WR=100% n=15 hold=80",
        "XAUUSD_M30_Doji_short": "🆕 XAUUSD M30 Doji+RSI>75+us做空 WR=100% n=12 hold=35",
        "USOIL_M30_long": "USOIL M30 CB>=4+RSI<25做多 WR=79.5% n=39 hold=110 跨周期3/3✅",
        "US500_H1_long": "🆕 US500 H1 CB>=4+RSI<20做多 WR=100% n=11 hold=30 [数据不足,需补美盘]",
        "US30_H1_long": "🆕 US30 H1 CB>=4+RSI<20做多 WR=92.9% n=14 hold=70 跨周期3/3✅",
        "AUDUSD_US": "AUDUSD美盘RSI<16+CB>=3 hold=125 WR=77.8% n=45",
        "JP225_US": "JP225美盘RSI<14+CB>=2 hold=55 WR=73.4% n=64",
        "XAGUSD_US": "XAG美盘RSI<18+CB>=3 hold=105 WR=75.0% n=60",
        "XAGUSD_EU": "XAG欧盘RSI<14+CB>=3 hold=85 WR=86.5% n=37"
    },
    "warnings": [
        "🔴 H1数据最新停于13:00/M30停于13:30 UTC，美盘后半段数据缺失(US18+=M1/M5的1/30)",
        "🔴 US500 H1 P3无数据，跨周期统计不全(2/3)，需调整下载时间至18-20 UTC",
        "⚠️ M1/M5做空信号整体弱于做多，XAUUSD/XAGUSD/JP225/US500/US30做空均<60% WR",
        "⚠️ UKOIL/USOIL WR极高(95-100%)但n仅23-32，仍需更多数据",
        "⚠️ XAUUSD M30 Doji+RSI>75+us做空WR=100%但n=12无增长",
        "⚠️ US30 M5未发现任何WR>65%的可靠策略"
    ],
    "next_actions": [
        "round37_001: JP225 H1/M30做多正式纳入best_known+月度跟踪启动",
        "round37_002: UKOIL M30做多继续积累 n=32→目标50，考虑纳入候补",
        "round37_003: XAUUSD M1 EU CB>=3+RSI<10跨周期再确认(n=36)+纳入best_known",
        "round37_004: EURUSD H1做多月度跟踪(第5月)",
        "round37_005: XAGUSD M30 SHORT积累 n=28→目标50",
        "round37_006: 调整MT5下载时间至18-20 UTC 补全美盘数据后重测US500/US30 H1",
        "round37_007: XAGUSD M5/M1 EU做多策略验证(WR>74% n>40)",
        "round37_008: US500 M5 EU CB>=4+RSI<14做多验证 WR=78.1% n=73 → 跨周期检查"
    ]
}

with open('/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/state/research_state.json', 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("State updated successfully (current_round=36)")
