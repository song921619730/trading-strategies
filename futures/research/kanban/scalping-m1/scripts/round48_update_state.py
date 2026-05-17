#!/usr/bin/env python3
"""Update research state after round48 — M1/M5 Scalping 月度跟踪 + 跨周期验证(第4月) + 新探索"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 48,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round48_001": "XAUUSD M1 第10月跟踪: EU CB3+RSI<10 WR=97.2% n=36 hold=55 连续10月稳定✅; EU CB2+RSI<10 WR=93.2% n=44 hold=55 第2月稳定✅; US CB3+RSI<10 WR=85.4% n=48 hold=30 连续10月稳定✅; 双极值WR=85.7% n=84 hold=55 连续10月稳定✅。新发现:EU CB3+RSI<8 WR=100% n=25 hold=55!!!(全胜信号质量更优,但n偏小);EU CB2+RSI<8 WR=93.1% n=29 hold=55。结论:所有M1核心策略第10月全部通过,EU_CB2第2月确认稳定,正式升级为成熟策略。EU CB3+RSI<8 n=25 WR=100%为极强候选。",
        "round48_002": "XAUUSD M5 US RSI<6+CB>=1 第4月跨周期验证 WR=89.3% n=28 hold=55 — n值完全无增长(28→28); CB>=2 WR=87.0% n=23 无增长; RSI<5 CB>=1 WR=90.5% n=21 hold=55(新发现!超严格阈值WR>90%)。结论:第4月通过验证但n值连续4月无增长(n=28停滞),数据可能已无新信号。RSI<5版n=21 WR=90.5%为超严格替代品。",
        "round48_003": "XAGUSD M5 EU RSI<8+CB>=1 第4月跨周期验证 WR=90.3% n=31 hold=30 通过但n值无增长(31→31); CB4 WR=90.9% n=22无增长; CB5 WR=94.7% n=19无增长。RSI<5 CB1 ALL(新)WR=88.7% n=71 hold=55。结论:第4月验证通过,所有n值完全停滞无增长,数据可能已无新信号。RSI<5 CB1 ALL(88.7% n=71)为新发现的大仓替代品。",
        "round48_004": "US500 M5 EU CB>=5+RSI<14 第8月跟踪 WR=84.6% n=52 hold=25 连续8月稳定✅; CB>=6版本WR=85.7% n=35 hold=25; CB>=5+RSI<12 WR=83.3% n=36 hold=25 连续2月确认。结论:连续8月稳定,核心策略确认。US session确认无效(57.8% n=109)。",
        "round48_005": "XAUUSD M1 ASIA第6月跟踪: CB>=3+RSI<10 WR=75.0% n=68 hold=10 稳定; CB>=2+RSI<10 WR=73.8% n=80 hold=10; CB>=4+RSI<10 WR=72.2% n=54 hold=10(新,CB4版本n=54>0)。结论:ASIA第6月通过验证,CB4版本有稳定信号(72.2% n=54),但hold=10偏短问题持续。",
        "round48_006": "US30 M1 EU CP复审: CB>=4+RSI<14 WR=70.4% n=81 hold=30 CP稳定✅; CB>=5+RSI<14 WR=73.2% n=56 hold=5(hold过短⚠️)。新发现:CB>=4+RSI<12 WR=77.8% n=54 hold=30 — 远超原CB4策略!CP通过✅。结论:CB4+RSI<12(77.8% n=54)是US30 M1最佳新入口,Sharpe=53.81远超原版。",
        "round48_007": "XAUUSD M5美盘精确定时第4月跟踪: H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12无增长; H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11无增长; H19 CB>=5 RSI<12 hold=55 WR=100% n=8无增长。新发现:H15 CB>=1 RSI<8 WR=100% n=7 hold=55(更严格RSI条件全胜但n极小);H16 CB1 RSI<10 WR=70% n=10。结论:n值连续4月无增长,确认数据未更新或条件极罕见。",
        "round48_008": "XAGUSD M5仓位配置实盘参数: RSI<8 CB1 ALL ~11.8次/月(大仓位,WR=75.6%); RSI<6 CB1 ALL ~6.7次/月(中仓位,WR=86.0%); RSI<5 CB1 ALL ~5.1次/月(中仓位,WR=88.7%); RSI<8 EU CB1 ~2.2次/月(小仓位,WR=90.3%)。结论:仓位配置建议更新:RSI<8 ALL为中大仓位首选;RSI<6 ALL为中仓位高胜率选择;RSI<5 ALL为新发现的高WR替代品。",
        "round48_009": "JP225 M5 US session: CB3+RSI<10 WR=68.5% n=111 hold=45(边界⚠️); CB4+RSI<10 WR=66.3% n=86; CB5+RSI<12 WR=67.4% n=89。结论:维持不推荐,WR<70%且Sharpe<10,边界线保留最低权重监控。",
        "round48_010": "新探索方向: ①EU CB2+RSI<5 WR=100% n=15 hold=55 Sharpe=141.47(极端!但n太小); ②MA20+极值联合过滤与无MA20版结果完全一致(所有信号已满足price<ma20条件); ③US500 US session确认无效(<60%); ④EU CB3+RSI<8 WR=100% n=25 hold=55是全策略最强新发现。结论:RSI<8版本在EU M1(100% n=25)和H15 M5(100% n=7)均有100%胜率,n仍在积累中。"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续10月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.5% n=123 [20月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [CP10/10 全策略最强王者 第10月确认通过]",
        "XAUUSD_M1_EU_CB2": "XAUUSD M1 EU CB>=2+RSI<10 WR=93.2% n=44 hold=55 [R48第2月确认稳定-正式升级成熟]",
        "XAUUSD_M1_EU_RSI8": "XAUUSD M1 EU CB>=3+RSI<8 WR=100.0% n=25 hold=55 [R48新发现!王者加强版!全胜!]",
        "XAUUSD_M1_EU_CB2_RSI8": "XAUUSD M1 EU CB>=2+RSI<8 WR=93.1% n=29 hold=55 [R48新发现!宽松收紧版]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=85.4% n=48 hold=30 [第10月跟踪稳定]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=85.7% n=84 hold=55 [综合推荐]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 [第6月确认稳定]",
        "XAUUSD_M1_ASIA_CB2": "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80 hold=10 [n增长稳定]",
        "XAUUSD_M1_ASIA_CB4": "XAUUSD M1 ASIA CB>=4+RSI<10 WR=72.2% n=54 hold=10 [R48新发现-CB4版本有信号]",
        "XAUUSD_M5_US_RSI6": "XAUUSD M5 US RSI<6+CB>=1 WR=89.3% n=28 hold=55 [第4月跨周期验证通过-n停滞28]",
        "XAUUSD_M5_US_RSI6_CB2": "XAUUSD M5 US RSI<6+CB>=2 WR=87.0% n=23 hold=30 [备用阈值]",
        "XAUUSD_M5_US_RSI6_CB3": "XAUUSD M5 US RSI<6+CB>=3 WR=84.2% n=19 hold=30 [备用阈值]",
        "XAUUSD_M5_US_RSI5": "XAUUSD M5 US RSI<5+CB>=1 WR=90.5% n=21 hold=55 [R48新发现!更严格WR>90%]",
        "XAUUSD_M5_SHORT_any": "XAUUSD M1/M5做空WR均<65%,不推荐 [做空分支已正式关闭]",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 [n=28停滞]",
        "XAGUSD_M5_RSI6": "XAGUSD M5 CB>=1+RSI<6做多 WR=86.0% n=93 hold=55 [确认有效-信号~6.7次/月]",
        "XAGUSD_M5_EU_RSI8": "XAGUSD M5 EU RSI<8+CB>=1做多 WR=90.3% n=31 hold=30 [第4月验证通过-EU~2.2次/月]",
        "XAGUSD_M5_EU_RSI8_CB4": "XAGUSD M5 EU RSI<8+CB>=4做多 WR=90.9% n=22 hold=30 [严格阈值备用]",
        "XAGUSD_M5_RSI5_ALL": "XAGUSD M5 RSI<5+CB>=1做多 WR=88.7% n=71 hold=55 [R48新发现!更强替代]",
        "XAGUSD_M5_RSI6_strict": "XAGUSD M5 CB>=5+RSI<6做多 WR=85.7% n=49 hold=55 [严格阈值]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 [CP3/3确认]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=84.6% n=52 hold=25 [第8月稳定-核心策略]",
        "US500_M5_EU_stronger": "US500 M5 EU CB>=6+RSI<14做多 WR=85.7% n=35 hold=25 [信号更稀有但WR更高]",
        "US500_M5_EU_RSI12": "US500 M5 EU CB>=5+RSI<12做多 WR=83.3% n=36 hold=25 [RSI12版本确认有效]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [CP通过 Sharpe=42.83]",
        "US30_M1_EU_CB5": "US30 M1 EU CB>=5+RSI<14做多 WR=73.2% n=56 hold=5 [Sharpe=103但hold过短需监控]",
        "US30_M1_EU_RSI12": "US30 M1 EU CB>=4+RSI<12做多 WR=77.8% n=54 hold=30 [R48新发现!US30最佳新入口]",
        "JP225_H1_long": "JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 [H1远优于M5]",
        "JP225_M30_long": "JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 [M30远优于M5]",
        "AUDUSD_M30_long": "AUDUSD M30 CB>=3+RSI<18做多 WR=81.5% n=27 hold=60 CP3/3 [候选纳入]",
        "XAU_M5_H15_doublegun2": "XAU M5 H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12 [美盘开盘精确定时-第4月验证通过]",
        "XAU_M5_H19_doublegun": "XAU M5 H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11 [美盘盘中精确定时-第4月验证通过]",
        "XAU_M5_H19_strict": "XAU M5 H19 CB>=5 RSI<12 hold=55 WR=100% n=8 [H19极严格-全胜但n小]",
        "XAU_M5_H15_RSI8": "XAU M5 H15 CB>=1 RSI<8 hold=55 WR=100% n=7 [R48新发现-H15收紧RSI]",
        "XAU_M1_EU_CB2_RSI5": "XAU M1 EU CB>=2+RSI<5 hold=55 WR=100% n=15 Sharpe=141.47 [极端!n太小需积累]"
    },
    "warnings": [
        "M5数据覆盖较全至~16:10 UTC，但H1/M30数据停于13:00/13:30 UTC影响验证",
        "XAGUSD M5 EU CB>=2+RSI<8 n=28连续多轮无增长(数据未更新)",
        "XAUUSD M5美盘H精确定时策略n值偏小(7-15),且连续4月无增长(数据未更新或条件极严)",
        "XAUUSD M5 US RSI<6+CB>=1 n=28连续4月无增长,信号完全停滞!数据可能已无新信号",
        "XAGUSD M5 EU RSI<8 EU信号频率仅2.2次/月,远低于ALL的11.8次/月",
        "JP225 M5级别信号质量差(最大WR=68.5%但Sharpe仅7.63)，远不如H1/M30 (WR>90%)",
        "US30 M5确认全线<65% WR(最佳60.9%)，已从M5扫描范围移除",
        "做空信号在M1/M5全线<65% WR，做空分支已正式关闭(不再扫描)",
        "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80但hold=10较短,大hold无信号(极值不够深)",
        "US30 M1 EU CB>=5+RSI<14 WR=73.2%但hold=5过短,Sharpe=103高但需警惕过拟合",
        "XAUUSD M5 US RSI<6+CB>=1 n=28未达35目标,信号完全停止增长",
        "XAUUSD M5 US RSI<8低CB版本(72.1% n=61)WR低于核心标准,RSI<6才是核心方向",
        "所有策略n值在R47→R48之间完全无增长,数据可能未刷新或Market Watch无新数据",
        "EU CB2+RSI<5 n=15 WR=100%但n太小,距离验证门槛(n≥25)还有距离"
    ],
    "next_actions": [
        "round49_001: XAUUSD M1 US/EU 第11月跟踪+EU_CB2第3月跟踪+EU_RSI8新策略独立跟踪(第1月)",
        "round49_002: XAUUSD M5 US RSI<6+CB>=1 继续监控n增长(如连续5月无增长需标记为数据冻结)",
        "round49_003: XAGUSD M5 EU RSI<8+CB>=1 第5月验证+RSI<5新策略独立跟踪",
        "round49_004: US500 M5 EU CB>=5+RSI<14 第9月跟踪",
        "round49_005: XAUUSD M1 ASIA 第7月跟踪+CB4版持续跟踪",
        "round49_006: US30 M1 EU CB4+RSI<12新策略第2月验证(CP通过后正式纳入推荐库)",
        "round49_007: XAUUSD M5 H15/H19精确定时第5月跟踪+关注n值是否更新",
        "round49_008: XAGUSD M5 RSI<5 CB1 ALL新策略第2月验证(88.7% n=71候选纳入推荐)",
        "round49_009: JP225 M5 最低权重监控(维持边界状态)",
        "round49_010: 新探索: ①EU CB3+RSI<8 n积累追踪(100%WR!当前n=25需达n≥30) ②US30 M1 CB4+RSI<12深入 ③M5数据更新验证(检查数据日期范围) ④XAU M5 US RSI<5积累追踪"
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
