#!/usr/bin/env python3
"""Update research state after round43 — M1/M5 Scalping Focused Scan"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 43,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round43_001": "XAUUSD M1 US CB>=3+RSI<10(第5月) WR=85.4% n=48 hold=30; 月跟踪续跑 WR稳住→2026-05数据仍有效; EU极值97.2% n=36稳定; 双极值联合85.7% n=84; ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 CP3/3确认。结论:US极值持续5月稳定,ASIA盘中度确认75%",
        "round43_002": "XAGUSD M5 EU新阈值CB>=2+RSI<8 WR=96.4% n=28 hold=35 n停滞; CB>=2+RSI<10 WR=79.2% n=48; 全品种M5网格扫描发现XAGUSD极端RSI<6全线>80% WR (CB>=1/2/3/4/5均>83% n=49-93)。结论:XAGUSD RSI<6+任意CB做多为近期最强新发现",
        "round43_003": "US500 M5 EU CB>=5+RSI<14 WR=84.6% n=52 hold=25月跟踪(第3月)稳定; CB>=4版本WR=78.1% n=73; US500 M5全品种扫描发现US500 CB>=5+RSI<6 WR=71.4% n=35 hold=5(信号稀有但可靠)。结论:US500 CB>=5版本正式纳入建议确认",
        "round43_004": "JP225 M5扫描: CB>=4/3+RSI<20 WR仅52.5-53.6%(hold=135)远低于H1/M30级别的WR>90%。结论:JP225 M5信号质量远不如H1/M30,建议维持H1/M30级别操作",
        "round43_005": "US30 M5探索: 所有CB+RSI组合WR均<53%,连续多轮无发现; M1 US30 EU CB>=4+RSI<14 WR=70.4% n=81 hold=30 CP2/3。结论:US30 M5无可靠策略,M1 EU有潜力但CP未全通过",
        "round43_006": "XAUUSD M1/M5做空全面探索: M1 US CBull>=4+RSI>85 WR=63.8% n=130 hold=10最佳但仍<65%; M5全部<55%。结论:做空信号整体弱于做多,暂不推荐",
        "round43_007": "XAUUSD时段细分-M1: 欧盘CB>=3+RSI<10 WR=97.2%n=36(最强),美盘CB>=4+RSI<10 WR=86.8%n=38(hold=30 Sharpe=76),亚洲CB>=3+RSI<10 WR=75.0%n=68(新)。结论:欧盘极值策略97.2%仍为全品种最强策略",
        "round43_008": "XAGUSD M5新发现: RSI<6+任意连阴组合WR>80%,其中CB>=1+RSI<6 WR=86.0% n=93 hold=55 avg=0.725% Sharpe=20.24。这是XAGUSD M5目前最高n>50的稳定策略。结论:XAGUSD M5 RSI<6连阴值得正式纳入候选",
        "round43_009": "US30 M1 EU CB>=4+RSI<14 WR=70.4% n=81 hold=30 avg=0.038% Sharpe=42.83; CP2/3未全通过但Sharpe极高; 时段子策略H8/H9 WR=100%但n小。结论:US30最佳策略仍在积累中",
        "round43_010": "做空扫描结论:所有5个目标品种M1/M5做空WR均<65%,M5做空全部<55%。做空信号在超短线框架下不可靠,建议继续聚焦做多"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续8月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.5% n=123 [18月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [CP3/3 全策略最强]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=85.4% n=48 hold=30 [第5月跟踪稳定]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=85.7% n=84 hold=55 [综合推荐]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 [新发现 CP3/3确认]",
        "XAUUSD_M5_SHORT_any": "XAUUSD M1/M5做空WR均<65%,不推荐",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 [新阈值n=28停滞]",
        "XAGUSD_M5_RSI6": "XAGUSD M5 CB>=1+RSI<6做多 WR=86.0% n=93 hold=55 [新发现-全品种最高n]",
        "XAGUSD_M5_RSI6_strict": "XAGUSD M5 CB>=5+RSI<6做多 WR=85.7% n=49 hold=55 [严格阈值]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 [CP3/3确认]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=84.6% n=52 hold=25 [正式纳入建议]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [CP2/3待确认]",
        "US30_M1_EU_H8": "US30 M1 EU hour=8 CB>=4+RSI<14 WR=100% n=17 hold=10 [时段子策略]",
        "JP225_H1_long": "JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 [H1远优于M5]",
        "JP225_M30_long": "JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 [M30远优于M5]",
        "AUDUSD_M30_long": "AUDUSD M30 CB>=3+RSI<18做多 WR=81.5% n=27 hold=60 CP3/3 [候选纳入]"
    },
    "warnings": [
        "M5数据覆盖较全至16:10 UTC，但H1/M30数据停于13:00/13:30 UTC影响验证",
        "XAGUSD M5 EU CB>=2+RSI<8 n=28连续多轮无增长(数据未更新)",
        "JP225 M5级别信号质量差(WR<55%)，远不如H1/M30 (WR>90%)",
        "US30 M5仍未发现任何WR>65%的可靠策略(连续多轮)",
        "做空信号在M1/M5全线<65% WR，不建议短线做空",
        "XAGUSD M5 RSI<6新发现n虽高(93)但RSI<6极端稀有，信号频率待评估",
        "US500 M5 EU策略需要监控跨周期稳定性(P1/P2/P3)"
    ],
    "next_actions": [
        "round44_001: XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第6月)+EU极值持续监控",
        "round44_002: XAGUSD M5 RSI<6新发现跨周期验证+频率统计(确认是否可实际应用)",
        "round44_003: XAGUSD M5 EU 继续积累CB>=2+RSI<8 n=28监测",
        "round44_004: US500 M5 EU CB>=5+RSI<14 月度跟踪续跑(第4月)+正式纳入",
        "round44_005: XAUUSD M1 ASIA CB>=3+RSI<10 跨周期验证(第2月)+n积累监控",
        "round44_006: US30 M1 EU 持续积累+检查CP3/3是否达成",
        "round44_007: M5全品种窄扫描: RSI<6/8/10 + 时段过滤 + 小时过滤",
        "round44_008: XAUUSD M5 美盘时段深度扫描(hour=15-21, CB+RSI精细网格)",
        "round44_009: 做空策略放弃评估 — 确认聚焦做多方向"
    ]
}

# Write to correct location
with open(os.path.join(BASE, 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

# Also write to scripts/state for compatibility
os.makedirs(os.path.join(BASE, 'scripts', 'state'), exist_ok=True)
with open(os.path.join(BASE, 'scripts', 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("State updated successfully (current_round=43)")
