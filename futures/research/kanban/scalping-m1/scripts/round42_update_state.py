#!/usr/bin/env python3
"""Update research state after round42"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 42,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round42_001": "XAUUSD M1 US CB>=3+RSI<10(第4月) WR=87.0% n=46 hold=30 CI=[76.1%,95.7%] CP3/3; 月跟踪(第4月续跑) n=46 WR=87.0%, 2026-05 83.3%n=6; EU极值97.2%n=36 CP3/3→月度跟踪续跑稳定; ASIA新阈值CB>=2+RSI<10 WR=75.3% n=85 hold=10 CP3/3; ASIA CB>=3+RSI<10 WR=75.7% n=70 CP2/3。结论:US极值持续4月有效,ASIA盘75%+确认CP3/3",
        "round42_002": "XAGUSD M5 EU CB>=2+RSI<8 WR=96.4% n=28 hold=35 CI=[89.3%,100%] CP3/3(P1=92.3% P2=100% P3=100%); n=28仍无增长; 原策略CB>=3+RSI<10 WR=76.2% n=42 CP3/3; CB>=2+RSI<10 WR=79.2% n=48 CP3/3。结论:新阈值n=28未增长但CP3/3全通过，原策略稳定",
        "round42_003": "EURUSD H1月跟踪(第10月) CB>=3+RSI<20 WR=100% n=11 hold=60 CP3/3; CB>=3+RSI<25 WR=82.1% n=28 hold=60 CP3/3; 月跟踪第10月:n=24 WR=83.3%连续10月稳定; M30 CB>=4+RSI<20 WR=80.6% n=31 hold=70 CP3/3月跟踪启动(n=30 WR=76.7%)。结论:EURUSD H1连续10月有效为最长跟踪策略",
        "round42_004": "US500 M5 EU CB>=5+RSI<14 WR=84.6% n=52 hold=25 CP3/3稳定; 月跟踪(第2月续跑) n=52 WR=84.6%, 2026-04 71.4% 2026-05 100%n=1; CB>=4+RSI<14 WR=78.1% n=73 CP3/3。结论:CB>=5版本84.6%已确认，建议正式纳入",
        "round42_005": "XAGUSD M30 SHORT CBull>=4+RSI>85 WR=93.8% n=16 hold=40 CP3/3; US子策略WR=100% n=10 hold=35 avg=3.069% CP3/3; n=16连续5轮无增长; 新发现:CBull>=5+RSI>85 WR=92.3% n=13 hold=35。结论:做空信号稀有但WR极高，US子策略100%",
        "round42_006": "GBPUSD H1 US CB>=3+RSI<25 WR=100% n=12 hold=10; M30 US CB>=3+RSI<20 WR=87.5% n=16 hold=115; AUDUSD M30 CB>=3+RSI<18 WR=81.5% n=27 hold=60 CP3/3; AUDUSD M30 US子策略CB>=4+RSI<20 WR=100% n=7 hold=115。结论:GBPUSD H1 US持续100% n=12, AUDUSD M30 US有潜力",
        "round42_007": "USTEC M30 CB>=4+RSI<18 WR=92.0% n=25 hold=30 CP3/3; M30 CB>=4+RSI<20 WR=90.0% n=30 hold=35 CP3/3→月跟踪启动(n=30 WR=83.3%); H1 CB>=5+RSI<25 WR=100% n=10 hold=115; H1 CB>=4+RSI<25 WR=80.0% n=20 hold=105 CP3/3。结论:USTEC M30多策略CP3/3通过，月度跟踪启动",
        "round42_008": "JP225 H1/M30月跟踪(第6月) H1 CB>=4+RSI<25 WR=92.3% n=26 hold=40 CP3/3; H1 CB>=5+RSI<25 WR=100% n=16 hold=40; M30 CB>=4+RSI<20 WR=95.5% n=22 hold=135 CP3/3; M30 CB>=3+RSI<20 WR=94.3% n=35 hold=135 CP3/3; 月跟踪第6月稳定。结论:持续有效",
        "round42_009": "HK50 H1 CB>=3+RSI<18 WR=86.4% n=22 hold=100 CP3/3; H1 CB>=2+RSI<18 WR=84.4% n=32 hold=100 CP3/3; H1 CB>=4+RSI<20 WR=84.2% n=19 hold=25 CP3/3; USDCHF H1 CB>=3+RSI<18 WR=90.9% n=22 hold=65 CP3/3→月度跟踪启动; USDCHF US子策略CB>=3+RSI<20 WR=91.7% n=12。结论:HK50多种组合通过CP3/3,USDCHF H1 CP3/3确认月跟踪启动",
        "round42_010": "XAUUSD M1 EU极值CB>=3+RSI<10 WR=97.2% n=36 hold=55 CI=[91.7%,100%] CP3/3月跟踪续跑; AUDUSD M30 CP3/3候选CB>=3+RSI<18 WR=81.5% n=27 hold=60 CP3/3(P1=83.3% P2=87.5% P3=73.3%)确认通过评估。结论:EU极值持续97.2%, AUDUSD M30 CB>=3+RSI<18 CP3/3候选纳入",
        "round42_011": "H1/M30形态深度探索: XAUUSD H1 Doji+RSI>75做空WR=93.3% n=15 hold=60 avg=1.660%; XAUUSD M30 Doji+RSI>75做空WR=89.3% n=28 hold=35 avg=1.022%; UKOIL M30 Hammer+RSI<30做多WR=100% n=10 hold=95 avg=3.491%; JP225 H1 EngulfBull+RSI<30做多WR=100% n=8 hold=105 avg=2.509%; AUDUSD H1 ShootingStar+RSI>75做空WR=100% n=5 hold=40 avg=0.483%。结论:形态+RSI联合策略展现高潜力，需跨周期验证"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续8月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.3% n=122 [18月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [CP3/3 已确认纳入 月跟踪稳定]",
        "XAUUSD_M1_US_extreme": "XAUUSD M1 US CB>=2+RSI<10 WR=82.8% n=58 hold=30 [CP3/3 正式纳入]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=87.0% n=46 hold=30 [CP3/3 正式纳入+月跟踪第4月稳定]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=86.6% n=82 hold=55 [CP3/3]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=2+RSI<10 WR=75.3% n=85 hold=10 [新发现 CP3/3确认]",
        "USDJPY_H1_long": "USDJPY H1 CB>=5+RSI<25做多 WR=100% n=17 hold=190 [月跟踪100%]",
        "EURUSD_H1_long": "EURUSD H1 CB>=3+RSI<20做多 WR=100% n=11 hold=60 CI=[100%,100%] CP3/3",
        "EURUSD_H1_long_safe": "EURUSD H1 CB>=3+RSI<25做多 WR=82.1% n=28 hold=60 CI=[67.9%,96.4%] CP3/3 月跟踪10月稳定83.3%",
        "EURUSD_M30_long": "EURUSD M30 CB>=3+RSI<20做多 WR=76.9% n=39 hold=70 CI=[64.1%,89.7%] CP3/3",
        "EURUSD_M30_strong": "EURUSD M30 CB>=4+RSI<20做多 WR=80.6% n=31 hold=70 CP3/3 [月跟踪启动]",
        "XAGUSD_M30_SHORT": "XAGUSD M30 SHORT CBull>=4+RSI>80 WR=78.6% n=28 hold=100 CI=[64.3%,92.9%] CP3/3",
        "XAGUSD_M30_SHORT_strong": "XAGUSD M30 SHORT CBull>=4+RSI>85 WR=93.8% n=16 hold=40 avg=2.698% [严格阈值]",
        "XAGUSD_M30_SHORT_strong_us": "XAGUSD M30 SHORT CBull>=4+RSI>85+us WR=100% n=10 hold=35 avg=3.069% [US时段极强]",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 CP3/3 [新阈值]",
        "XAGUSD_M5_EU_wide": "XAGUSD M5 EU CB>=2+RSI<10做多 WR=79.2% n=48 hold=35 CP3/3",
        "JP225_H1_long": "JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 CP3/3 [正式纳入]",
        "JP225_H1_long_safe": "JP225 H1 CB>=4+RSI<25做多 WR=92.3% n=26 hold=40 CP3/3 [月跟踪第6月]",
        "JP225_M30_long": "JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 CP3/3 [正式纳入]",
        "JP225_M30_long_safe": "JP225 M30 CB>=3+RSI<20做多 WR=94.3% n=35 hold=135 CP3/3",
        "UKOIL_M30_long": "UKOIL M30 CB>=4+RSI<25做多 WR=96.9% n=32 hold=140 CP3/3 [信号稀有]",
        "UKOIL_M30_hammer": "UKOIL M30 Hammer+RSI<30做多 WR=100% n=10 hold=95 avg=3.491% [新形态发现]",
        "USOIL_M30_long": "USOIL M30 CB>=4+RSI<25做多 WR=79.5% n=39 hold=110 CP3/3",
        "XAUUSD_M30_Doji": "XAUUSD M30 Doji+RSI>75做空 WR=89.3% n=28 hold=35 avg=1.022% [新形态策略]",
        "XAUUSD_H1_Doji": "XAUUSD H1 Doji+RSI>75做空 WR=93.3% n=15 hold=60 avg=1.660% [新形态策略]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 [CP3/3 确认纳入+月跟踪]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=84.6% n=52 hold=25 [严格阈值确认, 建议正式纳入]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [CP2/3待确认]",
        "US30_M1_EU_H8": "US30 M1 EU hour=8 CB>=4+RSI<14 WR=100% n=17 hold=10 [时段子策略]",
        "US30_M1_EU_H9": "US30 M1 EU hour=9 CB>=4+RSI<14 WR=100% n=10 hold=5 [时段子策略]",
        "AUDUSD_M30_long": "AUDUSD M30 CB>=3+RSI<18做多 WR=81.5% n=27 hold=60 CP3/3 [新候选纳入]",
        "AUDUSD_M30_US": "AUDUSD M30 US CB>=4+RSI<20做多 WR=100% n=7 hold=115 [US子策略高胜率]",
        "GBPUSD_H1_US": "GBPUSD H1 US CB>=3+RSI<25做多 WR=100% n=12 hold=10",
        "GBPUSD_M30_US": "GBPUSD M30 US CB>=3+RSI<20做多 WR=87.5% n=16 hold=115",
        "USDCHF_H1_long": "USDCHF H1 CB>=3+RSI<18做多 WR=90.9% n=22 hold=65 CP3/3 [月度跟踪启动]",
        "USDCHF_H1_US": "USDCHF H1 US CB>=3+RSI<20做多 WR=91.7% n=12 hold=65 [US子策略]",
        "USTEC_H1_long": "USTEC H1 CB>=5+RSI<25做多 WR=100% n=10 hold=115 avg=2.138%",
        "USTEC_M30_long_strong": "USTEC M30 CB>=4+RSI<18做多 WR=92.0% n=25 hold=30 CP3/3 [正式纳入]",
        "USTEC_M30_long": "USTEC M30 CB>=4+RSI<20做多 WR=90.0% n=30 hold=35 CP3/3 [月跟踪启动]",
        "HK50_H1_long": "HK50 H1 CB>=3+RSI<18做多 WR=86.4% n=22 hold=100 CP3/3",
        "HK50_H1_long_safe": "HK50 H1 CB>=2+RSI<18做多 WR=84.4% n=32 hold=100 CP3/3",
        "HK50_M30_ShootingStar": "HK50 M30 ShootingStar+RSI>70做空 WR=93.3% n=15 hold=20 [新形态]"
    },
    "warnings": [
        "H1数据最新停于13:00/M30停于13:30 UTC，美盘后半段数据缺失(US18+=M1/M5的1/30)",
        "M1/M5做空信号整体弱于做多，XAUUSD/XAGUSD/JP225/US500/US30做空均<60% WR",
        "XAGUSD M30 SHORT CBull>=4+RSI>85 n=16连续5轮无增长(US子策略WR=100%但n=10)",
        "XAGUSD M5 EU CB>=2+RSI<8 n=28连续3轮无增长(目标40)，但CP3/3全通过",
        "UKOIL M30 n=32连续多轮无增长(数据覆盖限制，信号稀有)",
        "US30 M5仍未发现任何WR>65%的可靠策略",
        "US500 M1 EU跨周期P3普遍弱于P1/P2(33-43% WR)，M5优于M1",
        "USTEC H1跨周期P3无数据(数据范围限制)",
        "形态+RSI联合策略WR高但n普遍偏小(5-15)，需更多数据积累"
    ],
    "next_actions": [
        "round43_001: XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第5月)+ASIA新阈值CB>=2+RSI<10月跟踪启动",
        "round43_002: XAGUSD M5 EU 新阈值CB>=2+RSI<8 n=28->继续积累; CB>=2+RSI<10 CP3/3确认跟踪",
        "round43_003: EURUSD H1做多月度跟踪(第11月)+M30 CB>=4+RSI<20持续跟踪",
        "round43_004: US500 M5 EU CB>=5+RSI<14月度跟踪续跑(第3月)+正式纳入确认决定",
        "round43_005: XAGUSD M30 SHORT CBull>=4+RSI>85+us n=10->持续积累; 形态+RSI跨周期验证启动",
        "round43_006: GBPUSD H1 US CB>=3+RSI<25 积累验证(n->20)+AUDUSD M30 CB>=3+RSI<18纳入评估",
        "round43_007: USTEC M30/H1 月度跟踪续跑(第2月)+M30 CB>=4+RSI<18正式纳入",
        "round43_008: JP225 H1/M30做多月度跟踪(第7月)+M30 InsideBar+RSI<25跟踪续跑",
        "round43_009: HK50 H1做多积累验证+USDCHF H1月度跟踪续跑(第2月)",
        "round43_010: 形态+RSI联合策略跨周期验证 (Doji/Engulf/Hammer/ShootingStar)" 
    ]
}

with open(os.path.join(BASE, 'scripts', 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("State updated successfully (current_round=42)")
