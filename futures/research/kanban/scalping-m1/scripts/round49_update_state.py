#!/usr/bin/env python3
"""Update research state after round49 — M1/M5 Scalping 月度跟踪(第11/9/7月) + 跨周期验证(第5月) + 新探索"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 49,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round49_001": "XAUUSD M1 第11月跟踪: EU CB3+RSI<10 WR=97.2% n=36 hold=55 连续11月稳定✅; EU CB2+RSI<10 WR=93.2% n=44 hold=55 第3月确认稳定✅(CP3/3正式成熟); US CB3+RSI<10 WR=85.4% n=48 hold=30 连续11月稳定✅; 双极值WR=85.7% n=84 hold=55 连续11月稳定✅。EU_RSI8第1月独立跟踪: EU CB3+RSI<8 WR=100.0% n=25 hold=55(维持全胜,但n未增长); EU CB2+RSI<8 WR=93.1% n=29。结论:所有M1核心策略第11月全部通过,EU_CB2第3月确认正式成熟。EU CB3+RSI<8仍维持100%但n停滞25。",
        "round49_002": "XAUUSD M5 US RSI<6+CB>=1 第5次监控 WR=89.3% n=28 hold=55 — n值连续5月完全无增长(28→28→28→28→28)。结论:❗连续5月无增长,正式标记为数据冻结。数据源可能不再产生新信号(条件过于严格或MT5数据无新记录)。RSI<5版WR=90.5% n=21同样停滞。建议关注数据更新机制。",
        "round49_003": "XAGUSD M5 EU RSI<8+CB>=1 第5月验证 WR=90.3% n=31 hold=30 — 通过但n值连续5月无增长(31→31); CB4 WR=90.9% n=22无增长。RSI<5 CB1 ALL第2月验证 WR=88.7% n=71 hold=55 — 第2月确认稳定✅,候选纳入推荐库。结论:第5月验证通过,EU版本n停滞问题持续。RSI<5 ALL第2月通过,CP2/2建议正式纳入推荐。",
        "round49_004": "US500 M5 EU CB>=5+RSI<14 第9月跟踪 WR=84.6% n=52 hold=25 连续9月稳定✅; CB>=6版本WR=85.7% n=35 hold=25; CB>=5+RSI<12 WR=83.3% n=36 hold=25; CB6+RSI12新发现WR=84.6% n=26 hold=25 Sharpe=45.78(高Sharpe!).结论:连续9月稳定,核心策略确认。新发现的CB6+RSI12版本Sharpe=45.78极优。",
        "round49_005": "XAUUSD M1 ASIA第7月跟踪: CB>=3+RSI<10 WR=75.0% n=68 hold=10 稳定; CB>=2+RSI<10 WR=73.8% n=80 hold=10; CB>=4+RSI<10 WR=72.2% n=54 hold=10。结论:ASIA第7月通过验证,hold=10偏短问题持续。",
        "round49_006": "US30 M1 EU CB4+RSI<12第2月验证 WR=77.8% n=54 hold=30 — CP通过✅第2月确认稳定!正式纳入推荐库。新发现:CB5+RSI<12 WR=80.0% n=40 hold=30 Sharpe=74.13更强!CB4+RSI<10 WR=77.8% n=36 hold=10(更严格版本但hold偏短)。结论:CB4+RSI<12 CP2/2确认推荐,CB5+RSI<12(80.0%)为新最强候选。",
        "round49_007": "XAUUSD M5 H15/H19精确定时第5月跟踪: H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12无增长; H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11无增长; H19 CB>=5 RSI<12 hold=55 WR=100% n=8无增长; H15 CB>=1 RSI<8 WR=100% n=7无增长。结论:n值连续5月无增长,确认数据冻结,H精确定时策略已无新增信号。",
        "round49_008": "XAGUSD M5 RSI<5 CB1 ALL第2月验证 WR=88.7% n=71 hold=55 Sharpe=20.70 — 第2月确认稳定✅。信号频率~5.1次/月(中仓位)。结论:正式纳入推荐库,替代RSI<6 CB1 ALL(86.0%)成为更高WR的中仓位选项。",
        "round49_009": "JP225 M5 US session第9月监控: CB3+RSI<10 WR=68.5% n=111 hold=45(边界); CB4+RSI<10 WR=66.3% n=86; CB5+RSI<12 WR=67.4% n=89。结论:维持不推荐,WR<70%且Sharpe<10(最佳7.63),边界线保留最低权重监控。",
        "round49_010": "新探索: ①EU CB3+RSI<7 WR=100.0% n=19 hold=55 Sharpe=69.24(新发现!RSI收紧至7仍100%全胜,但n=19<25需积累); ②US30 M1 CB5+RSI<12 WR=80.0% n=40 hold=30(最强US30版本!); ③M5数据更新验证: XAUUSD M5数据截至2026-05-13 16:10 UTC已含当日数据但无新信号产生,确认n值停滞非数据问题而是条件过于严格; ④XAU M5 US RSI<5 n=21停滞。结论:EU CB3+RSI<7(100% n=19)和US30 CB5+RSI<12(80% n=40)为新发现的最佳候选。"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续10月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.5% n=123 [20月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [CP11/11 全策略最强王者 第11月确认通过]",
        "XAUUSD_M1_EU_CB2": "XAUUSD M1 EU CB>=2+RSI<10 WR=93.2% n=44 hold=55 [R49第3月确认稳定-正式成熟]",
        "XAUUSD_M1_EU_RSI8": "XAUUSD M1 EU CB>=3+RSI<8 WR=100.0% n=25 hold=55 [第1月独立跟踪-维持全胜]",
        "XAUUSD_M1_EU_CB2_RSI8": "XAUUSD M1 EU CB>=2+RSI<8 WR=93.1% n=29 hold=55 [R49维持稳定]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=85.4% n=48 hold=30 [第11月跟踪稳定]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=85.7% n=84 hold=55 [综合推荐]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 [第7月确认稳定]",
        "XAUUSD_M1_ASIA_CB2": "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80 hold=10 [n增长稳定]",
        "XAUUSD_M1_ASIA_CB4": "XAUUSD M1 ASIA CB>=4+RSI<10 WR=72.2% n=54 hold=10 [持续稳定]",
        "XAUUSD_M5_US_RSI6": "XAUUSD M5 US RSI<6+CB>=1 WR=89.3% n=28 hold=55 [❗数据冻结-连续5月n=28]",
        "XAUUSD_M5_US_RSI6_CB2": "XAUUSD M5 US RSI<6+CB>=2 WR=87.0% n=23 hold=30 [备用阈值]",
        "XAUUSD_M5_US_RSI6_CB3": "XAUUSD M5 US RSI<6+CB>=3 WR=84.2% n=19 hold=30 [备用阈值]",
        "XAUUSD_M5_US_RSI5": "XAUUSD M5 US RSI<5+CB>=1 WR=90.5% n=21 hold=55 [RSI5版本-n冻结]",
        "XAUUSD_M5_SHORT_any": "XAUUSD M1/M5做空WR均<65%,不推荐 [做空分支已正式关闭]",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 [n=28停滞]",
        "XAGUSD_M5_RSI6": "XAGUSD M5 CB>=1+RSI<6做多 WR=86.0% n=93 hold=55 [确认有效-信号~6.7次/月]",
        "XAGUSD_M5_EU_RSI8": "XAGUSD M5 EU RSI<8+CB>=1做多 WR=90.3% n=31 hold=30 [第5月验证通过-数据冻结]",
        "XAGUSD_M5_EU_RSI8_CB4": "XAGUSD M5 EU RSI<8+CB>=4做多 WR=90.9% n=22 hold=30 [严格阈值备用]",
        "XAGUSD_M5_RSI5_ALL": "XAGUSD M5 RSI<5+CB>=1做多 WR=88.7% n=71 hold=55 [R49第2月确认-正式纳入推荐!]",
        "XAGUSD_M5_RSI6_strict": "XAGUSD M5 CB>=5+RSI<6做多 WR=85.7% n=49 hold=55 [严格阈值]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 [CP3/3确认]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=84.6% n=52 hold=25 [第9月稳定-核心策略]",
        "US500_M5_EU_stronger": "US500 M5 EU CB>=6+RSI<14做多 WR=85.7% n=35 hold=25 [信号更稀有但WR更高]",
        "US500_M5_EU_RSI12": "US500 M5 EU CB>=5+RSI<12做多 WR=83.3% n=36 hold=25 [RSI12版本确认有效]",
        "US500_M5_EU_CB6_RSI12": "US500 M5 EU CB>=6+RSI<12做多 WR=84.6% n=26 hold=25 [R49新发现!高Sharpe=45.78]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [CP通过 Sharpe=42.83]",
        "US30_M1_EU_CB5": "US30 M1 EU CB>=5+RSI<14做多 WR=73.2% n=56 hold=5 [Sharpe=103但hold过短需监控]",
        "US30_M1_EU_RSI12": "US30 M1 EU CB>=4+RSI<12做多 WR=77.8% n=54 hold=30 [R49第2月确认!正式纳入推荐]",
        "US30_M1_EU_CB5_RSI12": "US30 M1 EU CB>=5+RSI<12做多 WR=80.0% n=40 hold=30 [R49新发现!US30最强版本]",
        "US30_M1_EU_CB4_RSI10": "US30 M1 EU CB>=4+RSI<10做多 WR=77.8% n=36 hold=10 [R49新发现!严格阈值版]",
        "XAU_M1_EU_CB3_RSI7": "XAU M1 EU CB>=3+RSI<7做多 WR=100.0% n=19 hold=55 [R49新发现!王者再升级-RSI7]",
        "JP225_H1_long": "JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 [H1远优于M5]",
        "JP225_M30_long": "JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 [M30远优于M5]",
        "AUDUSD_M30_long": "AUDUSD M30 CB>=3+RSI<18做多 WR=81.5% n=27 hold=60 CP3/3 [候选纳入]",
        "XAU_M5_H15_doublegun2": "XAU M5 H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12 [美盘开盘精确定时-第5月通过-数据冻结]",
        "XAU_M5_H19_doublegun": "XAU M5 H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11 [美盘盘中精确定时-第5月通过-数据冻结]",
        "XAU_M5_H19_strict": "XAU M5 H19 CB>=5 RSI<12 hold=55 WR=100% n=8 [H19极严格-全胜但n小]",
        "XAU_M5_H15_RSI8": "XAU M5 H15 CB>=1 RSI<8 hold=55 WR=100% n=7 [H15收紧RSI-数据冻结]",
        "XAU_M1_EU_CB2_RSI5": "XAU M1 EU CB>=2+RSI<5 hold=55 WR=100% n=15 Sharpe=141.47 [极端!n太小需积累]"
    },
    "warnings": [
        "❗XAUUSD M5 US RSI<6+CB>=1 n=28连续5月无增长 — 正式标记为数据冻结,数据无更新",
        "❗XAUUSD M5美盘H精确定时所有策略连续5月无增长(n=7-12) — 数据冻结",
        "❗XAGUSD M5 EU RSI<8+CB>=1 n=31连续5月无增长 — 数据冻结",
        "M5数据截至2026-05-13 16:10 UTC虽已含当日数据,但极严格条件已无新信号",
        "H1/M30数据停于13:00/13:30 UTC影响验证(数据来源限制)",
        "XAGUSD M5 EU RSI<8 EU信号频率仅2.2次/月,远低于ALL的11.8次/月",
        "JP225 M5级别信号质量差(最大WR=68.5%但Sharpe仅7.63)，远不如H1/M30 (WR>90%)",
        "US30 M5确认全线<65% WR(最佳60.9%)，已从M5扫描范围移除",
        "做空信号在M1/M5全线<65% WR，做空分支已正式关闭(不再扫描)",
        "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80但hold=10较短,大hold无信号(极值不够深)",
        "US30 M1 EU CB5+RSI<14 WR=73.2%但hold=5过短,Sharpe=103高但需警惕过拟合",
        "EU CB3+RSI<7 WR=100% n=19但n<25,距验证门槛还有距离",
        "EU CB2+RSI<5 n=15 WR=100%但n太小,距离验证门槛(n≥25)还有距离"
    ],
    "next_actions": [
        "round50_001: XAUUSD M1 US/EU 第12月跟踪(年度审查)+EU_CB2第4月+EU_RSI8第2月跟踪+CB3+RSI7新独立跟踪(第1月)",
        "round50_002: XAUUSD M5 US RSI<6+CB>=1 数据冻结正式归档,转为季度检查(每3个月检查一次数据是否恢复)",
        "round50_003: XAGUSD M5 EU RSI<8+CB>=1 数据冻结归档+RSI<5 CB1 ALL第3月跟踪(正式纳入推荐后)",
        "round50_004: US500 M5 EU CB>=5+RSI<14 第10月跟踪(年度审查)+CB6+RSI12新策略跟踪",
        "round50_005: XAUUSD M1 ASIA 第8月跟踪",
        "round50_006: US30 M1 EU CB4+RSI<12第3月跟踪+CB5+RSI<12第2月验证(推荐候选)+CB4+RSI<10跟踪",
        "round50_007: XAUUSD M5 H15/H19精确定时数据冻结归档(季度检查恢复)",
        "round50_008: XAGUSD M5 RSI<5 CB1 ALL第3月跟踪(正式纳入推荐库后质量监控)",
        "round50_009: JP225 M5 最低权重监控(维持边界)",
        "round50_010: 新探索: ①EU CB3+RSI<7 n积累追踪(100%!n=19需达n≥25) ②US30 CB5+RSI<12积累 ③XAU M5数据源检查(是否可扩展) ④考虑切换到H1/M30级别扫描新品种"
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
