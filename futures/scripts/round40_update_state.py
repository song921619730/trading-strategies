#!/usr/bin/env python3
"""Update research state after round40"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 40,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round40_001": "XAUUSD M1 US CB>=3+RSI<10月度跟踪续跑(第2月) — WR=87.0% n=46 hold=30 CI=[76.1%,95.7%] 跨周期3/3✅(P1=100% P2=72.7% P3=86.4%); 月度跟踪(第2月): n=46 WR=87.0%(02:100% 03:75% 04:88.2% 05:83.3%)与R39相同(无新增信号); 双极值联合WR=86.6% n=82 hold=55。结论:🏆 持续稳定，信号频率稳定(无新增信号反映M1 US极值稀有度)",
        "round40_002": "XAGUSD M5 EU CB>=3+RSI<10 n=42→目标60 — WR=76.2% n=42 hold=35 CI=[61.9%,88.1%] 跨周期3/3✅; n=42仍无增长; 新发现:CB>=2+RSI<8 WR=96.4% n=28 hold=35 avg=0.705%🔥(n增长28). 结论:⏳ 原策略n=42停滞，新阈值CB>=2+RSI<8有潜力(n=28 WR=96.4%)",
        "round40_003": "EURUSD H1做多月度跟踪(第8月) — CB>=3+RSI<20 WR=100% n=11 hold=60 跨周期3/3✅; CB>=3+RSI<25 WR=82.1% n=28 月度跟踪(第8月): n=24 WR=83.3%连续8月稳定✅; 新EURUSD M30 CB>=3+RSI<20 WR=76.9% n=39 hold=70。结论:✅ 持续有效，EURUSD H1为最佳连续跟踪策略",
        "round40_004": "US500 M5 EU CB>=4+RSI<14月度跟踪续跑(第2月) — WR=78.1% n=73 hold=25 跨周期3/3✅; 月度跟踪: n=73 WR=78.1%稳定; 新发现:CB>=5+RSI<14 WR=84.6% n=52 hold=25🔥(更严格阈值WR更高). 结论:🏆 CB>=5版本WR提升至84.6% n=52，推荐升级",
        "round40_005": "XAGUSD M30 SHORT CBull>=4+RSI>85+us n→20 — WR=93.8% n=16 hold=40 跨周期3/3✅; US子策略WR=100% n=10 hold=35 avg=3.069%🔥; n=16无增长. 结论:🧪 n=16连续3轮无增长，但US子策略持续WR=100%",
        "round40_006": "US30 M1 EU时段子策略(H8/H9/H10)重验证 — H8 WR=100% n=17 hold=10✅; H9 WR=100% n=10 hold=5✅; H10 WR=81.8% n=11 hold=5✅; CB>=3+RSI<14替代方案WR=65.1% n=109 hold=10 跨周期3/3✅。结论:🧪 时段子策略全部维持，替代方案跨周期确认",
        "round40_007": "JP225 H1/M30做多月度跟踪(第4月) — H1 CB>=4+RSI<25 WR=92.3% n=26 hold=40 跨周期3/3✅; M30 CB>=4+RSI<20 WR=95.5% n=22 hold=135 跨周期3/3✅; 月度跟踪第4月: n=25 WR=92.0%稳定。结论:✅ 持续有效",
        "round40_008": "XAUUSD M1 EU极值+US极值月度跟踪 — EU极值CB>=3+RSI<10 WR=97.2% n=36 hold=55 CI=[91.7%,100%] 跨周期3/3✅; US极值CB>=3+RSI<10 WR=87.0% n=46 hold=30; 双极值联合WR=86.6% n=82。结论:✅ 双极值持续稳定，联合82信号有统计意义",
        "round40_009": "UKOIL M30做多n=32数据覆盖深度检查 — CB>=4+RSI<25 WR=96.9% n=32 hold=140; M5扩展: M5数据存在但CB>=4+RSI<20仅n=10 WR=70%一般; 信号稀有度确认。结论:⏳ UKOIL信号确实稀有，M5扩展未带来显著改善",
        "round40_010": "GBPUSD H1/M30做多策略探索🥇 — H1 US CB>=3+RSI<25 WR=100% n=12 hold=10🔥; H1 EU CB>=3+RSI<20 WR=100% n=5 hold=70; M30 US CB>=3+RSI<20 WR=87.5% n=16 hold=115。结论:🏆 GBPUSD H1 US CB>=3+RSI<25值得跟踪!",
        "round40_011": "HK50 H1/M30做多策略探索 — H1 CB>=3+RSI<18 WR=86.4% n=22 hold=100; H1 CB>=4+RSI<20 WR=84.2% n=19; ASIA CB>=3+RSI<25 WR=84.6% n=13。结论:🧪 HK50 H1策略WR>80%有潜力，但n<30",
        "round40_012": "USTEC H1/M30做多策略探索🥇 — H1 CB>=5+RSI<25 WR=100% n=10 hold=115 avg=2.138%🔥; M30 CB>=4+RSI<18 WR=92.0% n=25 hold=30; M30 CB>=4+RSI<20 WR=90.0% n=30。结论:🏆 USTEC M30/H1多策略WR>90%，强烈推荐继续研究",
        "round40_013": "XAUUSD M5 US做空探索 — CBull>=3+RSI>75+us/US做空: CBull>=4+RSI>80+us WR=56.2% n=16❌; 所有做空阈值均<65% WR。结论:❌ XAUUSD M5做空信号不如做多，不建议单独使用"
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
        "EURUSD_H1_long_safe": "✅ EURUSD H1 CB>=3+RSI<25做多 WR=82.1% n=28 hold=60 CI=[67.9%,96.4%] 跨周期3/3✅ 月度跟踪8月稳定83.3%",
        "EURUSD_M30_long": "✅ EURUSD M30 CB>=3+RSI<20做多 WR=76.9% n=39 hold=70 CI=[64.1%,89.7%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT": "✅ XAGUSD M30 SHORT CBull>=4+RSI>80 WR=78.6% n=28 hold=100 CI=[64.3%,92.9%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT_us": "XAGUSD M30 SHORT CBull>=4+RSI>80+us WR=85.7% n=14 hold=35",
        "XAGUSD_M30_SHORT_strong": "🆕 XAGUSD M30 SHORT CBull>=4+RSI>85 WR=93.8% n=16 hold=40 avg=2.698% [新严格阈值]",
        "XAGUSD_M30_SHORT_strong_us": "🆕 XAGUSD M30 SHORT CBull>=4+RSI>85+us WR=100% n=10 hold=35 avg=3.069% [US时段极强🔥]",
        "XAGUSD_M5_EU_long": "🆕 XAGUSD M5 EU CB>=3+RSI<10 WR=76.2% n=42 跨周期3/3✅ [推荐候补]",
        "XAGUSD_M5_EU_long_safe": "🆕 XAGUSD M5 EU CB>=4+RSI<14 WR=74.3% n=70 跨周期3/3✅",
        "XAGUSD_M5_EU_new": "🆕 XAGUSD M5 EU CB>=2+RSI<8 WR=96.4% n=28 hold=35🔥 [新阈值，信号更多]",
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
        "US500_M5_EU_strong": "🆕 US500 M5 EU CB>=5+RSI<14做多 WR=84.6% n=52 hold=25🔥 [更严格阈值推荐]",
        "US500_H1_long": "🧪 US500 H1 CB>=4+RSI<20做多 WR=100% n=11 hold=30 [数据不足]",
        "US30_H1_long": "✅ US30 H1 CB>=4+RSI<20做多 WR=92.9% n=14 hold=70 跨周期3/3✅",
        "US30_M1_EU_long": "🆕 US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [跨周期2/3⚠️待确认]",
        "US30_M1_EU_H8": "🆕 US30 M1 EU hour=8 CB>=4+RSI<14 WR=100% n=17 hold=10 [时段子策略]",
        "US30_M1_EU_H9": "🆕 US30 M1 EU hour=9 CB>=4+RSI<14 WR=100% n=10 hold=5 [时段子策略]",
        "US30_M1_EU_H10": "🆕 US30 M1 EU hour=10 CB>=4+RSI<14 WR=81.8% n=11 hold=5 [时段子策略]",
        "US30_M1_EU_alt": "🆕 US30 M1 EU CB>=3+RSI<14 WR=65.1% n=109 hold=10 [跨周期3/3✅替代方案]",
        "AUDUSD_US": "AUDUSD美盘RSI<16+CB>=3 hold=125 WR=77.8% n=45",
        "JP225_US": "JP225美盘RSI<14+CB>=2 hold=55 WR=73.4% n=64",
        "XAGUSD_US": "XAG美盘RSI<18+CB>=3 hold=105 WR=75.0% n=60",
        "XAGUSD_EU": "XAG欧盘RSI<14+CB>=3 hold=85 WR=86.5% n=37",
        "GBPUSD_H1_US": "🆕 GBPUSD H1 US CB>=3+RSI<25做多 WR=100% n=12 hold=10🔥 [新发现]",
        "GBPUSD_H1_EU": "🆕 GBPUSD H1 EU CB>=3+RSI<20做多 WR=100% n=5 hold=70 [n不足但WR=100%]",
        "GBPUSD_M30_US": "🆕 GBPUSD M30 US CB>=3+RSI<20做多 WR=87.5% n=16 hold=115",
        "USTEC_H1_long": "🆕 USTEC H1 CB>=5+RSI<25做多 WR=100% n=10 hold=115 avg=2.138%🔥 [新发现]",
        "USTEC_M30_long": "🆕 USTEC M30 CB>=4+RSI<18做多 WR=92.0% n=25 hold=30🔥 [新发现]",
        "USTEC_M30_long_safe": "🆕 USTEC M30 CB>=4+RSI<20做多 WR=90.0% n=30 hold=35🔥 [新发现]",
        "HK50_H1_long": "🆕 HK50 H1 CB>=3+RSI<18做多 WR=86.4% n=22 hold=100 [新发现]",
        "USDCHF_H1_long": "🆕 USDCHF H1 CB>=3+RSI<18做多 WR=90.9% n=22 hold=65 [新发现]"
    },
    "warnings": [
        "🔴 H1数据最新停于13:00/M30停于13:30 UTC，美盘后半段数据缺失(US18+=M1/M5的1/30)",
        "🔴 US500 H1 P3无数据，跨周期统计不全(2/3)",
        "⚠️ M1/M5做空信号整体弱于做多，XAUUSD/XAGUSD/JP225/US500/US30做空均<60% WR",
        "⚠️ US30 M5未发现任何WR>65%的可靠策略(M1 EU勉强达到70%)",
        "⚠️ XAUUSD M30 Doji+RSI>75+us做空WR=100%但n=12无增长(连续6轮无新增)",
        "⚠️ UKOIL M30 n=32连续多轮无增长(数据覆盖限制，信号稀有)",
        "⚠️ XAGUSD M30 SHORT CBull>=4+RSI>85 n=16连续3轮无增长",
        "⚠️ XAGUSD M5 EU CB>=3+RSI<10 n=42连续3轮无增长(目标60)，但新阈值CB>=2+RSI<8有潜力",
        "⚠️ US30 M1 EU CB>=4+RSI<14跨周期2/3(P2=59.1%略低于60%)"
    ],
    "next_actions": [
        "round41_001: XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第3月)+双极值联合监控持续",
        "round41_002: XAGUSD M5 EU 新阈值CB>=2+RSI<8 WR=96.4% n=28 → 积累验证(n→40)+跨周期验证",
        "round41_003: EURUSD H1做多月度跟踪(第9月)",
        "round41_004: US500 M5 EU CB>=5+RSI<14 WR=84.6% n=52 → 新严格阈值确认+月度跟踪启动",
        "round41_005: XAGUSD M30 SHORT CBull>=4+RSI>85+us WR=100% n=10 → 持续积累(n→20)",
        "round41_006: GBPUSD H1 US CB>=3+RSI<25 WR=100% n=12 → 积累验证(n→20)+跨周期验证",
        "round41_007: USTEC M30 H1做多策略深度验证 → M30 CB>=4+RSI<18 WR=92.0% n=25 + H1 CB>=5+RSI<25 WR=100% n=10",
        "round41_008: JP225 H1/M30做多月度跟踪(第5月)",
        "round41_009: HK50 H1/M30做多积累验证+USDCHF H1跟踪",
        "round41_010: XAUUSD M1双极值月度跟踪续跑"
    ]
}

with open(os.path.join(BASE, 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("✅ State updated successfully (current_round=40)")
