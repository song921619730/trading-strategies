#!/usr/bin/env python3
"""Update research state after round44 — M1/M5 Scalping Monthly Tracking + RSI<6 Cross-Validation"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 44,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round44_001": "XAUUSD M1 US CB>=3+RSI<10第6月跟踪 WR=85.4% n=48 hold=30 连续6月稳定; EU极值97.2% n=36 hold=55 连续6月稳定; 双极值联合85.7% n=84; ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 第2月稳定; ASIA CB>=2+RSI<10 WR=73.8% n=80(新n增长)。结论:所有核心XAU M1策略持续稳定,第6月确认通过",
        "round44_002": "XAGUSD M5 RSI<6跨周期验证完成: 频率~6次/月(波动大,0-22次),亚洲46>美40>欧22; 欧盘RSI<6+任意CB WR=100% n=18(全胜但n小); 全球CB>=1+RSI<6 WR=86.0% n=93 hold=55确认; 欧盘RSI<8+CB>=1 WR=90.3% n=31 hold=30(更实用)。结论:XAGUSD RSI<6确认有效但信号稀有,建议以RSI<8替代提升信号频率",
        "round44_003": "XAGUSD M5 EU CB>=2+RSI<8 WR=96.4% n=28无增长停滞; CB>=2+RSI<10 WR=79.2% n=48稳定。结论:n=28阈值组合已停滞多轮,可能数据源无新信号,建议聚焦RSI<6/8替代方案",
        "round44_004": "US500 M5 EU CB>=5+RSI<14第4月跟踪 WR=84.6% n=52 hold=25稳定; CB>=4版本WR=78.1% n=73。结论:连续4月稳定,正式纳入建议确认通过",
        "round44_005": "XAUUSD M1 ASIA CB>=3+RSI<10第2月跟踪 WR=75.0% n=68 hold=10稳定; CB>=2+RSI<10 WR=73.8% n=80(新n增长)。结论:亚洲策略第2月通过验证,信号量充足(68-80次)",
        "round44_006": "US30 M1 EU CB>=4+RSI<14 WR=70.4% n=81 hold=30持续积累; CB>=3版本WR=65.1% n=109。结论:US30 M1最佳策略仍为CB>=4+RSI<14,WR稳定70%但Sharpe极好(42.83)",
        "round44_007": "M5全品种窄扫描新发现: XAUUSD美盘RSI<6+CB>=1 WR=89.3% n=28 hold=55; XAGUSD欧盘RSI<8+CB>=1 WR=90.3% n=31 hold=30(极强); XAGUSD欧盘RSI<8+CB>=4 WR=90.9% n=22。结论:XAUUSD美盘RSI<6+CB>=1为新发现,XAGUSD RSI<8系列为近期最强",
        "round44_008": "XAUUSD M5美盘深度扫描(h15-21): H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12; H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11; H20 CB>=5 RSI<14 WR=90.0% n=10; H15多策略85-90%区间。结论:美盘开盘15点及19-20点为XAU M5关键做多窗口",
        "round44_009": "做空确认扫描:全部5品种M1/M5做空WR<65%,最佳XAUUSD M1 CBull>=4+RSI>85 WR=58.0% n=429。结论:确认放弃做空方向合理,继续聚焦做多"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续8月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.5% n=123 [18月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [CP3/3 全策略最强 第6月]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=85.4% n=48 hold=30 [第6月跟踪稳定]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=85.7% n=84 hold=55 [综合推荐]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 [第2月确认稳定]",
        "XAUUSD_M1_ASIA_CB2": "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80 hold=10 [新n增长候选]",
        "XAUUSD_M5_US_RSI6": "XAUUSD M5 US RSI<6+CB>=1 WR=89.3% n=28 hold=55 [新发现-美盘极值]",
        "XAUUSD_M5_SHORT_any": "XAUUSD M1/M5做空WR均<65%,不推荐",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 [n=28停滞]",
        "XAGUSD_M5_RSI6": "XAGUSD M5 CB>=1+RSI<6做多 WR=86.0% n=93 hold=55 [确认有效-稀有信号]",
        "XAGUSD_M5_EU_RSI8": "XAGUSD M5 EU RSI<8+CB>=1做多 WR=90.3% n=31 hold=30 [新发现-欧盘RSI<8极强]",
        "XAGUSD_M5_EU_RSI8_CB4": "XAGUSD M5 EU RSI<8+CB>=4做多 WR=90.9% n=22 hold=30 [新发现-严格阈值]",
        "XAGUSD_M5_RSI6_strict": "XAGUSD M5 CB>=5+RSI<6做多 WR=85.7% n=49 hold=55 [严格阈值]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 [CP3/3确认]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=84.6% n=52 hold=25 [第4月稳定-正式纳入]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [Sharpe=42.83]",
        "US30_M1_EU_H8": "US30 M1 EU hour=8 CB>=4+RSI<14 WR=100% n=17 hold=10 [时段子策略]",
        "JP225_H1_long": "JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 [H1远优于M5]",
        "JP225_M30_long": "JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 [M30远优于M5]",
        "AUDUSD_M30_long": "AUDUSD M30 CB>=3+RSI<18做多 WR=81.5% n=27 hold=60 CP3/3 [候选纳入]",
        "XAU_M5_H15_doublegun2": "XAU M5 H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12 [美盘开盘精确定时]",
        "XAU_M5_H19_doublegun": "XAU M5 H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11 [美盘盘中精确定时]"
    },
    "warnings": [
        "M5数据覆盖较全至16:10 UTC，但H1/M30数据停于13:00/13:30 UTC影响验证",
        "XAGUSD M5 EU CB>=2+RSI<8 n=28连续多轮无增长(数据未更新-可能已无新信号)",
        "JP225 M5级别信号质量差(WR<55%)，远不如H1/M30 (WR>90%)",
        "US30 M5仍未发现任何WR>65%的可靠策略(连续多轮)",
        "做空信号在M1/M5全线<65% WR，不推荐短线做空",
        "XAGUSD M5 RSI<6信号稀有(~6次/月,波动0-22次),建议优先使用RSI<8提升频率",
        "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80但hold=10较短,需监控大hold表现"
    ],
    "next_actions": [
        "round45_001: XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第7月)+EU极值继续监控",
        "round45_002: XAUUSD M5 US RSI<6+CB>=1 新发现跨周期验证(第1月)+n积累",
        "round45_003: XAGUSD M5 EU RSI<8+CB>=1 新发现跨周期验证+频率对比(RSI<6 vs RSI<8)",
        "round45_004: US500 M5 EU CB>=5+RSI<14 月度跟踪续跑(第5月)+正式纳入确认",
        "round45_005: XAUUSD M1 ASIA CB>=3+RSI<10 跨周期验证(第3月)+CB>=2版本对比",
        "round45_006: US30 M1 EU 持续积累+检查CP3/3是否达成",
        "round45_007: XAUUSD M5 美盘H15/H19精确定时策略跨周期验证",
        "round45_008: XAGUSD M5 RSI<8 欧盘全CB扫描(确定最佳CB阈值)",
        "round45_009: 做空策略放弃确认 — 关闭做空分支"
    ]
}

# Write to correct location
with open(os.path.join(BASE, 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

# Also write to scripts/state for compatibility
os.makedirs(os.path.join(BASE, 'scripts', 'state'), exist_ok=True)
with open(os.path.join(BASE, 'scripts', 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("State updated successfully (current_round=44)")
