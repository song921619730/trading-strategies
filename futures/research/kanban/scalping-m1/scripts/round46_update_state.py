#!/usr/bin/env python3
"""Update research state after round46 — M1/M5 Scalping Monthly Tracking + Cross-Validation"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 46,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round46_001": "XAUUSD M1 US CB>=3+RSI<10第8月跟踪 WR=85.4% n=48 hold=30 连续8月稳定; EU极值97.2% n=36 hold=55 连续8月稳定; 双极值联合85.7% n=84; ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 第4月稳定; ASIA CB>=2+RSI<10 WR=73.8% n=80稳定。结论:所有核心XAU M1策略连续8月稳定通过,正式标记为成熟策略",
        "round46_002": "XAUUSD M5 US RSI<6+CB>=1第2月跨周期验证 WR=89.3% n=28 hold=55 与round44/45数据完全一致; CB>=2版本WR=87.0% n=23。结论:美盘RSI<6策略连续2月跨周期验证通过,信号稳定(28次),可正式纳入核心策略库",
        "round46_003": "XAGUSD M5 EU RSI<8+CB>=1第2月跨周期验证 WR=90.3% n=31 hold=30 确认有效; RSI<8 CB>=4 WR=90.9% n=22; RSI<8 CB>=5 WR=94.7% n=19。结论:RSI<8系列第2月通过验证,数据与第1月一致,正式纳入推荐库",
        "round46_004": "US500 M5 EU CB>=5+RSI<14第6月跟踪 WR=84.6% n=52 hold=25 连续6月稳定; CB>=4版本78.1% n=73; CB>=6版本85.7% n=35 hold=25(新发现)。结论:连续6月稳定,确认纳入核心策略;CB>=6版本信号更少但WR更高(85.7%)",
        "round46_005": "XAUUSD M1 ASIA CB>=3+RSI<10第4月跟踪 WR=75.0% n=68 hold=10 稳定; CB>=2+RSI<10 WR=73.8% n=80。结论:亚洲策略第4月通过验证,信号量充足",
        "round46_006": "US30 M1 EU CB>=4+RSI<14 WR=70.4% n=81 hold=30 CP3/3保持; CB>=5版本WR=73.2% n=56 hold=5(新发现,Sharpe=103)。结论:US30 M1 EU表现稳定,CB>=5版本WR更高但hold=5过短需监控",
        "round46_007": "XAUUSD M5美盘精确定时策略第2月跨周期验证: H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12; H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11; H19 CB>=5 RSI<12 hold=55 WR=100% n=8。结论:精确定时策略第2月验证通过,数据一致(信号极稀有但质量极高)",
        "round46_008": "XAGUSD M5 RSI<8 vs RSI<6性能对比: RSI<6 CB1 ALL WR=86.0% n=93(~8次/月) vs RSI<8 CB1 ALL WR=75.6% n=164(~14次/月); EU RSI<8 CB1 WR=90.3% n=31(~11次/月)。结论:RSI<6信号稀有(6次/月)适合大仓位; RSI<8 EU信号更多(11次/月)适合常规仓位; RSI<10 WR<65%不推荐",
        "round46_009": "做空分支保持关闭(已确认关闭)",
        "round46_010": "JP225 M5最佳WR=68.5% n=111,虽>65%但Sharpe仅7.63且平均收益低(0.147%),维持不推荐; US30 M5最佳WR=60.9%全线<65%。结论:US30 M5可移除出M5扫描范围,JP225 M5继续监控但权重下调"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续10月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.5% n=123 [20月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [CP8/8 全策略最强王者 第8月确认通过]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=85.4% n=48 hold=30 [第8月跟踪稳定]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=85.7% n=84 hold=55 [综合推荐]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=3+RSI<10 WR=75.0% n=68 hold=10 [第4月确认稳定]",
        "XAUUSD_M1_ASIA_CB2": "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80 hold=10 [n增长稳定]",
        "XAUUSD_M5_US_RSI6": "XAUUSD M5 US RSI<6+CB>=1 WR=89.3% n=28 hold=55 [第2月跨周期验证通过-正式纳入核心]",
        "XAUUSD_M5_US_RSI6_CB2": "XAUUSD M5 US RSI<6+CB>=2 WR=87.0% n=23 hold=30 [备用阈值]",
        "XAUUSD_M5_SHORT_any": "XAUUSD M1/M5做空WR均<65%,不推荐 [做空分支已正式关闭]",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 [n=28停滞-数据未更新]",
        "XAGUSD_M5_RSI6": "XAGUSD M5 CB>=1+RSI<6做多 WR=86.0% n=93 hold=55 [确认有效-信号稀有~8次/月]",
        "XAGUSD_M5_EU_RSI8": "XAGUSD M5 EU RSI<8+CB>=1做多 WR=90.3% n=31 hold=30 [最佳综合入口~11次/月-第2月验证通过]",
        "XAGUSD_M5_EU_RSI8_CB4": "XAGUSD M5 EU RSI<8+CB>=4做多 WR=90.9% n=22 hold=30 [严格阈值备用]",
        "XAGUSD_M5_RSI6_strict": "XAGUSD M5 CB>=5+RSI<6做多 WR=85.7% n=49 hold=55 [严格阈值]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 [CP3/3确认]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=84.6% n=52 hold=25 [第6月稳定-核心策略]",
        "US500_M5_EU_stronger": "US500 M5 EU CB>=6+RSI<14做多 WR=85.7% n=35 hold=25 [新发现-信号更稀有但WR更高]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [CP3/3达标 Sharpe=42.83]",
        "US30_M1_EU_CB5": "US30 M1 EU CB>=5+RSI<14做多 WR=73.2% n=56 hold=5 [新发现-更高WR但hold过短需监控]",
        "JP225_H1_long": "JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 [H1远优于M5]",
        "JP225_M30_long": "JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 [M30远优于M5]",
        "AUDUSD_M30_long": "AUDUSD M30 CB>=3+RSI<18做多 WR=81.5% n=27 hold=60 CP3/3 [候选纳入]",
        "XAU_M5_H15_doublegun2": "XAU M5 H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12 [美盘开盘精确定时-第2月验证通过]",
        "XAU_M5_H19_doublegun": "XAU M5 H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11 [美盘盘中精确定时-第2月验证通过]",
        "XAU_M5_H19_strict": "XAU M5 H19 CB>=5 RSI<12 hold=55 WR=100% n=8 [H19极严格-全胜但n小]"
    },
    "warnings": [
        "M5数据覆盖较全至16:10 UTC，但H1/M30数据停于13:00/13:30 UTC影响验证",
        "XAGUSD M5 EU CB>=2+RSI<8 n=28连续多轮无增长(数据未更新-可能已无新信号)",
        "JP225 M5级别信号质量差(最大WR=68.5%但Sharpe仅7.63)，远不如H1/M30 (WR>90%)",
        "US30 M5确认全线<65% WR(最佳60.9%)，建议从M5扫描范围移除",
        "做空信号在M1/M5全线<65% WR，做空分支已正式关闭(不再扫描)",
        "XAGUSD M5 RSI<6信号稀有(~8次/月)，RSI<8(~11次/月)是更好替代但WR较低(75.6%无session过滤)",
        "XAUUSD M1 ASIA CB>=2+RSI<10 WR=73.8% n=80但hold=10较短,需监控大hold表现",
        "XAU M5美盘H精确定时策略n值偏小(8-15),需继续积累验证",
        "US30 M1 EU CB>=5+RSI<14 WR=73.2%但hold=5过短,Sharpe=103高但需警惕过拟合"
    ],
    "next_actions": [
        "round47_001: XAUUSD M1 US CB>=3+RSI<10 季度复审(第9月检查)+EU极值确认成熟标签",
        "round47_002: XAUUSD M5 US RSI<6+CB>=1 跨周期验证(第3月)+n积累目标n≥35",
        "round47_003: XAGUSD M5 EU RSI<8+CB>=1 跨周期验证(第3月)+仓位配置验证",
        "round47_004: US500 M5 EU CB>=5+RSI<14 月度跟踪(第7月)+CB>=6版本对比监控",
        "round47_005: XAUUSD M1 ASIA 第5月跟踪+大hold测试(hold=30/55)",
        "round47_006: US30 M1 EU CB>=4 vs CB>=5 对比+hold=10/20验证CB>=5稳定性",
        "round47_007: XAUUSD M5 美盘H15/H19精确定时第3月跟踪+n积累",
        "round47_008: XAGUSD M5 仓位配置模拟: RSI<6(大仓位) vs RSI<8 EU(常规仓位) vs RSI<8 ALL(轻仓位)",
        "round47_009: US30 M5从扫描范围移除确认",
        "round47_010: JP225 M5权重下调+仅保留US session监控"
    ]
}

# Write to state directory
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
