#!/usr/bin/env python3
"""Update research state after round45 — M1/M5 Scalping Monthly Tracking + New Discovery Cross-Validation"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 45,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round45_001": "XAUUSD M1 US CB>=3+RSI<10第7月跟踪 WR=85.4% n=48 hold=30 连续7月稳定; EU极值97.2% n=36 hold=55 连续7月稳定; 双极值联合85.7% n=84; ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 第3月稳定; ASIA CB>=2+RSI<10 WR=73.8% n=80稳定。结论:所有核心XAU M1策略继续稳定,第7月确认通过",
        "round45_002": "XAUUSD M5 US RSI<6+CB>=1第1月跨周期验证 WR=89.3% n=28 hold=55 与round44数据一致; CB>=2版本WR=87.0% n=23。结论:美盘RSI<6策略第1月通过,信号量适中(28次信号),可继续跟踪",
        "round45_003": "XAGUSD M5 EU RSI<8+CB>=1第1月跨周期验证 WR=90.3% n=31 hold=30 确认有效; RSI<8频率1.8x RSI<6(191 vs 108); 欧盘CB>=5 WR=94.7% n=19(稀有); CB>=4 WR=90.9% n=22。结论:RSI<8系列策略跨周期验证通过,推荐以RSI<8+CB>=1为主要入口",
        "round45_004": "US500 M5 EU CB>=5+RSI<14第5月跟踪 WR=84.6% n=52 hold=25 连续5月稳定; CB>=4版本78.1% n=73。结论:连续5月稳定,正式纳入确认通过",
        "round45_005": "XAUUSD M1 ASIA CB>=3+RSI<10第3月跟踪 WR=75.0% n=68 hold=10 稳定; CB>=2+RSI<10 WR=73.8% n=80持续增长。结论:亚洲策略第3月通过验证,信号量充足",
        "round45_006": "US30 M1 EU CB>=4+RSI<14 WR=70.4% n=81 hold=30 CP3/3检查通过; CB>=3版本65.1% n=109。结论:WR稳定70%,Sharpe=42.83良好,继续积累",
        "round45_007": "XAUUSD M5美盘精确定时跨周期验证: H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12; H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11; H19 CB>=5 RSI<12 hold=55 WR=100% n=8(全胜但n小)。结论:精确定时策略跨周期验证通过,信号稀有但质量极高",
        "round45_008": "XAGUSD M5 RSI<8欧盘全CB扫描完成: 最佳综合RSI<8+CB>=1 WR=90.3% n=31 hold=30; 严格版RSI<8+CB>=4 WR=90.9% n=22; 极严格RSI<8+CB>=5 WR=94.7% n=19。结论:推荐RSI<8+CB>=1为主要(31次),CB>=4为备用(22次)",
        "round45_009": "做空策略放弃最终确认:最佳WR=58.8%(XAGUSD M1 CBull>=5 RSI>90 hold=10)，全线<65%。结论:做空分支正式关闭,以后不再扫描做空方向"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续9月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.5% n=123 [19月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [CP7/7 全策略最强王者 第7月]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=85.4% n=48 hold=30 [第7月跟踪稳定]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=85.7% n=84 hold=55 [综合推荐]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 [第3月确认稳定]",
        "XAUUSD_M1_ASIA_CB2": "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80 hold=10 [n增长稳定]",
        "XAUUSD_M5_US_RSI6": "XAUUSD M5 US RSI<6+CB>=1 WR=89.3% n=28 hold=55 [第1月跨周期验证通过]",
        "XAUUSD_M5_US_RSI6_CB2": "XAUUSD M5 US RSI<6+CB>=2 WR=87.0% n=23 hold=30 [备用阈值]",
        "XAUUSD_M5_SHORT_any": "XAUUSD M1/M5做空WR均<65%,不推荐 [做空分支已正式关闭]",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 [n=28停滞-数据未更新]",
        "XAGUSD_M5_RSI6": "XAGUSD M5 CB>=1+RSI<6做多 WR=86.0% n=93 hold=55 [确认有效-信号稀有~6次/月]",
        "XAGUSD_M5_EU_RSI8": "XAGUSD M5 EU RSI<8+CB>=1做多 WR=90.3% n=31 hold=30 [最佳综合入口~11次/月]",
        "XAGUSD_M5_EU_RSI8_CB4": "XAGUSD M5 EU RSI<8+CB>=4做多 WR=90.9% n=22 hold=30 [严格阈值备用]",
        "XAGUSD_M5_RSI6_strict": "XAGUSD M5 CB>=5+RSI<6做多 WR=85.7% n=49 hold=55 [严格阈值]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 [CP3/3确认]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=84.6% n=52 hold=25 [第5月稳定-正式纳入]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [CP3/3达标 Sharpe=42.83]",
        "US30_M1_EU_H8": "US30 M1 EU hour=8 CB>=4+RSI<14 WR=100% n=17 hold=10 [时段子策略]",
        "JP225_H1_long": "JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 [H1远优于M5]",
        "JP225_M30_long": "JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 [M30远优于M5]",
        "AUDUSD_M30_long": "AUDUSD M30 CB>=3+RSI<18做多 WR=81.5% n=27 hold=60 CP3/3 [候选纳入]",
        "XAU_M5_H15_doublegun2": "XAU M5 H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12 [美盘开盘精确定时-跨周期验证通过]",
        "XAU_M5_H19_doublegun": "XAU M5 H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11 [美盘盘中精确定时-跨周期验证通过]",
        "XAU_M5_H19_strict": "XAU M5 H19 CB>=5 RSI<12 hold=55 WR=100% n=8 [H19极严格-全胜但n小]"
    },
    "warnings": [
        "M5数据覆盖较全至16:10 UTC，但H1/M30数据停于13:00/13:30 UTC影响验证",
        "XAGUSD M5 EU CB>=2+RSI<8 n=28连续多轮无增长(数据未更新-可能已无新信号)",
        "JP225 M5级别信号质量差(WR<55%)，远不如H1/M30 (WR>90%)",
        "US30 M5仍未发现任何WR>65%的可靠策略(连续多轮)",
        "做空信号在M1/M5全线<65% WR，做空分支已正式关闭(不再扫描)",
        "XAGUSD M5 RSI<6信号稀有(~6次/月)，RSI<8(~11次/月)已确认有效替代",
        "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80但hold=10较短,需监控大hold表现",
        "XAU M5美盘H精确定时策略n值偏小(8-15),需继续积累验证",
        "XAGUSD M5 EU RSI<8全CB扫描n值中等(19-31),hold=30表现最佳"
    ],
    "next_actions": [
        "round46_001: XAUUSD M1 US CB>=3+RSI<10 月度跟踪续跑(第8月)+EU极值继续监控",
        "round46_002: XAUUSD M5 US RSI<6+CB>=1 跨周期验证(第2月)+n积累",
        "round46_003: XAGUSD M5 EU RSI<8+CB>=1 跨周期验证(第2月)+最佳CB阈值确认",
        "round46_004: US500 M5 EU CB>=5+RSI<14 月度跟踪续跑(第6月)+正式纳入确认",
        "round46_005: XAUUSD M1 ASIA CB>=3+RSI<10 跨周期验证(第4月)+CB>=2版本对比",
        "round46_006: US30 M1 EU 持续积累+CP3/3季度复审",
        "round46_007: XAUUSD M5 美盘H15/H19精确定时策略跨周期验证(第2月)",
        "round46_008: XAGUSD M5 RSI<8 vs RSI<6 性能对比+仓位配置建议",
        "round46_009: 关闭做空分支—不再执行做空扫描",
        "round46_010: JP225/US30 M5级别最终评估—考虑移除出M5扫描范围"
    ]
}

# Write to correct location
with open(os.path.join(BASE, 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

# Also write to scripts/state for compatibility
os.makedirs(os.path.join(BASE, 'scripts', 'state'), exist_ok=True)
with open(os.path.join(BASE, 'scripts', 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print(f"✅ Research state updated to Round {state['current_round']}")
print(f"   Last run: {state['last_run']}")
print(f"   Hypotheses: {len(state['hypotheses'])}")
print(f"   Best known: {len(state['best_known'])}")
print(f"   Warnings: {len(state['warnings'])}")
print(f"   Next actions: {len(state['next_actions'])}")
