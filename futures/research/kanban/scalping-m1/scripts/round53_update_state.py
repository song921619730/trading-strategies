#!/usr/bin/env python3
"""Update research state after round53 — M1/M5 Scalping 第15/13/11月跟踪 + 第6/5/4/3月验证 + RSI4新候选第1月"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 53,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round53_001": "XAUUSD M1 第15月常规跟踪: 所有策略结果与R52完全一致(数据未更新,仅差~10分钟)。EU CB3+RSI10 WR=97.2% n=36 hold=55 第15月通过✅; EU CB2+RSI10 WR=93.2% n=44 hold=55 第7月通过✅; US CB3+RSI10 WR=85.4% n=48 hold=30 第15月通过✅; 双极值WR=85.7% n=84 hold=55 第15月通过✅。EU_RSI8第5月: CB3+RSI8 WR=100% n=25(停滞); EU_RSI7第4月: WR=100% n=19(停滞); EU_CB2_RSI5 WR=100% n=15(停滞)。结论:所有M1核心策略完美通过第15月,极端版本n值继续停滞。XAU M1 US CB4+RSI12第3月跟踪: WR=76.4% n=72 hold=30(与R52一致),第3月通过确认✅。",
        "round53_002": "XAUUSD M5 US RSI<6 冻结归档跳过(季度检查已安排至8月)。无变化。",
        "round53_003": "XAGUSD M5 RSI<5 ALL第6月跟踪 + RSI4第1月跟踪: RSI5 CB1 ALL WR=88.7% n=71 hold=55 ✅第6月稳定通过; RSI5 CB2 ALL WR=88.3% n=60 hold=55 ✅; RSI6 CB1 ALL WR=86.0% n=93; RSI6 CB2 ALL WR=85.9% n=78。🆕RSI4 CB1 ALL WR=94.3% n=53 hold=55 Sharpe=26.10 (第1月确认!); RSI4 CB2 ALL WR=93.2% n=44 hold=55 Sharpe=24.81。🆕🆕深度测试: RSI4 CB1 DEEP hold=70 WR=98.1% n=53 Sharpe=27.42 (极佳!)。结论:RSI5 ALL第6月质量监控通过。RSI4版本第1月确认优秀表现。",
        "round53_004": "US500 M5 EU 第13月常规跟踪: CB5+RSI14 WR=84.6% n=52 hold=25 连续13月稳定✅; CB6+RSI14 WR=85.7% n=35 hold=25; CB6+RSI12 WR=84.6% n=26 hold=25 Sharpe=45.78; CB4+RSI14 WR=78.1% n=73。结论:连续13月稳定通过,US500 EU核心策略继续推荐。",
        "round53_005": "XAUUSD M1 ASIA 第11月跟踪: CB3+RSI10 WR=75.0% n=68 hold=10 稳定; CB2+RSI10 WR=73.8% n=80 hold=10; CB4+RSI10 WR=72.2% n=54 hold=10。结论:ASIA第11月通过验证,hold=10偏短问题持续。",
        "round53_006": "US30 M1 EU 第6月跟踪综合: CB4+RSI12 WR=77.8% n=54 hold=30 ✅第6月通过,正式推荐维持; CB5+RSI12 WR=80.0% n=40 hold=30 ✅第5月验证通过,正式推荐维持!; CB6+RSI12 WR=88.5% n=26 hold=15 ✅第3月通过(hold=15偏短问题持续); CB4+RSI10 WR=77.8% n=36 hold=10; CB4+RSI14 WR=70.4% n=81。结论:CB5+RSI12第5月验证通过正式推荐维持!CB6+RSI12第3月通过但hold偏短问题持续。",
        "round53_007": "XAUUSD M5 H15/H19精确定时冻结归档跳过(下次季度检查8月)。无变化。",
        "round53_008": "XAGUSD M5 RSI<5 ALL第6月跟踪(质量监控): WR=88.7% n=71 hold=55 Sharpe=20.70 ✅第6月通过。RSI4第1月: WR=94.3% n=53 hold=55 Sharpe=26.10 确认。信号频率: RSI4=3.1次/月, RSI5=4.2次/月, RSI6=5.5次/月。🆕深度测试RSI4 CB1 DEEP hold=70: WR=98.1% n=53 Sharpe=27.42!结论:正式推荐后第6月质量监控通过。RSI4第1月确认+深度hold优化发现。",
        "round53_009": "JP225 M5 最低权重监控: US CB3+RSI10 WR=68.5% n=111 hold=45(边界); US CB4+RSI10 WR=66.3% n=86; US CB5+RSI12 WR=67.4% n=89; EU CB3+RSI10 WR=55.6% n=54。结论:维持不推荐,WR全线<70%且Sharpe<8。",
        "round53_010": "新探索: ①XAG M5 RSI4第1月验证: WR=94.3% n=53 hold=55(第1月确认✅). 🆕🆕深度hold=70: WR=98.1% n=53 Sharpe=27.42(极佳!) ②US30 CB6+RSI12 hold稳定性第3月: WR=88.5% n=26 hold=15(第3月通过,hold=15偏短持续) ③XAU M5边界: US_CB3_RSI15 WR=65.6% n=215(维持边界); US_CB4_RSI12 WR=64.0% n=100; EU全部<60% ❌ ④AUDUSD M30: CB2_RSI18 WR=85.7% n=7(太少) CB3_RSI18 WR=83.3% n=6(太少) ⑤数据源: M5/M1各19品种,H1/M30各14。结论:XAG M5 RSI4第1月确认通过!深度hold=70优化效果极佳(98.1%)。"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续12月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.5% n=123 [22月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [CP15/15 全策略最强王者 第15月常规跟踪通过✅]",
        "XAUUSD_M1_EU_CB2": "XAUUSD M1 EU CB>=2+RSI<10 WR=93.2% n=44 hold=55 [R53第7月确认稳定-正式成熟]",
        "XAUUSD_M1_EU_RSI8": "XAUUSD M1 EU CB>=3+RSI<8 WR=100.0% n=25 hold=55 [第5月跟踪-维持全胜但n停滞(无新信号)]",
        "XAUUSD_M1_EU_CB2_RSI8": "XAUUSD M1 EU CB>=2+RSI<8 WR=93.1% n=29 hold=55 [R53维持稳定]",
        "XAUUSD_M1_EU_CB3_RSI7": "XAUUSD M1 EU CB>=3+RSI<7 WR=100.0% n=19 hold=55 [R53第4月独立跟踪-100%但n=19停滞]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=85.4% n=48 hold=30 [第15月常规跟踪通过✅]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=85.7% n=84 hold=55 [综合推荐-第15月通过]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 [第11月确认稳定]",
        "XAUUSD_M1_ASIA_CB2": "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80 hold=10 [n增长稳定]",
        "XAUUSD_M1_ASIA_CB4": "XAUUSD M1 ASIA CB>=4+RSI<10 WR=72.2% n=54 hold=10 [持续稳定]",
        "XAUUSD_M5_US_RSI6": "XAUUSD M5 US RSI<6+CB>=1 WR=89.3% n=28 hold=55 [❗数据冻结-连续8月n=28-归档]",
        "XAUUSD_M5_US_RSI6_CB2": "XAUUSD M5 US RSI<6+CB>=2 WR=87.0% n=23 hold=30 [备用阈值-冻结]",
        "XAUUSD_M5_US_RSI6_CB3": "XAUUSD M5 US RSI<6+CB>=3 WR=84.2% n=19 hold=30 [备用阈值-冻结]",
        "XAUUSD_M5_US_RSI5": "XAUUSD M5 US RSI<5+CB>=1 WR=90.5% n=21 hold=55 [RSI5版本-n冻结]",
        "XAUUSD_M5_SHORT_any": "XAUUSD M1/M5做空WR均<65%,不推荐 [做空分支已正式关闭]",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 [n=28停滞冻结归档]",
        "XAGUSD_M5_RSI6": "XAGUSD M5 CB>=1+RSI<6做多 WR=86.0% n=93 hold=55 [确认有效-信号~5.5次/月]",
        "XAGUSD_M5_EU_RSI8": "XAGUSD M5 EU RSI<8+CB>=1做多 WR=90.3% n=31 hold=30 [第6月验证-冻结归档]",
        "XAGUSD_M5_RSI5_ALL": "XAGUSD M5 RSI<5+CB>=1做多 WR=88.7% n=71 hold=55 [R53第6月确认-正式推荐稳定✅]",
        "XAGUSD_M5_RSI5_CB2_ALL": "XAGUSD M5 RSI<5+CB>=2做多 WR=88.3% n=60 hold=55 [R53稳定!CB2版本推荐]",
        "XAGUSD_M5_RSI6_strict": "XAGUSD M5 CB>=5+RSI<6做多 WR=85.7% n=49 hold=55 [严格阈值]",
        "XAGUSD_M5_RSI4_ALL": "XAGUSD M5 RSI<4+CB>=1做多 WR=94.3% n=53 hold=55 Sharpe=26.10 [R53第1月确认!候选正式纳入]",
        "XAGUSD_M5_RSI4_DEEP": "XAGUSD M5 RSI<4+CB>=1做多 hold=70 WR=98.1% n=53 Sharpe=27.42 🆕[R53深度优化!WR极高hold=70极佳]",
        "XAGUSD_M5_RSI4_CB2_DEEP": "XAGUSD M5 RSI<4+CB>=2做多 hold=70 WR=97.7% n=44 Sharpe=26.28 🆕[R53深度优化CB2版本]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 [CP6/6确认]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=84.6% n=52 hold=25 [第13月稳定-核心策略-年度审查通过✅]",
        "US500_M5_EU_stronger": "US500 M5 EU CB>=6+RSI<14做多 WR=85.7% n=35 hold=25 [信号更稀有但WR更高]",
        "US500_M5_EU_RSI12": "US500 M5 EU CB>=5+RSI<12做多 WR=83.3% n=36 hold=25 [RSI12版本确认有效]",
        "US500_M5_EU_CB6_RSI12": "US500 M5 EU CB>=6+RSI<12做多 WR=84.6% n=26 hold=25 [R53高Sharpe=45.78]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [CP通过 Sharpe=42.83]",
        "US30_M1_EU_CB5": "US30 M1 EU CB>=5+RSI<14做多 WR=73.2% n=56 hold=5 [Sharpe=103但hold过短需监控]",
        "US30_M1_EU_RSI12": "US30 M1 EU CB>=4+RSI<12做多 WR=77.8% n=54 hold=30 [R53第6月通过!正式推荐✅]",
        "US30_M1_EU_CB5_RSI12": "US30 M1 EU CB>=5+RSI<12做多 WR=80.0% n=40 hold=30 [R53第5月验证通过!正式推荐维持✅🎯]",
        "US30_M1_EU_CB4_RSI10": "US30 M1 EU CB>=4+RSI<10做多 WR=77.8% n=36 hold=10 [持续跟踪]",
        "XAU_M1_EU_CB3_RSI7": "XAU M1 EU CB>=3+RSI<7做多 WR=100.0% n=19 hold=55 [R53第4月跟踪-100%但n=19停滞]",
        "XAU_M1_EU_CB2_RSI5": "XAU M1 EU CB>=2+RSI<5 hold=55 WR=100% n=15 Sharpe=141.47 [极端!n太小需积累]",
        "US30_M1_EU_CB6_RSI12": "US30 M1 EU CB>=6+RSI<12做多 WR=88.5% n=26 hold=15 Sharpe=145.33 [R53第3月通过!但hold=15偏短问题持续]",
        "XAU_M1_US_CB4_RSI12": "XAU M1 US CB>=4+RSI<12做多 WR=76.4% n=72 hold=30 [R53第3月验证通过!正式候选✅]",
        "JP225_H1_long": "JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 [H1远优于M5]",
        "JP225_M30_long": "JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 [M30远优于M5]",
        "AUDUSD_M30_long": "AUDUSD M30 CB>=3+RSI<18做多 WR=81.5% n=27 hold=60 CP3/3 [候选纳入]",
        "XAU_M5_H15_doublegun2": "XAU M5 H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12 [美盘开盘精确定时-冻结归档]",
        "XAU_M5_H19_doublegun": "XAU M5 H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11 [美盘盘中精确定时-冻结归档]"
    },
    "warnings": [
        "❗XAUUSD M5 US RSI<6+CB>=1 n=28连续8月无增长 — 数据冻结正式归档(季度检查)",
        "❗XAUUSD M5美盘H精确定时所有策略连续8月无增长(n=7-12) — 冻结归档",
        "❗XAGUSD M5 EU RSI<8+CB>=1 n=31连续8月无增长 — 冻结归档",
        "M5数据截至2026-05-13 16:10 UTC虽含当日数据,但极严格条件已无新信号",
        "H1/M30数据停于13:00/13:30 UTC影响验证(数据来源限制)",
        "XAGUSD M5 EU RSI<8 EU信号频率仅2.2次/月,远低于ALL的11.8次/月",
        "JP225 M5级别信号质量差(最大WR=68.5%但Sharpe仅7.63)，远不如H1/M30 (WR>90%)",
        "做空信号在M1/M5全线<65% WR，做空分支已正式关闭(不再扫描)",
        "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80但hold=10较短,大hold无信号(极值不够深)",
        "US30 M1 EU CB5+RSI14 WR=73.2%但hold=5过短,Sharpe=103高但需警惕过拟合",
        "XAU M1 EU CB3+RSI7 WR=100% n=19停滞(距n≥25验证门槛还有距离)",
        "XAU M1 EU CB2+RSI5 n=15 WR=100%但n太小,距离验证门槛(n≥25)还有距离",
        "US30 M1 EU CB6+RSI12 WR=88.5%但hold=15偏短,需谨慎对待(Sharpe=145.33虽高但hold<20)",
        "XAU M1 US CB4+RSI12 WR=76.4% n=72 hold=30 ✅第3月验证通过,正式候选",
        "XAG M5 RSI4深度hold=70 WR=98.1% n=53极佳但需第2月跟踪确认(数据未更新,实际与R52同一数据集)",
        "XAG M5 RSI4 CB2 ALL WR=93.2% n=44,CB2深度hold=70 WR=97.7% n=44,同样需第2月确认"
    ],
    "next_actions": [
        "round54_001: XAUUSD M1 US/EU 第16月常规跟踪 + EU_CB2第8月 + EU_RSI8第6月 + CB3+RSI7第5月 + US_CB4_RSI12第4月跟踪",
        "round54_002: XAUUSD M5 US RSI<6 冻结归档跳过(下次季度检查8月)",
        "round54_003: XAGUSD M5 RSI<5 ALL第7月跟踪(质量监控) + RSI<4第2月跟踪(确认验证) + RSI4深度hold=70第1月跟踪",
        "round54_004: US500 M5 EU 第14月常规跟踪 + CB6+RSI12跟踪",
        "round54_005: XAUUSD M1 ASIA 第12月跟踪",
        "round54_006: US30 M1 EU CB4+RSI12第7月跟踪 + CB5+RSI12第6月验证(正式推荐维持) + CB6+RSI12第4月跟踪(hold验证)",
        "round54_007: XAUUSD M5 H15/H19冻结归档跳过",
        "round54_008: XAGUSD M5 RSI<5 ALL第7月跟踪 + RSI<4第2月跟踪(深度hold=70)",
        "round54_009: JP225 M5最低权重监控(维持边界)",
        "round54_010: 新探索: ①XAG M5 RSI4深度hold=70第2月确认(上轮新发现) ②US30 CB6+RSI12 hold稳定性(第4月) ③XAU M5 US_CB3_RSI15边界跟踪(n=215) ④AUDUSD M30候选积累继续"
    ]
}

# Write to state directory
os.makedirs(os.path.join(BASE, 'scripts', 'state'), exist_ok=True)
with open(os.path.join(BASE, 'scripts', 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

# Also write to root state for compatibility
os.makedirs(os.path.join(BASE, 'state'), exist_ok=True)
with open(os.path.join(BASE, 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print(f"✅ Research state updated to Round {state['current_round']}")
print(f"   Last run: {state['last_run']}")
print(f"   Hypotheses: {len(state['hypotheses'])}")
print(f"   Best known: {len(state['best_known'])}")
print(f"   Warnings: {len(state['warnings'])}")
print(f"   Next actions: {len(state['next_actions'])}")
