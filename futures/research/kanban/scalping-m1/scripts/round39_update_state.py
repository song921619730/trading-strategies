#!/usr/bin/env python3
"""Update research state after round39"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 39,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round39_001": "XAUUSD M1 US CB>=3+RSI<10正式纳入+月度跟踪启动 — WR=87.0% n=46 hold=30 CI=[76.1%,95.7%] 跨周期3/3✅(P1=100% P2=72.7% P3=86.4%); 月度跟踪(2026-02至05): WR=87.0% n=46(02:100% 03:75% 04:88.2% 05:83.3%)。结论:🏆 正式纳入best_known，4/4月稳定",
        "round39_002": "XAGUSD M5 EU CB>=3+RSI<10积累 n=42→目标60 — WR=76.2% n=42 hold=35 CI=[61.9%,88.1%] 跨周期3/3✅; n=42无增长(与R38相同)。结论:⏳ n=42持续无增长，需等待更多数据",
        "round39_003": "UKOIL M30做多 n=32→50继续积累 — CB>=4+RSI<25 WR=96.9% n=32 hold=140 跨周期3/3✅; CB>=4+RSI<20 WR=100% n=23 hold=60 跨周期3/3✅; 数据覆盖:3380行,2026-01至05。结论:⏳ n=32无增长(信号稀有)，UKOIL建议降级为已确认候补",
        "round39_004": "EURUSD H1做多月度跟踪第7月 — CB>=3+RSI<20 WR=100% n=11 hold=60 跨周期3/3✅; CB>=3+RSI<25 WR=82.1% n=28 月度跟踪(第7月): 2026-02/03/04/05总计n=24 WR=83.3%。结论:✅ 连续7月有效，WR稳定83.3%",
        "round39_005": "US500 M5 EU CB>=4+RSI<14月度跟踪启动 — WR=78.1% n=73 hold=25 CI=[68.5%,87.7%] 跨周期3/3✅(P1=77.8% P2=66.7% P3=88.0%); 月度跟踪(首月): n=73 WR=78.1%(2025-11月WR=42.9%❌但整体稳定)。结论:🏆 确认纳入候补，月度跟踪启动",
        "round39_006": "XAGUSD M30 SHORT CBull>=4+RSI>85积累验证 n=16→30 — WR=93.8% n=16 hold=40 CI=[81.2%,100%] 跨周期3/3✅; n=16无增长; 新发现: US时段CBull>=4+RSI>85+us WR=100% n=10 hold=35 avg=3.069%🔥。结论:🧪 n=16连续2轮无增长，US子策略极强",
        "round39_007": "US30 M1 EU时段子策略验证(hour=8/9) — 核心CB>=4+RSI<14 WR=70.4% n=81 hold=30 跨周期2/3⚠️(P2=59.1%); hour=8 WR=100% n=17 hold=10✅; hour=9 WR=100% n=10 hold=5✅; 新发现:hour=10 WR=81.8% n=11 hold=5✅; CB>=3+RSI<14跨周期3/3✅WR=65.1% n=109。结论:🧪 时段子策略稳定，CB>=3作为替代方案跨周期完整通过",
        "round39_008": "JP225 H1/M30月度跟踪第3月 — H1 CB>=4+RSI<25 WR=92.3% n=26 hold=40 跨周期3/3✅; M30 CB>=4+RSI<20 WR=95.5% n=22 hold=135 跨周期3/3✅; 月度跟踪: n=25 WR=92.0%连续稳定(02:100% 03:89.5% 04:100%)。结论:✅ 持续有效",
        "round39_009": "XAUUSD M1 US+EU双极值策略监控 — EU极值CB>=3+RSI<10 WR=97.2% n=36 hold=55 CI=[91.7%,100%] 跨周期3/3✅; US极值CB>=3+RSI<10 WR=87.0% n=46 hold=30 跨周期3/3✅; 双极值联合CB>=3+RSI<10(EU+US) WR=86.6% n=82 hold=55。结论:✅ 双极值均稳定，联合信号n=82有统计学意义"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月度跟踪: 连续8月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.3% n=122 [18月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘→XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "🏆 XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [跨周期3/3✅ 已确认纳入]",
        "XAUUSD_M1_US_extreme": "🏆 XAUUSD M1 US CB>=2+RSI<10 WR=82.8% n=58 hold=30 [跨周期3/3✅ 正式纳入]",
        "XAUUSD_M1_US_strong": "🏆 XAUUSD M1 US CB>=3+RSI<10 WR=87.0% n=46 hold=30 [跨周期3/3✅ 正式纳入+月度跟踪4/4月稳定🔥]",
        "USDJPY_H1_long": "✅ USDJPY H1 CB>=5+RSI<25做多 WR=100% n=17 hold=190 [月度跟踪100%✅]",
        "EURUSD_H1_long": "✅ EURUSD H1 CB>=3+RSI<20做多 WR=100% n=11 hold=60 CI=[100%,100%] 跨周期3/3✅",
        "EURUSD_H1_long_safe": "✅ EURUSD H1 CB>=3+RSI<25做多 WR=82.1% n=28 hold=60 CI=[67.9%,96.4%] 跨周期3/3✅ 月度跟踪7月稳定83.3%",
        "EURUSD_M30_long": "✅ EURUSD M30 CB>=3+RSI<20做多 WR=76.9% n=39 hold=70 CI=[64.1%,89.7%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT": "✅ XAGUSD M30 SHORT CBull>=4+RSI>80 WR=78.6% n=28 hold=100 CI=[64.3%,92.9%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT_us": "XAGUSD M30 SHORT CBull>=4+RSI>80+us WR=85.7% n=14 hold=35",
        "XAGUSD_M30_SHORT_strong": "🆕 XAGUSD M30 SHORT CBull>=4+RSI>85 WR=93.8% n=16 hold=40 avg=2.698% [新严格阈值]",
        "XAGUSD_M30_SHORT_strong_us": "🆕 XAGUSD M30 SHORT CBull>=4+RSI>85+us WR=100% n=10 hold=35 avg=3.069% [US时段极强🔥]",
        "XAGUSD_M5_EU_long": "🆕 XAGUSD M5 EU CB>=3+RSI<10 WR=76.2% n=42 跨周期3/3✅ [推荐候补]",
        "XAGUSD_M5_EU_long_safe": "🆕 XAGUSD M5 EU CB>=4+RSI<14 WR=74.3% n=70 跨周期3/3✅",
        "JP225_H1_long": "✅ JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 跨周期3/3✅ [正式纳入]",
        "JP225_H1_long_safe": "✅ JP225 H1 CB>=4+RSI<25做多 WR=92.3% n=26 hold=40 跨周期3/3✅",
        "JP225_M30_long": "✅ JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 跨周期3/3✅ [正式纳入]",
        "JP225_M30_long_safe": "✅ JP225 M30 CB>=3+RSI<20做多 WR=94.3% n=35 hold=135 跨周期3/3✅",
        "UKOIL_M30_long": "✅ UKOIL M30 CB>=4+RSI<25做多 WR=96.9% n=32 hold=140 跨周期3/3✅ [推荐候补，信号稀有]",
        "UKOIL_M30_long_strong": "✅ UKOIL M30 CB>=4+RSI<20做多 WR=100% n=23 hold=60 跨周期3/3✅",
        "USOIL_M30_inside_long": "🆕 USOIL M30 InsideBar+RSI<20做多 WR=100% n=15 hold=80",
        "USOIL_M30_long": "USOIL M30 CB>=4+RSI<25做多 WR=79.5% n=39 hold=110 跨周期3/3✅ [n=40目标达标]",
        "XAUUSD_M30_Doji_short": "🧪 XAUUSD M30 Doji+RSI>75+us做空 WR=100% n=12 hold=35 [n=12无增长]",
        "US500_M5_EU_long": "🏆 US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 [跨周期3/3✅ P3=88.0%🔥确认纳入+月度跟踪启动]",
        "US500_H1_long": "🧪 US500 H1 CB>=4+RSI<20做多 WR=100% n=11 hold=30 [数据不足]",
        "US30_H1_long": "✅ US30 H1 CB>=4+RSI<20做多 WR=92.9% n=14 hold=70 跨周期3/3✅",
        "US30_M1_EU_long": "🆕 US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [跨周期2/3⚠️待确认]",
        "US30_M1_EU_H8": "🆕 US30 M1 EU hour=8 CB>=4+RSI<14 WR=100% n=17 hold=10 [时段子策略]",
        "US30_M1_EU_H9": "🆕 US30 M1 EU hour=9 CB>=4+RSI<14 WR=100% n=10 hold=5 [时段子策略]",
        "US30_M1_EU_H10": "🆕 US30 M1 EU hour=10 CB>=4+RSI<14 WR=81.8% n=11 hold=5 [时段子策略-新增]",
        "US30_M1_EU_alt": "🆕 US30 M1 EU CB>=3+RSI<14 WR=65.1% n=109 hold=10 [跨周期3/3✅替代方案]",
        "AUDUSD_US": "AUDUSD美盘RSI<16+CB>=3 hold=125 WR=77.8% n=45",
        "JP225_US": "JP225美盘RSI<14+CB>=2 hold=55 WR=73.4% n=64",
        "XAGUSD_US": "XAG美盘RSI<18+CB>=3 hold=105 WR=75.0% n=60",
        "XAGUSD_EU": "XAG欧盘RSI<14+CB>=3 hold=85 WR=86.5% n=37"
    },
    "warnings": [
        "🔴 H1数据最新停于13:00/M30停于13:30 UTC，美盘后半段数据缺失(US18+=M1/M5的1/30)",
        "🔴 US500 H1 P3无数据，跨周期统计不全(2/3)",
        "⚠️ M1/M5做空信号整体弱于做多，XAUUSD/XAGUSD/JP225/US500/US30做空均<60% WR",
        "⚠️ US30 M5未发现任何WR>65%的可靠策略(M1 EU勉强达到70%)",
        "⚠️ XAUUSD M30 Doji+RSI>75+us做空WR=100%但n=12无增长(连续5轮无新增)",
        "⚠️ UKOIL M30 n=32连续多轮无增长(数据覆盖限制，CB>=4+RSI<25信号稀有)",
        "⚠️ XAGUSD M30 SHORT CBull>=4+RSI>85 n=16连续2轮无增长",
        "⚠️ XAGUSD M5 EU CB>=3+RSI<10 n=42连续2轮无增长(目标60)",
        "⚠️ US30 M1 EU CB>=4+RSI<14跨周期2/3(P2=59.1%略低于60%)"
    ],
    "next_actions": [
        "round40_001: XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第2月)+双极值联合监控",
        "round40_002: XAGUSD M5 EU CB>=3+RSI<10 n=42→目标60持续监控(n无增长是否可调整阈值?)",
        "round40_003: EURUSD H1做多月度跟踪(第8月)",
        "round40_004: US500 M5 EU CB>=4+RSI<14 月度跟踪续跑(第2月)",
        "round40_005: XAGUSD M30 SHORT CBull>=4+RSI>85+us WR=100% n=10 → 积累验证(n→20)",
        "round40_006: US30 M1 EU 时段子策略(H8/H9/H10)重验证+CB>=3+RSI<14替代方案确认",
        "round40_007: JP225 H1/M30做多月度跟踪(第4月)",
        "round40_008: XAUUSD M1 EU极值月度跟踪续跑+US极值月度跟踪(第2月)",
        "round40_009: UKOIL M30做多n=32数据覆盖深度检查(是否可扩展至M5/M15寻找更多信号?)"
    ]
}

with open(os.path.join(BASE, 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("✅ State updated successfully (current_round=39)")
